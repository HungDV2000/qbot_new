# -*- coding: utf-8 -*-
"""
gg_sheet_factory KHÔNG được nạp numpy.

File này được MỌI bot nạp. numpy tốn ~30-40MB mỗi tiến trình, mà nó chỉ dùng
ở 2 dòng — một trong hai là hàm chết. 5 bot × 3 tài khoản = 15 tiến trình
→ lãng phí 450-600MB, đúng lúc VPS đang lỗi 0xc000012d (hết bộ nhớ).
"""
import ast, io, math, os, sys, types, unittest

QBOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, QBOT)


def _nap_ham():
    """Lấy sanitize_for_google_sheets THẬT mà không phải nạp cả module."""
    src = io.open(os.path.join(QBOT, "gg_sheet_factory.py"), encoding="utf-8").read()
    cay = ast.parse(src)
    lay = {}
    for n in cay.body:
        if isinstance(n, ast.FunctionDef) and n.name in (
                "sanitize_for_google_sheets", "sanitize_sheet_values_2d"):
            lay[n.name] = ast.get_source_segment(src, n)
    mod = types.ModuleType("gsf_test")
    mod.__dict__["math"] = math
    exec("\n\n".join(lay.values()), mod.__dict__)
    return mod


class _SoNumpyGia:
    """Giả số numpy: cùng cách nhận diện (__module__) và có .item()."""
    __module__ = "numpy"
    def __init__(self, v): self._v = v
    def item(self): return self._v


class _SoNumpyHong:
    __module__ = "numpy"
    def item(self): raise ValueError("hỏng")


class TestKhongConNumpy(unittest.TestCase):
    def test_gg_sheet_factory_KHONG_import_numpy(self):
        cay = ast.parse(io.open(os.path.join(QBOT, "gg_sheet_factory.py"),
                                encoding="utf-8").read())
        nap = set()
        for n in ast.walk(cay):
            if isinstance(n, ast.Import):
                nap |= {a.name.split(".")[0] for a in n.names}
            elif isinstance(n, ast.ImportFrom) and n.module:
                nap.add(n.module.split(".")[0])
        for x in ("numpy", "pandas"):
            self.assertNotIn(x, nap, f"🔴 gg_sheet_factory nạp {x} → 15 tiến trình cùng tốn RAM")

    def test_ham_chet_da_xoa(self):
        src = io.open(os.path.join(QBOT, "gg_sheet_factory.py"), encoding="utf-8").read()
        self.assertNotIn("def replace_nan", src, "hàm chết vẫn còn")

    def test_requirements_khong_con_numpy(self):
        req = io.open(os.path.join(QBOT, "requirements.txt"), encoding="utf-8").read()
        dong = [l.strip() for l in req.split("\n")
                if l.strip() and not l.strip().startswith("#")]
        self.assertFalse([l for l in dong if l.lower().startswith("numpy")],
                         "requirements.txt vẫn khai numpy")


class TestVanXuLyDungSoNumpy(unittest.TestCase):
    """Bỏ import nhưng PHẢI vẫn xử lý đúng số numpy do bot khác truyền vào."""

    def setUp(self):
        self.m = _nap_ham()

    def test_so_numpy_van_doi_ve_so_python(self):
        kq = self.m.sanitize_for_google_sheets(_SoNumpyGia(3.5))
        self.assertEqual(kq, 3.5)
        self.assertIsInstance(kq, float)

    def test_so_numpy_nguyen(self):
        self.assertEqual(self.m.sanitize_for_google_sheets(_SoNumpyGia(7)), 7)

    def test_so_numpy_NaN_thanh_o_trong(self):
        self.assertEqual(self.m.sanitize_for_google_sheets(_SoNumpyGia(float("nan"))), "")

    def test_so_numpy_vo_cuc_thanh_o_trong(self):
        self.assertEqual(self.m.sanitize_for_google_sheets(_SoNumpyGia(float("inf"))), "")

    def test_so_numpy_hong_thi_tra_o_trong_khong_ne_loi(self):
        self.assertEqual(self.m.sanitize_for_google_sheets(_SoNumpyHong()), "")


class TestKhongLamHongCaiCu(unittest.TestCase):
    def setUp(self):
        self.m = _nap_ham()

    def test_cac_kieu_thong_thuong(self):
        for vao, ra in ((None, ""), ("abc", "abc"), (True, True), (False, False),
                        (5, 5), (2.5, 2.5), ("", "")):
            with self.subTest(vao=vao):
                self.assertEqual(self.m.sanitize_for_google_sheets(vao), ra)

    def test_NaN_va_vo_cuc_thanh_o_trong(self):
        for v in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(v=v):
                self.assertEqual(self.m.sanitize_for_google_sheets(v), "")

    def test_chuoi_duoc_giu_NGUYEN_VEN(self):
        """Chuỗi trả về y nguyên — cố ý, để không làm hỏng mã coin, ghi chú..."""
        for v in ("12.5", "BTC/USDT", "Y", ""):
            with self.subTest(v=v):
                self.assertEqual(self.m.sanitize_for_google_sheets(v), v)

    def test_ma_tran_2d(self):
        kq = self.m.sanitize_sheet_values_2d([[1, float("nan"), "x"], [None, 2.5, True]])
        self.assertEqual(kq, [[1, "", "x"], ["", 2.5, True]])


if __name__ == "__main__":
    unittest.main(verbosity=2)
