"""Check custom field IDs and options on the PROD Jira instance."""
import requests, base64, os, json
from dotenv import load_dotenv
load_dotenv(override=True)

email = os.environ.get('JIRA_CLOUD_EMAIL')
token = os.environ.get('JIRA_API_TOKEN')
creds = base64.b64encode(f'{email}:{token}'.encode()).decode()
headers = {'Authorization': f'Basic {creds}', 'Accept': 'application/json'}
base = 'https://entain.atlassian.net'

target_fields = [
    'customfield_10449', 'customfield_10488', 'customfield_10616',
    'customfield_10617', 'customfield_13100', 'customfield_13101',
]

for proj in ['OMNIA', 'RGE', 'UKQA']:
    url = f'{base}/rest/api/3/issue/createmeta?projectKeys={proj}&issuetypeNames=Test&expand=projects.issuetypes.fields'
    r = requests.get(url, headers=headers, timeout=30)
    if r.status_code != 200:
        print(f'{proj}: HTTP {r.status_code} - {r.text[:100]}')
        continue
    data = r.json()
    for p in data.get('projects', []):
        for it in p.get('issuetypes', []):
            fields = it.get('fields', {})
            print(f'\n{"="*60}')
            print(f'Project: {proj}')
            print(f'{"="*60}')
            for fid in target_fields:
                f = fields.get(fid)
                if f:
                    name = f.get('name', '?')
                    print(f'\n  {fid}: {name}')
                    opts = f.get('allowedValues', [])
                    for opt in opts:
                        val = opt.get('value', opt.get('name', '?'))
                        if fid == 'customfield_10449':
                            if val.startswith(f'{proj}>') or val.startswith('OMNIA>') or val.startswith('RGE>') or val.startswith('UKQA>'):
                                print(f'    id={opt["id"]}, value={val}')
                        else:
                            print(f'    id={opt["id"]}, value={val}')
                else:
                    print(f'  {fid}: NOT on screen')
