import requests
import os
import json
from dotenv import load_dotenv

# Load environment variables
# Load environment variables
# load_dotenv('/opt/netbox/scripts/.env') # Permission denied for mis1

headers = {'X-Auth-Token': '3a8867568f635677054f1642220970a8'}
base_url = 'http://198.51.100.1/api/v0'
dev_id = 27 # xz-7f-3850-core

data = {}

# 1. Device Core Info
try:
    r = requests.get(f'{base_url}/devices/{dev_id}', headers=headers, verify=False)
    # The API returns {'devices': [{...}]}
    data['device'] = r.json().get('devices', [{}])[0]
except Exception as e:
    data['device'] = str(e)

# 2. Sub-resources
endpoints = ['ports', 'inventory', 'ip', 'vlans']
for ep in endpoints:
    try:
        r = requests.get(f'{base_url}/devices/{dev_id}/{ep}', headers=headers, verify=False)
        # Some endpoints return {endpoint: [...]}, others might differ
        json_resp = r.json()
        
        # Handle list vs dict response
        if ep in json_resp:
            items = json_resp[ep]
        elif 'devices' in json_resp: # sometimes rare endpoints wrap in devices? unlikely for sub-resource
            items = json_resp['devices']
        else:
            items = json_resp
            
        # Limit ports output to first 3 to avoid huge JSON
        if ep == 'ports' and isinstance(items, list):
            data[ep] = items[:3]
            data[ep+'_count'] = len(items)
        else:
            data[ep] = items
            
    except Exception as e:
        data[ep] = f"Error: {str(e)}"

print(json.dumps(data, indent=2))
