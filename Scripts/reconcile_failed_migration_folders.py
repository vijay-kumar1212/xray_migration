"""
Reconcile folder placement for the 46 test cases re-imported from the
migration report where 'Export to Xray Status == Failed'.

Workflow:
  1. Read the migration report and keep only rows with status=Failed.
     Each row gives us: TestRail ID (e.g. C1468070) and intended Test Repository.
  2. For each TestRail ID, find the matching Xray issue key via Jira JQL
     using the custom field customfield_10621 (which stores the TestRail ID).
  3. Query the test's current folder via Xray Cloud GraphQL.
  4. Compare current vs intended folder:
        - already correct -> skipped
        - mismatch         -> ensure folder, then move via updateTestFolder
        - no xray key     -> logged as error
  5. Write a reconciliation Excel report with the status of each row.

Reuses folder-ensure/move patterns from Scripts/move_tests_to_folders.py.
"""
import os
import re
import sys
import time
from datetime import datetime

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from xray.xray_client import XrayClient
from utilities.log_mngr import setup_custom_logger


# ======================== CONFIG ========================
INPUT_FILE = r"C:\Users\VijayKumar.Panga\Downloads\migration_report_20260424_184005.xlsx"
OUTPUT_DIR = r"C:\xray_migration\xray_migration"
PROJECT_KEY = 'OMNIA'

# Migration-report column names
TESTRAIL_ID_COL = 'Test Rail Id'
FOLDER_COL = 'Test Repository'
STATUS_COL = 'Export to Xray Status'

# Jira custom field that stores the TestRail ID (e.g. "C1468070")
TESTRAIL_ID_FIELD = 'customfield_10621'

REQUEST_DELAY = 0.25  # seconds between API calls
FLUSH_EVERY = 20

# Xray-disallowed characters in folder names
DISALLOWED_CHARS_PATTERN = re.compile(r'[\\:*?"<>|\x00-\x1f]')


logger = setup_custom_logger()


# ---------------------- Path helpers (copied from move_tests_to_folders.py) ----------------------
def sanitise_folder_name(name: str) -> str:
    if not isinstance(name, str):
        return ''
    cleaned = DISALLOWED_CHARS_PATTERN.sub('', name)
    cleaned = cleaned.strip()
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned


def sanitise_folder_path(path: str) -> str:
    if not isinstance(path, str) or not path.strip():
        return '/'
    segments = [sanitise_folder_name(s) for s in path.split('/')]
    segments = [s for s in segments if s]
    if not segments:
        return '/'
    return '/' + '/'.join(segments)


# ---------------------- Xray helpers ----------------------
def resolve_project_id(xray):
    resp = xray._upload_session.get(
        f'{xray.url}rest/api/3/project/{xray.project_key}',
        headers=xray.headers, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"Cannot resolve project {xray.project_key}: HTTP {resp.status_code}")
    return resp.json()['id']


def find_xray_key_for_testrail_id(xray, testrail_id):
    """
    Look up the Xray issue key whose TestRail ID custom field equals testrail_id
    (e.g. 'C1468070'). Returns (key, issue_id) or (None, None).
    Uses the new /rest/api/3/search/jql endpoint (the old /search was retired).
    """
    url = f"{xray.url}rest/api/3/search/jql"
    payload = {
        "jql": f'project = {xray.project_key} AND cf[10621] ~ "{testrail_id}"',
        "fields": ["summary", TESTRAIL_ID_FIELD],
        "maxResults": 5,
    }
    try:
        resp = xray._upload_session.post(url, headers=xray.headers, json=payload, timeout=30)
    except Exception as e:
        logger.warning(f"Search error for {testrail_id}: {e}")
        return None, None
    if resp.status_code != 200:
        logger.warning(f"Search HTTP {resp.status_code} for {testrail_id}: {resp.text[:200]}")
        return None, None
    issues = resp.json().get('issues') or []
    # Prefer an exact match on the custom field value
    exact = [i for i in issues
             if str(i.get('fields', {}).get(TESTRAIL_ID_FIELD, '')).strip() == testrail_id]
    chosen = exact[0] if exact else (issues[0] if issues else None)
    if not chosen:
        return None, None
    return chosen['key'], chosen['id']


