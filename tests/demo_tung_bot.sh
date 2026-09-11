#!/bin/bash
# ==============================================================================
# DIỄN TẬP BẬT / TẮT TỪNG BOT — start_bot.sh / stop_bot.sh
#
#   bash tests/demo_tung_bot.sh
#
# Sandbox trong /tmp: cst.py + script THẬT, bot giả (chỉ ngủ), 2 tài khoản.
# Không mạng, không tiền thật.
# ==============================================================================
set -u
QBOT="$(cd "$(dirname "$0")/.." && pwd)"
SB="/tmp/qbot_tungbot"
PASS=0; FAIL=0
ok(){ PASS=$((PASS+1)); echo "  ✅ $1"; }
ng(){ FAIL=$((FAIL+1)); echo "  ❌ $1"; }
song(){ local P; P="$(cat "$1" 2>/dev/null)"; [ -n "$P" ] && kill -0 "$P" 2>/dev/null; }

echo "════════════════════════════════════════════════════════════"
echo "  DIỄN TẬP BẬT / TẮT TỪNG BOT"
echo "════════════════════════════════════════════════════════════"

rm -rf "$SB"; mkdir -p "$SB"; cd "$SB" || exit 1
cp "$QBOT"/cst.py "$QBOT"/rate_guard.py "$QBOT"/sheet_config.py "$QBOT"/config_watcher.py .
cp "$QBOT"/start_bot.sh "$QBOT"/stop_bot.sh "$QBOT"/status.sh .
chmod +x ./*.sh

python3 - "$QBOT" <<'PY'
import sys, re
src = open(sys.argv[1] + "/config.ini.example", encoding="utf-8").read()
src = re.sub(r'(?m)^(bot_id|config_spreadsheet_id)\s*=.*$', r'\1 =', src)
src = re.sub(r'(?m)^account_start_stagger_sec\s*=.*$', 'account_start_stagger_sec = 0', src)
src = src.replace("[global]\n", "[global]\naccounts = kh_a, kh_b\n", 1)
for a in ("kh_a", "kh_b"):
    src += f"\n[{a}]\nkey_binance = KEY_{a}_1234567890\nsecret_binance = SEC_{a}_1234567890\nspreadsheet_id = SHEET_{a}\n"
open("config.ini", "w", encoding="utf-8").write(src)
PY
cat > telegram_factory.py <<'EOF'
def send_tele(*a, **k): pass
EOF
cat > binance_futures_direct.py <<'EOF'
def futures_signed_request(*a, **k): return {}
def resync_exchange_time(*a, **k): pass
EOF
for b in hd_update_cho_va_khop hd_order_multi hd_alert_possition_and_open_order \
         hd_cancel_selective hd_cancel_orders_schedule hd_update_all; do
cat > $b.py <<'EOF'
import cst, time
print(f"[{cst.account_name}] đang chạy", flush=True)
time.sleep(600)
EOF
done

echo ""
echo "▶ 1. Danh sách & tên sai"
./start_bot.sh | grep -q "hd_cancel_selective" && ok "Không tham số → in danh sách 6 bot" || ng "Không in danh sách"
./start_bot.sh hd_khong_co >/dev/null 2>&1 && ng "Tên sai vẫn chạy" || ok "Tên bot sai → báo lỗi"

echo ""
echo "▶ 2. Bật 1 bot cho MỌI tài khoản"
./start_bot.sh hd_update_all | sed 's/^/     /'
sleep 5
song pids/hd_update_all.pid && ok "Điều phối hd_update_all đang chạy" || ng "Điều phối không chạy"
song pids/kh_a/hd_update_all.lock && song pids/kh_b/hd_update_all.lock \
    && ok "Tự mở tiến trình con cho kh_a và kh_b" || ng "Thiếu tiến trình con"
ALL_PIDS="$(cat pids/hd_update_all.pid pids/kh_a/hd_update_all.lock pids/kh_b/hd_update_all.lock 2>/dev/null)"
for f in hd_order_multi hd_cancel_selective; do
    [ -f "pids/$f.pid" ] && ng "Bật lây sang $f" || true
done
ok "Chỉ bật đúng bot được gọi (các bot khác không chạy)"

echo ""
echo "▶ 3. Chống bật chồng"
./start_bot.sh hd_update_all 2>&1 | grep -q "đang chạy" && ok "Bật lại cùng bot → CHẶN" || ng "Không chặn bật trùng"
./start_bot.sh hd_update_all kh_a 2>&1 | grep -q "MỌI tài khoản" && ok "Bật riêng kh_a khi điều phối chung đang chạy → CHẶN" || ng "Không chặn trùng kh_a"

echo ""
echo "▶ 4. Bật 1 bot cho RIÊNG 1 tài khoản"
./start_bot.sh hd_alert_possition_and_open_order kh_b | sed 's/^/     /'
sleep 3
song pids/kh_b/hd_alert_possition_and_open_order.lock && ok "hd_alert chạy riêng cho kh_b" || ng "hd_alert kh_b không chạy"
[ -f pids/kh_a/hd_alert_possition_and_open_order.lock ] && ng "Bật lây sang kh_a" || ok "kh_a không bị bật theo"
./start_bot.sh hd_alert_possition_and_open_order 2>&1 | grep -q "riêng cho \[kh_b\]" \
    && ok "Bật cho mọi tài khoản khi kh_b đang chạy riêng → CHẶN" || ng "Không chặn trộn 2 cách chạy"
ALERT_PID="$(cat pids/kh_b/hd_alert_possition_and_open_order.lock 2>/dev/null)"

echo ""
echo "▶ 5. status.sh thấy bot đang chạy"
./status.sh 2>&1 | grep -q "hd_update_all" && ok "status.sh liệt kê hd_update_all" || ng "status.sh không thấy"

echo ""
echo "▶ 6. Dừng 1 bot (mọi tài khoản) — bot khác không bị ảnh hưởng"
./stop_bot.sh hd_update_all | sed 's/^/     /'
sleep 1
CON=0; for P in $ALL_PIDS; do kill -0 "$P" 2>/dev/null && CON=$((CON+1)); done
[ "$CON" = 0 ] && ok "Điều phối + 2 con của hd_update_all đã dừng hết" || ng "Còn $CON tiến trình hd_update_all"
kill -0 "$ALERT_PID" 2>/dev/null && ok "hd_alert [kh_b] VẪN chạy" || ng "hd_alert bị dừng oan"

echo ""
echo "▶ 7. Dừng bot riêng tài khoản"
./stop_bot.sh hd_alert_possition_and_open_order kh_b | sed 's/^/     /'
sleep 1
kill -0 "$ALERT_PID" 2>/dev/null && ng "hd_alert kh_b vẫn chạy" || ok "hd_alert kh_b đã dừng"
./stop_bot.sh hd_order_multi | grep -q "không chạy" && ok "Dừng bot không chạy → báo rõ, không lỗi" || ng "Báo sai khi bot không chạy"

# dọn
for P in $ALL_PIDS $ALERT_PID; do kill -9 "$P" 2>/dev/null; done

echo ""
echo "════════════════════════════════════════════════════════════"
echo "  KẾT QUẢ:  ✅ $PASS đạt   ❌ $FAIL lỗi"
echo "════════════════════════════════════════════════════════════"
[ "$FAIL" -eq 0 ]
