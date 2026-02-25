# IT Nexus 專案核心需求與指導原則 (Project Mandate)

本文件定義了 IT Nexus 專案必須滿足的業務目標與功能要求。所有開發與維運決策均應以此為依歸。

## 核心五大需求 (Core Requirements)

### 1. 全面掌握設備 (Asset Visibility)
- **目標**：掌握所有的 IT 基礎設施設備。
- **標準**：
    - 必須包含所有 IP 設備 (自動化) 與被動設備 (人工)。
    - 必須即時反映真實狀態 (Source of Truth)。
    - 必須分類明確 (Server/Network/IoT 等)。

### 2. 異動即時感知 (Change Awareness)
- **目標**：任何設備異動都可以在第一時間知道。
- **標準**：
    - 新設備上線、舊設備離線、關鍵參數 (IP/Serial) 變更時，必須主動通知。
    - 同步週期不應超過 **4 小時** (理想目標：即時/Event-driven)。

### 3. 異常即時告警 (Incident Alerting)
- **目標**：設備有狀況可以在第一時間知道。
- **標準**：
    - 覆蓋所有關鍵指標 (Ping, SNMP, Resource Usage)。
    - 告警需分級 (Critical/Warning) 並發送至正確管道 (IM/Email)。
    - **不僅僅是 Device Down**，還需包含效能與環境異常。

### 4. 組態變更追蹤 (Configuration Tracking)
- **目標**：出狀況後可以馬上知道設備任何參數做調整嗎。
- **標準**：
    - 必須具備網路設備組態備份 (Config Backup) 能力。
    - 必須能夠比對歷史版本差異 (Diff)。
    - 必須記錄「誰」在「什麼時候」改了「什麼」。

### 5. 事件閉環管理 (Incident Lifecycle)
- **目標**：狀況處理完之後，有記錄下發生原因跟處理方式嗎。
- **標準**：
    - 告警 → 工單 → 處理 → 結案 的完整流程。
    - 工單必須包含「根因 (Root Cause)」與「解決方案 (Resolution)」欄位。
    - 系統應協助自動關閉已恢復的告警工單。

---

## 進階管理期望 (Manager's Wish List)

除了上述核心需求，專案應朝以下方向演進：

1.  **管理儀表板 (Executive Dashboard)**：一頁式總覽 (Single Pane of Glass)。
2.  **資產生命週期 (Lifecycle Management)**：保固到期、EOS/EOL 提醒。
3.  **即時通訊整合 (ChatOps)**：LINE/Teams/Slack 雙向整合。
4.  **合規與稽核 (Compliance)**：定期產出資產盤點與權限審計報表。
5.  **容量規劃 (Capacity Planning)**：基於趨勢預測資源擴充需求。
6.  **SLA 追蹤**：量化可用性與修復時間 (MTTR)。
