"""
Huỷ lệnh ĐIỀU KIỆN ở Algo API (stop, stop limit, trailing, cắt lỗ closePosition).

Gặp thật khi đặt lệnh ARBUSDT: Binance đưa mọi lệnh điều kiện sang Algo API. STOP /
XÓA CHỜ / dọn lệnh khi vị thế đóng trước đây chỉ huỷ lệnh THƯỜNG → lệnh vào stop /
trailing còn treo sẽ MỞ LẠI vị thế sau khi bấm STOP. Chạy offline, không mạng.

    python3 tests/test_huy_algo.py
"""
import ast, importlib.util, io, os, sys, types, unittest
from unittest import mock

QBOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _nap_bfd():
    """Nạp binance_futures_direct THẬT (cst + requests giả để không cần mạng/config)."""
    gia = {"cst": types.ModuleType("cst")}
    try:
        import requests  # noqa: F401
    except ImportError:
        gia["requests"] = types.ModuleType("requests")
    spec = importlib.util.spec_from_file_location("bfd_that", os.path.join(QBOT, "binance_futures_direct.py"))
    m = importlib.util.module_from_spec(spec)
    with mock.patch.dict(sys.modules, gia):
        spec.loader.exec_module(m)
    return m


BFD = _nap_bfd()


class _San:
    """Algo API giả: ghi lại mọi lời gọi."""

    def __init__(self, ds, huy_loi=()):
        self.ds, self.huy_loi, self.goi = ds, set(huy_loi), []

    def __call__(self, method, endpoint, params=None, **k):
        self.goi.append((method, endpoint, dict(params or {})))
        if method == "GET":
            if isinstance(self.ds, Exception):
                raise self.ds
            return self.ds
        if params.get("algoId") in self.huy_loi:
            return None
        return {"algoId": params["algoId"], "code": "200", "msg": "success"}


def _chay(san, symbol=""):
    with mock.patch.object(BFD, "futures_signed_request", san):
        return BFD.cancel_algo_orders(symbol)


class TestHuyAlgo(unittest.TestCase):
    def test_huy_het_moi_ma(self):
        san = _San([{"symbol": "ARBUSDT", "algoId": 1}, {"symbol": "DOGEUSDT", "algoId": 2}])
        self.assertEqual(_chay(san), (2, 0))
        self.assertEqual(san.goi[0], ("GET", "/fapi/v1/openAlgoOrders", {}))
        self.assertEqual([g[2] for g in san.goi[1:]],
                         [{"symbol": "ARBUSDT", "algoId": 1}, {"symbol": "DOGEUSDT", "algoId": 2}])

    def test_theo_mot_ma(self):
        san = _San([{"symbol": "ARBUSDT", "algoId": 7}])
        self.assertEqual(_chay(san, "ARB/USDT:USDT"), (1, 0))
        self.assertEqual(san.goi[0][2], {"symbol": "ARBUSDT"})

    def test_khong_co_lenh(self):
        self.assertEqual(_chay(_San([])), (0, 0))

    def test_huy_loi_duoc_dem_rieng(self):
        san = _San([{"symbol": "ARBUSDT", "algoId": 1}, {"symbol": "ARBUSDT", "algoId": 2}], huy_loi={2})
        self.assertEqual(_chay(san), (1, 1))

    def test_khong_doc_duoc_danh_sach(self):
        for ds in (None, RuntimeError("mạng")):
            with self.subTest(ds=ds):
                san = _San(ds)
                self.assertEqual(_chay(san), (0, -1))
                self.assertEqual([g for g in san.goi if g[0] == "DELETE"], [], "không đọc được thì không huỷ mò")


def _doan(src, dau, cuoi):
    i = src.index(dau)
    return src[i:src.index(cuoi, i)]


class TestNoiVaoBot(unittest.TestCase):
    def setUp(self):
        self.multi = io.open(os.path.join(QBOT, "hd_order_multi.py"), encoding="utf-8").read()

    def test_STOP_huy_ca_lenh_algo(self):
        self.assertIn("cancel_algo_orders()", _doan(self.multi, "if state_value == STATE_STOP:", 'elif state_value == "XÓA CHỜ":'))

    def test_XOA_CHO_huy_ca_lenh_algo(self):
        self.assertIn("cancel_algo_orders()", _doan(self.multi, 'elif state_value == "XÓA CHỜ":', 'elif state_value == "XÓA VỊ THẾ":'))

    def test_dong_vi_the_don_ca_lenh_algo(self):
        src = io.open(os.path.join(QBOT, "hd_alert_possition_and_open_order.py"), encoding="utf-8").read()
        self.assertIn("cancel_algo_orders(symbol)", _doan(src, "def cancel_all_open_orders(", "\ndef "))

    def test_canh_bao_khi_con_lenh_chua_huy(self):
        fn = next(n for n in ast.parse(self.multi).body
                  if isinstance(n, ast.FunctionDef) and n.name == "_canh_bao_algo")
        ns = {}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), "hd_order_multi.py", "exec"), ns)
        self.assertEqual(ns["_canh_bao_algo"](0), "")
        self.assertIn("Còn 2", ns["_canh_bao_algo"](2))
        self.assertIn("Không đọc được", ns["_canh_bao_algo"](-1))


if __name__ == "__main__":
    unittest.main(verbosity=2)
