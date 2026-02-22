#!/usr/bin/env python3
# =============================================================================
# sync_librenms_to_netbox.py - IT Nexus v6.0 Comprehensive Data Sync
# 用途：從 LibreNMS 同步設備至 NetBox (Source of Truth)
# v6.0 功能：
#   1. **Interface Sync**: 全面同步 Ports, MAC, Description
#   2. **IP Address Sync**: 全面同步 IP 並自動綁定 Interface
#   3. **Inventory Sync**: 同步硬體組件 (Power, Fan, Modules)
#   4. **Location Sync**: 自動對應 sysLocation 至 Site
#   5. **Robustness**: 針對 API 500/404 錯誤的自動容錯機制
# =============================================================================

import os
import sys
import pynetbox
import re
from slugify import slugify
from dotenv import load_dotenv

from utils import setup_logging, save_metrics, request_with_retry, get_env_var

ENV_PATH = '/opt/netbox/scripts/.env'
load_dotenv(ENV_PATH)

logger = setup_logging('/var/log/it_nexus/sync_librenms.log')

RETRY_COUNT = int(get_env_var('RETRY_COUNT', '3'))
METRICS_FILE = get_env_var('METRICS_FILE_LIBRENMS', '/var/log/it_nexus/metrics_librenms.json')

MANUFACTURER_MAP = {
    'ios': 'Cisco', 'iosxe': 'Cisco', 'nxos': 'Cisco',
    'routeros': 'MikroTik', 
    'fortigate': 'Fortinet',
    'fortios': 'Fortinet', 'synology': 'Synology',
    'panos': 'Palo Alto', 'junos': 'Juniper',
    'arubaos': 'HPE Aruba', 'vmware': 'VMware',
    'vmware-esxi': 'VMware', 'powerwalker': 'BlueWalker',
}

def sanitize_string(text):
    """清理亂碼 (Mojibake) 並替換為可讀名稱，特別針對 Hyper-V 模式。"""
    if not text: return text
    
    # 移除不可見字元 (如 Null, Bell 等)
    text = "".join(char for char in text if char.isprintable())
    
    # 模式匹配與替換
    # 1. Hyper-V 虛擬網卡: 包含 'Hyper-V' 且帶有特定亂碼特徵 (如 Ӻ)
    # 範例: Hyper-V ?????A?Ӻ????????d #2
    if 'Hyper-V' in text and ('?' in text or '\u04fa' in text or '\u6d33' in text or '\ufffd' in text):
        # 提取結尾的 #N 序號
        num_match = re.search(r'#(\d+)', text)
        suffix = f" #{num_match.group(1)}" if num_match else ""
        
        # 提取過濾器後綴 (如 -WFP ..., -Microsoft ...) 以防止重複名稱
        filter_match = re.search(r'-(WFP|Microsoft|NDIS|Load|Failover).*$', text)
        filter_suffix = filter_match.group(0) if filter_match else ""
        
        # 根據特徵字元辨識類型
        if any(c.lower() in text.lower() for c in ['adapter', 'ethernet', '\u04fa', '\u04fb']): 
            return f"Hyper-V Virtual Ethernet Adapter{suffix}{filter_suffix}"
        if any(c.lower() in text.lower() for c in ['switch', 'vswitch', '\u6d3b', '\u6d33']): 
            return f"Hyper-V Virtual Switch{suffix}{filter_suffix}"
            
    # 如果包含過多問號且有 Hyper-V 字樣，嘗試歸類為 Network Adapter
    if 'Hyper-V' in text and text.count('?') > 2:
        num_match = re.search(r'#(\d+)', text)
        suffix = f" #{num_match.group(1)}" if num_match else ""
        return f"Hyper-V Network Adapter{suffix}"

    return text.strip()

def format_mac(mac):
    """將任何格式的 MAC 位址轉換為 NetBox 要求的 XX:XX:XX:XX:XX:XX 格式。"""
    if not mac: return None
    # 只保留 16 進位字元
    clean_mac = re.sub(r'[^0-9a-fA-F]', '', mac)
    if len(clean_mac) != 12: return mac # 格式不對則回傳原始值，讓後端決定是否報錯
    
    # 每兩位插入分號並轉大寫
    return ":".join(clean_mac[i:i+2].upper() for i in range(0, 12, 2))

