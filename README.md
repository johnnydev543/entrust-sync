# 華南永昌持股同步工具 v3

在本地電腦執行的瀏覽器自動化腳本，抓取華南永昌持股與交易紀錄。

## ⚠️ 安全提醒

- 帳密只存在你自己的電腦（`.env` 檔案）
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

### 第一次使用（推薦）

```bash
python explore.py
```

1. 瀏覽器開啟華南永昌登入頁
2. **手動登入**（帳密 + OTP）
3. **手動處理憑證視窗**（⚠️ 這是 Windows 元件，腳本無法自動操作）
4. 憑證會保存在 `browser_profile/`，之後不用再處理
5. 導航到想抓的頁面，按 Enter 抓取

### 之後使用

```bash
# 互動模式（手動操作 + 自動抓取）
python explore.py

# 自動模式（需設定 .env，帳密自動填入，OTP 仍手動）
cp .env.example .env  # 填入帳密
python entrust_sync.py --auto
```

### 一鍵啟動

```bash
./run.sh
# 選 1 = 探索模式
# 選 2 = 自動模式
# 選 3 = 清除 profile（重裝憑證）
```

## 重要：憑證視窗

華南永昌的憑證申請視窗是 **Windows 元件**（ActiveX/COM），
不是一般網頁彈出視窗，**沒有 URL，腳本無法自動操作**。

解法：用 **persistent context**（`browser_profile/` 目錄），
憑證只需安裝一次，之後每次啟動都會帶著。

如果需要重新安裝憑證：
```bash
rm -rf browser_profile/
python explore.py  # 重新走一次憑證流程
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