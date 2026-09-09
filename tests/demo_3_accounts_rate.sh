#!/bin/bash
# ==============================================================================
# DIỄN TẬP 3 TÀI KHOẢN — ĐO LỖI 429 (hạn mức Google Sheets)
#
#   ./tests/demo_3_accounts_rate.sh [số_giây]      # mặc định 180
#
# Chạy code THẬT (cst.py, hd_order_multi.py, order_state_tracker.py, rate_guard.py)
# nhưng Binance/Google/Telegram là bản giả → KHÔNG mạng, KHÔNG tiền thật.
#
# ĐỐI CHỨNG: chạy 2 lượt trên CÙNG bộ code, chỉ khác 1 tham số config
#     Lượt A — TẮT cache (ttl=0)  → tái hiện lỗi cũ
#     Lượt B — BẬT cache (ttl=10) → bản đã sửa
# Mỗi lượt đếm TỪNG lượt gọi API của cả 3 tài khoản vào 1 sổ CHUNG
# (vì hạn mức 60 lượt/phút của Google là dùng CHUNG), rồi soi cửa sổ trượt 60s.
# ==============================================================================
set -u
QBOT="$(cd "$(dirname "$0")/.." && pwd)"
SB="/tmp/qbot_rate3"
SECS="${1:-180}"
QUOTA=60
PASS=0; FAIL=0; BOT_CHET=0
ok(){ PASS=$((PASS+1)); echo "  ✅ $1"; }
ng(){ FAIL=$((FAIL+1)); echo "  ❌ $1"; }

echo "════════════════════════════════════════════════════════════"
echo "  DIỄN TẬP 3 TÀI KHOẢN — ĐO HẠN MỨC GOOGLE SHEETS"
echo "  Hạn mức: $QUOTA lượt đọc/phút (DÙNG CHUNG cho cả 3 tài khoản)"
echo "  Mỗi lượt chạy: ${SECS}s"
echo "════════════════════════════════════════════════════════════"

rm -rf "$SB"; mkdir -p "$SB"; cd "$SB" || exit 1

