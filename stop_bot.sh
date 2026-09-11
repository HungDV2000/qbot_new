#!/bin/bash
# ==============================================================================
# QBot — DỪNG TỪNG BOT — Linux / macOS / Git Bash
#
#   ./stop_bot.sh hd_order_multi         → dừng bot đó ở MỌI tài khoản
#   ./stop_bot.sh hd_order_multi kh_a    → chỉ tài khoản kh_a
#
# Muốn TẮT HẲN một tài khoản: để Bật = N trên sheet tổng rồi đổi ô B1 —
# mọi bot tự dừng tài khoản đó, không cần vào máy.
# ==============================================================================
cd "$(dirname "$0")" || exit 1

BOT="${1%.py}"; ACC="${2:-}"
[ -z "$BOT" ] && { echo "Cách dùng: ./stop_bot.sh <tên_bot> [tài_khoản]"; exit 1; }

_pid_tu() {
    for f in "$@"; do [ -f "$f" ] && { cat "$f" 2>/dev/null; echo; }; done \
        | grep -E '^[0-9]+$' | sort -u
}
# Chỉ giết đúng tiến trình của bot này — PID cũ có thể đã được cấp cho
# chương trình khác. Không xem được lệnh (Git Bash) thì tin kill -0.
_dung_bot() {
    local c; c="$(ps -p "$1" -o command= 2>/dev/null)"
    [ -z "$c" ] && return 0
    echo "$c" | grep -q "$BOT"
}
_giet() {   # $1 = tín hiệu, còn lại = PID
    local sig="$1" PID; shift
    for PID in "$@"; do
        kill -0 "$PID" 2>/dev/null && _dung_bot "$PID" && kill "$sig" "$PID" 2>/dev/null \
            && { echo "  ✔ PID $PID"; N=$((N+1)); }
    done
}

N=0
if [ -n "$ACC" ]; then
    CHA=""
    CON="$(_pid_tu "pids/$ACC/$BOT.pid" "pids/$ACC/$BOT.lock")"
    PID="$(cat "pids/$BOT.pid" 2>/dev/null)"
    if [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null; then
        echo "⚠️  $BOT đang chạy dưới điều phối chung (PID $PID). Dừng riêng [$ACC] thì"
        echo "   điều phối KHÔNG bật lại cho tới lần khởi động sau."
        echo "   Muốn tắt hẳn tài khoản: Bật = N trên sheet tổng rồi đổi ô B1."
    fi
    FILES=("pids/$ACC/$BOT.pid")
else
    CHA="$(_pid_tu "pids/$BOT.pid" "pids/$BOT.lock")"
    CON="$(_pid_tu pids/*/"$BOT".pid pids/*/"$BOT".lock)"
    FILES=("pids/$BOT.pid" pids/*/"$BOT".pid)
fi

echo "▶ Dừng $BOT${ACC:+ [$ACC]}"
# Điều phối trước — nó tự dừng các tiến trình con của mình
[ -n "$CHA" ] && { _giet -TERM $CHA; sleep 4; }
_giet -TERM $CON
sleep 2
for PID in $CHA $CON; do
    kill -0 "$PID" 2>/dev/null && _dung_bot "$PID" && kill -9 "$PID" 2>/dev/null \
        && echo "  ⚠ buộc dừng PID $PID"
done
rm -f "${FILES[@]}"

if [ "$N" = 0 ]; then echo "ℹ️  $BOT${ACC:+ [$ACC]} không chạy"
else echo "✅ Đã dừng $N tiến trình"; fi