def normalize_slug(text):
    """確保 slug 合法且不為空。"""
    slug = slugify(text)
    if not slug:
        slug = f"unknown-{abs(hash(text))}" # Fallback
    return slug

def get_manufacturer_name(device: dict) -> str:
    """強化版廠商判斷邏輯"""
    os_type = (device.get('os') or '').lower()
    hardware = (device.get('hardware') or 'Unknown').lower()
    
    # 優先查表 (Network Devices)
    if os_type in MANUFACTURER_MAP:
        return MANUFACTURER_MAP[os_type]
    
    # 特殊硬體判斷
    if 'vmware' in hardware or 'esxi' in hardware: return 'VMware'
    if 'qemu' in hardware or 'kvm' in hardware: return 'QEMU'
    # Windows/Linux: 依靠 Hardware 欄位
    
    # 預設回傳 hardware 的第一個單字 (例如 "HP ProLiant" -> "HP")
    if device.get('hardware'):
        return device.get('hardware').split(' ')[0]
        
    return 'Generic'

def get_or_create_platform(nb, manufacturer_name, os_name, version, dry_run=False):
    """取得或建立 Platform (OS Version)"""
    if not os_name: return None
    
    # 判斷 Platform 顯示名稱
    os_lower = os_name.lower()
    # 寬鬆比對：只要包含以下關鍵字就視為通用/Global OS
    keywords = ['windows', 'linux', 'unix', 'freebsd', 'ubuntu', 'centos', 'debian', 'vmware', 'generic', 'unknown', 'powerwalker', 'ping']
    is_generic_os = any(k in os_lower for k in keywords)

    logger.debug(f"  [Platform Check] OS='{os_name}', IsGeneric={is_generic_os}")

    if is_generic_os:
        # 對於通用 OS，手動指定完整的 Pretty Name
        if 'windows' in os_lower:       full_name = "Microsoft Windows"
        elif 'linux' in os_lower:       full_name = "Linux"
        elif 'vmware' in os_lower:      full_name = "VMware ESXi"
        else:                           full_name = os_name
    else:
        # Network OS 通常包含廠商名 (e.g. "Cisco IOS")
        full_name = f"{manufacturer_name} {os_name}"
        
    if version:
        full_name += f" {version}"
        
    slug = normalize_slug(full_name)
    
    try:
        platform = nb.dcim.platforms.get(slug=slug)
        
        # 關鍵修正: 通用 OS (Windows/Linux) 不綁定 Manufacturer
        mfr_id = None
        if not is_generic_os:
            mfr_slug = normalize_slug(manufacturer_name)
            mfr = nb.dcim.manufacturers.get(slug=mfr_slug)
            if mfr: mfr_id = mfr.id

        if not platform and not dry_run:
            logger.info(f"  [Auto-Create] 建立 Platform: {full_name} (Global={is_generic_os})")
            platform = nb.dcim.platforms.create(
                name=full_name, 
                slug=slug, 
                manufacturer=mfr_id 
            )
        elif platform and not dry_run and is_generic_os:
             # 若已存在且為通用 OS -> 強制檢查並解除廠商綁定
             # 注意：pynetbox 回傳的 platform.manufacturer 可能是 Record(id=...) 或 ID(int) 或 None
             mfr_val = platform.manufacturer
             has_mfr = False
             if hasattr(mfr_val, 'id'): has_mfr = True # Record
             elif isinstance(mfr_val, int): has_mfr = True # ID
             
             if has_mfr:
                 logger.info(f"  [Fix Platform] 解除 {full_name} 的廠商綁定 (設為 Global)")
                 platform.manufacturer = None
                 platform.save()

        return platform
    except Exception as e:
        logger.warning(f"  ⚠ 無法處理 Platform {full_name}: {e}")
        return None

def get_or_create_site(nb, location_name, dry_run=False):
    """取得或建立 Site"""
    if not location_name: return None
    slug = normalize_slug(location_name)
    
    try:
        site = nb.dcim.sites.get(slug=slug)
        if not site and not dry_run:
            logger.info(f"  [Auto-Create] 建立 Site: {location_name}")
            site = nb.dcim.sites.create(name=location_name, slug=slug, status='active')
        return site
    except Exception as e:
        logger.warning(f"  ⚠ 無法處理 Site {location_name}: {e}")
        return None

