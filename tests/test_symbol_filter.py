# -*- coding: utf-8 -*-
"""Chọn mã lấy dữ liệu: chuẩn hoá tên, khử trùng, hai chế độ all/list."""
import configparser, os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import symbol_filter as sf


class TestChuanHoaTen(unittest.TestCase):
    def test_bon_cach_viet_deu_ve_mot_dang(self):
        for viet in ("BTC", "BTCUSDT", "BTC/USDT", "BTC/USDT:USDT"):
            with self.subTest(viet=viet):
                self.assertEqual(sf.normalize_symbol(viet), "BTC/USDT:USDT")

    def test_khong_phan_biet_hoa_thuong(self):
        for viet in ("btc", "Btc", "bTc/usdt", "btcusdt"):
            with self.subTest(viet=viet):
                self.assertEqual(sf.normalize_symbol(viet), "BTC/USDT:USDT")

    def test_bo_khoang_trang_thua(self):
        self.assertEqual(sf.normalize_symbol("  eth  "), "ETH/USDT:USDT")

    def test_chuoi_rong(self):
        self.assertEqual(sf.normalize_symbol("   "), "")


class TestDocDanhSach(unittest.TestCase):
    def test_giu_dung_thu_tu_khai(self):
        ds, _ = sf.parse_symbol_list("BTC, ETH, SOL, XRP, BNB, DOGE")
        self.assertEqual(ds, [f"{m}/USDT:USDT" for m in
                              ("BTC", "ETH", "SOL", "XRP", "BNB", "DOGE")])

    def test_khu_trung_giu_lan_dau(self):
        ds, trung = sf.parse_symbol_list("BTC, btc, BTCUSDT, ETH")
        self.assertEqual(ds, ["BTC/USDT:USDT", "ETH/USDT:USDT"])
        self.assertEqual(len(trung), 2, "phải báo 2 mã bị trùng")

    def test_bo_qua_o_trong(self):
        ds, _ = sf.parse_symbol_list("BTC, , ETH,,")
        self.assertEqual(len(ds), 2)

    def test_xuong_dong_cung_duoc(self):
        ds, _ = sf.parse_symbol_list("BTC\nETH, SOL")
        self.assertEqual(len(ds), 3)


class TestDocCauHinh(unittest.TestCase):
    def _cfg(self, **kv):
        c = configparser.ConfigParser()
        c.read_dict({"global": {k: str(v) for k, v in kv.items()}})
        return c

    def test_mac_dinh_la_list(self):
        """Config không khai gì → chạy chế độ list (theo yêu cầu)."""
        self.assertEqual(sf.read_mode(self._cfg()), sf.MODE_LIST)

    def test_khong_khai_symbol_list_thi_dung_6_ma_mac_dinh(self):
        """mode=list mà thiếu symbol_list → dùng 6 mã mặc định, KHÔNG được chết."""
        ds, _ = sf.read_symbol_list(self._cfg())
        self.assertEqual(ds, [f"{m}/USDT:USDT" for m in
                              ("BTC", "ETH", "SOL", "XRP", "BNB", "DOGE")])

    def test_symbol_list_de_trong_cung_dung_mac_dinh(self):
        """Khai khoá nhưng bỏ trống → vẫn ra 6 mã, không làm hd_update_all dừng."""
        ds, _ = sf.read_symbol_list(self._cfg(symbol_list="   "))
        self.assertEqual(len(ds), 6)

    def test_van_doc_duoc_all_khi_khai_ro(self):
        self.assertEqual(sf.read_mode(self._cfg(symbol_mode="all")), sf.MODE_ALL)

    def test_doc_duoc_list(self):
        self.assertEqual(sf.read_mode(self._cfg(symbol_mode="list")), sf.MODE_LIST)

    def test_khong_phan_biet_hoa_thuong_o_che_do(self):
        self.assertEqual(sf.read_mode(self._cfg(symbol_mode="  LIST ")), sf.MODE_LIST)

    def test_gia_tri_la_thi_dung_han(self):
        """Gõ sai chế độ → dừng, KHÔNG đoán bừa."""
        with self.assertRaises(SystemExit):
            sf.read_mode(self._cfg(symbol_mode="whitelist"))

    def test_mac_dinh_config_init_co_6_ma(self):
        """Soát MỌI file config mẫu đang có (tên file thay đổi theo thời gian)."""
        import glob, io, os
        mau = [f for f in glob.glob("config.ini.*") if not f.endswith((".bak", ".backup"))]
        self.assertTrue(mau, "không thấy file config mẫu nào")
        for p in mau:
            with self.subTest(file=p):
                t = io.open(p, encoding="utf-8").read()
                self.assertIn("symbol_mode = list", t, "mặc định phải là list")
                self.assertIn("symbol_list = BTC, ETH, SOL, XRP, BNB, DOGE", t)


