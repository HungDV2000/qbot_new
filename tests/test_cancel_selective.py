"""
Test bot XOÁ LỆNH THEO TICK (hd_cancel_selective.py) — chạy LOCAL, sàn/sheet giả.

Bảo đảm:
  • Tick J KHÔNG xoá cắt lỗ kiểu closePosition (bản cũ xoá nhầm).
  • Tick K xoá được chốt lời kiểu LIMIT reduceOnly (bản cũ bỏ sót).
  • Tick bị xoá đúng dòng của MÃ dù dòng đã xê dịch.
  • Đã xoá lệnh mà chưa xoá được tick → KHÔNG xoá lệnh lần 2.

    python3 tests/test_cancel_selective.py
"""
import os, sys, types, configparser, tempfile, pathlib, unittest

QBOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(QBOT); sys.path.insert(0, QBOT)


def _mod(n, **a):
    m = types.ModuleType(n); [setattr(m, k, v) for k, v in a.items()]; sys.modules[n] = m; return m


def dong(ma, side="LONG", d="Y", J="", K="", L="", M=""):
    return [ma, side, "N", d, 1.0, 10, "N", "N", 0, J, K, L, M, "", "", ""]


# Lệnh mẫu đúng như hd_order_multi đặt
def entry(oid):      return {"id": oid, "type": "limit", "reduceOnly": False, "info": {"origType": "LIMIT", "reduceOnly": False}}
def sl_close(oid):   return {"id": oid, "type": "stop_market", "reduceOnly": False,
                             "info": {"origType": "STOP_MARKET", "reduceOnly": False, "closePosition": "true"}}
def tp_limit(oid):   return {"id": oid, "type": "limit", "reduceOnly": True, "info": {"origType": "LIMIT", "reduceOnly": True}}
def algo_sl(aid):    return {"algoId": aid, "algoStatus": "NEW", "algoType": "CONDITIONAL",
                             "orderType": "STOP_MARKET", "reduceOnly": False, "closePosition": True}
def algo_trail(aid): return {"algoId": aid, "algoStatus": "NEW", "algoType": "CONDITIONAL",
                             "orderType": "TRAILING_STOP_MARKET", "reduceOnly": True, "callbackRate": "1"}


class San:
    def __init__(s):
        s.thuong, s.algo, s.da_huy = {}, {}, []


class Sheet:
    def __init__(s, bang):
        s.bang, s.bang_sau = bang, None
        s.xoa, s.ghi, s.tele = [], [], []
        s.loi_xoa = False

    def get(s, rng, value_render_option=None):
        if rng == "A4:B1000" and s.bang_sau is not None:
            return [r[:2] for r in s.bang_sau]
        return s.bang

    def clear(s, tab, ranges):
        if s.loi_xoa:
            raise RuntimeError("429 quota")
        s.xoa.extend(ranges)
        b = s.bang_sau if s.bang_sau is not None else s.bang
        for r in ranges:
            b[int(r[1:]) - 4]["JKLM".index(r[0]) + 9] = ""

    def update_multi(s, tab, idx, arr, col):
        s.ghi.append((idx, col, arr))


def _nap(san, sheet):
    for m in ("hd_cancel_selective", "cst", "ccxt", "gg_sheet_factory", "telegram_factory",
              "binance_futures_direct", "config_watcher"):
        sys.modules.pop(m, None)

    class FE:
        def __init__(s, *a, **k): pass
        def setSandboxMode(s, *a, **k): pass
        def fetch_open_orders(s, sym): return [dict(o) for o in san.thuong.get(sym, [])]
        def cancel_order(s, oid, sym):
            san.thuong[sym] = [o for o in san.thuong.get(sym, []) if o["id"] != oid]
            san.da_huy.append(oid)
    _mod("ccxt", binance=FE)

    def fetch_algo(sym, **k):
        return [dict(a) for a in san.algo.get(sym.replace("/", "").replace(":USDT", ""), [])]

    def fsr(method, ep, params=None, **k):
        if method == "DELETE" and ep == "/fapi/v1/algoOrder":
            s_ = params["symbol"]
            san.algo[s_] = [a for a in san.algo.get(s_, []) if a["algoId"] != params["algoId"]]
            san.da_huy.append(params["algoId"])
            return {"code": "200", "msg": "success", "algoId": params["algoId"]}
        return None
    _mod("binance_futures_direct", fetch_algo_orders_for_symbol=fetch_algo,
         futures_signed_request=fsr, resync_exchange_time=lambda *a, **k: None)
    _mod("gg_sheet_factory", tab_cho_va_khop="Chờ và khớp", get_cho_va_khop=sheet.get,
         batch_clear_values=sheet.clear, update_multi=sheet.update_multi)
    _mod("telegram_factory", send_tele=lambda msg, *a, **k: sheet.tele.append(msg))
    _mod("config_watcher", ngu=lambda *a, **k: None)

    cfg = configparser.ConfigParser(); cfg.read_dict({"global": {}})
    tmp = pathlib.Path(tempfile.mkdtemp())
    def ad(b):
        d = tmp / b; d.mkdir(parents=True, exist_ok=True); return d
    _mod("cst", key_name="T", key_binance="x", secret_binance="y", chat_id="0", config=cfg, account_dir=ad)

    src = open(os.path.join(QBOT, "hd_cancel_selective.py"), encoding="utf-8").read()
    src = src.split("# Main loop")[0]
    mod = types.ModuleType("hd_cancel_selective")
    mod.__dict__["__file__"] = os.path.join(QBOT, "hd_cancel_selective.py")
    exec(compile(src, "hd_cancel_selective.py", "exec"), mod.__dict__)
    return mod


