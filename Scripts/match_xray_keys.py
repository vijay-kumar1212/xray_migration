"""
Match Test Case Keys from OMNIA folder export against the migration report.

For each Test Case Key in the OMNIA export that matches an Xray Key in the
migration report, output a row with all columns from the migration report.

Input:
    - OMNIA export:      Test Case Key, Summary, Created Date, TestRail ID
    - Migration report:  Test Rail Id, Xray Key, Test Repository,
                         Test Case Title, Export to Xray Status,
                         Status of Adding Steps to Xray, Failure Reason

Output:
    Excel file with all migration-report columns for matched keys only.
"""
import os
from datetime import datetime

import pandas as pd


# ======================== CONFIG ========================
OMNIA_FILE = r"C:\xray_migration\xray_migration\OMNIA__tests_20260427_152350.xlsx"
MIGRATION_FILE = r"C:\Users\VijayKumar.Panga\Downloads\migration_report_20260424_184005.xlsx"
OUTPUT_DIR = r"C:\xray_migration\xray_migration"


def main():
    print(f"Reading OMNIA file: {OMNIA_FILE}")
    omnia_df = pd.read_excel(OMNIA_FILE)
    print(f"  Rows: {len(omnia_df)}, Columns: {list(omnia_df.columns)}")

    print(f"\nReading migration report: {MIGRATION_FILE}")
    migration_df = pd.read_excel(MIGRATION_FILE)
    print(f"  Rows: {len(migration_df)}, Columns: {list(migration_df.columns)}")

    # Normalise keys for matching (strip whitespace, uppercase)
    omnia_keys = (
        omnia_df['Test Case Key']
        .dropna()
        .astype(str)
        .str.strip()
        .str.upper()
    )
    omnia_key_set = set(omnia_keys)
    print(f"\nUnique Test Case Keys in OMNIA file: {len(omnia_key_set)}")

    migration_df['_xray_key_normalised'] = (
        migration_df['Xray Key']
        .astype(str)
        .str.strip()
        .str.upper()
    )

    # Filter migration report to only rows where Xray Key is in OMNIA keys
    matched_df = migration_df[
        migration_df['_xray_key_normalised'].isin(omnia_key_set)
    ].copy()
    matched_df = matched_df.drop(columns=['_xray_key_normalised'])

    print(f"Matched rows: {len(matched_df)}")
    print(f"Unmatched OMNIA keys: {len(omnia_key_set) - matched_df['Xray Key'].str.upper().nunique()}")

    # Write output
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    output_file = os.path.join(
        OUTPUT_DIR,
        f"matched_migration_report_{timestamp}.xlsx"
    )
    matched_df.to_excel(output_file, index=False, sheet_name='Matched Tests')
    print(f"\nOutput written to: {output_file}")
    print(f"Matched rows: {len(matched_df)}")


if __name__ == '__main__':
    main()
