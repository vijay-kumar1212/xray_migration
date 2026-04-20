"""Debug: try different import formats for Xray Cloud REST v2."""
from xray.xray_client import XrayClient
import json

xray = XrayClient()

exec_key = 'DFE-72545'

# Try Xray JSON format (v2)
payload = {
    "testExecutionKey": exec_key,
    "info": {
        "summary": "Cloud Desktop Execution",
        "project": "DFE"
    },
    "tests": [
        {
            "testKey": "DFE-9457",
            "status": "PASSED"
        },
        {
            "testKey": "DFE-9458",
            "status": "FAILED"
        },
        {
            "testKey": "DFE-9462",
            "status": "TODO"
        }
    ]
}

print(f'Payload: {json.dumps(payload, indent=2)}')
print(f'\nImporting to {exec_key}...')
resp = xray._upload_session.post(
    'https://xray.cloud.getxray.app/api/v2/import/execution',
    json=payload,
    headers=xray._xray_headers(),
    timeout=60
)
print(f'Status: {resp.status_code}')
print(f'Response: {resp.text[:1000]}')

# Also try the multipart format
print('\n--- Try with content-type xray ---')
headers = xray._xray_headers()
resp2 = xray._upload_session.post(
    'https://xray.cloud.getxray.app/api/v2/import/execution',
    data=json.dumps(payload),
    headers=headers,
    timeout=60
)
print(f'Status: {resp2.status_code}')
print(f'Response: {resp2.text[:1000]}')