BTC = "BTC/USDT:USDT"


class TestPhanLoai(unittest.TestCase):
    def setUp(self):
        self.M = _nap(San(), Sheet([]))

    def test_sl_closePosition_la_SL_khong_phai_ENTRY(self):
        self.assertEqual(self.M.phan_loai(sl_close("1")), "SL")
        self.assertEqual(self.M.phan_loai(algo_sl(9), True), "SL")

    def test_tp_limit_reduceOnly_la_TP(self):
        self.assertEqual(self.M.phan_loai(tp_limit("2")), "TP")
        self.assertEqual(self.M.phan_loai(algo_trail(8), True), "TP")

    def test_lenh_vao(self):
        self.assertEqual(self.M.phan_loai(entry("3")), "ENTRY")

    def test_gia_tri_tick(self):
        for v in ("TRUE", True, "y", "x", "1", "✓"):
            self.assertTrue(self.M.has_delete_tick(v), v)
        for v in ("", None, "N", "FALSE", False, "0", "no"):
            self.assertFalse(self.M.has_delete_tick(v), v)


class TestXoaTheoTick(unittest.TestCase):
    def _chay(self, bang, thuong=(), algo=()):
        san, sheet = San(), Sheet(bang)
        san.thuong[BTC] = list(thuong)
        san.algo["BTCUSDT"] = list(algo)
        M = _nap(san, sheet)
        M.xu_ly_mot_vong()
        return M, san, sheet

    def test_J_chi_xoa_lenh_vao_GIU_cat_lo(self):
        _, san, sheet = self._chay([dong("BTC/USDT", J="TRUE")],
                                   [entry("E1"), sl_close("S1"), tp_limit("T1")], [algo_sl(91)])
        self.assertEqual(san.da_huy, ["E1"], "🔴 tick J xoá nhầm SL/TP!")
        self.assertEqual(sheet.xoa, ["J4"])

    def test_K_xoa_ca_SL_lan_TP_limit(self):
        _, san, _ = self._chay([dong("BTC/USDT", K="TRUE")],
                               [entry("E1"), sl_close("S1"), tp_limit("T1")], [algo_sl(91)])
        self.assertEqual(sorted(map(str, san.da_huy)), ["91", "S1", "T1"], "K phải xoá SL + TP, giữ lệnh vào")

    def test_L_chi_con_TP_thi_xoa_TP(self):
        _, san, _ = self._chay([dong("BTC/USDT", L="TRUE")], [entry("E1"), tp_limit("T1")])
        self.assertEqual(san.da_huy, ["T1"])

    def test_L_con_du_SL_TP_thi_khong_xoa(self):
        _, san, _ = self._chay([dong("BTC/USDT", L="TRUE")], [sl_close("S1"), tp_limit("T1")])
        self.assertEqual(san.da_huy, [])

    def test_K_va_L_cung_tick_thi_L_bo_qua(self):
        _, san, _ = self._chay([dong("BTC/USDT", K="TRUE", L="TRUE")], [sl_close("S1"), tp_limit("T1")])
        self.assertEqual(sorted(san.da_huy), ["S1", "T1"])

    def test_M_xoa_tat_ca(self):
        _, san, sheet = self._chay([dong("BTC/USDT", d="ĐÓNG", M="TRUE")],
                                   [entry("E1"), sl_close("S1"), tp_limit("T1")], [algo_sl(91), algo_trail(92)])
        self.assertEqual(len(san.da_huy), 5)
        self.assertEqual(sheet.xoa, ["M4"])

    def test_khong_tick_thi_khong_lam_gi(self):
        _, san, sheet = self._chay([dong("BTC/USDT", J="FALSE", K="N")], [entry("E1")])
        self.assertEqual(san.da_huy, []); self.assertEqual(sheet.xoa, []); self.assertEqual(sheet.tele, [])

    def test_cap_nhat_GHI_dong_do(self):
        _, _, sheet = self._chay([dong("BTC/USDT", K="TRUE")], [sl_close("S1"), tp_limit("T1")])
        self.assertEqual(sheet.ghi, [(-4, "G", [["N", "N", 0]])])


