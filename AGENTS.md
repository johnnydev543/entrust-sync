# AGENTS.md

AI 代理開發指引。使用者指南（安裝、兩種模式、憑證視窗限制、session 過期）見 [README.md](README.md)，勿重複其內容。

## 專案概觀

華南永昌證券（eztrade.entrust.com.tw）持股/交易明細同步工具。以 Playwright 開啟有頭瀏覽器登入，使用者手動完成 OTP 與憑證，再由腳本抓取表格匯出 JSON 至 `output/`。

## 指令

```bash
pip install -r requirements.txt          # playwright + python-dotenv
playwright install chromium              # 首次安裝瀏覽器
./run.sh                                 # 互動選單: 1) explore.py 2) entrust_sync.py --auto 3) 重置 browser_profile/
python3 explore.py                       # 探索模式（逐步截圖 + full_sync_*.json 摘要）
python3 entrust_sync.py --auto           # 自動填入帳密（需 .env: ENTRUST_ACCOUNT / ENTRUST_PASSWORD）
python3 debug_popup.py                   # popup 除錯工具，寫 debug_events.json
```

- Python 3.9+（使用 `tuple[str, str]` 等 builtin generics）。
- 無測試、無 linter、無 CI。驗證方式是實際跑腳本——**會開啟有頭瀏覽器並有 `input()` 互動提示**，不是可自動化執行的流程。

## 架構

三支獨立腳本，皆為扁平函式 + 模組全域變數（無 class、無共用模組）：

| 檔案 | 用途 |
|---|---|
| `entrust_sync.py` | 自動模式：argparse（`--auto`、`--debug`）、自動填帳密、抓持股與交易明細 |
| `explore.py` | 探索模式：同樣抓取邏輯，另注入 popup logger、逐步截圖、寫 `full_sync_*.json` |
| `debug_popup.py` | 診斷 popup 空白問題：攔截 `window.open`/dialog/response 事件 |

共用邏輯（`capture_all_tables`、dialog/popup handler、launch/init-script 區塊）在**三個檔案中是複製貼上的副本**——修改其中一個必須同步其他兩個，或先重構成共用模組。

輸出檔名慣例：`name_YYYY-MM-DD.json`（`date.today().isoformat()`）、截圖用 `HHMMSS`。`output/` 與 `browser_profile/` 皆在 `.gitignore` 中。

## 關鍵規則（違反會弄壞使用者環境）

1. **絕不修改或刪除 `browser_profile/`**——內含已安裝的客戶端憑證與活躍 session。重置只能經由 `run.sh` 選項 3，且會迫使使用者重跑 Windows 憑證安裝流程。
2. **不可改成 headless**——登入需要手動 OTP/驗證碼與 ActiveX 憑證元件，必須 `headless=False` + `channel="msedge"`（失敗時 fallback 到 bundled Chromium）。
3. **popup 處理順序不可動**——依初始 URL 立即關閉 `TransPage.aspx` popup（**不可先等 load**，等待會觸發 dialog 死鎖）；`about:blank` popup 必須保留（憑證流程需要）。
4. **`window.open` override 對非 TransPage URL 必須回傳真正的 Window**——回傳 `null` 會弄壞憑證表單提交。
5. **selector 全部是 guess-list fallback chain**（舊 ASP.NET 網站：frames、`txtLoginID`、`#btnLogin`）。修改時保留「依序嘗試多個 selector」的模式，勿假設單一 selector 永遠有效。

## 程式碼慣例

- 全部 UI/註解文字使用**繁體中文**；新增輸出訊息也用繁中。
- 使用 `print()` + emoji 前綴，不用 `logging` 模組——遵循現有風格。
- 大量的 `try/except Exception: pass` 是**刻意的**（容忍頁面 race condition），不要「修好」它。
- 憑證只存在 `.env`（`ENTRUST_ACCOUNT`/`ENTRUST_PASSWORD`，見 `.env.example`）；log 中永遠遮罩（如 `account[:3]***`），勿輸出完整帳密。
- alert/confirm/prompt 一律自動 accept（`on_dialog` + `add_init_script` 攔截 `window.alert/confirm`）；`add_init_script` 是刻意的（跨導航存活），勿改回 `page.evaluate`。
- 腳本間的差異用模組常數表達（`LOGIN_URL`、`USER_DATA_DIR`、`DEFAULT_TIMEOUT = 30_000`），維持現有的頂部常數區塊。