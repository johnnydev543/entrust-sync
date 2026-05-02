#!/bin/bash
# 華南永昌持股同步 — 一鍵啟動
set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# 檢查 Python
if ! command -v python3 &>/dev/null; then
    echo "❌ 找不到 python3"
    exit 1
fi

# 檢查 playwright
if ! python3 -c "import playwright" 2>/dev/null; then
    echo "📦 安裝依賴..."
    pip3 install -r requirements.txt
    echo "📦 安裝 Chromium..."
    playwright install chromium
fi

mkdir -p output

echo ""
echo "🏦 華南永昌持股同步 v3"
echo "========================"
echo ""
echo "選擇模式："
echo "  1) 探索模式（手動操作，推薦第一次用）"
echo "  2) 自動模式（需先設定 .env + 已安裝過憑證）"
echo "  3) 清除瀏覽器 profile（重新來過）"
echo ""
read -p "請選擇 [1/2/3]: " choice

case $choice in
    1)
        python3 explore.py
        ;;
    2)
        if [ ! -f .env ]; then
            echo "⚠️ 找不到 .env"
            echo "   cp .env.example .env  # 然後填入帳密"
            exit 1
        fi
        python3 entrust_sync.py --auto
        ;;
    3)
        echo "⚠️ 這會刪除瀏覽器 profile（含憑證）"
        read -p "確定嗎？ [y/N]: " confirm
        if [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
            rm -rf browser_profile/
            echo "✅ 已清除"
        fi
        ;;
    *)
        echo "啟動探索模式..."
        python3 explore.py
        ;;
esac