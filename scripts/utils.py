import os
import sys
import json
import time
import logging
import requests

def setup_logging(log_file, level=logging.INFO):
    """配置專案日誌系統。"""
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file),
        ]
    )
    return logging.getLogger(__name__)

def save_metrics(metrics_file, sync_source, stats):
    """輸出標準化的 JSON Metrics。"""
    try:
        os.makedirs(os.path.dirname(metrics_file), exist_ok=True)
        with open(metrics_file, 'w') as f:
            json.dump({
                'timestamp': time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                'sync_source': sync_source,
                'stats': stats,
            }, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"無法寫入 Metrics ({metrics_file}): {e}", file=sys.stderr)

def send_notification(title, message, status='info'):
    """發送通用 Webhook 通知 (支援 Slack/Teams/Discord 格式適配)。"""
    webhook_url = os.getenv('NOTIFICATION_URL')
    if not webhook_url:
        return

    try:
        # 通用 JSON Payload (可根據不同平台調整)
        payload = {
            'text': f"[{status.upper()}] {title}\n{message}",
            'title': title,
            'summary': message,
            'themeColor': 'FF0000' if status == 'error' else '00FF00'
        }
        
        requests.post(webhook_url, json=payload, timeout=5)
    except Exception as e:
        print(f"通知發送失敗: {e}", file=sys.stderr)

def request_with_retry(method, url, headers=None, payload=None, retry_count=3, timeout=30, logger=None, **kwargs):
    """執行帶有 Exponential Backoff 的 HTTP 請求。"""
    for attempt in range(1, retry_count + 1):
        try:
            resp = requests.request(method, url, headers=headers, json=payload, timeout=timeout, **kwargs)
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as e:
            wait = 2 ** attempt
            msg = f"API 請求失敗 ({method} {url}) [第 {attempt}/{retry_count} 次]: {e}"
            if logger:
                logger.warning(f"{msg}，{wait} 秒後重試...")
            else:
                print(msg, file=sys.stderr)
            
            if attempt == retry_count:
                raise
            time.sleep(wait)

def get_env_var(var_name, default=None, required=False):
    """讀取環境變數，支援必填檢查。"""
    val = os.getenv(var_name, default)
    if required and val is None:
        print(f"錯誤：缺少必要的環境變數 {var_name}", file=sys.stderr)
        sys.exit(1)
    return val
