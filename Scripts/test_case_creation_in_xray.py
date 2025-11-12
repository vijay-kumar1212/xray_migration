from testrail.testrail_client import TestRailClient
from xray.xray_client import XrayClient


class TestCaseCreation(TestRailClient):

    def test_create_case_in_xray(self):
        tr_case_data = self.get_case(case_id=17723913).json()
        xray = XrayClient()
        case = xray.create_issue(data=tr_case_data,issue_type='Test',test_repo='/LCG Digital Master Suite/Vanilla')
        add_steps = xray.add_steps_to_the_test_case(key=case['key'], steps=tr_case_data['custom_steps_separated'])

"""

response = session.put(url=url, json=step_payload)
            j = response.json()
            id = j['id']
            a_url = f"{xray_base_url}rest/raven/1.0/api/test/{'DFE-5614'}/step/{id}/attachment"
            r = requests.post(url=a_url, headers=headers, files=attachments)"""

obj = TestCaseCreation()
obj.test_create_case_in_xray()
