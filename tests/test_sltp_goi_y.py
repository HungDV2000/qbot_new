# -*- coding: utf-8 -*-
"""
Bot phải TỰ ĐIỀN gợi ý SL/TP vào cột N/O/P của tab "Chờ và khớp".

Trước bản vá: compute_default_sl_tp_prices() có sẵn nhưng KHÔNG AI GỌI
→ N/O/P luôn trống → hd_order_multi bỏ qua mọi dòng (nó đòi D='Y' VÀ P='Y'
VÀ N/O có giá) → vị thế mở mà KHÔNG CÓ CẮT LỖ.
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

    def get_cho_va_khop(self, rng, value_render_option=None):
        return self.doc_tra_ve

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
         account_name="test", account_suffix=lambda: "", config=None)
    sheet = _Sheet()
    sys.modules["gg_sheet_factory"] = sheet
    _mod("ccxt", binance=_Ex, __version__="4", BaseError=Exception, NetworkError=Exception)
    _mod("requests")
    _mod("binance_futures_direct", futures_signed_request=lambda *a, **k: {},
         fetch_algo_orders_for_symbol=lambda *a, **k: [],
         resync_exchange_time=lambda *a, **k: None,
         normalize_algo_orders_response=lambda *a, **k: [])
    _mod("binance_symbol_row", fetch_all_tickers_24h=lambda *a, **k: {},
         get_sheet_col_c_price=lambda *a, **k: 0)
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


class TestGoiYTungDong(unittest.TestCase):
    def setUp(self):
        self.M, self.sheet = _nap_module()

    def _dong(self, side, status, entry):
        # A=mã, B=side, C=chờ, D=trạng thái, E=giá vào
        return ["BTC/USDT", side, "", status, entry, 10, "N", "N", 0]

    def test_LONG_dang_mo_thi_co_goi_y(self):
        sl, tp, p = self.M.goi_y_sltp_cho_dong(self._dong("LONG", "Y", 100.0))
        self.assertAlmostEqual(float(sl), 98.0, places=4, msg="SL LONG = entry × (1-2%)")
        self.assertAlmostEqual(float(tp), 103.0, places=4, msg="TP LONG = entry × (1+3%)")
        self.assertEqual(p, "N", "cột P lấy từ default_allow_order")

    def test_SHORT_dao_chieu_dung(self):
        sl, tp, _ = self.M.goi_y_sltp_cho_dong(self._dong("SHORT", "Y", 100.0))
        self.assertAlmostEqual(float(sl), 102.0, places=4, msg="SL SHORT nằm TRÊN giá vào")
        self.assertAlmostEqual(float(tp), 97.0, places=4, msg="TP SHORT nằm DƯỚI giá vào")

    def test_dong_da_dong_thi_KHONG_boi_so(self):
        self.assertEqual(self.M.goi_y_sltp_cho_dong(self._dong("LONG", "ĐÓNG", 100.0)),
                         ["", "", ""])

    def test_chua_khop_thi_KHONG_boi_so(self):
        self.assertEqual(self.M.goi_y_sltp_cho_dong(self._dong("LONG", "N", 100.0)),
                         ["", "", ""])

    def test_gia_vao_khong_hop_le(self):
        self.assertEqual(self.M.goi_y_sltp_cho_dong(self._dong("LONG", "Y", 0)), ["", "", ""])
        self.assertEqual(self.M.goi_y_sltp_cho_dong(["BTC"]), ["", "", ""])


class TestGhiVaoSheet(unittest.TestCase):
    def setUp(self):
        self.M, self.sheet = _nap_module()

    BTC = ["BTC/USDT", "LONG", "N", "Y", 100.0, 10, "N", "N", 0]
    ETH = ["ETH/USDT", "SHORT", "N", "Y", 50.0, 10, "N", "N", 0]

    def test_ghi_tu_cot_J_dong_4(self):
        self.M.ghi_goi_y_sltp([["98", "103", "N"]], [self.BTC], [])
        self.assertEqual(len(self.sheet.ghi), 1)
        g = self.sheet.ghi[0]
        self.assertEqual(g["col"], "J", "ghi khối J–P (J–M tick, N=SL, O=TP, P=cho phép)")
        self.assertEqual(g["idx"], 2, "idx=2 → ghi từ dòng 4")
        self.assertEqual(g["rows"], [["", "", "", "", "98", "103", "N"]])

    def test_KHONG_de_len_so_nguoi_dung_da_sua(self):
        """Người dùng sửa SL thành 95 → lần chạy sau phải GIỮ NGUYÊN 95."""
        cu = [self.BTC + ["", "", "", "", "95", "", "Y"]]   # N=95 (user sửa), O trống, P=Y
        self.M.ghi_goi_y_sltp([["98", "103", "N"]], [self.BTC], cu)
        rows = self.sheet.ghi[0]["rows"]
        self.assertEqual(rows[0][4], "95", "🔴 ĐÈ MẤT giá SL người dùng nhập!")
        self.assertEqual(rows[0][5], "103", "ô trống thì mới điền gợi ý")
        self.assertEqual(rows[0][6], "Y", "🔴 ĐÈ MẤT cờ cho phép người dùng bật!")

    def test_dong_xe_dich_thi_tick_va_SL_di_theo_ma(self):
        """BTC từ dòng 4 xuống dòng 5 → tick J và SL 95 phải đi theo BTC."""
        cu = [self.BTC + [True, "", "", "", "95", "104", "Y"], self.ETH + [""] * 7]
        self.M.ghi_goi_y_sltp([["51", "48", "N"], ["98", "103", "N"]], [self.ETH, self.BTC], cu)
        rows = self.sheet.ghi[0]["rows"]
        self.assertEqual(rows[1], [True, "", "", "", "95", "104", "Y"], "🔴 J–P không đi theo BTC")
        self.assertEqual(rows[0][:4], ["", "", "", ""], "🔴 tick của BTC rơi sang ETH")
        self.assertEqual(rows[0][4:], ["51", "48", "N"], "ETH nhận gợi ý của chính nó")

    def test_tat_bang_config(self):
        M, sheet = _nap_module(fill=False)
        M.ghi_goi_y_sltp([["98", "103", "N"]], [self.BTC], [])
        self.assertEqual(sheet.ghi, [], "fill_default_cho_va_khop=false, không dời gì → không ghi")

    def test_doc_loi_thi_bo_qua_thay_vi_de_bua(self):
        """Đọc A–P lỗi → KHÔNG ghi J–P, để khỏi xoá mất số người dùng."""
        def no(*a, **k): raise RuntimeError("mạng lỗi")
        self.sheet.get_cho_va_khop = no
        anh = self.M.doc_anh_cu_cho_va_khop()
        self.assertIsNone(anh)
        self.M.ghi_goi_y_sltp([["98", "103", "N"]], [self.BTC], anh)
        self.assertEqual(self.sheet.ghi, [], "🔴 vẫn ghi dù không đọc được — nguy cơ đè mất dữ liệu")

    def test_doc_dang_FORMULA_de_giu_cong_thuc_va_do_chinh_xac(self):
        goi = []
        self.sheet.get_cho_va_khop = lambda rng, value_render_option=None: goi.append((rng, value_render_option)) or []
        self.M.doc_anh_cu_cho_va_khop()
        self.assertEqual(goi, [("A4:P1000", "FORMULA")])

    def test_default_allow_order_Y_thi_tu_dong_hoan_toan(self):
        M, sheet = _nap_module(allow="Y")
        p = M.goi_y_sltp_cho_dong(["BTC/USDT", "LONG", "", "Y", 100.0])[2]
        self.assertEqual(p, "Y", "đặt default_allow_order=Y thì SL/TP tự động hẳn")


class TestCodeDaNoi(unittest.TestCase):
    def test_ham_khong_con_la_code_chet(self):
        import io
        src = io.open("hd_update_cho_va_khop.py", encoding="utf-8").read()
        self.assertGreaterEqual(src.count("compute_default_sl_tp_prices"), 2,
                                "🔴 hàm vẫn không ai gọi")
        self.assertIn("ghi_goi_y_sltp(tab_sltp, tab_100_ma_2d_arr, anh_cu)", src,
                      "chưa nối vào luồng ghi sheet")
        # Phải chụp A–P TRƯỚC khi xoá A–I, nếu không sẽ không biết J–P thuộc mã nào
        self.assertLess(src.index("anh_cu = doc_anh_cu_cho_va_khop()"),
                        src.index('clear_multi(gg_sheet_factory.tab_cho_va_khop, 2, "a"'))

    def test_cac_tham_so_layer_da_duoc_dung(self):
        import io
        src = io.open("hd_update_cho_va_khop.py", encoding="utf-8").read()
        for k in ("cst.fill_default_cho_va_khop", "cst.default_allow_order"):
            with self.subTest(khoa=k):
                self.assertIn(k, src, f"{k} vẫn là tham số chết")


if __name__ == "__main__":
    unittest.main(verbosity=2)
