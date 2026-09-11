# -*- coding: utf-8 -*-
"""
Tự khởi động lại khi cấu hình trên sheet đổi.

Chỗ nguy hiểm nhất: THỨ TỰ NHẢ KHOÁ. Mở tiến trình mới trước khi nhả khoá
→ hai bot cùng chạy → ĐẶT LỆNH TRÙNG.
"""
import os, sys, unittest
from unittest import mock

QBOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, QBOT)
import config_watcher as cw


class TestDoThayDoi(unittest.TestCase):
    def setUp(self):
        cw._phien_ban_dau = None
        cw._lan_kiem_cuoi = 0.0

    def test_chua_khoi_tao_thi_khong_lam_gi(self):
        self.assertEqual(cw.co_thay_doi("BOT", "SHEET"), (False, None))

    def test_chua_toi_han_thi_KHONG_goi_mang(self):
        cw.khoi_tao("7")
        goi = []
        with mock.patch.object(cw, 'co_thay_doi', wraps=cw.co_thay_doi):
            import sheet_config
            with mock.patch.object(sheet_config, 'doc_o_phien_ban',
                                   lambda *a: goi.append(1)):
                doi, moi = cw.co_thay_doi("BOT", "SHEET", chu_ky_giay=9999)
        self.assertEqual((doi, moi), (False, None))
        self.assertEqual(goi, [], "chưa tới hạn mà vẫn gọi mạng → phí hạn mức")

    def test_phien_ban_giong_thi_khong_doi(self):
        cw.khoi_tao("7")
        import sheet_config
        with mock.patch.object(sheet_config, 'doc_o_phien_ban', lambda *a: "7"):
            self.assertEqual(cw.co_thay_doi("BOT", "SHEET", 0), (False, None))

    def test_phien_ban_khac_thi_bao_doi(self):
        cw.khoi_tao("7")
        import sheet_config
        with mock.patch.object(sheet_config, 'doc_o_phien_ban', lambda *a: "8"):
            doi, moi = cw.co_thay_doi("BOT", "SHEET", 0)
        self.assertTrue(doi)
        self.assertEqual(moi, "8")

    def test_doc_loi_thi_KHONG_lam_bot_chet(self):
        """Dò thay đổi thất bại chỉ là bỏ qua — bot chỉ dừng khi NẠP cấu hình lỗi."""
        cw.khoi_tao("7")
        import sheet_config
        def no(*a): raise RuntimeError("mạng lỗi")
        with mock.patch.object(sheet_config, 'doc_o_phien_ban', no):
            self.assertEqual(cw.co_thay_doi("BOT", "SHEET", 0), (False, None))


class TestThuTuNhaKhoa(unittest.TestCase):
    """🔴 Sai thứ tự = hai bot cùng chạy = đặt lệnh trùng."""

    def test_NHA_KHOA_TRUOC_roi_moi_mo_tien_trinh(self):
        thu_tu = []
        with mock.patch.object(cw.subprocess, 'Popen',
                               lambda *a, **k: thu_tu.append('mo_tien_trinh')):
            with self.assertRaises(SystemExit):
                cw.khoi_dong_lai("test", nha_khoa=lambda: thu_tu.append('nha_khoa'))
        self.assertEqual(thu_tu, ['nha_khoa', 'mo_tien_trinh'],
                         "🔴 phải NHẢ KHOÁ TRƯỚC khi mở tiến trình mới")

    def test_nha_khoa_loi_thi_KHONG_mo_tien_trinh(self):
        """Không nhả được khoá mà vẫn mở tiến trình mới = hai bot cùng chạy."""
        da_mo = []
        def no(): raise OSError("không xoá được file khoá")
        with mock.patch.object(cw.subprocess, 'Popen',
                               lambda *a, **k: da_mo.append(1)):
            with self.assertRaises(SystemExit):
                cw.khoi_dong_lai("test", nha_khoa=no)
        self.assertEqual(da_mo, [], "🔴 nhả khoá lỗi mà vẫn mở tiến trình mới!")

    def test_mo_tien_trinh_loi_thi_KHONG_thoat(self):
        """Mở tiến trình mới thất bại → bot cũ phải chạy tiếp, không được chết."""
        def no(*a, **k): raise OSError("hết bộ nhớ")
        with mock.patch.object(cw.subprocess, 'Popen', no):
            kq = cw.khoi_dong_lai("test", nha_khoa=lambda: None)
        self.assertIs(kq, False, "🔴 không mở được tiến trình mới mà vẫn thoát → bot chết hẳn")

    def test_truyen_cho_tien_trinh_moi_biet_phai_cho(self):
        env = {}
        def bat(*a, **k):
            env.update(k.get('env', {}))
        with mock.patch.object(cw.subprocess, 'Popen', bat):
            with self.assertRaises(SystemExit):
                cw.khoi_dong_lai("test", nha_khoa=lambda: None)
        self.assertEqual(env.get('QBOT_RESTART_DELAY'), '3',
                         "tiến trình mới phải chờ tiến trình cũ thoát hẳn")


class TestChoKhiVuaSinhRa(unittest.TestCase):
    def tearDown(self):
        os.environ.pop('QBOT_RESTART_DELAY', None)

    def test_khong_co_bien_thi_khong_cho(self):
        os.environ.pop('QBOT_RESTART_DELAY', None)
        ngu = []
        with mock.patch.object(cw.time, 'sleep', lambda s: ngu.append(s)):
            cw.cho_neu_vua_khoi_dong_lai()
        self.assertEqual(ngu, [])

    def test_co_bien_thi_cho_dung_so_giay(self):
        os.environ['QBOT_RESTART_DELAY'] = '3'
        ngu = []
        with mock.patch.object(cw.time, 'sleep', lambda s: ngu.append(s)):
            cw.cho_neu_vua_khoi_dong_lai()
        self.assertEqual(ngu, [3.0])
        self.assertNotIn('QBOT_RESTART_DELAY', os.environ, "phải xoá để lần sau không chờ lại")


class TestNoiVaoBot(unittest.TestCase):
    def test_hd_order_multi_kiem_tra_SAU_khi_quet_xong(self):
        """Không được cắt ngang lúc vừa vào lệnh mà chưa đặt cắt lỗ."""
        import io
        src = io.open(os.path.join(QBOT, "hd_order_multi.py"), encoding="utf-8").read()
        self.assertIn("config_watcher.ngu", src, "chưa nối bộ dò vào bot")
        i_quet = src.rindex("do_it()")
        i_do = src.index("config_watcher.ngu")
        self.assertLess(i_quet, i_do, "🔴 dò cấu hình phải nằm SAU do_it()")

    def test_cst_cho_truoc_khi_gianh_khoa(self):
        import io
        src = io.open(os.path.join(QBOT, "cst.py"), encoding="utf-8").read()
        i_cho = src.index("cho_neu_vua_khoi_dong_lai")
        i_khoa = src.rindex("acquire_single_instance_lock(_entry[:-3])")
        self.assertLess(i_cho, i_khoa, "🔴 phải CHỜ trước khi giành khoá")


if __name__ == "__main__":
    unittest.main(verbosity=2)
