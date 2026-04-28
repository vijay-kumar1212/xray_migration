import re
from testrail.testrail_client import TestRailClient
from xray.xray_client import XrayClient
import pandas as pd

class TestCaseCreation(TestRailClient):

    def test_create_case_in_xray(self, case_data): #66331235, 60092721 OMNIA, envision C65763904,RGE 66386708 dbt 62171047, df C869515
        xray = XrayClient()
        for case_id, test_repo in case_data:
            tr_case_data = self.get_case(case_id).json()
            # `test_repo` from the migration report already contains the full repository path
            # (e.g. "/Omnia Acceptance test Pack/.../Folder"), so use it as-is.
            test_repo_ = test_repo if str(test_repo).startswith('/') else f'/{xray.test_repository}/{test_repo}'

            # case = xray.get_test_case(key='DF-2292')
            case = xray.create_issue(data=tr_case_data, issue_type='Test',test_repo=test_repo_) # TODO

            if not case or 'key' not in case:
                self._logger.warning(f'Failed to import Test case: {case_id} from section {test_repo_}')
                print(case)
                continue
            else:
                self._logger.info(f"Test case {case_id}imported successfully: {case['key']}")
            preconditions = tr_case_data.get('custom_preconds')
            if preconditions and "index.php?/attachments/get/" in preconditions:
                attachment_ids = list(set(re.findall(r'index\.php\?/attachments/get/([\w-]+)', preconditions)))
                for attachment_id in attachment_ids:
                    attachment_data, file_name = self.get_attachment(attachment_id)
                    xray.upload_jira_attachment(issue_key=case['key'],file_name=f'prerequisite_{file_name}.png',file_bytes=attachment_data)
            steps = tr_case_data.get('custom_steps_separated')
            if steps:
                add_steps = xray.add_steps_to_the_test_case(case['key'], steps=steps, testrail_client=self)
                steps_status = "Success" if add_steps else "Failed"
                if steps_status == "Failed":
                    self._logger.warning(f"Failed to add steps to {case['key']} from Testrail case id: {case_id}")
            else:
                continue
        return None


obj = TestCaseCreation()

# Load failed rows from the migration report and re-import them.
MIGRATION_REPORT = r"C:\Users\VijayKumar.Panga\Downloads\migration_report_20260424_184005.xlsx"
file_1 = pd.read_excel(MIGRATION_REPORT)

# Keep only rows where the previous export to Xray failed.
file_1 = file_1[file_1['Export to Xray Status'].astype(str).str.strip().str.lower() == 'failed'].copy()

# Strip leading "C" from TestRail IDs (e.g. "C1468070" -> "1468070").
file_1['Test Rail Id'] = file_1['Test Rail Id'].astype(str).str.strip().str.replace(r'^C', '', regex=True)

# Normalise the Test Repository path (trim, collapse whitespace, drop stray quotes).
file_1['Test Repository'] = (
    file_1['Test Repository'].astype(str).str.strip()
        +
        .str.replace(r"\s+", " ", regex=True)
        .str.strip()
)

case_data = list(zip(file_1['Test Rail Id'], file_1['Test Repository']))

# Skip the first N rows that were already imported in a previous run.
# Set to 0 (or None) to import all failed rows.
ALREADY_IMPORTED = 2
if ALREADY_IMPORTED:
    case_data = case_data[ALREADY_IMPORTED:]
    print(f"Skipping first {ALREADY_IMPORTED} already-imported case(s).")

print(f"Retrying {len(case_data)} failed test case(s) from {MIGRATION_REPORT}")
obj.test_create_case_in_xray(case_data)