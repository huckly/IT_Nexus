# IT Nexus (IT 樞紐計畫) - Project Tasks

- [ ] **Phase 1: NetBox 建置 (New Host)**
    - [ ] 準備 Ubuntu 24.04 主機 (User 待建置)
    - [ ] 系統基礎設定 (IP, DNS, NTP, Docker)
    - [ ] 部署 NetBox (使用 Docker Compose)
    - [ ] 建立 Admin 帳號與 API Key

- [ ] **Phase 2: 系統整合 (Integration)**
    - [ ] **LibreNMS + NetBox** (整合現有 LibreNMS)
        - [ ] 設定 LibreNMS API 連線 (Target: 198.51.100.1)
        - [ ] 啟用 NetBox Integration
        - [ ] 驗證 Device Import
    - [ ] **NetBox -> GLPI** (整合現有 GLPI)
        - [ ] 確認 GLPI 版本與 API 開啟
        - [ ] 部署同步 Script


- [ ] **Phase 3: 進階自動化 (Optional)**
    - [ ] 設定 LibreNMS Alert Webhook
    - [ ] 開發 Webhook Handler (Middleware) 自動開立 GLPI 工單
    - [ ] 整合測試與驗證

- [ ] **Documentation & Handoff**
    - [ ] 撰寫架構文件
    - [ ] 撰寫維運手冊 (SOP)
