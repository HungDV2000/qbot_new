#!/bin/bash
# ==============================================================================
# QBot - Xem trạng thái các tài khoản đang chạy
#   ./status.sh          → tất cả
#   ./status.sh kh_a     → 1 tài khoản
# ==============================================================================
cd "$(dirname "$0")" || exit 1
CONFIG_FILE="${QBOT_CONFIG:-config.ini}"

echo "════════════════════════════════════════════════════════════"
echo " QBOT — TRẠNG THÁI   ($(date '+%Y-%m-%d %H:%M:%S'))"
echo "════════════════════════════════════════════════════════════"

if [ $# -gt 0 ]; then
    ACCOUNTS="$*"
else
    ACCOUNTS="$(python3 - "$CONFIG_FILE" <<'PY'
import configparser, sys
c = configparser.ConfigParser()
try:
    c.read(sys.argv[1], encoding='utf-8')
    print(' '.join(a.strip() for a in c.get('global','accounts',fallback='').split(',') if a.strip()))
except Exception:
    print('')
PY
)"
fi
[ -z "$ACCOUNTS" ] && ACCOUNTS="__single__"

TOTAL_RUN=0; TOTAL_DEAD=0
for ACC in $ACCOUNTS; do
    if [ "$ACC" = "__single__" ]; then PIDDIR="pids"; LOGDIR="logs"; LABEL="(1 tài khoản)"
    else PIDDIR="pids/$ACC"; LOGDIR="logs/$ACC"; LABEL="$ACC"; fi

    echo ""
    echo "┌─ 👤 $LABEL"
    if [ ! -d "$PIDDIR" ] || [ -z "$(ls -A "$PIDDIR" 2>/dev/null)" ]; then
        echo "└─ ⚫ Chưa chạy"
        continue
    fi
    run=0; dead=0
    for f in "$PIDDIR"/*.pid; do
        [ -f "$f" ] || continue
        NAME="$(basename "$f" .pid)"; PID="$(cat "$f")"
        if kill -0 "$PID" 2>/dev/null; then
            printf "│  🟢 %-34s PID %-8s\n" "$NAME" "$PID"; run=$((run+1))
        else
            printf "│  🔴 %-34s ĐÃ CHẾT\n" "$NAME"; dead=$((dead+1))
        fi
    done
    ERRSIZE=""
    [ -f "$LOGDIR/error.log" ] && ERRSIZE="  |  error.log: $(wc -c < "$LOGDIR/error.log" | tr -d ' ') bytes"
    echo "└─ Đang chạy: $run   Đã chết: $dead$ERRSIZE"
    TOTAL_RUN=$((TOTAL_RUN+run)); TOTAL_DEAD=$((TOTAL_DEAD+dead))
done

echo ""
echo "════════════════════════════════════════════════════════════"
echo " TỔNG: 🟢 $TOTAL_RUN đang chạy   🔴 $TOTAL_DEAD đã chết"
[ "$TOTAL_DEAD" -gt 0 ] && echo " ⚠️  Có tiến trình chết — xem log để biết nguyên nhân"
echo "════════════════════════════════════════════════════════════"
