import re
import pandas as pd

log_file = r"C:\xray_migration\xray_migration\ob digital opimized regression manual.log"       # your log file
output_file = "../dfe/errors.xlsx"  # output excel

patterns = [
    r"Created Xray test case\s+([A-Z]+-\d+)\s+for TestRail case\s+(\d+)"
    r"Error processing TestRail case (\d+): '(.*?)'",
    r"Failed to create Xray test case for TestRail case (\d+)"
]

rows = []

with open(log_file, "r", encoding="utf-8", errors="ignore") as f:
    for line in f:
        for pattern in patterns:
            match = re.search(pattern, line)
            if match:
                if "Error processing" in pattern:
                    rows.append({
                        "Type": "Processing Error",
                        "Case ID": match.group(1),
                        "Message": match.group(2)
                    })
                else:
                    rows.append({
                        "Type": "Creation Failed",
                        "Case ID": match.group(1),
                        "Message": "Xray creation failed"
                    })

df = pd.DataFrame(rows)
df.to_excel(output_file, index=False)

print("Excel created:", output_file)