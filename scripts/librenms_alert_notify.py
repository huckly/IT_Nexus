#!/usr/bin/env python3
# =============================================================================
# librenms_alert_notify.py - LibreNMS 通用 IM 通知腳本
# =============================================================================
# 用途：將告警內容發送到指定的 Webhook URL (支援 LINE/Teams/Slack)
# 配置：在 .env 中設定 IM_WEBHOOK_URL
# =============================================================================

import os
import sys
import json
import requests
from dotenv import load_dotenv

# 載入設定
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(BASE_DIR, '.env')
if os.path.exists(env_path):
    load_dotenv(env_path)

IM_WEBHOOK_URL = os.getenv('IM_WEBHOOK_URL')

def send_notification(title, message):
    if not IM_WEBHOOK_URL:
        print("⚠️ 未設定 IM_WEBHOOK_URL，跳過通知。")
        return

    # 根據標題判斷顏色/圖示 (簡易適配 Teams/Slack)
    status = "info"
    color = "00FF00" # Green
    if "Device Down" in title or "Critical" in title:
        status = "error"
        color = "FF0000" # Red
    elif "Warning" in title:
        status = "warning"
        color = "FFA500" # Orange
    elif "Recovery" in title or "OK" in title:
        status = "success"
        color = "00FF00"

    try:
        # 通用 Payload 設計 (同時兼容部分 Microsoft Teams connector 與 Slack incoming webhook)
        # 對於 LINE Notify，需要 application/x-www-form-urlencoded，這裡暫以 JSON 為主
        # 若需要 LINE Notify，需修改 header 與 payload 格式
        
        headers = {'Content-Type': 'application/json'}
        payload = {
            "title": title,
            "text": message,
            "themeColor": color,
            "summary": f"{title} - {message}"
        }
        
        # 針對 LINE Notify 的特別處理 (如果 URL 包含 line.me)
        if "line.me" in IM_WEBHOOK_URL:
            headers = {'Authorization': f'Bearer {IM_WEBHOOK_URL.split("/")[-1]}'} # 假設 URL 只有 Token 或者是標準 API
            # LINE Notify API: https://notify-api.line.me/api/notify
            # 這裡簡單處理：若 URL 是 API Endpoint
            requests.post(IM_WEBHOOK_URL, headers=headers, data={'message': f"\n[{status.upper()}] {title}\n{message}"})
        else:
            # Default JSON Webhook
            requests.post(IM_WEBHOOK_URL, headers=headers, json=payload, timeout=10)

        print(f"✅ 通知已發送: {title}")
        
    except Exception as e:
        print(f"❌ 通知發送失敗: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 librenms_alert_notify.py '<Title>' '<Message>'")
        sys.exit(1)
        
    title = sys.argv[1]
    msg = sys.argv[2] if len(sys.argv) > 2 else ""
    
    send_notification(title, msg)
