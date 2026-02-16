import pandas as pd

file_1 = pd.read_excel(r"C:\xray_migration\xray_migration\Scripts\symphony___oxygen_qa.xlsx")
file_2 = pd.read_excel(r"C:\xray_migration\xray_migration\Scripts\testrail_to_xray_migration_20260211_202340.xlsx")

col1 = file_1.columns[0]
col2 = file_2.columns[0]

file_1[col1] = file_1[col1].astype(str)
file_2[col2] = file_2[col2].astype(str)

file_1[col1] = file_1[col1].str.replace(r'^C', '', regex= True)

diff = set(file_1[col1]) - set(file_2[col2])
print(diff)
pd.DataFrame({"Missing_in_File2": list(diff)}).to_excel("missing_in_file2.xlsx", index=False)