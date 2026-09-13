# -*- coding: utf-8 -*-
"""
THỬ ĐẶT LỆNH THẬT trên Binance Futures — lần lượt từng loại lệnh, đặt lên được
thì HUỶ NGAY để giữ vốn. Ghi log từng bước.

  ⚠️ CHAY_THAT = True là GỬI LỆNH THẬT BẰNG TIỀN THẬT.
  ⚠️ Tên file cố ý KHÔNG bắt đầu bằng "test_" để không bị chạy chung bộ test.
  ⚠️ Đã điền key thì ĐỪNG commit/push file này lên git.

Cách chạy:
    1. Sửa khối THÔNG SỐ bên dưới (key, mã, vốn…). Để CHAY_THAT = False chạy thử
       trước: chỉ in kế hoạch giá/khối lượng, không gửi lệnh.
    2. Thấy ổn → đổi CHAY_THAT = True rồi chạy lại:
           python tests/thu_dat_lenh_that.py
    3. Xem kết quả cuối màn hình, chi tiết trong logs/thu_dat_lenh_<ngày_giờ>.txt

Đặt lệnh VÀ huỷ lệnh bằng CHÍNH hàm của bot → lệnh nào lỗi ở đây thì bot thật
cũng sẽ lỗi y như vậy:
  • đặt : binance_order_helper (hd_order_multi / hd_order / hd_order_123)
  • huỷ : cancel_all_open_orders_with_retry (hd_alert dọn lệnh khi đóng vị thế)
          cancel_algo_orders — lệnh điều kiện (STOP / XÓA CHỜ / hd_alert)
  Kiểm "đã hết lệnh" bằng REST riêng — không tin chính hàm vừa huỷ.
  Hai hàm huỷ của bot xoá MỌI lệnh của mã → mã thử phải KHÔNG có lệnh nào sẵn.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import giu_cua_so  # noqa: E402  Windows: dừng/lỗi thì giữ cửa sổ để đọc

# ══════════════════════════════════════════════════════════════════════════════
#  THÔNG SỐ — SỬA Ở ĐÂY
# ══════════════════════════════════════════════════════════════════════════════
API_KEY = ""
API_SECRET = ""

MA = "ARBUSDT"           # mã thử (DOGEUSDT, DOGE/USDT, DOGE… đều được). ARB: bước khối lượng rất mịn
DON_BAY = 20             # đòn bẩy đặt cho mã thử → lệnh 5.5 USDT chỉ giữ ~0.28 USDT ký quỹ
VON_USDT = 5.5           # giá trị MỖI lệnh (USDT). Binance tối thiểu 5 (có mã 20 / 100)
CHIEU = "buy"            # buy = thử phía LONG · sell = thử phía SHORT
CACH_GIA_PCT = 5         # lệnh chờ đặt cách giá hiện tại ngần này % → KHÔNG khớp
CALLBACK_PCT = 1         # callback % cho lệnh trailing (0.1 – 10)
CHO_GIAY = 2             # nghỉ giữa các bước (giây) — để kịp nhìn lệnh trên app

CHAY_THAT = False        # False = chỉ in kế hoạch · True = GỬI LỆNH THẬT

THU = {
    # ── Lệnh VÀO chờ (đặt xa giá → không khớp → huỷ ngay, KHÔNG tốn phí) ──
    "limit":       True,     # kiểu 1
    "stop_market": True,     # kiểu 3
    "stop_limit":  True,     # kiểu 4
    "trailing":    True,     # kiểu 5
    # ── ⚠️ Các mục dưới KHỚP THẬT → mở vị thế nhỏ rồi đóng ngay (mất phí + trượt giá) ──
    "market":      False,    # kiểu 2: mua/bán market rồi đóng lại
    "lenh_thoat":  False,    # mở vị thế → thử CẮT LỖ closePosition, CHỐT LỜI limit,
                             # CHỐT LỜI trailing (từng lệnh đặt rồi huỷ) → đóng vị thế
}
# ══════════════════════════════════════════════════════════════════════════════

import hashlib  # noqa: E402
import hmac  # noqa: E402
import math  # noqa: E402
import time  # noqa: E402
import traceback  # noqa: E402
import urllib.parse  # noqa: E402
from datetime import datetime  # noqa: E402
from pathlib import Path  # noqa: E402

import ccxt  # noqa: E402
import requests  # noqa: E402

from binance_order_helper import BinanceOrderHelper, cancel_all_open_orders_with_retry  # noqa: E402

# binance_futures_direct của bot lấy key từ cst — chạy độc lập nên dựng cst tối thiểu
import types  # noqa: E402
if "cst" not in sys.modules:
    _cst = types.ModuleType("cst")
    _cst.key_binance, _cst.secret_binance = API_KEY, API_SECRET
    sys.modules["cst"] = _cst
from binance_futures_direct import cancel_algo_orders  # noqa: E402

FAPI = "https://fapi.binance.com"
GOC = Path(__file__).resolve().parent.parent
(GOC / "logs").mkdir(exist_ok=True)
FILE_LOG = GOC / "logs" / f"thu_dat_lenh_{datetime.now():%Y%m%d_%H%M%S}.txt"


def ghi(msg=""):
    dong = f"{datetime.now():%H:%M:%S} {msg}"
    print(dong, flush=True)
    with open(FILE_LOG, "a", encoding="utf-8") as f:
        f.write(dong + "\n")


# ── Gọi REST có ký — dùng để KIỂM TRA lệnh có trên sàn và HUỶ (không phụ thuộc bản ccxt)
class LoiBinance(Exception):
    pass


_lech_gio = 0


def dong_bo_gio():
    global _lech_gio
    r = requests.get(FAPI + "/fapi/v1/time", timeout=10).json()
    _lech_gio = int(r["serverTime"]) - int(time.time() * 1000)


def goi(method, path, params=None):
    p = dict(params or {})
    p["timestamp"] = int(time.time() * 1000) + _lech_gio
    p["recvWindow"] = 10000
    q = urllib.parse.urlencode(p)
    ky = hmac.new(API_SECRET.encode(), q.encode(), hashlib.sha256).hexdigest()
    r = requests.request(method, f"{FAPI}{path}?{q}&signature={ky}",
                         headers={"X-MBX-APIKEY": API_KEY}, timeout=15)
    try:
        data = r.json()
    except ValueError:
        data = r.text
    if r.status_code != 200:
        raise LoiBinance(f"HTTP {r.status_code} {path}: {data}")
    return data


def ds_algo(data):
    if isinstance(data, dict):
        data = data.get("orders") or data.get("rows") or data.get("data") or []
    return data if isinstance(data, list) else []


# ── Sàn ───────────────────────────────────────────────────────────────────────
def chuan_hoa_ma(ma):
    ma = ma.strip().upper()
    if ":USDT" in ma:
        return ma
    if "/" in ma:
        return ma + ":USDT" if ma.endswith("/USDT") else ma
    if ma.endswith("USDT"):
        return f"{ma[:-4]}/USDT:USDT"
    return f"{ma}/USDT:USDT"


exchange = ccxt.binance({
    "enableRateLimit": True,
    "apiKey": API_KEY,
    "secret": API_SECRET,
    "options": {"defaultType": "future", "fetchCurrencies": False,
                # Chỉ nạp mã Futures USDⓈ-M. Mặc định ccxt nạp cả Spot + gọi API Margin
                # (/sapi/v1/margin/allPairs) → key CHỈ bật Futures bị -2015.
                "fetchMarkets": {"types": ["linear"]}, "fetchMargins": False,
                "adjustForTimeDifference": True, "recvWindow": 60000},
})
helper = BinanceOrderHelper(exchange)

symbol = chuan_hoa_ma(MA)
ma_api = ""
ket_qua = []          # (tên, đặt, huỷ, ghi chú)
da_tao = []           # [(la_algo, id)] — lưới an toàn: cuối chương trình huỷ nốt
vi_the_tu_mo = [0.0]  # khối lượng vị thế DO SCRIPT mở (để đóng lại)


def lam_tron_gia(v):
    return float(exchange.price_to_precision(symbol, v))


def lam_tron_kl(v):
    return float(exchange.amount_to_precision(symbol, v))


def vi_the_hien_tai():
    for p in goi("GET", "/fapi/v2/positionRisk", {"symbol": ma_api}):
        if p.get("symbol") == ma_api:
            return float(p.get("positionAmt") or 0)
    return 0.0


def tim_tren_san(la_algo, id_):
    if la_algo:
        return any(str(a.get("algoId")) == str(id_) or str(a.get("clientAlgoId")) == str(id_)
                   for a in ds_algo(goi("GET", "/fapi/v1/openAlgoOrders", {"symbol": ma_api})))
    return any(str(o.get("orderId")) == str(id_)
               for o in goi("GET", "/fapi/v1/openOrders", {"symbol": ma_api}))


def huy(la_algo, id_):
    """Huỷ bằng ĐÚNG hàm của bot. Mã thử đã kiểm là không có lệnh nào khác lúc bắt đầu."""
    if la_algo:
        da_huy, loi = cancel_algo_orders(symbol)
        return f"cancel_algo_orders({ma_api}) → đã huỷ {da_huy}, lỗi {loi}"
    sach, con = cancel_all_open_orders_with_retry(exchange, symbol, max_retries=2, delay=1)
    return f"cancel_all_open_orders_with_retry({ma_api}) → sạch={sach}, còn={con}"


def nhan_dien(od):
    """(la_algo, id) từ phản hồi đặt lệnh — lệnh điều kiện có thể nằm ở Algo API."""
    info = od.get("info") if isinstance(od.get("info"), dict) else {}
    if info.get("algoId") or info.get("clientAlgoId"):
        return True, info.get("algoId") or info.get("clientAlgoId")
    return False, info.get("orderId") or od.get("id")


def thu_lenh_cho(ten, mo_ta, dat):
    """Đặt 1 lệnh → kiểm có trên sàn → huỷ → kiểm đã hết."""
    ghi("")
    ghi(f"▶ {ten}: {mo_ta}")
    if not CHAY_THAT:
        ket_qua.append((ten, "(chưa gửi)", "", mo_ta))
        return
    t0 = time.time()
    try:
        od = dat()
    except Exception as e:
        ghi(f"   ❌ ĐẶT LỖI: {e}")
        ket_qua.append((ten, "❌ LỖI", "", str(e)[:160]))
        return
    la_algo, id_ = nhan_dien(od)
    da_tao.append((la_algo, id_))
    ghi(f"   ✅ Đã gửi ({time.time() - t0:.2f}s) — {'ALGO' if la_algo else 'THƯỜNG'} id={id_}")
    ghi(f"      phản hồi: {od.get('info')}")
    time.sleep(CHO_GIAY)
    try:
        co = tim_tren_san(la_algo, id_)
        ghi(f"   {'✅ Thấy lệnh trên sàn' if co else '⚠️ KHÔNG thấy lệnh trong danh sách lệnh mở (đã khớp? bị huỷ?)'}")
        r = huy(la_algo, id_)
        ghi(f"   phản hồi huỷ: {r}")
        time.sleep(1)
        con = tim_tren_san(la_algo, id_)
        if con:
            ghi("   ❌ HUỶ XONG MÀ LỆNH VẪN CÒN — vào app Binance kiểm tra!")
            ket_qua.append((ten, "✅ OK", "❌ CÒN LỆNH", ""))
        else:
            da_tao.remove((la_algo, id_))
            ghi("   ✅ Đã huỷ sạch")
            ket_qua.append((ten, "✅ OK", "✅ OK", "" if co else "không thấy trên sàn trước khi huỷ"))
    except Exception as e:
        ghi(f"   ❌ LỖI kiểm tra/huỷ: {e}")
        ket_qua.append((ten, "✅ OK", "❌ LỖI", str(e)[:160]))


def mo_vi_the(ten, kl):
    """Market khớp ngay → trả khối lượng thực tế đã mở (có dấu)."""
    truoc = vi_the_hien_tai()
    od = helper.create_market_order(symbol, CHIEU, kl, False)
    ghi(f"   phản hồi: {od.get('info')}")
    time.sleep(CHO_GIAY)
    mo = vi_the_hien_tai() - truoc
    vi_the_tu_mo[0] += mo
    ghi(f"   ✅ {ten}: vị thế thay đổi {mo:+g} (hiện tại {truoc + mo:+g})")
    return mo


def dong_vi_the_tu_mo():
    kl = vi_the_tu_mo[0]
    if not kl:
        return True
    phia = "sell" if kl > 0 else "buy"
    try:
        od = helper.create_market_order(symbol, phia, abs(kl), True)
        ghi(f"   phản hồi đóng: {od.get('info')}")
        time.sleep(CHO_GIAY)
        vi_the_tu_mo[0] = 0.0
        ghi(f"   ✅ Đã đóng {abs(kl):g} bằng market reduceOnly — vị thế còn {vi_the_hien_tai():+g}")
        return True
    except Exception as e:
        ghi(f"   ❌ KHÔNG ĐÓNG ĐƯỢC VỊ THẾ {kl:+g}: {e} — VÀO APP BINANCE ĐÓNG TAY!")
        return False


def chay():
    global ma_api
    ghi("=" * 70)
    ghi(f"THỬ ĐẶT LỆNH {'THẬT' if CHAY_THAT else '(CHẠY THỬ — KHÔNG GỬI LỆNH)'} — log: {FILE_LOG}")
    ghi("=" * 70)
    if CHIEU not in ("buy", "sell"):
        raise SystemExit("❌ CHIEU phải là 'buy' hoặc 'sell'")
    if CHAY_THAT and not (API_KEY and API_SECRET):
        raise SystemExit("❌ Chưa điền API_KEY / API_SECRET")

    exchange.load_markets()
    if symbol not in exchange.markets:
        raise SystemExit(f"❌ Không có mã {symbol} trên Binance Futures")
    thi_truong = exchange.markets[symbol]
    ma_api = thi_truong["id"]
    gia = float(exchange.fetch_ticker(symbol)["last"])
    toi_thieu = float(((thi_truong.get("limits") or {}).get("cost") or {}).get("min") or 5)
    for f in (thi_truong.get("info") or {}).get("filters", []):
        if f.get("filterType") == "MIN_NOTIONAL":
            toi_thieu = float(f.get("notional") or toi_thieu)

    d = 1 if CHIEU == "buy" else -1
    x = CACH_GIA_PCT / 100.0
    gia_duoi = gia * (1 - d * x)       # phía "thấp hơn" với LONG
    gia_tren = gia * (1 + d * x)       # phía "cao hơn" với LONG
    # Khối lượng tính theo giá THẤP nhất sẽ dùng → lệnh nào cũng đủ giá trị tối thiểu
    kl = lam_tron_kl(VON_USDT / min(gia_duoi, gia_tren))
    gia_tri_nho_nhat = kl * min(gia_duoi, gia_tren)

    ghi(f"Mã {symbol} ({ma_api}) · giá hiện tại {gia} · phía {'LONG (mua)' if d > 0 else 'SHORT (bán)'}")
    ghi(f"Khối lượng mỗi lệnh {kl} · giá trị nhỏ nhất ~{gia_tri_nho_nhat:.2f} USDT · sàn yêu cầu ≥ {toi_thieu:g}")
    if gia_tri_nho_nhat < toi_thieu:
        raise SystemExit(f"❌ Giá trị lệnh {gia_tri_nho_nhat:.2f} < tối thiểu {toi_thieu:g} USDT → tăng VON_USDT")

    if CHAY_THAT:
        dong_bo_gio()
        hai_chieu = goi("GET", "/fapi/v1/positionSide/dual").get("dualSidePosition")
        ghi(f"Chế độ vị thế: {'HAI CHIỀU (Hedge)' if hai_chieu else 'MỘT CHIỀU (One-way)'}")
        if hai_chieu:
            raise SystemExit("❌ Tài khoản đang ở chế độ HAI CHIỀU (Hedge) — bot dùng MỘT CHIỀU. "
                             "Đổi trong app Binance: Futures → ⚙ → Chế độ vị thế → Một chiều")
        thuong_co = goi("GET", "/fapi/v1/openOrders", {"symbol": ma_api})
        algo_co = ds_algo(goi("GET", "/fapi/v1/openAlgoOrders", {"symbol": ma_api}))
        if thuong_co or algo_co:
            raise SystemExit(f"❌ {ma_api} đang có {len(thuong_co)} lệnh thường + {len(algo_co)} lệnh điều kiện. "
                             "Bước huỷ dùng hàm của bot (xoá MỌI lệnh của mã) → chọn mã khác, "
                             "hoặc huỷ các lệnh đó trên app trước")
        co_san = vi_the_hien_tai()
        ghi(f"Vị thế đang có của {ma_api}: {co_san:+g}")
        if co_san and (THU["market"] or THU["lenh_thoat"]):
            ghi("⚠️ Mã này ĐANG CÓ vị thế thật → BỎ QUA 'market' và 'lenh_thoat' để không đụng vị thế của bạn")
            THU["market"] = THU["lenh_thoat"] = False
        try:
            exchange.setLeverage(DON_BAY, symbol)
            ghi(f"Đòn bẩy {DON_BAY}x")
        except Exception as e:
            ghi(f"⚠️ Không đặt được đòn bẩy: {e}")

    phia_vao, phia_ra = CHIEU, ("sell" if CHIEU == "buy" else "buy")

    # ── Lệnh VÀO chờ ──────────────────────────────────────────────────────────
    if THU["limit"]:
        p = lam_tron_gia(gia_duoi)
        thu_lenh_cho("1 LIMIT", f"{phia_vao} {kl} @ {p}",
                     lambda: helper.create_limit_order(symbol, phia_vao, kl, p, False))
    if THU["stop_market"]:
        p = lam_tron_gia(gia_tren)
        thu_lenh_cho("3 STOP MARKET", f"{phia_vao} {kl} kích hoạt {p}",
                     lambda: helper.create_stop_market_order(symbol, phia_vao, kl, p, False))
    if THU["stop_limit"]:
        p = lam_tron_gia(gia_tren)
        lim = lam_tron_gia(gia_tren * (1 + d * 0.002))
        thu_lenh_cho("4 STOP LIMIT", f"{phia_vao} {kl} kích hoạt {p} → limit {lim}",
                     lambda: helper.create_stop_limit_order(symbol, phia_vao, kl, p, lim, False))
    if THU["trailing"]:
        p = lam_tron_gia(gia_duoi)
        thu_lenh_cho("5 TRAILING", f"{phia_vao} {kl} kích hoạt {p} callback {CALLBACK_PCT}%",
                     lambda: helper.create_trailing_stop_order(symbol, phia_vao, kl, p, CALLBACK_PCT, False))

    # ── Market: khớp thật rồi đóng ────────────────────────────────────────────
    if THU["market"]:
        ghi("")
        ghi(f"▶ 2 MARKET: {phia_vao} {kl} (KHỚP NGAY) → đóng lại")
        if CHAY_THAT:
            try:
                mo = mo_vi_the("MARKET", kl)
                dong = dong_vi_the_tu_mo()
                ket_qua.append(("2 MARKET", "✅ OK" if mo else "⚠️ không thấy khớp",
                                "✅ ĐÃ ĐÓNG" if dong else "❌ CHƯA ĐÓNG", f"khớp {mo:+g}"))
            except Exception as e:
                ghi(f"   ❌ LỖI: {e}")
                ket_qua.append(("2 MARKET", "❌ LỖI", "", str(e)[:160]))
        else:
            ket_qua.append(("2 MARKET", "(chưa gửi)", "", ""))

    # ── Lệnh THOÁT: cần có vị thế ─────────────────────────────────────────────
    if THU["lenh_thoat"]:
        ghi("")
        ghi(f"▶ LỆNH THOÁT: mở vị thế {phia_vao} {kl} bằng market")
        mo = 0.0
        if CHAY_THAT:
            try:
                mo = mo_vi_the("MỞ VỊ THẾ", kl)
            except Exception as e:
                ghi(f"   ❌ Không mở được vị thế: {e}")
                ket_qua.append(("LỆNH THOÁT", "❌ LỖI mở vị thế", "", str(e)[:160]))
        if mo or not CHAY_THAT:
            kl_ra = abs(mo) or kl
            sl = lam_tron_gia(gia_duoi)
            thu_lenh_cho("SL closePosition", f"{phia_ra} TOÀN BỘ vị thế, kích hoạt {sl}",
                         lambda: helper.create_stop_market_order(symbol, phia_ra, kl_ra, sl, True,
                                                                 close_position=True))
            tp = lam_tron_gia(gia_tren)
            thu_lenh_cho("TP LIMIT reduceOnly", f"{phia_ra} {kl_ra} @ {tp}",
                         lambda: helper.create_limit_order(symbol, phia_ra, kl_ra, tp, True))
            thu_lenh_cho("TP TRAILING reduceOnly", f"{phia_ra} {kl_ra} kích hoạt {tp} callback {CALLBACK_PCT}%",
                         lambda: helper.create_trailing_stop_order(symbol, phia_ra, kl_ra, tp, CALLBACK_PCT, True))
            if CHAY_THAT:
                ghi("")
                ghi("▶ Đóng vị thế đã mở để thử")
                dong_vi_the_tu_mo()


def don_dep():
    """Lưới an toàn: huỷ nốt lệnh script tạo mà chưa huỷ được, đóng vị thế script mở."""
    if not CHAY_THAT:
        return
    if da_tao or vi_the_tu_mo[0]:
        ghi("")
        ghi("▶ DỌN DẸP (có bước lỗi / bị ngắt giữa chừng)")
    for la_algo, id_ in list(da_tao):
        try:
            if tim_tren_san(la_algo, id_):
                huy(la_algo, id_)
                ghi(f"   ✅ Đã huỷ nốt {'algo' if la_algo else 'lệnh'} {id_}")
        except Exception as e:
            ghi(f"   ❌ Không huỷ được {id_}: {e} — VÀO APP BINANCE HUỶ TAY!")
    dong_vi_the_tu_mo()


def tong_ket():
    ghi("")
    ghi("=" * 70)
    ghi(f"{'LOẠI LỆNH':24} {'ĐẶT':12} {'HUỶ / ĐÓNG':14} GHI CHÚ")
    ghi("-" * 70)
    for ten, dat, huy_, chu in ket_qua:
        ghi(f"{ten:24} {dat:12} {huy_:14} {chu}")
    ghi("=" * 70)
    ghi(f"Log đầy đủ: {FILE_LOG}")


if __name__ == "__main__":
    try:
        chay()
    except KeyboardInterrupt:
        ghi("⏹ Bị ngắt (Ctrl+C)")
    except SystemExit as e:
        ghi(str(e))
    except Exception as e:
        ghi(f"❌ LỖI: {e}")
        ghi(traceback.format_exc())
    finally:
        don_dep()
        tong_ket()
