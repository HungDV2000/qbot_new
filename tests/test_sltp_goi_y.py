# -*- coding: utf-8 -*-
"""
Tab "Chờ và khớp": hd_update_cho_va_khop CHỈ GHI A2 + A4:I — không bao giờ đụng J–P/Q.

Khách 07–08/10/2026: SL/TP khách gõ ở N/O bị đè bằng số gợi ý; công thức IMPORTRANGE
tràn vào J–P bị ghi thành số cứng. Gốc: bot ghi lại cả khối J4:P mỗi khi thứ tự dòng
đổi / mã tạm vắng (Binance lỗi trả rỗng). Nay: giữ chỗ dòng theo mã, chỉ ghi A–I,
Binance lỗi thì bỏ cả vòng ghi. SL/TP mặc định do hd_order_multi tính trong bộ nhớ.
"""
import os, sys, types, unittest
from unittest import mock

QBOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, QBOT)
os.chdir(QBOT)


def _mod(ten, **kw):
    m = types.ModuleType(ten)
    for k, v in kw.items():
        setattr(m, k, v)
    sys.modules[ten] = m
    return m


class _Sheet:
    """Google Sheets giả — nhớ lại mọi lệnh ghi để soi."""
    tab_cho_va_khop = "Chờ và khớp"
    tab_dat_lenh = "ĐẶT LỆNH"

    def __init__(self):
        self.ghi = []
        self.doc_tra_ve = []

    spreadsheetId = "SHEET_TEST"

    def get_cho_va_khop(self, rng, value_render_option=None):
        return self.doc_tra_ve

    def batch_update_values(self, tab, data):
        self.ghi.append({"tab": tab, "batch": data})

    def update_multi(self, tab, idx, arr, col):
        self.ghi.append({"tab": tab, "idx": idx, "col": col, "rows": arr})


def _nap_module(fill=True, allow="N"):
    """
    Nạp hd_update_cho_va_khop để lấy HÀM THẬT, nhưng KHÔNG chạy bot.

    File này không có guard `if __name__ == "__main__"` — cuối file là
    `while True:` nên import bình thường sẽ khởi động bot và treo mãi.
    Cách làm: cắt mã nguồn ngay TRƯỚC vòng lặp rồi exec phần còn lại.
    Toàn bộ hàm vẫn là hàm thật trong file, không phải bản chép.
    """
    class _Ex:
        def __init__(self, *a, **k): self.markets = {}
        def setSandboxMode(self, *a, **k): pass
        def load_markets(self, *a, **k): return {}
        def fetch_positions(self, *a, **k): return []
        def fetch_open_orders(self, *a, **k): return []

    _mod("cst", default_sl_rate_layer_1=2, default_sl_rate_layer_2=5, default_sl_rate_layer_3=10,
         default_tp_rate_layer_1=3, default_tp_rate_layer_2=6, default_tp_rate_layer_3=10,
         fill_default_cho_va_khop=fill, default_allow_order=allow,
         key_binance="k", secret_binance="s", key_name="TEST", chat_id="0",
         delay_cho_va_khop=600, tab_dat_lenh="ĐẶT LỆNH",
         account_dir=lambda b: __import__("pathlib").Path("/tmp"),
         account_name="test", account_suffix=lambda: "", config=None,
         bao_nhip=lambda *a, **k: None)
    sheet = _Sheet()
    sys.modules["gg_sheet_factory"] = sheet
    _mod("ccxt", binance=_Ex, __version__="4", BaseError=Exception, NetworkError=Exception)
    _mod("requests")
    _mod("binance_futures_direct", futures_signed_request=lambda *a, **k: {},
         fetch_algo_orders_for_symbol=lambda *a, **k: [],
         resync_exchange_time=lambda *a, **k: None,
         normalize_algo_orders_response=lambda *a, **k: [])
    _mod("telegram_factory", send_tele=lambda *a, **k: None)
    g = types.ModuleType("googleapiclient"); e = types.ModuleType("googleapiclient.errors")
    class HttpError(Exception): pass
    e.HttpError = HttpError; g.errors = e
    sys.modules["googleapiclient"] = g; sys.modules["googleapiclient.errors"] = e

    import io as _io
    src = _io.open("hd_update_cho_va_khop.py", encoding="utf-8").read()
    cat = src.index("\nwhile True:")          # cắt ngay trước vòng lặp chính
    M = types.ModuleType("hd_update_cho_va_khop_test")
    M.__file__ = os.path.join(QBOT, "hd_update_cho_va_khop.py")
    exec(compile(src[:cat], "hd_update_cho_va_khop.py", "exec"), M.__dict__)
    return M, sheet


