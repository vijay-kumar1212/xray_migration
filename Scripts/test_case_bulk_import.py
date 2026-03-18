import re
import sys
import os
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

from utilities.log_mngr import setup_custom_logger

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from testrail.testrail_client import TestRailClient
from xray.xray_client import XrayClient
import pandas as pd


class TestCaseCreation(TestRailClient):
    _logger = setup_custom_logger()

    def test_create_case_in_xray(self, case_data):
        xray = XrayClient()

        # Excel output files for tracking results
        successful_cases_file = f"reimport_{xray.test_repository.replace('/', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        failed_cases_file = f"reimport_failed_{xray.test_repository.replace('/', '_')}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"

        excel_data = []
        failed_cases = []
        processed_count = 0
        imported_count = 0

        # === PERFORMANCE IMPROVEMENT: Pre-fetch all TestRail case data in parallel ===
        # Instead of calling get_case() one-by-one inside the loop, fetch all upfront.
        self._logger.info(f"Pre-fetching {len(case_data)} TestRail case details in parallel...")
        tr_case_cache = {}
        unique_case_ids = list(set(cid for cid, _ in case_data))

        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_id = {
                executor.submit(self._fetch_case_data, cid): cid
                for cid in unique_case_ids
            }
            for future in as_completed(future_to_id):
                cid = future_to_id[future]
                try:
                    result = future.result()
                    if result:
                        tr_case_cache[str(cid)] = result
                except Exception as e:
                    self._logger.error(f"Failed to pre-fetch TestRail case {cid}: {str(e)}")
        self._logger.info(f"Pre-fetched {len(tr_case_cache)}/{len(unique_case_ids)} TestRail cases")

        for case_id, test_repo in case_data:
            case_id_str = str(case_id)
            test_repo_ = f'/{test_repo}'
            x_case = None
            export_status = "Failed"
            steps_status = "Not Attempted"

            try:
                tr_case_data = tr_case_cache.get(case_id_str)
                if not tr_case_data:
                    self._logger.warning(f"No cached data for case {case_id}, fetching now...")
                    tr_case_data = self.get_case(case_id).json()

                x_case = xray.create_issue(data=tr_case_data, issue_type='Test', test_repo=test_repo_)

                export_status = "Success" if x_case and 'key' in x_case else "Failed"
                if export_status == "Success":
                    imported_count += 1
                    self._logger.info(f"Test case imported successfully: {x_case['key']} from TestRail {case_id}")
                else:
                    failed_cases.append({
                        'test_rail_id': case_id,
                        'Test Repository': test_repo_,
                        'error': x_case
                    })
                    self._logger.warning(f"Failed to import Test case: {case_id} from section {test_repo_}")
                    continue

                # === PERFORMANCE IMPROVEMENT: Parallel precondition attachment upload ===
                preconditions = tr_case_data.get('custom_preconds')
                if preconditions and "index.php?/attachments/get/" in preconditions:
                    attachment_ids = list(set(re.findall(r'index\.php\?/attachments/get/([\w-]+)', preconditions)))
                    self._logger.debug(f"Found {len(attachment_ids)} precondition attachments for case {case_id}")
                    uploaded = xray.upload_precondition_attachments_parallel(
                        issue_key=x_case['key'],
                        attachment_ids=attachment_ids,
                        testrail_client=self
                    )
                    self._logger.debug(
                        f"Uploaded {uploaded}/{len(attachment_ids)} precondition attachments for {x_case['key']}")

                # Steps already use parallel attachment download via optimized add_steps_to_the_test_case
                try:
                    steps = tr_case_data.get('custom_steps_separated')
                    if steps:
                        add_steps = xray.add_steps_to_the_test_case(x_case['key'], steps=steps, testrail_client=self)
                        steps_status = "Success" if add_steps else "Failed"
                        if steps_status == "Failed":
                            self._logger.warning(
                                f"Failed to add steps to {x_case['key']} from Testrail case id: {case_id}")
                except Exception as e:
                    self._logger.error(f"Error adding steps to {x_case['key']}: {str(e)}")
                    steps_status = f"Failed: {str(e)}"

                excel_data.append({
                    'Test Rail Id': case_id,
                    'Xray Key': x_case['key'],
                    'Test Repository': test_repo_,
                    'Export to Xray Status': export_status,
                    'Status of Adding Steps to Xray': steps_status
                })
                processed_count += 1

                # Update Excel every 50 cases for progress tracking
                if processed_count % 50 == 0:
                    pd.DataFrame(excel_data).to_excel(successful_cases_file, index=False)
                    if failed_cases:
                        pd.DataFrame(failed_cases).to_excel(failed_cases_file, index=False)
                    self._logger.info(f"Progress: Processed {processed_count}/{len(case_data)} test cases")
                    print(f"Processed {processed_count}/{len(case_data)} test cases...")

            except Exception as e:
                self._logger.error(
                    f"Error processing TestRail case {case_id}: {str(e)} {x_case['key'] if x_case and 'key' in x_case else ''}")
                excel_data.append({
                    'Test Rail Id': case_id,
                    'Test Repository': test_repo_,
                    'Export to Xray Status': f"Failed: {str(e)}",
                    'Status of Adding Steps to Xray': "Not Attempted"
                })

        # Final Excel update
        if excel_data:
            pd.DataFrame(excel_data).to_excel(successful_cases_file, index=False)
            self._logger.info(f"Excel report saved as: {successful_cases_file} with {len(excel_data)} cases")
            print(f"Excel report saved as: {successful_cases_file} with {len(excel_data)} cases")
        if failed_cases:
            pd.DataFrame(failed_cases).to_excel(failed_cases_file, index=False)
            self._logger.info(f"Failed cases report saved as: {failed_cases_file} with {len(failed_cases)} cases")
            print(f"Failed cases report saved as: {failed_cases_file} with {len(failed_cases)} cases")

        return excel_data, failed_cases, imported_count

    def _fetch_case_data(self, case_id):
        """Thread-safe helper to fetch a single TestRail case."""
        return self.get_case(case_id).json()


# === INPUT: Excel file reading — UNCHANGED from original implementation ===
obj = TestCaseCreation()
obj._logger.info("=== Starting TestRail to Xray re-import ===")
file_1 = pd.read_excel(
    r"/Users/sakella/PycharmProjects/xray_migration/Scripts/failed_cases_test1_20260317_104755.xlsx")  # TODO
file_1['test_rail_id'] = file_1['test_rail_id'].astype(str).str.replace(r'^C', '', regex=True)
file_1['Test Repository'] = (
    file_1['Test Repository']
    .str.replace("'", "", regex=False)
    .str.replace(r"\s+", " ", regex=True)
    .str.strip()
)
case_data = list(zip(file_1['test_rail_id'], file_1['Test Repository']))
obj.test_create_case_in_xray(case_data)
obj._logger.info("=== Re-import completed ===")