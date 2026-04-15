xray_priority = {
        4: '1',  # xray:Highest P1 testrail:Critical
        3: '2',  # High P2
        2: '3',  # Medium P3
        1: '4',  # Low P4
        5: '5',
        10000 : 'Urgent',
        10001: 'Unprioritised'
    }

automation_status = {
        3: '13423',  # Can't Automate (testrail: Cannot be automated)
        1: '13424',  # Ready For Automation (testrail: Manual)
        'Automation In Progress': '13425',  # Automation In Progress
        2: '13426',  # Automated
        'Maintenance': '13427',  # Maintenance
        'No Automation Required': '13428'  # No Automation Required
    }
df_automation_type = {
    1: '13424',  # Manual → Ready For Automation
    2: '13426',  # Automated → Automated
    3: '13423',  # Cannot be automated → Can't Automate
    }

dbt_automation_type = {
        1: "Automation",
        2: "Manual"
    }
omnia_auto_type = {
    1: "-1",      # New → None (no Xray equivalent)
    2: "13424",   # Automation Candidate → Ready For Automation
    3: "13426",   # Automated → Automated
    4: "13423",   # Cannot Automate → Can't Automate
    5: "13425",   # PR raised yet to merge → Automation In Progress
    6: "13427",   # Automated but descoped/deprecated → Maintenance
    7: "13424"    # Manual → Ready For Automation
    }
gbs_auto_type = {
    1: '13426',  # Automated → Automated
    2: '13424',  # Manual → Ready For Automation
    3: '13423',  # Cannot Automate → Can't Automate
    4: '13424',  # → Ready For Automation
    5: '13427'   # → Maintenance
    }
envision_auto_type = {
    1: '-1',      # New → None
    2: '13424',   # Automation Candidate → Ready For Automation
    3: '13426',   # Automated → Automated
    4: '13423',   # Cannot Automate → Can't Automate
    5: '13427'    # Automated but descoped/deprecated → Maintenance
}
custom_brand = {

        1: 'Coral Only',
        2: 'Ladbrokes Only',
        3: 'Both Coral and Ladbrokes',
        4: 'Vanilla Only',
        5: 'All Brands'
    }

xr_devices = {
        3: '14906', #'Desktop'
        1 :'14907', #'Mobile'
        13 : '14908', # 'Mobile&Desktop' for tablet in testrail id is 2
        0 : '-1' # None
    }

omnia_squads = {
    1: "12369",   # Marvels → OMNIA>Retail Marvels
    2: "12370",   # Mavericks → OMNIA>Retail Mavericks
    3: "12371",   # Spartans → OMNIA>Retail Spartans
    4: "12367",   # Falcons → OMNIA>Retail Falcons
    5: "12368",   # Guardians → OMNIA>Retail Guardians
    6: "12365",   # Core Cobras → OMNIA>Retail Core Cobra
    7: "-1",      # Wolfpack (old cell) → IGNORE
    8: "12505"    # Regression Squad → UKQA>Omnia
    }
gbs_squad = {
    1: "E Nerds",
    2: "Dream Team",
    3: "Acceptance Team"
}

assigned_squad_team_map = {
    12365: "OMNIA>Retail Core Cobra",   # Core Cobras
    12367: "OMNIA>Retail Falcons",      # Falcons
    12368: "OMNIA>Retail Guardians",    # Guardians
    12369: "OMNIA>Retail Marvels",      # Marvels
    12370: "OMNIA>Retail Mavericks",    # Mavericks
    12371: "OMNIA>Retail Spartans",     # Spartans

    12413: "RGE>Envision-Agni",         # Envision Agni
    12414: "RGE>Envision-Prithvi",      # Envision Prithvi
    12415: "RGE>GBS-DreamTeam",         # Dream Team
    12416: "RGE>GBS-E.Nerds",           # E Nerds
    12417: "RGE>UK Retail Product Design",

    12502: "UKQA>Envision",
    12503: "UKQA>GBS",
    12504: "UKQA>Load Testing",
    12505: "UKQA>Omnia",
    12506: "UKQA>Retail Automation",
    12507: "UKQA>Retail CP",
    12508: "UKQA>Sportbook Automation",
    12509: "UKQA>Sportsbook Regression"
    }
lead_sign_off = {
    "1": "13934",   # Awaiting Lead Review
    "2": "13935",   # Lead reviewed & signed off
    "None": "-1"
}
hard_ware_dependent = {
    "1": "13932",   # Yes
    "2": "13933",   # No
    "None": "-1"
}
