#!/bin/bash
# =============================================================================
# install_netbox_secure.sh - IT Nexus v5.2 Security Hardened Edition
# 用途：在 Ubuntu 24.04 上安全部署 NetBox v4.5.2
# 執行方式：sudo ./install_netbox_secure.sh
# =============================================================================
set -e

# --- 變數設定 ---
NETBOX_VERSION="v4.5.2"
NETBOX_IP="198.51.100.3"
NETBOX_DOMAIN="example.com"
NETBOX_HOME="/opt/netbox"
SCRIPTS_HOME="$NETBOX_HOME/scripts"
LOG_DIR="/var/log/it_nexus"

echo "=== IT Nexus v5.2 - NetBox $NETBOX_VERSION 安全安裝 (Ubuntu 24.04) ==="

# --- 步驟 0：環境檢查 ---
echo ">>> 0. 執行系統環境檢查..."
# 檢查 OS 版本 (僅支援 Ubuntu 24.04)
OS_VERSION=$(lsb_release -rs)
if [ "$OS_VERSION" != "24.04" ]; then
    echo "警告：本腳本針對 Ubuntu 24.04 設計，當前系統版本為 $OS_VERSION。可能存在相容性問題。"
fi

# 檢查記憶體 (NetBox 建議至少 2GB)
TOTAL_MEM=$(free -m | awk '/^Mem:/{print $2}')
if [ "$TOTAL_MEM" -lt 1900 ]; then
    echo "警告：系統記憶體少於 2GB ($TOTAL_MEM MB)，NetBox 運行可能會不穩定。"
fi

# --- 步驟 1：系統更新與相依套件 ---
echo ">>> 1. 安裝系統相依套件..."
apt update && apt upgrade -y
apt install -y curl wget git unzip vim tar gnupg2 build-essential \
    libpq-dev libssl-dev libffi-dev zlib1g-dev redis-server \
    python3 python3-pip python3-venv python3-dev \
    postgresql postgresql-contrib nginx openssl

# --- 步驟 2：生成 SSL 憑證 ---
echo ">>> 2. 處理 SSL 憑證..."
# [選項 A] 生成 Self-Signed 憑證 (預設)
echo "正在生成 Self-Signed 憑證 (適合內網測試)..."
mkdir -p /etc/ssl/private /etc/ssl/certs
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout /etc/ssl/private/netbox.key \
    -out /etc/ssl/certs/netbox.crt \
    -subj "/C=TW/ST=Taiwan/L=Taipei/O=IT/CN=${NETBOX_IP}"
chmod 600 /etc/ssl/private/netbox.key

# [選項 B] 如果您有正式 CA 或想使用 Let's Encrypt (ACME)：
# 請註解上方生成代碼，並參考以下連結配置 certbot：
# https://certbot.eff.org/instructions?os=ubuntunoble&tab=nginx

# --- 步驟 3：設定 PostgreSQL (動態強密碼) ---
echo ">>> 3. 設定 PostgreSQL..."
DB_PASS=$(openssl rand -base64 24)
systemctl enable --now postgresql
sudo -u postgres psql -c "CREATE DATABASE netbox;" 2>/dev/null || true
sudo -u postgres psql -c "CREATE USER netbox WITH PASSWORD '${DB_PASS}';" 2>/dev/null || true
sudo -u postgres psql -c "ALTER USER netbox WITH PASSWORD '${DB_PASS}';" || true
sudo -u postgres psql -c "ALTER DATABASE netbox OWNER TO netbox;" || true

# --- 步驟 4：設定 Redis ---
echo ">>> 4. 設定 Redis..."
systemctl enable --now redis-server

# --- 步驟 5：下載 NetBox ---
echo ">>> 5. 下載 NetBox $NETBOX_VERSION..."
mkdir -p $NETBOX_HOME
cd $NETBOX_HOME
if [ ! -d ".git" ]; then
    git clone -b $NETBOX_VERSION https://github.com/netbox-community/netbox.git .
fi

# --- 步驟 6：建立使用者與權限 ---
echo ">>> 6. 建立使用者與權限..."
id -u netbox &>/dev/null || adduser --system --group netbox
chown -R netbox:netbox $NETBOX_HOME

# --- 步驟 7：設定 configuration.py ---
echo ">>> 7. 設定 NetBox configuration.py..."
cd $NETBOX_HOME/netbox/netbox/
if [ ! -f "configuration.py" ]; then
    cp configuration_example.py configuration.py
fi

# 產生 SECRET_KEY
SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(50))')

