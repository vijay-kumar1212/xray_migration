import pandas as pd
source_file = r"C:\xray_migration\xray_migration\Oxygen Native Regression Package.xlsx"
generated_file_from_run = r'C:\xray_migration\xray_migration\Oxygen Native Regression Package.xlsx'

pdg = pd.read_excel(generated_file_from_run)
pds = pd.read_excel(source_file)

# Convert both ID columns to strings and remove 'C' prefix from source
pds_ids = pds.iloc[:, 0].astype(str).str.replace(r'^C', '', regex=True)
pdg_ids = pdg.iloc[:, 0].astype(str).str.replace(r'^C', '', regex=True)

# Filter out rows where IDs match
pds_filtered = pds[~pds_ids.isin(pdg_ids)]

# Save the filtered result
pds_filtered.to_excel(source_file.replace('.xlsx', '_filtered.xlsx'), index=False)

