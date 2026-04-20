"""Get all custom dropdown fields and options from TestRail for project 127 (OMNIA)."""
import json
from testrail.testrail_client import TestRailClient

tr = TestRailClient(project_id=127)
r = tr.session.get(f'{tr.url}/get_case_fields', headers=tr.headers, timeout=30)
fields = r.json()
print(f'Total case fields: {len(fields)}\n')

for f in fields:
    type_id = f.get('type_id')
    # 6=Dropdown, 12=Multi-select, 4=Integer, 7=Checkbox, 3=Text, 1=String, 9=URL, 8=Date
    if f.get('configs'):
        name = f.get('label', f.get('name', '?'))
        sys_name = f.get('system_name', '?')
        type_map = {1: 'String', 2: 'Integer', 3: 'Text', 4: 'URL', 5: 'Checkbox',
                    6: 'Dropdown', 7: 'User', 8: 'Date', 9: 'Milestone', 10: 'Steps',
                    11: 'Step Results', 12: 'Multi-select'}
        type_name = type_map.get(type_id, f'type_{type_id}')

        for cfg in f.get('configs', []):
            ctx = cfg.get('context', {})
            proj_ids = ctx.get('project_ids', [])
            is_global = ctx.get('is_global', False)
            if is_global or not proj_ids or 127 in proj_ids:
                options = cfg.get('options', {})
                items = options.get('items', '')
                if type_id in [6, 12] and items:
                    print(f'=== {name} (system_name={sys_name}, type={type_name}) ===')
                    for line in items.split('\n'):
                        line = line.strip()
                        if line:
                            print(f'  {line}')
                    print()
                elif type_id == 5:
                    print(f'=== {name} (system_name={sys_name}, type=Checkbox) ===')
                    print()
