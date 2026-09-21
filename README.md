# 華南永昌持股同步工具 v3

在本地電腦執行的瀏覽器自動化腳本，抓取華南永昌持股與交易紀錄。

## ⚠️ 安全提醒

- 帳號與密碼只在華南登入頁由使用者手動輸入，程式不保存
- OTP 一定手動輸入
- 腳本只做**讀取**，不下單
- `browser_profile/` 可能含有敏感的登入與瀏覽器狀態，不會上傳

## 安裝

本專案使用 Python、Playwright 與 FastAPI，沒有直接依賴 Windows
ActiveX/COM。瀏覽器自動化程式可跨平台執行，但券商的首次憑證申請流程可能
因作業系統、瀏覽器及憑證儲存方式而異。

macOS／Linux：

```bash
cd entrust-sync
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m playwright install chromium
```

Windows PowerShell：

```powershell
cd entrust-sync
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
```

## 使用方式

```bash
./run.sh
```

`run.sh` 適用於 macOS、Linux、WSL 與 Git Bash。Windows PowerShell 可直接
執行：

```powershell
.\.venv\Scripts\python.exe api_server.py
```

程式會同時啟動 API 與有頭瀏覽器。使用者只需在瀏覽器手動完成帳密、OTP
與憑證流程，不需要自行進入持股或交易頁。登入完成後，API 請求會跨 iframe
自動開啟對應查詢頁、擷取最新資料並回傳。

API 文件位於 `http://127.0.0.1:8000/docs`。若要重設瀏覽器 profile，執行
`./run.sh reset`；這會要求再次確認。

## 重要：憑證與瀏覽器 profile

華南永昌的憑證申請流程可能開啟新頁籤、瀏覽器外的原生視窗，或由系統／
瀏覽器的憑證機制接手。這類介面不一定會出現在 Playwright 的 `page` 清單中，
因此腳本不嘗試自動操作；使用者需手動完成帳密、OTP 與憑證步驟。

程式使用 **persistent context**（`browser_profile/` 目錄）保留 cookies、
網站儲存狀態與瀏覽器設定，讓後續啟動可以重用已完成的登入環境。憑證私鑰
也可能由作業系統 Keychain／憑證儲存區或網站的 WebCA 機制管理，因此不應
假設所有憑證資料都只存在 `browser_profile/`。

`browser_profile/` 含有重要的登入與瀏覽器狀態，請勿手動刪除或修改。只有在
確定需要重建環境，且願意重新完成登入與憑證流程時，才執行：

```bash
./run.sh reset
```

### 平台相容性

| 平台 | 啟動方式 | 注意事項 |
|---|---|---|
| macOS | `./run.sh` | 支援有頭 Edge／Chromium；憑證可能使用 Keychain |
| Linux 桌面 | `./run.sh` | 需要圖形桌面；首次憑證申請依券商支援情況而定 |
| Windows | PowerShell、WSL 或 Git Bash | 原生 PowerShell 直接執行 `api_server.py`；憑證可能使用 Windows 憑證儲存區 |

平台可啟動不代表券商的首次憑證申請已在所有作業系統與瀏覽器組合完成驗證。

## Session 有效期

華南永昌的 session 大約 **1 小時**過期。
腳本使用 persistent context 保存 cookies，
但超過 1 小時後需要重新登入（只需帳密 + OTP，不用重裝憑證）。

## 輸出

抓取結果存在 `output/` 目錄：
- `holdings_YYYY-MM-DD.json` — 持股明細
- `transactions_YYYY-MM-DD.json` — 交易紀錄
- `screenshot_*.png` — 各步驟截圖

## API（供 AI agent 使用）

API 預設只監聽本機 `http://127.0.0.1:8000`，互動文件位於
`http://127.0.0.1:8000/docs`，OpenAPI 規格位於 `/openapi.json`。

| 路徑 | 用途 |
|---|---|
| `GET /health` | 健康檢查 |
| `GET /api/v1/dates` | 列出持股與交易的可查詢日期 |
| `GET /api/v1/statements/today` | 自動查詢當日對帳單；可選填 `stock_code` |
| `GET /api/v1/statements/history` | 自動查詢歷史對帳單；必填 `date_from`、`date_to`，可選填 `stock_code` |
| `GET /api/v1/statements/history/full` | 自動分段取得最近兩年的完整對帳單 |
| `GET /api/v1/portfolio/opening-inventory` | 以現有庫存與後續成交反推指定日期的期初現股數量 |
| `GET /api/v1/inventory` | 自動查詢彙總庫存 |
| `GET /api/v1/profit-loss/unrealized` | 自動查詢未實現損益；可選填 `stock_code` |
| `GET /api/v1/profit-loss/realized` | 自動查詢已實現損益；可選填 `stock_code` |
| `GET /api/v1/holdings` | 自動重新擷取現有持股；可加 `?refresh=false` 只讀快取 |
| `GET /api/v1/transactions/today` | 自動重新擷取今日交易 |
| `GET /api/v1/transactions?date=YYYY-MM-DD` | 指定日期交易 |
| `GET /api/v1/transactions/history` | 自動開啟歷史交易並擷取；支援 `date_from`、`date_to`、`limit` |

