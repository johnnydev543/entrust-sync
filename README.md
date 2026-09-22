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

程式預設啟動 Chromium，並使用 **persistent context**（`browser_profile/`
目錄）保留 cookies、網站儲存狀態與瀏覽器設定。登入成功與正常關閉時，程式
也會在同一目錄保存 session cookies，讓容器重建後可重用仍未過期的登入環境。
券商伺服器端已失效的 session 仍必須重新登入。憑證私鑰
也可能由作業系統 Keychain／憑證儲存區或網站的 WebCA 機制管理，因此不應
假設所有憑證資料都只存在 `browser_profile/`。

Docker 內的 HTTP 與媒體快取會寫入 `/dev/shm`；Chromium 固定建立的
`Cache`、`Code Cache`、`GPUCache` 與 shader cache 目錄則由 Compose 掛載為
64 MiB 的 nested `tmpfs`。這些目錄名稱仍然可見，但內容只存在記憶體，容器
重建後不保留。cookies、Local Storage、IndexedDB、session restore 與
Chromium `ClientCertificates` 繼續保存在 `browser_profile/`。這些網站狀態
可能共同參與券商登入與憑證驗證，不應只保留單一 cookie 檔。

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

### Linux Docker GUI／noVNC

伺服器沒有實體桌面時，可使用專案內的 `compose.yaml` 啟動持久化的 Linux
GUI、Chromium、HTTPS noVNC 與資料 API：

```bash
cp .env.example .env
mkdir -p tls browser_profile output
```

在 `.env` 設定：

```dotenv
ENTRUST_API_TOKEN=<使用 openssl rand -hex 32 產生>
ENTRUST_VNC_PASSWORD=<8 位英數密碼>
ENTRUST_API_HOST=0.0.0.0
ENTRUST_API_PORT=8888
```

產生區網用自簽憑證；請將範例 IP 換成伺服器實際位址：

```bash
SERVER_IP=192.168.1.50
openssl req -x509 -newkey rsa:3072 -sha256 -nodes -days 825 \
  -keyout tls/novnc.key \
  -out tls/novnc.crt \
  -subj "/CN=$SERVER_IP" \
  -addext "subjectAltName=IP:$SERVER_IP,IP:127.0.0.1,DNS:localhost"
chmod 600 tls/novnc.key
```

啟動服務：

```bash
docker compose up -d --build
```

修改 `.env`（尤其是 `ENTRUST_API_TOKEN` 或 `ENTRUST_VNC_PASSWORD`）後，
既有容器不會自動重新載入新值。請強制重建容器：

```bash
docker compose up -d --force-recreate
```

否則 helper 可能讀到新 token，但 API 容器仍使用舊 token，導致請求回傳
`401 Unauthorized`。

- noVNC：`https://<server-ip>:6080/`；根路徑會導向 `vnc.html`，不開放目錄列表。
- API：`https://<server-ip>:8888/docs`；受保護端點需要 Bearer Token。
- 同機 agent：`./scripts/entrust-api /api/v1/inventory`。

同一張 TLS 憑證同時保護 noVNC 與 API。`ENTRUST_API_HOST` 與
`ENTRUST_API_PORT` 控制主機對外綁定；nginx 在容器內接收 HTTPS，再轉送至
僅監聽 `127.0.0.1:8889` 的 FastAPI，因此 8889 不會發布到主機。如需調整
對外位址或連接埠，只需修改 `.env` 後重建容器。自簽憑證首次使用時不會被瀏覽器自動信任；可將
`tls/novnc.crt` 匯入受信任裝置。不要把 `tls/`、`.env`、`browser_profile/`
或 `output/` 提交到 Git。

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
