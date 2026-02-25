#!/usr/bin/env python3
# =============================================================================
# sync_librenms_interfaces.py - 同步 Interface 資訊 (v3 - Clean Sync)
# =============================================================================
# 功能：將 LibreNMS 的 實體 Interface 資訊同步至 NetBox。
# 策略：先清除設備上所有 NetBox Interface，再從 LibreNMS 重新建立。
# 預設僅同步實體 Port (Ethernet, GigabitEthernet 等) 和 LAG (Port-Channel)。
#
# 用法：
#   python3 sync_librenms_interfaces.py [--dry-run] [--limit N] [--device NAME]
# =============================================================================

import os
import sys
import argparse
import logging
import json
import pynetbox
import requests
import urllib3
import re
from dotenv import load_dotenv

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Load Env ---
load_dotenv('/opt/netbox/scripts/.env')
LIBRENMS_URL = os.getenv('LIBRENMS_URL', '').rstrip('/')
LIBRENMS_TOKEN = os.getenv('LIBRENMS_TOKEN', '')
NETBOX_URL = os.getenv('NETBOX_URL', '')
NETBOX_TOKEN = os.getenv('NETBOX_TOKEN', '')

HEADERS_LNM = {'X-Auth-Token': LIBRENMS_TOKEN}

# ============================================================================
# 實體介面白名單 (只有符合這些前綴的介面才會同步)
# ============================================================================
PHYSICAL_PREFIXES = (
    # --- Cisco ---
    'Fa', 'Gi', 'Te', 'Fo', 'Tw', 'Hu',
    'FastEthernet', 'GigabitEthernet', 'TenGigabitEthernet',
    'Ethernet', 'Eth',
    'mgmt', 'Management',
    # --- Linux / Generic ---
    'eth', 'ens', 'enp', 'eno', 'em',
    'wlan', 'wl',
    # --- LAG ---
    'Po', 'Port-channel', 'Bond', 'bond', 'ae',
    # --- Fortinet ---
    'port', 'wan', 'dmz', 'internal',
    # --- Aruba / HP ---
    'ge-', 'xe-', 'et-',
)

# 排除清單
SKIP_PATTERNS = [
    'WFP', 'LightWeight Filter', 'WAN Miniport',
    'Microsoft Kernel Debug', 'Pseudo-Interface',
    'isatap', 'Teredo', 'Microsoft ISATAP',
    'Miniport', 'Microsoft Wi-Fi Direct',
    'Hyper-V', 'vSwitch', 'NDIS',
    'Null', 'Nu0',
]


def format_mac(raw_mac):
    """將 LibreNMS MAC 格式轉為 NetBox 格式。
    '001ef609b601' → '00:1E:F6:09:B6:01'
    """
    if not raw_mac:
        return None
    mac = raw_mac.strip().replace(':', '').replace('-', '').replace('.', '')
    if len(mac) != 12 or mac.replace('0', '') == '':
        return None
    return ':'.join(mac[i:i+2] for i in range(0, 12, 2))


def get_librenms_device_map():
    """取得 LibreNMS 所有設備，建立 {sysName: {id, ip}} 對照表。"""
    resp = requests.get(f"{LIBRENMS_URL}/devices", headers=HEADERS_LNM, verify=False, timeout=30)
    resp.raise_for_status()
    dev_map = {}
    for d in resp.json().get('devices', []):
        name = d.get('sysName') or d.get('hostname')
        if name:
            dev_map[name] = {
                'id': d['device_id'],
                'ip': d.get('ip') or d.get('hostname'),
            }
    return dev_map


def get_device_ports(device_id):
    """使用 /devices/:id/ports 端點取得 Port (與 LibreNMS Web UI 一致)。"""
    url = f"{LIBRENMS_URL}/devices/{device_id}/ports?columns=ifName,ifAlias,ifPhysAddress,ifType,ifSpeed,ifMtu,ifOperStatus,ifAdminStatus,ifDescr"
    try:
        resp = requests.get(url, headers=HEADERS_LNM, verify=False, timeout=30)
        data = resp.json()
        if data.get('status') == 'error':
            logger.warning(f"  LibreNMS API Error (ID: {device_id}): {data.get('message')}")
            return []
        return data.get('ports', [])
    except Exception as e:
        logger.error(f"  Failed to fetch ports for ID {device_id}: {e}")
        return []


def is_physical_interface(if_name):
    """判斷是否為實體介面 (白名單機制)。"""
    name = (if_name or '').strip()
    if not name:
        return False
    if any(pat in name for pat in SKIP_PATTERNS):
        return False
    return name.startswith(PHYSICAL_PREFIXES)


