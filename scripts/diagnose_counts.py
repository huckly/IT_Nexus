import requests
import pynetbox
import os
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv('/opt/netbox/scripts/.env')

# Connect to NetBox
nb = pynetbox.api(os.getenv('NETBOX_URL'), token=os.getenv('NETBOX_TOKEN'))
nb.http_session.verify = False 

# Connect to LibreNMS
headers = {'X-Auth-Token': os.getenv('LIBRENMS_TOKEN')}
resp = requests.get(os.getenv('LIBRENMS_URL') + '/devices', headers=headers, verify=False)
libre_data = resp.json().get('devices', [])

# Process Data
libre_devs = { (d.get('sysName') or d.get('hostname') or '').lower(): d for d in libre_data }
nb_devs = list(nb.dcim.devices.all())
nb_names = { (d.name or '').lower() for d in nb_devs }

# Analyze Status
status_counts = {}
for d in nb_devs:
    status = d.status.value if d.status else 'unknown'
    status_counts[status] = status_counts.get(status, 0) + 1

# Find Missing
missing_names = list(set(libre_devs.keys()) - nb_names)
missing_details = [
    {
        'name': name, 
        'libre_id': libre_devs[name].get('device_id'),
        'hardware': libre_devs[name].get('hardware'),
        'os': libre_devs[name].get('os')
    } 
    for name in missing_names
]

# Output
output = {
    'librenms_total': len(libre_devs),
    'netbox_total': len(nb_devs),
    'netbox_status_breakdown': status_counts,
    'missing_in_netbox_count': len(missing_names),
    'missing_devices': missing_details
}

print(json.dumps(output, indent=2))
