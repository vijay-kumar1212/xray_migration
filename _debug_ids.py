"""Debug: check Jira IDs and Xray internal IDs for test cases."""
from xray.xray_client import XrayClient

xray = XrayClient()

for key in ['DFE-9457', 'DFE-9458', 'DFE-9462']:
    resp = xray._upload_session.get(
        f'{xray.url}rest/api/3/issue/{key}?fields=summary',
        headers=xray.headers, timeout=30)
    if resp.status_code == 200:
        data = resp.json()
        jira_id = data['id']
        summary = data['fields']['summary'][:60]
        print(f'{key}: jira_id={jira_id}, summary={summary}')
        
        # Try to get Xray internal test ID via GraphQL
        gql_data = xray._graphql("""
            query GetTest($issueId: String!) {
                getTest(issueId: $issueId) {
                    issueId
                    testType { name }
                    jira(fields: ["key"])
                }
            }
        """, {"issueId": jira_id})
        if gql_data:
            print(f'  Xray data: {gql_data}')
        else:
            print(f'  Xray: no data returned')
    else:
        print(f'{key}: HTTP {resp.status_code}')
