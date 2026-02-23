import base64
import json
from bs4 import MarkupResemblesLocatorWarning
import warnings
import mimetypes
import os
import re
from pathlib import Path
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import requests

from utilities.log_mngr import setup_custom_logger
from utilities.requests_wrapper import do_request

load_dotenv()


class XrayClient:
    _logger = setup_custom_logger()
    #https://jira-enterprise-uat.corp.entaingroup.com
    def __init__(self,
                 base_url='https://jira-enterprise.corp.entaingroup.com/',
                 project_key='DFE', # TODO DFE,DF, DBT OMNIA, RGE for GBS, UKQA for envision,
                 issue_type='Test',
                 test_repo_ = 'LCG Sportsbook Master TestSuite', #TODO  modify the Test Repository Path based on the project LCG Digital Master Suite
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
        if d in [2, 5, 4]: #  If tablet is present then we are making it to mobile in xray
            return self.mappings['xr_devices']['1']
        return self.mappings['xr_devices'][str(d)]

    @staticmethod
    def strip_html(html_text):
        if not html_text:
            return html_text
        warnings.filterwarnings("ignore", category=MarkupResemblesLocatorWarning)
        soup = BeautifulSoup(html_text, "html.parser")
        # return soup.get_text(strip=True)
        text = soup.get_text(separator='\n')

    #   to remove excessive blank lines
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = '\n'.join(chunk for chunk in chunks if chunk)
        return text

    def create_issue(self, data, issue_type=None,test_repo=None):
        self._logger.info(f"Creating issue: type={issue_type or self.issue_type}, project={self.project_key}")
        payload = {
            "fields": {
                "project": {"key": self.project_key},
                "summary": data['title'].replace("\r", "").replace("\n", " ") if issue_type==self.issue_type else data['name'],
                "issuetype": {"name": issue_type if issue_type is not None else self.issue_type},
                "priority": {"id": self.mappings['xray_priority'].get(str(data.get('custom_priorityomnia')), self.mappings['xray_priority']['3']) if self.project_key == 'OMNIA' else self.mappings['xray_priority'].get(str(data.get('priority_id')), self.mappings['xray_priority']['3'])}
            }
        }
        if issue_type == 'Test Execution' and data['description']:
            payload['decription'] = data['description']
            payload['priority'] = '10001'
        elif issue_type == self.issue_type:
            payload['fields']["description"] = self.strip_html(data['custom_description']) if data['custom_description'] else '' #Description
            payload['fields']["customfield_10270"] = test_repo if test_repo else self.test_repository # Test Repository Path
            automation_status_map = self.mappings.get(f'{self.project_key.lower()}_automation_status', {})
            default_automation_id = list(automation_status_map.values())[0] if automation_status_map else '10600'
            if self.project_key not in ['UKQA', 'RGE', 'OMNIA']:
                automation_id = automation_status_map.get(str(data.get('custom_automatedd')), default_automation_id)
            else:
                automation_id = automation_status_map.get(str(data.get('custom_autotype')), default_automation_id)
            payload['fields']["customfield_11426"] = {"id": automation_id}
            payload['fields']['customfield_13006'] = self.strip_html(data['custom_preconds']) #Preconditions Previous id 12901
            payload['fields']['customfield_13001'] = f'S{data['suite_id']}' #Test Suit ID 12903
            payload['fields']['customfield_13004'] = f'C{data['id']}' # Test rail Id 12906
            payload['fields']['customfield_13003'] = data['refs'] #References 12905
            payload['fields']['customfield_13000'] = {'id': self.mappings['xr_test_level']['1'] if data['type_id'] == 1 else self.mappings['xr_test_level']['6']} # Test Level Acceptance/Functional 12902
            if self.project_key in ['DFE', 'DF']:
                payload['fields']['labels'] = [self.mappings['custom_brand'].get(str(data.get('custom_brand')), 'Unknown').replace(" ", "_")]
                payload['fields']['customfield_13005'] = {'id': self.get_custom_device(data.get('custom_device', []))}  # Device 12907
                payload['fields']['customfield_13002'] = self.mappings['feature_map'].get(str(data['custom_feature']) if data['custom_feature'] else '', '')  # Feature dictionary 12904
            if self.project_key in ['OMNIA', 'RGE', 'UKQA']:
                payload['fields']['customfield_13101'] = {'id': self.mappings['lead_sign_off'].get(str(data.get('custom_omnialeadreview')), self.mappings['lead_sign_off']['0'])} #lead sign off
                payload['fields']['customfield_13100'] = {'id': self.mappings['hard_ware_dependent'].get(str(data.get('custom_hardwaredependent')), self.mappings['hard_ware_dependent']['0'])} #hard_ware_dependent NA for ukqa
                payload['fields']['customfield_10292'] = {'id' : self.mappings['omnia_squad_map'].get(str(data.get('custom_squad_name')), self.mappings['omnia_squad_map']['0']) if self.project_key == 'OMNIA' else self.mappings['gbs_squad_map'].get(str(data.get('custom_case_gbs_squad')), self.mappings['gbs_squad_map']['0'])}
        self._logger.debug(f"Payload prepared for issue creation: {json.dumps(payload, indent=2)}")
        response = do_request(url='{host_name}rest/api/2/issue'.format(host_name=self.url), method='POST',json_=payload, headers=self.headers, allow_redirects=False)
        self._logger.info(f"Issue created successfully: {response.get('key', 'N/A')}")
        return response

    def create_test_plan_or_execution(self,test_plan_name,data):
        # payload = {"fields": {
        #         "project": {"key": self.project_key},
        #         "summary": test_plan_name,
        #         "issuetype": {"name": 'Test Plan'},
        #         "description": data['description'],
        #     }
        return True
    def add_steps_to_the_test_case(self, key, steps, testrail_client=None):
        self._logger.info(f"Adding {len(steps)} steps to test case: {key}")
        url = f"{self.url}rest/raven/1.0/api/test/{key}/step/"
        for step in steps:
            step_payload = {
                'step': self.strip_html(step.get('content', '')),
                'data': "None",
                'result': self.strip_html(step.get('expected', '')),
                'attachments': []
            }
            if step_payload['step'] == "" and step_payload['result'] == "":
                continue
            elif step_payload['step'] == "":
                step_payload['step'] = " * "
            
            xray_step = do_request(url=url, method='PUT', json_=step_payload, headers=self.headers)
            if not xray_step or 'id' not in xray_step:
                self._logger.error(f"Failed to create step for test case {key}")
                return False
            self.__class__.step_id = xray_step['id']
            self._logger.debug(f"Step created successfully: step_id={self.__class__.step_id}")
            
            # Process attachments if present in content or expected
            content = step.get('content', '')
            expected = step.get('expected', '')
            if "index.php?/attachments/get/" in content or "index.php?/attachments/get/" in expected:
                attachment_ids = re.findall(r'index\.php\?/attachments/get/([\w-]+)', content + expected)
                self._logger.debug(f"Found {len(attachment_ids)} attachments for step {self.__class__.step_id}")
                for attachment_id in attachment_ids:
                    try:
                        attachment_data,file_name = testrail_client.get_attachment(attachment_id=attachment_id)
                        if not attachment_data:
                            self._logger.warning(f"Skipping attachment {attachment_id} - no data returned")
                            continue
                        encoded_data = base64.b64encode(attachment_data).decode("utf-8")
                        file_name = f'{file_name}.png'
                        mime_type, _ = mimetypes.guess_type(file_name)
                        mime_type = mime_type or "application/octet-stream"
                        payload = {
                            "attachments": {
                                "add": [
                                    {
                                        "data": encoded_data,
                                        "filename": file_name,
                                        "contentType": mime_type
                                    }
                                ]
                            }
                        }
                        attachment_url = f"{self.url}rest/raven/1.0/api/test/{key}/step/{self.__class__.step_id}"
                        do_request(url=attachment_url, method='POST', json_=payload, headers=self.headers)
                        self._logger.debug(f"Attachment uploaded: {file_name}")
                    except Exception as e:
                        self._logger.warning(f"Skipping attachment {attachment_id} for Test Case {key}: {str(e)}")
        return True


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

    def get_cases_from_section(self, section_id = None, project_key = None, limit = 100, all_descendants = True):
        """
        :param section_id:
        :param project_key:
        :param page:
        :param limit:
        :param all_descendants:
        :return: a list of test cases for a test suite or specific section in a test suite.
        """
        page = 1
        results = []
        project_key = self.project_key if project_key is None else project_key
        while True:
            url = f'{self.url}rest/raven/1.0/api/testrepository/{project_key}/folders/{section_id}/tests?page={page}&limit={limit}&allDescendants=true'
            resp = do_request(method='GET', url=url, headers=self.headers)
            data = resp
            if not data:
                break
            results.extend(data)
            page += 1
        return results


    def get_all_sections(self, method='GET',  section = None):
        """
        :param method:
        :param section:
        :return: a list of all sections in a test suite or specific section in a test repository.
        """
        return do_request(url=f'{self.url}rest/raven/1.0/api/testrepository/{self.project_key}/folders/{section}/folders',
                   method=method, headers=self.headers)