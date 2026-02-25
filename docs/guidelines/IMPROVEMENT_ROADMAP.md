# IT Nexus 改善藍圖 (Improvement Roadmap)

基於 2026 年 2 月的 [評估報告](EVALUATION_REPORT_2026.md)，本專案的優先改善項目如下。

## ✅ 2026/02 已完成里程碑 (Completed Milestones)

- **[Core] 同步腳本升級 v5.6**:
    - 修正 `Int` 類型錯誤與 `ProLiant` 廠商對應問題。
    - 新增 **IP 地址同步** (自動建立 Interface 與 Primary IP)。
    - 新增 **Platform/OS 版本同步** (自動處理 Windows/VMware/Generic 平台)。
    - 解決 **重複設備 (Duplicate Devices)** 造成的資料不一致問題。
- **[Real-time] Webhook 機制修復**:
    - 修正 JSON Payload 解析錯誤 (List vs Dict)。
    - 實現 LibreNMS 新增/告警即時觸發 NetBox 同步。

## 🔴 P0 - 立即改善 (Immediate Action)

針對嚴重影響「即時性」與「可追溯性」的缺口進行修補。

- [x] **提高同步頻率 / 即時同步**
    - **狀態**：✅ 已完成
    - **對策**：
        1. 部署 Systemd Timer (每 15 分鐘執行一次完整同步)。
        2. 修復 Webhook Receiver，實現 LibreNMS 異動即時推播。
    - **效益**：縮短資料落差視窗 (Requirement #2)。
    
- [ ] **建立變更通知機制**
    - **目標**：當同步腳本偵測到新設備、狀態改變或關鍵欄位異動時，主動發送通知 (Email/IM)。
    - **效益**：實現「第一時間知道異動」(Requirement #2)。

- [ ] **導入組態備份 (Oxidized)**
    - **目標**：整合 Oxidized 與 LibreNMS，定期備份 Switch/Firewall Config。
    - **效益**：實現「參數調整追蹤」(Requirement #4)。

## 🟡 P1 - 短期目標 (Short-term Goals)

針對「告警完整性」與「工單閉環」進行優化。

- [ ] **工單自動化閉環**
    - **目標**：當 LibreNMS 告警恢復 (Recovery) 時，自動更新或關閉對應的 GLPI 工單。
    - **效益**：減少無效工單，確保狀態同步 (Requirement #5)。

- [ ] **強化工單內容**
    - **目標**：修改 GLPI 工單範本，強制要求填寫「根因分析」與「處理方式」。
    - **效益**：累積知識庫，落實事後檢討 (Requirement #5)。

- [ ] **擴充告警範圍**
    - **目標**：將 CPU、Memory、Disk、溫度、流量異常等納入自動開單範圍。
    - **效益**：全面掌握設備狀況 (Requirement #3)。

- [ ] **整合即時通訊 (IM)**
    - **目標**：對接 LINE Notify 或 Microsoft Teams，發送 Critical 告警。
    - **效益**：提升反應速度。

## 🟢 P2 - 中長期目標 (Medium-term Goals)

針對「管理決策支援」的功能。

- [ ] **建立管理儀表板 (Grafana)**
    - **目標**：整合各方數據，提供給 IT 經理的統一視圖。
    
- [ ] **資產保固提醒**
    - **目標**：自動寄送保固即將到期之設備清單。

- [ ] **SLA / Uptime 報表**
    - **目標**：定期產出服務水準報告。
