# 華南永昌持股同步工具

在本地電腦執行的瀏覽器自動化腳本，自動登入華南永昌數位網，抓取持股與交易紀錄。

## ⚠️ 安全提醒

- 帳號密碼存在**你自己的電腦**上，不經過任何雲端服務
- OTP 驗證碼需要手動輸入（無法繞過）
- 腳本只做**讀取**，不會下單或修改任何資料
- 建議用環境變數或 `.env` 檔管理密碼，不要 hardcode

## 安裝

```bash
cd entrust-sync
pip install -r requirements.txt
playwright install chromium
```

## 使用方式

### 1. 互動模式（首次使用推薦）

```bash
python entrust_sync.py
```

會自動開啟瀏覽器，你需要：
1. 輸入身分證字號和密碼
2. 輸入 OTP 驗證碼
3. 等待腳本自動抓取資料

### 2. 自動模式（設定好 .env 之後）

```bash
cp .env.example .env
# 編輯 .env 填入你的帳號密碼
python entrust_sync.py --auto
```

### 3. 匯出結果

抓取完成後，資料會存在 `output/` 目錄：
- `holdings_YYYY-MM-DD.json` — 持股明細
- `transactions_YYYY-MM-DD.json` — 交易紀錄

## 流程

```
開啟瀏覽器 → 登入頁面 → 輸入帳密 → OTP驗證(手動)
→ 進入帳務查詢 → 抓取持股明細 → 抓取交易紀錄 → 存檔 → 關閉
```