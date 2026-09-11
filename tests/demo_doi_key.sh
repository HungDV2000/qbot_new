#!/bin/bash
# ==============================================================================
# DIỄN TẬP ĐỔI KEY TRÊN SHEET — chạy THẬT, không mạng, không tiền
#
#   ./tests/demo_doi_key.sh
#
# Kịch bản đúng như khách sẽ làm:
#   1. Bot chạy, nạp key từ sheet tổng
#   2. Sửa key trên sheet + đổi ô phiên bản
#   3. Bot TỰ khởi động lại, chạy bằng key mới — không ai vào VPS
#
# Kiểm nghiêm ngặt: KHÔNG BAO GIỜ có hai tiến trình cùng chạy (đặt lệnh trùng).
# ==============================================================================
set -u
QBOT="$(cd "$(dirname "$0")/.." && pwd)"
SB="/tmp/qbot_doikey"
PASS=0; FAIL=0
ok(){ PASS=$((PASS+1)); echo "  ✅ $1"; }
ng(){ FAIL=$((FAIL+1)); echo "  ❌ $1"; }

echo "════════════════════════════════════════════════════════════"
echo "  DIỄN TẬP: ĐỔI KEY TRÊN SHEET, BOT TỰ NẠP LẠI"
echo "════════════════════════════════════════════════════════════"
rm -rf "$SB"; mkdir -p "$SB"; cd "$SB" || exit 1

cp "$QBOT"/cst.py "$QBOT"/rate_guard.py "$QBOT"/symbol_filter.py \
   "$QBOT"/config_watcher.py "$QBOT"/sheet_config.py .
mv sheet_config.py sheet_config_that.py

# Binance giả: key bắt đầu bằng HONG thì đăng nhập thất bại
cat > binance_futures_direct.py <<'EOF'
def futures_signed_request(*a, api_key=None, **k):
    return None if (api_key or '').startswith('HONG') else {}
EOF

# Sheet tổng giả: đọc từ file, sửa file = sửa sheet
cat > trang_thai.txt <<'EOF'
1|KEY_CU
EOF

cat > sheet_config.py <<'EOF'
import io
from sheet_config_that import LoiSheetCauHinh, LoiDocSheet, tim_tai_khoan
def _doc():
    pb, key = io.open("trang_thai.txt", encoding="utf-8").read().strip().split("|")
    return pb, key
def doc_o_phien_ban(sid, tab):
    return _doc()[0]
def nap(bot_id, sid):
    pb, key = _doc()
    import sheet_config_that as t
    bang = [["PHIÊN BẢN", pb],
            ["Tài khoản", "Bật", "API Key", "API Secret", "Sheet ID"],
            ["kh_a", "Y", key, "SEC_A", "SHEET_A"]]
    _pb, b = t.phan_tich_bang(bang)
    b = t.loc_dang_bat(b); t.kiem_tra_du_khoa(b)
    return _pb, b
EOF

# config.ini tối thiểu — đúng như khách sẽ có
python3 - "$QBOT" <<'PY'
import io, re, sys
s = io.open(sys.argv[1] + "/config.ini.example", encoding="utf-8").read()
s = re.sub(r'(?m)^bot_id\s*=.*$', 'bot_id = QBOT01', s)
s = re.sub(r'(?m)^config_spreadsheet_id\s*=.*$', 'config_spreadsheet_id = SHEET_TONG', s)
s = re.sub(r'(?m)^config_reload_seconds\s*=.*$', 'config_reload_seconds = 2', s)
s = re.sub(r'(?m)^accounts\s*=.*$', 'accounts =', s)
io.open("config.ini", "w", encoding="utf-8").write(s)
PY

# Bot giả: dùng cst + config_watcher THẬT, chỉ thay phần giao dịch
cat > hd_giadinh.py <<'EOF'
import os, sys, time, cst, config_watcher
print(f"KHOI_DONG pid={os.getpid()} key={cst.key_binance} pb={cst.config_sheet_version}",
      flush=True)
while True:
    print(f"QUET pid={os.getpid()} key={cst.key_binance}", flush=True)
    config_watcher.ngu(1)   # đi đúng đường thật: nghỉ + dò + XÁC MINH rồi mới nạp
EOF

echo ""
echo "▶ BƯỚC 1 — Bật bot, nạp key từ sheet"
echo "────────────────────────────────────────────"
QBOT_ACCOUNT=kh_a QBOT_MIN_RESTART_GAP=0 nohup python3 hd_giadinh.py > bot.log 2>&1 &
sleep 4
grep -q "key=KEY_CU" bot.log && ok "Nạp đúng KEY_CU từ sheet tổng" || ng "Không nạp được key"
PID1=$(grep -o "KHOI_DONG pid=[0-9]*" bot.log | head -1 | grep -o "[0-9]*")
echo "     ↳ PID ban đầu: $PID1"
[ -f "pids/kh_a/hd_giadinh.lock" ] && ok "Đã giành khoá chống chạy trùng" || ng "Không thấy file khoá"

echo ""
echo "▶ BƯỚC 2 — Sửa key trên sheet + đổi ô phiên bản"
echo "────────────────────────────────────────────"
echo "2|KEY_MOI" > trang_thai.txt
echo "     ↳ đã đổi: phiên bản 1→2, key KEY_CU→KEY_MOI"
sleep 12

echo ""
echo "▶ BƯỚC 3 — Kiểm kết quả"
echo "────────────────────────────────────────────"
grep -q "khởi động lại" bot.log && ok "Bot phát hiện thay đổi và tự khởi động lại" \
                                 || ng "Bot KHÔNG tự khởi động lại"
grep -q "key=KEY_MOI" bot.log && ok "Đang chạy bằng KEY MỚI (không ai vào VPS)" \
                              || ng "Vẫn chạy key cũ"

PID2=$(grep -o "KHOI_DONG pid=[0-9]*" bot.log | tail -1 | grep -o "[0-9]*")
echo "     ↳ PID sau khi nạp lại: $PID2"
[ -n "$PID2" ] && [ "$PID1" != "$PID2" ] && ok "Là tiến trình MỚI (PID đổi)" \
                                         || ng "PID không đổi — chưa thực sự nạp lại"

# Chỉ ĐÚNG MỘT tiến trình được sống — hai cái là đặt lệnh trùng
SONG=$(pgrep -f "hd_giadinh.py" | wc -l | tr -d ' ')
[ "$SONG" = "1" ] && ok "Chỉ 1 tiến trình đang chạy (không đặt lệnh trùng)" \
                  || ng "🔴 CÓ $SONG tiến trình cùng chạy — NGUY CƠ ĐẶT LỆNH TRÙNG"

kill -0 "$PID1" 2>/dev/null && ng "Tiến trình cũ vẫn sống" || ok "Tiến trình cũ đã thoát sạch"
[ -f "pids/kh_a/hd_giadinh.lock" ] && \
  ok "Khoá đã bàn giao cho tiến trình mới (PID $(cat pids/kh_a/hd_giadinh.lock))" \
  || ng "Mất file khoá sau khi nạp lại"

pkill -f "hd_giadinh.py" 2>/dev/null
sleep 1
echo ""
echo "════════════════════════════════════════════════════════════"
echo "  KẾT QUẢ:  ✅ $PASS đạt   ❌ $FAIL lỗi"
echo "  Nhật ký: $SB/bot.log"
echo "════════════════════════════════════════════════════════════"
[ "$FAIL" -eq 0 ]
