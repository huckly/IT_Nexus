# IT Nexus 專案指導原則 (Project Guidelines)

本目錄存放 IT Nexus 專案的核心需求、評估報告與發展藍圖。所有開發人員與維運人員在進行系統變更時，應參考本目錄文件。

## 文件索引

### 1. [核心需求與指導原則 (CORE_REQUIREMENTS.md)](CORE_REQUIREMENTS.md)
> **必讀**。定義了本專案必須滿足的 5 大核心業務目標（掌握設備、即時異動、即時告警、組態追蹤、事件閉環）。

### 2. [改善藍圖 (IMPROVEMENT_ROADMAP.md)](IMPROVEMENT_ROADMAP.md)
> 定義了專案的優先改善順序 (Delta from v5.4)。
> - **P0**: 提高同步頻率、變更通知、組態備份。
> - **P1**: 工單閉環、告警擴充、IM 整合。

### 3. [2026 評估報告 (EVALUATION_REPORT_2026.md)](EVALUATION_REPORT_2026.md)
> 2026/02/17 由資訊部經理進行的詳細功能審查與差距分析報告。

---

## 快速檢核 (Quick Check)

在提交任何程式碼或架構變更前，請自問：
- [ ] 這個變更是否讓設備資訊更準確？(Req #1)
- [ ] 這個變更是否能即時通知相關人員？(Req #2, #3)
- [ ] 這個變更是否有留下記錄 (Log/Ticket)？(Req #4, #5)
