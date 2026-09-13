#!/bin/bash
# ==============================================================================
# DIỄN TẬP BOT KIỂU CŨ: hd_order + hd_order_123 — chạy code THẬT, sàn/sheet GIẢ
#
#   bash tests/demo_order_cu.sh
#
#   1. hd_order đặt lệnh VÀO trailing đúng cột (C callback, D kích hoạt), vòng
#      sau KHÔNG đặt trùng — kể cả khi sửa giá cột D.
#   2. Bật hd_order_multi khi hd_order đang chạy → bị CHẶN (đặt lệnh trùng).
#   3. Vị thế khớp → hd_order_123 đặt cắt lỗ giá N + chốt lời trailing (O trống =
#      kích hoạt ngay, callback ô N1), vòng sau KHÔNG đặt trùng.
#   4. hd_order chạy chung hd_order_123 được; hd_order_multi thì bị chặn.
# ==============================================================================
set -u
QBOT="$(cd "$(dirname "$0")/.." && pwd)"
SB="/tmp/qbot_order_cu"
PASS=0; FAIL=0
ok(){ PASS=$((PASS+1)); echo "  ✅ $1"; }
ng(){ FAIL=$((FAIL+1)); echo "  ❌ $1"; }

echo "════════════════════════════════════════════════════════════"
echo "  DIỄN TẬP BOT KIỂU CŨ: hd_order + hd_order_123"
echo "════════════════════════════════════════════════════════════"
pkill -f "$SB/" 2>/dev/null
rm -rf "$SB"; mkdir -p "$SB"; cd "$SB" || exit 1

cp "$QBOT"/cst.py "$QBOT"/hd_order_multi.py "$QBOT"/hd_order.py "$QBOT"/hd_order_123.py \
   "$QBOT"/binance_order_helper.py "$QBOT"/rate_guard.py "$QBOT"/giu_cua_so.py \
   "$QBOT"/sheet_config.py "$QBOT"/config_watcher.py "$QBOT"/phan_loai_lenh.py .

python3 - "$QBOT" <<'PY'
import re, sys
s = open(sys.argv[1] + "/config.ini.example", encoding="utf-8").read()
s = re.sub(r'(?m)^(bot_id|config_spreadsheet_id)\s*=.*$', r'\1 =', s)
s = re.sub(r'(?m)^delay_vao_lenh\s*=.*$', 'delay_vao_lenh = 3', s)
s = re.sub(r'(?m)^delay_vao_lenh_123\s*=.*$', 'delay_vao_lenh_123 = 3', s)
s = re.sub(r'(?m)^callback_rate_123\s*=.*$', 'callback_rate_123 = 2', s)
s = s.replace("[global]\n", "[global]\naccounts = kh_a\n", 1)
s += "\n[kh_a]\nkey_binance = KEY_A\nsecret_binance = SEC_A\nspreadsheet_id = SHEET_A\nchat_id = -1\nkey_name = Khach A\n"
open("config.ini", "w", encoding="utf-8").write(s)
PY

# ── Sàn giả: lệnh đặt được lưu vào so_lenh.json → vòng sau đọc lại (chống trùng) ──
cat > san_gia.py <<'EOF'
import json, os
F = "so_lenh.json"
def doc():
    return json.load(open(F)) if os.path.exists(F) else {"thuong": [], "algo": []}
def ghi(d):
    json.dump(d, open(F, "w"))
def vi_the():
    if not os.path.exists("vi_the.txt"):
        return "0", "0"
    return open("vi_the.txt").read().strip().split("|")
