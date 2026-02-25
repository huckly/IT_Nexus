
import os
import json
import requests
from dotenv import load_dotenv

# Load environment variables
load_dotenv('/opt/netbox/scripts/.env')

headers = {'X-Auth-Token': os.getenv('LIBRENMS_TOKEN')}
base_url = os.getenv('LIBRENMS_URL')
dev_id = 27 # xz-7f-3850-core


try:
    print(f"--- ATTEMPT 4: Find Port with VLAN Data ---")
    cols = "port_id,ifName,ifPhysAddress,ifVlan,ifTrunk,ifType"
    resp = requests.get(f"{base_url}/devices/{dev_id}/ports", params={'columns': cols}, headers=headers, verify=False, timeout=10)
    data = resp.json()
    ports = data.get('ports', [])
    print(f"Found {len(ports)} ports via Columns.")
    
    found_vlan = False
    for p in ports:
        if p.get('ifVlan') or p.get('ifTrunk'):
             print("--- MATCH FOUND (Has VLAN Data) ---")
             print(json.dumps(p, indent=2))
             found_vlan = True
             break
             
    if not found_vlan:
        print("--- NO PORTS WITH VLAN DATA FOUND ---")
        # Dump a few random ones just to be sure
        if ports:
            print("First 3 ports:")
            print(json.dumps(ports[:3], indent=2))

except Exception as e:
    print(f"Error: {e}")


