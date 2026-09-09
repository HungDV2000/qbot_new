#!/bin/bash
# ==============================================================================
# DIỄN TẬP 2 TÀI KHOẢN — chạy THẬT trên máy, KHÔNG kết nối Binance/Google.
#
#   ./tests/demo_2_accounts.sh
#
# Dựng sandbox trong /tmp: dùng code THẬT (cst.py, hd_order_multi.py, các script)
# nhưng thay Binance/Google/Telegram bằng bản giả → an toàn tuyệt đối, không tốn tiền.
# ==============================================================================
set -u
QBOT="$(cd "$(dirname "$0")/.." && pwd)"
SB="/tmp/qbot_demo2acc"
PASS=0; FAIL=0
ok(){ PASS=$((PASS+1)); echo "  ✅ $1"; }
ng(){ FAIL=$((FAIL+1)); echo "  ❌ $1"; }

echo "════════════════════════════════════════════════════════════"
echo "  DIỄN TẬP 2 TÀI KHOẢN (local, không dùng tiền thật)"
echo "════════════════════════════════════════════════════════════"

rm -rf "$SB"; mkdir -p "$SB"; cd "$SB" || exit 1

# ── Code THẬT ────────────────────────────────────────────────────────────────
cp "$QBOT"/cst.py "$QBOT"/hd_order_multi.py "$QBOT"/binance_order_helper.py \
   "$QBOT"/rate_guard.py "$QBOT"/symbol_filter.py .