def map_interface_type(if_name, speed_bps):
    """根據介面名稱與速率判斷 NetBox Interface Type。"""
    name = (if_name or '').strip()

    # LAG
    if name.startswith(('Po', 'Port-channel', 'Bond', 'bond', 'ae')):
        return 'lag'

    # 根據速率判斷
    speed = int(speed_bps or 0)
    if speed >= 100000000000: return '100gbase-x-qsfp28'
    if speed >= 40000000000:  return '40gbase-x-qsfpp'
    if speed >= 25000000000:  return '25gbase-x-sfp28'
    if speed >= 10000000000:  return '10gbase-t'
    if speed >= 1000000000:   return '1000base-t'
    if speed >= 10000000:     return '100base-tx'
    if speed == 0:            return 'other'
    return 'other'


def clean_device_interfaces(nb, device_id, device_name):
    """清除設備上所有現有的 Interfaces。"""
    existing = list(nb.dcim.interfaces.filter(device_id=device_id))
    if not existing:
        return 0
    count = 0
    for iface in existing:
        try:
            iface.delete()
            count += 1
        except Exception as e:
            logger.error(f"  ❌ 刪除失敗 {iface.name}: {e}")
    logger.info(f"  🗑 已清除 {count} 個舊 Interface")
    return count


def main():
    parser = argparse.ArgumentParser(description='Sync LibreNMS Interfaces to NetBox (v3 Clean Sync)')
    parser.add_argument('--dry-run', action='store_true', help="只顯示預計同步的內容，不寫入")
    parser.add_argument('--limit', type=int, default=0, help="限制處理的設備數量 (0=全部)")
    parser.add_argument('--device', type=str, default='', help="只處理指定設備 (hostname)")
    args = parser.parse_args()

    if not all([LIBRENMS_URL, LIBRENMS_TOKEN, NETBOX_URL, NETBOX_TOKEN]):
        logger.error("缺少必要環境變數 (LIBRENMS_URL/TOKEN, NETBOX_URL/TOKEN)")
        sys.exit(1)

    nb = pynetbox.api(NETBOX_URL, token=NETBOX_TOKEN)
    nb.http_session.verify = False

    logger.info("=== 開始同步 Interfaces (v3 Clean Sync) ===")
    logger.info("策略: 清除舊 Interface → 從 LibreNMS 重建 (僅實體 Port)")

    # 1. Build LibreNMS Map
    librenms_map = get_librenms_device_map()
    logger.info(f"LibreNMS: {len(librenms_map)} 台設備")

    # 2. Get NetBox Devices
    nb_devices = list(nb.dcim.devices.filter(status='active'))
    logger.info(f"NetBox: {len(nb_devices)} 台 Active 設備")

    stats = {
        'devices_processed': 0,
        'interfaces_created': 0,
        'interfaces_cleaned': 0,
        'interfaces_skipped': 0,
        'errors': 0,
    }

    for nb_dev in nb_devices:
        if args.limit > 0 and stats['devices_processed'] >= args.limit:
            break

        # 指定設備模式
        if args.device and nb_dev.name != args.device:
            continue

        dev_info = librenms_map.get(nb_dev.name)
        if not dev_info:
            continue

        lid = dev_info['id']
        dev_ip = dev_info.get('ip')

        logger.info(f"📡 {nb_dev.name} (LibreNMS ID: {lid}, IP: {dev_ip}, NetBox ID: {nb_dev.id})")

        # 取得 LibreNMS Ports
        ports = get_device_ports(lid)
        if not ports:
            logger.info(f"  ⏭ 無 Port 資料")
            continue

        # 過濾：僅保留實體介面
        valid_ports = [p for p in ports if p.get('ifName') and is_physical_interface(p['ifName'])]
        skipped = len(ports) - len(valid_ports)
        stats['interfaces_skipped'] += skipped

        logger.info(f"  LibreNMS 回傳 {len(ports)} 個 Port, 過濾後 {len(valid_ports)} 個實體介面 (跳過 {skipped})")

        stats['devices_processed'] += 1

        if args.dry_run:
            for p in valid_ports:
                name = p.get('ifName', '?')
                speed = p.get('ifSpeed', 0)
                mac = p.get('ifPhysAddress') or 'N/A'
                t = map_interface_type(name, speed)
                enabled = str(p.get('ifAdminStatus', '')).lower() == 'up'
                print(f"    {name:35s} | Type: {t:15s} | MAC: {mac:20s} | Enabled: {enabled}")
            continue

        # === Clean Sync: 先刪除, 再建立 ===
        cleaned = clean_device_interfaces(nb, nb_dev.id, nb_dev.name)
        stats['interfaces_cleaned'] += cleaned

        # 建立新的 Interfaces
        for p in valid_ports:
            if_name = (p.get('ifName') or '').strip()
            if not if_name:
                continue

            # 截斷 (NetBox 限制 64 字元)
            if len(if_name) > 64:
                if_name = if_name[:64]

            mac = format_mac(p.get('ifPhysAddress'))

            mtu = p.get('ifMtu')
            speed = p.get('ifSpeed', 0)
            enabled = str(p.get('ifAdminStatus', '')).lower() == 'up'
            description = p.get('ifAlias') or p.get('ifDescr') or ''
            type_slug = map_interface_type(if_name, speed)

            try:
                payload = {
                    'device': nb_dev.id,
                    'name': if_name,
                    'type': type_slug,
                    'enabled': enabled,
                }
                if mtu: payload['mtu'] = int(mtu)
                if description: payload['description'] = description[:200]

                new_if = nb.dcim.interfaces.create(payload)
                stats['interfaces_created'] += 1

                # NetBox v4.2+: MAC Address 為獨立物件
                if mac:
                    try:
                        mac_obj = nb.dcim.mac_addresses.create(
                            mac_address=mac,
                            assigned_object_type='dcim.interface',
                            assigned_object_id=new_if.id,
                        )
                        # 設定為 Primary MAC
                        new_if.update({'primary_mac_address': mac_obj.id})
                    except Exception as mac_err:
                        logger.warning(f"    ⚠ {if_name} MAC 寫入失敗: {mac_err}")

            except Exception as e:
                logger.error(f"    ❌ {if_name}: {e}")
                stats['errors'] += 1

        # === 設備 IP 同步 ===
        if dev_ip and not args.dry_run:
            # 驗證 IP 格式 (排除 hostname)
            if not re.match(r'^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$', str(dev_ip)):
                logger.warning(f"  ⚠ IP '{dev_ip}' 不是有效 IPv4 格式，跳過")
            else:
                try:
                    # 找介面 (優先用已存在的介面)
                    mgmt_if = nb.dcim.interfaces.get(device_id=nb_dev.id, name='Management')
                    if not mgmt_if:
                        mgmt_if = nb.dcim.interfaces.get(device_id=nb_dev.id, name='Gi0/1')
                    if not mgmt_if:
                        mgmt_if = nb.dcim.interfaces.get(device_id=nb_dev.id, name='Fa0/1')
                    if not mgmt_if:
                        all_ifs = list(nb.dcim.interfaces.filter(device_id=nb_dev.id))
                        mgmt_if = all_ifs[0] if all_ifs else None

                    # 若設備無任何 Interface，建立一個 Management 介面
                    if not mgmt_if:
                        mgmt_if = nb.dcim.interfaces.create(
                            device=nb_dev.id,
                            name='Management',
                            type='virtual',
                            description='Auto-created for IP assignment',
                        )
                        logger.info(f"  📎 已建立 Management 虛擬介面")

                    # 檢查 IP 是否已存在
                    ip_addr = f"{dev_ip}/32"
                    existing_ip = nb.ipam.ip_addresses.get(address=dev_ip)

                    if existing_ip:
                        # 更新綁定
                        existing_ip.assigned_object_type = 'dcim.interface'
                        existing_ip.assigned_object_id = mgmt_if.id
                        existing_ip.save()
                        ip_id = existing_ip.id
                    else:
                        # 建立新 IP
                        new_ip = nb.ipam.ip_addresses.create(
                            address=ip_addr,
                            assigned_object_type='dcim.interface',
                            assigned_object_id=mgmt_if.id,
                            description=f'Management IP ({nb_dev.name})',
                        )
                        ip_id = new_ip.id

                    # 設定 Primary IPv4
                    if not nb_dev.primary_ip4 or str(nb_dev.primary_ip4) != dev_ip:
                        nb_dev.update({'primary_ip4': ip_id})
                        logger.info(f"  🌐 已設定 Primary IPv4: {dev_ip}")
                    stats['ips_synced'] = stats.get('ips_synced', 0) + 1
                except Exception as e:
                    logger.error(f"  ❌ IP 同步失敗 ({dev_ip}): {e}")

    logger.info("=== 同步完成 ===")
    logger.info(f"統計: 設備={stats['devices_processed']}, "
                f"清除={stats['interfaces_cleaned']}, "
                f"新建={stats['interfaces_created']}, "
                f"跳過={stats['interfaces_skipped']}, "
                f"IP={stats.get('ips_synced', 0)}, "
                f"錯誤={stats['errors']}")


if __name__ == "__main__":
    main()
