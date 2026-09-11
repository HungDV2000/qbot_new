"""
Bot XOÁ LỆNH THEO TICK — tab "Chờ và khớp", cột J–M.

Người dùng tick vào dòng của một mã, bot xoá lệnh tương ứng trên Binance:
  J  XOÁ ENTRY     → xoá lệnh VÀO còn treo (không đụng SL/TP)
  K  XOÁ SL/TP     → xoá cả cắt lỗ lẫn chốt lời
  L  XOÁ LỆNH SÓT  → chỉ xoá khi còn SÓT MỘT phía (chỉ còn SL hoặc chỉ còn TP)
  M  XOÁ TẤT CẢ    → xoá mọi lệnh của mã (dùng khi vị thế đã ĐÓNG)
Xử lý xong: xoá dấu tick, cập nhật lại G/H/I của dòng đó, báo Telegram.

Giá trị tick được nhận: TRUE (ô checkbox), Y, YES, X, 1, ✓ …  (N/FALSE/trống = không)

Khác bản cũ trong qbot_setup:
  • Nhận đúng SL kiểu closePosition (bot multi đặt) — bản cũ coi nó là lệnh
    VÀO nên tick J xoá luôn cả cắt lỗ.
  • Nhận đúng TP kiểu LIMIT reduceOnly (bot multi đặt) — bản cũ bỏ sót nên
    tick K không xoá được chốt lời.
  • Log theo từng tài khoản; tự nạp lại khi đổi key trên sheet tổng.
  • Xoá tick theo MÃ (tìm lại dòng ngay trước khi xoá), không theo số dòng cũ.
  • Đã xoá lệnh mà chưa xoá được tick → KHÔNG xoá lệnh lần 2.
"""

import giu_cua_so  # PHẢI nạp ĐẦU TIÊN: dừng/lỗi thì giữ cửa sổ Windows để đọc thông báo
import ccxt
import cst
import config_watcher
import cot_nguoi_dung
import gg_sheet_factory
from phan_loai_lenh import kieu as _kieu, phan_loai
import telegram_factory
import logging
import os
import time
from datetime import datetime
from binance_futures_direct import (
    fetch_algo_orders_for_symbol,
    futures_signed_request,
    resync_exchange_time,
)

file_name = os.path.basename(os.path.abspath(__file__))
os.system(f"title {file_name} - {cst.key_name}")

logs_dir = cst.account_dir('logs')  # [MULTI-ACC] tách theo tài khoản
logs_dir.mkdir(exist_ok=True)
log_filename = logs_dir / f"hd_cancel_selective_{datetime.now().strftime('%d_%m_%Y_%H_%M_%S')}.txt"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    encoding='utf-8'
)
logger = logging.getLogger(__name__)
file_handler = logging.FileHandler(log_filename, encoding='utf-8')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
file_handler.setLevel(logging.INFO)
logger.addHandler(file_handler)

exchange = ccxt.binance({
    'enableRateLimit': True,
    'apiKey': cst.key_binance,
    'secret': cst.secret_binance,
    'options': {
        'defaultType': 'future',
        'fetchCurrencies': False,
        'adjustForTimeDifference': True,
        'recvWindow': 60000,
    }
})
exchange.setSandboxMode(False)

try:
    CHU_KY_GIAY = max(15, cst.config.getint('global', 'cancel_selective_seconds', fallback=60))
except Exception:
    CHU_KY_GIAY = 60

DONG_DAU = 4
VUNG_DOC = "A4:P1000"
VUNG_TIM_LAI = "A4:B1000"
COT_TICK = (("J", 9), ("K", 10), ("L", 11), ("M", 12))
TEN_COT = {"J": "XOÁ ENTRY", "K": "XOÁ SL/TP", "L": "XOÁ LỆNH SÓT", "M": "XOÁ TẤT CẢ"}
GIA_TRI_TICK = {"Y", "YES", "TRUE", "1", "X", "TICK", "✓", "✔"}

# Tick vừa xử lý: {(khoá dòng, cột): {"t": lúc xử lý, "da_xoa_tick": bool}}
#   • Chưa xoá được tick trên sheet → chỉ thử xoá tick lại, KHÔNG xoá lệnh lần 2
#     (tick J lần 2 sẽ xoá cả lệnh vào mới đặt sau đó).
#   • Đã xoá tick mà tick hiện lại trong CHAN_LAP_GIAY → là tick "ma" do
#     hd_update_cho_va_khop ghi lại J–P từ ảnh chụp cũ → chỉ xoá tick.
CHAN_LAP_GIAY = 180
_vua_xu_ly = {}


