# IT_Nexus 同步指南 (Project Synchronization Guidelines)

本文件說明如何將私有的 `IT_Nexus` 工作區變更同步到公開的 `https://github.com/huckly/IT_Nexus` 儲存庫。

## 專案架構說明
- **私有工作區**: `/Users/randall/dotfiles/workspaces/IT_Nexus` (此處包含敏感設定與完整開發環境)
- **公開儲存庫**: `https://github.com/huckly/IT_Nexus` (僅包含此目錄的公開版本，不含敏感資料)

## 同步與清理機制 (Sanitization & Single Commit)
為了徹底保護敏感資料，同步腳本會自動進行以下處理：
1. **隱私資料清理**: 會自動掃描所有設定檔，將真實的 IPv4 位址替換為安全的虛擬位址 (例如 `198.51.100.x`)，並將網域名稱替換為 `example.com`。
2. **無歷史紀錄 (Single Commit)**: 腳本每次同步時都會建立一個全新的臨時儲存庫，並執行強制推送 (Force Push)。這確保公開儲存庫**不會保留任何先前的 Git 歷史紀錄**，避免從舊的 Commits 中洩漏敏感資料。

## 如何執行同步

在您的工作區根目錄 (`dotfiles/workspaces/IT_Nexus`) 執行以下指令：

```bash
./scripts/sync_it_nexus.sh
```

### 腳本執行流程
1.  **建立臨時目錄**: 複製所有檔案 (自動排除 `.git` 及密碼檔)。
2.  **執行資料清理**: 呼叫 `scripts/sanitize_data.py` 進行 IP 與網域替換。
3.  **建立全新版本**: 在臨時目錄中執行 `git init` 並加入所有檔案。
4.  **強制推送**: 將這個只有一個提交 (Commit) 的乾淨版本強制推送到 GitHub 上的 `it_nexus/main`。
5.  **清理**: 刪除臨時目錄。

> [!CAUTION]
> 這是 **單向同步** 且會 **覆蓋公開儲存庫的所有紀錄**。任何直接在公開 `IT_Nexus` 上所做的變更與提交歷史都會在同步時被清除。請務必只在您的 `dotfiles/workspaces/IT_Nexus` 目錄中進行修改。

## 前置設定 (已完成)
若需在其他環境重新設定，請執行：
1.  新增遠端: `git remote add it_nexus git@github.com:huckly/IT_Nexus.git`
2.  確保 `scripts/sync_it_nexus.sh` 具有執行權限: `chmod +x scripts/sync_it_nexus.sh`
