"""Debug: try linking tests to execution via Jira issue links."""
from xray.xray_client import XrayClient

xray = XrayClient()

exec_key = 'DFE-72545'
test_keys = ['DFE-9457', 'DFE-9458', 'DFE-9462']

# First, let's check what link types are available
print('--- Available link types ---')
resp = xray._upload_session.get(
    f'{xray.url}rest/api/3/issueLinkType',
    headers=xray.headers, timeout=30)
if resp.status_code == 200:
    for lt in resp.json().get('issueLinkTypes', []):
        if 'test' in lt['name'].lower() or 'xray' in lt.get('inward', '').lower():
            print(f"  {lt['id']}: {lt['name']} (inward: {lt['inward']}, outward: {lt['outward']})")

# Try to find the right link type for test execution -> test
print('\n--- All link types ---')
for lt in resp.json().get('issueLinkTypes', []):
    print(f"  {lt['id']}: {lt['name']} ({lt['inward']} / {lt['outward']})")