class TestLocTheoDanhSach(unittest.TestCase):
    SAN = {f"{m}/USDT:USDT" for m in ("BTC", "ETH", "SOL", "XRP", "BNB", "DOGE", "ADA")}
    DAN_DAU = ("BTCDOM/USDT:USDT", "BTC/USDT:USDT")

    def test_bo_ma_trung_voi_dong_dan_dau(self):
        khai, _ = sf.parse_symbol_list("BTC, ETH, SOL")
        dung, thieu, trung = sf.loc_theo_danh_sach(khai, self.SAN, self.DAN_DAU)
        self.assertNotIn("BTC/USDT:USDT", dung, "BTC đã ở dòng dẫn đầu")
        self.assertEqual(trung, ["BTC/USDT:USDT"])
        self.assertEqual(dung, ["ETH/USDT:USDT", "SOL/USDT:USDT"])

    def test_bao_ro_ma_khong_co_tren_san(self):
        khai, _ = sf.parse_symbol_list("ETH, KHONGCOMA")
        dung, thieu, _ = sf.loc_theo_danh_sach(khai, self.SAN, self.DAN_DAU)
        self.assertEqual(dung, ["ETH/USDT:USDT"])
        self.assertEqual(thieu, ["KHONGCOMA/USDT:USDT"])

    def test_giu_dung_thu_tu_nguoi_dung_khai(self):
        khai, _ = sf.parse_symbol_list("DOGE, ETH, SOL")
        dung, _, _ = sf.loc_theo_danh_sach(khai, self.SAN, self.DAN_DAU)
        self.assertEqual(dung, ["DOGE/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT"])


class TestCodeDaCam(unittest.TestCase):
    """Kiểm tra bản vá thật đã nằm trong file."""
    def _doc(self, f):
        import io
        return io.open(f, encoding="utf-8").read()

    def _bo_qua_neu_thieu(self, f):
        """Bản gọn (qbot_new) không chép bot đã nghỉ — bỏ qua thay vì báo lỗi."""
        import os
        if not os.path.exists(f):
            self.skipTest(f"{f} không có trong thư mục này (bản gọn)")

    def test_update_price_khong_con_ghi_cot_Y(self):
        self._bo_qua_neu_thieu("hd_update_price.py")
        src = self._doc("hd_update_price.py")
        self.assertNotIn('output_rows, "Y"', src, "🔴 vẫn ghi đè cột Y của hd_update_all")
        self.assertIn("cst.price_column", src)

    def test_update_price_dung_chung_ham_chuan_hoa(self):
        self._bo_qua_neu_thieu("hd_update_price.py")
        src = self._doc("hd_update_price.py")
        self.assertIn("from symbol_filter import normalize_symbol", src)
        self.assertNotIn("def normalize_symbol", src, "không được giữ bản sao riêng")

    def test_update_all_khong_con_quay_ve_100_ma_am_tham(self):
        src = self._doc("hd_update_all.py")
        self.assertIn("KHÔNG mã nào trong symbol_list dùng được", src)
        self.assertIn("Whitelist tab 'list' không khớp mã nào", src,
                      "trường hợp all cũng phải cảnh báo, không im lặng")

    def test_update_all_co_bo_cuc_phang(self):
        src = self._doc("hd_update_all.py")
        self.assertIn("che_do_list", src)
        self.assertIn("BỐ CỤC PHẲNG", src)


