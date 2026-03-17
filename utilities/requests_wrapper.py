import json
from time import sleep

import requests
from requests import HTTPError
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib3.exceptions import InsecureRequestWarning

from utilities.exceptions import MigrationAPIError
from utilities.log_mngr import setup_custom_logger

requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
_logger = setup_custom_logger()

# === PERFORMANCE IMPROVEMENT: Shared session with connection pooling and retry ===
# Instead of creating a new connection per request, reuse connections via a session.
# HTTPAdapter with pool_connections/pool_maxsize allows concurrent reuse.
# Retry strategy uses exponential backoff instead of flat sleep(10).
_session = requests.Session()
_retry_strategy = Retry(
    total=3,
    backoff_factor=1,  # 1s, 2s, 4s exponential backoff
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET", "POST", "PUT", "DELETE"],
    raise_on_status=False
)
_adapter = HTTPAdapter(
    max_retries=_retry_strategy,
    pool_connections=10,  # Connection pool size
    pool_maxsize=20  # Max connections in pool (supports parallel threads)
)
_session.mount("https://", _adapter)
_session.mount("http://", _adapter)


def do_request(url, method="GET", headers=None, data=None, json_=None, proxies=None, load_response=True, **kwargs):
    """
    Performs an HTTP request using a shared session with connection pooling.

    PERFORMANCE CHANGES:
    - Uses shared requests.Session with connection pooling (was: new connection per call)
    - Uses urllib3 Retry with exponential backoff (was: flat sleep(10) retry)
    - Removed redundant manual retry loops
    - Timeout increased to 60s for large attachment uploads
    """
    keywords = kwargs
    _logger.info('*** Requesting %s Request %s' % (method, url))
    if data:
        data = json.dumps(data)

    try:
        r = _session.request(
            url=url, method=method, headers=headers, data=data,
            json=json_, proxies=proxies, verify=False, timeout=60,
            **keywords
        )
    except Exception as e:
        _logger.warning(f"Request failed, retrying once: {e}")
        sleep(2)
        r = _session.request(
            url=url, method=method, headers=headers, data=data,
            json=json_, proxies=proxies, verify=False, timeout=60,
            **keywords
        )

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
        _logger.error('API Returned HTTP %s (%s)' % (e, error))
        return {'error': f'API Returned HTTP {e} ({error})'}
    return result


def check_status_code(request_):
    r = request_
    try:
        r.raise_for_status()
    except HTTPError as e:
        return e
