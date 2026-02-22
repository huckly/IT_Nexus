#!/usr/bin/env python3
# =============================================================================
# sync_netbox_to_glpi.py - IT Nexus v5.4 企業級同步腳本 (模組化版)
# 用途：將 NetBox (Source of Truth) 中 Active 設備同步至 GLPI
# 執行身份：netbox 系統帳號
# =============================================================================

import os
import sys
import pynetbox
import requests
from dotenv import load_dotenv

# 匯入 IT Nexus 自定義工具模組
from utils import setup_logging, save_metrics, request_with_retry, get_env_var

# --- 載入環境變數 ---
ENV_PATH = '/opt/netbox/scripts/.env'
load_dotenv(ENV_PATH)

# --- 初始化日誌 ---
logger = setup_logging('/var/log/it_nexus/sync_glpi.log')

# --- 配置 ---
RETRY_COUNT = int(get_env_var('RETRY_COUNT', '3'))
METRICS_FILE = get_env_var('METRICS_FILE_GLPI', '/var/log/it_nexus/metrics_glpi.json')

# 資產分類對照表 (NetBox Role slug -> GLPI Endpoint)
ROLE_TO_ENDPOINT = {
    'server': 'Computer', 'vm-host': 'Computer',
    'switch': 'NetworkEquipment', 'router': 'NetworkEquipment',
    'firewall': 'NetworkEquipment', 'access-point': 'NetworkEquipment',
    'network': 'NetworkEquipment',  # 預設 Network 角色
    'printer': 'Printer',
}
DEFAULT_GLPI_ENDPOINT = 'Computer'  # 未知角色的預設對應

def init_glpi_session(glpi_url, app_token, user_token):
    """初始化 GLPI API 工作階段。"""
    # 修正：確保 URL 不會以 / 結尾，避免 // 雙斜線問題
    glpi_url = glpi_url.rstrip('/')
    
    headers = {'App-Token': app_token, 'Authorization': f'user_token {user_token}'}
    # 修正：完整路徑拼接，修正 404 錯誤
    init_url = f'{glpi_url}/initSession'
    
    try:
        resp = request_with_retry('GET', init_url, headers=headers, retry_count=RETRY_COUNT, logger=logger)
        return resp.json()['session_token']
    except Exception as e:
        logger.error(f"GLPI Session 初始化失敗 (URL: {init_url}): {e}")
        raise

def search_glpi(glpi_url, headers, endpoint, field, value):
    """在 GLPI 中搜尋設備。"""
    glpi_url = glpi_url.rstrip('/')
    try:
        search_url = f"{glpi_url}/search/{endpoint}?criteria[0][field]={field}&criteria[0][searchtype]=equals&criteria[0][value]={value}"
        resp = request_with_retry('GET', search_url, headers=headers, retry_count=RETRY_COUNT, logger=logger)
        result = resp.json()
        if result.get('totalcount', 0) > 0 and result.get('data'):
            # GLPI 搜尋結果可能是 list 或 dict，視版本而定
            first_item = result['data'][0]
            return first_item.get('2') or first_item.get(2) # ID 通常在欄位 2
    except Exception as e:
        logger.warning(f"GLPI 搜尋失敗 ({value}): {e}")
    return None

def main():
    logger.info("=" * 60)
    logger.info(">>> 開始同步 (v5.4): NetBox -> GLPI")
    logger.info("=" * 60)

    dry_run = get_env_var('DRY_RUN', 'False').lower() == 'true'
    if dry_run: logger.warning("⚠ DRY-RUN 模式啟用")

    stats = {'created': 0, 'updated': 0, 'skipped': 0, 'failed': 0}

    # --- API 本體 ---
    try:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        
        nb = pynetbox.api(get_env_var('NETBOX_URL', required=True), token=get_env_var('NETBOX_TOKEN', required=True))
        nb.http_session.verify = False  # 支援 Self-signed Certificate
        glpi_url = get_env_var('GLPI_API_URL', required=True)
        app_token = get_env_var('GLPI_APP_TOKEN', required=True)
        user_token = get_env_var('GLPI_USER_TOKEN', required=True)
        
        session_token = init_glpi_session(glpi_url, app_token, user_token)
        glpi_headers = {'Session-Token': session_token, 'App-Token': app_token, 'Content-Type': 'application/json'}
    except Exception as e:
        logger.error(f"API 初始化失敗: {e}")
        sys.exit(1)

    try:
        devices = nb.dcim.devices.filter(status='active')
        for dev in devices:
            try:
                role_obj = getattr(dev, 'role', None) or getattr(dev, 'device_role', None)
                role_slug = role_obj.slug if role_obj else ''
                endpoint = ROLE_TO_ENDPOINT.get(role_slug, DEFAULT_GLPI_ENDPOINT)

                logger.info(f"處理: {dev.name} -> {endpoint}")
                
                # 建構 Payload
                # 注意：GLPI 不同類型的必填欄位可能不同，這裡是通用欄位
                payload = {
                    "input": {
                        "name": dev.name,
                        "serial": dev.serial or '',
                        "otherserial": str(dev.id), # 用 NetBox ID 當作輔助識別
                        "comment": f"自動同步自 NetBox. 型號: {dev.device_type.model if dev.device_type else 'N/A'}"
                    }
                }

                if dry_run: stats['created'] += 1; continue

                # 搜尋策略：Serial (field 5) -> Name (field 1)
                # 注意：如果 serial 為空，搜尋可能會不準確，建議有 serial 才搜
                exists_id = None
                if dev.serial:
                    exists_id = search_glpi(glpi_url, glpi_headers, endpoint, 5, dev.serial)
                
                if not exists_id:
                    exists_id = search_glpi(glpi_url, glpi_headers, endpoint, 1, dev.name)

                if exists_id:
                    request_with_retry('PUT', f"{glpi_url}/{endpoint}/{exists_id}", headers=glpi_headers, payload=payload, logger=logger)
                    stats['updated'] += 1
                else:
                    request_with_retry('POST', f"{glpi_url}/{endpoint}", headers=glpi_headers, payload=payload, logger=logger)
                    stats['created'] += 1
            except Exception as e:
                logger.error(f"  ❌ {dev.name} 同步失敗: {e}")
                stats['failed'] += 1
    finally:
        try: requests.get(f'{glpi_url}/killSession', headers=glpi_headers, timeout=10)
        except: pass

    save_metrics(METRICS_FILE, 'netbox_to_glpi', stats)
    logger.info("<<< 同步完成")
    if stats['failed'] > 0: sys.exit(1)

if __name__ == "__main__":
    main()