def sync_detailed_data(nb, nb_device, librenms_url, librenms_token, libre_dev_id, dry_run=False):
    """v6.0 全面同步：Interface, IP, Inventory"""
    # if dry_run: return  <-- allow dry run to proceed

    headers = {'X-Auth-Token': librenms_token}
    
    
    # 1. Sync VLANs (Priority: High, needed for Interface binding)
    vlan_map = {} # VID -> VLAN Object
    try:
        try:
            resp = request_with_retry('GET', f"{librenms_url}/devices/{libre_dev_id}/vlans", headers=headers, retry_count=1, logger=logger)
        except Exception: resp = None

        vlans = resp.json().get('vlans', []) if resp and resp.status_code == 200 else []
        
        # 取得現有 VLANs (Site Scope)
        if nb_device.site:
            site_vlans = {v.vid: v for v in nb.ipam.vlans.filter(site_id=nb_device.site.id)}
            # logger.debug(f"  [VLAN] Site '{nb_device.site.name}' has {len(site_vlans)} existing VLANs. LibreNMS has {len(vlans)}.")

            for v in vlans:
                try:
                    vid = int(v.get('vlan_vlan'))
                    if vid > 4094: continue # NetBox standard VID limit
                except (ValueError, TypeError): continue
                
                name = v.get('vlan_name') 
                
                if not vid or not name: continue
                if vid in [1002, 1003, 1004, 1005] and v.get('vlan_type') != 'ethernet': continue
                
                status = 'active'
                
                if vid in site_vlans:
                    # Update
                    nb_vlan = site_vlans[vid]
                    vlan_map[vid] = nb_vlan
                    if nb_vlan.name != name:
                         if not dry_run:
                             nb_vlan.name = name
                             nb_vlan.save()
                             logger.info(f"  [VLAN] 更新 VLAN {vid} 名稱: {nb_vlan.name} -> {name}")
                         else:
                             logger.info(f"  [Dry-Run] Would Update VLAN {vid} Name: {nb_vlan.name} -> {name}")
                else:
                    # Create
                    try:
                        if not dry_run:
                            new_vlan = nb.ipam.vlans.create(site=nb_device.site.id, vid=vid, name=name, status=status)
                            logger.info(f"  [VLAN] 新增 VLAN: {vid} ({name})")
                            vlan_map[vid] = new_vlan
                        else:
                            logger.info(f"  [Dry-Run] Would Create VLAN: {vid} ({name})")
                    except Exception as e:
                        logger.warning(f"  ⚠ 建立 VLAN {vid} 失敗: {e}")
            
            logger.info(f"  [VLAN] Synced {len(vlans)} VLANs (Site: {nb_device.site.name})")
        else:
             logger.warning(f"  ⚠ 設備 {nb_device.name} 未指定 Site，無法同步 VLAN (需 Site Scope)")
        
    except Exception as e:
        logger.debug(f"  ℹ 同步 VLAN 失敗: {e}")

    # 2. Sync Interfaces
    # 建立 LibreNMS Port ID -> NetBox Interface ID 對照表
    port_id_map = {} 
    
    try:
        logger.debug(f"  [Detail] Fetching ports for Device ID {libre_dev_id}...")
        try:
            # Request specific columns to Ensure we get VLAN data
            cols = "port_id,ifName,ifPhysAddress,ifAlias,ifAdminStatus,ifSpeed,ifVlan,ifTrunk,ifType"
            resp = request_with_retry('GET', f"{librenms_url}/devices/{libre_dev_id}/ports", headers=headers, params={'columns': cols}, retry_count=1, logger=logger)
        except Exception: resp = None
        
        ports = resp.json().get('ports', []) if resp and resp.status_code == 200 else []
        logger.debug(f"  [Detail] Found {len(ports)} ports.")
        
        # 取得現有介面以避免重複呼叫
        nb_interfaces = {i.name: i for i in nb.dcim.interfaces.filter(device_id=nb_device.id)}
        
        for port in ports:
            if_name = port.get('ifName')
            port_id = port.get('port_id')
            if not if_name or not port_id: continue
            
            # 應用亂碼過濾與 MAC 格式化
            clean_if_name = sanitize_string(if_name)
            clean_alias = sanitize_string(port.get('ifAlias') or '')
            formatted_mac = format_mac(port.get('ifPhysAddress'))

            # 對應欄位
            data = {
                'device': nb_device.id,
                'name': clean_if_name,
                'type': '1000base-t', # 預設
                'description': clean_alias,
                'enabled': port.get('ifAdminStatus') == 'up'
            }
            
            # NetBox < 4.0 支援直接寫入 mac_address
            try:
                if float(nb.version[:3]) < 4.0:
                    data['mac_address'] = formatted_mac
            except: pass
            
            # VLAN Binding Logic
            try:
                if_vlan_id = int(port.get('ifVlan')) if port.get('ifVlan') else None
            except ValueError: if_vlan_id = None
            
            if_trunk_ids = port.get('ifTrunk')    # Trunk VLAN IDs

            # Determine Mode & VLANs
            mode = None
            untagged_vlan = None
            tagged_vlans = []

            # Access VLAN
            if if_vlan_id and if_vlan_id in vlan_map:
                untagged_vlan = vlan_map[if_vlan_id].id
                mode = 'access'

            
            # Trunk VLANs
            if if_trunk_ids:
                mode = 'tagged'
                if isinstance(if_trunk_ids, str):
                    trunk_vids = [int(v.strip()) for v in if_trunk_ids.split(',') if v.strip().isdigit()]
                elif isinstance(if_trunk_ids, list):
                    trunk_vids = [int(v) for v in if_trunk_ids if isinstance(v, (int, str)) and str(v).isdigit()]
                else: 
                    trunk_vids = []
                
                for vid in trunk_vids:
                    if vid in vlan_map:
                        tagged_vlans.append(vlan_map[vid].id)

            if mode:
                data['mode'] = mode
            if untagged_vlan:
                data['untagged_vlan'] = untagged_vlan
            if tagged_vlans:
                data['tagged_vlans'] = tagged_vlans

            # 簡單的 Type 對應邏輯
            speed = port.get('ifSpeed') or 0
            if speed >= 10000000000: data['type'] = '10gbase-t'
            elif speed >= 1000000000: data['type'] = '1000base-t'
            elif speed >= 100000000:  data['type'] = '100base-tx'
            elif 'vlan' in if_name.lower(): data['type'] = 'virtual'
            
            # 檢查是否存在 (優先檢查原始名稱，再檢查清洗後的名稱以支援更名更新)
            nb_int = nb_interfaces.get(if_name) or nb_interfaces.get(clean_if_name)

            if nb_int:
                # Update Existing Interface
                port_id_map[port_id] = nb_int
                
                update_needed = False
                if clean_if_name != nb_int.name: update_needed = True
                if clean_alias != nb_int.description: update_needed = True
                if mode and nb_int.mode != mode: update_needed = True
                if untagged_vlan and nb_int.untagged_vlan and nb_int.untagged_vlan.id != untagged_vlan: update_needed = True
                if not nb_int.untagged_vlan and untagged_vlan: update_needed = True
                
                # MAC 檢查 (版本差異)
                is_nb4 = False
                try: is_nb4 = float(nb.version[:3]) >= 4.0
                except: pass

                if formatted_mac:
                    if is_nb4:
                        # 4.0+ 檢查 mac_addresses 列表
                        current_macs = [str(m).upper() for m in nb_int.mac_addresses]
                        if formatted_mac.upper() not in current_macs:
                            update_needed = True
                    else:
                        # < 4.0 檢查單一欄位
                        if nb_int.mac_address != formatted_mac:
                            update_needed = True
                
                if update_needed:
                     if not dry_run:
                        nb_int.name = clean_if_name
                        nb_int.description = clean_alias
                        nb_int.mode = mode
                        if not is_nb4:
                            nb_int.mac_address = formatted_mac
                        if untagged_vlan: nb_int.untagged_vlan = untagged_vlan
                        if tagged_vlans: nb_int.tagged_vlans = tagged_vlans
                        nb_int.save()
                        
                        # NetBox 4.0+ 特殊處理: 建立 MACAddress 關聯
                        if is_nb4 and formatted_mac:
                            try:
                                # 檢查此介面是否已有此 MAC
                                existing_macs = nb.dcim.mac_addresses.filter(
                                    mac_address=formatted_mac,
                                    assigned_object_type='dcim.interface',
                                    assigned_object_id=nb_int.id
                                )
                                if not list(existing_macs):
                                    # 建立新紀錄並連結
                                    nb.dcim.mac_addresses.create(
                                        mac_address=formatted_mac,
                                        assigned_object_type='dcim.interface',
                                        assigned_object_id=nb_int.id
                                    )
                                    logger.info(f"  [MAC] 已連結 {formatted_mac} 到介面")
                            except Exception as e:
                                logger.warning(f"  ⚠ 無法建立 MAC 關聯 ({formatted_mac}): {e}")

                        logger.info(f"  [Interface] 更新完成: {clean_if_name}")
                     else:
                        mac_status = ""
                        if formatted_mac:
                            if is_nb4:
                                current_macs = [str(m).upper() for m in nb_int.mac_addresses]
                                if formatted_mac.upper() not in current_macs:
                                    mac_status = f"MAC (4.x): Add {formatted_mac}"
                            else:
                                if nb_int.mac_address != formatted_mac:
                                    mac_status = f"MAC: {nb_int.mac_address} -> {formatted_mac}"
                        
                        logger.info(f"  [Dry-Run] Would Update Interface {if_name} -> {clean_if_name} (Mode={mode}, {mac_status})")

            else:
                try:
                    if not dry_run:
                        logger.info(f"  [Auto-Create] 建立介面: {clean_if_name}")
                        new_int = nb.dcim.interfaces.create(**data)
                        port_id_map[port_id] = new_int
                    else:
                        logger.info(f"  [Dry-Run] Would Create Interface: {clean_if_name}")
                except Exception as e:
                    logger.warning(f"  ⚠ 建立介面失敗 {clean_if_name}: {e}")

    except Exception as e:
        logger.debug(f"  ℹ 同步介面失敗 (可能無 Ports 資料): {e}")

    # 3. Sync Inventory
    try:
        try:
             # Use /inventory/{id}/all instead of /devices/{id}/inventory to avoid 500 errors
            resp = request_with_retry('GET', f"{librenms_url}/inventory/{libre_dev_id}/all", headers=headers, retry_count=1, logger=logger)
        except Exception as e:
             logger.warning(f"  ⚠ 取得 Inventory 失敗 (Device ID {libre_dev_id}): {e}")
             resp = None

        inventory = resp.json().get('inventory', []) if resp and resp.status_code == 200 else []

        # 取得現有 Inventory
        nb_inventory = {i.name: i for i in nb.dcim.inventory_items.filter(device_id=nb_device.id)}
        
        for item in inventory:
            # 簡化名稱
            safe_name = item.get('entPhysicalName') or item.get('entPhysicalDescr') or 'Unknown'
            part_id = item.get('entPhysicalModelName')
            serial = item.get('entPhysicalSerialNum')
            
            if not part_id or not serial: continue # 略過無意義資料
            
            if safe_name not in nb_inventory:
                 # Create
                 try:
                     if not dry_run:
                         nb.dcim.inventory_items.create(
                             device=nb_device.id,
                             name=safe_name,
                             part_id=part_id,
                             serial=serial,
                             manufacturer=None # 難以對應，先留空
                         )
                         logger.info(f"  [Inventory] 新增組件: {safe_name}")
                     else:
                         logger.info(f"  [Dry-Run] Would Add Inventory: {safe_name} (S/N: {serial})")
                 except Exception as e:
                     pass
                     
    except Exception as e:
        logger.debug(f"  ℹ 同步 Inventory 失敗: {e}")