def has_delete_tick(value):
    """Tick xoá phải rõ ràng để tránh kích hoạt nhầm."""
    if value is None:
        return False
    return str(value).strip().upper() in GIA_TRI_TICK


def format_symbol_ccxt(symbol):
    """HOME/USDT hoặc HOMEUSDT → HOME/USDT:USDT"""
    symbol = symbol.strip().upper()
    if ':USDT' in symbol:
        return symbol
    if '/' in symbol:
        return f"{symbol}:USDT"
    if symbol.endswith('USDT'):
        return f"{symbol[:-4]}/USDT:USDT"
    return f"{symbol}/USDT:USDT"


def _ma_api(symbol):
    return symbol.replace('/', '').replace(':USDT', '')


# ── Lấy / huỷ lệnh trên Binance ──────────────────────────────────────────────

def _lay_lenh(symbol):
    """(lệnh thường, algo NEW/TRIGGERED, lấy_đủ). lấy_đủ=False nếu 1 trong 2 API lỗi."""
    du = True
    try:
        thuong = exchange.fetch_open_orders(symbol) or []
    except Exception as e:
        logger.error(f"Lỗi lấy lệnh thường {symbol}: {e}")
        thuong, du = [], False
    try:
        ds = fetch_algo_orders_for_symbol(symbol)
    except Exception as e:
        logger.error(f"Lỗi lấy algo {symbol}: {e}")
        ds = None
    if ds is None:
        algo, du = [], False
    else:
        algo = [a for a in ds if str(a.get('algoStatus', '')).upper() in ('NEW', 'TRIGGERED')]
    return thuong, algo, du


def _huy(symbol, o, la_algo):
    try:
        if la_algo:
            r = futures_signed_request('DELETE', '/fapi/v1/algoOrder',
                                       {'symbol': _ma_api(symbol), 'algoId': o.get('algoId')})
            ok = isinstance(r, dict) and (str(r.get('code', '')) == '200' or r.get('algoId') is not None)
            if not ok:
                logger.warning(f"Không huỷ được algo {o.get('algoId')} {symbol}: {r}")
            return ok
        exchange.cancel_order(o.get('id'), symbol)
        return True
    except Exception as e:
        logger.error(f"Lỗi huỷ {'algo ' + str(o.get('algoId')) if la_algo else 'lệnh ' + str(o.get('id'))} {symbol}: {e}")
        return False


def _mo_ta(o, la_algo):
    if la_algo:
        return f"{phan_loai(o, True)} algo #{o.get('algoId')} ({o.get('algoStatus', '')})"
    return f"{phan_loai(o)} #{o.get('id')} ({_kieu(o) or 'ORDER'})"


def _huy_nhom(symbol, thuong, algo):
    items = []
    for o in thuong:
        if _huy(symbol, o, False):
            items.append(_mo_ta(o, False))
    for a in algo:
        if _huy(symbol, a, True):
            items.append(_mo_ta(a, True))
    return items


def xoa_entry(symbol):
    thuong, algo, _ = _lay_lenh(symbol)
    return _huy_nhom(symbol,
                     [o for o in thuong if phan_loai(o) == 'ENTRY'],
                     [a for a in algo if phan_loai(a, True) == 'ENTRY']), None


def xoa_sl_tp(symbol):
    thuong, algo, _ = _lay_lenh(symbol)
    return _huy_nhom(symbol,
                     [o for o in thuong if phan_loai(o) in ('SL', 'TP')],
                     [a for a in algo if phan_loai(a, True) in ('SL', 'TP')]), None


def xoa_sot(symbol):
    thuong, algo, du = _lay_lenh(symbol)
    if not du:
        return [], "không lấy đủ danh sách lệnh — bỏ qua cho an toàn"
    loai = [phan_loai(o) for o in thuong] + [phan_loai(a, True) for a in algo]
    co_sl, co_tp = 'SL' in loai, 'TP' in loai
    if co_sl and co_tp:
        return [], "đang có đủ cả SL và TP — muốn xoá cặp thì tick K"
    if not co_sl and not co_tp:
        return [], "không còn SL/TP nào trên sàn"
    phia = 'SL' if co_sl else 'TP'
    return _huy_nhom(symbol,
                     [o for o in thuong if phan_loai(o) == phia],
                     [a for a in algo if phan_loai(a, True) == phia]), None


def xoa_tat_ca(symbol):
    thuong, algo, _ = _lay_lenh(symbol)
    return _huy_nhom(symbol, thuong, algo), None


HANH_DONG = {"J": xoa_entry, "K": xoa_sl_tp, "L": xoa_sot, "M": xoa_tat_ca}