class TestDongXeDich(unittest.TestCase):
    def test_xoa_tick_dung_dong_moi_cua_ma(self):
        san, sheet = San(), Sheet([dong("BTC/USDT", J="TRUE"), dong("ETH/USDT")])
        san.thuong[BTC] = [entry("E1")]
        # Trong lúc xoá lệnh, hd_update_cho_va_khop đã đẩy BTC xuống dòng 5
        sheet.bang_sau = [dong("ETH/USDT"), dong("BTC/USDT", J="TRUE")]
        M = _nap(san, sheet)
        M.xu_ly_mot_vong()
        self.assertEqual(sheet.xoa, ["J5"], "🔴 xoá tick ở dòng CŨ — dòng 4 giờ là ETH")
        self.assertEqual(sheet.ghi[0][0], -5, "G/H/I phải ghi vào dòng mới của BTC")

    def test_ma_roi_bang_thi_khong_xoa_bua(self):
        san, sheet = San(), Sheet([dong("BTC/USDT", J="TRUE")])
        san.thuong[BTC] = [entry("E1")]
        sheet.bang_sau = [dong("ETH/USDT")]
        M = _nap(san, sheet)
        M.xu_ly_mot_vong()
        self.assertEqual(sheet.xoa, [], "không tìm thấy mã thì không được xoá tick của mã khác")


class TestKhongXoaLan2(unittest.TestCase):
    def test_chua_xoa_duoc_tick_thi_khong_xoa_lenh_lai(self):
        san, sheet = San(), Sheet([dong("BTC/USDT", J="TRUE")])
        san.thuong[BTC] = [entry("E1")]
        sheet.loi_xoa = True
        M = _nap(san, sheet)
        M.xu_ly_mot_vong()
        self.assertEqual(san.da_huy, ["E1"])
        san.thuong[BTC] = [entry("E2")]          # bot multi đặt lệnh vào MỚI
        M.xu_ly_mot_vong()                       # tick vẫn còn vì xoá lỗi
        self.assertEqual(san.da_huy, ["E1"], "🔴 xoá lệnh lần 2 chỉ vì tick chưa xoá được")
        sheet.loi_xoa = False
        M.xu_ly_mot_vong()
        self.assertEqual(sheet.xoa, ["J4"], "lượt sau phải thử xoá tick lại")
        self.assertEqual(san.da_huy, ["E1"])

    def test_tick_ma_hien_lai_ngay_thi_khong_xoa_lenh_lai(self):
        """hd_update_cho_va_khop ghi lại J–P từ ảnh chụp cũ → tick hiện lại."""
        san, sheet = San(), Sheet([dong("BTC/USDT", K="TRUE")])
        san.thuong[BTC] = [sl_close("S1")]
        M = _nap(san, sheet)
        M.xu_ly_mot_vong()
        sheet.bang[0][10] = "TRUE"
        san.thuong[BTC] = [sl_close("S2")]       # bot multi đặt lại cắt lỗ
        M.xu_ly_mot_vong()
        self.assertEqual(san.da_huy, ["S1"], "🔴 tick ma làm xoá cắt lỗ lần 2")
        self.assertEqual(sheet.xoa, ["K4", "K4"])

    def test_tick_lai_sau_han_chan_thi_xu_ly_binh_thuong(self):
        san, sheet = San(), Sheet([dong("BTC/USDT", J="TRUE")])
        san.thuong[BTC] = [entry("E1")]
        M = _nap(san, sheet)
        M.xu_ly_mot_vong()
        for e in M._vua_xu_ly.values():
            e["t"] -= M.CHAN_LAP_GIAY + 1
        sheet.bang[0][9] = "TRUE"
        san.thuong[BTC] = [entry("E2")]
        M.xu_ly_mot_vong()
        self.assertEqual(san.da_huy, ["E1", "E2"])


class TestNoiDay(unittest.TestCase):
    def test_co_trong_start_all_bots(self):
        self.assertIn("hd_cancel_selective.py", open("start_all_bots.sh", encoding="utf-8").read())


if __name__ == "__main__":
    unittest.main(verbosity=2)
