"""List all fields on Test issue screen for OMNIA, RGE, UKQA."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from xray.xray_client import XrayClient

x = XrayClient(project_key='OMNIA')

for proj in ['OMNIA', 'RGE', 'UKQA']:
    print(f"\n{'='*60}")
    print(f"PROJECT: {proj}")
    print(f"{'='*60}")
    url = f'{x.url}rest/api/3/issue/createmeta/{proj}/issuetypes'
    r = x._upload_session.get(url, headers=x.headers, timeout=30)
    if r.status_code != 200:
        print(f"  Error: {r.status_code}")
        continue
    for t in r.json().get('values', []):
        if t.get('name') == 'Test':
            tid = t.get('id')
            furl = f'{x.url}rest/api/3/issue/createmeta/{proj}/issuetypes/{tid}'
            fr = x._upload_session.get(furl, headers=x.headers, timeout=30)
            if fr.status_code == 200:
                fdata = fr.json()
                for f in fdata.get('fields', {}).items() if isinstance(fdata.get('fields'), dict) else fdata.get('values', fdata.get('fields', [])):
                    if isinstance(f, tuple):
                        fid, finfo = f
                        fname = finfo.get('name', '')
                    else:
                        fid = f.get('fieldId', f.get('key', ''))
                        fname = f.get('name', '')
                    if 'custom' in str(fid):
                        opts = ''
                        allowed = f.get('allowedValues', []) if isinstance(f, dict) else finfo.get('allowedValues', []) if isinstance(f, tuple) else []
                        if allowed:
                            opts = ', '.join([f"{o.get('id')}={o.get('value','')}" for o in allowed[:5]])
                        print(f"  {fid}: {fname}  {f'[{opts}]' if opts else ''}")
            break
