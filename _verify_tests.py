"""Verify test cases are Xray-indexed."""
from xray.xray_client import XrayClient

xray = XrayClient()

for key in ['DFE-72547', 'DFE-72548']:
    resp = xray._upload_session.get(
        f'{xray.url}rest/api/3/issue/{key}?fields=summary,issuetype',
        headers=xray.headers, timeout=30)
    if resp.status_code == 200:
        data = resp.json()
        jira_id = data['id']
        itype = data['fields']['issuetype']['name']
        summary = data['fields']['summary'][:60]
        print(f'{key}: type={itype}, id={jira_id}, summary={summary}')
        
        # Check Xray indexing
        gql = xray._graphql("""
            query GetTest($issueId: String!) {
                getTest(issueId: $issueId) {
                    issueId
                    testType { name }
                    jira(fields: ["key"])
                }
            }
        """, {"issueId": jira_id})
        if gql and 'getTest' in gql:
            print(f'  Xray indexed: YES - {gql["getTest"]}')
        else:
            print(f'  Xray indexed: NO')
    else:
        print(f'{key}: HTTP {resp.status_code}')
