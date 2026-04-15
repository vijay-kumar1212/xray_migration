"""
Xray Client for Jira Cloud (Xray as Jira App)
==============================================
All operations go through https://entain-test.atlassian.net/
Authentication: Basic Auth (email + API token) for everything.
Xray endpoints: rest/raven/1.0/api/ (embedded in Jira Cloud)
Jira endpoints: rest/api/3/ (Jira Cloud REST API v3)
"""

import base64
import json
from bs4 import MarkupResemblesLocatorWarning
import warnings
import mimetypes
import os
import re
import time
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
    MAX_ATTACHMENT_WORKERS = 5

    def __init__(self,
                 base_url='https://entain-test.atlassian.net/',
                 project_key='OMNIA',
                 issue_type='Test',
                 test_repo_='Cloud Instance Test',
                 test_set_id=None,
                 jira_email=None,
                 jira_api_token=None):
        self.url = base_url if base_url.endswith('/') else base_url + '/'
        self.project_key = project_key
        self.issue_type = issue_type
        self.test_set_id = test_set_id
        self.test_repository = test_repo_

        mapping_file = Path(__file__).resolve().parent / "xray_mappings.json"
        with open(mapping_file, 'r', encoding="utf-8") as f:
            self.mappings = json.load(f)

        # Auth: Basic Auth (email + API token) for ALL requests
        self.jira_email = jira_email or os.environ.get('JIRA_CLOUD_EMAIL')
        self.jira_api_token = jira_api_token or os.environ.get('JIRA_API_TOKEN')
        if not self.jira_email or not self.jira_api_token:
            raise ValueError(
                "JIRA_CLOUD_EMAIL and JIRA_API_TOKEN must be set in .env file. "
                "Generate a token at https://id.atlassian.com/manage-profile/security/api-tokens")
        creds = base64.b64encode(
            f"{self.jira_email}:{self.jira_api_token}".encode()).decode()
        self.headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Basic {creds}',
            'Accept': 'application/json',
            'X-Atlassian-Token': 'no-check'
        }

        self._upload_session = requests.Session()
        retry = Retry(total=3, backoff_factor=1,
                      status_forcelist=[429, 500, 502, 503, 504],
                      allowed_methods=["POST", "PUT", "GET"],
                      raise_on_status=False)
        adapter = HTTPAdapter(max_retries=retry,
                              pool_connections=10, pool_maxsize=20)
        self._upload_session.mount("https://", adapter)
        self._upload_session.mount("http://", adapter)

        # Optional: Xray Cloud GraphQL API for folder operations
        # Set XRAY_CLIENT_ID and XRAY_CLIENT_SECRET in .env to enable
        self._xray_graphql_available = False
        self._xray_token = None
        self._xray_token_expiry = 0
        xray_id = os.environ.get('XRAY_CLIENT_ID', '')
        xray_secret = os.environ.get('XRAY_CLIENT_SECRET', '')
        if xray_id and xray_secret and not xray_id.startswith('your-'):
            try:
                self._xray_client_id = xray_id
                self._xray_client_secret = xray_secret
                self._authenticate_xray()
                self._xray_graphql_available = True
                self._logger.info("Xray Cloud GraphQL enabled (folder operations available)")
            except Exception as e:
                self._logger.warning(f"Xray Cloud auth failed, folder operations disabled: {e}")
        else:
            self._logger.info("Xray Cloud API keys not set — folder operations will be skipped")

    # ===================== XRAY CLOUD GRAPHQL (optional, for folder ops) =====================

    def _authenticate_xray(self):
        resp = requests.post('https://xray.cloud.getxray.app/api/v2/authenticate',
                             json={"client_id": self._xray_client_id,
                                   "client_secret": self._xray_client_secret},
                             headers={'Content-Type': 'application/json'})
        if resp.status_code != 200:
            raise ValueError(f"Xray auth failed ({resp.status_code}): {resp.text}")
        self._xray_token = resp.text.strip('"')
        self._xray_token_expiry = time.time() + (23 * 3600)

    def _xray_headers(self):
        if time.time() >= self._xray_token_expiry:
            self._authenticate_xray()
        return {'Content-Type': 'application/json',
                'Authorization': f'Bearer {self._xray_token}'}

    def _graphql(self, query, variables=None):
        if not self._xray_graphql_available:
            return None
        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        resp = self._upload_session.post('https://xray.cloud.getxray.app/api/v2/graphql',
                                         json=payload, headers=self._xray_headers(), timeout=60)
        if resp.status_code != 200:
            self._logger.error(f"GraphQL failed ({resp.status_code}): {resp.text}")
            return None
        result = resp.json()
        if 'errors' in result:
            self._logger.error(f"GraphQL errors: {result['errors']}")
            return None
        return result.get('data')

    # ===================== UTILITIES =====================

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
        chunks = (phrase.strip() for line in lines
                  for phrase in line.split("  "))
        text = '\n'.join(chunk for chunk in chunks if chunk)
        return text

    # ===================== ISSUE CREATION =====================

    def create_issue(self, data, issue_type=None, test_repo=None):
        self._logger.info(f"Creating issue: type={issue_type or self.issue_type}, project={self.project_key}")
        raw_desc = ''
        if issue_type == 'Test Execution' and data.get('description'):
            raw_desc = data['description']
        elif issue_type == self.issue_type:
            raw_desc = self.strip_html(data.get('custom_description', '')) or ''
        adf_desc = {"version": 1, "type": "doc",
                    "content": [{"type": "paragraph",
                                 "content": [{"type": "text", "text": raw_desc}] if raw_desc else []}]}
        payload = {"fields": {
            "project": {"key": self.project_key},
            "summary": (data['title'].replace("\r", "").replace("\n", " ")
                        if issue_type == self.issue_type else data['name']),
            "issuetype": {"name": issue_type or self.issue_type},
            "description": adf_desc,
            "priority": {"name": (
                self.mappings['xray_priority'].get(str(data.get('custom_priorityomnia')),
                    self.mappings['xray_priority']['2']) if self.project_key == 'OMNIA'
                else self.mappings['xray_priority'].get(str(data.get('priority_id')),
                    self.mappings['xray_priority']['2']))}
        }}
        if issue_type == 'Test Execution':
            payload['fields']['priority'] = {'name': 'Medium'}
        elif issue_type == self.issue_type:
            auto_map = self.mappings.get(f'{self.project_key.lower()}_automation_status', {}) # TODO
            default_auto = list(auto_map.values())[0] if auto_map else '10600'
            auto_id = (auto_map.get(str(data.get('custom_automatedd')), default_auto)
                       if self.project_key not in ['UKQA', 'RGE', 'OMNIA']
                       else auto_map.get(str(data.get('custom_autotype')), default_auto))
            payload['fields']["customfield_10488"] = {"id": auto_id}
            precond = self.strip_html(data.get('custom_preconds', '')) or ''
            payload['fields']['customfield_10624'] = {"version": 1, "type": "doc",
                "content": [{"type": "paragraph",
                             "content": [{"type": "text", "text": precond}] if precond else []}]}
            payload['fields']['customfield_10618'] = f'S{data["suite_id"]}'
            payload['fields']['customfield_10621'] = f'C{data["id"]}'
            payload['fields']['customfield_10623'] = data.get('refs', '')
            payload['fields']['customfield_10616'] = {
                'id': (self.mappings['xr_test_level']['1'] if data.get('type_id') == 1
                       else self.mappings['xr_test_level']['6'])}
            if self.project_key in ['DFE', 'DF']:
                payload['fields']['labels'] = [
                    self.mappings['custom_brand'].get(str(data.get('custom_brand')), 'Unknown').replace(" ", "_")]
                payload['fields']['customfield_10617'] = {'id': self.get_custom_device(data.get('custom_device', []))}
                payload['fields']['customfield_10620'] = self.mappings['feature_map'].get(
                    str(data.get('custom_feature')) if data.get('custom_feature') else '', '')
            if self.project_key in ['OMNIA', 'RGE', 'UKQA']:
                payload['fields']['customfield_10622'] = {'id': self.mappings['lead_sign_off'].get(
                    str(data.get('custom_omnialeadreview')), self.mappings['lead_sign_off']['None'])}
                payload['fields']['customfield_10619'] = {'id': self.mappings['hard_ware_dependent'].get(
                    str(data.get('custom_hardwaredependent')), self.mappings['hard_ware_dependent']['None'])}
                squad_id = (self.mappings['omnia_squad_map'].get(str(data.get('custom_squad_name')),
                    self.mappings['omnia_squad_map']['None']) if self.project_key == 'OMNIA'
                    else self.mappings['gbs_squad_map'].get(str(data.get('custom_case_gbs_squad')),
                    self.mappings['gbs_squad_map']['None']))
                payload['fields']['customfield_10449'] = {'id': squad_id}
        self._logger.debug(f"Payload: {json.dumps(payload, indent=2)}")
        response = do_request(url=f"{self.url}rest/api/3/issue", method='POST',
                              json_=payload, headers=self.headers, allow_redirects=False)
        self._logger.info(f"Issue created: {response.get('key', 'N/A')}")

        # Move test to folder in Test Repository via Xray Cloud GraphQL
        if issue_type == self.issue_type and response and 'key' in response:
            folder_path = test_repo or self.test_repository
            if self._xray_graphql_available:
                self._ensure_folder_exists(folder_path)
                self._move_test_to_folder(response['key'], folder_path)
            else:
                self._logger.info(f"Test {response['key']} created. Target folder: {folder_path} (move skipped — no Xray API keys)")

        return response

    def create_test_plan(self, name, project_key=None):
        """Create a Test Plan issue in Jira via REST API v3."""
        project_key = project_key or self.project_key
        self._logger.info(f"Creating Test Plan: '{name}' in project {project_key}")
        adf_desc = {"version": 1, "type": "doc",
                    "content": [{"type": "paragraph", "content": []}]}
        payload = {"fields": {
            "project": {"key": project_key},
            "summary": name,
            "issuetype": {"name": "Test Plan"},
            "description": adf_desc
        }}
        response = do_request(url=f"{self.url}rest/api/3/issue", method='POST',
                              json_=payload, headers=self.headers, allow_redirects=False)
        if 'error' in response:
            self._logger.error(f"Failed to create Test Plan: {response['error']}")
            return response
        self._logger.info(f"Test Plan created: {response.get('key', 'N/A')}")
        return response

    def create_test_execution(self, name, project_key=None, plan_key=None):
        """Create a Test Execution issue and optionally link it to a Test Plan."""
        project_key = project_key or self.project_key
        self._logger.info(f"Creating Test Execution: '{name}' in project {project_key}")
        adf_desc = {"version": 1, "type": "doc",
                    "content": [{"type": "paragraph", "content": []}]}
        payload = {"fields": {
            "project": {"key": project_key},
            "summary": name,
            "issuetype": {"name": "Test Execution"},
            "description": adf_desc
        }}
        response = do_request(url=f"{self.url}rest/api/3/issue", method='POST',
                              json_=payload, headers=self.headers, allow_redirects=False)
        if 'error' in response:
            self._logger.error(f"Failed to create Test Execution: {response['error']}")
            return response
        self._logger.info(f"Test Execution created: {response.get('key', 'N/A')}")
        if plan_key and self._xray_graphql_available:
            try:
                plan_resp = self._upload_session.get(
                    f'{self.url}rest/api/3/issue/{plan_key}?fields=summary',
                    headers=self.headers, timeout=30)
                exec_resp = self._upload_session.get(
                    f'{self.url}rest/api/3/issue/{response["key"]}?fields=summary',
                    headers=self.headers, timeout=30)
                if plan_resp.status_code == 200 and exec_resp.status_code == 200:
                    plan_id = plan_resp.json()['id']
                    exec_id = exec_resp.json()['id']
                    link_result = self._graphql("""
                        mutation AddTestExecutionsToTestPlan($testPlanIssueId: String!, $testExecIssueIds: [String!]!) {
                            addTestExecutionsToTestPlan(issueId: $testPlanIssueId, testExecIssueIds: $testExecIssueIds) {
                                addedTestExecutions
                                warning
                            }
                        }
                    """, {"testPlanIssueId": plan_id, "testExecIssueIds": [exec_id]})
                    if link_result:
                        self._logger.info(f"Linked {response['key']} to Test Plan {plan_key}")
                    else:
                        self._logger.warning(f"Failed to link {response['key']} to Test Plan {plan_key}")
                else:
                    self._logger.warning(f"Could not resolve keys for linking: {plan_key}, {response['key']}")
            except Exception as e:
                self._logger.warning(f"Error linking execution to plan: {e}")
        return response

    def _move_test_to_folder(self, issue_key, folder_path):
        """Move a test into a Test Repository folder via Xray Cloud GraphQL."""
        if not folder_path.startswith('/'):
            folder_path = '/' + folder_path
        try:
            # Resolve issue key to issue ID (GraphQL needs numeric ID)
            resp = self._upload_session.get(
                f"{self.url}rest/api/3/issue/{issue_key}?fields=summary",
                headers=self.headers, timeout=30)
            if resp.status_code != 200:
                self._logger.warning(f"Could not resolve {issue_key} to ID, skipping folder move")
                return
            issue_id = resp.json()['id']

            # Use updateTestFolder GraphQL mutation
            result = self._graphql(
                """mutation($issueId: String!, $folderPath: String!) {
                    updateTestFolder(issueId: $issueId, folderPath: $folderPath)
                }""",
                {"issueId": issue_id, "folderPath": folder_path})
            if result is not None:
                self._logger.debug(f"Moved {issue_key} to folder '{folder_path}'")
            else:
                self._logger.warning(f"Failed to move {issue_key} to folder '{folder_path}'")
        except Exception as e:
            self._logger.warning(f"Error moving {issue_key} to folder '{folder_path}': {e}")

    def _ensure_folder_exists(self, folder_path):
        """
        Create a folder in the Test Repository via Xray Cloud GraphQL.
        Returns True on success, None on failure.
        """
        if not self._xray_graphql_available:
            self._logger.warning("Xray Cloud GraphQL not available — cannot create folders")
            return None
        if not folder_path.startswith('/'):
            folder_path = '/' + folder_path

        # Resolve project key to numeric project ID
        proj_resp = self._upload_session.get(
            f'{self.url}rest/api/3/project/{self.project_key}',
            headers=self.headers, timeout=30)
        if proj_resp.status_code != 200:
            self._logger.error(f"Could not resolve project {self.project_key}")
            return None
        project_id = proj_resp.json()['id']

        data = self._graphql("""
            mutation CreateFolder($projectId: String!, $path: String!) {
                createFolder(projectId: $projectId, path: $path) {
                    folder {
                        name
                        path
                    }
                    warnings
                }
            }
        """, {"projectId": project_id, "path": folder_path})
        if data and 'createFolder' in data:
            self._logger.info(f"Folder ensured: {folder_path}")
            return True
        self._logger.error(f"Failed to create folder: {folder_path}")
        return None

    # ===================== ATTACHMENTS =====================

    def _download_and_encode_attachment(self, testrail_client, attachment_id):
        attachment_data, file_name = testrail_client.get_attachment(attachment_id=attachment_id)
        if not attachment_data:
            return None
        encoded_data = base64.b64encode(attachment_data).decode("utf-8")
        file_name = f'{file_name}.png'
        mime_type, _ = mimetypes.guess_type(file_name)
        mime_type = mime_type or "application/octet-stream"
        return {'attachment_id': attachment_id, 'encoded_data': encoded_data,
                'file_name': file_name, 'mime_type': mime_type}

    def upload_jira_attachment(self, issue_key, file_bytes, file_name):
        url = f"{self.url}rest/api/3/issue/{issue_key}/attachments"
        files = {"file": (file_name, file_bytes)}
        upload_headers = {'Authorization': self.headers['Authorization'],
                          'X-Atlassian-Token': 'no-check'}
        response = self._upload_session.post(url, headers=upload_headers, files=files,
                                             timeout=60, allow_redirects=False)
        if response.status_code not in [200, 201]:
            raise Exception(f"Upload failed {response.status_code}: {response.text}")
        return response.json()[0]

    def upload_precondition_attachments_parallel(self, issue_key, attachment_ids, testrail_client):
        uploaded = 0
        def _download_and_upload(att_id):
            attachment_data, file_name = testrail_client.get_attachment(att_id)
            if attachment_data:
                self.upload_jira_attachment(issue_key=issue_key,
                    file_name=f'prerequisite_{file_name}.png', file_bytes=attachment_data)
                return True
            return False
        with ThreadPoolExecutor(max_workers=self.MAX_ATTACHMENT_WORKERS) as executor:
            future_to_id = {executor.submit(_download_and_upload, aid): aid for aid in attachment_ids}
            for future in as_completed(future_to_id):
                try:
                    if future.result():
                        uploaded += 1
                except Exception as e:
                    self._logger.warning(f"Skipping attachment {future_to_id[future]} for {issue_key}: {e}")
        return uploaded

    # ===================== TEST STEPS (Xray Cloud GraphQL) =====================

    def add_steps_to_the_test_case(self, key, steps, testrail_client=None):
        """Add test steps via Xray Cloud GraphQL API (updateTestSteps mutation)."""
        self._logger.info(f"Adding {len(steps)} steps to test case: {key}")

        if not self._xray_graphql_available:
            self._logger.error("Xray Cloud GraphQL not available — cannot add steps")
            return False

        # Resolve issue key to Jira issue ID (GraphQL needs the internal ID)
        try:
            resp = self._upload_session.get(
                f"{self.url}rest/api/3/issue/{key}?fields=summary",
                headers=self.headers, timeout=30)
            if resp.status_code != 200:
                self._logger.error(f"Could not resolve {key} to ID: {resp.status_code}")
                return False
            issue_id = resp.json()['id']
        except Exception as e:
            self._logger.error(f"Error resolving {key}: {e}")
            return False

        # Pre-download attachments referenced in steps
        all_attachment_ids = set()
        for step in steps:
            combined = step.get('content', '') + step.get('expected', '')
            if "index.php?/attachments/get/" in combined:
                all_attachment_ids.update(re.findall(r'index\.php\?/attachments/get/([\w-]+)', combined))
        attachment_cache = {}
        if all_attachment_ids and testrail_client:
            self._logger.info(f"Pre-downloading {len(all_attachment_ids)} attachments for {key}")
            with ThreadPoolExecutor(max_workers=self.MAX_ATTACHMENT_WORKERS) as executor:
                future_to_id = {executor.submit(self._download_and_encode_attachment, testrail_client, aid): aid
                                for aid in all_attachment_ids}
                for future in as_completed(future_to_id):
                    aid = future_to_id[future]
                    try:
                        result = future.result()
                        if result:
                            attachment_cache[aid] = result
                    except Exception as e:
                        self._logger.warning(f"Failed to download attachment {aid} for {key}: {e}")
            self._logger.info(f"Downloaded {len(attachment_cache)}/{len(all_attachment_ids)} attachments for {key}")

        # Build GraphQL steps array
        gql_steps = []
        for step in steps:
            action = self.strip_html(step.get('content', '')) or ''
            result = self.strip_html(step.get('expected', '')) or ''
            if action == '' and result == '':
                continue
            if action == '':
                action = ' * '

            step_obj = {"action": action, "data": "", "result": result}

            # Attach inline attachments if any
            combined = step.get('content', '') + step.get('expected', '')
            if "index.php?/attachments/get/" in combined:
                att_ids = re.findall(r'index\.php\?/attachments/get/([\w-]+)', combined)
                attachments = []
                for att_id in att_ids:
                    cached = attachment_cache.get(att_id)
                    if cached:
                        attachments.append({
                            "data": cached['encoded_data'],
                            "filename": cached['file_name'],
                            "mimeType": cached['mime_type']
                        })
                if attachments:
                    step_obj["attachments"] = attachments

            gql_steps.append(step_obj)

        if not gql_steps:
            self._logger.warning(f"No valid steps to add for {key}")
            return True

        # Execute GraphQL mutation — add steps one at a time
        for i, step_obj in enumerate(gql_steps):
            mutation = """
            mutation AddTestStep($issueId: String!, $step: CreateStepInput!) {
                addTestStep(issueId: $issueId, step: $step) {
                    id
                    action
                    data
                    result
                }
            }
            """
            step_input = {
                "action": step_obj["action"],
                "data": step_obj.get("data", ""),
                "result": step_obj.get("result", "")
            }
            # Add attachments if present
            if "attachments" in step_obj:
                step_input["attachments"] = step_obj["attachments"]

            result = self._graphql(mutation, {"issueId": issue_id, "step": step_input})
            if result and 'addTestStep' in result:
                self._logger.debug(f"Step {i+1} added: id={result['addTestStep'].get('id')}")
            else:
                self._logger.error(f"Failed to add step {i+1} to {key}")
                return False

        self._logger.info(f"Successfully added {len(gql_steps)} steps to {key}")
        return True

    # ===================== ISSUE QUERIES =====================

    def update_case_to_repo(self, case_id, test_repo):
        """Move a test case to a different test repository folder via Xray REST API."""
        self._move_test_to_folder(case_id, test_repo)

    def get_repo_folders(self):
        """Get test repository folders via Xray Cloud GraphQL."""
        if not self._xray_graphql_available:
            return {"error": "Xray Cloud GraphQL not available"}
        data = self._graphql("""
            query GetFolders($projectId: String!) {
                getFolder(projectId: $projectId, path: "/") {
                    name
                    folders {
                        name
                        folders {
                            name
                        }
                    }
                }
            }
        """, {"projectId": self.project_key})
        return data if data else {"error": "GraphQL query failed"}

    def get_test_case(self, key):
        """Get test details via Xray Cloud GraphQL."""
        if not self._xray_graphql_available:
            return None
        # Resolve issue ID first
        resp = self._upload_session.get(
            f'{self.url}rest/api/3/issue/{key}?fields=summary',
            headers=self.headers, timeout=30)
        if resp.status_code != 200:
            return None
        issue_id = resp.json()['id']
        data = self._graphql("""
            query GetTest($issueId: String!) {
                getTest(issueId: $issueId) {
                    issueId
                    testType { name }
                    steps { id action data result }
                    folder { path }
                }
            }
        """, {"issueId": issue_id})
        return data

    def get_issue_summary(self, key):
        url = f'{self.url}rest/api/3/issue/{key}?fields=summary'
        response = self._upload_session.get(url=url, headers=self.headers, timeout=30)
        if response.status_code == 200:
            return response.json()['fields']['summary']
        return None

    def get_field_options(self):
        url = f'{self.url}rest/api/3/field'
        response = self._upload_session.get(url=url, headers=self.headers, timeout=30)
        return response.json() if response.status_code == 200 else None

    # ===================== TEST REPOSITORY (Xray Cloud GraphQL) =====================

    def get_cases_from_section(self, section_id=None, project_key=None, limit=100, all_descendants=True):
        """Get tests from a folder via Xray Cloud GraphQL."""
        project_key = self.project_key if project_key is None else project_key
        if not self._xray_graphql_available:
            return []
        folder_path = section_id if isinstance(section_id, str) else f"/{section_id}" if section_id else "/"
        results = []
        cursor = None
        while True:
            after_clause = f', after: "{cursor}"' if cursor else ''
            data = self._graphql(f"""
                query GetTests($projectId: String!, $folderPath: String!) {{
                    getTests(projectId: $projectId, folderPath: $folderPath, limit: {limit}{after_clause}) {{
                        total
                        results {{
                            issueId
                            jira(fields: ["key", "summary"])
                        }}
                    }}
                }}
            """, {"projectId": project_key, "folderPath": folder_path})
            if not data or 'getTests' not in data:
                break
            batch = data['getTests'].get('results', [])
            results.extend(batch)
            if len(batch) < limit:
                break
            # Xray Cloud GraphQL doesn't use cursor pagination for getTests in the same way
            break
        return results

    def get_all_sections(self, method='GET', section=None):
        """Get subfolders via Xray Cloud GraphQL."""
        if not self._xray_graphql_available:
            return []
        folder_path = section if isinstance(section, str) else f"/{section}" if section else "/"
        data = self._graphql("""
            query GetFolder($projectId: String!, $path: String!) {
                getFolder(projectId: $projectId, path: $path) {
                    name
                    folders { name }
                }
            }
        """, {"projectId": self.project_key, "path": folder_path})
        if data and 'getFolder' in data:
            return data['getFolder'].get('folders', [])
        return []

    # ===================== TEST EXECUTION (Xray Cloud GraphQL) =====================

    def get_tests_in_execution(self, test_exec_key, limit=200):
        """Get tests in a test execution via Xray Cloud GraphQL."""
        if not self._xray_graphql_available:
            return []
        resp = self._upload_session.get(
            f'{self.url}rest/api/3/issue/{test_exec_key}?fields=summary',
            headers=self.headers, timeout=30)
        if resp.status_code != 200:
            return []
        issue_id = resp.json()['id']
        results = []
        cursor = None
        while True:
            after_clause = f', after: "{cursor}"' if cursor else ''
            data = self._graphql(f"""
                query GetTestExecution($issueId: String!) {{
                    getTestExecution(issueId: $issueId) {{
                        tests(limit: {limit}{after_clause}) {{
                            total
                            results {{
                                issueId
                                status {{ name }}
                                jira(fields: ["key", "summary"])
                            }}
                        }}
                    }}
                }}
            """, {"issueId": issue_id})
            if not data or 'getTestExecution' not in data:
                break
            batch = data['getTestExecution'].get('tests', {}).get('results', [])
            results.extend(batch)
            if len(batch) < limit:
                break
            break
        return results

    def add_tests_to_test_run(self, key, issues_list):
        """Add tests to a test execution via Xray Cloud GraphQL."""
        if not self._xray_graphql_available:
            return None
        resp = self._upload_session.get(
            f'{self.url}rest/api/3/issue/{key}?fields=summary',
            headers=self.headers, timeout=30)
        if resp.status_code != 200:
            return None
        exec_id = resp.json()['id']
        # Resolve test issue keys to IDs
        test_ids = []
        for issue_key in issues_list:
            r = self._upload_session.get(
                f'{self.url}rest/api/3/issue/{issue_key}?fields=summary',
                headers=self.headers, timeout=30)
            if r.status_code == 200:
                test_ids.append(r.json()['id'])
        if not test_ids:
            return None
        data = self._graphql("""
            mutation AddTestsToExec($issueId: String!, $testIssueIds: [String!]!) {
                addTestsToTestExecution(issueId: $issueId, testIssueIds: $testIssueIds) {
                    addedTests
                    warning
                }
            }
        """, {"issueId": exec_id, "testIssueIds": test_ids})
        return data

    def _get_test_run_id(self, exec_key, test_key):
        """Get the test run ID for a test within a test execution."""
        if not self._xray_graphql_available:
            return None
        exec_resp = self._upload_session.get(
            f'{self.url}rest/api/3/issue/{exec_key}?fields=summary',
            headers=self.headers, timeout=30)
        if exec_resp.status_code != 200:
            self._logger.error(f"Could not resolve exec key: {exec_key}")
            return None
        exec_id = exec_resp.json()['id']
        # Get test runs from the execution to find the run ID for this test
        data = self._graphql("""
            query GetTestExecution($issueId: String!) {
                getTestExecution(issueId: $issueId) {
                    testRuns(limit: 100) {
                        results {
                            id
                            status { name }
                            test {
                                issueId
                                jira(fields: ["key"])
                            }
                        }
                    }
                }
            }
        """, {"issueId": exec_id})
        if not data or 'getTestExecution' not in data:
            self._logger.error(f"Failed to get test runs for {exec_key}")
            return None
        runs = data['getTestExecution'].get('testRuns', {}).get('results', [])
        for run in runs:
            test_jira = run.get('test', {}).get('jira', {})
            run_key = test_jira.get('key', '') if isinstance(test_jira, dict) else ''
            if run_key == test_key:
                return run['id']
        self._logger.error(f"Test run not found for {test_key} in {exec_key}")
        return None

    def update_test_status(self, exec_key, test_key, status):
        """Update test run status via Xray Cloud GraphQL."""
        if not self._xray_graphql_available:
            return None
        run_id = self._get_test_run_id(exec_key, test_key)
        if not run_id:
            return None
        data = self._graphql("""
            mutation UpdateTestRunStatus($id: String!, $status: String!) {
                updateTestRunStatus(id: $id, status: $status)
            }
        """, {"id": run_id, "status": status})
        return data

    def get_test_run_steps(self, exec_key, test_key):
        """Retrieve test run steps via Xray Cloud GraphQL."""
        if not self._xray_graphql_available:
            self._logger.error("Xray Cloud GraphQL not available")
            return None
        # Resolve both keys to issue IDs
        exec_resp = self._upload_session.get(
            f'{self.url}rest/api/3/issue/{exec_key}?fields=summary',
            headers=self.headers, timeout=30)
        test_resp = self._upload_session.get(
            f'{self.url}rest/api/3/issue/{test_key}?fields=summary',
            headers=self.headers, timeout=30)
        if exec_resp.status_code != 200 or test_resp.status_code != 200:
            self._logger.error(f"Could not resolve keys: {exec_key}, {test_key}")
            return None
        exec_id = exec_resp.json()['id']
        test_id = test_resp.json()['id']
        data = self._graphql("""
            query GetTestRun($testExecIssueId: String!, $testIssueId: String!) {
                getTestRun(testExecIssueId: $testExecIssueId, testIssueId: $testIssueId) {
                    id
                    status { name }
                    steps {
                        id
                        action
                        data
                        result
                        status { name }
                    }
                }
            }
        """, {"testExecIssueId": exec_id, "testIssueId": test_id})
        if data and 'getTestRun' in data:
            steps = data['getTestRun'].get('steps', [])
            self._logger.info(f"Retrieved {len(steps)} steps for {test_key} in {exec_key}")
            return steps
        self._logger.error(f"Failed to get test run steps for {test_key} in {exec_key}")
        return None

    def update_test_run_step_status(self, exec_key, test_key, step_index, status):
        """Update a single step's status within a test run."""
        steps = self.get_test_run_steps(exec_key, test_key)
        if steps is None:
            return None
        if step_index < 0 or step_index >= len(steps):
            self._logger.error(f"Step index {step_index} out of range (0-{len(steps)-1}) for {test_key}")
            return None
        step_id = steps[step_index]['id']
        data = self._graphql("""
            mutation UpdateTestRunStep($testRunStepId: String!, $status: String!) {
                updateTestRunStep(id: $testRunStepId, status: $status)
            }
        """, {"testRunStepId": step_id, "status": status})
        if data is not None:
            self._logger.debug(f"Step {step_index} of {test_key} updated to {status}")
        else:
            self._logger.error(f"Failed to update step {step_index} of {test_key}")
        return data

    def update_all_step_statuses(self, exec_key, test_key, statuses):
        """Bulk-update all step statuses for a test run."""
        steps = self.get_test_run_steps(exec_key, test_key)
        if steps is None:
            self._logger.error(f"Cannot update step statuses for {test_key}")
            return {"updated": 0, "failed": 0}
        count = min(len(statuses), len(steps))
        if len(statuses) != len(steps):
            self._logger.warning(
                f"Status count mismatch for {test_key}: {len(statuses)} statuses vs {len(steps)} steps. "
                f"Updating first {count} steps.")
        updated = 0
        failed = 0
        for i in range(count):
            step_id = steps[i]['id']
            result = self._graphql("""
                mutation UpdateTestRunStep($testRunStepId: String!, $status: String!) {
                    updateTestRunStep(id: $testRunStepId, status: $status)
                }
            """, {"testRunStepId": step_id, "status": statuses[i]})
            if result is not None:
                updated += 1
                self._logger.debug(f"Step {i} of {test_key} -> {statuses[i]}")
            else:
                failed += 1
                self._logger.error(f"Failed to update step {i} of {test_key}")
        self._logger.info(f"Step status update for {test_key}: {updated} updated, {failed} failed")
        return {"updated": updated, "failed": failed}
