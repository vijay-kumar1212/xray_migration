from testrail.testrail_client import TestRailClient
from xray.xray_client import XrayClient

class TestRailRunToXray:
    Tr = TestRailClient()
    run_data = Tr.get_run(run_id=234326)
    run_cases = Tr.get_tests(234326).json()
    all_cases = []
    for case in run_cases['tests']:
        all_cases.append((case['title'],case['status_id']))

    Xray = XrayClient()
    x_cases = Xray.get_all_tests()
    identified_x_cases = []
    case_status = {}
    test_run = Xray.create_issue(issue_type='Test Execution', data = run_data)
    test_run_key = test_run['key']
    # TR_STATUSES = {'passed': 1, 'canceled': 2, 'blocked': 2, 'broken': 2, 'untested': 3, 'retest': 4, 'failed': 5}
    for case in x_cases:
        case_id = case['id']
        case_ = Xray.get_test_(id = case_id)
        name = case_['fields']['summary']
        for case_name_, status_id in all_cases:
            if name == case_name_:
                identified_x_cases.append(case_['key'])
                case_status[case_['key']] = status_id
    Xray.add_tests_to_test_run(key=test_run_key, issues_list=identified_x_cases)
    # run_statuses = Xray.get_run_test_statuses()
    xray_test_execution_status = {
        1: 0,  # PASS/PASSED
        2: 1000,  # BLOCKED
        3: 1,  # TO_DO/ UNTESTED
        4: 2,  # EXECUTING/RETEST
        5: 3,  # FAIL/failed
        'N/A': 1001,  # N/A
        "ABORTED": 4,  # "ABORTED"
        "NO_RUN": 1002,  # "NO_RUN"
    }
    for key in case_status.keys():
        Xray.update_test_status(exec_key=test_run_key,test_key=key,status=xray_test_execution_status[case_status[key]])


"""
#  rest/raven/1.0/api/testrun/944608/status 
0 : {id: 0, name: "PASS", description: "The test run/iteration has passed", color: "#95C160",…}
1 : {id: 3, name: "FAIL", description: "The test run/iteration has failed", color: "#D45D52",…}
2 : {id: 4, name: "ABORTED", description: "The test run/iteration was aborted", color: "#111111",…}
3 : {id: 1001, name: "N/A", description: "The test may not be applicable to execute in a specific label",…}
4 : {id: 1002, name: "NO_RUN", description: "The test may not be applicable to execute", color: "#454545",…}
5 : {id: 2, name: "EXECUTING", description: "The test run/iteration is currently being executed",…}
6 : {id: 1000, name: "BLOCKED", description: "The test run/iteration was blocked", color: "#1414FF",…}
7 : {id: 1, name: "TODO", description: "The test run/iteration has not started", color: "#A2A6AE",…}

"""
