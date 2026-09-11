#!/bin/bash
# ==============================================================================
# QBot (bản gọn) — khởi động bot, HỖ TRỢ ĐA TÀI KHOẢN
#
#   ./start_all_bots.sh              → chạy TẤT CẢ tài khoản khai trong config
#   ./start_all_bots.sh kh_a         → chỉ chạy tài khoản kh_a
#   ./start_all_bots.sh --force      → bỏ qua kiểm tra "đang chạy"
#
#   QBOT_CONFIG=khac.ini ./start_all_bots.sh   → dùng file config khác
#
# Bản này chỉ chạy 5 bot cần thiết. Các bot đã nghỉ (hd_update_price,
# hd_track_30_prices, hd_periodic_report, hd_order_123) KHÔNG có trong thư mục.
# ==============================================================================
cd "$(dirname "$0")" || exit 1

CONFIG_FILE="${QBOT_CONFIG:-config.ini}"
FORCE=0; SKIPPED=0; ARGS=()
for a in "$@"; do
    case "$a" in
        --force|-f) FORCE=1 ;;
        *) ARGS+=("$a") ;;
    esac
done
set -- "${ARGS[@]}"

echo "========================================"
echo "QBot - Khởi động (bản gọn)"
echo "========================================"

command -v python3 >/dev/null 2>&1 || { echo "❌ Không tìm thấy Python3"; exit 1; }
[ -f "$CONFIG_FILE" ] || { echo "❌ Không tìm thấy $CONFIG_FILE"; exit 1; }

read_accounts() {
    python3 - "$CONFIG_FILE" <<'PY'
import configparser, sys
c = configparser.ConfigParser(inline_comment_prefixes=(';',))
c.read(sys.argv[1], encoding='utf-8')
print(' '.join(a.strip() for a in c.get('global','accounts',fallback='').split(',') if a.strip()))
PY
}

if [ $# -gt 0 ]; then ACCOUNTS="$*"; else ACCOUNTS="$(read_accounts)"; fi

# Chế độ SHEET TỔNG: danh sách tài khoản nằm trên Google Sheet, không nằm ở đây
SHEET_MODE="$(python3 - "$CONFIG_FILE" <<'PY2'
import configparser, sys
c = configparser.ConfigParser(inline_comment_prefixes=(';',))
c.read(sys.argv[1], encoding='utf-8')
print('1' if c.get('global', 'config_spreadsheet_id', fallback='').strip() else '')
PY2
)"

# Chống khởi động TRÙNG: 2 bộ bot cùng key = ĐẶT LỆNH TRÙNG
is_running() {
    local PIDDIR="$1" f PID
    [ -d "$PIDDIR" ] || return 1
    for f in "$PIDDIR"/*.pid; do
        [ -f "$f" ] || continue
        PID="$(cat "$f" 2>/dev/null)"
        [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null && return 0
    done
    return 1
}

start_account() {
    local ACC="$1" LABEL LOGDIR PIDDIR
    if [ -z "$ACC" ]; then
        LABEL="(1 tài khoản)"; LOGDIR="logs"; PIDDIR="pids"; unset QBOT_ACCOUNT
    else
        LABEL="[$ACC]"; LOGDIR="logs/$ACC"; PIDDIR="pids/$ACC"; export QBOT_ACCOUNT="$ACC"
    fi
    mkdir -p "$LOGDIR" "$PIDDIR"

    if is_running "$PIDDIR" && [ "$FORCE" != "1" ]; then
        echo ""
        echo "⛔ $LABEL ĐANG CHẠY — bỏ qua để tránh đặt lệnh TRÙNG."
        echo "   Khởi động lại:  ./stop_all_bots.sh ${ACC:--y}  rồi chạy lại"
        SKIPPED=$((SKIPPED+1)); return
    fi

    echo ""
    echo "──────────────────────────────────────"
    echo "▶ Khởi động $LABEL"
    echo "──────────────────────────────────────"

    run_bot() {
        local FILE="$1" DESC="$2" NAME
        NAME="$(basename "$FILE" .py)"
        nohup python3 "$FILE" > "$LOGDIR/$NAME.log" 2>> "$LOGDIR/error.log" &
        echo $! > "$PIDDIR/$NAME.pid"
        echo "  ✔ $DESC (PID $!)"
        sleep 1
    }

    run_bot hd_order_multi.py                     "Đặt lệnh + SL/TP"
    run_bot hd_update_cho_va_khop.py              "Chờ và khớp (NGUỒN CẤP SL/TP)"
    run_bot hd_update_all.py                      "Số dư → J1:M2"
    run_bot hd_alert_possition_and_open_order.py  "Cảnh báo"
    run_bot hd_cancel_orders_schedule.py          "Hủy lệnh treo quá lâu"
}

if [ -n "$SHEET_MODE" ] && [ $# -eq 0 ]; then
    echo "📄 Chế độ SHEET TỔNG — mỗi bot là 1 tiến trình ĐIỀU PHỐI: tự mở tiến trình"
    echo "   con cho từng tài khoản đang Bật trên sheet, và tự bật lại khi cấu hình đổi."
    start_account ""; TOTAL=1
elif [ -z "$ACCOUNTS" ]; then
    echo "ℹ️  Config không khai 'accounts' → chế độ 1 tài khoản"
    start_account ""; TOTAL=1
else
    echo "📋 Tài khoản sẽ chạy: $ACCOUNTS"
    TOTAL=0
    for ACC in $ACCOUNTS; do start_account "$ACC"; TOTAL=$((TOTAL+1)); done
fi

echo ""
echo "========================================"
if [ "$SKIPPED" -gt 0 ]; then
    echo "✅ Đã khởi động $((TOTAL-SKIPPED))/$TOTAL tài khoản (bỏ qua $SKIPPED vì đang chạy)"
else
    echo "✅ Đã khởi động $TOTAL tài khoản — $((TOTAL*5)) tiến trình"
fi
echo "========================================"
echo "Trạng thái: ./status.sh   |   Dừng: ./stop_all_bots.sh"
echo "========================================"
