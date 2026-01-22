import json
import os
from pathlib import Path

from bs4 import BeautifulSoup
from dotenv import load_dotenv
import requests
from requests import post

load_dotenv()


class XrayClient:
    #https://jira-enterprise-uat.corp.entaingroup.com
    def __init__(self,
                 base_url='https://jira-enterprise.corp.entaingroup.com/',
                 project_key='RGE', # TODO DFE,DF, DBT OMNIA, RGE for GBS, UKQA for envision,
                 issue_type='Test',
                 test_repo_ = '/LCG Digital Master Suite', #TODO  modify the Test Repository Path based on the project
                 test_set_id=None,
                 pat=None):
        self.url = base_url
        self.project_key = project_key
        self.issue_type = issue_type
        self.test_set_id = test_set_id
        self.test_repository = test_repo_
        mapping_file = Path(__file__).resolve().parent / "xray_mappings.json"
        with open(mapping_file, 'r',encoding="utf-8") as f:
            self.mappings = json.load(f)
        self.pat = pat if pat is not None else os.environ.get('PAT')
        if not self.pat:
            raise ValueError("PAT environment variable is not set. Please set it using 'export PAT=your_token_here' for mac; for windows use set PAT=your_token_here' or add it to .env file")
        self.headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + self.pat,
            "Accept": "application/json",
            "X-Atlassian-Token": "no-check"
        }

    def get_custom_device(self, devices):
        if {1, 3}.issubset(devices) or len(devices) >= 2:
            return self.mappings['xr_devices']['13']
        if not devices:
            return self.mappings['xr_devices']['0']
        d = devices[0]
        if d == 2: #  If tablet is present then we are making it to mobile in xray
            return self.mappings['xr_devices']['1']
        return self.mappings['xr_devices'][str(d)]

    @staticmethod
    def strip_html(html_text):
        if not html_text:
            return html_text
        soup = BeautifulSoup(html_text, "html.parser")
        # return soup.get_text(strip=True)
        text = soup.get_text(separator='\n')

    #   to remove excessive blank lines
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = '\n'.join(chunk for chunk in chunks if chunk)
        return text

    def create_issue(self, data, issue_type=None,test_repo=None):
        payload = {
            "fields": {
                "project": {"key": self.project_key},
                "summary": data['title'] if issue_type==self.issue_type else data['name'],
                "issuetype": {"name": issue_type if issue_type is not None else self.issue_type},
                "priority": {"id": str(data['custom_priorityomnia']) if self.project_key == 'OMNIA' else self.mappings['xray_priority'][str(data['priority_id'])]}
            }
        }
        if issue_type == 'Test Execution' and data['description']:
            payload['decription'] = data['description']
            payload['priority'] = '10001'
        elif issue_type == self.issue_type:
            payload['fields']["description"] = self.strip_html(data['custom_description']) if data['custom_description'] else '' #Description
            payload['fields']["customfield_10270"] = test_repo if test_repo else self.test_repository # Test Repository Path
            payload['fields']["customfield_11426"] =  {"id": self.mappings[f'{self.project_key.lower()}_automation_status'][str(data['custom_automatedd'])] if self.project_key not in ['UKQA', 'RGE', 'OMNIA'] else self.mappings[f'{self.project_key.lower()}_automation_status'][str(data.get('custom_autotype'))]} # Test Automation status TODO
            payload['fields']['customfield_13006'] = self.strip_html(data['custom_preconds']) #Preconditions Previous id 12901
            payload['fields']['customfield_13001'] = f'S{data['suite_id']}' #Test Suit ID 12903
            payload['fields']['customfield_13004'] = f'C{data['id']}' # Test rail Id 12906
            payload['fields']['customfield_13003'] = data['refs'] #References 12905
            payload['fields']['customfield_13000'] = {'id': self.mappings['xr_test_level']['1'] if data['type_id'] == 1 else self.mappings['xr_test_level']['6']} # Test Level Acceptance/Functional 12902
            if self.project_key in ['DFE', 'DF']:
                payload['fields']['labels'] = [self.mappings['custom_brand'][str(data['custom_brand'])].replace(" ", "_")]
                payload['fields']['customfield_13005'] = {'id': self.get_custom_device(data['custom_device'])}  # Device 12907
                payload['fields']['customfield_13002'] = self.mappings['feature_map'][str(data['custom_feature'])]  # Feature dictionary 12904
            if self.project_key in ['OMNIA', 'RGE', 'UKQA']:
                payload['fields']['customfield_13101'] = {'id': self.mappings['lead_sign_off'][str(data['custom_omnialeadreview'])]} #lead sign off
                payload['fields']['customfield_13100'] = {'id': self.mappings['hard_ware_dependent'][str(data.get('custom_hardwaredependent', None))]} #hard_ware_dependent NA for ukqa
                payload['fields']['customfield_10292'] = {'id' : self.mappings['omnia_squad_map'][str(data['custom_squad_name'])] if self.project_key == 'OMNIA' else self.mappings['gbs_squad_map'][str(data.get('custom_case_gbs_squad', None))]}
        response = post(url='{host_name}rest/api/2/issue'.format(host_name=self.url), headers=self.headers,
                    json=payload, verify=False,allow_redirects=False)
        if response.status_code != 201:
            raise Exception(f"API Error {response.status_code}: {response.text}")
        return response.json()

    def update_case_to_repo(self, case_id, test_repo):
        payload = {
            "fields": {
                "customfield_10270": test_repo}
        }
        return requests.put(url=f"{self.url}rest/api/2/issue/{case_id}", headers=self.headers, json=payload, verify=False)


    def get_repo_folders(self):
        response = requests.get(url='%s%s' %(self.url, 'rest/raven/1.0/api/testrepository/DFE/folders/-1'), headers=self.headers, verify=False)
        if response.status_code == 200:
            try:
                return response.json()
            except json.JSONDecodeError:
                return {"error": f"Invalid JSON response: {response.text}"}
        else:
            return {"error": f"HTTP {response.status_code}: {response.text}"}

    def get_test_case(self, key):
        url = f'{self.url}/rest/raven/1.0/api/test?keys={key}'
        response = requests.get(url=url, headers=self.headers, verify=False)
        return response

    def get_field_options(self):
        url = self.url + '/rest/api/3/issue/{DF-2292}'
        response = requests.get(url=url, headers=self.headers, verify=False)
        fields = response.json()

    def upload_jira_attachment(self, issue_key, file_bytes, file_name):
        url = f"{self.url}rest/api/2/issue/{issue_key}/attachments"
        files = {
            "file": (file_name, file_bytes)
        }
        
        # Create headers without Content-Type and Accept for file upload
        upload_headers = {
            'Authorization': self.headers['Authorization'],
            'X-Atlassian-Token': 'no-check'
        }

        response = requests.post(
            url,
            headers=upload_headers,
            files=files,
            verify=False,
            allow_redirects=False
        )

        if response.status_code not in [200, 201]:
            raise Exception(f"Upload failed {response.status_code}: {response.text}")
        return response.json()[0]  # attachment metadata