BTC = ["BTC/USDT", "LONG", "N", "Y", 100.0, 10, "N", "N", 0]
ETH = ["ETH/USDT", "SHORT", "N", "Y", 50.0, 10, "N", "N", 0]


class TestKeHoachGhi(unittest.TestCase):
    def setUp(self):
        self.M, self.sheet = _nap_module()

    def test_chi_A2_va_A_den_I(self):
        cu = [BTC + [True, "", "", "", 95, 104, "Y"]]
        kh = dict(self.M.ke_hoach_ghi_cho_va_khop([ETH, BTC], cu, "T"))
        self.assertEqual(set(kh), {"A2", "A4:I5"}, "🔴 bot ghi ngoài A–I")
        self.assertEqual(kh["A4:I5"], [BTC, ETH], "BTC giữ dòng 4, ETH mới vào dòng 5")

    def test_doc_bang_cu_loi_thi_KHONG_ghi(self):
        self.assertIsNone(self.M.ke_hoach_ghi_cho_va_khop([BTC], None, "T"),
                          "🔴 không biết dòng nào của mã nào mà vẫn ghi")

    def test_bang_rong_van_ghi_hop_le(self):
        kh = dict(self.M.ke_hoach_ghi_cho_va_khop([], [], "T"))
        self.assertEqual(kh["A4:I4"], [[""] * 9])

    def test_doc_A_den_P_dang_FORMULA(self):
        goi = []
        self.sheet.get_cho_va_khop = lambda rng, value_render_option=None: goi.append((rng, value_render_option)) or []
        self.M.doc_anh_cu_cho_va_khop()
        self.assertEqual(goi, [("A4:P1000", "FORMULA")])

    def test_doc_loi_tra_None(self):
        def no(*a, **k): raise RuntimeError("mạng lỗi")
        self.sheet.get_cho_va_khop = no
        self.assertIsNone(self.M.doc_anh_cu_cho_va_khop())


class TestBinanceLoiThiKhongGhi(unittest.TestCase):
    """Gốc lỗi khách 08/10: lấy vị thế lỗi → trả [] → ghi bảng THIẾU → J–P mất chỗ dựa."""

    def setUp(self):
        self.M, self.sheet = _nap_module()

    def _co_ghi(self):
        return [g for g in self.sheet.ghi if "batch" in g]

    def test_lay_vi_the_loi(self):
        class Ex:
            def fetch_positions(self, *a, **k): raise RuntimeError("429 Too Many Requests")
            def fetch_open_orders(self, *a, **k): return []
        self.M.exchange = Ex()
        self.M.do_it()
        self.assertEqual(self._co_ghi(), [], "🔴 Binance lỗi mà vẫn ghi sheet")

    def test_lay_lenh_cho_loi(self):
        class Ex:
            def fetch_positions(self, *a, **k): return []
            def fetch_open_orders(self, *a, **k): raise RuntimeError("timeout")
        self.M.exchange = Ex()
        self.M.do_it()
        self.assertEqual(self._co_ghi(), [])

    def test_lay_algo_loi(self):
        self.M.get_all_open_algo_orders_batch = lambda: None
        self.M.get_algo_orders_for_symbol = lambda s: (_ for _ in ()).throw(RuntimeError("x"))
        self.M.exchange.markets = {"BTC/USDT:USDT": {}}
        self.M.do_it()
        self.assertEqual(self._co_ghi(), [])

    def test_du_lieu_du_thi_ghi_chi_A_den_I(self):
        self.M.do_it()
        ghi = self._co_ghi()
        self.assertEqual(len(ghi), 1)
        self.assertEqual([v for v, _ in ghi[0]["batch"]], ["A2", "A4:I4"])

    def test_ma_loi_khi_xu_ly_thi_giu_dong_cu(self):
        self.M._ma_loi_vong.update({"BTC/USDT"})
        self.sheet.doc_tra_ve = [BTC + [""] * 7]
        kh = dict(self.M.ke_hoach_ghi_cho_va_khop([], self.sheet.doc_tra_ve, "T",
                                                  giu_ma=self.M._ma_loi_vong))
        self.assertEqual(kh["A4:I4"], [BTC])


