"""Debug: try different testInfo formats."""
from xray.xray_client import XrayClient

xray = XrayClient()

exec_key = 'DFE-72545'

# Try with minimal testInfo - just type
payload = {
    "testExecutionKey": exec_key,
    "tests": [
        {
            "testKey": "DFE-9457",
            "status": "PASSED",
            "testInfo": {
                "type": "Manual"
            }
        }
    ]
}

print('Try 1: minimal testInfo with type=Manual')
resp = xray._upload_session.post(
    'https://xray.cloud.getxray.app/api/v2/import/execution',
    json=payload,
    headers=xray._xray_headers(),
    timeout=60
)
print(f'Status: {resp.status_code}')
print(f'Response: {resp.text[:500]}')

# Try with type=Generic
payload['tests'][0]['testInfo']['type'] = 'Generic'
print('\nTry 2: testInfo with type=Generic')
resp = xray._upload_session.post(
    'https://xray.cloud.getxray.app/api/v2/import/execution',
    json=payload,
    headers=xray._xray_headers(),
    timeout=60
)
print(f'Status: {resp.status_code}')
print(f'Response: {resp.text[:500]}')

# Try with summary + type
payload['tests'][0]['testInfo'] = {"summary": "test", "type": "Manual"}
print('\nTry 3: testInfo with summary + type')
resp = xray._upload_session.post(
    'https://xray.cloud.getxray.app/api/v2/import/execution',
    json=payload,
    headers=xray._xray_headers(),
    timeout=60
)
print(f'Status: {resp.status_code}')
print(f'Response: {resp.text[:500]}')