# 使用 sed 修改設定檔 (使用 | 作為分隔符號防止密碼含 / 報錯)
sed -i "s|ALLOWED_HOSTS = \[\]|ALLOWED_HOSTS = ['${NETBOX_IP}', '${NETBOX_DOMAIN}', 'localhost']|" configuration.py
sed -i "/DATABASES = {/,/}/ s|'USER': '',|'USER': 'netbox',|" configuration.py
sed -i "/DATABASES = {/,/}/ s|'PASSWORD': '',|'PASSWORD': '${DB_PASS}',|" configuration.py
sed -i "s|SECRET_KEY = ''|SECRET_KEY = '${SECRET_KEY}'|" configuration.py

# --- 步驟 8：執行 NetBox 安裝程序 ---
echo ">>> 8. 執行 NetBox 安裝程序 (upgrade.sh)..."
$NETBOX_HOME/upgrade.sh

# --- 步驟 9：設定 Gunicorn & Systemd ---
echo ">>> 9. 設定 Gunicorn & Systemd..."
cp $NETBOX_HOME/contrib/gunicorn.py $NETBOX_HOME/gunicorn.py
cp $NETBOX_HOME/contrib/*.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now netbox netbox-rq

# --- 步驟 10：設定 Nginx (強制 HTTPS) ---
echo ">>> 10. 設定 Nginx (強制 HTTPS)..."
cat > /etc/nginx/sites-available/netbox <<EOF
# HTTP -> HTTPS 重導向
server {
    listen 80;
    server_name ${NETBOX_IP} ${NETBOX_DOMAIN};
    return 301 https://\$host\$request_uri;
}

# HTTPS 站點
server {
    listen 443 ssl;
    server_name ${NETBOX_IP} ${NETBOX_DOMAIN};

    ssl_certificate /etc/ssl/certs/netbox.crt;
    ssl_certificate_key /etc/ssl/private/netbox.key;
    ssl_protocols TLSv1.2 TLSv1.3;

    client_max_body_size 25m;

    location /static/ {
        alias ${NETBOX_HOME}/netbox/static/;
    }

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_set_header X-Forwarded-Host \$http_host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF
ln -sf /etc/nginx/sites-available/netbox /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default
systemctl restart nginx

# --- 步驟 11：建立同步腳本環境 ---
echo ">>> 11. 建立同步腳本環境..."
mkdir -p $SCRIPTS_HOME
sudo -u netbox python3 -m venv $SCRIPTS_HOME/venv

# --- 步驟 12：建立日誌目錄 ---
echo ">>> 12. 建立日誌目錄..."
mkdir -p $LOG_DIR
chown netbox:netbox $LOG_DIR
chmod 750 $LOG_DIR

# --- 步驟 13：儲存 DB 密碼供備份腳本使用 ---
echo ">>> 13. 儲存機密資訊..."
echo "DB_PASSWORD=${DB_PASS}" > $SCRIPTS_HOME/.db_secret
chmod 600 $SCRIPTS_HOME/.db_secret
chown root:root $SCRIPTS_HOME/.db_secret

# --- 步驟 14：建立 .env 範本 ---
echo ">>> 14. 建立 .env 範本 (請手動填入 Token)..."
if [ ! -f "$SCRIPTS_HOME/.env" ]; then
    cat > $SCRIPTS_HOME/.env <<ENVEOF
# IT Nexus v5.2 - 同步腳本設定檔
# NetBox (本機)
NETBOX_URL=http://127.0.0.1:8001
NETBOX_TOKEN=請填入您的_NetBox_Token

# LibreNMS (監控來源)
LIBRENMS_URL=http://198.51.100.1/api/v0
LIBRENMS_TOKEN=請填入您的_LibreNMS_Token

# GLPI (資產管理)
GLPI_API_URL=http://198.51.100.2/glpi/apirest.php
GLPI_APP_TOKEN=請填入您的_GLPI_App_Token
GLPI_USER_TOKEN=請填入您的_GLPI_User_Token

# 通用設定
DRY_RUN=False
AUTO_CREATE_NEW=False
LOG_LEVEL=INFO
RETRY_COUNT=3
METRICS_FILE_LIBRENMS=/var/log/it_nexus/metrics_librenms.json
METRICS_FILE_GLPI=/var/log/it_nexus/metrics_glpi.json
ENVEOF
    chown root:netbox $SCRIPTS_HOME/.env
    chmod 640 $SCRIPTS_HOME/.env
fi

echo ""
echo "============================================="
echo "  安裝完成！"
echo "  存取 NetBox: https://${NETBOX_IP}"
echo "============================================="
echo ""
echo "下一步："
echo "  1. 建立超級使用者："
echo "     sudo -u netbox bash -c 'source /opt/netbox/venv/bin/activate && python3 /opt/netbox/netbox/manage.py createsuperuser'"
echo "  2. 編輯 .env 填入 API Token："
echo "     sudo vim /opt/netbox/scripts/.env"
echo "  3. 安裝同步腳本套件："
echo "     sudo -u netbox /opt/netbox/scripts/venv/bin/pip install -r /opt/netbox/scripts/requirements.txt"