API 在登入完成後會自動操作查詢頁；它不會代替使用者完成登入。若要開放給
其他裝置，必須先設定 `ENTRUST_API_TOKEN`，呼叫時使用
`Authorization: Bearer <token>`；仍建議只在受信任的私人網路使用。

### 同一區網的其他裝置存取

API 預設只接受執行服務之裝置本身的連線。若要讓同一個 Wi-Fi／LAN 內的
手機、電腦或 AI agent 存取，請依下列步驟啟動區網模式。

1. 若尚未有 `.env`，先從範例建立：

```bash
cp .env.example .env
```

若 `.env` 已存在，不要覆蓋，直接編輯並加入下列設定：

```dotenv
ENTRUST_API_HOST=0.0.0.0
ENTRUST_API_PORT=8000
ENTRUST_API_TOKEN=請換成長且隨機的字串
```

2. 產生一組長且隨機的 Token，將輸出的字串填入 `.env` 的
`ENTRUST_API_TOKEN`：

```bash
openssl rand -hex 32
```

3. 直接啟動；程式會自動載入專案根目錄的 `.env`：

```bash
cd /path/to/entrust-sync
./run.sh
```

若作業系統防火牆詢問是否允許 Python 接收區網連線，請依實際網路環境決定
是否允許；不應在公共網路開放此服務。

4. 查詢執行服務之裝置的區網 IP。常用指令如下：

```bash
# macOS（Wi-Fi 通常是 en0）
ipconfig getifaddr en0

# Linux
hostname -I
```

```powershell
# Windows PowerShell
ipconfig
```

假設結果是 `192.168.1.50`，其他裝置的 API 文件網址就是：

```text
http://192.168.1.50:8000/docs
```

5. 遠端呼叫 API 時加入 Bearer Token：

```bash
curl \
  -H "Authorization: Bearer <your-token>" \
  http://192.168.1.50:8000/api/v1/inventory
```

在 Swagger 的端點測試畫面中，`authorization` 欄位需填入完整內容：

```text
Bearer <your-token>
```

注意事項：

- 只有同一 Wi-Fi／LAN 或彼此可路由的私人網路才能連線。
- 訪客 Wi-Fi 常會開啟裝置隔離，因此裝置之間可能無法互相連線。
- 不要在路由器設定 port forwarding，也不要將 API 暴露到公開網路。
- 不要把 `ENTRUST_API_TOKEN` 寫入 Git 或傳給不受信任的人。
- 關閉終端或按 `Ctrl+C` 停止服務後，其他裝置便無法繼續存取。

對帳單範例：

```text
GET /api/v1/statements/today
GET /api/v1/statements/today?stock_code=2330
GET /api/v1/statements/history?date_from=2026-08-01&date_to=2026-09-18
GET /api/v1/statements/history?date_from=2026-08-01&date_to=2026-09-18&stock_code=2330
GET /api/v1/statements/history/full?date_from=2025-09-01&date_to=2026-09-21
GET /api/v1/portfolio/opening-inventory?as_of=2025-09-01
GET /api/v1/inventory
GET /api/v1/profit-loss/unrealized
GET /api/v1/profit-loss/unrealized?stock_code=2330
GET /api/v1/profit-loss/realized
GET /api/v1/profit-loss/realized?stock_code=2330
```

省略 `stock_code` 代表查詢全部股票。歷史查詢會在送往華南網站前驗證日期
區間，避免超出站方「最近兩年、單次最多六個月」的限制。
`history/full` 會自動處理六個月分段；`opening-inventory` 可精確反推
期初數量，但若原始買進早於站方兩年上限，精確成本仍需其他資料來源。

庫存資料的 `depository`、`margin`、`short` 單位為 `lot`（張），`odd_lot`
單位為 `share`（股）。每筆庫存另有 `share_summary`，將整張乘以 1,000 後
提供 `cash_shares`、`margin_shares`、`short_shares`、`long_shares` 與
`net_shares`，避免零股數量被誤認為張數。
