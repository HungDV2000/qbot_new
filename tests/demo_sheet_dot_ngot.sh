#!/bin/bash
# ==============================================================================
# DIỄN TẬP: SHEET TỔNG BỊ SỬA ĐỘT NGỘT — chạy THẬT, không mạng, không tiền
#
# Dùng cst.py / config_watcher.py / sheet_config.py / stop_all_bots.sh THẬT.
# Chỉ giả Google Sheet (đọc từ file) và Binance (key bắt đầu HONG = sai key).
#
#   A. Chế độ ĐIỀU PHỐI (python3 hd_xxx.py, cha trông con):
#      đổi key (KHÔNG đổi B1) · trùng key · key dán thiếu · key không đăng nhập
#      được · thêm tài khoản kèm 1 dòng lỗi · tắt tài khoản · tắt hết rồi bật lại
#   B. Chế độ chạy lẻ (start_all_bots theo tài khoản): đổi key rồi stop_all_bots
# ==============================================================================
set -u
QBOT="$(cd "$(dirname "$0")/.." && pwd)"
SB="/tmp/qbot_dotngot"
PASS=0; FAIL=0
ok(){ PASS=$((PASS+1)); echo "  ✅ $1"; }
ng(){ FAIL=$((FAIL+1)); echo "  ❌ $1"; }
dem(){ pgrep -f "hd_mophong.py" 2>/dev/null | wc -l | tr -d ' '; }
pid_cuoi(){ grep -o "CHAY tk=$1 pid=[0-9]*" "$2" | tail -1 | grep -o '[0-9]*$'; }

pkill -f hd_mophong.py 2>/dev/null; sleep 1
rm -rf "$SB"; mkdir -p "$SB"; cd "$SB" || exit 1
cp "$QBOT"/cst.py "$QBOT"/rate_guard.py "$QBOT"/config_watcher.py \
   "$QBOT"/stop_all_bots.sh "$QBOT"/status.sh .
cp "$QBOT"/sheet_config.py sheet_config_that.py

cat > sheet_config.py <<'EOF'
import json
from sheet_config_that import LoiSheetCauHinh, LoiDocSheet, tim_tai_khoan, nap_tu_bang
def _rows(): return json.load(open("bang.json", encoding="utf-8"))
def nap(bot_id, sid): return nap_tu_bang(_rows(), bot_id)   # KIỂM TRA DỮ LIỆU THẬT
EOF
cat > binance_futures_direct.py <<'EOF'
def futures_signed_request(*a, api_key=None, **k):
    return None if (api_key or '').startswith('HONG') else {}
EOF
cat > telegram_factory.py <<'EOF'
def send_tele(msg, chat_id, *a, **k):
    open("tele.log", "a", encoding="utf-8").write(msg.replace("\n", " ") + "\n")
EOF
cat > hd_mophong.py <<'EOF'
import os, cst, config_watcher
print(f"CHAY tk={cst.account} pid={os.getpid()} key={cst.key_binance[:5]}", flush=True)
while True:
    config_watcher.ngu(1)
EOF
python3 - "$QBOT" <<'PY'
import io, re, sys
s = io.open(sys.argv[1] + "/config.ini.example", encoding="utf-8").read()
for k, v in (("bot_id", "QBOT01"), ("config_spreadsheet_id", "SHEET_TONG"),
             ("config_reload_seconds", "2"), ("account_start_stagger_sec", "0")):
    s = re.sub(rf'(?m)^{k}\s*=.*$', f'{k} = {v}', s)
io.open("config.ini", "w", encoding="utf-8").write(s)
PY

# ghi_bang <phiên bản> <dòng tài khoản…>  mỗi dòng: tên|bật|key|secret|sheet
ghi_bang(){
    python3 - "$@" <<'PY'
import json, sys
rows = [["PHIÊN BẢN", sys.argv[1]], ["Tài khoản", "Bật", "API Key", "API Secret", "Sheet ID"]]
for d in sys.argv[2:]:
    rows.append(d.split("|"))
json.dump(rows, open("bang.json", "w", encoding="utf-8"), ensure_ascii=False)
PY
}
K(){ python3 -c "print(('$1' + 'x'*64)[:64])"; }
A1=$(K KEYA1); A2=$(K KEYA2); B1=$(K KEYB1); C1=$(K KEYC1); SEC=$(K SECRET); HONG=$(K HONGA)
export QBOT_MIN_RESTART_GAP=0

