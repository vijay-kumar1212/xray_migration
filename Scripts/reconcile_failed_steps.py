"""
Reconcile test steps for rows in the migration report where
'Status of Adding Steps to Xray' == 'Failed'.

Workflow (per row):
  1. Read the migration report and keep only Failed rows. Each row gives
     us: Test Rail Id (e.g. 'C1468070') and its Xray Key (e.g. 'OMNIA-123').
  2. Fetch the TestRail case via TestRailClient.get_case() and read
     'custom_steps_separated'.
  3. Fetch the current Xray test via XrayClient.get_test_case() and read
     the steps array (GraphQL getTest.steps).
  4. Compute the 'effective' TestRail step count using the same filter
     XrayClient.add_steps_to_the_test_case() applies (steps whose stripped
     action AND expected are both empty are skipped).
  5. If effective TestRail count == Xray count -> mark 'Already Matches'.
     Otherwise call add_steps_to_the_test_case(), which appends the
     TestRail steps (with attachments) via the addTestStep mutation.
  6. Re-read Xray step count for verification and record the result.

Parallelism:
  Rows are processed concurrently with a bounded ThreadPoolExecutor
  (MAX_WORKERS). A lock protects the shared result list, counters, and
  periodic Excel flushes. Both clients use requests.Session with a
  pooled HTTPAdapter, so sharing a single TestRailClient / XrayClient
  across threads is fine for this workload.

Idempotency:
  add_steps_to_the_test_case APPENDS steps. If a row has already been
  reconciled (Xray count == TestRail effective count) a restart skips
  it. Interruption/restart is therefore safe against the *same* report.
"""
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from xray.xray_client import XrayClient
from testrail.testrail_client import TestRailClient
from utilities.log_mngr import setup_custom_logger


# ======================== CONFIG ========================
INPUT_FILE = r"C:\Users\VijayKumar.Panga\Downloads\migration_report_20260424_184005.xlsx"
# Save the report next to the other *_report_*.xlsx files, i.e. the
# xray_migration folder (parent of this Scripts directory). Resolving
# relative to __file__ keeps it portable across machines/checkouts.
OUTPUT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_KEY = 'OMNIA'

# Migration-report column names
TESTRAIL_ID_COL = 'Test Rail Id'
XRAY_KEY_COL = 'Xray Key'
STATUS_COL = 'Status of Adding Steps to Xray'
FAILED_VALUE = 'failed'  # compared case-insensitively

# Jira custom field that stores the TestRail ID (e.g. "C1468070")
TESTRAIL_ID_FIELD = 'customfield_10621'

# Parallelism
MAX_WORKERS = 5       # concurrent rows. Stay conservative; each row does several API calls.
FLUSH_EVERY = 25      # write Excel snapshot every N completed rows

# Set to an int (e.g. 1) to process only the first N failed rows; None = all
LIMIT = None

logger = setup_custom_logger()


# ---------------------- Helpers ----------------------
def _effective_testrail_step_count(steps, xray):
    """
    Mirror the filter used inside XrayClient.add_steps_to_the_test_case():
    steps whose stripped action AND stripped expected are both empty are
    skipped. Returns the number of steps that would actually be added.
    """
    if not steps:
        return 0
    count = 0
    for step in steps:
        action = xray.strip_html(step.get('content', '')) or ''
        result = xray.strip_html(step.get('expected', '')) or ''
        if action == '' and result == '':
            continue
        count += 1
    return count


def _get_xray_step_count(xray, xray_key):
    """Return (count, raw_data). count is -1 if the call failed."""
    try:
        data = xray.get_test_case(xray_key)
    except Exception as e:
        logger.warning(f"get_test_case({xray_key}) raised: {e}")
        return -1, None
    if not data or 'getTest' not in data or data['getTest'] is None:
        return -1, None
    steps = data['getTest'].get('steps') or []
    return len(steps), steps