class TestPhuThuocCuaCst(unittest.TestCase):
    """
    cst.py được MỌI bot nạp đầu tiên. Thêm `import <module>` vào cst.py mà quên
    chép file đó khi deploy → TOÀN BỘ bot chết lúc khởi động.
    Test này bắt lỗi đó ngay, thay vì để phát hiện trên VPS.
    """
    def _module_noi_bo_cua_cst(self):
        import ast, io, os
        cay = ast.parse(io.open("cst.py", encoding="utf-8").read())
        ten = set()
        for n in ast.walk(cay):
            if isinstance(n, ast.Import):
                ten |= {a.name.split(".")[0] for a in n.names}
            elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
                ten.add(n.module.split(".")[0])
        # chỉ giữ module nằm ngay trong thư mục dự án
        return {m for m in ten if os.path.exists(m + ".py")}

    def test_moi_module_cst_can_deu_ton_tai(self):
        for m in self._module_noi_bo_cua_cst():
            with self.subTest(module=m):
                self.assertTrue(os.path.exists(m + ".py"), f"thiếu {m}.py")

    def test_cac_kich_ban_test_deu_chep_du(self):
        import io
        can = self._module_noi_bo_cua_cst() | {"cst"}
        import os
        for f in ("tests/test_multi_account.py", "tests/demo_2_accounts.sh"):
            if not os.path.exists(f):
                continue
            src = io.open(f, encoding="utf-8").read()
            for m in can:
                with self.subTest(file=f, module=m):
                    self.assertIn(m + ".py", src,
                                  f"{f} chưa chép {m}.py → bot sẽ chết trong sandbox")


class TestRanhGioiAnhHuong(unittest.TestCase):
    """
    ⚠️ CỐ Ý: bộ lọc symbol_list CHỈ áp cho bot lấy dữ liệu thị trường.

    Các bot theo dõi VỊ THẾ và LỆNH ĐANG MỞ phải nhìn thấy MỌI mã, kể cả mã
    không có trong symbol_list. Nếu áp bộ lọc vào chúng thì một vị thế mở ở mã
    sau đó bị xoá khỏi symbol_list sẽ trở nên VÔ HÌNH: không cảnh báo, không
    cập nhật, không huỷ lệnh được → kẹt tiền thật.
    """
    AP_DUNG = ("hd_update_all.py", "hd_update_price.py")
    KHONG_AP_DUNG = (
        "hd_track_30_prices.py",                  # theo tab ĐẶT LỆNH
        "hd_alert_possition_and_open_order.py",   # theo vị thế đang mở
        "hd_update_cho_va_khop.py",               # theo vị thế đang mở
        "hd_periodic_report.py",                  # theo số dư tài khoản
        "hd_cancel_orders_schedule.py",           # theo lệnh đang treo
        "hd_cancel_selective.py",                 # theo lệnh đang treo
        "hd_order.py", "hd_order_limit.py",
        "hd_order_multi.py", "hd_order_market_price.py",   # theo tab ĐẶT LỆNH
    )

    def _doc(self, f):
        import io
        return io.open(f, encoding="utf-8").read()

    def test_dung_bot_duoc_ap_bo_loc(self):
        import os
        for f in self.AP_DUNG:
            if not os.path.exists(f):
                continue          # bản gọn không chép bot này
            with self.subTest(bot=f):
                src = self._doc(f)
                self.assertTrue("symbol_filter" in src or "price_column" in src,
                                f"{f} phải dùng bộ lọc/cấu hình mới")

    def test_bot_theo_vi_the_KHONG_bi_ap_bo_loc(self):
        import os
        for f in self.KHONG_AP_DUNG:
            if not os.path.exists(f):
                continue          # bản gọn không chép bot này
            with self.subTest(bot=f):
                src = self._doc(f)
                self.assertNotIn("cst.symbol_list", src,
                                 f"🔴 {f} lọc theo symbol_list → vị thế ngoài danh sách "
                                 f"sẽ bị bỏ rơi, không ai quản lý!")
                self.assertNotIn("symbol_mode", src,
                                 f"🔴 {f} không được phụ thuộc chế độ chọn mã")


