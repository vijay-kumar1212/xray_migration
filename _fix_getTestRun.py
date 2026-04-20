"""Fix getTestRun query to use correct parameters."""
import os

file_path = os.path.join(os.path.dirname(__file__), 'xray', 'xray_client.py')

with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix get_test_run_steps: getTestRun uses testExecIssueId + testIssueId, not id
old = '''    def get_test_run_steps(self, exec_key, test_key):
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

new = '''    def get_test_run_steps(self, exec_key, test_key):
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
        return None'''

if old in content:
    content = content.replace(old, new)
    print("Fixed get_test_run_steps to use testExecIssueId + testIssueId")
else:
    print("WARNING: Could not find old get_test_run_steps")

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

import ast
ast.parse(content)
print("Syntax OK")
