#!/bin/bash
# 華南永昌持股同步 — 一鍵啟動
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 固定使用專案的虛擬環境，避免套件與瀏覽器版本混用
PYTHON="$SCRIPT_DIR/.venv/bin/python"
if [ ! -x "$PYTHON" ]; then
    echo "❌ 找不到 .venv Python：$PYTHON"
    echo "   請先建立虛擬環境：python3 -m venv .venv"
    exit 1
fi

# 首次安裝 Playwright 時一併準備 Chromium
if ! "$PYTHON" -c "import playwright" 2>/dev/null; then
    echo "📦 安裝依賴..."
    "$PYTHON" -m pip install -r requirements.txt
    echo "📦 安裝 Chromium..."
    "$PYTHON" -m playwright install chromium
elif ! "$PYTHON" -c "import fastapi, uvicorn, dotenv" 2>/dev/null; then
    echo "📦 安裝 API 依賴..."
    "$PYTHON" -m pip install -r requirements.txt
fi

mkdir -p output

if [ "${1:-}" = "reset" ]; then
        echo "⚠️ 這會刪除瀏覽器 profile（含憑證）"
        read -p "確定嗎？ [y/N]: " confirm
        if [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
            rm -rf browser_profile/
            echo "✅ 已清除"
        fi
        exit 0
fi

echo "🏦 啟動華南永昌資料 API 與登入瀏覽器"
"$PYTHON" api_server.py