def get_current_folder(xray, issue_id):
    """
    Return the current Test Repository folder path for an issue.
    Returns a string path (e.g. '/A/B') or '' if the test is at the root /
    or '__ERROR__' if the call fails.
    """
    query = """
    query($issueIds: [String]) {
        getTests(issueIds: $issueIds, limit: 1) {
            results {
                issueId
                folder { path }
            }
        }
    }
    """
    data = xray._graphql(query, {"issueIds": [str(issue_id)]})
    if data is None:
        return '__ERROR__'
    results = (data.get('getTests') or {}).get('results') or []
    if not results:
        return '__ERROR__'
    folder = results[0].get('folder') or {}
    path = folder.get('path')
    # Xray returns None or '/' for root
    if not path or path == '/':
        return '/'
    return path


def ensure_folder(xray, project_id, path, cache):
    """Create folder if needed. Returns status string."""
    if path in cache:
        return 'Cached'
    if not path.startswith('/'):
        path = '/' + path

    mutation = """
        mutation CreateFolder($projectId: String!, $path: String!) {
            createFolder(projectId: $projectId, path: $path) {
                folder { name path }
                warnings
            }
        }
    """
    payload = {"query": mutation, "variables": {"projectId": project_id, "path": path}}
    try:
        resp = xray._upload_session.post(
            'https://xray.cloud.getxray.app/api/v2/graphql',
            json=payload, headers=xray._xray_headers(), timeout=60)
    except Exception as e:
        return f'Error: {e}'

    if resp.status_code != 200:
        return f'Error: HTTP {resp.status_code}'

    result = resp.json()
    errors = result.get('errors') or []
    if errors:
        for err in errors:
            msg = err.get('message', '').lower()
            if 'already exists' in msg:
                cache.add(path)
                return 'Already Exists'
        return f'Failed: {errors[0].get("message", "unknown")}'

    if result.get('data') and result['data'].get('createFolder'):
        cache.add(path)
        return 'Ensured'
    return 'Failed: empty response'


def move_test(xray, issue_id, folder_path):
    """Move a test (by issue_id) to a folder. Returns (ok, reason)."""
    try:
        data = xray._graphql(
            """mutation($issueId: String!, $folderPath: String!) {
                updateTestFolder(issueId: $issueId, folderPath: $folderPath)
            }""",
            {"issueId": str(issue_id), "folderPath": folder_path})
        if data is not None:
            return True, ''
        return False, 'GraphQL updateTestFolder returned no data'
    except Exception as e:
        return False, f'Move error: {e}'


def flush_report(rows, output_file):
    cols = [
        'TestRail ID', 'Xray Key', 'Intended Folder', 'Current Folder',
        'Action', 'Folder Ensured', 'Move Status', 'Notes'
    ]
    pd.DataFrame(rows, columns=cols).to_excel(output_file, index=False, sheet_name='Reconciliation')


