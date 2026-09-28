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

    def _jp(self, sltp, rows, cu, M=None):
        """Vùng J–P trong kế hoạch ghi (None nếu không ghi J–P)."""
        kh = (M or self.M).ke_hoach_ghi_cho_va_khop(rows, [[0]] * len(rows), sltp, cu, "t")
        jp = [(r, v) for r, v in kh if r.startswith("J")]
        return jp[0] if jp else None

    def test_ghi_tu_cot_J_dong_4(self):
        vung, rows = self._jp([["98", "103", "N"]], [self.BTC], [])
        self.assertEqual(vung, "J4:P4", "ghi khối J–P (J–M tick, N=SL, O=TP, P=cho phép) từ dòng 4")
        self.assertEqual(rows, [["", "", "", "", "98", "103", "N"]])

    def test_KHONG_de_len_so_nguoi_dung_da_sua(self):
        """Người dùng sửa SL thành 95 → lần chạy sau phải GIỮ NGUYÊN 95."""
        cu = [self.BTC + ["", "", "", "", "95", "", "Y"]]   # N=95 (user sửa), O trống, P=Y
        _, rows = self._jp([["98", "103", "N"]], [self.BTC], cu)
        self.assertEqual(rows[0][4], "95", "🔴 ĐÈ MẤT giá SL người dùng nhập!")
        self.assertEqual(rows[0][5], "103", "ô trống thì mới điền gợi ý")
        self.assertEqual(rows[0][6], "Y", "🔴 ĐÈ MẤT cờ cho phép người dùng bật!")

    def test_dong_xe_dich_thi_tick_va_SL_di_theo_ma(self):
        """BTC từ dòng 4 xuống dòng 5 → tick J và SL 95 phải đi theo BTC."""
        cu = [self.BTC + [True, "", "", "", "95", "104", "Y"], self.ETH + [""] * 7]
        _, rows = self._jp([["51", "48", "N"], ["98", "103", "N"]], [self.ETH, self.BTC], cu)
        self.assertEqual(rows[1], [True, "", "", "", "95", "104", "Y"], "🔴 J–P không đi theo BTC")
        self.assertEqual(rows[0][:4], ["", "", "", ""], "🔴 tick của BTC rơi sang ETH")
        self.assertEqual(rows[0][4:], ["51", "48", "N"], "ETH nhận gợi ý của chính nó")

    def test_tat_bang_config(self):
        M, sheet = _nap_module(fill=False)
        self.assertIsNone(self._jp([["98", "103", "N"]], [self.BTC], [], M),
                          "fill_default_cho_va_khop=false, không dời gì → không ghi J–P")

    def test_doc_loi_thi_bo_qua_thay_vi_de_bua(self):
        """Đọc A–Q lỗi → KHÔNG ghi J–P, để khỏi xoá mất số người dùng."""
        def no(*a, **k): raise RuntimeError("mạng lỗi")
        self.sheet.get_cho_va_khop = no
        anh = self.M.doc_anh_cu_cho_va_khop()
        self.assertIsNone(anh)
        self.assertIsNone(self._jp([["98", "103", "N"]], [self.BTC], anh),
                          "🔴 vẫn ghi dù không đọc được — nguy cơ đè mất dữ liệu")

    def test_doc_dang_FORMULA_de_giu_cong_thuc_va_do_chinh_xac(self):
        goi = []
        self.sheet.get_cho_va_khop = lambda rng, value_render_option=None: goi.append((rng, value_render_option)) or []
        self.M.doc_anh_cu_cho_va_khop()
        self.assertEqual(goi, [("A4:Q1000", "FORMULA")], "đọc tới Q để biết bảng cũ dài bao nhiêu")

    def test_default_allow_order_Y_thi_tu_dong_hoan_toan(self):
        M, sheet = _nap_module(allow="Y")
        p = M.goi_y_sltp_cho_dong(["BTC/USDT", "LONG", "", "Y", 100.0])[2]
        self.assertEqual(p, "Y", "đặt default_allow_order=Y thì SL/TP tự động hẳn")


