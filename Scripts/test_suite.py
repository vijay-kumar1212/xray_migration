import re
import sys
import os
import pandas as pd
from datetime import datetime

from utilities.log_mngr import setup_custom_logger

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from testrail.testrail_client import TestRailClient
from xray.xray_client import XrayClient


class TestSuiteExport(TestRailClient):
    _logger = setup_custom_logger()

    def export_test_suite_to_xray(self,project_id=36,suite_id=637):
        self._logger.info(f"Starting test suite export - Project ID: {project_id}, Suite ID: {suite_id}")
        sections = self.get_all_sections_data(project_id, suite_id)
        self._logger.info(f"Retrieved {len(sections)} sections")
        xray = XrayClient()
        folder_paths = self.build_folder_paths(sections)
        
        # Create Excel file before loop
        successfull_cases_file = f"{xray.test_repository}_testrail_to_xray_migration_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        failed_cases_file = f"failed_cases_{xray.test_repository}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        excel_data = []
        failed_cases = []
        processed_count = 0
        total_suite_cases = 0
        imported_cases_to_xray = 0
        
        for section in sections:
            test_repository = f"/{xray.test_repository}/{folder_paths[section['id']]}"
            test_cases = self.get_section_cases(suite_id=suite_id, section_id=section['id']).get('cases')
            section_cases = len(test_cases)
            total_suite_cases += section_cases
            self._logger.debug(f"Processing section '{section['name']}' with {len(test_cases)} test cases")
            for case in test_cases:
                try:
                    x_case = xray.create_issue(data=case, issue_type='Test',test_repo=test_repository)
                    tr_case_data = self.get_case(case_id=case['id']).json()
                    
                    export_status = "Success" if x_case and 'key' in x_case else "Failed"
                    if export_status == "Success":
                        imported_cases_to_xray += 1
                        self._logger.info(f"Created Xray test case {x_case['key']} for TestRail case {case['id']}")
                    else:
                        failed_cases.append({
                            'test_rail_id': case['id'],
                            'Test Repository': test_repository,
                            'error': x_case
                        })
                        self._logger.warning(f"Failed to create Xray test case for TestRail case {case['id']}")
                    # Preconditions attachments we can't add while creating a new issue as we are using rich edit text box, so added directly to the ticket
                    preconditions = tr_case_data.get('custom_preconds')
                    if preconditions and "index.php?/attachments/get/" in preconditions:
                        attachment_ids = list(set(re.findall(r'index\.php\?/attachments/get/([\w-]+)', preconditions)))
                        self._logger.debug(f"Found {len(attachment_ids)} attachments for case {case['id']}")
                        for attachment_id in attachment_ids:
                            try:
                                attachment_data, file_name = self.get_attachment(attachment_id)
                                if attachment_data:
                                    xray.upload_jira_attachment(issue_key=x_case['key'],
                                                                file_name=f'prerequisite_{file_name}.png',
                                                                file_bytes=attachment_data)
                            except Exception as e:
                                self._logger.warning(f"Skipping attachment {attachment_id} for case {case['id']}: {str(e)}")
                    try:
                        steps = tr_case_data['custom_steps_separated']
                        if steps:
                            add_steps = xray.add_steps_to_the_test_case(x_case['key'], steps=steps,testrail_client=self)
                            steps_status = "Success" if add_steps else "Failed"
                            if steps_status == "Failed":
                                self._logger.warning(f"Failed to add steps to {x_case['key']}")
                    except Exception as e:
                        self._logger.error(f"Error adding steps to {x_case['key']}: {str(e)}")
                        steps_status = f"Failed: {str(e)}"
                    
                    excel_data.append({
                        'Test Rail Id': case['id'],
                        'Xray Key': x_case['key'],
                        'Test Repository': test_repository,
                        'Test Case Title': case.get('title', 'N/A'),
                        'Export to Xray Status': export_status,
                        'Status of Adding Steps to Xray': steps_status
                    })
                    processed_count += 1
                    
                    # Update Excel every 100 cases
                    if processed_count % 100 == 0:
                        pd.DataFrame(excel_data).to_excel(successfull_cases_file, index=False)
                        if failed_cases:
                            pd.DataFrame(failed_cases).to_excel(failed_cases_file, index=False)
                        self._logger.info(f"Progress: Processed {processed_count} test cases")
                        print(f"Processed {processed_count} test cases...")
                except Exception as e:
                    self._logger.error(f"Error processing TestRail case {case['id']}: {str(e)}")
                    excel_data.append({
                        'Test Rail Id': case['id'],
                        'Test Repository': test_repository,
                        'Test Case Title': case.get('title', 'N/A'),
                        'Export to Xray Status': f"Failed: {str(e)}",
                        'Status of Adding Steps to Xray': "Not Attempted"
                    })
        
        # Final Excel update
        pd.DataFrame(excel_data).to_excel(successfull_cases_file, index=False)
        self._logger.info(f"Excel report saved as: {successfull_cases_file} with {len(excel_data)} test cases")
        print(f"Excel report saved as: {successfull_cases_file} with {len(excel_data)} test cases")

        if failed_cases:
            pd.DataFrame(failed_cases).to_excel(failed_cases_file, index=False)
            self._logger.info(f"Failed cases report saved as: {failed_cases_file}")
            print(f"Excel report saved as: {failed_cases_file} with {len(failed_cases)} test cases")

        return excel_data, failed_cases, total_suite_cases, imported_cases_to_xray

    def get_all_test_repo_paths(self, repo_data):
        """Extract all testRepositoryPath values from repo folders structure"""
        self._logger.debug("Extracting test repository paths")
        paths = []
        
        def extract_paths(folder):
            if folder.get('testRepositoryPath') == "":
                paths.append(f'/{folder['name']}')
            elif '/' in folder.get('testRepositoryPath') and folder['name'] not in folder.get('testRepositoryPath'):
                paths.append(f'{folder['testRepositoryPath']}/{folder["name"]}')
            for subfolder in folder.get('folders', []):
                extract_paths(subfolder)
        
        if 'error' in repo_data:
            self._logger.warning("Error in repo_data, returning empty paths")
            return paths
        for folder in repo_data.get('folders', []):
            extract_paths(folder)
        self._logger.debug(f"Extracted {len(paths)} repository paths")
        return paths

    def build_folder_paths(self, sections):
        """
        Build folder paths for all sections at once, with caching.
        Returns dict: {section_id: full_path}
        """
        self._logger.debug(f"Building folder paths for {len(sections)} sections")
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
obj._logger.info("=== Starting TestRail to Xray migration ===")
all_cases = obj.export_test_suite_to_xray()
obj._logger.info("=== Migration completed ===")