def update_primary_ip(nb, nb_device, ip_address, dry_run=False):
    """更新設備 IP 位址 (包含建立 Interface)"""
    if not ip_address: return

    try:
        # 1. 檢查/建立 IP Address 物件
        ip_obj = nb.ipam.ip_addresses.get(address=ip_address)
        if not ip_obj:
            if not dry_run:
                logger.info(f"  [Auto-Create] 建立 IP: {ip_address}/32")
                ip_obj = nb.ipam.ip_addresses.create(address=f"{ip_address}/32", status='active')
            else:
                logger.info(f"  [Dry-Run] Would Create IP: {ip_address}/32")
                return # 無法繼續綁定
            
        # 2. 檢查設備是否有 Interface
        interface_name = 'Management'
        interface = nb.dcim.interfaces.get(device_id=nb_device.id, name=interface_name)
        
        if not interface:
            if not dry_run:
                logger.info(f"  [Auto-Create] 建立介面: {interface_name}")
                interface = nb.dcim.interfaces.create(
                    device=nb_device.id, 
                    name=interface_name, 
                    type='virtual'
                )
            else:
                logger.info(f"  [Dry-Run] Would Create Interface: {interface_name}")
                return
            
        # 3. 將 IP 綁定到介面 (若尚未綁定)
        if ip_obj.assigned_object_id != interface.id:
            if not dry_run:
                logger.info(f"  [IP Bind] 綁定 {ip_address} -> {interface_name}")
                ip_obj.assigned_object_type = 'dcim.interface'
                ip_obj.assigned_object_id = interface.id
                ip_obj.save()
            else:
                logger.info(f"  [Dry-Run] Would Bind IP {ip_address} -> {interface_name}")
            
        # 4.設定為設備 Primary IP
        # 注意: pynetbox 的 primary_ip 可能是物件或 None
        current_ip = nb_device.primary_ip.address.split('/')[0] if nb_device.primary_ip else None
        
        if current_ip != ip_address:
             if not dry_run:
                 logger.info(f"  [Primary IP] 設定 {ip_address} 為 Primary IP")
                 nb_device.primary_ip4 = ip_obj.id
                 nb_device.save()
             else:
                 logger.info(f"  [Dry-Run] Would Set Primary IP to {ip_address}")
              
    except Exception as e:
        logger.error(f"  ❌ 設定 IP 失敗 ({ip_address}): {e}")

