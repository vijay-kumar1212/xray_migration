"""Patch xray_client.py to add new methods on disk."""
import os

file_path = os.path.join(os.path.dirname(__file__), 'xray', 'xray_client.py')

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

old_stub = """    def create_test_plan_or_execution(self, test_plan_name, data):
        return True"""

new_methods = '''    def create_test_plan(self, name, project_key=None):
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
        return response'''

# Also add the step-level methods before the final closing of the file
step_methods = """
    def get_test_run_steps(self, exec_key, test_key):
        \\"\\"\\"Retrieve test run steps via Xray Cloud GraphQL.\\"\\"\\"
        if not self._xray_graphql_available:
            self._logger.error("Xray Cloud GraphQL not available")
            return None
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
        data = self._graphql(\\"\\"\\"
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
        \\"\\"\\", {"testExecIssueId": exec_id, "testIssueId": test_id})
        if data and 'getTestRun' in data:
            steps = data['getTestRun'].get('steps', [])
            self._logger.info(f"Retrieved {len(steps)} steps for {test_key} in {exec_key}")
            return steps
        self._logger.error(f"Failed to get test run steps for {test_key} in {exec_key}")
        return None
"""

if old_stub in content:
    content = content.replace(old_stub, new_methods)
    print("Replaced old stub with create_test_plan + create_test_execution")
else:
    print("Old stub not found - may already be replaced")

# Add step methods and update methods after update_test_status if not already present
if 'def get_test_run_steps' not in content:
    # Find the end of update_test_status method
    marker = '        return data\n'
    # Find the last occurrence (which should be update_test_status)
    idx = content.rfind('updateTestRunStatus')
    if idx > 0:
        # Find the next 'return data' after that
        ret_idx = content.find('        return data\n', idx)
        if ret_idx > 0:
            insert_point = ret_idx + len('        return data\n')
            step_code = '''
    def get_test_run_steps(self, exec_key, test_key):
        """Retrieve test run steps via Xray Cloud GraphQL."""
        if not self._xray_graphql_available:
            self._logger.error("Xray Cloud GraphQL not available")
            return None
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
'''
            content = content[:insert_point] + step_code + content[insert_point:]
            print("Added step-level methods")

# Also fix the missing comma bug if present
content = content.replace(
    '"description": adf_desc\n            "priority"',
    '"description": adf_desc,\n            "priority"'
)

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

# Verify
with open(file_path, 'r', encoding='utf-8') as f:
    final = f.read()
print(f"create_test_plan: {'def create_test_plan(' in final}")
print(f"create_test_execution: {'def create_test_execution(' in final}")
print(f"get_test_run_steps: {'def get_test_run_steps(' in final}")
print(f"update_test_run_step_status: {'def update_test_run_step_status(' in final}")
print(f"update_all_step_statuses: {'def update_all_step_statuses(' in final}")
print(f"old stub gone: {'create_test_plan_or_execution' not in final}")
