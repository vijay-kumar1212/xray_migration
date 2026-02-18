import re
from testrail.testrail_client import TestRailClient
from xray.xray_client import XrayClient
import pandas as pd

class TestCaseCreation(TestRailClient):

    def test_create_case_in_xray(self, case_ids): #66331235, 60092721 OMNIA, envision C65763904,RGE 66386708 dbt 62171047, df C869515
        xray = XrayClient()
        for case_id in case_ids:
            tr_case_data = self.get_case(case_id).json()

            # case = xray.get_test_case(key='DF-2292')
            case = xray.create_issue(data=tr_case_data, issue_type='Test', test_repo='LCG Digital Master Suite/Vanilla') #test_repo='/LCG Digital Master Suite/Vanilla'

            if not case or 'key' not in case:
                return None
            preconditions = tr_case_data.get('custom_preconds')
            if preconditions and "index.php?/attachments/get/" in preconditions:
                attachment_ids = list(set(re.findall(r'index\.php\?/attachments/get/([\w-]+)', preconditions)))
                for attachment_id in attachment_ids:
                    attachment_data, file_name = self.get_attachment(attachment_id)
                    xray.upload_jira_attachment(issue_key=case['key'],file_name=f'prerequisite_{file_name}.png',file_bytes=attachment_data)
            steps = tr_case_data.get('custom_steps_separated', [])
            if not steps:
                continue
            xray.add_steps_to_the_test_case(key=case['key'], steps=steps, testrail_client=self)
        return None


obj = TestCaseCreation()
# file_1 = pd.read_excel(r"C:\Users\VijayKumar.Panga\Downloads\retail___omnia_v2 (1).xlsx")
# col1 = file_1.columns[0]
# file_1[col1] = file_1[col1].astype(str)
# file_1[col1] = file_1[col1].str.replace(r'^C', '', regex=True)
# case_ids = file_1[col1].tolist()
obj.test_create_case_in_xray(case_ids=[66331235])
