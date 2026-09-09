#!/bin/bash
# ==============================================================================
# QBot - Dừng bot (HỖ TRỢ ĐA TÀI KHOẢN)
#   ./stop_all_bots.sh           → dừng TẤT CẢ tài khoản
#   ./stop_all_bots.sh kh_a      → chỉ dừng tài khoản kh_a
#   ./stop_all_bots.sh -y        → không hỏi xác nhận
# ==============================================================================
cd "$(dirname "$0")" || exit 1

ASSUME_YES=0
ARGS=()
for a in "$@"; do
    if [ "$a" = "-y" ] || [ "$a" = "--yes" ]; then ASSUME_YES=1; else ARGS+=("$a"); fi
done

echo "========================================"
echo "QBot - Dừng bot"
echo "========================================"

# Xác định tài khoản cần dừng
if [ ${#ARGS[@]} -gt 0 ]; then
    TARGETS=("${ARGS[@]}")
elif [ -d pids ]; then
    TARGETS=()
    for d in pids/*/; do [ -d "$d" ] && TARGETS+=("$(basename "$d")"); done
    [ ${#TARGETS[@]} -eq 0 ] && TARGETS=("")     # chế độ 1 tài khoản
else
    TARGETS=("")
fi

stop_one() {
    local ACC="$1" PIDDIR LABEL n=0
    if [ -z "$ACC" ]; then PIDDIR="pids"; LABEL="(1 tài khoản)"; else PIDDIR="pids/$ACC"; LABEL="[$ACC]"; fi
    [ -d "$PIDDIR" ] || { echo "  ⏭️  $LABEL: không có tiến trình nào"; return; }

    echo ""
    echo "▶ Dừng $LABEL"
    for f in "$PIDDIR"/*.pid; do
        [ -f "$f" ] || continue
        local PID; PID="$(cat "$f")"
        if kill -0 "$PID" 2>/dev/null; then
            kill "$PID" 2>/dev/null && echo "  ✔ $(basename "$f" .pid) (PID $PID)"
            n=$((n+1))
        fi
        rm -f "$f"
    done
    sleep 2
    # Buộc dừng nếu còn sót
    for f in "$PIDDIR"/*.pid; do
        [ -f "$f" ] || continue
        local PID; PID="$(cat "$f")"
        kill -0 "$PID" 2>/dev/null && kill -9 "$PID" 2>/dev/null && echo "  ⚠ buộc dừng PID $PID"
        rm -f "$f"
    done
    echo "  → Đã dừng $n tiến trình"
}

echo "📋 Sẽ dừng: ${TARGETS[*]:-(1 tài khoản)}"
if [ "$ASSUME_YES" -ne 1 ]; then
    read -p "Xác nhận dừng? (y/n) " -n 1 -r; echo ""
    [[ $REPLY =~ ^[Yy]$ ]] || { echo "Đã hủy."; exit 0; }
fi

for ACC in "${TARGETS[@]}"; do stop_one "$ACC"; done

# Dọn tiến trình mồ côi (khởi động tay, không có PID file)
REMAIN="$(pgrep -f 'python3 hd_' 2>/dev/null | wc -l | tr -d ' ')"
if [ "$REMAIN" != "0" ]; then
    echo ""
    echo "⚠️  Còn $REMAIN tiến trình hd_* chạy ngoài PID file (khởi động thủ công?)"
    echo "   Xem:  pgrep -af 'python3 hd_'"
    echo "   Dừng: pkill -f 'python3 hd_'"
fi

echo ""
echo "✅ Hoàn tất"
echo "========================================"
