"""Check custom field IDs on the test instance for OMNIA/RGE/UKQA projects."""
import requests, base64, os, json
from dotenv import load_dotenv
load_dotenv()

email = os.environ.get('JIRA_CLOUD_EMAIL')
token = os.environ.get('JIRA_API_TOKEN')
creds = base64.b64encode(f'{email}:{token}'.encode()).decode()
headers = {'Authorization': f'Basic {creds}', 'Accept': 'application/json'}
base = 'https://entain-test.atlassian.net'

target_fields = ['customfield_10619', 'customfield_10622', 'customfield_13100', 'customfield_13101']

for proj_key in ['OMNIA', 'RGE', 'UKQA']:
    print(f'\n{"="*60}')
    print(f'Project: {proj_key}')
    print(f'{"="*60}')
    url = f'{base}/rest/api/3/issue/createmeta?projectKeys={proj_key}&issuetypeNames=Test&expand=projects.issuetypes.fields'
    r = requests.get(url, headers=headers, timeout=30)
    if r.status_code != 200:
        print(f'  Status: {r.status_code}')
        continue
    data = r.json()
    for proj in data.get('projects', []):
        for it in proj.get('issuetypes', []):
            fields = it.get('fields', {})
            for fid in target_fields:
                if fid in fields:
                    f = fields[fid]
                    name = f.get('name', '?')
                    print(f'\n  {fid}: {name}')
                    for opt in f.get('allowedValues', []):
                        val = opt.get('value', opt.get('name', '?'))
                        print(f'    id={opt["id"]}, value={val}')
                else:
                    print(f'  {fid}: NOT on screen')