EOF
cat > ccxt.py <<'EOF'
import san_gia
class binance:
    def __init__(self, *a, **k):
        self.markets = {"ATOM/USDT:USDT": {"active": True, "info": {"status": "TRADING"}}}
    def setSandboxMode(self, *a, **k): pass
    def load_markets(self, *a, **k): return self.markets
    def price_to_precision(self, s, v): return round(float(v), 4)
    def amount_to_precision(self, s, v): return round(float(v), 2)
    def fetch_ticker(self, s): return {"last": 2.0}
    def setLeverage(self, l, s): pass
    def fetch_balance(self):
        amt, gia = san_gia.vi_the()
        return {"info": {"positions": [{"symbol": "ATOMUSDT", "positionAmt": amt, "entryPrice": gia}]}}
    def fetch_open_orders(self, s=None):
        return san_gia.doc()["thuong"]
    def create_order(self, symbol, type, side, amount, price=None, params=None):
        params = params or {}
        d = san_gia.doc()
        cp = str(params.get("closePosition", "")).lower() == "true"
        d["thuong"].append({"id": f"O{len(d['thuong'])+1}", "type": type.lower(), "side": side,
                            "amount": amount, "stopPrice": params.get("stopPrice"),
                            "reduceOnly": bool(params.get("reduceOnly")),
                            "info": {"closePosition": "true" if cp else "false", "origType": type}})
        san_gia.ghi(d)
        return {"id": d["thuong"][-1]["id"], "info": {}}
    def fapiPrivatePostAlgoOrder(self, p):
        d = san_gia.doc()
        d["algo"].append({"algoId": len(d["algo"]) + 1, "algoStatus": "NEW", "side": p["side"],
                          "orderType": p["type"], "activatePrice": p["activatePrice"],
                          "callbackRate": p["callbackRate"], "quantity": p["quantity"],
                          "reduceOnly": p.get("reduceOnly") == "true"})
        san_gia.ghi(d)
        return {"clientAlgoId": f"A{len(d['algo'])}", "algoStatus": "NEW"}
EOF
cat > binance_futures_direct.py <<'EOF'
import san_gia
def fetch_algo_orders_for_symbol(*a, **k): return san_gia.doc()["algo"]
def resync_exchange_time(*a, **k): pass
EOF
cat > telegram_factory.py <<'EOF'
def send_tele(*a, **k): pass
EOF
# ── Sheet giả: giá cột D đọc từ gia_d.txt (sửa file = sửa sheet) ──────────────
cat > gg_sheet_factory.py <<'EOF'
import cst
tab_dat_lenh = cst.tab_dat_lenh
tab_cho_va_khop = "Chờ và khớp"
def init_sheet_api(): pass
def get_dat_lenh(rng):
    if rng.startswith("B2"): return [["LONG"]]
    if rng.startswith("D1"): return [["1%", ""], ["10", "10"]]
    d = open("gia_d.txt").read().strip()
    #        A            B    C=callback D=kích hoạt E  F   G   H=vốn
    return [["ATOM/USDT", "5", "1.5",     d,         "", "", "", "20"]]
def get_cho_va_khop(rng, value_render_option=None):
    h1 = [""] * 13 + [0.8]                        # N1 = callback 0.8%
    dong = ["ATOM/USDT", "LONG", "N", "Y", 1.95, 5, "N", "N", 0, "", "", "", "",
            1.8, "", "Y"]                         # N = 1.8 cắt lỗ · O trống = ngay · P = Y
    return [h1, [], [], dong] if rng.startswith("A1") else [dong]
def update_single_value(*a, **k): pass
def update_multi(*a, **k): pass
EOF
mkdir -p googleapiclient
: > googleapiclient/__init__.py
echo "class HttpError(Exception): pass" > googleapiclient/errors.py

chay(){ QBOT_ACCOUNT=kh_a QBOT_GIU_CUA_SO=0 nohup python3 -u "$1" > "$2" 2>&1 & echo $!; }
dem(){ python3 -c "import san_gia,sys; d=san_gia.doc(); print(sum(1 for o in d['thuong']+d['algo'] if $1))"; }

echo ""
echo "▶ 1 — hd_order: lệnh VÀO trailing"
echo "────────────────────────────────────────────"
echo "1.9" > gia_d.txt
P1=$(chay "$SB/hd_order.py" order.log)
sleep 5
[ "$(dem "o.get('orderType')=='TRAILING_STOP_MARKET' and o['side']=='BUY'")" = "1" ] \
  && ok "Đặt 1 lệnh TRAILING MUA" || ng "Không thấy lệnh trailing mua ($(cat so_lenh.json 2>/dev/null))"
python3 -c "import san_gia; a=san_gia.doc()['algo'][0]; assert a['activatePrice']=='1.9' and a['callbackRate']=='1.5' and not a['reduceOnly']" 2>/dev/null \
  && ok "Kích hoạt = cột D (1.9), callback = cột C (1.5%), không reduceOnly" || ng "Sai cột: $(cat so_lenh.json)"