echo "════════════════════════════════════════════════════════════"
echo "  A. CHẾ ĐỘ ĐIỀU PHỐI — cha trông các con"
echo "════════════════════════════════════════════════════════════"
ghi_bang 1 "kh_a|Y|$A1|$SEC|SH_A" "kh_b|Y|$B1|$SEC|SH_B"
nohup python3 hd_mophong.py > cha.log 2>&1 &
CHA=$!; sleep 6
[ "$(dem)" = "3" ] && ok "Bật lên: 1 điều phối + 2 tài khoản" || ng "Bật lên: $(dem) tiến trình (cần 3)"

echo "▶ A1 — đổi key kh_a hợp lệ — KHÔNG đổi ô B1"
PA=$(pid_cuoi kh_a cha.log)
ghi_bang 1 "kh_a|Y|$A2|$SEC|SH_A" "kh_b|Y|$B1|$SEC|SH_B"; sleep 10
grep -q "CHAY tk=kh_a pid=[0-9]* key=KEYA2" cha.log && ok "kh_a chạy bằng KEY MỚI" || ng "kh_a chưa nhận key mới"
[ "$(pid_cuoi kh_a cha.log)" != "$PA" ] && ok "kh_a là tiến trình mới" || ng "kh_a không khởi động lại"
kill -0 $CHA 2>/dev/null && ok "Điều phối VẪN SỐNG (lỗi cũ: chết sạch)" || ng "🔴 điều phối đã chết"
[ "$(dem)" = "3" ] && ok "Vẫn đúng 3 tiến trình" || ng "Có $(dem) tiến trình (cần 3)"

giu_nguyen(){   # $1 = mô tả, $2 = chuỗi phải thấy trong tele.log
    local PA PB; PA=$(pid_cuoi kh_a cha.log); PB=$(pid_cuoi kh_b cha.log)
    sleep 10
    [ "$(pid_cuoi kh_a cha.log)" = "$PA" ] && [ "$(pid_cuoi kh_b cha.log)" = "$PB" ] \
        && ok "$1 → GIỮ NGUYÊN cấu hình đang chạy, không khởi động lại" \
        || ng "🔴 $1 → bot đã nạp lại vào cấu hình hỏng"
    grep -q "$2" tele.log 2>/dev/null && ok "   có báo Telegram ('$2')" || ng "   không thấy báo Telegram '$2'"
    [ "$(dem)" = "3" ] || ng "   số tiến trình lệch: $(dem)"
}
echo "▶ A2 — chép dòng quên sửa: kh_b trùng API key kh_a"
ghi_bang 3 "kh_a|Y|$A2|$SEC|SH_A" "kh_b|Y|$A2|$SEC|SH_B"; giu_nguyen "Trùng API key" "ĐẶT LỆNH TRÙNG"
echo "▶ A3 — đang dán key thì bot đọc (key cụt)"
ghi_bang 4 "kh_a|Y|KEYA2cut|$SEC|SH_A" "kh_b|Y|$B1|$SEC|SH_B"; giu_nguyen "Key dán thiếu" "dán thiếu"
echo "▶ A4 — key mới không đăng nhập được Binance"
ghi_bang 5 "kh_a|Y|$HONG|$SEC|SH_A" "kh_b|Y|$B1|$SEC|SH_B"; giu_nguyen "Key sai" "KHÔNG đăng nhập được"

echo "▶ A5 — thêm kh_c hợp lệ + kh_d dán thiếu key (cùng lúc)"
ghi_bang 6 "kh_a|Y|$A2|$SEC|SH_A" "kh_b|Y|$B1|$SEC|SH_B" "kh_c|Y|$C1|$SEC|SH_C" "kh_d|Y|KEYDcut|$SEC|SH_D"; sleep 12
grep -q "\[kh_c\] tài khoản MỚI" cha.log && ok "Điều phối tự mở kh_c" || ng "Không mở kh_c"
grep -q "kh_d.*BỎ QUA" tele.log 2>/dev/null && ok "kh_d lỗi → bị BỎ RIÊNG + báo Telegram" || ng "Không báo kh_d bị bỏ qua"
grep -q "\[kh_d\] đã khởi động" cha.log && ng "🔴 mở cả tài khoản lỗi kh_d" || ok "Không mở tài khoản lỗi kh_d"
[ "$(dem)" = "4" ] && ok "Đúng 4 tiến trình — dòng lỗi KHÔNG chặn kh_c" || ng "Có $(dem) tiến trình (cần 4)"

