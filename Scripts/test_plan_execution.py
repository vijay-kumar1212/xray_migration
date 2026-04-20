"""
Test Plan & Execution Automation Script
========================================
Creates a Test Plan, two Test Executions (Desktop & Mobile),
adds test cases to each execution, and updates test-level
and step-level statuses via Xray Cloud GraphQL.
"""

import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utilities.log_mngr import setup_custom_logger
from xray.xray_client import XrayClient

_logger = setup_custom_logger()

# ===================== CONFIGURATION =====================

PROJECT_KEY = "DFE"
PLAN_NAME = "CloudInstance Test Plan"

# Two executions under the same plan
EXECUTIONS = [
    {"name": "Cloud Desktop Execution"},
    {"name": "Cloud Mobile Execution"},
]

# Test cases to add to EACH execution
TEST_CASE_KEYS = ["DFE-72547", "DFE-72548"]

# Status mapping per test case (applied to BOTH executions)
# DFE-72547 = PASS, DFE-72548 = FAIL
TEST_STATUS_MAP = {
    "DFE-72547": {
        "status": "PASSED",
        "step_status": "PASSED",       # all steps PASS
    },
    "DFE-72548": {
        "status": "FAILED",
        "step_status": "FAILED",       # all steps FAIL
    },
}


# ===================== ORCHESTRATION =====================

def main():
    _logger.info("=== Starting Test Plan & Execution Automation ===")
    xray = XrayClient()

    # --- Step 1: Create Test Plan ---
    plan = None
    try:
        plan = xray.create_test_plan(name=PLAN_NAME, project_key=PROJECT_KEY)
        if 'error' in plan:
            _logger.error(f"Test Plan creation failed: {plan['error']}")
            plan = None
        else:
            _logger.info(f"[OK] Test Plan created: {plan['key']}")
    except Exception as e:
        _logger.error(f"Exception creating Test Plan: {e}")

    plan_key = plan['key'] if plan and 'key' in plan else None

    # --- Step 2: Create Test Executions linked to the Plan ---
    execution_keys = []
    for exec_config in EXECUTIONS:
        try:
            exec_result = xray.create_test_execution(
                name=exec_config['name'],
                project_key=PROJECT_KEY,
                plan_key=plan_key
            )
            if 'error' in exec_result:
                _logger.error(f"Execution '{exec_config['name']}' creation failed: {exec_result['error']}")
            else:
                execution_keys.append(exec_result['key'])
                _logger.info(f"[OK] Test Execution created: {exec_result['key']} ({exec_config['name']})")
        except Exception as e:
            _logger.error(f"Exception creating execution '{exec_config['name']}': {e}")

    # --- Step 3: Add test cases to each execution ---
    tests_added_total = 0
    for exec_key in execution_keys:
        try:
            result = xray.add_tests_to_test_run(key=exec_key, issues_list=TEST_CASE_KEYS)
            if result:
                added = result.get('addTestsToTestExecution', {}).get('addedTests', 0)
                tests_added_total += added
                _logger.info(f"[OK] Added {added} tests to {exec_key}")
            else:
                _logger.warning(f"No result adding tests to {exec_key}")
        except Exception as e:
            _logger.error(f"Exception adding tests to {exec_key}: {e}")

    # --- Step 4: Update test-level statuses ---
    test_statuses_updated = 0
    for exec_key in execution_keys:
        for test_key, config in TEST_STATUS_MAP.items():
            try:
                result = xray.update_test_status(
                    exec_key=exec_key,
                    test_key=test_key,
                    status=config['status']
                )
                if result is not None:
                    test_statuses_updated += 1
                    _logger.info(f"[OK] {test_key} -> {config['status']} in {exec_key}")
                else:
                    _logger.warning(f"Failed to update {test_key} status in {exec_key}")
            except Exception as e:
                _logger.error(f"Exception updating {test_key} status in {exec_key}: {e}")

    # --- Step 5: Update step-level statuses ---
    step_updates_total = {"updated": 0, "failed": 0}
    for exec_key in execution_keys:
        for test_key, config in TEST_STATUS_MAP.items():
            step_status = config.get('step_status')
            if not step_status:
                continue
            try:
                # Get steps to know how many there are
                steps = xray.get_test_run_steps(exec_key=exec_key, test_key=test_key)
                if not steps:
                    _logger.warning(f"No steps found for {test_key} in {exec_key}")
                    continue
                # Build a list of the same status for all steps
                statuses = [step_status] * len(steps)
                result = xray.update_all_step_statuses(
                    exec_key=exec_key,
                    test_key=test_key,
                    statuses=statuses
                )
                step_updates_total['updated'] += result.get('updated', 0)
                step_updates_total['failed'] += result.get('failed', 0)
                _logger.info(
                    f"[OK] Step statuses for {test_key} in {exec_key}: "
                    f"{result['updated']} updated, {result['failed']} failed"
                )
            except Exception as e:
                _logger.error(f"Exception updating step statuses for {test_key} in {exec_key}: {e}")

    # --- Summary ---
    print("\n" + "=" * 60)
    print("  TEST PLAN & EXECUTION AUTOMATION — SUMMARY")
    print("=" * 60)
    print(f"  Test Plan:              {plan_key or 'FAILED'}")
    for i, exec_key in enumerate(execution_keys):
        print(f"  Execution {i+1}:            {exec_key} ({EXECUTIONS[i]['name']})")
    print(f"  Tests added (total):    {tests_added_total}")
    print(f"  Test statuses updated:  {test_statuses_updated}")
    print(f"  Step statuses updated:  {step_updates_total['updated']}")
    print(f"  Step updates failed:    {step_updates_total['failed']}")
    print("=" * 60)

    _logger.info("=== Automation completed ===")


if __name__ == '__main__':
    main()
