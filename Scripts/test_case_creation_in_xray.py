import base64
import mimetypes
import re
import requests
from testrail.testrail_client import TestRailClient
from xray.xray_client import XrayClient


class TestCaseCreation(TestRailClient):

    def test_create_case_in_xray(self, case_id= 17723927): #66331235, 60092721 OMNIA, envision C65763904,RGE 66386708 dbt 62171047, df C869515
        tr_case_data = self.get_case(case_id=case_id).json()
        xray = XrayClient()
        # case = xray.get_test_case(key='DF-2292')
        case = xray.create_issue(data=tr_case_data, issue_type='Test',test_repo='') #test_repo='/LCG Digital Master Suite/Vanilla'

        if not case or 'key' not in case:
            return None
        preconditions = tr_case_data['custom_preconds']
        if "index.php?/attachments/get/" in preconditions:
            attachment_id = list(set(re.findall(r'index\.php\?/attachments/get/([\w-]+)', preconditions)))
            attachment_data, file_name = self.get_attachment(attachment_id[0])
            xray.upload_jira_attachment(issue_key=case['key'],file_name=f'{file_name}.png',file_bytes=attachment_data)
        steps = tr_case_data.get('custom_steps_separated', [])
        if not steps:
            return case
            
        session = requests.Session()
        session.headers.update(xray.headers)
        session.verify = False
        url = f"{xray.url}rest/raven/1.0/api/test/{case['key']}/step/"
        
        for step in steps:
            step_payload = {
                'step': xray.strip_html(step.get('content', '')),
                'data': "None",
                'result': xray.strip_html(step.get('expected', '')),
                'attachments': []  # Keep for tracking
            }
            xray_step = session.put(url=url, json=step_payload)
            if xray_step.status_code == 200:
                self.__class__.step_id = xray_step.json()['id']
            else:
                raise requests.HTTPError(f"step creation is failed for {case['key']}: {xray_step.text}")
            # Process attachments if present in content or expected
            content = step.get('content', '')
            expected = step.get('expected', '')
            if "index.php?/attachments/get/" in content or "index.php?/attachments/get/" in expected:
                attachment_ids = re.findall(r'index\.php\?/attachments/get/([\w-]+)', content + expected)
                for attachment_id in attachment_ids:
                    try:
                        attachment_data,file_name = self.get_attachment(attachment_id=attachment_id)
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

                        # Upload attachment
                        attachment_url = f"{xray.url}rest/raven/1.0/api/test/{case['key']}/step/{self.__class__.step_id}"
                        session.post(url=attachment_url,  json=payload)
                    except Exception as e:
                        print(f"Attachment processing failed for ID {attachment_id}: {e}")
                
        return case



obj = TestCaseCreation()
obj.test_create_case_in_xray()
