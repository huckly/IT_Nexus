#!/usr/bin/env python3
# =============================================================================
# librenms_alert_glpi.py - LibreNMS 告警自動開立 GLPI 工單
# =============================================================================
#
# 用途：此腳本供 LibreNMS "Alert Transport" (Script) 呼叫。
# 當監控到設備 Down 時，自動在 GLPI 建立 "Incident" 工單。
#
# 配置方式 (LibreNMS 端):
# 1. 將此檔案放置於 LibreNMS Server (通常在 /opt/librenms/scripts/)
# 2. 賦予執行權限: chmod +x librenms_alert_glpi.py
# 3. 在 LibreNMS Web UI -> Alerts -> Alert Transports -> Create
#    - Transport Type: Script
#    - Script Path: /opt/librenms/scripts/librenms_alert_glpi.py
# 4. 在 Alert Rule 中關聯此 Transport
#
# =============================================================================

import os
import sys
import json
import requests
import urllib3
import argparse
from dotenv import load_dotenv

# 禁用 SSL 警告
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# 嘗試載入 .env
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(BASE_DIR, '.env')

# 載入順序: 當前目錄 -> NetBox 預設目錄
if os.path.exists(env_path):
    load_dotenv(env_path)
elif os.path.exists('/opt/netbox/scripts/.env'):
    load_dotenv('/opt/netbox/scripts/.env')

GLPI_API_URL = os.getenv('GLPI_API_URL', 'http://198.51.100.2/apirest.php')
GLPI_APP_TOKEN = os.getenv('GLPI_APP_TOKEN')
GLPI_USER_TOKEN = os.getenv('GLPI_USER_TOKEN')

def init_session():
    if not GLPI_APP_TOKEN or not GLPI_USER_TOKEN:
        print("❌ 設定錯誤: 缺少 GLPI_APP_TOKEN 或 GLPI_USER_TOKEN")
        sys.exit(1)

    url = f"{GLPI_API_URL.rstrip('/')}/initSession"
    headers = {
        'App-Token': GLPI_APP_TOKEN,
        'Authorization': f'user_token {GLPI_USER_TOKEN}'
    }
    try:
        resp = requests.get(url, headers=headers, verify=False, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get('session_token')
    except Exception as e:
        print(f"❌ GLPI Session 初始化失敗: {e}")
        sys.exit(1)

    except Exception as e:
        print(f"❌ GLPI Session 初始化失敗: {e}")
        sys.exit(1)

def kill_session(session_token, headers):
    try:
        requests.get(f"{GLPI_API_URL.rstrip('/')}/killSession", headers=headers, verify=False, timeout=5)
    except: pass

def search_ticket(title, session_token):
    """搜尋未結案的工單 (Status: New(1), Processing(2), Pending(3))"""
    headers = {
        'Session-Token': session_token,
        'App-Token': GLPI_APP_TOKEN,
        'Content-Type': 'application/json'
    }
    
    # 搜尋條件: Title contains <title> AND Status IN (1, 2, 3)
    # 注意: GLPI 搜尋 API 較複雜，這裡簡化為搜尋 Title 包含字串，且 Status != Solved(5)/Closed(6)
    # Field 1 = Name (Title), Field 12 = Status
    
    params = {
        'criteria[0][field]': 1,
        'criteria[0][searchtype]': 'contains',
        'criteria[0][value]': title,
        'criteria[1][link]': 'AND',
        'criteria[1][field]': 12,
        'criteria[1][searchtype]': 'equals',
        'criteria[1][value]': 'notold', # 搜尋所有未結案
        'forcedisplay[0]': 2 # ID
    }
    
    try:
        resp = requests.get(f"{GLPI_API_URL.rstrip('/')}/Ticket", headers=headers, params=params, verify=False)
        resp.raise_for_status()
        data = resp.json()
        
        # GLPI 回傳格式可能是 list 或 dict (視版本與結果數量)
        # 若無結果通常回傳空 list []
        if isinstance(data, list) and len(data) > 0:
             # 回傳第一筆符合的 ID
             return data[0].get('id')
        return None
    except Exception as e:
        print(f"⚠️ 搜尋工單失敗: {e}")
        return None

def resolve_ticket(ticket_id, content, session_token):
    """將工單狀態改為 Solved (5) 並加入解決方案"""
    headers = {
        'Session-Token': session_token,
        'App-Token': GLPI_APP_TOKEN,
        'Content-Type': 'application/json'
    }
    
    # 1. Update Status to Solved (5)
    try:
        payload = {"input": {"id": ticket_id, "status": 5}}
        requests.put(f"{GLPI_API_URL.rstrip('/')}/Ticket/{ticket_id}", headers=headers, json=payload, verify=False)
        print(f"✅ 工單 #{ticket_id} 狀態已更新為 Solved")
    except Exception as e:
        print(f"❌ 更新工單狀態失敗: {e}")
        return

    # 2. Add Solution
    try:
        solution_payload = {
            "input": {
                "items_id": ticket_id,
                "itemtype": "Ticket",
                "content": f"Auto-Resolved by LibreNMS Recovery: {content}",
                "solutiontypes_id": 1 # Default Solution Type
            }
        }
        requests.post(f"{GLPI_API_URL.rstrip('/')}/ITILSolution", headers=headers, json=solution_payload, verify=False)
        print(f"✅ 已加入解決方案至工單 #{ticket_id}")
    except Exception as e:
        print(f"⚠️ 加入解決方案失敗: {e}")

def create_ticket(title, content, urgency, session_token):
    headers = {
        'Session-Token': session_token,
        'App-Token': GLPI_APP_TOKEN,
        'Content-Type': 'application/json'
    }
    
    payload = {
        "input": {
            "name": title,
            "content": content,
            "status": 1, # New
            "urgency": urgency,
            "type": 1, # Incident
        }
    }
    
    try:
        resp = requests.post(f"{GLPI_API_URL.rstrip('/')}/Ticket", headers=headers, json=payload, verify=False)
        resp.raise_for_status()
        print(f"✅ 工單建立成功! Ticket ID: {resp.json().get('id')}")
    except Exception as e:
        print(f"❌ 工單建立失敗: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 librenms_alert_glpi.py '<Title>' '<Message>'")
        sys.exit(1)
        
    title = sys.argv[1]
    msg = sys.argv[2] if len(sys.argv) > 2 else "No details provided."
    
    # 判斷是否為恢復通知
    is_recovery = "Recovery" in title or "Recovered" in title or "OK" in title
    
    # 初始化 Session
    session_token = init_session()
    headers = {'Session-Token': session_token, 'App-Token': GLPI_APP_TOKEN}

    if is_recovery:
        # 嘗試搜尋對應的未結工單 (移除 'Recovery' 字樣以匹配原始告警)
        search_title = title.replace("Recovery: ", "").replace("Recovered: ", "").strip()
        ticket_id = search_ticket(search_title, session_token)
        
        if ticket_id:
            print(f"🔍 發現未結工單 #{ticket_id}，執行自動結案...")
            resolve_ticket(ticket_id, msg, session_token)
        else:
            print(f"ℹ️ 未發現相關未結工單 ('{search_title}')，忽略此恢復通知。")
    else:
        # 下載/開立新工單
        urgency = 3
        if "Device Down" in title or "Critical" in title: urgency = 5
        elif "Warning" in title: urgency = 3
        
        # 檢查是否已有重複工單 (避免重複開單)
        if search_ticket(title, session_token):
            print(f"ℹ️ 工單已存在 ('{title}')，跳過開單。")
        else:
            create_ticket(title, msg, urgency, session_token)

    kill_session(session_token, headers)

