# -*- coding: utf-8 -*-
"""
Chế độ balance_only: hd_update_all CHỈ lấy số dư, ghi vào J1:M2 tab ĐẶT LỆNH,
và KHÔNG đụng tới tab "100 mã" (tab đó sắp bị xoá khỏi sheet).

Chạy bot THẬT trong hộp cát, ghi lại mọi lệnh gọi sheet rồi soi — không chỉ
đọc chữ trong file. Không mạng, không tiền thật.
"""
import io, json, os, shutil, subprocess, sys, tempfile, textwrap, unittest
from pathlib import Path

QBOT = Path(__file__).resolve().parent.parent

CONFIG = """
[global]
accounts =
key_name = test
key_binance = K
secret_binance = S
spreadsheet_id = SHEET
chat_id = -100
bot_token = X
is_print_mode = false
test_mode = true
tab_dat_lenh = ĐẶT LỆNH (100 MÃ)
top_count = 50
time_gap_do_it = 0
max_increase_decrease_4h_day_count = 60
lenh2_rate_long = 1
lenh2_rate_short = 1
lenh3_rate_long = 1
lenh3_rate_short = 1
lenh3_callback_rate = 1
delay_vao_lenh = 60
delay_vao_lenh_123 = 300
delay_cho_va_khop = 600
delay_calert_possition_and_open_order = 120
delay_update_price = 120
delay_update_all = 120
delay_track_30_prices = 60
delay_periodic_report = 300
cancel_orders_minutes = 60
cancel_order_after_minutes = 30
{them}
"""

MOCKS = {
"gg_sheet_factory.py": '''
import json, os, cst
tab_dat_lenh = cst.tab_dat_lenh
tab_list_all_ma = "100 ma (50 tang va 50 giam)"
tab_cho_va_khop = "Cho va khop"
tab_white_list = "list"
_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sheet_calls.log")
def _ghi(op, tab, extra=""):
    with open(_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps({"op": op, "tab": tab, "extra": extra}, ensure_ascii=False) + "\\n")
def init_sheet_api(): pass
def get_dat_lenh(rng): _ghi("read", tab_dat_lenh, rng); return []
def get_100_ma(rng):   _ghi("read", tab_list_all_ma, rng); return []
def get_white_list():  _ghi("read", tab_white_list, "A1:A1000"); return []
def get_cho_va_khop(rng, value_render_option=None): _ghi("read", tab_cho_va_khop, rng); return []
def update_multi(tab, idx, arr, col):
    _ghi("write", tab, json.dumps({"col": col, "idx": idx, "rows": arr}, ensure_ascii=False))
def update_single_value(tab, rng, v): _ghi("write", tab, rng)
def clear_multi(tab, *a, **k): _ghi("clear", tab)
''',
"binance_futures_direct.py": '''
def futures_signed_request(method, path, **k):
    return {"totalMarginBalance": "2000.5", "totalWalletBalance": "12345.67",
            "totalCrossUnPnl": "-50.25"}
def fetch_algo_orders_for_symbol(*a, **k): return []
def resync_exchange_time(*a, **k): pass
def normalize_algo_orders_response(*a, **k): return []
clock = 0
drift = 0
''',
"binance_symbol_row.py": '''
def build_symbol_data(*a, **k): return []
def preload_exchange_caches(*a, **k): pass
def fetch_all_tickers_24h(*a, **k): return {}
def get_sheet_col_c_price(*a, **k): return 0
def ticker_key_from_pair_display(p): return p
def fetch_ticker_24h(*a, **k): return {"lastPrice": "1"}
''',
"requests.py": '''
class _R:
    status_code = 200
    text = "[]"
    def json(self): return []
    def raise_for_status(self): pass
def get(*a, **k): return _R()
def post(*a, **k): return _R()
class exceptions:
    class RequestException(Exception): pass
''',
"telegram_factory.py": "def send_tele(*a, **k): pass\n",
"utils.py": "def get_all_open_orders_symbol_local(): return []\n",
"binance_utils.py": "def get_price_precision(s): return 4\n",
"ccxt.py": '''
__version__ = "4"
class BaseError(Exception): pass
class NetworkError(BaseError): pass
class ExchangeError(BaseError): pass
class binance:
    def __init__(self, *a, **k): self.markets = {}
    def setSandboxMode(self, *a, **k): pass
    def load_markets(self, *a, **k): return {}
    def fetch_tickers(self, *a, **k): return {}
''',
}


def _dung_hop_cat(them_config=""):
    d = Path(tempfile.mkdtemp(prefix="qbot_bal_"))
    # hd_update_price.py là bot ĐÃ NGHỈ — bản gọn (qbot_new) không chép nó,
    # nên chỉ copy file nào thực sự có.
    for f in ("cst.py", "rate_guard.py", "symbol_filter.py", "config_watcher.py",
              "sheet_config.py", "hd_update_all.py", "hd_update_price.py"):
        if (QBOT / f).exists():
            shutil.copy(QBOT / f, d / f)
    for ten, noi_dung in MOCKS.items():
        (d / ten).write_text(textwrap.dedent(noi_dung), encoding="utf-8")
    (d / "googleapiclient").mkdir(exist_ok=True)
    (d / "googleapiclient" / "__init__.py").write_text("", encoding="utf-8")
    (d / "googleapiclient" / "errors.py").write_text(
        "class HttpError(Exception): pass\n", encoding="utf-8")
    (d / "config.ini").write_text(
        textwrap.dedent(CONFIG.format(them=them_config)), encoding="utf-8")
    return d


