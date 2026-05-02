#!/bin/bash
# 華南永昌持股同步 — 一鍵啟動
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 檢查 Python
if ! command -v python3 &>/dev/null; then
    echo "❌ 找不到 python3，請先安裝 Python 3.10+"
    exit 1
fi

# 檢查 playwright
if ! python3 -c "import playwright" 2>/dev/null; then
    echo "📦 安裝依賴..."
    pip3 install -r requirements.txt
    echo "📦 安裝 Chromium..."
    playwright install chromium
fi

# 建立輸出目錄
mkdir -p output

echo ""
echo "🏦 華南永昌持股同步"
echo "========================"
echo ""
echo "選擇模式："
echo "  1) 探索模式（第一次使用，手動操作 + 自動抓取）"
echo "  2) 自動模式（需先設定 .env）"
echo "  3) 自動模式 + debug 截圖"
echo ""
read -p "請選擇 [1/2/3]: " choice

case $choice in
    1)
        python3 explore.py
        ;;
    2)
        if [ ! -f .env ]; then
            echo "⚠️ 找不到 .env 檔案"
            echo "   請複製 .env.example 為 .env 並填入帳密"
            echo "   cp .env.example .env"
            exit 1
        fi
        python3 entrust_sync.py --auto --headed
        ;;
    3)
        if [ ! -f .env ]; then
            echo "⚠️ 找不到 .env 檔案"
            exit 1
        fi
        python3 entrust_sync.py --auto --headed --debug
        ;;
    *)
        echo "無效選擇，啟動探索模式..."
        python3 explore.py
        ;;
esac