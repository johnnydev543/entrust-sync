# 華南永昌持股同步工具 v3

在本地電腦執行的瀏覽器自動化腳本，抓取華南永昌持股與交易紀錄。

## ⚠️ 安全提醒

- 帳號與密碼只在華南登入頁由你手動輸入，程式不保存
- OTP 一定手動輸入
- 腳本只做**讀取**，不下單
- 憑證保存在 `browser_profile/`，不會上傳

## 安裝

```bash
cd entrust-sync
pip install -r requirements.txt
playwright install chromium
```

## 使用方式

```bash
./run.sh
```

程式會同時啟動 API 與有頭瀏覽器。你只需要在瀏覽器手動完成帳密、OTP
與憑證流程，不需要自行進入持股或交易頁。登入完成後，API 請求會跨 iframe
自動開啟對應查詢頁、擷取最新資料並回傳。

API 文件位於 `http://127.0.0.1:8000/docs`。若要重設瀏覽器 profile，執行
`./run.sh reset`；這會要求再次確認。

## 重要：憑證視窗

華南永昌的憑證申請視窗是 **Windows 元件**（ActiveX/COM），
不是一般網頁彈出視窗，**沒有 URL，腳本無法自動操作**。

解法：用 **persistent context**（`browser_profile/` 目錄），
憑證只需安裝一次，之後每次啟動都會帶著。

如果需要重新安裝憑證：
```bash
rm -rf browser_profile/
./run.sh  # 重新走一次憑證流程
```

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

API 預設只接受這台 Mac 自己的連線。若要讓同一個 Wi-Fi／LAN 內的手機、
電腦或 AI agent 存取，請依下列步驟啟動區網模式。

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
cd /Volumes/Kingston_1T/Codes/entrust-sync
./run.sh
```

若 macOS 詢問是否允許 Python 接收連線，請選擇允許。

4. 查詢 Mac 的區網 IP（Wi-Fi 通常是 `en0`）：

```bash
ipconfig getifaddr en0
```

假設結果是 `192.168.1.50`，其他裝置的 API 文件網址就是：

```text
http://192.168.1.50:8000/docs
```

5. 遠端呼叫 API 時加入 Bearer Token：

```bash
curl \
  -H "Authorization: Bearer 你的Token" \
  http://192.168.1.50:8000/api/v1/inventory
```

在 Swagger 的端點測試畫面中，`authorization` 欄位需填入完整內容：

```text
Bearer 你的Token
```

注意事項：

- 只有同一 Wi-Fi／LAN 或彼此可路由的私人網路才能連線。
- 訪客 Wi-Fi 常會開啟裝置隔離，因此可能無法連到 Mac。
- 不要在路由器設定 port forwarding，也不要將 API 暴露到公開網路。
- 不要把 `ENTRUST_API_TOKEN` 寫入 Git 或傳給不受信任的人。
- 關閉終端或按 `Ctrl+C` 停止服務後，其他裝置便無法繼續存取。

對帳單範例：

```text
GET /api/v1/statements/today
GET /api/v1/statements/today?stock_code=2330
GET /api/v1/statements/history?date_from=2026-08-01&date_to=2026-09-18
GET /api/v1/statements/history?date_from=2026-08-01&date_to=2026-09-18&stock_code=2330
GET /api/v1/inventory
GET /api/v1/profit-loss/unrealized
GET /api/v1/profit-loss/unrealized?stock_code=2330
GET /api/v1/profit-loss/realized
GET /api/v1/profit-loss/realized?stock_code=2330
```

省略 `stock_code` 代表查詢全部股票。歷史查詢會在送往華南網站前驗證日期
區間，避免超出站方「最近兩年、單次最多六個月」的限制。

庫存資料的 `depository`、`margin`、`short` 單位為 `lot`（張），`odd_lot`
單位為 `share`（股）。每筆庫存另有 `share_summary`，將整張乘以 1,000 後
提供 `cash_shares`、`margin_shares`、`short_shares`、`long_shares` 與
`net_shares`，避免零股數量被誤認為張數。