# ── Code THẬT ────────────────────────────────────────────────────────────────
cp "$QBOT"/*.py .                       # TOÀN BỘ code thật
cp "$QBOT"/start_all_bots.sh "$QBOT"/stop_all_bots.sh "$QBOT"/status.sh .
chmod +x ./*.sh

# ── Giả lập Binance / Telegram ───────────────────────────────────────────────
cat > ccxt.py <<'EOF'
SYMS=[f"SYM{i}/USDT:USDT" for i in range(50)]
__version__ = "4.0.0"
class BaseError(Exception): pass
class NetworkError(BaseError): pass
class ExchangeError(BaseError): pass
class ExchangeNotAvailable(NetworkError): pass
class RequestTimeout(NetworkError): pass
class DDoSProtection(NetworkError): pass
class InsufficientFunds(ExchangeError): pass
class InvalidOrder(ExchangeError): pass
class OrderNotFound(ExchangeError): pass
class RateLimitExceeded(NetworkError): pass
class AuthenticationError(BaseError): pass
class binance:
    def __init__(self,*a,**k):
        self.markets={s:{"active":True,"info":{"status":"TRADING"},
                         "precision":{"price":4,"amount":2}} for s in SYMS}
    def setSandboxMode(self,*a,**k): pass
    def load_markets(self,*a,**k): return self.markets
    def price_to_precision(self,s,v): return v
    def amount_to_precision(self,s,v): return v
    def fetch_ticker(self,s): return {"last":1.413}
    def fetch_open_orders(self,s=None): return []
    def fetch_balance(self): return {"info":{"positions":[]}}
    def setLeverage(self,l,s): pass
    def load_time_difference(self): pass
    def create_order(self,symbol,type,side,amount,price=None,params=None):
        return {"id":"DEMO1","info":{},"symbol":symbol,"side":side,"status":"NEW"}
    def create_market_buy_order(self,*a,**k):  return {"id":"DEMO1","info":{}}
    def create_market_sell_order(self,*a,**k): return {"id":"DEMO1","info":{}}
    def cancel_order(self,*a,**k): return {}
    def fetch_positions(self,*a,**k): return []
    def fetch_tickers(self,*a,**k): return {s:{"last":1.413} for s in SYMS}
    def fetch_ohlcv(self,*a,**k): return [[0,1,1,1,1,1] for _ in range(30)]
    def market(self,s): return self.markets.get(s,{"precision":{"price":4,"amount":2}})
    def milliseconds(self): 
        import time; return int(time.time()*1000)
EOF
cat > binance_futures_direct.py <<'EOF'
def fetch_algo_orders_for_symbol(*a,**k): return []
def resync_exchange_time(*a,**k): pass
def futures_signed_request(*a,**k): return []
def normalize_algo_orders_response(*a,**k): return []
clock = 0
drift = 0
EOF
# pandas chưa cài trên máy này → bản tối giản đủ cho data_collector nạp được
cat > numpy.py <<'EOF'
nan = float("nan")
def array(x=None,*a,**k): return x or []
def mean(x,*a,**k): return 0
EOF
cat > pandas.py <<'EOF'
class DataFrame:
    def __init__(self,*a,**k): self.empty=True
    def __len__(self): return 0
def to_datetime(*a,**k): return None
def concat(*a,**k): return DataFrame()
def read_csv(*a,**k): return DataFrame()
NaT = None
EOF
cat > binance_utils.py <<'EOF'
def get_price_precision(sym): return 4
EOF
cat > utils.py <<'EOF'
def get_all_open_orders_symbol_local(): return []
EOF
cat > telegram_factory.py <<'EOF'
def send_tele(msg, chat_id, is_html=True, prev=True): pass
EOF

# ── Google Sheets giả: GHI SỔ CHUNG mọi lượt gọi của MỌI tài khoản ───────────
cat > gg_sheet_factory.py <<'EOF'
import os, re, time, cst
_CHI_COT_A = re.compile(r"^A\d+:A\d+$")
tab_dat_lenh = cst.tab_dat_lenh
tab_cho_va_khop = "Chờ và khớp"
_LOG = os.path.join(os.environ.get("RATE_LOG_DIR", "."), "api_calls.log")

def _ghi(rng):
    # O_APPEND: 3 tiến trình ghi chung 1 sổ vẫn an toàn (dòng ngắn, ghi nguyên khối)
    line = f"{time.time():.3f}|{cst.account_name}|{rng}\n"
    fd = os.open(_LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o644)
    try: os.write(fd, line.encode())
    finally: os.close(fd)

def init_sheet_api(): pass

def get_dat_lenh(rng):
    _ghi(rng)
    if rng.startswith("B2"):  return [["LONG"]]
    if rng.startswith("D1"):  return [["1%",""],["10","10"]]
    if rng.startswith("E2"):  return [["100"]]        # vốn mặc định
    if rng.startswith("C2"):  return [["100"]]
    # CHỈ cột A (vd "A4:A53") → danh sách mã; KHÁC với "A4:Z53" là cả bảng
    if _CHI_COT_A.match(rng):
        return [[f"SYM{i}/USDT"] for i in range(50)]
    # cả bảng: 50 mã × (A=mã, B=đòn bẩy, D=giá vào, F=kiểu lệnh, H=vốn)
    #        A=mã          B=đòn bẩy C=callback% D=giá vào E   F=kiểu G   H=vốn
    return [[f"SYM{i}/USDT", "10",     "1",       "1.38",   "", "1",  "", "10"]
            for i in range(50)]

def get_cho_va_khop(rng, value_render_option=None):
    _ghi("ChoVaKhop!" + rng); return []

tab_list_all_ma = "100 ma"
def get_100_ma(rng):
    _ghi("100Ma!" + rng)          # cũng tính vào hạn mức Google
    return [[f"SYM{i}/USDT"] for i in range(50)]
def clear_multi(*a, **k): pass

def update_single_value(*a,**k): pass
def update_multi(*a,**k): pass
EOF
mkdir -p googleapiclient
: > googleapiclient/__init__.py
cat > googleapiclient/errors.py <<'EOF'
class HttpError(Exception): pass
EOF

# ── Chặn mạng: bất kỳ lệnh gọi HTTP nào cũng phải lộ ra, không im lặng ──────
cat > requests.py <<'EOF'
class _R:
    status_code = 200
    text = "[]"
    def json(self): return []
    def raise_for_status(self): pass
def get(*a, **k):  return _R()
def post(*a, **k): return _R()
class exceptions:
    class RequestException(Exception): pass
EOF

# ── Sinh config 3 tài khoản; $1 = state_ttl, $2 = row_ttl ────────────────────
gen_config(){
python3 - "$QBOT" "$1" "$2" <<'PY'
import sys, re
qbot, sttl, rttl = sys.argv[1], sys.argv[2], sys.argv[3]
src = open(qbot+"/config.ini.example", encoding="utf-8").read()
src = src.replace("accounts =\n", "accounts = kh_a, kh_b, kh_c\n", 1)
def setkey(s, k, v):
    if re.search(rf"(?m)^{k}\s*=", s):
        return re.sub(rf"(?m)^{k}\s*=.*$", f"{k} = {v}", s)
    return s.replace("[global]", f"[global]\n{k} = {v}", 1)
src = setkey(src, "state_cache_ttl_sec", sttl)
src = setkey(src, "row_cache_ttl_sec",   rttl)
src = setkey(src, "account_start_stagger_sec", "20")
for i, n in enumerate(("a","b","c"), 1):
    src += f"""
[kh_{n}]
key_binance = KEY_{n.upper()}
secret_binance = SEC_{n.upper()}
spreadsheet_id = SHEET_{n.upper()}
chat_id = -100{i}
key_name = Khach {n.upper()}
"""
open("config.ini","w",encoding="utf-8").write(src)
PY
}

# ── Phân tích sổ: cửa sổ trượt 60 giây ──────────────────────────────────────
phan_tich(){
python3 - "$1" "$2" "$QUOTA" <<'PY'
import sys, collections
log, nhan, quota = sys.argv[1], sys.argv[2], int(sys.argv[3])
try:
    rows=[l.split('|',2) for l in open(log,encoding='utf-8') if l.strip()]
except FileNotFoundError:
    print(f"  ⚠️  {nhan}: không có sổ gọi API"); sys.exit(2)
ts=sorted(float(r[0]) for r in rows)
if not ts: print(f"  ⚠️  {nhan}: sổ rỗng"); sys.exit(2)
# đỉnh cửa sổ trượt 60s
dinh=0; j=0
for i,t in enumerate(ts):
    while ts[j] < t-60: j+=1
    dinh=max(dinh, i-j+1)
kd=(ts[-1]-ts[0]) or 1
theo_tk=collections.Counter(r[1] for r in rows)
theo_range=collections.Counter(r[2].strip().split('!')[-1][:14] for r in rows)
print(f"  Tổng lượt gọi        : {len(ts)} trong {kd:.0f}s")
print(f"  ĐỈNH cửa sổ 60 giây  : {dinh} lượt/phút   (hạn mức {quota})")
print(f"  Theo tài khoản       : " + ", ".join(f"{k}={v}" for k,v in sorted(theo_tk.items())))
print(f"  Vùng đọc nhiều nhất  : " + ", ".join(f"{k}×{v}" for k,v in theo_range.most_common(3)))
sys.exit(0 if dinh<=quota else 1)
PY
}

MODE="${MODE:-multi}"
chay_luot(){   # $1=nhãn  $2=state_ttl  $3=row_ttl  $4=thư_mục
    local NHAN="$1" STTL="$2" RTTL="$3" DIR="$4"
    mkdir -p "$DIR"; rm -f "$DIR/api_calls.log"
    gen_config "$STTL" "$RTTL"
    rm -rf logs pids data
    export RATE_LOG_DIR="$SB/$DIR"
    echo ""
    echo "▶ $NHAN  (state_cache_ttl_sec=$STTL, row_cache_ttl_sec=$RTTL)"
    echo "────────────────────────────────────────────────────────────"
    ORDER_BOT_MODE="$MODE" ./start_all_bots.sh >/dev/null 2>&1
    echo "  ⏳ đang chạy ${SECS}s (3 tài khoản, 50 mã)..."
    sleep "$SECS"

    # SỨC KHOẺ: bot chết thì tải đo được sẽ THẤP GIẢ TẠO → phải lộ ra
    local SONG=0 CHET=0 ACC
    for ACC in kh_a kh_b kh_c; do
        for f in pids/$ACC/*.pid; do
            [ -f "$f" ] || continue
            if kill -0 "$(cat "$f")" 2>/dev/null; then SONG=$((SONG+1)); else
                CHET=$((CHET+1)); echo "     💀 chết: $(basename "$f" .pid) [$ACC]"
            fi
        done
    done
    echo "  Bot đang chạy: $SONG   |   đã chết: $CHET"
    if [ "$CHET" -gt 0 ]; then
        echo "  ── lỗi đầu tiên ──"
        head -4 logs/kh_a/error.log 2>/dev/null | sed 's/^/     /'
    fi
    BOT_CHET=$CHET

    ./stop_all_bots.sh -y >/dev/null 2>&1
    sleep 2
}

# ══ LƯỢT A — TẮT cache (tái hiện lỗi cũ) ════════════════════════════════════
chay_luot "LƯỢT A — TẮT cache (mô phỏng code TRƯỚC khi sửa)" 0 0 truoc
phan_tich "$SB/truoc/api_calls.log" "TRƯỚC"; RC_A=$?

# ══ LƯỢT B — BẬT cache (bản đã sửa) ═════════════════════════════════════════
chay_luot "LƯỢT B — BẬT cache (code SAU khi sửa)" 10 60 sau
phan_tich "$SB/sau/api_calls.log" "SAU"; RC_B=$?

echo ""
echo "▶ BOT NGOÀI start_all_bots.sh (chạy tay) — kiểm tra khởi động"
echo "────────────────────────────────────────────────────────────"
export QBOT_ACCOUNT=kh_a
for B in hd_order_market_price hd_cancel_selective; do
    KQ=$(python3 - "$B" <<'PY2'
import subprocess, sys, time, re
b = sys.argv[1]
p = subprocess.Popen([sys.executable, b + ".py"], stdout=subprocess.PIPE,
                     stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace")
time.sleep(14)
song = p.poll() is None
p.kill(); out, _ = p.communicate()
loi = [l for l in out.split("\n") if re.search(r"Error|Exception", l)]
print(("SONG" if song else "CHET") + "|" + (loi[-1][:60] if loi else ""))
PY2
)
    TT="${KQ%%|*}"; MSG="${KQ#*|}"
    if [ "$TT" = "SONG" ] && [ -z "$MSG" ]; then ok "$B khởi động sạch"
    elif [ "$TT" = "SONG" ]; then ng "$B chạy nhưng có lỗi: $MSG"
    else ng "$B CHẾT: $MSG"; fi
done
for B in hd_update_danhmuc hd_isolated_crossed_converter; do
    echo "  ⏭️  $B — có input(), là công cụ CHẠY TAY hỏi đáp, không test tự động được"
done
unset QBOT_ACCOUNT

echo ""
echo "▶ KẾT LUẬN"
echo "────────────────────────────────────────────────────────────"
[ "$RC_A" -eq 1 ] && ok "TRƯỚC khi sửa: VƯỢT hạn mức → tái hiện đúng lỗi 429" \
                 || ng "TRƯỚC khi sửa lại KHÔNG vượt — bài đo chưa đủ tải, cần xem lại"
[ "$RC_B" -eq 0 ] && ok "SAU khi sửa: nằm TRONG hạn mức $QUOTA lượt/phút" \
                 || ng "SAU khi sửa VẪN vượt hạn mức — chưa đạt"

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  KẾT QUẢ:  ✅ $PASS đạt   ❌ $FAIL lỗi"
echo "  Sổ chi tiết: $SB/truoc/api_calls.log , $SB/sau/api_calls.log"
echo "════════════════════════════════════════════════════════════"
[ "$FAIL" -eq 0 ]
