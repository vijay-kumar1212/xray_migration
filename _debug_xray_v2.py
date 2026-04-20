"""Debug: try Xray Cloud REST v2 API and GraphQL with keys."""
from xray.xray_client import XrayClient

xray = XrayClient()

exec_key = 'DFE-72545'
test_keys = ['DFE-9457', 'DFE-9458', 'DFE-9462']

# Approach 1: Try GraphQL with issue keys instead of IDs
print('--- Approach 1: GraphQL with issue keys ---')
resp = xray._upload_session.get(
    f'{xray.url}rest/api/3/issue/{exec_key}?fields=summary',
    headers=xray.headers, timeout=30)
exec_id = resp.json()['id']

# Try passing keys as testIssueIds (some Xray versions accept keys)
data = xray._graphql("""
    mutation AddTestsToExec($issueId: String!, $testIssueIds: [String!]!) {
        addTestsToTestExecution(issueId: $issueId, testIssueIds: $testIssueIds) {
            addedTests
            warning
        }
    }
""", {"issueId": exec_id, "testIssueIds": test_keys})
print(f'With keys: {data}')

# Approach 2: Try Xray Cloud REST v2 API
print('\n--- Approach 2: Xray Cloud REST v2 ---')
import json
# Import execution results format
payload = {
    "testExecutionKey": exec_key,
    "tests": [
        {"testKey": key, "status": "TODO"} for key in test_keys
    ]
}
resp = xray._upload_session.post(
    'https://xray.cloud.getxray.app/api/v2/import/execution',
    json=payload,
    headers=xray._xray_headers(),
    timeout=60
)
print(f'Status: {resp.status_code}')
print(f'Response: {resp.text[:500]}')
