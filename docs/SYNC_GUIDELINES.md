# IT_Nexus 同步指南 (Project Synchronization Guidelines)

本文件說明如何將私有的 `IT_Nexus` 工作區變更同步到公開的 `https://github.com/huckly/IT_Nexus` 儲存庫。

## 專案架構說明
- **私有工作區**: `/Users/randall/dotfiles/workspaces/IT_Nexus` (此處包含敏感設定與完整開發環境)
- **公開儲存庫**: `https://github.com/huckly/IT_Nexus` (僅包含此目錄的公開版本)

## 同步機制
我們使用 `git subtree` 技術，將私有儲存庫中的特定子目錄 (`workspaces/IT_Nexus`) 推送至公開儲存庫的 `main` 分支。

## 如何執行同步

在您的工作區根目錄 (`dotfiles/workspaces/IT_Nexus`) 執行以下指令：

```bash
./scripts/sync_it_nexus.sh
```

### 腳本執行流程
1.  **建立臨時分支**: 將 `workspaces/IT_Nexus` 目錄隔離到一個臨時分支。
2.  **強制推送**: 將此分支強制推送 (force push) 到 GitHub 上的 `it_nexus/main`。
3.  **清理**: 刪除臨時分支。

> [!CAUTION]
> 這是 **單向同步**。任何直接在公開 `IT_Nexus` 儲存庫上所做的變更都會被此腳本覆蓋。請務必只在您的 `dotfiles/workspaces/IT_Nexus` 目錄中進行變更。

## 前置設定 (已完成)
若需在其他環境重新設定，請執行：
1.  新增遠端: `git remote add it_nexus git@github.com:huckly/IT_Nexus.git`
2.  確保 `scripts/sync_it_nexus.sh` 具有執行權限: `chmod +x scripts/sync_it_nexus.sh`
