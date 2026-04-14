import pandas as pd

df = pd.read_excel(r'C:\xray_migration\xray_migration\Scripts\reimport_E2E Suite To be Migrated_20260321_015640.xlsx')
df2 = df[df['Export to Xray Status'] == "Failed: 'title'"]
df2.to_excel('failed2_re_import_cases.xlsx', index=False, columns=['Test Rail Id', 'Test Repository'])
