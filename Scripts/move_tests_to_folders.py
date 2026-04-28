"""
Move Xray test cases to their target Test Repository folders (sequential).

Reads a matched-migration Excel file (containing 'Xray Key' and
'Test Repository' columns), and for each row (processed one-by-one):
  1. Sanitises the folder path (removes Xray-disallowed characters)
  2. Creates the folder if it doesn't exist (cached after first creation)
  3. Moves the test case to that folder

Generates a status Excel with success/failure per row.
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
INPUT_FILE = r"C:\xray_migration\xray_migration\matched_migration_report_20260427_160325.xlsx"
OUTPUT_DIR = r"C:\xray_migration\xray_migration"
PROJECT_KEY = 'OMNIA'

# Column names in the input Excel
XRAY_KEY_COL = 'Xray Key'
FOLDER_COL = 'Test Repository'

# Delay between API calls (stays well under Xray Cloud's rate limits)
REQUEST_DELAY = 0.25  # seconds

# Periodically flush results to disk so a crash doesn't lose progress
FLUSH_EVERY = 50


# Xray Cloud folder name restrictions:
# Not allowed: \ : * ? " < > | and control characters
# ('/' is the path separator so it's only stripped from individual segments)
DISALLOWED_CHARS_PATTERN = re.compile(r'[\\:*?"<>|\x00-\x1f]')


logger = setup_custom_logger()


def sanitise_folder_name(name: str) -> str:
    """Remove Xray-disallowed characters from a single folder name segment."""
    if not isinstance(name, str):
        return ''
    cleaned = DISALLOWED_CHARS_PATTERN.sub('', name)
    cleaned = cleaned.strip()
    cleaned = re.sub(r'\s+', ' ', cleaned)
    return cleaned


def sanitise_folder_path(path: str) -> str:
    """
    Sanitise a full folder path.
    Splits on '/' (the only path separator), cleans each segment,
    drops empty segments, and rebuilds the path.
    """
    if not isinstance(path, str) or not path.strip():
        return '/'
    segments = [sanitise_folder_name(s) for s in path.split('/')]
    segments = [s for s in segments if s]
    if not segments:
        return '/'
    return '/' + '/'.join(segments)


def ensure_folder(xray, path, cache):
    """
    Create the folder if not already ensured. Returns status string.
    Treats "folder already exists" errors from Xray as success.
    """
    if path in cache:
        return 'Cached'

    # Resolve project ID once (cached in closure via outer scope)
    proj_resp = xray._upload_session.get(
        f'{xray.url}rest/api/3/project/{xray.project_key}',
        headers=xray.headers, timeout=30)
    if proj_resp.status_code != 200:
        return f'Error: cannot resolve project {xray.project_key}'
    project_id = proj_resp.json()['id']

    # Normalise path
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
        # Check if it's an "already exists" error — that's a success for us
        for err in errors:
            msg = err.get('message', '').lower()
            if 'already exists' in msg:
                cache.add(path)
                return 'Already Exists'
        # Real error
        return f'Failed: {errors[0].get("message", "unknown")}'

    if result.get('data') and result['data'].get('createFolder'):
        cache.add(path)
        return 'Ensured'

    return 'Failed: empty response'


def move_test(xray, xray_key, folder_path):
    """
    Move a test to the given folder via GraphQL.
    Returns (success: bool, reason: str).
    """
    try:
        resp = xray._upload_session.get(
            f"{xray.url}rest/api/3/issue/{xray_key}?fields=summary",
            headers=xray.headers, timeout=30)
        if resp.status_code != 200:
            return False, f'Issue lookup failed ({resp.status_code})'
        issue_id = resp.json()['id']

        gql_result = xray._graphql(
            """mutation($issueId: String!, $folderPath: String!) {
                updateTestFolder(issueId: $issueId, folderPath: $folderPath)
            }""",
            {"issueId": issue_id, "folderPath": folder_path})

        if gql_result is not None:
            return True, ''
        return False, 'GraphQL updateTestFolder returned no data'
    except Exception as e:
        return False, f'Move error: {e}'


def flush_report(results, output_file):
    """Write current results to the Excel report."""
    df = pd.DataFrame(results, columns=[
        'Xray Key', 'Original Folder', 'Sanitised Folder',
        'Folder Created', 'Move Status', 'Failure Reason'
    ])
    df.to_excel(output_file, index=False, sheet_name='Folder Move Report')


def main():
    logger.info(f"Reading input: {INPUT_FILE}")
    df = pd.read_excel(INPUT_FILE)
    logger.info(f"  Rows: {len(df)}, Columns: {list(df.columns)}")

    for col in (XRAY_KEY_COL, FOLDER_COL):
        if col not in df.columns:
            logger.error(f"Required column '{col}' missing from input")
            return

    df = df.dropna(subset=[XRAY_KEY_COL]).reset_index(drop=True)
    total = len(df)
    logger.info(f"Processing {total} rows sequentially")
    print(f"Processing {total} rows sequentially...")

    xray = XrayClient(project_key=PROJECT_KEY)
    if not xray._xray_graphql_available:
        logger.error("Xray Cloud GraphQL not available — cannot continue")
        return

    # Prepare output file upfront so partial progress is preserved
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = os.path.join(OUTPUT_DIR, f"folder_move_report_{timestamp}.xlsx")

    folder_cache = set()
    results = []
    success_count = 0
    failed_count = 0

    start_time = time.time()

    for idx, row in df.iterrows():
        xray_key = str(row[XRAY_KEY_COL]).strip()
        raw_folder = str(row[FOLDER_COL]) if row[FOLDER_COL] is not None else ''
        sanitised = sanitise_folder_path(raw_folder)

        result = {
            'Xray Key': xray_key,
            'Original Folder': raw_folder,
            'Sanitised Folder': sanitised,
            'Folder Created': '',
            'Move Status': 'Failed',
            'Failure Reason': ''
        }

        if not xray_key or xray_key.lower() == 'nan':
            result['Failure Reason'] = 'Missing Xray Key'
            results.append(result)
            failed_count += 1
            continue

        # 1. Ensure folder exists
        folder_status = ensure_folder(xray, sanitised, folder_cache)
        result['Folder Created'] = folder_status
        time.sleep(REQUEST_DELAY)

        # Only 'Ensured', 'Already Exists', and 'Cached' count as successful
        if folder_status not in ('Ensured', 'Already Exists', 'Cached'):
            result['Failure Reason'] = f'Could not ensure folder: {sanitised} ({folder_status})'
            results.append(result)
            failed_count += 1
            logger.warning(f"[{idx + 1}/{total}] {xray_key}: folder failed ({sanitised}) - {folder_status}")
            continue

        # 2. Move test to folder
        ok, reason = move_test(xray, xray_key, sanitised)
        time.sleep(REQUEST_DELAY)

        if ok:
            result['Move Status'] = 'Success'
            success_count += 1
        else:
            result['Failure Reason'] = reason
            failed_count += 1

        results.append(result)

        processed = idx + 1
        if processed % 10 == 0 or processed == total:
            elapsed = time.time() - start_time
            rate = processed / elapsed if elapsed > 0 else 0
            remaining = (total - processed) / rate if rate > 0 else 0
            pct = (processed / total) * 100
            msg = (f"[{processed}/{total}] ({pct:.1f}%) "
                   f"success={success_count} failed={failed_count} "
                   f"rate={rate:.1f}/s ETA={remaining/60:.1f}m")
            logger.info(msg)
            print(msg)

        # Periodic flush so crashes don't lose work
        if processed % FLUSH_EVERY == 0:
            flush_report(results, output_file)

    # Final write
    flush_report(results, output_file)

    elapsed = time.time() - start_time
    summary = (
        f"\n{'='*60}\n"
        f"Folder Move Summary\n"
        f"{'='*60}\n"
        f"Total rows:       {total}\n"
        f"Successful moves: {success_count}\n"
        f"Failed:           {failed_count}\n"
        f"Unique folders:   {len(folder_cache)}\n"
        f"Elapsed:          {elapsed/60:.1f} minutes\n"
        f"Report saved:     {output_file}\n"
        f"{'='*60}"
    )
    logger.info(summary)
    print(summary)


if __name__ == '__main__':
    main()
