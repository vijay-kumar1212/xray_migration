"""Debug: try different approaches to find tests in Xray."""
from xray.xray_client import XrayClient

xray = XrayClient()

# Try addTestsToTestExecution with string IDs directly
exec_key = 'DFE-72545'
test_keys = ['DFE-9457', 'DFE-9458', 'DFE-9462']

# Resolve exec key
resp = xray._upload_session.get(
    f'{xray.url}rest/api/3/issue/{exec_key}?fields=summary',
    headers=xray.headers, timeout=30)
exec_id = resp.json()['id']
print(f'Exec ID: {exec_id}')

# Try with Jira issue IDs as strings
test_ids = []
for key in test_keys:
    r = xray._upload_session.get(
        f'{xray.url}rest/api/3/issue/{key}?fields=summary',
        headers=xray.headers, timeout=30)
    if r.status_code == 200:
        test_ids.append(r.json()['id'])
        print(f'{key} -> Jira ID: {r.json()["id"]}')

print(f'\nTrying addTestsToTestExecution with Jira IDs: {test_ids}')
data = xray._graphql("""
    mutation AddTestsToExec($issueId: String!, $testIssueIds: [String!]!) {
        addTestsToTestExecution(issueId: $issueId, testIssueIds: $testIssueIds) {
            addedTests
            warning
        }
    }
""", {"issueId": exec_id, "testIssueIds": test_ids})
print(f'Result: {data}')

# Try using Xray REST API instead of GraphQL
print('\n--- Trying Xray REST API ---')
url = f'{xray.url}rest/raven/1.0/api/testexec/{exec_key}/test'
payload = {"add": test_keys}
print(f'POST {url}')
resp = xray._upload_session.post(url, json=payload, headers=xray.headers, timeout=30)
print(f'Status: {resp.status_code}')
print(f'Response: {resp.text[:500]}')
