"""Fix GraphQL mutations to use correct Xray Cloud API schema."""
import os

file_path = os.path.join(os.path.dirname(__file__), 'xray', 'xray_client.py')

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix 1: update_test_status - needs to get test run ID first, then update by ID
old_update_status = '''    def update_test_status(self, exec_key, test_key, status):
        """Update test run status via Xray Cloud GraphQL."""
        if not self._xray_graphql_available:
            return None
        # Resolve both keys to IDs
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
            mutation UpdateTestRunStatus($testExecIssueId: String!, $testIssueId: String!, $status: String!) {
                updateTestRunStatus(testExecIssueId: $testExecIssueId, testIssueId: $testIssueId, status: $status)
            }
        """, {"testExecIssueId": exec_id, "testIssueId": test_id, "status": status})
        return data'''

new_update_status = '''    def _get_test_run_id(self, exec_key, test_key):
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
        return data'''

if old_update_status in content:
    content = content.replace(old_update_status, new_update_status)
    print("Fixed update_test_status to use test run ID")
else:
    print("WARNING: Could not find old update_test_status to replace")

# Fix 2: get_test_run_steps - use test run ID approach
old_get_steps = '''    def get_test_run_steps(self, exec_key, test_key):
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
        return None'''

new_get_steps = '''    def get_test_run_steps(self, exec_key, test_key):
        """Retrieve test run steps via Xray Cloud GraphQL."""
        if not self._xray_graphql_available:
            self._logger.error("Xray Cloud GraphQL not available")
            return None
        run_id = self._get_test_run_id(exec_key, test_key)
        if not run_id:
            return None
        data = self._graphql("""
            query GetTestRun($id: String!) {
                getTestRun(id: $id) {
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
        """, {"id": run_id})
        if data and 'getTestRun' in data:
            steps = data['getTestRun'].get('steps', [])
            self._logger.info(f"Retrieved {len(steps)} steps for {test_key} in {exec_key}")
            return steps
        self._logger.error(f"Failed to get test run steps for {test_key} in {exec_key}")
        return None'''

if old_get_steps in content:
    content = content.replace(old_get_steps, new_get_steps)
    print("Fixed get_test_run_steps to use test run ID")
else:
    print("WARNING: Could not find old get_test_run_steps to replace")

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

# Verify
with open(file_path, 'r', encoding='utf-8') as f:
    final = f.read()
print(f"_get_test_run_id: {'def _get_test_run_id(' in final}")
print(f"Uses 'id: $id': {'mutation UpdateTestRunStatus($id: String!' in final}")
import ast
ast.parse(final)
print("Syntax OK")
