import base64
import requests

all_section_data = []

class TestRailClient:

    def __init__(self,
                 base_url="https://ladbrokescoral.testrail.com/",
                 project_id = 36,
                 suite_id = 3779,
                 mile_stone_id = 1026,
                 user = None,   # vijaykumar.panga@ivycomptech.com   Vijay123
                 password = None):
        self.session = requests.Session()
        # self.session.verify = False
        self.project_id = project_id
        self.suite_id = suite_id
        self.milestone_id = mile_stone_id
        (self.user,self.password) = (user, password) if user and password else ("vijaykumar.panga@ivycomptech.com", "Vijay123")
    #     if we don't have user and password then need to raise an error here
        self.base_url = base_url
        if not base_url.endswith('/'):
            self.base_url = base_url + '/'
        self.url = self.base_url + "index.php?/api/v2"
        creds = f'{self.user}:{self.password}'
        creds = creds.encode('utf-8')
        self.auth = base64.b64encode(creds).decode('utf-8')
        self.headers = {
            'Authorization': f'Basic {self.auth}',
            'Content-Type': 'application/json'
        }
        self.login()

    def login(self):
        login_url = f"{self.base_url}index.php?/auth/login"

        payload = {
            "name": self.user,
            "password": self.password,
            "rememberme": 1
        }

        response = self.session.post(login_url, data=payload)
        response.raise_for_status()

        if "auth/login" in response.url:
            raise Exception("TestRail login failed")

    def get_attachment(self, attachment_id):
        if not attachment_id:
            return None, None

        url = f"{self.base_url}index.php?/attachments/get/{attachment_id}"

        response = self.session.get(url, stream=True)
        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "")

        # 🚨 Detect auth failure
        if "text/html" in content_type.lower():
            raise Exception(
                f"HTML returned instead of attachment for ID {attachment_id}. "
                "Authentication/session issue."
            )

        # Extract filename
        filename = f"{attachment_id}"
        cd = response.headers.get("Content-Disposition", "")
        if "filename=" in cd:
            filename = cd.split("filename*")[-1].strip('"')

        return response.content, filename

    def get_testrail_username_password(self):
        return self.user, self.password

    def get_custom_fields(self): #TODO
        return requests.get(url='%s/get_case_fields'%(self.url), headers=self.headers).json()

    def get_case(self, case_id):
        return self.session.get(url='%s/get_case/%s'%(self.url, case_id), headers=self.headers)

    def get_cases(self, project_id, suite_id, section_id=None, offset=0,test_name=None):
        project_id = project_id if project_id else self.project_id
        suite_id = suite_id if suite_id else self.suite_id
        params = {
            'suite_id': suite_id,
        }
        if section_id:
            params['section_id'] = section_id
        return requests.get(url=f'{self.url}/get_cases/{project_id}&suite_id={suite_id}&offset={offset}&filter={test_name}',headers=self.headers)

    def get_section(self, section_id):
        """
        :param section_id: The ID of the section
        :return: an existing section
        """
        return requests.get(
                          url='{host_name}/get_section/{section_id}'.format(host_name=self.url, section_id=section_id),
                          headers=self.headers).json()

    def get_sections(self,project_id, suite_id, offset=0):
        """
        :param offset: Number that sets the position where the response should start from
        :param project_id:
        :param suite_id:
        :return: a list of sections for a project and test suite.
        :Below are the changes with respect to new api change -version TestRail 7.2.1
        :Adding parameter offset=0 and change the url format
        """
        return requests.get(
                          url='{host_name}/get_sections/{project_id}&suite_id={suite_id}&offset={offset}'
                          .format(host_name=self.url, project_id=self.project_id if not project_id else project_id, suite_id=self.suite_id if not suite_id else suite_id,
                                  offset=offset),
                          headers=self.headers)

    def get_section_cases(self, suite_id, section_id):
        cases = requests.get(url=f'{self.url}/get_cases/{self.project_id}&suite_id={suite_id}&section_id={section_id}',headers=self.headers).json()
        return cases

    def get_runs(self, is_completed=0):
        """
        :param project_id: The ID of the project
        :param is_completed: 1 to return completed test runs only. 0 to return active test runs only.
        :return: a list of test runs for a project
        """
        return requests.get(
                          url='{host_name}/get_runs/{project_id}&is_completed={is_completed}'
                          .format(host_name=self.url, project_id=self.project_id, is_completed=is_completed),
                          headers=self.headers).json()

    def get_run(self, run_id):
        """
        :param run_id: The ID of the test run
        :return: an existing test run
        """
        return requests.get(
                          url='{host_name}/get_run/{run_id}'
                          .format(host_name=self.url, run_id=run_id),
                          headers=self.headers).json()


    def get_tests(self, run_id, offset=0):
        """
        :param offset: Number that sets the position where the response should start from
        :param run_id: The ID of the test run
        :return: a list of tests for a test run.
        :Code update date: 21/09/2021
        :Below are the changes with respect to new api change -version TestRail 7.2.1
        :Adding parameter offset=0 and change the url format
        """
        url = '{host_name}/get_tests/{run_id}&status_id=1,2,4,5&offset={offset}'.format(host_name=self.url,
                                                                                        run_id=run_id, offset=offset)
        return requests.get(
                          url=url,
                          headers=self.headers)


    def get_all_sections_data(self,project_id,suite_id):
        """
        Date-07 Oct 2021
        To get all sections data use this method. Added method with respect new API's update from Testrail API-7.2.1
        :return: If successful, this method returns all the sections data from the respective suite
        """
        # self._logger.info('********* Collecting Section data from testrail **********')
        # print('********* Collecting Section data from testrail **********')
        count = 0
        while True:
            sections = self.get_sections(offset=count,project_id=project_id,suite_id=suite_id).json()
            all_section_data.extend(sections['sections'])
            next_link = sections['_links']['next'] if sections['_links']['next'] is not None else None
            if next_link is None:
                break
            count += 250

        return all_section_data

    def get_current_section_for_case(self, path):
        """
        :param path: path to the test (e.g. tests.pack003.test_C29588 or tests/pack003/test_C29588.py)
        :return: Current section where testcase is placed
        """
        path = path.replace('.', '/').split('/')
        path[0] = 'Automation Tests'

        # available_sections = self.get_sections()
        # parent_section_id = None
        # for folder in path:
        #     if folder.startswith('test_'):
        #         break
        #     current_section = next((section for section in available_sections['sections']
        #                             if (section['name'] == folder and section['parent_id'] == parent_section_id)), None)
        #     if not current_section:
        #         current_section = self.add_section(data={'name': folder, 'parent_id': parent_section_id, 'suite_id': self.suite_id})
        #     parent_section_id = current_section['id']
        #     # self._logger.debug('*** Parent section id %s' % parent_section_id)

        # Added below changes with respective new API change from testrail. Testrail API - 7.2.1 (Date - 07 Oct 2021)
        global all_section_data
        try:
            if not all_section_data:
                self.get_all_sections_data()
        except Exception as e:
            all_section_data.clear()
            self.get_all_sections_data()

        parent_section_id = None
        for folder in path:
            if folder.startswith('test_'):
                break
            current_section = next((section for section in all_section_data
                                    if (section['name'] == folder and section['parent_id'] == parent_section_id)), None)
            if not current_section:
                current_section = self.add_section(
                    data={'name': folder, 'parent_id': parent_section_id, 'suite_id': self.suite_id})
            parent_section_id = current_section['id']

        return current_section


    def get_all_test_cases(self, run_id):
        """
        Retrieves all test data for a specified run ID from a paginated API endpoint.

        This method fetches test data from a server in chunks, handling pagination
        by iterating with an offset until all data is retrieved. The data is gathered
        into a single list and returned.

        Parameters:
        run_id (str): The unique identifier for the run for which to retrieve tests.

        Returns:
        list: A list containing all the test data for the specified run.

        Raises:
        Exception: If the request to the server fails or returns an error.

        Example:
        tests = instance.get_all_test_cases(run_id='12345')
        """
        all_tests = []
        offset = 0
        while True:
            resp = requests.get(
                              url='{host_name}/get_tests/{run_id}&offset={offset}'.format(host_name=self.url, run_id=run_id, offset=offset),
                              headers=self.headers)
            all_tests.extend(resp.get('tests'))
            next_link = resp['_links']['next'] if resp['_links']['next'] is not None else None
            if next_link is None:
                break
            offset += 250
        return all_tests




    # def get_results_for_case(self, case_id):
    #     return requests.get(f'get_results_for_case/{case_id}')
    # 
    # def get_results_for_run(self, run_id):
    #     return requests.get(f'get_results_for_run/{run_id}')
    # 
    # def add_result_for_case(self, case_id, data):
    #     return requests.post(f'add_result_for_case/{case_id}', data)
    # 
    # def add_results_for_cases(self, run_id, data):
    #     return requests.post(f'add_results_for_cases/{run_id}', data)
