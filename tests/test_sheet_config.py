# -*- coding: utf-8 -*-
"""Đọc cấu hình từ sheet tổng — phần tách dữ liệu, chạy offline."""
import os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sheet_config as sc

BANG_MAU = [
    ["PHIÊN BẢN", "7"],
    ["Tài khoản", "Bật", "API Key", "API Secret", "Sheet ID", "Chat ID", "Lớp", "%SL", "%TP"],
    ["q2pri", "Y", "KEY_A", "SEC_A", "SHEET_A", "-100", "1", "2", "3"],
    ["q2pub", "Y", "KEY_B", "SEC_B", "SHEET_B", "-100", "2", "5", "6"],
    ["q3fu",  "N", "KEY_C", "SEC_C", "SHEET_C", "-100", "3", "10", "10"],
]


class TestTachDuLieu(unittest.TestCase):
    def test_doc_dung_phien_ban_va_so_tai_khoan(self):
        pb, bang = sc.phan_tich_bang(BANG_MAU)
        self.assertEqual(pb, "7")
        self.assertEqual(sorted(bang), ["q2fu" if False else "q2pri", "q2pub", "q3fu"])

    def test_map_dung_nhan_tieng_viet_sang_tham_so(self):
        _, bang = sc.phan_tich_bang(BANG_MAU)
        a = bang["q2pri"]
        self.assertEqual(a["key_binance"], "KEY_A")
        self.assertEqual(a["secret_binance"], "SEC_A")
        self.assertEqual(a["spreadsheet_id"], "SHEET_A")
        self.assertEqual(a["chat_id"], "-100")
        self.assertEqual(a["default_sl_rate_layer_1"], "2")
        self.assertEqual(a["default_tp_rate_layer_1"], "3")

    def test_cot_Lop_cu_bi_bo_qua(self):
        """Sheet cũ còn cột "Lớp" → không sinh ra tham số nào, không làm hỏng gì."""
        _, bang = sc.phan_tich_bang(BANG_MAU)      # BANG_MAU vẫn có cột "Lớp"
        for ten, muc in bang.items():
            with self.subTest(tk=ten):
                # So khớp CHÍNH XÁC: default_sl_rate_layer_1 là tham số hợp lệ,
                # chỉ bắt các khoá sinh ra từ cột "Lớp".
                self.assertFalse([k for k in muc if k in ("__lop__", "lop", "layer", "lớp")],
                                 "cột Lớp lọt thành tham số")
                self.assertEqual(muc["default_sl_rate_layer_1"],
                                 {"q2pri": "2", "q2pub": "5", "q3fu": "10"}[ten],
                                 "cột %SL ngay sau cột Lớp phải đọc đúng")

    def test_tieu_de_khong_dau_van_hieu(self):
        b = [r[:] for r in BANG_MAU]
        b[1] = ["Tai khoan", "Bat", "Api Key", "API SECRET", "sheet id", "Chat ID", "Lop", "% SL", "% TP"]
        _, bang = sc.phan_tich_bang(b)
        self.assertEqual(bang["q2pri"]["key_binance"], "KEY_A")

    def test_them_cot_ten_tham_so_la_dung_duoc_ngay(self):
        """Gõ thẳng `allow_dca` làm tiêu đề → có tác dụng, không cần sửa code."""
        b = [r[:] for r in BANG_MAU]
        b[1] = b[1] + ["allow_dca"]
        b[2] = b[2] + ["true"]
        _, bang = sc.phan_tich_bang(b)
        self.assertEqual(bang["q2pri"]["allow_dca"], "true")

    def test_o_trong_thi_bo_qua_khong_ghi_de(self):
        b = [r[:] for r in BANG_MAU]
        b[2][5] = ""                       # Chat ID để trống
        _, bang = sc.phan_tich_bang(b)
        self.assertNotIn("chat_id", bang["q2pri"])

    def test_trung_ten_tai_khoan_thi_DUNG(self):
        b = [r[:] for r in BANG_MAU] + [["Q2PRI", "Y", "K", "S", "SH"]]
        with self.assertRaises(sc.LoiSheetCauHinh) as e:
            sc.phan_tich_bang(b)
        self.assertIn("trùng", str(e.exception))

    def test_thieu_cot_tai_khoan_thi_bao_ro(self):
        b = [r[:] for r in BANG_MAU]
        b[1][0] = "Ghi chú"
        with self.assertRaises(sc.LoiSheetCauHinh) as e:
            sc.phan_tich_bang(b)
        self.assertIn("Tài khoản", str(e.exception))

    def test_sheet_rong_hoac_thieu_dong(self):
        for xau in ([], [["PHIÊN BẢN", "1"]], [["PHIÊN BẢN", "1"], ["Tài khoản"]]):
            with self.subTest(bang=xau):
                with self.assertRaises(sc.LoiSheetCauHinh):
                    sc.phan_tich_bang(xau)


class TestLocVaKiemTra(unittest.TestCase):
    def test_cot_Bat_N_thi_loai(self):
        _, bang = sc.phan_tich_bang(BANG_MAU)
        bat = sc.loc_dang_bat(bang)
        self.assertEqual(sorted(bat), ["q2pri", "q2pub"])
        self.assertNotIn("q3fu", bat, "q3fu để Bật=N nên phải bị loại")

    def test_khong_khai_cot_Bat_thi_coi_nhu_bat(self):
        bang = {"x": {"__ten__": "x"}}
        self.assertIn("x", sc.loc_dang_bat(bang))

    def test_thieu_key_thi_DUNG(self):
        bang = {"x": {"__ten__": "x", "key_binance": "K"}}   # thiếu secret + sheet
        with self.assertRaises(sc.LoiSheetCauHinh) as e:
            sc.kiem_tra_du_khoa(bang)
        self.assertIn("secret_binance", str(e.exception))
        self.assertIn("spreadsheet_id", str(e.exception))

    def test_du_key_thi_qua(self):
        bang = {"x": {"__ten__": "x", "key_binance": "K",
                      "secret_binance": "S", "spreadsheet_id": "SH"}}
        sc.kiem_tra_du_khoa(bang)      # không được ném


class TestTimTaiKhoan(unittest.TestCase):
    def setUp(self):
        _, self.bang = sc.phan_tich_bang(BANG_MAU)

    def test_khop_chinh_xac(self):
        self.assertEqual(sc.tim_tai_khoan(self.bang, "q2pri"), "q2pri")

    def test_khop_bo_qua_hoa_thuong(self):
        self.assertEqual(sc.tim_tai_khoan(self.bang, "Q2PRI"), "q2pri")

    def test_khong_co_thi_tra_None(self):
        self.assertIsNone(sc.tim_tai_khoan(self.bang, "khong_ton_tai"))


class TestKhongNapCheo(unittest.TestCase):
    def test_khong_import_cst_hay_gg_sheet_factory(self):
        """Nạp chéo sẽ thành vòng lặp import — phải giữ module này độc lập."""
        import ast, io
        cay = ast.parse(io.open("sheet_config.py", encoding="utf-8").read())
        cam = set()
        for n in ast.walk(cay):
            if isinstance(n, ast.Import):
                cam |= {a.name.split(".")[0] for a in n.names}
            elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
                cam.add(n.module.split(".")[0])
        for x in ("cst", "gg_sheet_factory"):
            self.assertNotIn(x, cam, f"🔴 sheet_config nạp {x} → vòng lặp import")


if __name__ == "__main__":
    unittest.main(verbosity=2)
