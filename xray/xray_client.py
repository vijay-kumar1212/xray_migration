import base64
import json
from bs4 import MarkupResemblesLocatorWarning
import warnings
import mimetypes
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from bs4 import BeautifulSoup
from dotenv import load_dotenv
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from utilities.log_mngr import setup_custom_logger
from utilities.requests_wrapper import do_request

load_dotenv()


class XrayClient:
    _logger = setup_custom_logger()

    # === PERFORMANCE IMPROVEMENT: Max workers for parallel attachment processing ===
    MAX_ATTACHMENT_WORKERS = 5

    def __init__(self,
                 base_url='https://jira-enterprise.corp.entaingroup.com/',
                 project_key='UKQA',
                 issue_type='Test',
                 test_repo_='test1',
                 test_set_id=None,
                 pat=None):
        self.url = base_url
        self.project_key = project_key
        self.issue_type = issue_type
        self.test_set_id = test_set_id
        self.test_repository = test_repo_
        mapping_file = Path(__file__).resolve().parent / "xray_mappings.json"
        with open(mapping_file, 'r', encoding="utf-8") as f:
            self.mappings = json.load(f)
        self.pat = pat if pat is not None else os.environ.get('PAT')
        if not self.pat:
            raise ValueError(
                "PAT environment variable is not set. Please set it using 'export PAT=your_token_here' for mac; for windows use set PAT=your_token_here' or add it to .env file")
        self.headers = {
            'Content-Type': 'application/json',
            'Authorization': 'Bearer ' + self.pat,
            "Accept": "application/json",
            "X-Atlassian-Token": "no-check"
        }

        # === PERFORMANCE IMPROVEMENT: Shared session with connection pooling for Jira uploads ===
        # Reuses TCP connections instead of opening a new one per attachment upload.
        self._upload_session = requests.Session()
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["POST", "PUT", "GET"],
            raise_on_status=False
        )
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=20)
        self._upload_session.mount("https://", adapter)
        self._upload_session.mount("http://", adapter)

    def get_custom_device(self, devices):
        if {1, 3}.issubset(devices) or len(devices) >= 2:
            return self.mappings['xr_devices']['13']
        if not devices:
            return self.mappings['xr_devices']['0']
        d = devices[0]
        if d in [2, 5, 4]:
            return self.mappings['xr_devices']['1']
        return self.mappings['xr_devices'][str(d)]

    @staticmethod
    def strip_html(html_text):
        if not html_text:
            return html_text
        warnings.filterwarnings("ignore", category=MarkupResemblesLocatorWarning)
        soup = BeautifulSoup(html_text, "html.parser")
        text = soup.get_text(separator='\n')
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = '\n'.join(chunk for chunk in chunks if chunk)
        return text

    def create_issue(self, data, issue_type=None, test_repo=None):
        self._logger.info(f"Creating issue: type={issue_type or self.issue_type}, project={self.project_key}")
        payload = {
            "fields": {
                "project": {"key": self.project_key},
                "summary": data['title'].replace("\r", "").replace("\n", " ") if issue_type == self.issue_type else
                data['name'],
                "issuetype": {"name": issue_type if issue_type is not None else self.issue_type},
                "priority": {"id": self.mappings['xray_priority'].get(str(data.get('custom_priorityomnia')),
                                                                      self.mappings['xray_priority'][
                                                                          '3']) if self.project_key == 'OMNIA' else
                self.mappings['xray_priority'].get(str(data.get('priority_id')), self.mappings['xray_priority']['3'])}
            }
        }
        if issue_type == 'Test Execution' and data['description']:
            payload['decription'] = data['description']
            payload['priority'] = '10001'
        elif issue_type == self.issue_type:
            payload['fields']["description"] = self.strip_html(data['custom_description']) if data[
                'custom_description'] else ''
            payload['fields']["customfield_10270"] = test_repo if test_repo else self.test_repository
            automation_status_map = self.mappings.get(f'rge_automation_status', {})
            default_automation_id = list(automation_status_map.values())[0] if automation_status_map else '10600'
            if self.project_key not in ['UKQA', 'RGE', 'OMNIA']:
                automation_id = automation_status_map.get(str(data.get('custom_automatedd')), default_automation_id)
            else:
                automation_id = automation_status_map.get(str(data.get('custom_autotype')), default_automation_id)
            payload['fields']["customfield_11426"] = {"id": automation_id}
            payload['fields']['customfield_13006'] = self.strip_html(data['custom_preconds'])
            payload['fields']['customfield_13001'] = f'S{data['suite_id']}'
            payload['fields']['customfield_13004'] = f'C{data['id']}'
            payload['fields']['customfield_13003'] = data['refs']
            payload['fields']['customfield_13000'] = {
                'id': self.mappings['xr_test_level']['1'] if data['type_id'] == 1 else self.mappings['xr_test_level'][
                    '6']}
            if self.project_key in ['DFE', 'DF']:
                payload['fields']['labels'] = [
                    self.mappings['custom_brand'].get(str(data.get('custom_brand')), 'Unknown').replace(" ", "_")]
                payload['fields']['customfield_13005'] = {'id': self.get_custom_device(data.get('custom_device', []))}
                payload['fields']['customfield_13002'] = self.mappings['feature_map'].get(
                    str(data['custom_feature']) if data['custom_feature'] else '', '')
            if self.project_key in ['OMNIA', 'RGE', 'UKQA']:
                payload['fields']['customfield_13101'] = {
                    'id': self.mappings['lead_sign_off'].get(str(data.get('custom_omnialeadreview')),
                                                             self.mappings['lead_sign_off']['None'])}
                payload['fields']['customfield_13100'] = {
                    'id': self.mappings['hard_ware_dependent'].get(str(data.get('custom_hardwaredependent')),
                                                                   self.mappings['hard_ware_dependent']['None'])}
                payload['fields']['customfield_10292'] = {
                    'id': self.mappings['omnia_squad_map'].get(str(data.get('custom_squad_name')),
                                                               self.mappings['omnia_squad_map'][
                                                                   'None']) if self.project_key == 'OMNIA' else
                    self.mappings['gbs_squad_map'].get(str(data.get('custom_case_gbs_squad')),
                                                       self.mappings['gbs_squad_map']['None'])}
        self._logger.debug(f"Payload prepared for issue creation: {json.dumps(payload, indent=2)}")
        response = do_request(url='{host_name}rest/api/2/issue'.format(host_name=self.url), method='POST',
                              json_=payload, headers=self.headers, allow_redirects=False)
        self._logger.info(f"Issue created successfully: {response.get('key', 'N/A')}")
        return response

    def create_test_plan_or_execution(self, test_plan_name, data):
        return True

    def _download_and_encode_attachment(self, testrail_client, attachment_id):
        """
        === PERFORMANCE IMPROVEMENT: Extracted helper for parallel attachment processing ===
        Downloads an attachment from TestRail and returns base64-encoded data ready for Xray upload.
        This method is thread-safe and designed to be called from ThreadPoolExecutor.
        """
        attachment_data, file_name = testrail_client.get_attachment(attachment_id=attachment_id)
        if not attachment_data:
            return None
        encoded_data = base64.b64encode(attachment_data).decode("utf-8")
        file_name = f'{file_name}.png'
        mime_type, _ = mimetypes.guess_type(file_name)
        mime_type = mime_type or "application/octet-stream"
        return {
            'attachment_id': attachment_id,
            'encoded_data': encoded_data,
            'file_name': file_name,
            'mime_type': mime_type
        }

    def add_steps_to_the_test_case(self, key, steps, testrail_client=None):
        """
        PERFORMANCE CHANGES in this method:
        1. Pre-collects ALL attachment IDs across all steps before processing
        2. Downloads all attachments in PARALLEL using ThreadPoolExecutor
        3. Caches downloaded attachments to avoid re-downloading duplicates across steps
        4. Uploads attachments to steps using the pre-downloaded cache
        This reduces the total time from O(steps * attachments_per_step) sequential API calls
        to O(steps) sequential step creation + O(unique_attachments) parallel downloads.
        """
        self._logger.info(f"Adding {len(steps)} steps to test case: {key}")
        url = f"{self.url}rest/raven/1.0/api/test/{key}/step/"

        # === PERFORMANCE IMPROVEMENT: Pre-collect all unique attachment IDs across all steps ===
        all_attachment_ids = set()
        for step in steps:
            content = step.get('content', '')
            expected = step.get('expected', '')
            combined = content + expected
            if "index.php?/attachments/get/" in combined:
                ids = re.findall(r'index\.php\?/attachments/get/([\w-]+)', combined)
                all_attachment_ids.update(ids)

        # === PERFORMANCE IMPROVEMENT: Download ALL attachments in parallel before step creation ===
        attachment_cache = {}
        if all_attachment_ids and testrail_client:
            self._logger.info(f"Pre-downloading {len(all_attachment_ids)} unique attachments in parallel for {key}")
            with ThreadPoolExecutor(max_workers=self.MAX_ATTACHMENT_WORKERS) as executor:
                future_to_id = {
                    executor.submit(self._download_and_encode_attachment, testrail_client, att_id): att_id
                    for att_id in all_attachment_ids
                }
                for future in as_completed(future_to_id):
                    att_id = future_to_id[future]
                    try:
                        result = future.result()
                        if result:
                            attachment_cache[att_id] = result
                    except Exception as e:
                        self._logger.warning(f"Failed to pre-download attachment {att_id} for {key}: {str(e)}")
            self._logger.info(f"Pre-downloaded {len(attachment_cache)}/{len(all_attachment_ids)} attachments for {key}")

        # Process steps sequentially (Xray API requires ordered step creation)
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

            # === PERFORMANCE IMPROVEMENT: Upload attachments from pre-downloaded cache ===
            content = step.get('content', '')
            expected = step.get('expected', '')
            if "index.php?/attachments/get/" in content or "index.php?/attachments/get/" in expected:
                attachment_ids = re.findall(r'index\.php\?/attachments/get/([\w-]+)', content + expected)
                self._logger.debug(f"Found {len(attachment_ids)} attachments for step {self.__class__.step_id}")
                for attachment_id in attachment_ids:
                    try:
                        cached = attachment_cache.get(attachment_id)
                        if not cached:
                            self._logger.warning(f"Skipping attachment {attachment_id} - not in cache")
                            continue
                        payload = {
                            "attachments": {
                                "add": [
                                    {
                                        "data": cached['encoded_data'],
                                        "filename": cached['file_name'],
                                        "contentType": cached['mime_type']
                                    }
                                ]
                            }
                        }
                        attachment_url = f"{self.url}rest/raven/1.0/api/test/{key}/step/{self.__class__.step_id}"
                        do_request(url=attachment_url, method='POST', json_=payload, headers=self.headers)
                        self._logger.debug(f"Attachment uploaded: {cached['file_name']}")
                    except Exception as e:
                        self._logger.warning(f"Skipping attachment {attachment_id} for Test Case {key}: {str(e)}")
        return True

    def upload_precondition_attachments_parallel(self, issue_key, attachment_ids, testrail_client):
        """
        === PERFORMANCE IMPROVEMENT: Parallel precondition attachment upload ===
        Downloads and uploads all precondition attachments in parallel instead of sequentially.
        Returns count of successfully uploaded attachments.
        """
        uploaded = 0

        def _download_and_upload(att_id):
            attachment_data, file_name = testrail_client.get_attachment(att_id)
            if attachment_data:
                self.upload_jira_attachment(
                    issue_key=issue_key,
                    file_name=f'prerequisite_{file_name}.png',
                    file_bytes=attachment_data
                )
                return True
            return False

        with ThreadPoolExecutor(max_workers=self.MAX_ATTACHMENT_WORKERS) as executor:
            future_to_id = {
                executor.submit(_download_and_upload, att_id): att_id
                for att_id in attachment_ids
            }
            for future in as_completed(future_to_id):
                att_id = future_to_id[future]
                try:
                    if future.result():
                        uploaded += 1
                except Exception as e:
                    self._logger.warning(f"Skipping precondition attachment {att_id} for {issue_key}: {str(e)}")

        return uploaded

    def update_case_to_repo(self, case_id, test_repo):
        payload = {
            "fields": {
                "customfield_10270": test_repo}
        }
        return requests.put(url=f"{self.url}rest/api/2/issue/{case_id}", headers=self.headers, json=payload,
                            verify=False)

    def get_repo_folders(self):
        response = requests.get(url='%s%s' % (self.url, 'rest/raven/1.0/api/testrepository/DFE/folders/-1'),
                                headers=self.headers, verify=False)
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
        """
        PERFORMANCE CHANGE: Uses shared session with connection pooling
        instead of raw requests.post (was: new connection per upload).
        """
        url = f"{self.url}rest/api/2/issue/{issue_key}/attachments"
        files = {
            "file": (file_name, file_bytes)
        }
        upload_headers = {
            'Authorization': self.headers['Authorization'],
            'X-Atlassian-Token': 'no-check'
        }
        response = self._upload_session.post(
            url,
            headers=upload_headers,
            files=files,
            verify=False,
            allow_redirects=False
        )
        if response.status_code not in [200, 201]:
            raise Exception(f"Upload failed {response.status_code}: {response.text}")
        return response.json()[0]

    def get_cases_from_section(self, section_id=None, project_key=None, limit=100, all_descendants=True):
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

    def get_all_sections(self, method='GET', section=None):
        """
        :param method:
        :param section:
        :return: a list of all sections in a test suite or specific section in a test repository.
        """
        return do_request(
            url=f'{self.url}rest/raven/1.0/api/testrepository/{self.project_key}/folders/{section}/folders',
            method=method, headers=self.headers)
