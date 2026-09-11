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
else
    # Dừng tiến trình ĐIỀU PHỐI (pids/*.pid) TRƯỚC — nó tự dọn các tiến trình
    # con. Sau đó quét từng thư mục tài khoản cho sạch.
    TARGETS=("")
    if [ -d pids ]; then
        for d in pids/*/; do [ -d "$d" ] && TARGETS+=("$(basename "$d")"); done
    fi
fi

# PID từ CẢ .pid lẫn .lock. Bot tự khởi động lại khi đổi cấu hình trên sheet
# thì PID đổi; .lock luôn giữ PID của tiến trình đang chạy thật.
_pids_in() {
    local d="$1" f
    for f in "$d"/*.pid "$d"/*.lock; do [ -f "$f" ] && { cat "$f" 2>/dev/null; echo; }; done \
        | grep -E '^[0-9]+$' | sort -u
}

# Chỉ giết tiến trình Python — tránh PID cũ đã bị hệ điều hành cấp lại cho
# chương trình khác. Không xem được (vd ps của Git Bash không thấy tiến trình
# Windows gốc) thì tin kill -0 như cũ.
_la_bot() {
    local out; out="$(ps -p "$1" 2>/dev/null | tail -n +2)"
    [ -z "$out" ] && return 0
    echo "$out" | grep -qi python
}

stop_one() {
    local ACC="$1" PIDDIR LABEL n=0 PID DS
    if [ -z "$ACC" ]; then PIDDIR="pids"; LABEL="(điều phối / 1 tài khoản)"
    else PIDDIR="pids/$ACC"; LABEL="[$ACC]"; fi
    [ -d "$PIDDIR" ] || return
    DS="$(_pids_in "$PIDDIR")"
    [ -z "$DS" ] && return

    echo ""
    echo "▶ Dừng $LABEL"
    for PID in $DS; do
        kill -0 "$PID" 2>/dev/null && _la_bot "$PID" && kill "$PID" 2>/dev/null \
            && { echo "  ✔ PID $PID"; n=$((n+1)); }
    done
    sleep 4
    # Lượt 2: bot có thể vừa tự khởi động lại và ghi PID mới trong lúc chờ
    for PID in $(_pids_in "$PIDDIR"); do
        kill -0 "$PID" 2>/dev/null && _la_bot "$PID" && kill "$PID" 2>/dev/null \
            && { echo "  ✔ PID $PID (tiến trình vừa sinh lại)"; n=$((n+1)); }
    done
    sleep 2
    for PID in $(_pids_in "$PIDDIR"); do
        kill -0 "$PID" 2>/dev/null && _la_bot "$PID" && kill -9 "$PID" 2>/dev/null \
            && echo "  ⚠ buộc dừng PID $PID"
    done
    rm -f "$PIDDIR"/*.pid
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