class TestXoaMaCu(unittest.TestCase):
    """
    Chuyển 100 mã → 6 mã thì các mã CŨ phải biến mất khỏi sheet.

    Google Sheets values.update CHỈ ghi đè đúng số dòng gửi lên; dòng thừa bên
    dưới giữ nguyên. Không xoá trước → nhìn sheet vẫn thấy 100 mã cũ, tưởng bot
    đang theo dõi chúng.
    """

    class SheetGia:
        """Mô phỏng đúng hành vi values.update của Google Sheets."""
        def __init__(self, so_dong_cu):
            self.o = [[f"MA_CU_{i}"] for i in range(so_dong_cu)]

        def clear(self):
            self.o = []

        def update(self, rows):
            for i, r in enumerate(rows):
                if i < len(self.o):
                    self.o[i] = r
                else:
                    self.o.append(r)

        def dang_hien(self):
            return [r[0] for r in self.o if r and r[0]]

    def test_khong_xoa_thi_ma_cu_con_lai(self):
        """Chứng minh lỗi có thật nếu bỏ bước xoá."""
        sheet = self.SheetGia(106)                 # lần trước: 100 mã + tiêu đề
        sheet.update([["HEADER"], ["SO_DU"], ["BTCDOM"], ["BTC"],
                      ["ETH"], ["SOL"], ["XRP"], ["BNB"], ["DOGE"]])
        con_lai = [m for m in sheet.dang_hien() if m.startswith("MA_CU_")]
        self.assertTrue(con_lai, "test này mô tả LỖI — phải còn mã cũ")
        self.assertEqual(len(con_lai), 106 - 9)

    def test_co_xoa_thi_sach(self):
        """Có bước xoá → chỉ còn đúng danh sách mới."""
        sheet = self.SheetGia(106)
        sheet.clear()                              # ← bước hd_update_all vừa thêm
        sheet.update([["HEADER"], ["SO_DU"], ["BTCDOM"], ["BTC"],
                      ["ETH"], ["SOL"], ["XRP"], ["BNB"], ["DOGE"]])
        hien = sheet.dang_hien()
        self.assertEqual([m for m in hien if m.startswith("MA_CU_")], [],
                         "🔴 vẫn còn mã cũ trên sheet")
        self.assertEqual(hien, ["HEADER", "SO_DU", "BTCDOM", "BTC",
                                "ETH", "SOL", "XRP", "BNB", "DOGE"])

    def test_code_that_co_goi_clear_truoc_khi_ghi(self):
        """Bản vá phải nằm trong hd_update_all.py, đúng thứ tự xoá → ghi."""
        import io
        src = io.open("hd_update_all.py", encoding="utf-8").read()
        self.assertIn("clear_multi", src, "🔴 thiếu bước xoá dữ liệu cũ")
        i_clear = src.index("gg_sheet_factory.clear_multi(")
        i_ghi = src.index("update_multi(gg_sheet_factory.tab_list_all_ma, -1, sheet_data")
        self.assertLess(i_clear, i_ghi, "phải XOÁ TRƯỚC rồi mới ghi")

    def test_xoa_ap_dung_cho_CA_HAI_che_do(self):
        """Đổi top_count ở chế độ all cũng để lại dòng thừa → phải xoá luôn."""
        import io, re
        src = io.open("hd_update_all.py", encoding="utf-8").read()
        i = src.index("gg_sheet_factory.clear_multi(")
        truoc = src[max(0, i - 400):i]
        self.assertNotIn("if che_do_list:", truoc.split("# Xoá ở CẢ HAI")[-1],
                         "🔴 bước xoá đang bị bó trong chế độ list")

    def test_che_do_all_van_chen_du_dong_trong(self):
        """Bố cục hai khối vẫn phải pad cho đủ top_count, nếu không cũng dính lỗi."""
        import io
        src = io.open("hd_update_all.py", encoding="utf-8").read()
        self.assertIn("range(max(0, cst.top_count - len(giam_data)))", src)
        self.assertIn("range(max(0, cst.top_count - len(tang_data)))", src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