def trang_thai_ghi(symbol):
    """G/H/I sau khi xoá: (Có SL, Có TP, số lệnh). None nếu không lấy đủ."""
    thuong, algo, du = _lay_lenh(symbol)
    if not du:
        return None
    loai = [phan_loai(o) for o in thuong] + [phan_loai(a, True) for a in algo]
    return ["Y" if 'SL' in loai else "N", "Y" if 'TP' in loai else "N", len(thuong) + len(algo)]


# ── Sheet ─────────────────────────────────────────────────────────────────────

def _doc_cac_dong(rows):
    """[(số dòng, khoá, mã, cột D, [cột có tick])] cho các dòng có mã hợp lệ."""
    khoa = cot_nguoi_dung.khoa_cac_dong(rows)
    out = []
    for i, row in enumerate(rows):
        k = khoa[i]
        if k is None or "USDT" not in k[0]:
            continue
        cols = [c for c, j in COT_TICK if j < len(row) and has_delete_tick(row[j])]
        d = str(row[3]).strip().upper() if len(row) > 3 and row[3] is not None else ""
        out.append((DONG_DAU + i, k, str(row[0]).strip(), d, cols))
    return out


def _tim_lai_vi_tri():
    """{khoá: số dòng hiện tại}. None nếu đọc lỗi."""
    try:
        rows = gg_sheet_factory.get_cho_va_khop(VUNG_TIM_LAI) or []
    except Exception as e:
        logger.error(f"Không đọc lại được vị trí dòng: {e}")
        return None
    return {k: DONG_DAU + i for i, k in enumerate(cot_nguoi_dung.khoa_cac_dong(rows)) if k is not None}


def _xoa_tick(o_can_xoa):
    if not o_can_xoa:
        return True
    try:
        gg_sheet_factory.batch_clear_values(gg_sheet_factory.tab_cho_va_khop, o_can_xoa)
        print(f"   🧽 Đã xoá tick: {', '.join(o_can_xoa)}", flush=True)
        return True
    except Exception as e:
        logger.error(f"Lỗi xoá tick {o_can_xoa}: {e}")
        print(f"   ⚠️  Chưa xoá được tick ({e}) — lượt sau thử lại, KHÔNG xoá lệnh lần 2", flush=True)
        return False


def _gui_bao_cao(bao_cao):
    khoi = []
    tong = 0
    for bc in bao_cao:
        dong = bc["dong_moi"] or bc["dong"]
        dau = f"<b>• {bc['ma']}</b> — dòng {dong}" + (f" <code>[D={bc['d']}]</code>" if bc['d'] else "")
        dong_ct = [dau]
        for c, items, ly_do in bc["chi_tiet"]:
            tong += len(items)
            s = f"  <b>{c} — {TEN_COT[c]}:</b> đã huỷ {len(items)}"
            if ly_do:
                s += f" <i>({ly_do})</i>"
            for it in items[:10]:
                s += f"\n    ▸ {it}"
            if len(items) > 10:
                s += f"\n    ▸ … (+{len(items) - 10} nữa)"
            dong_ct.append(s)
        if bc["dong_moi"] is None:
            dong_ct.append("  ⚠️ <i>Không tìm lại được dòng của mã để xoá tick</i>")
        khoi.append("\n".join(dong_ct))
    msg = (f"🧹 <b>XOÁ LỆNH THEO TICK</b> — {cst.key_name}\n"
           f"Tổng lệnh đã huỷ: <b>{tong}</b> · {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
           + "\n\n".join(khoi))
    try:
        telegram_factory.send_tele(msg, cst.chat_id, True, True)
    except Exception as e:
        logger.error(f"Lỗi gửi Telegram: {e}")


