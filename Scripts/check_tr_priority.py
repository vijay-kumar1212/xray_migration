"""Get all priority-related fields from TestRail for project 127."""
import json
from testrail.testrail_client import TestRailClient

tr = TestRailClient(project_id=127)

# Built-in priorities
r = tr.session.get(f'{tr.url}/get_priorities', headers=tr.headers, timeout=30)
print('=== Built-in Priorities (priority_id field) ===')
for p in r.json():
    pid = p['id']
    name = p['name']
    short = p.get('short_name', '?')
    default = p.get('is_default', '?')
    print(f'  id={pid}, name={name}, short_name={short}, is_default={default}')

# Custom priority fields
print()
r2 = tr.session.get(f'{tr.url}/get_case_fields', headers=tr.headers, timeout=30)
for f in r2.json():
    label = f.get('label', f.get('name', ''))
    sys_name = f.get('system_name', '')
    if 'priority' in label.lower() or 'priority' in sys_name.lower():
        type_id = f.get('type_id', '?')
        print(f'=== {label} (system_name={sys_name}, type_id={type_id}) ===')
        for cfg in f.get('configs', []):
            ctx = cfg.get('context', {})
            proj_ids = ctx.get('project_ids', [])
            is_global = ctx.get('is_global', False)
            if is_global or not proj_ids or 127 in proj_ids:
                items = cfg.get('options', {}).get('items', '')
                if items:
                    for line in items.split('\n'):
                        line = line.strip()
                        if line:
                            print(f'  {line}')
        print()

# Also get a sample case to see which priority fields are populated
print('=== Sample case from project 127 ===')
r3 = tr.session.get(f'{tr.url}/get_cases/127&suite_id=8696&limit=1', headers=tr.headers, timeout=30)
cases = r3.json()
if isinstance(cases, dict) and 'cases' in cases:
    cases = cases['cases']
if cases:
    c = cases[0]
    print(f'  case_id={c.get("id")}')
    print(f'  priority_id={c.get("priority_id")}')
    print(f'  custom_priorityomnia={c.get("custom_priorityomnia")}')
