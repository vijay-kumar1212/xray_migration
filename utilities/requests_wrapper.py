import json
from time import sleep

import requests
from requests import request, HTTPError
from urllib3.exceptions import InsecureRequestWarning

from utilities.exceptions import MigrationAPIError
from utilities.log_mngr import setup_custom_logger

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
_logger = setup_custom_logger()

def do_request(url, method = "GET", headers = None, data=None, json_ = None, proxies = None, load_response =True, **kwargs):
    keywords = kwargs
    _logger.info('*** Requesting %s Request %s' %(method, url))
    if data:
        data = json.dumps(data)

    try:
        r = request(url=url, method=method, headers=headers, data=data, json=json_, proxies=proxies, verify=False, timeout=40,
                    **keywords)
        if not f"{r.status_code}".startswith("2"):
            sleep(10)
            r = request(url=url, method=method, headers=headers, data=data, json=json_, proxies=proxies, verify=False, timeout=60,
                        **keywords)
    except Exception as e:
        _logger.warning(e)
        sleep(1)
        r = request(url=url, method=method, headers=headers, data=data, json=json_, proxies=proxies, verify=False, timeout=60,
                    **keywords)
        if not f"{r.status_code}".startswith("2"):
            sleep(10)
            r = request(url=url, method=method, headers=headers, data=data, json=json_, proxies=proxies, verify=False, timeout=60,
                        **keywords)
    e = check_status_code(r)
    if load_response:
        if r.text == '':
            raise MigrationAPIError(f"Empty response from {url}")
        resp_dict = json.loads(r.text)
        result = resp_dict
    else:
        result = r.text
    if e is not None:
        if result and 'error' in result:
            error = result['error'] if isinstance(result, dict) else result
        else:
            error = "No additional error message is received"
        raise MigrationAPIError('API Returned HTTP %s (%s)' %(e, error))
    return result

def check_status_code(request_):
    r = request_
    try:
        r.raise_for_status()
    except HTTPError as e:
        return e