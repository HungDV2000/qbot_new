"""
Sheet thiếu tab → bot phải nói thẳng, không in lỗi thô của Google.

Gặp thật trên VPS:
  HttpError 400 ... "Unable to parse range: 'ĐẶT LỆNH'!J1:ZZ1000"
nghĩa là sheet riêng của khách KHÔNG CÓ tab tên 'ĐẶT LỆNH'.

Hàm được lấy ra bằng AST nên chạy offline: không nạp cst, không gọi mạng.

    python3 tests/test_thieu_tab.py
"""
import ast, configparser, io, re, sys, types, unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

QBOT = Path(__file__).resolve().parent.parent


def _lay_ham(file, ten, ns_them=None):
    tree = ast.parse(io.open(QBOT / file, encoding="utf-8").read())
    lay = [n for n in tree.body
           if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name in ten]
    assert len(lay) == len(ten), f"thiếu hàm trong {file}: {ten}"
    ns = {"re": re, "print": print}
    ns.update(ns_them or {})
    exec(compile(ast.Module(body=lay, type_ignores=[]), file, "exec"), ns)
    return ns


class TestCauBaoThieuTab(unittest.TestCase):
    LOI = ("<HttpError 400 when requesting https://sheets.googleapis.com/v4/spreadsheets/"
           "1AL5IPYagg/values/%27%C4%90%E1%BA%B6T%20L%E1%BB%86NH%27%21J1%3AZZ1000?"
           "valueInputOption=USER_ENTERED&alt=json returned \"Unable to parse range: "
           "'ĐẶT LỆNH'!J1:ZZ1000\". Details: \"Unable to parse range: 'ĐẶT LỆNH'!J1:ZZ1000\">")

    def setUp(self):
        self.ns = _lay_ham("gg_sheet_factory.py", ["ten_tab_trong_loi", "mo_ta_thieu_tab"])

    def test_lay_dung_ten_tab_tu_loi_google(self):
        self.assertEqual(self.ns["ten_tab_trong_loi"](self.LOI), "ĐẶT LỆNH")

    def test_loi_la_thi_khong_doan_bua(self):
        self.assertEqual(self.ns["ten_tab_trong_loi"]("mạng hỏng"), "(không rõ)")

    def test_cau_bao_liet_ke_tab_dang_co(self):
        msg = self.ns["mo_ta_thieu_tab"]("ĐẶT LỆNH", ["ĐẶT LỆNH (100 MÃ)", "Chờ và khớp"], "1AL5")
        self.assertIn("KHÔNG có tab tên 'ĐẶT LỆNH'", msg)
        self.assertIn("'ĐẶT LỆNH (100 MÃ)'", msg)
        self.assertIn("tab_dat_lenh", msg, "phải chỉ ra sửa tên tab hoặc sửa config")
        self.assertIn("TỪNG KÝ TỰ", msg)

    def test_khong_doc_duoc_danh_sach_tab(self):
        msg = self.ns["mo_ta_thieu_tab"]("ĐẶT LỆNH", [], "1AL5")
        self.assertIn("Không đọc được danh sách tab", msg)


class TestSoatTabTungTaiKhoan(unittest.TestCase):
    """kiem_tra_cau_hinh phải bắt lỗi sai tên tab TRƯỚC khi bật bot."""

    def _cst(self, sheet_theo_tk):
        cfg = configparser.ConfigParser()
        cfg.read_dict({"global": {"spreadsheet_id": ""}})
        for ten, sid in sheet_theo_tk.items():
            cfg.read_dict({ten: {"spreadsheet_id": sid}})
        return types.SimpleNamespace(tab_dat_lenh="ĐẶT LỆNH", config=cfg,
                                     resolve_section=lambda t: t)

    def _chay(self, sheet_theo_tk, tab_theo_sheet, loi_theo_sheet=None):
        loi_theo_sheet = loi_theo_sheet or {}

        class SV:
            def spreadsheets(s):
                class S:
                    def get(_s, spreadsheetId=None, fields=None):
                        class R:
                            def execute(__s):
                                if spreadsheetId in loi_theo_sheet:
                                    raise Exception(loi_theo_sheet[spreadsheetId])
                                return {"sheets": [{"properties": {"title": t}}
                                                   for t in tab_theo_sheet.get(spreadsheetId, [])]}
                        return R()
                return S()
        gia = types.ModuleType("sheet_config"); gia._lay_service = lambda: SV()
        ns = _lay_ham("kiem_tra_cau_hinh.py", ["soat_tab_tung_tai_khoan"])
        out = io.StringIO()
        with mock.patch.dict(sys.modules, {"sheet_config": gia}), redirect_stdout(out):
            n = ns["soat_tab_tung_tai_khoan"](self._cst(sheet_theo_tk), list(sheet_theo_tk))
        return n, out.getvalue()

    def test_du_tab_thi_khong_loi(self):
        n, out = self._chay({"q2pri": "S_A"}, {"S_A": ["ĐẶT LỆNH", "Chờ và khớp", "khác"]})
        self.assertEqual(n, 0, out)
        self.assertIn("✅ [q2pri]", out)

    def test_thieu_tab_thi_bao_va_liet_ke(self):
        n, out = self._chay({"q2pri": "S_A"}, {"S_A": ["ĐẶT LỆNH (100 MÃ)", "Chờ và khớp"]})
        self.assertEqual(n, 1)
        self.assertIn("THIẾU tab", out)
        self.assertIn("'ĐẶT LỆNH'", out)
        self.assertIn("'ĐẶT LỆNH (100 MÃ)'", out, "phải liệt kê tab đang có để đối chiếu")

    def test_thieu_tab_cho_va_khop(self):
        n, out = self._chay({"q2pri": "S_A"}, {"S_A": ["ĐẶT LỆNH"]})
        self.assertEqual(n, 1)
        self.assertIn("Chờ và khớp", out)

    def test_sai_sheet_id_va_thieu_quyen(self):
        n, out = self._chay({"a": "S_A", "b": "S_B"}, {},
                            {"S_A": "<HttpError 404 ... not found>",
                             "S_B": "<HttpError 403 ... permission>"})
        self.assertEqual(n, 2)
        self.assertIn("Sheet ID sai", out)
        self.assertIn("quyền", out)

    def test_nhieu_tai_khoan_chi_bao_dung_cai_sai(self):
        n, out = self._chay({"a": "S_A", "b": "S_B"},
                            {"S_A": ["ĐẶT LỆNH", "Chờ và khớp"], "S_B": ["Sheet1"]})
        self.assertEqual(n, 1)
        self.assertIn("✅ [a]", out)
        self.assertIn("❌ [b]", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
