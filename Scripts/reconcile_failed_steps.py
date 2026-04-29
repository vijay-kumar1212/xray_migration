"""
Re-do step migration for rows in the previous reconciliation report.

Scenario:
  The prior run produced `steps_reconciliation_report_*.xlsx` with rows
  whose Action was one of:
      - 'Add Failed'                  (1723 rows)
      - 'Error'                       (395 rows)
      - 'Steps Added (count mismatch)'(142 rows)
  These rows may now hold partial / garbage steps in Xray. For each
  such row we:
      1. Look up the Xray Key and TestRail ID from the report.
      2. DELETE all existing steps on the Xray test via the Xray Cloud
         GraphQL `removeTestStep` mutation
         (XrayClient.remove_all_test_steps).
      3. FETCH fresh steps from TestRail
         (TestRailClient.get_case(...).json()['custom_steps_separated']).
      4. ADD them back into Xray with attachments via
         XrayClient.add_steps_to_the_test_case (addTestStep mutation).
      5. VERIFY the post-add step count and record the outcome.

Parallelism:
  Rows are processed concurrently with a bounded ThreadPoolExecutor
  (MAX_WORKERS). Both clients use pooled requests.Session objects, so
  sharing a single TestRailClient / XrayClient across threads is safe
  for this workload.

Idempotency:
  The delete-then-add flow leaves the Xray test with exactly the
  TestRail step set. Re-running on the same input is safe.
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
INPUT_FILE = r"C:\Users\VijayKumar.Panga\Downloads\steps_reconciliation_report_20260428_113650.xlsx"
# Save the report next to the other *_report_*.xlsx files, i.e. the
# xray_migration folder (parent of this Scripts directory).
OUTPUT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_KEY = 'OMNIA'

# Input report columns
TESTRAIL_ID_COL = 'TestRail ID'
XRAY_KEY_COL = 'Xray Key'
ACTION_COL = 'Action'

# Only reprocess rows whose previous Action is in this set.
# Set to None to reprocess every row in the input file.
ACTIONS_TO_REPROCESS = {
    'Add Failed',
    'Error',
    'Steps Added (count mismatch)',
}

# Jira custom field that stores the TestRail ID (e.g. "C1468070") — used
# as a fallback lookup when the row has no Xray Key.
TESTRAIL_ID_FIELD = 'customfield_10621'

# Parallelism
MAX_WORKERS = 3       # concurrent rows
FLUSH_EVERY = 25      # write Excel snapshot every N completed rows

# Set to an int (e.g. 1) to process only the first N rows; None = all
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
    """Return (c_form, numeric_id). c_form is 'C1234', numeric_id is int or None."""
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
        'Row', 'TestRail ID', 'Xray Key', 'Previous Action',
        'Xray Steps Before', 'Steps Removed', 'Remove Failures',
        'TestRail Total Steps', 'TestRail Effective Steps',
        'Add OK', 'Xray Steps After', 'Final Action', 'Notes'
    ]
    ordered = sorted(rows, key=lambda r: r.get('Row', 0))
    pd.DataFrame(ordered, columns=cols).to_excel(
        output_file, index=False, sheet_name='Steps Re-migration')


# ---------------------- Per-row worker ----------------------
def _process_row(row_idx, total, row, xray, testrail, has_xray_col):
    """
    Handle a single row: delete existing Xray steps, then re-add from
    TestRail. Returns (result_dict, outcome_bucket) where outcome_bucket
    is one of: steps_readded, partial_after_add, add_failed,
    remove_failed, not_found, no_testrail_steps, failed.
    """
    raw_testrail_id = str(row[TESTRAIL_ID_COL])
    reported_xray_key = str(row[XRAY_KEY_COL]).strip() if has_xray_col else ''
    if reported_xray_key.lower() in ('', 'nan', 'none'):
        reported_xray_key = ''
    prev_action = str(row.get(ACTION_COL, '')).strip()

    testrail_id, numeric_id = _normalise_testrail_id(raw_testrail_id)

    result = {
        'Row': row_idx,
        'TestRail ID': testrail_id or raw_testrail_id,
        'Xray Key': reported_xray_key,
        'Previous Action': prev_action,
        'Xray Steps Before': '',
        'Steps Removed': '',
        'Remove Failures': '',
        'TestRail Total Steps': '',
        'TestRail Effective Steps': '',
        'Add OK': '',
        'Xray Steps After': '',
        'Final Action': '',
        'Notes': '',
    }

    prefix = f"[{row_idx}/{total}]"

    if numeric_id is None:
        result['Final Action'] = 'Skipped'
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
        result['Final Action'] = 'Skipped'
        result['Notes'] = 'No Xray Key in report and JQL lookup returned nothing'
        logger.warning(f"{prefix} {testrail_id}: no Xray key resolved")
        return result, 'not_found'

    # 2. Snapshot current Xray step count
    xray_before, _ = _get_xray_step_count(xray, xray_key)
    if xray_before < 0:
        result['Final Action'] = 'Error'
        result['Notes'] = 'Could not read Xray steps via GraphQL (before)'
        logger.warning(f"{prefix} {xray_key}: failed to read Xray steps before remove")
        return result, 'failed'
    result['Xray Steps Before'] = xray_before

    # 3. Fetch TestRail steps FIRST so that if TestRail is down we never
    #    delete without being able to re-add.
    try:
        tr_resp = testrail.get_case(numeric_id)
        tr_case = tr_resp.json() if tr_resp is not None else {}
    except Exception as e:
        result['Final Action'] = 'Error'
        result['Notes'] = f'TestRail get_case failed: {e}'
        logger.warning(f"{prefix} {testrail_id}: TestRail error - {e}")
        return result, 'failed'

    tr_steps = tr_case.get('custom_steps_separated') or []
    tr_total = len(tr_steps)
    tr_effective = _effective_testrail_step_count(tr_steps, xray)
    result['TestRail Total Steps'] = tr_total
    result['TestRail Effective Steps'] = tr_effective

    if tr_effective == 0:
        result['Final Action'] = 'Skipped'
        result['Notes'] = 'TestRail case has no steps with non-empty action/expected'
        logger.info(f"{prefix} {xray_key}: TestRail has 0 effective steps, skipping remove/add")
        return result, 'no_testrail_steps'

    # 4. Remove all existing steps from the Xray test
    try:
        removed, remove_failed = xray.remove_all_test_steps(xray_key)
    except Exception as e:
        result['Final Action'] = 'Error'
        result['Notes'] = f'remove_all_test_steps raised: {e}'
        logger.warning(f"{prefix} {xray_key}: remove_all_test_steps raised - {e}")
        return result, 'failed'

    if removed < 0:
        result['Final Action'] = 'Remove Failed'
        result['Notes'] = 'remove_all_test_steps could not enumerate steps'
        logger.warning(f"{prefix} {xray_key}: could not enumerate/delete existing steps")
        return result, 'remove_failed'

    result['Steps Removed'] = removed
    result['Remove Failures'] = remove_failed
    if remove_failed > 0:
        logger.warning(f"{prefix} {xray_key}: {remove_failed} step(s) failed to delete — "
                       f"continuing with add anyway")

    # 5. Add fresh steps (with attachments) from TestRail
    try:
        ok = xray.add_steps_to_the_test_case(xray_key, steps=tr_steps,
                                             testrail_client=testrail)
    except Exception as e:
        result['Add OK'] = False
        result['Final Action'] = 'Add Error'
        result['Notes'] = f'add_steps_to_the_test_case raised: {e}'
        logger.warning(f"{prefix} {xray_key}: add_steps raised - {e}")
        return result, 'add_failed'
    result['Add OK'] = bool(ok)

    # 6. Verify final step count
    xray_after, _ = _get_xray_step_count(xray, xray_key)
    result['Xray Steps After'] = xray_after if xray_after >= 0 else ''

    if not ok:
        result['Final Action'] = 'Add Failed'
        result['Notes'] = 'add_steps_to_the_test_case returned False (see log)'
        logger.warning(f"{prefix} {xray_key}: add_steps returned False")
        return result, 'add_failed'

    if xray_after == tr_effective:
        result['Final Action'] = 'Steps Re-added'
        logger.info(f"{prefix} {xray_key}: re-added {tr_effective} steps "
                    f"(before={xray_before}, after={xray_after})")
        return result, 'steps_readded'

    result['Final Action'] = 'Steps Added (count mismatch)'
    result['Notes'] = (f'Expected after={tr_effective}, got {xray_after} '
                       f'(removed={removed}, remove_failed={remove_failed})')
    logger.warning(f"{prefix} {xray_key}: post-add count mismatch "
                   f"(expected {tr_effective}, got {xray_after})")
    return result, 'partial_after_add'


# ---------------------- Main ----------------------
def main():
    logger.info(f"=== Re-doing step migration from: {INPUT_FILE} ===")
    df = pd.read_excel(INPUT_FILE)

    for col in (TESTRAIL_ID_COL, XRAY_KEY_COL):
        if col not in df.columns:
            logger.error(f"Required column '{col}' missing from {INPUT_FILE}")
            print(f"ERROR: column '{col}' not found in input")
            return

    has_action_col = ACTION_COL in df.columns
    if ACTIONS_TO_REPROCESS is not None:
        if not has_action_col:
            logger.error(f"Column '{ACTION_COL}' missing — cannot filter by action")
            print(f"ERROR: column '{ACTION_COL}' missing. Set ACTIONS_TO_REPROCESS=None to process all rows.")
            return
        mask = df[ACTION_COL].astype(str).str.strip().isin(ACTIONS_TO_REPROCESS)
        target = df[mask].copy()
    else:
        target = df.copy()

    target[TESTRAIL_ID_COL] = target[TESTRAIL_ID_COL].astype(str).str.strip()
    target[XRAY_KEY_COL] = target[XRAY_KEY_COL].astype(str).str.strip()

    total_target = len(target)
    logger.info(f"Found {total_target} rows to reprocess "
                f"(filter={sorted(ACTIONS_TO_REPROCESS) if ACTIONS_TO_REPROCESS else 'ALL'})")
    print(f"Found {total_target} rows to reprocess "
          f"(filter={sorted(ACTIONS_TO_REPROCESS) if ACTIONS_TO_REPROCESS else 'ALL'})")
    if total_target == 0:
        return

    if LIMIT is not None and LIMIT > 0:
        target = target.head(LIMIT).copy()
        logger.info(f"LIMIT={LIMIT} -> processing only the first {len(target)} row(s)")
        print(f"LIMIT={LIMIT} -> processing only the first {len(target)} row(s)")
    total = len(target)

    xray = XrayClient(project_key=PROJECT_KEY)
    if not xray._xray_graphql_available:
        logger.error("Xray Cloud GraphQL not available — cannot read/write steps")
        print("ERROR: Xray GraphQL not available (check XRAY_CLIENT_ID/SECRET)")
        return

    testrail = TestRailClient()

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    output_file = os.path.join(OUTPUT_DIR, f"steps_remigration_report_{timestamp}.xlsx")

    rows = []
    counters = {
        'steps_readded': 0,
        'partial_after_add': 0,
        'add_failed': 0,
        'remove_failed': 0,
        'no_testrail_steps': 0,
        'not_found': 0,
        'failed': 0,
    }
    state_lock = threading.Lock()
    start_time = time.time()

    reset = target.reset_index(drop=True)
    has_xray_col = XRAY_KEY_COL in reset.columns
    tasks = [(i + 1, r) for i, r in enumerate(reset.to_dict('records'))]

    logger.info(f"Starting parallel re-migration: {total} rows, MAX_WORKERS={MAX_WORKERS}")
    print(f"Starting parallel re-migration: {total} rows, MAX_WORKERS={MAX_WORKERS}")

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
                    'TestRail ID': '', 'Xray Key': '', 'Previous Action': '',
                    'Xray Steps Before': '', 'Steps Removed': '', 'Remove Failures': '',
                    'TestRail Total Steps': '', 'TestRail Effective Steps': '',
                    'Add OK': '', 'Xray Steps After': '',
                    'Final Action': 'Error',
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
                                f"(re-added={counters['steps_readded']}, "
                                f"partial={counters['partial_after_add']}, "
                                f"add_failed={counters['add_failed']}, "
                                f"remove_failed={counters['remove_failed']}, "
                                f"not_found={counters['not_found']}, "
                                f"failed={counters['failed']})")

    flush_report(rows, output_file)

    elapsed = time.time() - start_time
    summary = (
        f"\n{'='*60}\n"
        f"Steps Re-migration Summary\n"
        f"{'='*60}\n"
        f"Total rows processed:         {total}\n"
        f"Parallel workers:             {MAX_WORKERS}\n"
        f"Steps re-added (count match): {counters['steps_readded']}\n"
        f"Added but count mismatch:     {counters['partial_after_add']}\n"
        f"Add failed:                   {counters['add_failed']}\n"
        f"Remove failed:                {counters['remove_failed']}\n"
        f"No TestRail steps to add:     {counters['no_testrail_steps']}\n"
        f"Xray key not resolved:        {counters['not_found']}\n"
        f"Other errors:                 {counters['failed']}\n"
        f"Elapsed:                      {elapsed/60:.1f} minutes\n"
        f"Report saved:                 {output_file}\n"
        f"{'='*60}"
    )
    logger.info(summary)
    print(summary)


if __name__ == '__main__':
    main()