cp "$QBOT"/start_all_bots.sh "$QBOT"/stop_all_bots.sh "$QBOT"/status.sh .
chmod +x ./*.sh

# ── Config: 2 tài khoản, key/sheet KHÁC NHAU ─────────────────────────────────
python3 - "$QBOT" <<'PY'
import sys
src=open(sys.argv[1]+"/config.ini.example",encoding="utf-8").read()
src=src.replace("accounts =\n","accounts = kh_a, kh_b\n",1)
src+="""
[kh_a]
key_binance = KEY_CUA_A
secret_binance = SEC_CUA_A
spreadsheet_id = SHEET_CUA_A
chat_id = -1001
key_name = Khach A

[kh_b]
key_binance = KEY_CUA_B
secret_binance = SEC_CUA_B
spreadsheet_id = SHEET_CUA_B
chat_id = -1002
key_name = Khach B
"""
open("config.ini","w",encoding="utf-8").write(src)
PY

# ── Giả lập Binance / Google / Telegram ──────────────────────────────────────
cat > ccxt.py <<'EOF'
class binance:
    def __init__(self,*a,**k): self.markets={"ATOM/USDT:USDT":{"active":True,"info":{"status":"TRADING"},"precision":{"price":4,"amount":2}}}
    def setSandboxMode(self,*a,**k): pass
    def load_markets(self,*a,**k): return self.markets
    def price_to_precision(self,s,v): return v
    def amount_to_precision(self,s,v): return v
    def fetch_ticker(self,s): return {"last":1.413}
    def fetch_open_orders(self,s=None): return []
    def fetch_balance(self): return {"info":{"positions":[]}}
    def setLeverage(self,l,s): pass
    def load_time_difference(self): pass
    def create_order(self, symbol, type, side, amount, price=None, params=None):
        # "Sàn giả": ghi lệnh ra file của ĐÚNG tài khoản đang chạy
        import cst
        params = params or {}
        with open(cst.account_dir("data")/"orders_placed.log","a",encoding="utf-8") as f:
            f.write(f"{cst.key_binance}|{symbol}|{type}|{side}|{amount}|{price}|"
                    f"ro={params.get('reduceOnly',False)}\n")
        return {"id":"DEMO1","info":{},"symbol":symbol,"side":side,"status":"NEW"}
EOF
cat > binance_futures_direct.py <<'EOF'
def fetch_algo_orders_for_symbol(*a,**k): return []
def resync_exchange_time(*a,**k): pass
EOF
cat > binance_utils.py <<'EOF'
def get_price_precision(sym): return 4
EOF
cat > utils.py <<'EOF'
def get_all_open_orders_symbol_local(): return []
EOF
cat > telegram_factory.py <<'EOF'
import cst
def send_tele(msg, chat_id, is_html=True, prev=True):
    # Ghi lại để kiểm chứng: mỗi tài khoản gửi đúng chat_id của mình
    with open(cst.account_dir("data")/"telegram_sent.log","a",encoding="utf-8") as f:
        f.write(f"chat_id={chat_id}\n")
EOF
# gg_sheet_factory giả: trả dữ liệu sheet RIÊNG theo spreadsheet_id của từng tài khoản
cat > gg_sheet_factory.py <<'EOF'
import cst
tab_dat_lenh = cst.tab_dat_lenh
tab_cho_va_khop = "Chờ và khớp"
def init_sheet_api(): pass
def get_dat_lenh(rng):
    # Ghi lại sheet_id thực sự đang dùng → để kiểm chứng không lẫn tài khoản
    with open(cst.account_dir("data")/"sheet_reads.log","a",encoding="utf-8") as f:
        f.write(f"{cst.spreadsheet_id}|{rng}\n")
    if rng.startswith("B2"): return [["LONG"]]
    if rng.startswith("D1"): return [["1%",""],["10","10"]]
    return [["ATOM/USDT","10","","1.38","","1","","10"]]
def get_cho_va_khop(rng, value_render_option=None): return []
def update_single_value(*a,**k): pass
def update_multi(*a,**k): pass
EOF
mkdir -p googleapiclient && cat > googleapiclient/__init__.py <<'EOF'
EOF
cat > googleapiclient/errors.py <<'EOF'
class HttpError(Exception): pass
EOF
# 8 bot phụ: giả (chỉ ngủ) — đủ để kiểm tra script start/stop/status
for b in hd_order_123 hd_update_all hd_update_price hd_update_cho_va_khop \
         hd_alert_possition_and_open_order hd_cancel_orders_schedule \
         hd_track_30_prices hd_periodic_report; do
cat > $b.py <<'EOF'
import cst, time
print(f"[{cst.account_name}] bot phụ đang chạy", flush=True)
time.sleep(600)
EOF
done

echo ""
echo "▶ BƯỚC 1 — Khởi động CẢ 2 tài khoản"
echo "────────────────────────────────────────────"
ORDER_BOT_MODE=multi ./start_all_bots.sh 2>&1 | grep -E "Tài khoản sẽ chạy|Khởi động \[|Đã khởi động"
sleep 6

echo ""
echo "▶ BƯỚC 2 — Kiểm tra CÁCH LY dữ liệu"
echo "────────────────────────────────────────────"
[ -d logs/kh_a ] && [ -d logs/kh_b ] && ok "Log tách riêng: logs/kh_a & logs/kh_b" || ng "Log KHÔNG tách riêng"
[ -d data/kh_a ] && [ -d data/kh_b ] && ok "Dữ liệu tách riêng: data/kh_a & data/kh_b" || ng "Dữ liệu KHÔNG tách"

# Mỗi tài khoản phải đọc ĐÚNG sheet của mình
A_SHEET=$(cut -d'|' -f1 data/kh_a/sheet_reads.log 2>/dev/null | sort -u | tr '\n' ' ')
B_SHEET=$(cut -d'|' -f1 data/kh_b/sheet_reads.log 2>/dev/null | sort -u | tr '\n' ' ')
[ "$(echo $A_SHEET)" = "SHEET_CUA_A" ] && ok "kh_a đọc đúng SHEET_CUA_A" || ng "kh_a đọc sai sheet: '$A_SHEET'"
[ "$(echo $B_SHEET)" = "SHEET_CUA_B" ] && ok "kh_b đọc đúng SHEET_CUA_B" || ng "kh_b đọc sai sheet: '$B_SHEET'"

# Telegram phải gửi đúng chat_id riêng
grep -q "chat_id=-1001" data/kh_a/telegram_sent.log 2>/dev/null && ok "kh_a gửi Telegram đúng chat -1001" || echo "  ℹ️  kh_a chưa gửi Telegram (chưa đặt lệnh)"
grep -q "chat_id=-1002" data/kh_b/telegram_sent.log 2>/dev/null && ok "kh_b gửi Telegram đúng chat -1002" || echo "  ℹ️  kh_b chưa gửi Telegram (chưa đặt lệnh)"

# Lệnh đặt ra phải mang ĐÚNG key của từng tài khoản
if [ -f data/kh_a/orders_placed.log ]; then
    grep -q "^KEY_CUA_A|" data/kh_a/orders_placed.log && ok "kh_a đặt lệnh bằng ĐÚNG KEY_CUA_A" || ng "kh_a đặt lệnh sai key"
    grep -q "KEY_CUA_B" data/kh_a/orders_placed.log && ng "LẪN KEY! kh_a dùng key của B" || ok "kh_a không dùng nhầm key của B"
    echo "     ↳ lệnh kh_a: $(head -1 data/kh_a/orders_placed.log)"
else
    ng "kh_a không đặt được lệnh nào"
fi
if [ -f data/kh_b/orders_placed.log ]; then
    grep -q "^KEY_CUA_B|" data/kh_b/orders_placed.log && ok "kh_b đặt lệnh bằng ĐÚNG KEY_CUA_B" || ng "kh_b đặt lệnh sai key"
    echo "     ↳ lệnh kh_b: $(head -1 data/kh_b/orders_placed.log)"
else
    ng "kh_b không đặt được lệnh nào"
fi

# Không được lẫn key giữa 2 tài khoản
if grep -rq "KEY_CUA_B" logs/kh_a/ 2>/dev/null; then ng "LẪN KEY! kh_a thấy key của B"; else ok "Không lẫn key giữa 2 tài khoản"; fi

echo ""
echo "▶ BƯỚC 3 — status.sh"
echo "────────────────────────────────────────────"
./status.sh 2>&1 | grep -E "👤|Đang chạy|TỔNG"
RUN=$(./status.sh 2>&1 | grep -c "│  🟢")   # chỉ đếm dòng tiến trình
[ "$RUN" -ge 2 ] && ok "Có tiến trình đang chạy cho cả 2 tài khoản ($RUN tiến trình)" || ng "Số tiến trình bất thường: $RUN"

echo ""
echo "▶ BƯỚC 4 — CHẶN khởi động TRÙNG"
echo "────────────────────────────────────────────"
OUT=$(ORDER_BOT_MODE=multi ./start_all_bots.sh 2>&1)
echo "$OUT" | grep -q "ĐANG CHẠY" && ok "Chạy lại bị CHẶN (không tạo lệnh trùng)" || ng "KHÔNG chặn — nguy cơ đặt lệnh trùng!"

echo ""
echo "▶ BƯỚC 5 — Dừng RIÊNG 1 tài khoản"
echo "────────────────────────────────────────────"
./stop_all_bots.sh kh_a -y 2>&1 | grep -E "Dừng \[|Đã dừng"
sleep 2
A_LEFT=$(./status.sh kh_a 2>&1 | grep -c "│  🟢")
B_LEFT=$(./status.sh kh_b 2>&1 | grep -c "│  🟢")
[ "$A_LEFT" = "0" ] && ok "kh_a đã dừng hẳn" || ng "kh_a vẫn còn $A_LEFT tiến trình"
[ "$B_LEFT" -ge 1 ] && ok "kh_b VẪN CHẠY (không bị ảnh hưởng)" || ng "kh_b bị dừng oan!"

echo ""
echo "▶ BƯỚC 6 — Dọn dẹp"
echo "────────────────────────────────────────────"
./stop_all_bots.sh -y >/dev/null 2>&1
pkill -f "$SB" 2>/dev/null
sleep 1
echo "  Đã dừng toàn bộ"

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  KẾT QUẢ:  ✅ $PASS đạt   ❌ $FAIL lỗi"
echo "  Sandbox: $SB (xoá được: rm -rf $SB)"
echo "════════════════════════════════════════════════════════════"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
