import pandas as pd

primary_file = pd.read_excel(r'C:\xray_migration\xray_migration\E2E Suite to be migrated_filtered.xlsx')
secondary_file = pd.read_excel(r'C:\xray_migration\xray_migration\failed_cases_E2E Suite To be Migrated_20260312_172233.xlsx')

col1 = primary_file.columns[0]
missed_cases = set(primary_file.iloc[:, 0]) - set(secondary_file.iloc[:, 0])

pd.DataFrame({col1: list(missed_cases)}).to_excel('missed_cases.xlsx', index=False)
print(f'Missed cases: {len(missed_cases)}')