"""
TestRail to Xray Cloud - Test Case Migration (Multithreaded)
=============================================================
Reads case IDs + section hierarchy from an Excel file, creates test cases
in Xray Cloud with steps and attachments, and generates a status report.

Rate limiting: Xray Cloud allows ~10 req/s for REST and ~4 req/s for GraphQL.
We use max_workers=5 with a per-request throttle to stay well within limits.
"""

import re
import time
import threading
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import pandas as pd
from testrail.testrail_client import TestRailClient
from xray.xray_client import XrayClient
from utilities.log_mngr import setup_custom_logger


class TestCaseCreation(TestRailClient):
    _logger = setup_custom_logger()

    # Xray Cloud rate limits: ~10 req/s REST, ~4 req/s GraphQL
    # With 5 workers each sleeping 0.5s between calls we stay around 10 req/s total
    MAX_WORKERS = 5
    REQUEST_DELAY = 0.5  # seconds between API calls per thread

    def __init__(self):
        super().__init__()
        self._results_lock = threading.Lock()
        self._throttle_lock = threading.Lock()
        self._last_request_time = 0

    def _throttle(self):
        """Simple global throttle to respect Xray Cloud rate limits."""
        with self._throttle_lock:
            now = time.time()
            elapsed = now - self._last_request_time
            if elapsed < self.REQUEST_DELAY:
                time.sleep(self.REQUEST_DELAY - elapsed)
            self._last_request_time = time.time()

    def _process_single_case(self, case_id, test_repo, xray):
        """
        Process one test case: fetch from TestRail → create in Xray → add steps.
        Returns a result dict for the Excel report.
        """
        result = {
            'Test Rail Id': f'C{case_id}',
            'Xray Key': '',
            'Test Repository': test_repo,
            'Test Case Title': '',
            'Export to Xray Status': 'Failed',
            'Status of Adding Steps to Xray': 'Not Attempted',
            'Failure Reason': ''
        }

        try:
            # 1. Fetch case from TestRail
            self._throttle()
            tr_response = self.get_case(case_id)
            tr_case_data = tr_response.json()
            result['Test Case Title'] = tr_case_data.get('title', 'N/A')

            # 2. Create issue in Xray
            self._throttle()
            x_case = xray.create_issue(data=tr_case_data, issue_type='Test', test_repo=test_repo)

            if not x_case or 'key' not in x_case:
                error_msg = str(x_case) if x_case else 'No response from Xray'
                result['Failure Reason'] = error_msg
                self._logger.warning(f'Failed to import case {case_id}: {error_msg}')
                return result

            result['Xray Key'] = x_case['key']
            result['Export to Xray Status'] = 'Success'
            self._logger.info(f"Created {x_case['key']} for TestRail case {case_id}")

            # 3. Upload precondition attachments
            preconditions = tr_case_data.get('custom_preconds', '')
            if preconditions and "index.php?/attachments/get/" in preconditions:
                attachment_ids = list(set(
                    re.findall(r'index\.php\?/attachments/get/([\w-]+)', preconditions)
                ))
                for att_id in attachment_ids:
                    try:
                        self._throttle()
                        att_data, file_name = self.get_attachment(att_id)
                        if att_data:
                            self._throttle()
                            xray.upload_jira_attachment(
                                issue_key=x_case['key'],
                                file_name=f'prerequisite_{file_name}.png',
                                file_bytes=att_data
                            )
                    except Exception as e:
                        self._logger.warning(
                            f"Skipping attachment {att_id} for {x_case['key']}: {e}"
                        )

            # 4. Add test steps
            steps = tr_case_data.get('custom_steps_separated')
            if steps:
                self._throttle()
                add_ok = xray.add_steps_to_the_test_case(
                    x_case['key'], steps=steps, testrail_client=self
                )
                result['Status of Adding Steps to Xray'] = 'Success' if add_ok else 'Failed'
                if not add_ok:
                    result['Failure Reason'] = 'Steps creation failed'
                    self._logger.warning(
                        f"Failed to add steps to {x_case['key']} (TR case {case_id})"
                    )
            else:
                result['Status of Adding Steps to Xray'] = 'No Steps'

        except Exception as e:
            result['Failure Reason'] = str(e)
            self._logger.error(f"Error processing case {case_id}: {e}")

        return result

    def test_create_case_in_xray(self, case_data, max_workers=None):
        """
        Migrate test cases from TestRail to Xray Cloud using multithreading.

        Args:
            case_data: list of (case_id, section_hierarchy) tuples
            max_workers: thread pool size (default: self.MAX_WORKERS)

        Returns:
            Path to the generated Excel report
        """
        workers = max_workers or self.MAX_WORKERS
        xray = XrayClient()
        total = len(case_data)

        self._logger.info(
            f"Starting migration of {total} test cases with {workers} workers"
        )
        print(f"Starting migration of {total} test cases with {workers} workers...")

        results = []
        processed = 0

        with ThreadPoolExecutor(max_workers=workers) as executor:
            future_map = {}
            for case_id, test_repo_section in case_data:
                test_repo = f'/{xray.test_repository}/{test_repo_section}'
                future = executor.submit(
                    self._process_single_case, case_id, test_repo, xray
                )
                future_map[future] = case_id

            for future in as_completed(future_map):
                case_id = future_map[future]
                try:
                    result = future.result()
                except Exception as e:
                    result = {
                        'Test Rail Id': f'C{case_id}',
                        'Xray Key': '',
                        'Test Repository': '',
                        'Test Case Title': 'N/A',
                        'Export to Xray Status': 'Failed',
                        'Status of Adding Steps to Xray': 'Not Attempted',
                        'Failure Reason': str(e)
                    }
                    self._logger.error(f"Unhandled error for case {case_id}: {e}")

                with self._results_lock:
                    results.append(result)
                    processed += 1
                    if processed % 50 == 0 or processed == total:
                        pct = (processed / total) * 100
                        self._logger.info(
                            f"Progress: {processed}/{total} ({pct:.1f}%)"
                        )
                        print(f"Progress: {processed}/{total} ({pct:.1f}%)")

        # Generate Excel report
        report_file = (
            f"migration_report_"
            f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        )
        df = pd.DataFrame(results, columns=[
            'Test Rail Id', 'Xray Key', 'Test Repository',
            'Test Case Title', 'Export to Xray Status',
            'Status of Adding Steps to Xray', 'Failure Reason'
        ])
        df.to_excel(report_file, index=False, sheet_name='Migration Report')

        # Summary
        success_count = df[df['Export to Xray Status'] == 'Success'].shape[0]
        failed_count = df[df['Export to Xray Status'] == 'Failed'].shape[0]
        steps_ok = df[df['Status of Adding Steps to Xray'] == 'Success'].shape[0]

        summary = (
            f"\n{'='*60}\n"
            f"Migration Summary\n"
            f"{'='*60}\n"
            f"Total cases:       {total}\n"
            f"Created in Xray:   {success_count}\n"
            f"Failed:            {failed_count}\n"
            f"Steps added:       {steps_ok}\n"
            f"Report saved:      {report_file}\n"
            f"{'='*60}"
        )
        self._logger.info(summary)
        print(summary)

        return report_file


# ======================== MAIN ========================
if __name__ == '__main__':
    obj = TestCaseCreation()

    file_path = r"C:\xray_migration\xray_migration\Scripts\omnia cloud instance test.xlsx"
    file_1 = pd.read_excel(file_path)

    file_1['ID'] = file_1['ID'].astype(str).str.replace(r'^C', '', regex=True)
    file_1['Section Hierarchy'] = (
        file_1['Section Hierarchy'].str.strip()
        .str.replace(r"[\"']", "", regex=True)
        .str.replace(r"[\\/]", " & ", regex=True)
        .str.replace(r"\s+", " ", regex=True)
        .str.replace(r"\s*>\s*", "/", regex=True)
        .str.strip()
    )

    case_data = list(zip(file_1['ID'], file_1['Section Hierarchy']))
    obj.test_create_case_in_xray(case_data)