class TestNguon(unittest.TestCase):
    def _src(self):
        import io as _io
        return _io.open("hd_update_cho_va_khop.py", encoding="utf-8").read()

    def test_khong_con_ghi_JP_Q(self):
        src = self._src()
        for cam in ("J{DONG_DAU", "Q{DONG_DAU", "khoi_jp", "goi_y_sltp", "tab_q_prices", "can_chinh"):
            self.assertNotIn(cam, src, f"🔴 còn dấu vết ghi J–P/Q: {cam}")
        for cam in ("clear_multi(", "update_single_value(", "update_multi("):
            self.assertNotIn(cam, src, f"🔴 còn lệnh ghi/xoá rời {cam}")
        self.assertEqual(src.count("gg_sheet_factory.batch_update_values("), 1)

    def test_khong_nuot_loi_tra_rong(self):
        src = self._src()
        self.assertNotIn("all_open_orders = []", src, "🔴 lỗi lấy lệnh lại thành danh sách rỗng")
        self.assertNotIn("get_all_open_algo_orders_batch() or []", src)

    def test_doc_bang_cu_truoc_khi_ghi(self):
        src = self._src()
        self.assertLess(src.index("anh_cu = doc_anh_cu_cho_va_khop()"),
                        src.index("gg_sheet_factory.batch_update_values("))


class TestKhongDungHang1Den3(unittest.TestCase):
    """Hàng 1–3 tab "Chờ và khớp" là tiêu đề + công thức của NGƯỜI DÙNG (VD IMPORTRANGE
    J2). Không bot nào được ghi vào đó — trừ ô A2 (giờ quét của hd_update_cho_va_khop)."""

    def setUp(self):
        self.M, _ = _nap_module()

    @staticmethod
    def _dong_dau(vung):
        import re
        return [int(x) for x in re.findall(r"[A-Z]+(\d+)", vung)]

    def test_ke_hoach_ghi_chi_tu_dong_4_tru_A2(self):
        for cu in ([], [BTC + [""] * 7] * 5):
            for vung, _ in self.M.ke_hoach_ghi_cho_va_khop([BTC], cu, "T"):
                if vung == "A2":
                    continue
                self.assertTrue(all(r >= 4 for r in self._dong_dau(vung)), f"🔴 ghi vào {vung}")

    def test_chi_2_bot_ghi_tab_cho_va_khop_va_dung_cach(self):
        """Soát nguồn MỌI bot: lệnh ghi/xoá nào đụng tab_cho_va_khop phải nằm trong danh
        sách đã kiểm — thêm chỗ ghi mới thì test đỏ, buộc phải xem lại hàng 1–3."""
        import io, re, glob
        cho_phep = {
            ("hd_update_cho_va_khop.py", "batch_update_values"),   # A2 + dòng ≥4 (test trên)
            ("hd_cancel_selective.py", "batch_clear_values"),      # tick J–M, dòng DONG_DAU+i
            ("hd_cancel_selective.py", "update_multi"),            # G–I, -dong_moi (dòng ≥4)
        }
        thay = set()
        for f in glob.glob("*.py"):
            src = io.open(f, encoding="utf-8").read()
            for m in re.finditer(r"gg_sheet_factory\.(\w+)\(\s*gg_sheet_factory\.tab_cho_va_khop", src):
                thay.add((f, m.group(1)))
        self.assertEqual(thay, cho_phep)
        src = io.open("hd_cancel_selective.py", encoding="utf-8").read()
        self.assertIn("DONG_DAU = 4", src)


