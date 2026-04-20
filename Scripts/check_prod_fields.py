"""Check custom field IDs and options on the PROD Jira instance."""
import requests, base64, os, json
from dotenv import load_dotenv
load_dotenv()

email = os.environ.get('JIRA_CLOUD_EMAIL')
token = os.environ.get('JIRA_API_TOKEN')
creds = base64.b64encode(f'{email}:{token}'.encode()).decode()
headers = {'Authorization': f'Basic {creds}', 'Accept': 'application/json'}
base = 'https://entain.atlassian.net'

target_fields = {
    'customfield_10449': 'Squad/Assigned Team',
    'customfield_10488': 'Test Automation Status',
    'customfield_10616': 'Test Level',
    'customfield_10617': 'Device',
    'customfield_10619': 'Hardware Dependent (test)',
    'customfield_10622': 'Lead Sign off (test)',
    'customfield_13100': 'Hardware Dependent (prod?)',
    'customfield_13101': 'Lead Sign off (prod?)',
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
                    opts = f.get('allowedValues', [])
                    if opts:
                        # Only show OMNIA/RGE/UKQA relevant squads for squad field
                        for opt in opts:
                            val = opt.get('value', opt.get('name', '?'))
                            if fid == 'customfield_10449':
                                if val.startswith(f'{proj}>') or val.startswith('OMNIA>') or val.startswith('RGE>') or val.startswith('UKQA>'):
                                    print(f'    id={opt["id"]}, value={val}')
                            else:
                                print(f'    id={opt["id"]}, value={val}')
                    else:
                        print(f'    (no allowedValues)')
                else:
                    print(f'  {fid} ({label}): NOT on screen')
