xray_priority = {
        4: '1',  # xray:Highest P1 testrail:Critical
        3: '2',  # High P2
        2: '3',  # Medium P3
        1: '4',  # Low P4
        5: 'Lowest',
        10000 : 'Urgent',
        10001: 'Unprioritised'
    }

automation_status = {
        3: '13500',  # xray: "Can't Automate" testrail:Cannot be automated

        1: '13501',  # xray:"Ready For Automation" testrail:Manual

        'Automation In Progress': '13502',

        2: '13503',  # "Automated"

        'Maintenance': 13504,

        'No Automation Required': 13505,
        4: '13500'
    }
df_automation_type = {
    1: '13501', # Manual
    2: '13503', # Automated
    3: '13500', # Cannot be automated
    }

dbt_automation_type = {
        1: "Automation",
        2: "Manual"
    }
omnia_auto_type = {  #Todo
    1: "New",
    2: "Automation Candidate",
    3: '13503', # Automated
    4: '13500', # Cannot Automate
    5: "PR raised yet to merge",
    6: "Automated but descoped/deprecated"
    }
gbs_auto_type = {
    1: '13503', # Automated
    2: '13501', # Manual  # xray:"Ready For Automation"
    3: '13500', # Cannot Automate
    4: "Automation Candidate",
    5: "Automated but descoped/deprecated"
    }
envision_auto_type = {
    1: '13501', # New
    2: "Automation Candidate",
    3: '13503', # Automated
    4: '13500', # Cannot Automate
    5: "Automated but descoped/deprecated"
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
    1: "Marvels",
    3: "Spartans",
    2: "Mavericks",
    4: "Falcons",
    5: "Guardians",
    6: "Core Cobras",
    7: "Wolfpack (old cell)",
    8: "Regression Squad"
    }
gbs_squad = {
    1: "E Nerds",
    2: "Dream Team",
    3: "Acceptance Team"
}

assigned_squad_team_map = {
    10832: "OMNIA>Retail Core Cobra", # Core Cobras
    10833: "OMNIA>Retail Falcons", # Falcons
    10835: "OMNIA>Retail Guardians", # Guardians
    10837: "OMNIA>Retail Marvels", #"Marvels",
    10839: "OMNIA>Retail Mavericks", # Mavericks
    10841: "OMNIA>Retail Spartans", # Spartans

    10824: "RGE&gt;Envision-Agni",
    10826: "RGE&gt;Envision-Prithvi",
    10828: "RGE&gt;GBS-DreamTeam", # Dream Team
    10830: "RGE&gt;GBS-E.Nerds", # E Nerds
    12212: "RGE&gt;UK Retail Product Design",

    12113: "UKQA>Envision",
    12115: "UKQA>GBS", #"Acceptance Team"
    12117: "UKQA>Load Testing",
    12119: "UKQA>Omnia",
    12121: "UKQA>Retail Automation",
    12208: "UKQA>Retail CP",
    12123: "UKQA>Sportbook Automation",
    12125: "UKQA>Sportsbook Regression"
    }

# Legacy payload structure - kept for tracking
# {
#     'step': step_content,
#     'data': "None",
#     'result': expected_result,
#     'attachments': [{
#         'data': base64_encoded_data,
#         'filename': file_name,
#         'contentType': content_type
#     }]
# }# Keep attachment payload for tracking
#                         attachment_payload = {'attachments': [{
#                             'data': encoded_data,
#                             'filename': file_name,
#                             "contentType": "plain/text" #'data:image/png:base64'
#                         }]}