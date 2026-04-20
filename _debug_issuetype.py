"""Debug: check issue types for the test cases."""
from xray.xray_client import XrayClient

xray = XrayClient()

for key in ['DFE-9457', 'DFE-9458', 'DFE-9462']:
    resp = xray._upload_session.get(
        f'{xray.url}rest/api/3/issue/{key}?fields=summary,issuetype',
        headers=xray.headers, timeout=30)
    if resp.status_code == 200:
        data = resp.json()
        itype = data['fields']['issuetype']['name']
        summary = data['fields']['summary'][:60]
        print(f'{key}: type={itype}, summary={summary}')
    else:
        print(f'{key}: HTTP {resp.status_code}')