def _find_xray_key_for_testrail_id(xray, testrail_id):
    """Fallback lookup when the report row has no Xray Key."""
    url = f"{xray.url}rest/api/3/search/jql"
    payload = {
        "jql": f'project = {xray.project_key} AND cf[10621] ~ "{testrail_id}"',
        "fields": ["summary", TESTRAIL_ID_FIELD],
        "maxResults": 5,
    }
    try:
        resp = xray._upload_session.post(url, headers=xray.headers,
                                         json=payload, timeout=30)
    except Exception as e:
        logger.warning(f"JQL search error for {testrail_id}: {e}")
        return None
    if resp.status_code != 200:
        logger.warning(f"JQL search HTTP {resp.status_code} for {testrail_id}")
        return None
    issues = resp.json().get('issues') or []
    exact = [i for i in issues
             if str(i.get('fields', {}).get(TESTRAIL_ID_FIELD, '')).strip() == testrail_id]
    chosen = exact[0] if exact else (issues[0] if issues else None)
    return chosen['key'] if chosen else None


def _normalise_testrail_id(raw):
    """Return both the 'C1234' form (for JQL) and the numeric id (for TestRail API)."""
    s = str(raw).strip()
    if not s:
        return None, None
    c_form = s if s.upper().startswith('C') else f'C{s}'
    numeric = c_form[1:]
    if not numeric.isdigit():
        return c_form, None
    return c_form, int(numeric)


def flush_report(rows, output_file):
    cols = [
        'Row', 'TestRail ID', 'Xray Key',
        'TestRail Total Steps', 'TestRail Effective Steps', 'Xray Steps Before',
        'Counts Matched', 'Action', 'Xray Steps After', 'Notes'
    ]
    # Sort by original row index so the Excel stays ordered even with parallel completion
    ordered = sorted(rows, key=lambda r: r.get('Row', 0))
    pd.DataFrame(ordered, columns=cols).to_excel(
        output_file, index=False, sheet_name='Steps Reconciliation')


