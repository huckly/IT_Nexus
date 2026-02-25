#!/usr/bin/env python3
# =============================================================================
# webhook_receiver.py - LibreNMS Webhook Receiver for NetBox Sync
# =============================================================================
# 功能：
# 1. 接收來自 LibreNMS 的 Alert Webhook (JSON Payload)
# 2. 解析告警中的 Hostname
# 3. 觸發 `sync_librenms_to_netbox.py --device <HOSTNAME>` 進行單機同步
#
# 部署：
# - 放置於 NetBox Server (198.51.100.3)
# - 建議使用 Systemd 運行 (Port 5005)
# =============================================================================

import os
import sys
import json
import subprocess
import logging
from flask import Flask, request, jsonify
from datetime import datetime

# --- Configuration ---
LOG_FILE = '/var/log/it_nexus/webhook_receiver.log'
SYNC_SCRIPT = '/opt/netbox/scripts/sync_librenms_to_netbox.py'
PYTHON_EXEC = '/opt/netbox/scripts/venv/bin/python3'
HOST = '0.0.0.0'
PORT = 5005

# --- Logging Setup ---
logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

def trigger_sync(hostname):
    """執行同步腳本 (異步或同步執行視需求而定，這裡採同步等待以便回傳結果)"""
    cmd = [PYTHON_EXEC, SYNC_SCRIPT, '--device', hostname]
    logger.info(f"🚀 Triggering sync for {hostname}...")
    
    try:
        # 使用 subprocess.run 執行同步
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300 # 5分鐘 timeout
        )
        
        if result.returncode == 0:
            logger.info(f"✅ Sync successful for {hostname}")
            logger.debug(f"Output: {result.stdout}")
            return True, result.stdout
        else:
            logger.error(f"❌ Sync failed for {hostname} (Exit Code: {result.returncode})")
            logger.error(f"Error: {result.stderr}")
            return False, result.stderr
            
    except Exception as e:
        logger.error(f"❌ Execution error: {e}")
        return False, str(e)

@app.route('/webhook', methods=['POST'])
def handle_webhook():
    """接收 LibreNMS Webhook"""
    try:
        data = request.json
        if not data:
            return jsonify({'status': 'error', 'message': 'No JSON payload'}), 400
        # 處理 List 類型的 Payload (例如 LibreNMS Test Transport 或 API 輸出)
        if isinstance(data, list):
            if len(data) > 0:
                data = data[0] # 取第一筆資料
            else:
                return jsonify({'status': 'error', 'message': 'Empty JSON list'}), 400

        # LibreNMS Alert Payload 格式通常包含 'hostname' 或 'sysName'
        # 根據實際 LibreNMS Template 調整
        hostname = data.get('hostname') or data.get('sysName')
        
        # 嘗試從 rule 陣列中提取 (LibreNMS Default Structure)
        if not hostname and 'rule' in data and isinstance(data['rule'], list) and len(data['rule']) > 0:
            hostname = data['rule'][0].get('hostname') or data['rule'][0].get('sysName')

        # 嘗試從 faults 陣列中提取
        if not hostname and 'faults' in data and isinstance(data['faults'], list) and len(data['faults']) > 0:
            hostname = data['faults'][0].get('hostname') or data['faults'][0].get('sysName')
            
        # 最後嘗試 title
        if not hostname:
             hostname = data.get('title', '').split(' ')[0]

        if not hostname or hostname == "NetBox": # 避免誤觸 NetBox 自身的 Rule
            logger.warning(f"⚠ Received webhook but could not extract hostname. Payload: {json.dumps(data)}")
            return jsonify({'status': 'ignored', 'message': 'Hostname not found'}), 200

        logger.info(f"📩 Received Alert for: {hostname} (State: {data.get('state')}, Alert: {data.get('name')})")

        # 觸發同步
        success, output = trigger_sync(hostname)

        if success:
            return jsonify({'status': 'success', 'message': f'Sync triggered for {hostname}'}), 200
        else:
            return jsonify({'status': 'error', 'message': 'Sync script failed', 'details': output}), 500

    except Exception as e:
        logger.error(f"🔥 Webhook processing error: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok', 'timestamp': datetime.now().isoformat()}), 200

if __name__ == '__main__':
    # 確保 Log 目錄存在
    log_dir = os.path.dirname(LOG_FILE)
    if not os.path.exists(log_dir):
        try:
            os.makedirs(log_dir, exist_ok=True)
            # 嘗試設為 netbox 權限 (若以 root 執行)
            os.system(f"chown -R netbox:netbox {log_dir}")
        except:
            pass

    print(f"Starting Webhook Receiver on {HOST}:{PORT}...")
    app.run(host=HOST, port=PORT)
