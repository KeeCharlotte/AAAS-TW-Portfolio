# AAAS-TW｜可追溯會計工作台

**把來源文件、會計處理、人工覆核與交付結果接在一起，讓每個數字能追查依據與處理過程。**

完整專案保存在私人庫，涵蓋來源查閱、草稿、獨立覆核與補件、過帳、對帳與異常處理、CSV 與佐證交付。本庫展示整體進度與實際成果，並公開一個完整政策模組及配套測試，供教授、招募者與工程師檢視。

目前是**受控的會計工作台原型**：已有合成資料整合流程實證；最新安全修正的完整回歸仍待補驗。

## 具體成果

| 已取得的結果 | 可查看的證據 |
|---|---|
| 三人分工流程：105 元草稿退回後，建立 210 元新版，重新獨立確認與核准，再由第三人過帳，匯出 3 行分錄 CSV | [實際畫面、CSV 與案例說明](docs/CASE_STUDY.md) |
| 公開政策模組：條件符合才產生分錄建議；來源不足、科目或金額矛盾時停止 | [完整程式](src/domain/accounting/posting_policy.py) · [112 項測試](tests/test_posting_policy.py) |
| 完整工程範圍、保留但暫緩的模組，以及未完成工作 | [完整功能、公開範圍與待辦](docs/ARCHITECTURE.md) |

以上流程使用合成資料。測試版本與結果見 [RESULTS.json](evidence/RESULTS.json)；尚無真實客戶成效或專業會計採信。

## 我的角色與 AI 分工

我的工作是提出需求、界定問題與範圍、要求 AI 修改。程式、文件、測試與修復由 AI 產出，測試也由 AI 執行；我尚未親自重跑、獨立驗證或除錯整套系統。

## 執行公開模組測試

使用 Python 3.11 以上，在儲存庫根目錄執行：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-test.txt
python -m pytest -q
```

Windows PowerShell 的啟用指令為 `.venv\Scripts\Activate.ps1`。

模組執行僅需 Python 標準函式庫；測試使用 pytest 9.0.2，無須資料庫或外部服務。公開版本已由 AI 在 Python 3.12.14 環境本地執行：**112 項測試通過**。這組測試驗證政策函式，完整工作台的歷史實證另列於案例。

原始檔案版本與雜湊見 [SOURCE.json](SOURCE.json)；使用範圍見 [LICENSE](LICENSE)。
