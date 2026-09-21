# AGENTS.md

AI 代理開發指引。使用者指南（安裝、平台、憑證流程、Docker GUI、session
過期）見 [README.md](README.md)，勿重複其內容。

## 專案概觀

華南永昌證券（eztrade.entrust.com.tw）持股／交易明細同步工具。以 Playwright
開啟有頭瀏覽器，使用者手動完成登入、OTP 與憑證，再由常駐瀏覽器 worker
接收 FastAPI 請求、操作查詢頁並將結果輸出至 `output/`。

## 指令

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python -m playwright install chromium
./run.sh                                 # 啟動 API 與有頭瀏覽器
PYTHONPATH=. .venv/bin/python -m unittest discover -s tests -v
docker compose up -d --build             # Linux GUI／HTTPS noVNC 部署
```

- Python 3.9+（使用 `tuple[str, str]` 等 builtin generics）。
- 單元測試不取代實際登入驗證；瀏覽器登入流程需要人工操作。

## 架構

FastAPI 入口 + `entrust/` 共用套件：

| 檔案 | 用途 |
|---|---|
| `api_server.py` | FastAPI 路由、Token 驗證、輸入驗證與 lifespan |
| `entrust/config.py` | 共用常數：`SCRIPT_DIR`、`OUTPUT_DIR`、`USER_DATA_DIR`、`LOGIN_URL`、`DEFAULT_TIMEOUT`、`LAUNCH_ARGS` |
| `entrust/handlers.py` | `on_dialog`（自動 accept）、`on_popup`（非阻塞記錄）、`alert_log`、`reset_alert_log` |
| `entrust/capture.py` | `capture_all_tables`、`capture_aggregate_inventory`、`download_aggregate_inventory_xls`、`save_step` |
| `entrust/browser.py` | `launch_browser()`：Edge→Chromium fallback + `add_init_script`（webdriver 偽裝、alert/confirm/window.open 覆蓋）+ handler 註冊 |
| `entrust/live_sync.py` | 單一瀏覽器 worker、登入狀態偵測、工作 queue 與查詢操作 |
| `entrust/api_data.py` | 輸出檔案讀取、日期索引與快取資料查詢 |
| `entrust/portfolio.py` | 對帳單彙整、分段日期與期初庫存反推 |
| `inventory_export.py` | 站方 XLS → UTF-8 JSON/CSV 轉換（與 entrust/ 平行的獨立模組） |
| `Dockerfile` / `compose.yaml` | Linux GUI、HTTPS noVNC、API 與持久化 volume |

修改共用行為（selector、popup 處理、init script、表格擷取）一律改 `entrust/` 內的模組，**不要改回複製貼上**。

輸出檔名慣例：`name_YYYY-MM-DD.json`（`date.today().isoformat()`）、截圖用 `HHMMSS`。`output/` 與 `browser_profile/` 皆在 `.gitignore` 中。

## 關鍵規則（違反會弄壞使用者環境）

1. **絕不修改或刪除 `browser_profile/`**——內含敏感的瀏覽器狀態與活躍 session。重置只能由使用者明確執行 `./run.sh reset`，且會迫使使用者重跑登入與憑證流程。
2. **不可改成 headless**——登入需要手動帳密、OTP／驗證碼與可能由瀏覽器或系統接手的憑證流程，必須 `headless=False`；優先 Edge，失敗時 fallback 到 bundled Chromium。
3. **popup 處理順序不可動**——依初始 URL 立即關閉 `TransPage.aspx` popup（**不可先等 load**，等待會觸發 dialog 死鎖）；`about:blank` popup 必須保留（憑證流程需要）。
4. **`window.open` override 對非 TransPage URL 必須回傳真正的 Window**——回傳 `null` 會弄壞憑證表單提交。
5. **selector 全部是 guess-list fallback chain**（舊 ASP.NET 網站：frames、`txtLoginID`、`#btnLogin`）。修改時保留「依序嘗試多個 selector」的模式，勿假設單一 selector 永遠有效。

## 程式碼慣例

- 全部 UI/註解文字使用**繁體中文**；新增輸出訊息也用繁中。
- 使用 `print()` + emoji 前綴，不用 `logging` 模組——遵循現有風格。
- 大量的 `try/except Exception: pass` 是**刻意的**（容忍頁面 race condition），不要「修好」它。
- `.env`、`tls/`、`browser_profile/` 與 `output/` 都可能含秘密或金融資料，禁止提交。log 中不得輸出完整 Token、密碼、Cookie 或持股／交易內容。
- alert/confirm/prompt 一律自動 accept（`on_dialog` + `add_init_script` 攔截 `window.alert/confirm`）；`add_init_script` 是刻意的（跨導航存活），勿改回 `page.evaluate`。
- 腳本間的差異用模組常數表達（`LOGIN_URL`、`USER_DATA_DIR`、`DEFAULT_TIMEOUT = 30_000`），維持現有的頂部常數區塊。