def xu_ly_mot_vong():
    rows = gg_sheet_factory.get_cho_va_khop(VUNG_DOC) or []
    cac_dong = _doc_cac_dong(rows)
    bay_gio = time.time()

    con_tick = {(k, c) for _, k, _, _, cols in cac_dong for c in cols}
    for kc, e in list(_vua_xu_ly.items()):
        if kc not in con_tick and (not e["da_xoa_tick"] or bay_gio - e["t"] >= CHAN_LAP_GIAY):
            del _vua_xu_ly[kc]      # người dùng tự bỏ tick / mã rời bảng / hết hạn chặn lặp

    viec, chi_xoa_tick = [], []
    for so_dong, k, ma, d, cols in cac_dong:
        moi = []
        for c in cols:
            e = _vua_xu_ly.get((k, c))
            if e is None or (e["da_xoa_tick"] and bay_gio - e["t"] >= CHAN_LAP_GIAY):
                moi.append(c)
            else:
                chi_xoa_tick.append((k, c, f"{c}{so_dong}"))
                logger.info(f"{ma} {c}: đã xử lý lúc {datetime.fromtimestamp(e['t']):%H:%M:%S} — chỉ xoá tick")
        if moi:
            viec.append((so_dong, k, ma, d, moi))

    if chi_xoa_tick and _xoa_tick([o for _, _, o in chi_xoa_tick]):
        for k, c, _ in chi_xoa_tick:
            _vua_xu_ly[(k, c)]["da_xoa_tick"] = True

    if not viec:
        print(f"[{datetime.now():%H:%M:%S}] ℹ️  Không có tick xoá mới", flush=True)
        return

    bao_cao = []
    for so_dong, k, ma, d, cols in viec:
        sym = format_symbol_ccxt(ma)
        print(f"\n🔍 Dòng {so_dong} {ma}: tick {', '.join(cols)}", flush=True)
        chi_tiet = []
        for c in cols:
            if c == "L" and "K" in cols:
                chi_tiet.append((c, [], "bỏ qua vì K cũng tick — K đã xoá cặp SL/TP"))
                continue
            if c == "M" and d != "ĐÓNG":
                logger.warning(f"{ma}: tick M khi D={d} (không phải ĐÓNG) — vẫn xoá theo yêu cầu")
            try:
                items, ly_do = HANH_DONG[c](sym)
            except Exception as e:
                logger.error(f"Lỗi {c} {ma}: {e}", exc_info=True)
                items, ly_do = [], f"lỗi: {e}"
            if c == "M" and d != "ĐÓNG":
                ly_do = ((ly_do + "; ") if ly_do else "") + f"D={d or 'trống'}, vị thế có thể CHƯA đóng"
            print(f"   {c} — {TEN_COT[c]}: huỷ {len(items)}" + (f" ({ly_do})" if ly_do else ""), flush=True)
            logger.info(f"{ma} {c}: huỷ {len(items)} {items} {ly_do or ''}")
            chi_tiet.append((c, items, ly_do))
        for c in cols:
            _vua_xu_ly[(k, c)] = {"t": time.time(), "da_xoa_tick": False}
        bao_cao.append({"dong": so_dong, "khoa": k, "ma": ma, "sym": sym, "d": d,
                        "cols": cols, "chi_tiet": chi_tiet, "dong_moi": None})

    # Xử lý mất vài giây — dòng có thể đã xê dịch → tìm lại vị trí theo MÃ rồi mới xoá tick
    vi_tri = _tim_lai_vi_tri()
    o_xoa = []
    for bc in bao_cao:
        bc["dong_moi"] = vi_tri.get(bc["khoa"]) if vi_tri is not None else None
        if bc["dong_moi"] is not None:
            o_xoa += [f"{c}{bc['dong_moi']}" for c in bc["cols"]]
    if o_xoa and _xoa_tick(o_xoa):
        for bc in bao_cao:
            if bc["dong_moi"] is not None:
                for c in bc["cols"]:
                    _vua_xu_ly[(bc["khoa"], c)]["da_xoa_tick"] = True

    for bc in bao_cao:
        if bc["dong_moi"] is None:
            continue
        ghi = trang_thai_ghi(bc["sym"])
        if ghi is None:
            continue
        try:
            gg_sheet_factory.update_multi(gg_sheet_factory.tab_cho_va_khop, -bc["dong_moi"], [ghi], "G")
        except Exception as e:
            logger.error(f"Lỗi cập nhật G/H/I dòng {bc['dong_moi']}: {e}")

    _gui_bao_cao(bao_cao)


def xu_ly_an_toan():
    try:
        xu_ly_mot_vong()
    except Exception as e:
        if '-1021' in str(e) or 'recvWindow' in str(e):
            resync_exchange_time(exchange, min_interval=0)
        print(f"❌ Lỗi vòng xoá lệnh theo tick: {e}", flush=True)
        logger.error(f"Lỗi vòng xoá lệnh theo tick: {e}", exc_info=True)


# Main loop
print(f"🚀 Bot xoá lệnh theo tick J–M khởi động — đọc tick mỗi {CHU_KY_GIAY} giây", flush=True)
logger.info(f"Khởi động hd_cancel_selective — chu kỳ {CHU_KY_GIAY}s")

xu_ly_an_toan()
while True:
    try:
        config_watcher.ngu(CHU_KY_GIAY)
        resync_exchange_time(exchange)
        xu_ly_an_toan()
    except KeyboardInterrupt:
        print("\n⚠️  Nhận Ctrl+C - Dừng bot...", flush=True)
        logger.info("Bot dừng bởi user (Ctrl+C)")
        break

print("👋 Bot đã dừng", flush=True)
logger.info("Bot đã dừng")