def _chay(d, bot, giay=25):
    p = subprocess.Popen([sys.executable, bot], cwd=d,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, encoding="utf-8", errors="replace")
    try:
        out, _ = p.communicate(timeout=giay)
    except subprocess.TimeoutExpired:
        p.kill(); out, _ = p.communicate()
    goi = []
    f = d / "sheet_calls.log"
    if f.exists():
        goi = [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]
    return out, goi


class TestBalanceOnly(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.d = _dung_hop_cat()
        cls.out, cls.goi = _chay(cls.d, "hd_update_all.py")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.d, ignore_errors=True)

    def test_bot_chay_duoc_khong_loi(self):
        self.assertNotIn("Traceback", self.out, f"bot lỗi:\n{self.out[:600]}")

    # ⚠️ Tab ĐẶT LỆNH tên là "ĐẶT LỆNH (100 MÃ)" — CŨNG chứa chữ "100".
    # Phải so khớp ĐÚNG TÊN tab bị bỏ, không dùng chuỗi con "100".
    TAB_DA_BO = ("100 ma (50 tang va 50 giam)", "list")

    def test_KHONG_dung_toi_tab_100_ma(self):
        """Tab này sắp bị xoá khỏi sheet — đụng vào là bot sẽ lỗi trên máy thật."""
        cham = [g for g in self.goi if g["tab"] in self.TAB_DA_BO]
        self.assertEqual(cham, [], f"🔴 vẫn đụng tab đã bỏ: {cham}")

    def test_ghi_so_du_vao_tab_dat_lenh(self):
        ghi = [g for g in self.goi if g["op"] == "write" and "ĐẶT LỆNH" in g["tab"]]
        self.assertTrue(ghi, f"không ghi gì vào tab ĐẶT LỆNH. Đã gọi: {self.goi}")

    def test_ghi_dung_vung_J1_M2(self):
        ghi = [g for g in self.goi if g["op"] == "write" and "ĐẶT LỆNH" in g["tab"]][0]
        chi_tiet = json.loads(ghi["extra"])
        self.assertEqual(chi_tiet["col"], "J", "phải bắt đầu từ cột J")
        self.assertEqual(chi_tiet["idx"], -1, "idx=-1 nghĩa là ghi từ dòng 1")
        self.assertEqual(len(chi_tiet["rows"]), 2, "phải đúng 2 dòng (J1:M2)")
        for dong in chi_tiet["rows"]:
            self.assertEqual(len(dong), 4, "mỗi dòng đúng 4 cột (J,K,L,M)")

    def test_dung_so_du_lay_tu_san(self):
        ghi = [g for g in self.goi if g["op"] == "write" and "ĐẶT LỆNH" in g["tab"]][0]
        tieu_de, gia_tri = json.loads(ghi["extra"])["rows"]
        self.assertEqual(tieu_de, ["Số dư ví", "Ký quỹ", "Lãi/lỗ mở", "Cập nhật lúc"])
        self.assertEqual(gia_tri[0], 12345.67, "cột J = số dư ví")
        self.assertEqual(gia_tri[1], 2000.5,   "cột K = ký quỹ")
        self.assertEqual(gia_tri[2], -50.25,   "cột L = lãi/lỗ mở")
        self.assertRegex(str(gia_tri[3]), r"\d{2}/\d{2}/\d{4} \d{2}:\d{2}:\d{2}")

    def test_rat_it_luot_goi_sheet(self):
        """Chế độ nhẹ: 1 vòng chỉ nên tốn 1 lượt ghi."""
        self.assertLessEqual(len(self.goi), 2, f"gọi quá nhiều: {self.goi}")


@unittest.skipUnless((QBOT / "hd_update_price.py").exists(),
                     "hd_update_price.py không có trong thư mục này (bản gọn)")
class TestUpdatePriceDaNghi(unittest.TestCase):
    def test_tu_thoat_kem_giai_thich(self):
        d = _dung_hop_cat()
        try:
            out, goi = _chay(d, "hd_update_price.py", giay=20)
            self.assertIn("ĐÃ NGHỈ", out, f"phải báo rõ đã nghỉ:\n{out[:400]}")
            self.assertNotIn("Traceback", out)
            self.assertEqual(goi, [], "đã nghỉ thì không được gọi sheet lần nào")
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_van_chay_lai_duoc_khi_dat_full(self):
        d = _dung_hop_cat(them_config="update_all_mode = full")
        try:
            out, _ = _chay(d, "hd_update_price.py", giay=20)
            self.assertNotIn("ĐÃ NGHỈ", out, "đặt full thì phải chạy lại")
        finally:
            shutil.rmtree(d, ignore_errors=True)


class TestCauHinhSai(unittest.TestCase):
    def test_gia_tri_la_thi_dung_han(self):
        d = _dung_hop_cat(them_config="update_all_mode = nhe")
        try:
            out, _ = _chay(d, "hd_update_all.py", giay=20)
            self.assertIn("không hợp lệ", out, "gõ sai chế độ phải báo, không đoán bừa")
        finally:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
