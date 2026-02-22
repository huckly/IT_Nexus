# IT Nexus 維運與排錯手冊 (Maintenance & Troubleshooting)

本手冊提供 IT Nexus v5.4 系統的日常維管指令、常見問題排除以及災難復原流程。

## 1. 標準作業程序 (SOP) - 設備新增流程

### 1.1 監控設備 (伺服器、交換器、防火牆)
**請在 [LibreNMS] 新增設備。**
- LibreNMS 會自動發現序號、作業系統與硬體型號。
- 同步腳本 (`sync_librenms_to_netbox.py`) 會自動將其建立至 NetBox。
- NetBox 再自動同步至 GLPI。

### 1.2 被動設備 (Patch Panel、無 IP 設備、備品)
**請直接在 [NetBox] 新增設備。**
- 由於 LibreNMS 無法監控此類設備，需手動在 NetBox 建立資料。
- 這些設備不會被 LibreNMS 同步腳本覆蓋或刪除。

### 1.3 資料流向示意
```mermaid
graph LR
    User[IT 管理員]
    User -->|新增 IP 設備| LibreNMS
    User -->|新增 無 IP/被動設備| NetBox
    LibreNMS -->|Sync (自動)| NetBox
    NetBox -->|Sync (自動)| GLPI
```

---

### 1.4 故障與維修流程 (Incident Response)

#### 1.4.1 設備/線路中斷
- **監控**: LibreNMS 偵測到設備 Down。
- **自動化**: 同步腳本會將 NetBox 中該設備狀態標記為 `Decommissioning` (離線)。
- **處置**: 工程師進行搶修。

#### 1.4.2 服務恢復
- **監控**: LibreNMS 偵測到設備恢復 Up。
- **自動化**: 同步腳本會將 NetBox 中該設備狀態改回 `Active`。

#### 1.4.3 硬體更換 (RMA)
若設備故障無法修復，需更換硬體：
1. **更換硬體**: 上架新設備，設定與舊設備相同的 IP。
2. **LibreNMS**: 執行 `Discovery` 與 `Poller`，更新序號與硬體資訊。
3. **NetBox**: 下一次同步時，腳本會自動更新 NetBox 中的序號 (Serial Number)。
4. **GLPI**: NetBox 會將新資訊同步至 GLPI。

### 1.5 自動化工單配置 (Automated Ticketing)
若需由 LibreNMS 自動開立 GLPI 工單，請配置 Alert Transport：

1. **部署腳本**:
   將 `scripts/librenms_alert_glpi.py` 複製到 LibreNMS 主機 (例如 `/opt/librenms/scripts/`)。
   ```bash
   chmod +x /opt/librenms/scripts/librenms_alert_glpi.py
   ```

2. **LibreNMS 設定**:
   - **Alert Transports** -> **Create new transport**
   - **Transport type**: `Script`
   - **Script**: `/opt/librenms/scripts/librenms_alert_glpi.py`
   
3. **關聯規則**:
   在 Alert Rule (如 "Devices Down") 中，新增此 Transport。

### 1.6 Interface (Port) 同步

同步 LibreNMS 的實體介面資訊至 NetBox（v3 Clean Sync 策略）。
每次同步會**先清除該設備所有舊 Interface，再從 LibreNMS 重建**，確保資料一致。

同步內容包含：介面名稱、類型、MTU、MAC Address（NetBox v4.2+ 獨立物件）、設備 Primary IPv4。

```bash
# Dry-Run (預覽，不寫入)
sudo -E /opt/netbox/scripts/venv/bin/python3 /opt/netbox/scripts/sync_librenms_interfaces.py --dry-run --limit 3

# 同步單一設備
sudo -E /opt/netbox/scripts/venv/bin/python3 /opt/netbox/scripts/sync_librenms_interfaces.py --device example.com

# 正式同步所有設備
sudo -E /opt/netbox/scripts/venv/bin/python3 /opt/netbox/scripts/sync_librenms_interfaces.py
```

**可用參數：**
| 參數 | 說明 |
|------|------|
| `--dry-run` | 預覽模式，不寫入 NetBox |
| `--limit N` | 限制處理設備數量 (0=全部) |
| `--device HOSTNAME` | 只處理指定設備 |

> **注意**: 僅同步實體 Port，白名單包含 `Fa*`, `Gi*`, `Te*`, `Po*`, `eth*`, `ens*` 等前綴。
> Windows 虛擬介面 (WFP, Hyper-V) 與非實體介面會自動過濾。

---

## 2. 服務管理指令 (Service Management)

IT Nexus 所有的同步與備份任務均由 Systemd 驅動。

### 2.1 查看服務狀態
```bash
# 查看 LibreNMS 設備同步計時器
systemctl status netbox-sync-librenms.timer

# 查看 Interface 同步計時器
systemctl status netbox-sync-interfaces.timer

# 查看 GLPI 同步計時器
systemctl status netbox-sync-glpi.timer

# 查看備份計時器
systemctl status netbox-backup.timer
```

### 2.2 查看執行日誌
同步腳本的輸出會同時記錄在日誌檔與 Journald 中：
```bash
# 即時查看 LibreNMS 同步日誌
tail -f /var/log/it_nexus/sync_librenms.log

# 透過 journalctl 查看 (包含 Systemd 錯誤)
journalctl -u netbox-sync-librenms.service -e
```

---

## 3. 備份與還原 (Backup & Restore)

### 3.1 驗證備份檔案
備份存放在 `/opt/netbox/backups`：
```bash
ls -lh /opt/netbox/backups
```
`.dump` 為資料庫備份，`.tar.gz` 為設定與媒體檔。

### 3.2 災難復原流程 (Rollback)
若同步導致資料損壞，請依序執行：
1. **停止服務**：`sudo systemctl stop netbox`
2. **清除現有 DB**：`sudo -u postgres drpodb netbox && sudo -u postgres createdb netbox`
3. **還原資料庫**：`sudo -u postgres pg_restore -d netbox /opt/netbox/backups/netbox_db_YYYYMMDD.dump`
4. **啟動服務**：`sudo systemctl start netbox`

---

## 4. 常見問題排除 (Troubleshooting)

### 4.1 錯誤：`ConnectionRefusedError`
- **可能原因**：NetBox、LibreNMS 或 GLPI 伺服器斷線，或 API 網址填寫錯誤。
- **檢查方法**：確認 `.env` 中的 `URL` 參數是否能從本機以 `curl` 存取。

### 4.2 錯誤：`HTTP 403 Forbidden / 401 Unauthorized`
- **可能原因**：API Token 過期或權限不足。
- **檢查方法**：在 NetBox 管理介面檢查 Token 狀態，並確認 `NETBOX_TOKEN` 在 `.env` 中正確無誤。

### 4.3 新設備沒有出現在 NetBox 中
- **可能原因**：`AUTO_CREATE_NEW` 設為 `False` (預設)。
- **操作方法**：檢查 `/var/log/it_nexus/sync_librenms.log`，若看到 `[發現新設備] ... - AUTO_CREATE_NEW=False, 跳過`，則需手動建立或開啟該設定。

### 4.4 GLPI 搜尋不到設備
- **可能原因**：NetBox 設備狀態不是 `Active`，或 Serial Number 缺失。
- **解決方法**：確認 NetBox 中設備狀態。

---

## 5. 資料庫常用查詢 (SQL)

若需直接檢視 NetBox 資料庫狀態：
```bash
sudo -u postgres psql netbox

# 查詢所有除役中的設備
SELECT name, serial FROM dcim_device WHERE status = 'decommissioning';
```