def main():
    logger.info("=" * 60)
    logger.info(">>> 開始同步 (v6.0): LibreNMS -> NetBox (Comprehensive Sync)")
    logger.info("=" * 60)

    dry_run = get_env_var('DRY_RUN', 'False').lower() == 'true'
    auto_create = get_env_var('AUTO_CREATE_NEW', 'True').lower() == 'true'
    
    if dry_run: logger.warning("⚠ DRY-RUN 模式啟用")

    # --- Argument Parsing ---
    import argparse
    parser = argparse.ArgumentParser(description='Sync LibreNMS to NetBox')
    parser.add_argument('--device', help='Sync specific device by hostname')
    parser.add_argument('--dry-run', action='store_true', help='Simulate changes')
    args = parser.parse_args()

    target_device = args.device
    if args.dry_run:
        dry_run = True
        logger.warning("⚠ DRY-RUN 模式啟用 (via CLI)")

    if target_device:
        auto_create = True
        logger.info(f"🎯 指定同步設備: {target_device} (強制 Auto-Create)")

    stats = {'created': 0, 'updated': 0, 'decommissioned': 0, 'recovered': 0, 'skipped': 0, 'failed': 0}

    # --- API 本體 ---
    try:
        import requests as req_lib
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        nb = pynetbox.api(get_env_var('NETBOX_URL', required=True), token=get_env_var('NETBOX_TOKEN', required=True))
        nb.http_session.verify = False 
        
        librenms_url = get_env_var('LIBRENMS_URL', required=True)
        librenms_token = get_env_var('LIBRENMS_TOKEN', required=True)
    except SystemExit:
        sys.exit(1)
    except Exception as e:
        logger.error(f"API 初始化失敗: {e}")
        sys.exit(1)

    # --- Fetch ---
    try:
        headers = {'X-Auth-Token': librenms_token}
        resp = request_with_retry('GET', f"{librenms_url}/devices", headers=headers, retry_count=RETRY_COUNT, logger=logger)
        librenms_devices = resp.json().get('devices', [])
        
        if target_device:
            librenms_devices = [d for d in librenms_devices if 
                                str(target_device) == str(d.get('device_id')) or
                                target_device.lower() == (d.get('sysName') or '').lower() or 
                                target_device.lower() == (d.get('hostname') or '').lower() or
                                target_device.lower() in (d.get('sysName') or '').lower() or 
                                target_device.lower() in (d.get('hostname') or '').lower()]
            # If multiple matches found but one is an exact ID or Name match, prioritize it
            exact_matches = [d for d in librenms_devices if 
                             str(target_device) == str(d.get('device_id')) or
                             target_device.lower() == (d.get('sysName') or '').lower() or 
                             target_device.lower() == (d.get('hostname') or '').lower()]
            if exact_matches:
                librenms_devices = exact_matches

        logger.info(f"從 LibreNMS 取得 {len(librenms_devices)} 台設備")
    except Exception as e:
        logger.error(f"取得 LibreNMS 設備列表失敗: {e}")
        sys.exit(1)

    # --- Role Helper ---
    role_cache = {}
    def ensure_role(slug):
        if slug in role_cache: return role_cache[slug]
        role_defs = {
            'printer': {'name': 'Printer', 'color': '9e9e9e'},
            'access-point': {'name': 'Access Point', 'color': '4caf50'},
            'firewall': {'name': 'Firewall', 'color': 'f44336'},
            'switch': {'name': 'Switch', 'color': '00bcd4'},
            'server': {'name': 'Server', 'color': '3f51b5'},
            'vm-host': {'name': 'VM Host', 'color': '673ab7'},
            'network': {'name': 'Network', 'color': '2196f3'},
        }
        role = nb.dcim.device_roles.get(slug=slug)
        if not role and not dry_run:
            info = role_defs.get(slug, role_defs['network'])
            role = nb.dcim.device_roles.create(name=info['name'], slug=slug, color=info['color'])
            logger.info(f"  [Auto-Create] 建立新角色: {info['name']} ({slug})")
        if role: role_cache[slug] = role
        return role

    def get_role_slug(device):
        os_type = (device.get('os') or '').lower()
        hardware = (device.get('hardware') or '').lower()
        if 'printer' in os_type or 'printer' in hardware: return 'printer'
        if os_type in ['fortigate', 'panos', 'paloalto'] or 'fortinet' in hardware: return 'firewall'
        if os_type == 'arubaos' or 'access point' in hardware: return 'access-point'
        if 'vmware' in os_type or 'esxi' in hardware: return 'vm-host'
        if os_type in ['ios', 'iosxe', 'nxos', 'junos', 'routeros', 'edgeos'] or 'switch' in hardware: return 'switch'
        if os_type in ['linux', 'windows', 'windows', 'freebsd', 'ubuntu', 'centos', 'debian']: return 'server'
        return 'network'

    # --- Default Site ---
    try:
        site_slug = 'main-site'
        default_site = nb.dcim.sites.get(slug=site_slug)
        if not default_site and not dry_run:
             default_site = nb.dcim.sites.create(name='Main Site', slug=site_slug, status='active')
    except Exception: pass

    # --- Main Loop ---
    for dev in librenms_devices:
        hostname = dev.get('sysName') or dev.get('hostname')
        if not hostname: hostname = f"Unknown-{dev.get('device_id')}"
        
        serial = dev.get('serial')
        hardware = dev.get('hardware') or 'Generic'
        os_name = dev.get('os')
        version = dev.get('version') # e.g., "Server 2012 R2"
        ip_addr = dev.get('ip')
        if ip_addr and ',' in ip_addr: ip_addr = ip_addr.split(',')[0] # 若有多個IP取第一個
        
        location = dev.get('location') # LibreNMS sysLocation
        description = dev.get('sysDescr') # Full Description
        display_name = dev.get('display') # Generic display name

        is_down = str(dev.get('status', '')).lower() in ['0', 'down', 'false']

        try:
            # 1. 準備必要關聯資料 (Manufacturer, Type, Role, Platform)
            mfr_name = get_manufacturer_name(dev)
            mfr_slug = normalize_slug(mfr_name)
            
            # 若廠商不是 Generic 但硬體是 Generic，則將硬體名稱改為 "{廠商} Generic"
            if mfr_name != 'Generic' and hardware == 'Generic':
                hardware = f"{mfr_name} Generic"
            
            target_role = ensure_role(get_role_slug(dev))
            
            # [v6.0] Site (Location)
            target_site = default_site
            if location:
                loc_site = get_or_create_site(nb, location, dry_run)
                if loc_site: target_site = loc_site
            
            # Platform (OS)
            target_platform = get_or_create_platform(nb, mfr_name, os_name, version, dry_run)
            
            # Manufacturer & Device Type
            mfr = nb.dcim.manufacturers.get(slug=mfr_slug)
            if not mfr and not dry_run:
                mfr = nb.dcim.manufacturers.create(name=mfr_name, slug=mfr_slug)
            
            dt_slug = normalize_slug(hardware)
            dt = nb.dcim.device_types.get(slug=dt_slug)
            if not dt and not dry_run and mfr:
                dt = nb.dcim.device_types.create(manufacturer=mfr.id, model=hardware, slug=dt_slug, u_height=1)

            # 2. 搜尋設備 (優先 Serial，次之 Name)
            nb_device = None
            if serial: nb_device = nb.dcim.devices.get(serial=serial)
            if not nb_device: nb_device = nb.dcim.devices.get(name=hostname)

            # 3. 更新或建立
            if nb_device:
                # === Update Logic (Full Update) ===
                changes = []
                
                # [v6.0] Update Site
                if target_site and nb_device.site.id != target_site.id:
                    old_site = nb_device.site.name if hasattr(nb_device.site, 'name') else str(nb_device.site)
                    if not dry_run: nb_device.site = target_site.id
                    changes.append(f"Site: {old_site}->{target_site.name}")
                    
                # [v6.0] Update Description/Comments
                if display_name and nb_device.description != display_name:
                    if not dry_run: nb_device.description = display_name
                    changes.append("Desc Update")
                
                # 檢查 Status
                current_status = nb_device.status.value if nb_device.status else 'unknown'
                target_status = 'decommissioning' if is_down else 'active'
                if current_status != target_status:
                    if not dry_run: nb_device.status = target_status
                    changes.append(f"Status: {current_status}->{target_status}")

                # 檢查 Role
                current_role_id = nb_device.role.id if nb_device.role else None
                if target_role and current_role_id != target_role.id:
                    old_role = nb_device.role.name if hasattr(nb_device.role, 'name') else str(nb_device.role)
                    if not dry_run: nb_device.role = target_role.id
                    changes.append(f"Role: {old_role}->{target_role.name}")

                # 檢查 Device Type (Model)
                # Pynetbox 可能回傳 id (int) 或 Record (object)
                current_dt_id = nb_device.device_type.id if hasattr(nb_device.device_type, 'id') else nb_device.device_type
                
                if dt and current_dt_id != dt.id:
                    if not dry_run: nb_device.device_type = dt.id
                    changes.append(f"Type: Update to {dt.model}")

                # 檢查 Platform (OS)
                current_platform_id = nb_device.platform.id if nb_device.platform else None
                if target_platform and current_platform_id != target_platform.id:
                     if not dry_run: nb_device.platform = target_platform.id
                     changes.append(f"Platform: -> {target_platform.name}")

                # 檢查 Serial
                if serial and nb_device.serial != serial:
                    if not dry_run: nb_device.serial = serial
                    changes.append(f"Serial: Update")

                if changes:
                    if not dry_run: nb_device.save()
                    logger.info(f"  [Updated] {hostname}: {', '.join(changes)}")
                    stats['updated'] += 1
                else:
                    # 無變更
                    pass

                # 更新 IP (Independent Check)
                update_primary_ip(nb, nb_device, ip_addr, dry_run)
                # [v6.0] Detailed Sync
                sync_detailed_data(nb, nb_device, librenms_url, librenms_token, dev.get('device_id'), dry_run)

            else:
                # === Create Logic ===
                if not auto_create:
                    logger.info(f"  [Skip New] {hostname} (Auto-Create=False)")
                    stats['skipped'] += 1
                    continue
                
                if not dry_run and dt and target_role and target_site:
                    new_status = 'decommissioning' if is_down else 'active'
                    nb_device = nb.dcim.devices.create(
                        name=hostname,
                        device_type=dt.id,
                        role=target_role.id,
                        site=target_site.id,
                        serial=serial or '',
                        status=new_status,
                        platform=target_platform.id if target_platform else None,
                        description=display_name or ''
                    )
                    logger.info(f"  ✅ [Created] {hostname} (Type={dt.model}, Platform={target_platform.name if target_platform else 'None'})")
                    stats['created'] += 1
                    
                    # 建立後直接綁定 IP 與詳細資料
                    update_primary_ip(nb, nb_device, ip_addr)
                    sync_detailed_data(nb, nb_device, librenms_url, librenms_token, dev.get('device_id'), dry_run)
                elif dry_run:
                    logger.info(f"  (Dry-Run) Would Create: {hostname}")

        except Exception as e:
            logger.error(f"  ❌ {hostname} 處理失敗: {e}")
            stats['failed'] += 1

    save_metrics(METRICS_FILE, 'librenms_to_netbox', stats)
    logger.info("<<< 同步完成")
    if stats['failed'] > 0: sys.exit(1)

if __name__ == "__main__":
    main()
