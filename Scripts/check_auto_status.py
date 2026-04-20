"""Check Test Automation Status field options on the test instance."""
import requests, base64, os, json
from dotenv import load_dotenv
load_dotenv()

email = os.environ.get('JIRA_CLOUD_EMAIL')
token = os.environ.get('JIRA_API_TOKEN')
creds = base64.b64encode(f'{email}:{token}'.encode()).decode()
headers = {'Authorization': f'Basic {creds}', 'Accept': 'application/json'}
base = 'https://entain-test.atlassian.net'

for proj in ['DFE', 'DF', 'OMNIA', 'RGE', 'UKQA', 'DBT']:
    url = f'{base}/rest/api/3/issue/createmeta?projectKeys={proj}&issuetypeNames=Test&expand=projects.issuetypes.fields'
    r = requests.get(url, headers=headers, timeout=30)
    if r.status_code != 200:
        print(f'{proj}: HTTP {r.status_code}')
        continue
    data = r.json()
    for p in data.get('projects', []):
        for it in p.get('issuetypes', []):
            fields = it.get('fields', {})
            f = fields.get('customfield_10488')
            if f:
                name = f.get('name', '?')
                print(f'\n{proj} - {name} (customfield_10488):')
                for opt in f.get('allowedValues', []):
                    val = opt.get('value', '?')
                    print(f'  id={opt["id"]}, value={val}')
            else:
                print(f'{proj}: customfield_10488 NOT on screen')
