from testrail.testrail_client import TestRailClient
from xray.xray_client import XrayClient
import pandas as pd

class RunCompare(TestRailClient):

    def get_all_test_cases_from_testrail_run(self, run_id):
        run_cases = self.get_tests(run_id).json()
        desktop_cases = []
        mobile_cases = []
        other_cases = []
        for case in run_cases['tests']:
            title = case['title']
            if '[DESKTOP CHROME]' in title:
                title = title.replace('[DESKTOP CHROME]', '').strip()
                desktop_cases.append(title)
            elif '[IPHONE 14 PRO MAX]' in title:
                title = title.replace('[IPHONE 14 PRO MAX]', '').strip()
                mobile_cases.append(title)
            else:
                other_cases.append(title)

        return desktop_cases,mobile_cases,other_cases

    def get_test_case_titles(self, run_id):
        # run_data = self.get_run(run_id=run_id)
        all_cases = self.get_all_test_cases_from_testrail_run(run_id=run_id)
        return all_cases

    @staticmethod
    def get_tests_from_xray_run(execution_key):
        xr = XrayClient()
        xr_case_titles = []
        xr_cases = xr.get_tests_in_execution(execution_key)
        for case in xr_cases:
            summary = xr.get_issue_summary(case['key'])
            if summary:
                xr_case_titles.append(summary)
        return xr_case_titles

    def cases_not_covered_in_xray(self):
        testrail_cases_desktop, mobile, other = self.get_test_case_titles(236454) #236454
        xr_cases = self.get_tests_from_xray_run('DFE-72002')
        xr_mobile_cases = self.get_tests_from_xray_run('DFE-72003')

        diff_m = set(mobile) - set(xr_mobile_cases)
        diff_d = set(testrail_cases_desktop) - set(xr_cases)
        return diff_d, len(diff_d), diff_m, len(diff_m)
run = RunCompare()
dif, len_, mob, l = run.cases_not_covered_in_xray()
df = pd.DataFrame(dif, columns=['Title'] )
df2 = pd.DataFrame(mob, columns=['Title'] )
df.to_excel('desktop_cases.xlsx', index = False)
df2.to_excel( 'mobile_cases.xlsx', index = False)
print(len_, f'\n mobile mised cases: {l}')
for i in dif:
    print('\n' + i)
print("=" * 18)
for j in mob:
    print('\n' + j)
