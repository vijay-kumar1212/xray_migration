"""Debug: add tests to execution via Jira issue links, then update status."""
from xray.xray_client import XrayClient
import json
import time

xray = XrayClient()

exec_key = 'DFE-72545'
test_keys = ['DFE-9457', 'DFE-9458', 'DFE-9462']

# Step 1: Link tests to execution via Jira issue links
print('--- Step 1: Linking tests to execution via Jira issue links ---')
for test_key in test_keys:
    payload = {
        "type": {"name": "Test"},
        "inwardIssue": {"key": exec_key},
        "outwardIssue": {"key": test_key}
    }
    resp = xray._upload_session.post(
        f'{xray.url}rest/api/3/issueLink',
        json=payload,
        headers=xray.headers,
        timeout=30
    )
    print(f'  Link {exec_key} -> {test_key}: {resp.status_code} {resp.text[:200]}')

# Wait for Xray to sync
print('\nWaiting 5s for Xray to sync...')
time.sleep(5)

# Step 2: Check if tests appear in the execution now
print('\n--- Step 2: Check tests in execution ---')
resp = xray._upload_session.get(
    f'{xray.url}rest/api/3/issue/{exec_key}?fields=summary',
    headers=xray.headers, timeout=30)
exec_id = resp.json()['id']

data = xray._graphql("""
    query GetTestExecution($issueId: String!) {
        getTestExecution(issueId: $issueId) {
            testRuns(limit: 100) {
                results {
                    id
                    status { name }
                    test {
                        issueId
                        jira(fields: ["key"])
                    }
                }
            }
        }
    }
""", {"issueId": exec_id})

if data and 'getTestExecution' in data:
    runs = data['getTestExecution'].get('testRuns', {}).get('results', [])
    print(f'Found {len(runs)} test runs:')
    for run in runs:
        test_jira = run.get('test', {}).get('jira', {})
        key = test_jira.get('key', 'unknown') if isinstance(test_jira, dict) else 'unknown'
        print(f'  Run ID: {run["id"]}, Test: {key}, Status: {run["status"]["name"]}')
else:
    print('No test execution data found')
