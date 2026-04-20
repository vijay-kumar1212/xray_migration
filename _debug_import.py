"""Debug: use Xray Cloud REST v2 import with testInfo."""
from xray.xray_client import XrayClient

xray = XrayClient()

exec_key = 'DFE-72545'

# Use the import/execution endpoint with testInfo
payload = {
    "testExecutionKey": exec_key,
    "tests": [
        {
            "testKey": "DFE-9457",
            "status": "PASSED",
            "testInfo": {
                "summary": "Test DFE-9457",
                "type": "Manual"
            }
        },
        {
            "testKey": "DFE-9458",
            "status": "FAILED",
            "testInfo": {
                "summary": "Test DFE-9458",
                "type": "Manual"
            }
        },
        {
            "testKey": "DFE-9462",
            "status": "ABORTED",
            "testInfo": {
                "summary": "Test DFE-9462",
                "type": "Manual"
            }
        }
    ]
}

print(f'Importing results to {exec_key}...')
resp = xray._upload_session.post(
    'https://xray.cloud.getxray.app/api/v2/import/execution',
    json=payload,
    headers=xray._xray_headers(),
    timeout=60
)
print(f'Status: {resp.status_code}')
print(f'Response: {resp.text[:1000]}')
