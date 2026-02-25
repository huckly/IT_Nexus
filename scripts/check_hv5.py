import requests
import pynetbox
import os
import json
from dotenv import load_dotenv

# Load environment variables
load_dotenv('/opt/netbox/scripts/.env')

# Connect to NetBox
try:
    nb = pynetbox.api(os.getenv('NETBOX_URL'), token=os.getenv('NETBOX_TOKEN'))
    nb.http_session.verify = False 
    
    # 1. Check by IP
    target_ip = '198.51.100.4'
    ip_obj = nb.ipam.ip_addresses.get(address=target_ip)
    nb_result = {
        'search_ip': target_ip,
        'found': bool(ip_obj),
        'assigned_object': str(ip_obj.assigned_object) if ip_obj else None,
        'status': str(ip_obj.status) if ip_obj else None
    }
except Exception as e:
    nb_result = {'error': str(e)}

# Connect to LibreNMS
try:
    headers = {'X-Auth-Token': os.getenv('LIBRENMS_TOKEN')}
    libre_url = os.getenv('LIBRENMS_URL')
    
    # 2. Check Duplicates [104, 8, 102]
    libre_results = []
    for did in [104, 8, 102]:
        try:
            r = requests.get(f'{libre_url}/devices/{did}', headers=headers, verify=False)
            if r.status_code == 200:
                d = r.json().get('devices', [{}])[0]
                libre_results.append({
                    'id': did,
                    'sysName': d.get('sysName'),
                    'hostname': d.get('hostname'),
                    'status': d.get('status'), # 1=Up, 0=Down
                    'hardware': d.get('hardware'),
                    'ip': d.get('ip')
                })
            else:
                libre_results.append({'id': did, 'error': f"HTTP {r.status_code}"})
        except Exception as e:
            libre_results.append({'id': did, 'error': str(e)})

except Exception as e:
    libre_results = {'error': str(e)}

print(json.dumps({
    'netbox_check': nb_result,
    'librenms_duplicates': libre_results
}, indent=2))
