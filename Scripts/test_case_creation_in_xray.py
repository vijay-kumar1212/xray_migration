import base64
import re

import requests

from testrail.testrail_client import TestRailClient
from xray.xray_client import XrayClient


class TestCaseCreation(TestRailClient):

    def test_create_case_in_xray(self, case_id=66331235):
        tr_case_data = self.get_case(case_id=case_id).json()
        xray = XrayClient()
        case = xray.create_issue(data=tr_case_data, issue_type='Test', test_repo='/LCG Digital Master Suite/Vanilla')
        
        if not case or 'key' not in case:
            return None
            
        steps = tr_case_data.get('custom_steps_separated', [])
        if not steps:
            return case
            
        session = requests.Session()
        session.headers.update(xray.headers)
        session.verify = False
        url = f"{xray.url}rest/raven/1.0/api/test/{case['key']}/step/"
        
        for step in steps:
            step_payload = {
                'step': step.get('content', ''),
                'data': "None",
                'result': step.get('expected', ''),
                'attachments': []  # Keep for tracking
            }
            
            # Process attachments if present in content or expected
            content = step.get('content', '')
            expected = step.get('expected', '')
            if "![](index.php?/attachments/get/" in content or "![](index.php?/attachments/get/" in expected:
                attachment_ids = re.findall(r'index\.php\?/attachments/get/(\d+)', content + expected)
                for attachment_id in attachment_ids:
                    try:
                        attachment_data = self.get_attachment(attachment_id=attachment_id)
                        encoded_data = base64.b64encode(attachment_data).decode("utf-8")
                        file_name = f'{attachment_id}.png'
                        
                        # Keep attachment payload for tracking
                        attachment_payload = {'attachments': [{
                            'data': encoded_data,
                            'filename': file_name,
                            "contentType": "plain/text"
                        }]}
                        
                        # Create step first
                        xray_step = session.put(url=url, json=step_payload)
                        if xray_step.status_code == 200:
                            step_id = xray_step.json()['id']
                            # Upload attachment
                            attachment_url = f"{xray.url}rest/raven/1.0/api/test/{case['key']}/step/{step_id}/attachment"
                            files = {'file': (file_name, attachment_data, 'application/octet-stream')}
                            session.put(url=attachment_url, headers=xray.headers, files=files)
                            # session.put(url=attachment_url, headers=xray.headers, json=attachment_payload)
                    except Exception as e:
                        print(f"Attachment processing failed for ID {attachment_id}: {e}")
            else:
                session.put(url=url, json=step_payload)
                
        return case

    # Legacy payload structure - kept for tracking
    # {
    #     'step': step_content,
    #     'data': "None", 
    #     'result': expected_result,
    #     'attachments': [{
    #         'data': base64_encoded_data,
    #         'filename': file_name,
    #         'contentType': content_type
    #     }]
    # }

obj = TestCaseCreation()
obj.test_create_case_in_xray()