# ---------------------- Per-row worker ----------------------
def _process_row(row_idx, total, row, xray, testrail, has_xray_col):
    """
    Handle a single failed row. Returns a (result_dict, outcome_bucket)
    tuple where outcome_bucket is one of:
      already_matches, steps_added, partial_after_add, failed,
      not_found, no_testrail_steps.
    """
    raw_testrail_id = str(row[TESTRAIL_ID_COL])
    reported_xray_key = str(row[XRAY_KEY_COL]).strip() if has_xray_col else ''
    if reported_xray_key.lower() in ('', 'nan', 'none'):
        reported_xray_key = ''

    testrail_id, numeric_id = _normalise_testrail_id(raw_testrail_id)

    result = {
        'Row': row_idx,
        'TestRail ID': testrail_id or raw_testrail_id,
        'Xray Key': reported_xray_key,
        'TestRail Total Steps': '',
        'TestRail Effective Steps': '',
        'Xray Steps Before': '',
        'Counts Matched': '',
        'Action': '',
        'Xray Steps After': '',
        'Notes': '',
    }

    prefix = f"[{row_idx}/{total}]"

    if numeric_id is None:
        result['Action'] = 'Skipped'
        result['Notes'] = f'Invalid TestRail ID: {raw_testrail_id}'
        logger.warning(f"{prefix} invalid TestRail ID '{raw_testrail_id}'")
        return result, 'failed'

    # 1. Resolve Xray key (prefer the one from the report)
    xray_key = reported_xray_key
    if not xray_key:
        xray_key = _find_xray_key_for_testrail_id(xray, testrail_id)
        if xray_key:
            result['Xray Key'] = xray_key

    if not xray_key:
        result['Action'] = 'Skipped'
        result['Notes'] = 'No Xray Key in report and JQL lookup returned nothing'
        logger.warning(f"{prefix} {testrail_id}: no Xray key resolved")
        return result, 'not_found'

    # 2. Fetch TestRail case + steps
    try:
        tr_resp = testrail.get_case(numeric_id)
        tr_case = tr_resp.json() if tr_resp is not None else {}
    except Exception as e:
        result['Action'] = 'Error'
        result['Notes'] = f'TestRail get_case failed: {e}'
        logger.warning(f"{prefix} {testrail_id}: TestRail error - {e}")
        return result, 'failed'

    tr_steps = tr_case.get('custom_steps_separated') or []
    tr_total = len(tr_steps)
    tr_effective = _effective_testrail_step_count(tr_steps, xray)
    result['TestRail Total Steps'] = tr_total
    result['TestRail Effective Steps'] = tr_effective

    if tr_effective == 0:
        result['Action'] = 'Skipped'
        result['Notes'] = 'TestRail case has no steps with non-empty action/expected'
        logger.info(f"{prefix} {xray_key}: TestRail has 0 effective steps, skipping")
        return result, 'no_testrail_steps'

    # 3. Fetch current Xray step count
    xray_before, _ = _get_xray_step_count(xray, xray_key)
    if xray_before < 0:
        result['Action'] = 'Error'
        result['Notes'] = 'Could not read Xray steps via GraphQL'
        logger.warning(f"{prefix} {xray_key}: failed to read Xray steps")
        return result, 'failed'
    result['Xray Steps Before'] = xray_before

    # 4. Compare counts
    if xray_before == tr_effective:
        result['Counts Matched'] = 'Yes'
        result['Action'] = 'Already Matches'
        result['Xray Steps After'] = xray_before
        logger.info(f"{prefix} {xray_key}: step counts already match ({xray_before}), skipping")
        return result, 'already_matches'

    result['Counts Matched'] = 'No'

    # 5. Add steps (with attachments) to Xray — this APPENDS, not replaces
    try:
        ok = xray.add_steps_to_the_test_case(xray_key, steps=tr_steps,
                                             testrail_client=testrail)
    except Exception as e:
        result['Action'] = 'Error'
        result['Notes'] = f'add_steps_to_the_test_case raised: {e}'
        logger.warning(f"{prefix} {xray_key}: add_steps raised - {e}")
        return result, 'failed'

    # 6. Re-read Xray step count to verify
    xray_after, _ = _get_xray_step_count(xray, xray_key)
    result['Xray Steps After'] = xray_after if xray_after >= 0 else ''

    if not ok:
        result['Action'] = 'Add Failed'
        result['Notes'] = 'add_steps_to_the_test_case returned False (see log)'
        logger.warning(f"{prefix} {xray_key}: add_steps returned False")
        return result, 'failed'

    expected_after = xray_before + tr_effective
    if xray_after == expected_after or xray_after == tr_effective:
        result['Action'] = 'Steps Added'
        logger.info(f"{prefix} {xray_key}: added {tr_effective} steps "
                    f"(before={xray_before}, after={xray_after})")
        return result, 'steps_added'

    result['Action'] = 'Steps Added (count mismatch)'
    result['Notes'] = (f'Expected after={expected_after} or ={tr_effective}, '
                       f'got {xray_after}')
    logger.warning(f"{prefix} {xray_key}: post-add count mismatch "
                   f"(expected {expected_after} or {tr_effective}, got {xray_after})")
    return result, 'partial_after_add'