echo "▶ A6 — tắt kh_b (gõ 'Không' vào cột Bật)"
ghi_bang 7 "kh_a|Y|$A2|$SEC|SH_A" "kh_b|Không|$B1|$SEC|SH_B" "kh_c|Y|$C1|$SEC|SH_C"; sleep 12
grep -qE "\[kh_b\].*(TẮT|không còn Bật)|kh_b.*TẮT/XOÁ" cha.log && ok "kh_b dừng, không bật lại" || ng "kh_b không dừng"
[ "$(dem)" = "3" ] && ok "Còn đúng 3 tiến trình" || ng "Có $(dem) tiến trình (cần 3)"

echo "▶ A7 — TẮT HẾT tài khoản (máy tự bật/tắt)"
ghi_bang 8 "kh_a|N|$A2|$SEC|SH_A" "kh_b|N|$B1|$SEC|SH_B" "kh_c|N|$C1|$SEC|SH_C"; sleep 14
[ "$(dem)" = "1" ] && ok "Mọi tài khoản đã dừng, chỉ còn điều phối" || ng "Có $(dem) tiến trình (cần 1)"
kill -0 $CHA 2>/dev/null && ok "Điều phối KHÔNG thoát — ngồi chờ tài khoản được Bật" || ng "🔴 điều phối thoát khi hết tài khoản"
grep -q "chờ tài khoản được Bật" cha.log && ok "   có báo đang chờ" || ng "   không báo đang chờ"

echo "▶ A8 — BẬT LẠI kh_a"
ghi_bang 8 "kh_a|Y|$A2|$SEC|SH_A" "kh_b|N|$B1|$SEC|SH_B" "kh_c|N|$C1|$SEC|SH_C"; sleep 10
[ "$(dem)" = "2" ] && ok "Bật Y là tự mở lại kh_a (không cần vào máy, không đổi B1)" || ng "Có $(dem) tiến trình (cần 2)"

kill $CHA 2>/dev/null; sleep 4
[ "$(dem)" = "0" ] && ok "Dừng điều phối → dừng sạch mọi tài khoản" || ng "Còn sót $(dem) tiến trình"
pkill -f hd_mophong.py 2>/dev/null; sleep 1

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  B. CHẠY LẺ (start_all_bots theo tài khoản) + stop_all_bots"
echo "════════════════════════════════════════════════════════════"
rm -rf pids logs; mkdir -p pids/kh_a logs/kh_a
ghi_bang 10 "kh_a|Y|$A1|$SEC|SH_A" "kh_b|Y|$B1|$SEC|SH_B"
QBOT_ACCOUNT=kh_a nohup python3 hd_mophong.py > logs/kh_a/bot.log 2>&1 &
echo $! > pids/kh_a/hd_mophong.pid; sleep 4
CU=$(cat pids/kh_a/hd_mophong.pid)
ghi_bang 10 "kh_a|Y|$A2|$SEC|SH_A" "kh_b|Y|$B1|$SEC|SH_B"; sleep 12   # B1 y nguyên
THAT=$(pgrep -f hd_mophong.py | head -1)
[ -n "$THAT" ] && [ "$THAT" != "$CU" ] && ok "Tự khởi động lại (PID $CU → $THAT)" || ng "Không khởi động lại"
[ "$(cat pids/kh_a/hd_mophong.pid)" = "$THAT" ] && ok ".pid đã ghi PID MỚI" || ng "🔴 .pid vẫn PID cũ"
./stop_all_bots.sh -y > stop.log 2>&1; sleep 1
[ "$(dem)" = "0" ] && ok "stop_all_bots DỪNG ĐƯỢC bot sau khi tự khởi động lại (lỗi cũ: không dừng được)" \
                   || ng "🔴 stop_all_bots để sót $(dem) tiến trình"
pkill -f hd_mophong.py 2>/dev/null

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  KẾT QUẢ:  ✅ $PASS đạt   ❌ $FAIL lỗi"
echo "  Nhật ký: $SB/cha.log , $SB/tele.log"
echo "════════════════════════════════════════════════════════════"
[ "$FAIL" -eq 0 ]
