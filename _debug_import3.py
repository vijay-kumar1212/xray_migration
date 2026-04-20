"""Debug: import with full testInfo including projectKey."""
from xray.xray_client import XrayClient

xray = XrayClient()

# First get summaries for the test cases
test_data = {}
for key in ['DFE-9457', 'DFE-9458', 'DFE-9462']:
    resp = xray._upload_session.get(
        f'{xray.url}rest/api/3/issue/{key}?fields=summary',
        headers=xray.headers, timeout=30)
    if resp.status_code == 200:
        test_data[key] = resp.json()['fields']['summary']

exec_key = 'DFE-72545'

payload = {
    "testExecutionKey": exec_key,
    "tests": [
        {
            "testKey": "DFE-9457",
            "status": "PASSED",
            "testInfo": {
                "summary": test_data.get("DFE-9457", "Test DFE-9457"),
                "projectKey": "DFE",
                "type": "Manual"
            }
        },
        {
            "testKey": "DFE-9458",
            "status": "FAILED",
            "testInfo": {
                "summary": test_data.get("DFE-9458", "Test DFE-9458"),
                "projectKey": "DFE",
                "type": "Manual"
            }
        },
        {
            "testKey": "DFE-9462",
            "status": "ABORTED",
            "testInfo": {
                "summary": test_data.get("DFE-9462", "Test DFE-9462"),
                "projectKey": "DFE",
                "type": "Manual"
            }
        }
    ]
}

import json
print(f'Importing to {exec_key}...')
resp = xray._upload_session.post(
    'https://xray.cloud.getxray.app/api/v2/import/execution',
    json=payload,
    headers=xray._xray_headers(),
    timeout=60
)
print(f'Status: {resp.status_code}')
print(f'Response: {resp.text[:1000]}')

if resp.status_code == 200:
    # Now do the same for the second execution
    exec_key2 = 'DFE-72546'
    payload['testExecutionKey'] = exec_key2
    print(f'\nImporting to {exec_key2}...')
    resp2 = xray._upload_session.post(
        'https://xray.cloud.getxray.app/api/v2/import/execution',
        json=payload,
        headers=xray._xray_headers(),
        timeout=60
    )
    print(f'Status: {resp2.status_code}')
    print(f'Response: {resp2.text[:1000]}')
