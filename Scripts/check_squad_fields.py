"""Check Squad and other remaining custom field options on the test Jira instance."""
import requests, base64, os, json
from dotenv import load_dotenv
load_dotenv()

email = os.environ.get('JIRA_CLOUD_EMAIL')
token = os.environ.get('JIRA_API_TOKEN')
creds = base64.b64encode(f'{email}:{token}'.encode()).decode()
headers = {'Authorization': f'Basic {creds}', 'Accept': 'application/json'}
base = 'https://entain-test.atlassian.net'

# Fields to check: Squad (10449), Test Level (10616), Device (10617)
target_fields = {
    'customfield_10449': 'Squad',
    'customfield_10616': 'Test Level',
    'customfield_10617': 'Device',
    'customfield_10488': 'Test Automation Status',
}

for proj in ['OMNIA', 'RGE', 'UKQA', 'DFE']:
    url = f'{base}/rest/api/3/issue/createmeta?projectKeys={proj}&issuetypeNames=Test&expand=projects.issuetypes.fields'
    r = requests.get(url, headers=headers, timeout=30)
    if r.status_code != 200:
        print(f'{proj}: HTTP {r.status_code}')
        continue
    data = r.json()
    for p in data.get('projects', []):
        for it in p.get('issuetypes', []):
            fields = it.get('fields', {})
            print(f'\n{"="*60}')
            print(f'Project: {proj}')
            print(f'{"="*60}')
            for fid, label in target_fields.items():
                f = fields.get(fid)
                if f:
                    name = f.get('name', '?')
                    print(f'\n  {fid}: {name}')
                    for opt in f.get('allowedValues', []):
                        val = opt.get('value', opt.get('name', '?'))
                        print(f'    id={opt["id"]}, value={val}')
                else:
                    print(f'  {fid} ({label}): NOT on screen')
