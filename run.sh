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

# 檢查 playwright
if ! "$PYTHON" -c "import playwright" 2>/dev/null; then
    echo "📦 安裝依賴..."
    "$PYTHON" -m pip install -r requirements.txt
    echo "📦 安裝 Chromium..."
    "$PYTHON" -m playwright install chromium
fi

check_browser_profile_available() {
    if pgrep -f -- "--user-data-dir=$SCRIPT_DIR/browser_profile" >/dev/null 2>&1; then
        echo "❌ 上一次同步程序仍在背景執行，無法再次開啟同一個 browser_profile。"
        echo "   只關閉瀏覽器視窗不會結束正在等待輸入的程序。"
        echo "   請回到上一次執行的終端按 Ctrl+C，再重新執行 ./run.sh。"
        exit 1
    fi
}

mkdir -p output

echo ""
echo "🏦 華南永昌持股同步"
echo "========================"
echo ""
echo "選擇模式："
echo "  1) 探索模式（登入後自行選擇要擷取的頁面）"
echo "  2) 自動模式（有設定 .env 時自動填入帳密）"
echo "  3) 清除瀏覽器 profile（重新來過）"
echo ""
read -p "請選擇 [1/2/3]: " choice

case $choice in
    1)
        check_browser_profile_available
        "$PYTHON" explore.py
        ;;
    2)
        if [ ! -f .env ]; then
            echo "⚠️ 找不到 .env"
            echo "   cp .env.example .env  # 然後填入帳密"
            exit 1
        fi
        check_browser_profile_available
        "$PYTHON" entrust_sync.py --auto
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
        check_browser_profile_available
        "$PYTHON" explore.py
        ;;
esac
