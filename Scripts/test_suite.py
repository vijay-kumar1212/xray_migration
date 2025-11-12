import sys
import os
import pandas as pd
from datetime import datetime
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from testrail.testrail_client import TestRailClient
from xray.xray_client import XrayClient


class TestSuiteExport(TestRailClient):

    def export_test_suite_to_xray(self,project_id=36,suite_id=637):
        sections = self.get_all_sections_data(project_id, suite_id)
        xray = XrayClient()
        folder_paths = self.build_folder_paths(sections)
        
        # Excel tracking data
        excel_data = []
        processed_count = 0
        
        for section in sections:
            test_repository = f"/LCG Digital Master Suite/{folder_paths[section['id']]}"
            test_cases = self.get_section_cases(suite_id=suite_id, section_id=section['id']).get('cases')
            for case in test_cases:
                try:
                    x_case = xray.create_issue(data=case, issue_type='Test',test_repo=test_repository)
                    tr_case_data = self.get_case(case_id=case['id']).json()
                    
                    export_status = "Success" if x_case and 'key' in x_case else "Failed"
                    
                    try:
                        add_steps = xray.add_steps_to_the_test_case(x_case['key'], steps=tr_case_data['custom_steps_separated'])
                        steps_status = "Success" if add_steps else "Failed"
                    except Exception as e:
                        steps_status = f"Failed: {str(e)}"
                    
                    excel_data.append({
                        'Test Rail Id': case['id'],
                        'Test Repository': test_repository,
                        'Test Case Title': case.get('title', 'N/A'),
                        'Export to Xray Status': export_status,
                        'Status of Adding Steps to Xray': steps_status
                    })
                    processed_count += 1
                    if processed_count % 100 == 0:
                        print(f"Processed {processed_count} test cases...")
                except Exception as e:
                    excel_data.append({
                        'Test Rail Id': case['id'],
                        'Test Repository': test_repository,
                        'Test Case Title': case.get('title', 'N/A'),
                        'Export to Xray Status': f"Failed: {str(e)}",
                        'Status of Adding Steps to Xray': "Not Attempted"
                    })
        
        # Create Excel file
        df = pd.DataFrame(excel_data)
        filename = f"testrail_to_xray_migration_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        df.to_excel(filename, index=False)
        print(f"Excel report saved as: {filename} with {len(excel_data)} test cases")
        return excel_data

    def get_all_test_repo_paths(self, repo_data):
        """Extract all testRepositoryPath values from repo folders structure"""
        paths = []
        
        def extract_paths(folder):
            if folder.get('testRepositoryPath') == "":
                paths.append(f'/{folder['name']}')
            elif '/' in folder.get('testRepositoryPath') and folder['name'] not in folder.get('testRepositoryPath'):
                paths.append(f'{folder['testRepositoryPath']}/{folder["name"]}')
            for subfolder in folder.get('folders', []):
                extract_paths(subfolder)
        
        if 'error' in repo_data:
            return paths
        for folder in repo_data.get('folders', []):
            extract_paths(folder)
        return paths

    def build_folder_paths(self, sections):
        """
        Build folder paths for all sections at once, with caching.
        Returns dict: {section_id: full_path}
        """
        section_map = {s['id']: s for s in sections}
        path_cache = {}

        def _build_path(sec_id):
            if sec_id in path_cache:
                return path_cache[sec_id]

            sec = section_map.get(sec_id)
            if not sec:
                return ""
            if sec['parent_id'] is None:
                path_cache[sec_id] = sec['name']
            else:
                parent_path = _build_path(sec['parent_id'])
                path_cache[sec_id] = f"{parent_path}/{sec['name']}"
            return path_cache[sec_id]

        # Build paths for all sections
        for s in sections:
            _build_path(s['id'])

        return path_cache

obj = TestSuiteExport()
all_cases = obj.export_test_suite_to_xray()