class TestLogDeChuanDoan(unittest.TestCase):
    """Khách báo "quét không ra": phải biết bot ghi vào SHEET NÀO và phân loại lệnh ra sao."""

    def _src(self):
        import io as _io
        return _io.open("hd_update_cho_va_khop.py", encoding="utf-8").read()

    def test_log_sheet_id_khi_ghi(self):
        src = self._src()
        self.assertGreaterEqual(src.count("gg_sheet_factory.spreadsheetId"), 2,
                                "🔴 không log Sheet ID → không biết bot ghi nhầm file hay không")

    def test_log_chi_tiet_tung_lenh(self):
        self.assertIn("mo_ta_lenh(", self._src(),
                      "🔴 không log chi tiết lệnh → không biết vì sao cột G/H sai")


class TestCotCoSlCoTp(unittest.TestCase):
    """Cột G/H (Có SL / Có TP) phải nhận đúng lệnh hd_order_multi đặt:
    SL = STOP_MARKET closePosition, TP = LIMIT reduceOnly. Bản cũ H luôn = N."""
    SL = {"id": "S", "type": "stop_market", "reduceOnly": False,
          "info": {"origType": "STOP_MARKET", "closePosition": "true"}}
    TP = {"id": "T", "type": "limit", "reduceOnly": True,
          "info": {"origType": "LIMIT", "reduceOnly": True}}
    VAO = {"id": "E", "type": "limit", "reduceOnly": False, "info": {"origType": "LIMIT"}}

    def setUp(self):
        self.M, _ = _nap_module()
        self.M.get_algo_orders_for_symbol = lambda s: []

    def test_nhan_du_SL_va_TP(self):
        self.assertEqual(self.M.check_sl_tp_orders("BTC/USDT:USDT", [self.SL, self.TP, self.VAO]),
                         (True, True, 3), "🔴 TP LIMIT / SL closePosition không được nhận ra")

    def test_chi_co_lenh_vao(self):
        self.assertEqual(self.M.check_sl_tp_orders("BTC/USDT:USDT", [self.VAO]), (False, False, 1))

    def test_algo_trailing_la_TP(self):
        self.M.get_algo_orders_for_symbol = lambda s: [
            {"algoStatus": "NEW", "orderType": "TRAILING_STOP_MARKET", "reduceOnly": True, "callbackRate": "1"}]
        self.assertEqual(self.M.check_sl_tp_orders("X", []), (False, True, 1))

    def test_vi_the_dong_con_SL_closePosition_van_nhan_ra(self):
        sl = dict(self.SL, symbol="BTC/USDT:USDT", side="sell")

        class Ex:
            def fetch_open_orders(self, *a, **k): return [sl]
        self.M.exchange = Ex()
        self.M.get_all_open_algo_orders_batch = lambda: []
        kq = self.M.get_all_reduce_only_orders_by_symbol()
        self.assertIn("BTCUSDT", kq, "🔴 SL closePosition sót lại không bị phát hiện → không có dòng ĐÓNG")
        self.assertTrue(kq["BTCUSDT"]["has_sl"])
        self.assertEqual(kq["BTCUSDT"]["side"], "LONG")


if __name__ == "__main__":
    unittest.main(verbosity=2)
