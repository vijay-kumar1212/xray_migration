from testrail.testrail_client import TestRailClient
from xray.xray_client import XrayClient

class TestRailRunToXray(TestRailClient):
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

    def test_run_export_to_xray(self, plan_id=10335, run_id = 235827, is_plan = False):
        xray = XrayClient()
        case_ = xray.get_test_case(key='DFE-50677')
        if is_plan:
            test_plan_name, run_data = self.get_plan(plan_id=plan_id)
            xray.create_test_plan_or_execution(issue_type='Test Plan', test_plan_name=test_plan_name)
        else:
            run_data = self.get_run(run_id=run_id)
            # execution = xray.create_test_plan_or_execution(issue_type='Test Execution', test_run_name=run_data['name'])
        

        all_cases = self.get_all_test_cases_from_testrail_run(run_id=run_id)
        x_cases = xray.get_cases_from_section(section_id=22182)
        identified_x_cases = []
        case_status = {}
        # test_run = xray.create_issue(issue_type='Test Execution', data = run_data)
        test_run_key = 'DFE-65756'
        # TR_STATUSES = {'passed': 1, 'canceled': 2, 'blocked': 2, 'broken': 2, 'untested': 3, 'retest': 4, 'failed': 5}
        for case in x_cases:
            case_key = case['key']
            case_ = xray.get_test_case(key=case_key)
            if case_.status_code != 200:
                continue
            case_data = case_.json()
            name = case_data.get('fields', {}).get('summary', '')
            for case_name_, status_id in all_cases:
                if name == case_name_:
                    identified_x_cases.append(case_key)
                    case_status[case_key] = status_id
        xray.add_tests_to_test_run(key=test_run_key, issues_list=identified_x_cases)
        # run_statuses = xray.get_run_test_statuses()
        
        for key in case_status.keys():
            xray.update_test_status(exec_key=test_run_key,test_key=key,status=self.xray_test_execution_status[case_status[key]])


    def get_all_test_cases_from_testrail_run(self, run_id):
        run_cases = self.get_tests(run_id).json()
        all_cases = []
        for case in run_cases['tests']:
            all_cases.append((case['title'], case['status_id']))
        return all_cases

    def runs_data_from_test_plan(self,plan_id):
        tr_plan = self.get_plan(plan_id=plan_id)
        test_plan_name = tr_plan['name']
        runs_in_plan = tr_plan['entries']
        runs_data = []
        run_data = {
            'name': None,
            'run_id': None,
            'suite_id': None,
            'passed_cases': None

        }
        for run in runs_in_plan:
            run_data['name'] = run['runs'][0]['name']
            run_data['run_id'] = run['runs'][0]['id']
            run_data['suite_id'] = run['runs'][0]['suite_id']
            runs_data.append(run_data.copy())
        return test_plan_name, runs_data

test_run = TestRailRunToXray()
test_run.test_run_export_to_xray()



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
