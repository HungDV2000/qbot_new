#!/bin/bash
# ==============================================================================
# QBot — BẬT TỪNG BOT (chạy nền) — Linux / macOS / Git Bash
#
#   ./start_bot.sh                          → xem danh sách bot
#   ./start_bot.sh hd_update_cho_va_khop    → bật 1 bot cho MỌI tài khoản đang Bật
#   ./start_bot.sh hd_order_multi kh_a      → chỉ cho tài khoản kh_a
#
# Dừng: ./stop_bot.sh <tên_bot> [tài_khoản]      Xem: ./status.sh
# Windows (CMD): dùng chay_bot.bat
# ==============================================================================
cd "$(dirname "$0")" || exit 1

BOTS=(hd_update_cho_va_khop hd_order_multi hd_alert_possition_and_open_order
      hd_cancel_selective hd_cancel_orders_schedule hd_update_all)
MOTA=("Chờ và khớp — nguồn cấp SL/TP (bật TRƯỚC)"
      "Đặt lệnh vào + SL/TP"
      "Cảnh báo Telegram, dọn lệnh khi vị thế đóng"
      "Xoá lệnh theo tick J–M"
      "Huỷ lệnh vào treo quá lâu"
      "Số dư → tab ĐẶT LỆNH J1:M2")

danh_sach() {
    echo "Cách dùng: ./start_bot.sh <tên_bot> [tài_khoản]"
    echo ""
    for i in "${!BOTS[@]}"; do printf "  %-36s %s\n" "${BOTS[$i]}" "${MOTA[$i]}"; done
}

_song() { local PID; PID="$(cat "$1" 2>/dev/null)"; [ -n "$PID" ] && kill -0 "$PID" 2>/dev/null && echo "$PID"; }

BOT="${1%.py}"; ACC="${2:-}"
[ -z "$BOT" ] && { danh_sach; exit 0; }
CO=0; for b in "${BOTS[@]}"; do [ "$b" = "$BOT" ] && CO=1; done
[ "$CO" = 1 ] || { echo "❌ Không có bot '$BOT'"; echo ""; danh_sach; exit 1; }
[ -f "${QBOT_CONFIG:-config.ini}" ] || { echo "❌ Không tìm thấy ${QBOT_CONFIG:-config.ini}"; exit 1; }
command -v python3 >/dev/null 2>&1 && PY=python3 || PY=python

if [ -n "$ACC" ]; then
    PIDDIR="pids/$ACC"; LOGDIR="logs/$ACC"; NHAN="[$ACC]"; export QBOT_ACCOUNT="$ACC"
else
    PIDDIR="pids"; LOGDIR="logs"; NHAN="(mọi tài khoản đang Bật)"; unset QBOT_ACCOUNT
fi
mkdir -p "$PIDDIR" "$LOGDIR"

# Chống bật chồng = chống ĐẶT LỆNH TRÙNG
# Điều phối chung kiểm TRƯỚC: tiến trình con của nó cũng giữ khoá pids/<tk>/,
# kiểm sau thì câu báo "đang chạy" không cho biết là do điều phối chung.
if [ -n "$ACC" ]; then
    PID="$(_song "pids/$BOT.pid")" && {
        echo "⛔ $BOT đang chạy cho MỌI tài khoản (PID $PID) — đã gồm $ACC."; exit 1; }
fi
for f in "$PIDDIR/$BOT.lock" "$PIDDIR/$BOT.pid"; do
    PID="$(_song "$f")" && { echo "⛔ $BOT $NHAN đang chạy (PID $PID) — không bật chồng."; exit 1; }
done
if [ -z "$ACC" ]; then
    for f in pids/*/"$BOT".lock; do
        [ -f "$f" ] || continue
        PID="$(_song "$f")" && {
            A="$(basename "$(dirname "$f")")"
            echo "⛔ $BOT đang chạy riêng cho [$A] (PID $PID)."
            echo "   Dừng nó trước:  ./stop_bot.sh $BOT $A"; exit 1; }
    done
fi

nohup "$PY" "$BOT.py" > "$LOGDIR/$BOT.log" 2>> "$LOGDIR/error.log" &
PID=$!
echo "$PID" > "$PIDDIR/$BOT.pid"
sleep 3
if kill -0 "$PID" 2>/dev/null; then
    echo "✅ Đã bật $BOT $NHAN — PID $PID"
    echo "   Xem màn hình:  tail -f $LOGDIR/$BOT.log"
    echo "   Dừng:          ./stop_bot.sh $BOT${ACC:+ $ACC}"
else
    echo "❌ $BOT tắt ngay sau khi bật. 20 dòng cuối $LOGDIR/$BOT.log:"
    tail -20 "$LOGDIR/$BOT.log"
    rm -f "$PIDDIR/$BOT.pid"
    exit 1
fi
