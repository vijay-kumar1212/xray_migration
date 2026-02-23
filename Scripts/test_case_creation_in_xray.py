import re
from testrail.testrail_client import TestRailClient
from xray.xray_client import XrayClient
import pandas as pd

class TestCaseCreation(TestRailClient):

    def test_create_case_in_xray(self, case_data): #66331235, 60092721 OMNIA, envision C65763904,RGE 66386708 dbt 62171047, df C869515
        xray = XrayClient()
        for case_id, test_repo in case_data:
            tr_case_data = self.get_case(case_id).json()
            test_repo_ = f'/{xray.test_repository}/{test_repo}'  #TODO

            # case = xray.get_test_case(key='DF-2292')
            case = xray.create_issue(data=tr_case_data, issue_type='Test', test_repo=test_repo_) # TODO

            if not case or 'key' not in case:
                self._logger.warning(f'Failed to import Test case: {case_id} from section {test_repo_}') # TODO
                print(case)
            else:
                self._logger.info(f"Test case imported successfully: {case['key']}")
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
file_1 = pd.read_excel(r"C:\xray_migration\xray_migration\Scripts\symphony___oxygen_qa (3).xlsx") #TODO
file_1['ID'] = file_1['ID'].astype(str).str.replace(r'^C', '', regex=True)
file_1['Section Hierarchy'] = (
    file_1['Section Hierarchy']
        .str.replace("'", "", regex=False)                # remove single quotes  (.str.replace(r"[\\/]", " or ", regex=True)   # replace / or \ with ' or '    *** .str.replace(r"\s*>\s*", "/", regex=True)        # replace > with /)
        .str.replace(r"\s+", " ", regex=True)            # clean extra spaces
        .str.strip()
)
case_data = list(zip(file_1['ID'], file_1['Section Hierarchy']))
# case_ids = [65949626]
obj.test_create_case_in_xray(case_data)
