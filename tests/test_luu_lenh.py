"""
hd_order_multi.printf lưu mỗi lệnh đã đặt vào order/<tài khoản>/<mã>/<id>.txt.

Lỗi trên VPS Windows: tên mã "ATOM/USDT:USDT" dùng thẳng làm thư mục →
'order\\q2pri\\ATOM\\USDT:USDT' → WinError 267 (Windows cấm ':' trong tên).
Trên Mac/Linux ':' hợp lệ nên phải soi tên thư mục, không chờ lỗi xảy ra.

    python3 tests/test_luu_lenh.py
"""
import ast, io, os, shutil, tempfile, types, unittest
from datetime import datetime
from pathlib import Path

QBOT = Path(__file__).resolve().parent.parent
KY_TU_WINDOWS_CAM = set('<>:"/\\|?*')


def _nap_printf(thu_muc):
    tree = ast.parse(io.open(QBOT / "hd_order_multi.py", encoding="utf-8").read())
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "printf")
    loi = []
    ns = {
        "os": os, "datetime": datetime, "Path": Path,
        "logger": types.SimpleNamespace(error=lambda *a, **k: loi.append(a[0]),
                                        warning=lambda *a, **k: None),
        "cst": types.SimpleNamespace(account_dir=lambda b: Path(thu_muc) / b / "q2pri"),
    }
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "hd_order_multi.py", "exec"), ns)
    return ns["printf"], loi


class TestLuuLenh(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(prefix="qbot_order_")
        self.printf, self.loi = _nap_printf(self.d)

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def _cac_file(self):
        return [Path(r) / f for r, _, fs in os.walk(self.d) for f in fs]

    def test_ten_ma_ccxt_khong_con_ky_tu_windows_cam(self):
        self.printf("ATOM/USDT:USDT", {"id": "123456"})
        self.assertEqual(self.loi, [], f"🔴 printf lỗi: {self.loi}")
        fs = self._cac_file()
        self.assertEqual(len(fs), 1)
        rel = fs[0].relative_to(Path(self.d) / "order" / "q2pri")
        self.assertEqual(str(rel).replace("\\", "/"), "ATOMUSDT/123456.txt")
        for phan in rel.parts:
            self.assertFalse(KY_TU_WINDOWS_CAM & set(phan), f"🔴 '{phan}' có ký tự Windows cấm")

    def test_id_algo_trong_info(self):
        self.printf("BTC/USDT:USDT", {"info": {"algoId": 987}})
        self.assertTrue((Path(self.d) / "order" / "q2pri" / "BTCUSDT" / "987.txt").exists())

    def test_ten_ma_da_la_dang_gon(self):
        self.printf("ETHUSDT", {"id": "1"})
        self.assertTrue((Path(self.d) / "order" / "q2pri" / "ETHUSDT" / "1.txt").exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
