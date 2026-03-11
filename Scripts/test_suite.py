import re
import sys
import os
import pandas as pd
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from io import BytesIO
from PIL import Image

from utilities.log_mngr import setup_custom_logger

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from testrail.testrail_client import TestRailClient
from xray.xray_client import XrayClient


class TestSuiteExport(TestRailClient):
    _logger = setup_custom_logger()

    def __init__(self):
        super().__init__()
        self.excel_lock = Lock()
        self.counter_lock = Lock()

    @staticmethod
    def compress_image(image_bytes, max_size_kb=500, quality=85):
        """
        Compress image to reduce file size
        
        Args:
            image_bytes: Original image bytes
            max_size_kb: Maximum target size in KB (default 500KB)
            quality: JPEG quality 1-100 (default 85)
        
        Returns:
            Compressed image bytes
        """
        try:
            # Open image from bytes
            img = Image.open(BytesIO(image_bytes))
            
            # Convert RGBA to RGB if necessary (for JPEG compatibility)
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
                img = background
            
            # Get original size
            original_size = len(image_bytes) / 1024  # KB
            
            # If already small enough, return original
            if original_size <= max_size_kb:
                return image_bytes
            
            # Compress with quality adjustment
            output = BytesIO()
            current_quality = quality
            
            # Try compressing with decreasing quality until size is acceptable
            while current_quality > 20:
                output.seek(0)
                output.truncate()
                img.save(output, format='JPEG', quality=current_quality, optimize=True)
                compressed_size = output.tell() / 1024  # KB
                
                if compressed_size <= max_size_kb:
                    break
                    
                current_quality -= 10
            
            compressed_bytes = output.getvalue()
            compressed_size = len(compressed_bytes) / 1024
            
            TestSuiteExport._logger.debug(
                f"Image compressed: {original_size:.1f}KB -> {compressed_size:.1f}KB "
                f"(quality={current_quality}, reduction={((original_size-compressed_size)/original_size*100):.1f}%)"
            )
            
            return compressed_bytes
            
        except Exception as e:
            TestSuiteExport._logger.warning(f"Image compression failed: {str(e)}, using original")
            return image_bytes

    def process_single_case(self, case, test_repository, xray):
        """Process a single test case - designed for multithreading"""
        x_case = None
        export_status = "Failed"
        steps_status = "Not Attempted"
        
        try:
            x_case = xray.create_issue(data=case, issue_type='Test', test_repo=test_repository)
            tr_case_data = self.get_case(case_id=case['id']).json()
            
            export_status = "Success" if x_case and 'key' in x_case else "Failed"
            
            if export_status == "Success":
                self._logger.info(f"Created Xray test case {x_case['key']} for TestRail case {case['id']}")
                
                # Handle preconditions attachments
                preconditions = tr_case_data.get('custom_preconds')
                if preconditions and "index.php?/attachments/get/" in preconditions:
                    attachment_ids = list(set(re.findall(r'index\.php\?/attachments/get/([\w-]+)', preconditions)))
                    self._logger.debug(f"Found {len(attachment_ids)} attachments for case {case['id']}")
                    for attachment_id in attachment_ids:
                        try:
                            attachment_data, file_name = self.get_attachment(attachment_id)
                            if attachment_data:
                                # Compress image before uploading
                                compressed_data = self.compress_image(attachment_data)
                                xray.upload_jira_attachment(
                                    issue_key=x_case['key'],
                                    file_name=f'prerequisite_{file_name}.png',
                                    file_bytes=compressed_data
                                )
                        except Exception as e:
                            self._logger.warning(f"Skipping attachment {attachment_id} for case {case['id']}: {str(e)}")
                
                # Add steps
                try:
                    steps = tr_case_data['custom_steps_separated']
                    if steps:
                        add_steps = xray.add_steps_to_the_test_case(x_case['key'], steps=steps, testrail_client=self)
                        steps_status = "Success" if add_steps else "Failed"
                        if steps_status == "Failed":
                            self._logger.warning(f"Failed to add steps to {x_case['key']}")
                except Exception as e:
                    self._logger.error(f"Error adding steps to {x_case['key']}: {str(e)}")
                    steps_status = f"Failed: {str(e)}"
            else:
                self._logger.warning(f"Failed to create Xray test case for TestRail case {case['id']}")
                return {
                    'success': False,
                    'test_rail_id': case['id'],
                    'Test Repository': test_repository,
                    'error': x_case
                }
            
            return {
                'success': True,
                'Test Rail Id': case['id'],
                'Xray Key': x_case['key'],
                'Test Repository': test_repository,
                'Test Case Title': case.get('title', 'N/A'),
                'Export to Xray Status': export_status,
                'Status of Adding Steps to Xray': steps_status
            }
            
        except Exception as e:
            self._logger.error(f"Error processing TestRail case {case['id']}: {str(e)}")
            return {
                'success': False,
                'Test Rail Id': case['id'],
                'Test Repository': test_repository,
                'Test Case Title': case.get('title', 'N/A'),
                'Export to Xray Status': f"Failed: {str(e)}",
                'Status of Adding Steps to Xray': "Not Attempted"
            }

    def export_test_suite_to_xray(self, project_id=50, suite_id=2753, max_workers=10):
        self._logger.info(f"Starting test suite export - Project ID: {project_id}, Suite ID: {suite_id}, Max Workers: {max_workers}")
        sections = self.get_all_sections_data(project_id, suite_id)
        self._logger.info(f"Retrieved {len(sections)} sections")
        xray = XrayClient()
        folder_paths = self.build_folder_paths(sections)
        
        # Create Excel file before loop
        successful_cases_file = f"{xray.test_repository.replace('/', '_')}_testrail_to_xray_migration_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        failed_cases_file = f"failed_cases_{xray.test_repository.replace('/', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        
        excel_data = []
        failed_cases = []
        processed_count = 0
        total_suite_cases = 0
        imported_cases_to_xray = 0
        
        # Collect all test cases with their repository paths
        all_tasks = []
        for section in sections:
            test_repository = f"/{xray.test_repository}/{folder_paths[section['id']]}"
            test_cases = self.get_section_cases(suite_id=suite_id, section_id=section['id']).get('cases')
            section_cases = len(test_cases)
            total_suite_cases += section_cases
            self._logger.debug(f"Processing section '{section['name']}' with {len(test_cases)} test cases")
            
            for case in test_cases:
                all_tasks.append((case, test_repository))
        
        self._logger.info(f"Total test cases to process: {total_suite_cases}")
        print(f"Starting multithreaded import of {total_suite_cases} test cases with {max_workers} workers...")
        
        # Process test cases using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_case = {
                executor.submit(self.process_single_case, case, test_repo, xray): (case['id'], test_repo)
                for case, test_repo in all_tasks
            }
            
            # Process completed tasks
            for future in as_completed(future_to_case):
                case_id, test_repo = future_to_case[future]
                try:
                    result = future.result()
                    
                    with self.counter_lock:
                        processed_count += 1
                        
                        if result['success']:
                            imported_cases_to_xray += 1
                            excel_data.append({
                                'Test Rail Id': result['Test Rail Id'],
                                'Xray Key': result['Xray Key'],
                                'Test Repository': result['Test Repository'],
                                'Test Case Title': result['Test Case Title'],
                                'Export to Xray Status': result['Export to Xray Status'],
                                'Status of Adding Steps to Xray': result['Status of Adding Steps to Xray']
                            })
                        else:
                            if 'error' in result:
                                failed_cases.append({
                                    'test_rail_id': result['test_rail_id'],
                                    'Test Repository': result['Test Repository'],
                                    'error': result['error']
                                })
                            else:
                                excel_data.append({
                                    'Test Rail Id': result['Test Rail Id'],
                                    'Test Repository': result['Test Repository'],
                                    'Test Case Title': result['Test Case Title'],
                                    'Export to Xray Status': result['Export to Xray Status'],
                                    'Status of Adding Steps to Xray': result['Status of Adding Steps to Xray']
                                })
                        
                        # Update Excel every 100 cases
                        if processed_count % 100 == 0:
                            with self.excel_lock:
                                pd.DataFrame(excel_data).to_excel(successful_cases_file, index=False)
                                if failed_cases:
                                    pd.DataFrame(failed_cases).to_excel(failed_cases_file, index=False)
                            self._logger.info(f"Progress: Processed {processed_count}/{total_suite_cases} test cases")
                            print(f"Progress: {processed_count}/{total_suite_cases} test cases ({(processed_count/total_suite_cases)*100:.1f}%)")
                
                except Exception as e:
                    self._logger.error(f"Error processing future for case {case_id}: {str(e)}")
                    with self.counter_lock:
                        processed_count += 1
                        excel_data.append({
                            'Test Rail Id': case_id,
                            'Test Repository': test_repo,
                            'Test Case Title': 'N/A',
                            'Export to Xray Status': f"Failed: {str(e)}",
                            'Status of Adding Steps to Xray': "Not Attempted"
                        })
        
        # Final Excel update
        pd.DataFrame(excel_data).to_excel(successful_cases_file, index=False)
        self._logger.info(f"Excel report saved as: {successful_cases_file} with {len(excel_data)} test cases")
        print(f"Excel report saved as: {successful_cases_file} with {len(excel_data)} test cases")

        if failed_cases:
            pd.DataFrame(failed_cases).to_excel(failed_cases_file, index=False)
            self._logger.info(f"Failed cases report saved as: {failed_cases_file}")
            print(f"Failed cases report saved as: {failed_cases_file} with {len(failed_cases)} test cases")

        self._logger.info(f"Migration Summary: {imported_cases_to_xray}/{total_suite_cases} cases successfully imported")
        print(f"\nMigration Summary: {imported_cases_to_xray}/{total_suite_cases} cases successfully imported")

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

        def clean_name(value):
            if not isinstance(value, str):
                return ""
            value = re.sub(r'[\"\']', '', value)
            value = re.sub(r'[\\/]', ' or ', value)
            value = re.sub(r'\s*>\s*', '/', value)
            value = re.sub(r'\s+', ' ', value)
            return value.strip()

        def _build_path(sec_id):
            if sec_id in path_cache:
                return path_cache[sec_id]

            sec = section_map.get(sec_id)
            if not sec:
                return ""

            cleaned_name = clean_name(sec.get('name'))

            if sec.get('parent_id') is None:
                full_path = cleaned_name
            else:
                parent_path = _build_path(sec.get('parent_id'))
                full_path = f"{parent_path}/{cleaned_name}" if parent_path else cleaned_name

            path_cache[sec_id] = full_path
            return full_path

        # Build paths for all sections
        for s in sections:
            _build_path(s['id'])

        return path_cache
obj = TestSuiteExport()
obj._logger.info("=== Starting TestRail to Xray migration ===")
all_cases = obj.export_test_suite_to_xray()
obj._logger.info("=== Migration completed ===")