class TestGhiMotLenh(unittest.TestCase):
    """Bug 1 (09/2026): trước đây xoá A4:I1000 + Q4:Q1000 rồi ghi A2, A–I, Q, J–P bằng
    6 lệnh rời. Lỗi/429 giữa chừng → A–I trống mà J–P còn → vòng sau J–P mồ côi trao
    nhầm cho mã mới (bug 2). Nay: 1 lệnh batchUpdate, KHÔNG xoá trước."""

    BTC = TestGhiVaoSheet.BTC
    ETH = TestGhiVaoSheet.ETH

    def setUp(self):
        self.M, self.sheet = _nap_module()

    def _kh(self, rows, cu, q=None):
        q = q if q is not None else [[1.0]] * len(rows)
        return dict(self.M.ke_hoach_ghi_cho_va_khop(rows, q, [["", "", ""]] * len(rows), cu, "T"))

    def test_mot_lenh_du_A2_AI_Q(self):
        kh = self._kh([self.BTC], [])
        self.assertEqual(kh["A2"], [["T"]])
        self.assertEqual(kh["A4:I4"], [self.BTC])
        self.assertEqual(kh["Q4:Q4"], [[1.0]])

    def test_bang_ngan_lai_thi_de_o_trong_len_dong_thua(self):
        """Cũ 3 dòng, mới 1 dòng → dòng 5–6 của A–I và Q phải thành ô trống (thay cho clear)."""
        cu = [self.BTC + [""] * 8, self.ETH + [""] * 8, self.ETH + [""] * 8]
        kh = self._kh([self.BTC], cu)
        self.assertEqual(kh["A4:I6"], [self.BTC, [""] * 9, [""] * 9])
        self.assertEqual(kh["Q4:Q6"], [[1.0], [""], [""]])

    def test_doc_bang_cu_loi_thi_de_trong_toi_het_vung(self):
        kh = self._kh([self.BTC], None)
        self.assertIn("A4:I1000", kh)
        self.assertEqual(len(kh["A4:I1000"]), 997)
        self.assertNotIn("J4:P4", kh, "không đọc được bảng cũ → không đụng J–P")

    def test_bang_rong_van_ghi_hop_le(self):
        kh = self._kh([], [])
        self.assertEqual(kh["A4:I4"], [[""] * 9])

    def test_do_it_khong_con_xoa_truoc_ghi(self):
        import io
        src = io.open("hd_update_cho_va_khop.py", encoding="utf-8").read()
        for cam in ("clear_multi(", "update_single_value(", "update_multi("):
            self.assertNotIn(cam, src, f"🔴 còn lệnh ghi/xoá rời {cam} trong hd_update_cho_va_khop")
        self.assertEqual(src.count("gg_sheet_factory.batch_update_values("), 1)


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
        BTC = TestGhiVaoSheet.BTC
        for cu in ([], None, [BTC + [""] * 8] * 5):
            for vung, _ in self.M.ke_hoach_ghi_cho_va_khop([BTC], [[1]], [["1", "2", "N"]], cu, "T"):
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


class TestCodeDaNoi(unittest.TestCase):
    def test_ham_khong_con_la_code_chet(self):
        import io
        src = io.open("hd_update_cho_va_khop.py", encoding="utf-8").read()
        self.assertGreaterEqual(src.count("compute_default_sl_tp_prices"), 2,
                                "🔴 hàm vẫn không ai gọi")
        self.assertIn("khoi_jp_can_ghi(tab_sltp, rows_ai, anh_cu)", src,
                      "chưa nối vào luồng ghi sheet")
        # Phải chụp A–Q TRƯỚC khi ghi, nếu không sẽ không biết J–P thuộc mã nào
        self.assertLess(src.index("anh_cu = doc_anh_cu_cho_va_khop()"),
                        src.index("gg_sheet_factory.batch_update_values("))

    def test_cac_tham_so_layer_da_duoc_dung(self):
        import io
        src = io.open("hd_update_cho_va_khop.py", encoding="utf-8").read()
        for k in ("cst.fill_default_cho_va_khop", "cst.default_allow_order"):
            with self.subTest(khoa=k):
                self.assertIn(k, src, f"{k} vẫn là tham số chết")


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