echo "1.85" > gia_d.txt
sleep 7
[ "$(dem "True")" = "1" ] && ok "Qua nhiều vòng + SỬA giá D → vẫn 1 lệnh (không vào lệnh thứ hai)" \
                          || ng "🔴 Đặt trùng: $(cat so_lenh.json)"

echo ""
echo "▶ 2 — Bật hd_order_multi khi hd_order đang chạy"
echo "────────────────────────────────────────────"
PM=$(chay "$SB/hd_order_multi.py" multi.log)
sleep 5
kill -0 "$PM" 2>/dev/null && { ng "🔴 hd_order_multi vẫn chạy song song"; kill "$PM"; } || ok "hd_order_multi tự DỪNG"
grep -q "ĐẶT LỆNH TRÙNG" multi.log && ok "   báo rõ: ĐẶT LỆNH TRÙNG" || ng "   không báo lý do: $(tail -3 multi.log)"
kill -0 "$P1" 2>/dev/null && ok "hd_order vẫn chạy bình thường" || ng "hd_order bị chết theo"
kill "$P1" 2>/dev/null; sleep 2

echo ""
echo "▶ 3 — Vị thế đã khớp → hd_order_123 đặt SL/TP"
echo "────────────────────────────────────────────"
echo '{"thuong": [], "algo": []}' > so_lenh.json      # lệnh vào đã khớp, không còn treo
echo "10|1.95" > vi_the.txt
P3=$(chay "$SB/hd_order_123.py" o123.log)
sleep 5
[ "$(dem "o.get('info',{}).get('closePosition')=='true' and o['side']=='sell' and float(o['stopPrice'])==1.8")" = "1" ] \
  && ok "Cắt lỗ STOP MARKET BÁN tại giá N (1.8), closePosition" || ng "Không thấy cắt lỗ đúng: $(cat so_lenh.json)"
python3 -c "
import san_gia; a=[x for x in san_gia.doc()['algo'] if x['orderType']=='TRAILING_STOP_MARKET']
assert len(a)==1 and a[0]['side']=='SELL' and a[0]['reduceOnly'] and a[0]['callbackRate']=='0.8'
assert 1.99 <= float(a[0]['activatePrice']) < 2.0 and float(a[0]['quantity'])==10" 2>/dev/null \
  && ok "Chốt lời TRAILING BÁN: kích hoạt ngay (~giá hiện tại), callback ô N1 = 0.8%, KL 10" \
  || ng "Chốt lời sai: $(cat so_lenh.json)"
sleep 7
[ "$(dem "True")" = "2" ] && ok "Qua nhiều vòng → vẫn đúng 2 lệnh (không đặt trùng)" || ng "🔴 Đặt trùng: $(cat so_lenh.json)"

echo ""
echo "▶ 4 — Chạy chung"
echo "────────────────────────────────────────────"
PM=$(chay "$SB/hd_order_multi.py" multi2.log)
sleep 5
kill -0 "$PM" 2>/dev/null && { ng "🔴 hd_order_multi chạy chung với hd_order_123"; kill "$PM"; } \
  || { grep -q "ĐẶT LỆNH TRÙNG" multi2.log && ok "hd_order_multi bị CHẶN khi hd_order_123 đang chạy" || ng "multi dừng nhưng không báo lý do"; }
P4=$(chay "$SB/hd_order.py" order2.log)
sleep 6
kill -0 "$P4" 2>/dev/null && ok "hd_order + hd_order_123 chạy chung được" || ng "hd_order bị chặn nhầm: $(tail -3 order2.log)"
[ "$(dem "True")" = "2" ] && ok "Có vị thế → hd_order không vào thêm lệnh" || ng "🔴 $(cat so_lenh.json)"

kill "$P3" "$P4" 2>/dev/null; sleep 1
pkill -f "$SB/" 2>/dev/null
echo ""
echo "════════════════════════════════════════════════════════════"
echo "  KẾT QUẢ:  ✅ $PASS đạt   ❌ $FAIL lỗi"
echo "  Nhật ký: $SB/*.log"
echo "════════════════════════════════════════════════════════════"
[ "$FAIL" -eq 0 ]
