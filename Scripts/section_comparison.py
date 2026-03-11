from xray.xray_client import XrayClient

xray = XrayClient()

sections = xray.get_all_sections(section=22182)