# ---------------------- Main ----------------------
def main():
    logger.info(f"=== Reconciling failed steps from: {INPUT_FILE} ===")
    df = pd.read_excel(INPUT_FILE)

    for col in (TESTRAIL_ID_COL, STATUS_COL):
        if col not in df.columns:
            logger.error(f"Required column '{col}' missing from {INPUT_FILE}")
            print(f"ERROR: column '{col}' not found")
            return

    failed = df[df[STATUS_COL].astype(str).str.strip().str.lower() == FAILED_VALUE].copy()
    failed[TESTRAIL_ID_COL] = failed[TESTRAIL_ID_COL].astype(str).str.strip()
    has_xray_col = XRAY_KEY_COL in failed.columns
    if has_xray_col:
        failed[XRAY_KEY_COL] = failed[XRAY_KEY_COL].astype(str).str.strip()

    total_failed = len(failed)
    logger.info(f"Found {total_failed} rows with '{STATUS_COL}' == Failed")
    print(f"Found {total_failed} rows with '{STATUS_COL}' == Failed")
    if total_failed == 0:
        return

    if LIMIT is not None and LIMIT > 0:
        failed = failed.head(LIMIT).copy()
        logger.info(f"LIMIT={LIMIT} -> processing only the first {len(failed)} row(s)")
        print(f"LIMIT={LIMIT} -> processing only the first {len(failed)} row(s)")
    total = len(failed)

    xray = XrayClient(project_key=PROJECT_KEY)
    if not xray._xray_graphql_available:
        logger.error("Xray Cloud GraphQL not available — cannot read/write steps")
        print("ERROR: Xray GraphQL not available (check XRAY_CLIENT_ID/SECRET)")
        return

    testrail = TestRailClient()

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_file = os.path.join(OUTPUT_DIR, f"steps_reconciliation_report_{timestamp}.xlsx")

    rows = []
    counters = {
        'already_matches': 0,
        'steps_added': 0,
        'partial_after_add': 0,
        'failed': 0,
        'not_found': 0,
        'no_testrail_steps': 0,
    }
    state_lock = threading.Lock()
    start_time = time.time()

    # Build the task list with a stable 1-based row index for logging / sorting.
    reset = failed.reset_index(drop=True)
    tasks = [(i + 1, r) for i, r in enumerate(reset.to_dict('records'))]

    logger.info(f"Starting parallel reconciliation: {total} rows, MAX_WORKERS={MAX_WORKERS}")
    print(f"Starting parallel reconciliation: {total} rows, MAX_WORKERS={MAX_WORKERS}")

    completed = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        future_to_idx = {
            executor.submit(_process_row, idx, total, row, xray, testrail, has_xray_col): idx
            for idx, row in tasks
        }
        for fut in as_completed(future_to_idx):
            idx = future_to_idx[fut]
            try:
                result, bucket = fut.result()
            except Exception as e:
                logger.exception(f"[{idx}/{total}] worker crashed: {e}")
                result = {
                    'Row': idx,
                    'TestRail ID': '', 'Xray Key': '',
                    'TestRail Total Steps': '', 'TestRail Effective Steps': '',
                    'Xray Steps Before': '', 'Counts Matched': '',
                    'Action': 'Error',
                    'Xray Steps After': '',
                    'Notes': f'Worker crashed: {e}',
                }
                bucket = 'failed'

            with state_lock:
                rows.append(result)
                counters[bucket] = counters.get(bucket, 0) + 1
                completed += 1
                if completed % FLUSH_EVERY == 0:
                    flush_report(rows, output_file)
                    logger.info(f"Progress: {completed}/{total} "
                                f"(added={counters['steps_added']}, "
                                f"matched={counters['already_matches']}, "
                                f"failed={counters['failed']}, "
                                f"not_found={counters['not_found']})")

    flush_report(rows, output_file)

    elapsed = time.time() - start_time
    summary = (
        f"\n{'='*60}\n"
        f"Steps Reconciliation Summary\n"
        f"{'='*60}\n"
        f"Total rows processed:        {total}\n"
        f"Parallel workers:            {MAX_WORKERS}\n"
        f"Already matched (no action): {counters['already_matches']}\n"
        f"Steps added successfully:    {counters['steps_added']}\n"
        f"Added but count mismatch:    {counters['partial_after_add']}\n"
        f"No TestRail steps to add:    {counters['no_testrail_steps']}\n"
        f"Xray key not resolved:       {counters['not_found']}\n"
        f"Failed / errored:            {counters['failed']}\n"
        f"Elapsed:                     {elapsed/60:.1f} minutes\n"
        f"Report saved:                {output_file}\n"
        f"{'='*60}"
    )
    logger.info(summary)
    print(summary)


if __name__ == '__main__':
    main()
