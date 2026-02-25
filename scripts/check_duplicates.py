import requests
import os
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv('/opt/netbox/scripts/.env')

# Connect to LibreNMS
headers = {'X-Auth-Token': os.getenv('LIBRENMS_TOKEN')}
resp = requests.get(os.getenv('LIBRENMS_URL') + '/devices', headers=headers, verify=False)
libre_data = resp.json().get('devices', [])

raw_count = len(libre_data)
print(f"Raw Device Count from API: {raw_count}")

# Check names
name_map = {}
key_usage = {}

for d in libre_data:
    # Logic used in sync script
    hostname = d.get('sysName') or d.get('hostname')
    
    # Logic if even hostname is missing
    if not hostname:
        hostname = f"Unknown-{d.get('device_id')}"
        
    normalized = hostname.lower()
    
    if normalized in name_map:
        name_map[normalized].append(d.get('device_id'))
    else:
        name_map[normalized] = [d.get('device_id')]

duplicates = {k:v for k,v in name_map.items() if len(v) > 1}

print(json.dumps({
    'total_raw': raw_count,
    'unique_names': len(name_map),
    'duplicates': duplicates
}, indent=2))
