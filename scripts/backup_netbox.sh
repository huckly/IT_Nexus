#!/bin/bash
# =============================================================================
# backup_netbox.sh - IT Nexus v5.2 NetBox 備份腳本
# 用途：每日備份 PostgreSQL 資料庫與設定檔
# 格式：pg_dump -Fc (壓縮格式，支援平行還原)
# 保留：7 天
# =============================================================================
set -e

# 讀取 DB 密碼
if [ -f /opt/netbox/scripts/.db_secret ]; then
    source /opt/netbox/scripts/.db_secret
    export PGPASSWORD="${DB_PASSWORD}"
else
    echo "錯誤：找不到 .db_secret 檔案" >&2
    exit 1
fi

BACKUP_DIR="/opt/netbox/backups"
DATE=$(date +%Y%m%d_%H%M%S)

echo ">>> 開始 NetBox 備份..."

# 建立備份目錄
mkdir -p "$BACKUP_DIR"
chown netbox:netbox "$BACKUP_DIR"

# 1. 資料庫備份 (Custom Format, 壓縮)
echo "  1. 備份 PostgreSQL..."
pg_dump -h localhost -U netbox -Fc netbox > "$BACKUP_DIR/netbox_db_${DATE}.dump"
echo "     完成: netbox_db_${DATE}.dump"

# 2. 設定檔與媒體備份
echo "  2. 備份設定檔與媒體..."
tar -czf "$BACKUP_DIR/netbox_files_${DATE}.tar.gz" \
    -C /opt/netbox/netbox \
    netbox/configuration.py \
    media/ 2>/dev/null || true
echo "     完成: netbox_files_${DATE}.tar.gz"

# 3. 清理過期備份 (保留 7 天)
echo "  3. 清理 7 天前的舊備份..."
find "$BACKUP_DIR" -type f -mtime +7 -delete

echo ">>> 備份完成！目錄: $BACKUP_DIR"
ls -lh "$BACKUP_DIR"
