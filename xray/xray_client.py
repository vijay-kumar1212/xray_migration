import json
import os
from dotenv import load_dotenv

import requests
from requests import post

load_dotenv()


class XrayClient:
    #https://jira-enterprise.corp.entaingroup.com
    def __init__(self,
                 base_url='https://jira-enterprise-uat.corp.entaingroup.com/',
                 project_key='DFE',
                 issue_type='Test',
                 test_set_id=None,
                 pat=None):
        self.url = base_url
        self.project_key = project_key
        self.issue_type = issue_type
        self.test_set_id = test_set_id
        self.pat = pat if pat is not None else os.environ.get('PAT')
        if not self.pat:
            raise ValueError("PAT environment variable is not set. Please set it using 'export PAT=your_token_here' for mac; for windows use set PAT=your_token_here' or add it to .env file")
        self.headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + self.pat,
            "Accept": "application/json",
            "X-Atlassian-Token": "no-check"
        }

    xray_priority = {
        4: '1',  # xray:'Highest'  testrail:Critical
        3: '2',  # 'High'
        2: '3',  # 'Medium'
        1: '4',  # 'Low'
        5: 'Lowest',
        10000 : 'Urgent',
        10001: 'Unprioritised'
    }

    automation_status = {
        3: '13500',  # xray: "Can't Automate" testrail:Cannot be automated

        1: '13501',  # xray:"Ready For Automation" testrail:Manual

        'Automation In Progress': '13502',

        2: '13503',  # "Automated"

        'Maintenance': 13504,

        'No Automation Required': 13505
    }

    custom_brand = {

        1: 'Coral Only',
        2: 'Ladbrokes Only',
        3: 'Both Coral and Ladbrokes',
        4: 'Vanilla Only',
        5: 'All Brands'
    }

    xr_devices = {
        3: '14906', #'Desktop'
        1 :'14907', #'Mobile'
        13 : '14908', # 'Mobile&Desktop' for tablet in testrail id is 2
        0 : '-1' # None
    }

    def get_custom_device(self, devices):
        if {1, 3}.issubset(devices) or len(devices) >= 2:
            return self.xr_devices[13]
        if not devices:
            return self.xr_devices[0]
        d = devices[0]
        if d == 2: #  If tablet is present then we are making it to mobile in xray
            return self.xr_devices[1]
        return self.xr_devices[d]

    xr_test_level = {
         "-1": "None",
        1 : '14904', # Acceptance
        6 : '14905', # Functional
    }
    FEATURE_MAP = {1: 'User Account', # Test rail Feature naming map for LCG Digital project
                   2: 'Betslip',
                   3: 'Quick Bet',
                   4: 'Bet History/Open Bets',
                   5: 'Cash Out',
                   6: 'Navigation',
                   7: 'Sports',
                   8: 'Races',
                   9: 'In-Play',
                   10: 'Streaming',
                   11: 'Build Your Bet',
                   12: 'Lotto',
                   13: 'Virtual Sports',
                   14: 'Retail',
                   15: 'Featured',
                   16: 'Promotions/Banners/Offers',
                   17: 'Other'}

    def create_issue(self, data, issue_type=None,test_repo=None):
        payload = {
            "fields": {
                "project": {"key": "DFE"},
                "summary": data['title'] if issue_type==self.issue_type else data['name'],
                "issuetype": {"name": issue_type if issue_type is not None else self.issue_type},
                "priority": {"id": XrayClient.xray_priority[data['priority_id']] if issue_type== self.issue_type else '10001'},
                "labels": [XrayClient.custom_brand[data['custom_brand']].replace(" ", "_")] if issue_type == self.issue_type else None,
            }
        }
        if issue_type == 'Test Execution' and data['description']:
            payload['decription'] = data['description']
        if issue_type == self.issue_type:
            payload['fields']["description"] = data['custom_description'] #Description
            payload['fields']["customfield_10270"] = test_repo if test_repo else '/LCG Digital Master Suite' # Test Repository Path
            payload['fields']["customfield_11426"] =  {"id": str(XrayClient.automation_status[data['custom_automatedd']])} # Test Automation status]
            payload['fields']['customfield_12901'] = data['custom_preconds'] #Pre conditions
            payload['fields']['customfield_12903'] = f'S{data['suite_id']}' #Test Suit ID
            payload['fields']['customfield_12906'] = f'C{data['id']}' # Test rail Id
            payload['fields']['customfield_12904'] = self.FEATURE_MAP[data['custom_feature']] # Feature dictionary TODO
            payload['fields']['customfield_12905'] = data['refs'] #References
            payload['fields']['customfield_12907'] = {'id':self.get_custom_device(data['custom_device'])} # Device
            payload['fields']['customfield_12902'] = {'id': self.xr_test_level[1] if data['type_id'] == 1 else self.xr_test_level[6]} # Test Level Acceptance/Functional
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
            return {"error": f"Status {response.status_code}: {response.text}"}

    def create_folder_in_repo(self, folder_name, testRepository, main_folder_id = 22182):
        payload = {
            'name': folder_name,
            "testRepositoryPath": testRepository, # "/LCG Digital"
        }
        return requests.post(
            f"{self.url}rest/raven/1.0/api/testrepository/DFE/folders/{main_folder_id}",
            headers=self.headers,
            json=payload,
            verify=False
        ).json()

    def add_steps_to_the_test_case(self, key, steps):
        url = f"{self.url}rest/raven/1.0/api/test/{key}/step/"
        session = requests.Session()
        session.headers.update(self.headers)
        session.verify = False
        for step in steps:
            step_payload = {
                'step': step['content'],
                'data': "None",
                'result': step['expected'],
                'attachments': []
            }
            session.put(url=url, json=step_payload)
        session.close()

    def get_test_(self, id):
        return requests.get(url='%s%s%s' %(self.url, 'rest/api/2/issue/', id),headers=self.headers, verify=False).json()

    def get_all_tests(self):
        # /rest/raven/1.0/api/test?projectKey=PROJECT_KEY&folderId=FOLDER_ID
        params = {
            "jql": "project = DFE AND issuetype = Test"
        }
        return requests.get(url='%s%s' %(self.url, 'rest/raven/1.0/api/test'),headers=self.headers,params=params, verify=False).json()


    def add_tests_to_test_run(self, key,issues_list):
        data = {'add': issues_list}
        return requests.post(url='%s%s' % (self.url, f'rest/raven/1.0/api/testexec/{key}/test'), json=data,
                             headers=self.headers, verify=False).json()

    def get_run_test_statuses(self):
        url = f"{self.url}rest/raven/1.0/api/testexec/{'DFE-5745'}/test?detailed=true"
        return requests.get(url, headers=self.headers, verify=False).json()


    def update_test_status(self, exec_key, test_key, status):
        return requests.post(url='%s%s' % (self.url, f"rest/raven/1.0/testexec/{exec_key}/execute/{test_key}"), json=status, headers=self.headers, verify=False).json()

    def debug_response(self, method, url, **kwargs):
        """Debug helper to inspect API responses"""
        response = requests.request(method, url, headers=self.headers, verify=False, **kwargs)
        print(f"Status: {response.status_code}")
        print(f"Headers: {dict(response.headers)}")
        print(f"Content: {response.text[:500]}...")  # First 500 chars
        return response