# ---------------------- Main ----------------------
def main():
    logger.info(f"=== Reconciling folders for Failed rows in: {INPUT_FILE} ===")
    df = pd.read_excel(INPUT_FILE)

    for col in (TESTRAIL_ID_COL, FOLDER_COL, STATUS_COL):
        if col not in df.columns:
            logger.error(f"Required column '{col}' missing from {INPUT_FILE}")
            print(f"ERROR: column '{col}' not found")
            return

    failed = df[df[STATUS_COL].astype(str).str.strip().str.lower() == 'failed'].copy()
    failed[TESTRAIL_ID_COL] = failed[TESTRAIL_ID_COL].astype(str).str.strip()
    failed[FOLDER_COL] = failed[FOLDER_COL].astype(str).str.strip()
    total = len(failed)
    logger.info(f"Found {total} failed rows to reconcile")
    print(f"Found {total} failed rows to reconcile")
    if total == 0:
        return

    xray = XrayClient(project_key=PROJECT_KEY)
    if not xray._xray_graphql_available:
        logger.error("Xray Cloud GraphQL not available — cannot continue")
        print("ERROR: Xray GraphQL not available (XRAY_CLIENT_ID/SECRET)")
        return

    project_id = resolve_project_id(xray)
    logger.info(f"Project {PROJECT_KEY} -> id {project_id}")

    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = os.path.join(OUTPUT_DIR, f"folder_reconciliation_report_{timestamp}.xlsx")

    folder_cache = set()
    rows = []
    counters = {'already_correct': 0, 'moved': 0, 'failed': 0, 'not_found': 0}
    start_time = time.time()

    for idx, row in failed.reset_index(drop=True).iterrows():
        raw_testrail_id = str(row[TESTRAIL_ID_COL])
        intended_raw = str(row[FOLDER_COL])
        intended = sanitise_folder_path(intended_raw)

        # Normalise TestRail ID to have leading C (custom field stores "C<digits>")
        testrail_id = raw_testrail_id if raw_testrail_id.upper().startswith('C') else f'C{raw_testrail_id}'

        result = {
            'TestRail ID': testrail_id,
            'Xray Key': '',
            'Intended Folder': intended,
            'Current Folder': '',
            'Action': '',
            'Folder Ensured': '',
            'Move Status': '',
            'Notes': '',
        }

        # 1. Resolve Xray key
        xray_key, issue_id = find_xray_key_for_testrail_id(xray, testrail_id)
        time.sleep(REQUEST_DELAY)
        if not xray_key:
            result['Action'] = 'Skipped'
            result['Notes'] = 'No Xray issue found for this TestRail ID'
            counters['not_found'] += 1
            rows.append(result)
            logger.warning(f"[{idx + 1}/{total}] {testrail_id}: no Xray issue found")
            continue
        result['Xray Key'] = xray_key

        # 2. Get current folder
        current = get_current_folder(xray, issue_id)
        time.sleep(REQUEST_DELAY)
        result['Current Folder'] = current

        if current == '__ERROR__':
            result['Action'] = 'Error'
            result['Notes'] = 'Could not read current folder via GraphQL'
            counters['failed'] += 1
            rows.append(result)
            logger.warning(f"[{idx + 1}/{total}] {xray_key}: failed to read current folder")
            continue

        # 3. Compare
        if current == intended:
            result['Action'] = 'Already Correct'
            counters['already_correct'] += 1
            rows.append(result)
            logger.info(f"[{idx + 1}/{total}] {xray_key}: already in correct folder ({current})")
        else:
            # 4. Ensure folder and move
            folder_status = ensure_folder(xray, project_id, intended, folder_cache)
            result['Folder Ensured'] = folder_status
            time.sleep(REQUEST_DELAY)
            if folder_status not in ('Ensured', 'Already Exists', 'Cached'):
                result['Action'] = 'Error'
                result['Move Status'] = 'Skipped'
                result['Notes'] = f'Folder ensure failed: {folder_status}'
                counters['failed'] += 1
                rows.append(result)
                logger.warning(f"[{idx + 1}/{total}] {xray_key}: folder ensure failed ({folder_status})")
                continue

            ok, reason = move_test(xray, issue_id, intended)
            time.sleep(REQUEST_DELAY)
            if ok:
                result['Action'] = 'Moved'
                result['Move Status'] = 'Success'
                counters['moved'] += 1
                logger.info(f"[{idx + 1}/{total}] {xray_key}: moved '{current}' -> '{intended}'")
            else:
                result['Action'] = 'Move Failed'
                result['Move Status'] = 'Failed'
                result['Notes'] = reason
                counters['failed'] += 1
                logger.warning(f"[{idx + 1}/{total}] {xray_key}: move failed - {reason}")
            rows.append(result)

        if (idx + 1) % FLUSH_EVERY == 0:
            flush_report(rows, output_file)

    flush_report(rows, output_file)

    elapsed = time.time() - start_time
    summary = (
        f"\n{'='*60}\n"
        f"Folder Reconciliation Summary\n"
        f"{'='*60}\n"
        f"Total rows:       {total}\n"
        f"Already correct:  {counters['already_correct']}\n"
        f"Moved:            {counters['moved']}\n"
        f"Not found (Xray): {counters['not_found']}\n"
        f"Failed:           {counters['failed']}\n"
        f"Elapsed:          {elapsed/60:.1f} minutes\n"
        f"Report saved:     {output_file}\n"
        f"{'='*60}"
    )
    logger.info(summary)
    print(summary)


if __name__ == '__main__':
    main()
