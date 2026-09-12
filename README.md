# AAAS-TW｜會計政策判定作品

**以明確條件決定何時能產生分錄建議。**

我從會計流程自動化出發，逐漸關注資料來源、判定條件與錯誤追溯。這份作品公開 AAAS-TW 的一個真實模組：檢查交易事實、政策與科目對應，條件符合才產生分錄建議；資料不足或矛盾時，回傳原因。

| 想了解什麼 | 從這裡開始 |
|---|---|
| 會計問題與實際結果 | [代表案例](docs/CASE_STUDY.md) |
| 如何實作與檢查失敗情況 | [政策模組](src/domain/accounting/posting_policy.py) · [測試](tests/test_posting_policy.py) |
| 在完整系統中的位置 | [架構與範圍](docs/ARCHITECTURE.md) |

## 我的角色與 AI 分工

我的工作是提出需求、界定問題與範圍、要求 AI 修改。程式、文件、測試與修復由 AI 產出，測試也由 AI 執行；我尚未親自重跑或獨立驗證整套系統。

## 執行測試

使用 Python 3.11 以上，在儲存庫根目錄執行：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-test.txt
python -m pytest -q
```

Windows PowerShell 的啟用指令為 `.venv\Scripts\Activate.ps1`。

此公開版本由 AI 在獨立 Python 3.12.14 環境執行：**112 項測試通過**。未使用 GitHub Actions。原始檔案版本與雜湊見 [SOURCE.json](SOURCE.json)。

## 目前範圍

公開內容是獨立政策模組與合成資料測試，無須資料庫或外部服務。測試檢查函式行為；完整過帳、身分權限、外部證據真實性與專業會計適用性，均不在本庫驗證範圍內。使用範圍見 [LICENSE](LICENSE)。
