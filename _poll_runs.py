"""Poll for test runs in execution after linking."""
import time
from xray.xray_client import XrayClient

xray = XrayClient()

for exec_key in ['DFE-72545', 'DFE-72546']:
    resp = xray._upload_session.get(
        f'{xray.url}rest/api/3/issue/{exec_key}?fields=summary',
        headers=xray.headers, timeout=30)
    exec_id = resp.json()['id']
    
    print(f'\n=== Checking {exec_key} (id={exec_id}) ===')
    for attempt in range(4):
        data = xray._graphql("""
            query GetTestExecution($issueId: String!) {
                getTestExecution(issueId: $issueId) {
                    testRuns(limit: 100) {
                        results {
                            id
                            status { name }
                            test { issueId jira(fields: ["key"]) }
                        }
                    }
                }
            }
        """, {"issueId": exec_id})
        runs = data.get('getTestExecution', {}).get('testRuns', {}).get('results', []) if data else []
        print(f'  Attempt {attempt+1}: {len(runs)} test runs')
        if runs:
            for r in runs:
                tj = r.get('test', {}).get('jira', {})
                k = tj.get('key', '?') if isinstance(tj, dict) else '?'
                print(f'    Run {r["id"]}: {k} -> {r["status"]["name"]}')
            break
        if attempt < 3:
            print(f'  Waiting 10s...')
            time.sleep(10)

# Also link tests to second execution
print('\n--- Linking tests to DFE-72546 ---')
for test_key in ['DFE-9457', 'DFE-9458', 'DFE-9462']:
    payload = {
        "type": {"name": "Test"},
        "inwardIssue": {"key": "DFE-72546"},
        "outwardIssue": {"key": test_key}
    }
    resp = xray._upload_session.post(
        f'{xray.url}rest/api/3/issueLink',
        json=payload,
        headers=xray.headers,
        timeout=30
    )
    print(f'  Link DFE-72546 -> {test_key}: {resp.status_code}')
