# -*- coding: utf-8 -*-
"""
Theo dõi sheet tổng (so nội dung, KHÔNG cần đổi B1) và tự nạp lại / tắt / mở bot.

Chỗ nguy hiểm nhất: THỨ TỰ NHẢ KHOÁ. Mở tiến trình mới trước khi nhả khoá
→ hai bot cùng chạy → ĐẶT LỆNH TRÙNG.
"""
import os, shutil, sys, tempfile, types, unittest
from pathlib import Path
from unittest import mock

QBOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, QBOT)
import config_watcher as cw


K1, S1, K2 = "A" * 64, "B" * 64, "C" * 64


def muc(key=K1, sec=S1, sheet="SH_A", **them):
    d = {"__ten__": "kh_a", "key_binance": key, "secret_binance": sec, "spreadsheet_id": sheet}
    d.update(them)
    return d


class _TatCanhBao(unittest.TestCase):
    def setUp(self):
        cw._key_hong.clear()
        self.dang_nhap = []
        self.cho_dang_nhap = True
        self._p = [mock.patch.object(cw, "_canh_bao", lambda *a, **k: None),
                   mock.patch.object(cw, "_thu_dang_nhap_binance",
                                     lambda k, s: self.dang_nhap.append(k) or self.cho_dang_nhap)]
        for p in self._p:
            p.start()

    def tearDown(self):
        for p in self._p:
            p.stop()


class TestDanhGiaMotDong(_TatCanhBao):
    """So dòng trên bảng MỚI với cấu hình đang chạy — không cần ô B1."""

    def test_khong_doi(self):
        self.assertEqual(cw.danh_gia("kh_a", muc(), {"kh_a": muc()}, [])[0], "khong_doi")

    def test_cot_dieu_khien_khong_tinh_la_doi(self):
        moi = muc(); moi["__bat__"] = "Y"
        self.assertEqual(cw.danh_gia("kh_a", muc(), {"kh_a": moi}, [])[0], "khong_doi")

    def test_doi_tham_so_thi_nap_lai_khong_goi_Binance(self):
        kq, _ = cw.danh_gia("kh_a", muc(), {"kh_a": muc(default_sl_rate_layer_1="3")}, [])
        self.assertEqual(kq, "nap_lai")
        self.assertEqual(self.dang_nhap, [], "không đổi key thì không cần thử đăng nhập")

    def test_doi_key_dang_nhap_duoc_thi_nap_lai(self):
        self.assertEqual(cw.danh_gia("kh_a", muc(), {"kh_a": muc(key=K2)}, [])[0], "nap_lai")
        self.assertEqual(self.dang_nhap, [K2])

    def test_doi_key_KHONG_dang_nhap_duoc_thi_GIU(self):
        self.cho_dang_nhap = False
        kq, ct = cw.danh_gia("kh_a", muc(), {"kh_a": muc(key=K2)}, [])
        self.assertEqual(kq, "giu_loi")
        self.assertIn("KHÔNG đăng nhập được", ct)
        cw.danh_gia("kh_a", muc(), {"kh_a": muc(key=K2)}, [])
        self.assertEqual(self.dang_nhap, [K2], "key hỏng không được thử lại MỖI chu kỳ")

    def test_tat_hoac_xoa_dong(self):
        self.assertEqual(cw.danh_gia("kh_a", muc(), {}, [])[0], "tat")

    def test_dong_dang_chay_bi_sua_HONG_thi_GIU(self):
        kq, ct = cw.danh_gia("kh_a", muc(), {}, [("kh_a", "key dán thiếu?")])
        self.assertEqual(kq, "giu_loi", "🔴 dòng đang chạy bị sửa dở mà bot lại TẮT tài khoản")
        self.assertIn("dán thiếu", ct)

    def test_ten_khong_phan_biet_hoa_thuong(self):
        self.assertEqual(cw.danh_gia("kh_a", muc(), {"KH_A": muc()}, [])[0], "khong_doi")


class TestKeHoachDieuPhoi(_TatCanhBao):
    def _kh(self, dang_chay, hop_le, bo_qua=(), **kw):
        return cw.ke_hoach_dieu_phoi(dang_chay, hop_le, list(bo_qua), bay_gio=10_000, **kw)

    def test_tai_khoan_moi_Bat_thi_mo(self):
        self.assertEqual(self._kh({}, {"kh_a": muc()}), [("mo", "kh_a")])

    def test_Bat_N_thi_ra_lenh_tat(self):
        kh = self._kh({"kh_a": muc()}, {})
        self.assertEqual([v[:2] for v in kh], [("tat", "kh_a")])

    def test_MOT_dong_loi_KHONG_chan_dong_khac(self):
        kh = self._kh({}, {"kh_a": muc()}, [("kh_b", "API Key DÙNG CHUNG")])
        self.assertIn(("mo", "kh_a"), kh, "🔴 một dòng lỗi làm đứng cả hệ")
        self.assertTrue(any(v[0] == "canh_bao" and "kh_b" in v[1] for v in kh))
        self.assertFalse(any(v[:2] == ("mo", "kh_b") for v in kh))

    def test_dong_dang_chay_loi_thi_canh_bao_khong_tat(self):
        kh = self._kh({"kh_a": muc()}, {}, [("kh_a", "dán thiếu")])
        self.assertEqual([v[0] for v in kh], ["canh_bao"])

    def test_vua_mo_thi_CHUA_nap_lai(self):
        kh = self._kh({"kh_a": muc()}, {"kh_a": muc(default_sl_rate_layer_1="3")},
                      lan_mo_cuoi={"kh_a": 10_000 - 5})
        self.assertEqual(kh, [], "chống bật/tắt liên tục")

    def test_da_ra_lenh_thi_khong_ra_lai(self):
        kh = self._kh({"kh_a": muc()}, {}, da_ra_lenh={"kh_a": ("tat", 0)})
        self.assertEqual(kh, [])

    def test_chet_vi_loi_dong_chua_sua_thi_KHONG_mo_lai(self):
        self.assertEqual(self._kh({}, {"kh_a": muc()}, chet={"kh_a": muc()}), [])

    def test_chet_vi_loi_dong_da_sua_thi_mo_lai(self):
        kh = self._kh({}, {"kh_a": muc(key=K2)}, chet={"kh_a": muc()})
        self.assertEqual(kh, [("mo", "kh_a")])

    def test_doi_key_dang_nhap_duoc_thi_nap_lai(self):
        kh = self._kh({"kh_a": muc()}, {"kh_a": muc(key=K2)})
        self.assertEqual([v[:2] for v in kh], [("nap_lai", "kh_a")])


class _CstGia(types.ModuleType):
    def __init__(self, thu_muc, bang=None):
        super().__init__("cst")
        self.nap_tu_sheet, self.bot_id, self.config_spreadsheet_id = True, "BOT", "SID"
        self.account = "kh_a"
        self.account_name, self.chat_id, self.bot_token = "kh_a", "", ""
        self.config = mock.Mock(getint=lambda *a, **k: 60)
        self._bang_tk = bang if bang is not None else {"kh_a": muc()}
        self.nha_khoa = lambda: None
        self._thu_muc = Path(thu_muc)

    def account_dir(self, base):
        p = self._thu_muc / base / self.account
        p.mkdir(parents=True, exist_ok=True)
        return p


class _MoiTruong(unittest.TestCase):
    giam_sat = True

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="qbot_cw_")
        self._cwd = os.getcwd()
        os.chdir(self.tmp)
        self._cst = sys.modules.get("cst")
        sys.modules["cst"] = _CstGia(self.tmp)
        self._argv = sys.argv[:]
        sys.argv = ["hd_thu.py"]
        self._env = os.environ.get("QBOT_SUPERVISED")
        if self.giam_sat:
            os.environ["QBOT_SUPERVISED"] = "1"
        else:
            os.environ.pop("QBOT_SUPERVISED", None)
        self.doc_sheet = []
        import sheet_config
        self._p = [mock.patch.object(cw, "_canh_bao", lambda *a, **k: None),
                   mock.patch.object(sheet_config, "nap", lambda *a: self.doc_sheet.append(a) or self.bang)]
        for p in self._p:
            p.start()
        self.bang = ("", {"kh_a": muc()}, [])

    def tearDown(self):
        for p in self._p:
            p.stop()
        os.chdir(self._cwd)
        shutil.rmtree(self.tmp, ignore_errors=True)
        sys.argv = self._argv
        if self._cst is None:
            sys.modules.pop("cst", None)
        else:
            sys.modules["cst"] = self._cst
        if self._env is None:
            os.environ.pop("QBOT_SUPERVISED", None)
        else:
            os.environ["QBOT_SUPERVISED"] = self._env


class TestKenhLenhChaCon(_MoiTruong):
    """Có điều phối: con KHÔNG đọc Google, chỉ nhận lệnh qua file cục bộ."""

    def test_con_khong_doc_sheet(self):
        for _ in range(5):
            cw.kiem_tra_va_ap_dung()
        self.assertEqual(self.doc_sheet, [], "🔴 con tự đọc sheet → 6 bot × N tài khoản vượt hạn mức Google")

    def test_lenh_nap_lai_thi_thoat_MA_NAP_LAI(self):
        cw.gui_lenh("hd_thu", "kh_a", "nap_lai", "key đổi")
        with self.assertRaises(SystemExit) as e:
            cw.kiem_tra_va_ap_dung()
        self.assertEqual(e.exception.code, cw.MA_NAP_LAI)
        self.assertFalse(cw.duong_dan_lenh("hd_thu", "kh_a").exists(), "lệnh làm xong phải xoá")

    def test_lenh_tat_thi_thoat_MA_BI_TAT(self):
        cw.gui_lenh("hd_thu", "kh_a", "tat")
        with self.assertRaises(SystemExit) as e:
            cw.kiem_tra_va_ap_dung()
        self.assertEqual(e.exception.code, cw.MA_BI_TAT)

    def test_ghi_lenh_nguyen_khoi(self):
        cw.gui_lenh("hd_thu", "kh_a", "tat", "x")
        self.assertEqual([p.name for p in Path("pids/kh_a").iterdir()], ["hd_thu.lenh"],
                         "không được để lại file tạm — con có thể đọc phải lệnh dở")

    def test_xoa_lenh_cu_truoc_khi_mo_con_moi(self):
        cw.gui_lenh("hd_thu", "kh_a", "tat")
        cw.xoa_lenh("hd_thu", "kh_a")
        cw.kiem_tra_va_ap_dung()          # không được thoát


class TestChayLe(_MoiTruong):
    """Không có điều phối: tiến trình tự đọc bảng mỗi config_reload_seconds."""
    giam_sat = False

    def setUp(self):
        super().setUp()
        cw._lan_kiem_cuoi = 0.0
        self._bd = cw._bat_dau
        cw._bat_dau = 0.0
        self.nap_lai = []
        self._p2 = mock.patch.object(cw, "khoi_dong_lai", lambda *a, **k: self.nap_lai.append(a))
        self._p2.start()

    def tearDown(self):
        self._p2.stop()
        cw._bat_dau = self._bd
        super().tearDown()

    def test_chua_toi_han_thi_KHONG_doc(self):
        import time as _t
        cw._lan_kiem_cuoi = _t.time()
        cw.kiem_tra_va_ap_dung()
        self.assertEqual(self.doc_sheet, [], "chưa tới hạn mà vẫn gọi mạng → phí hạn mức")

    def test_dong_doi_KHONG_can_doi_B1_van_nap_lai(self):
        self.bang = ("1", {"kh_a": muc(default_sl_rate_layer_1="3")}, [])   # B1 y nguyên
        cw.kiem_tra_va_ap_dung()
        self.assertEqual(len(self.nap_lai), 1)

    def test_dong_khong_doi_thi_chay_tiep(self):
        cw.kiem_tra_va_ap_dung()
        self.assertEqual(self.nap_lai, [])

    def test_dong_loi_thi_giu_nguyen(self):
        self.bang = ("", {}, [("kh_a", "dán thiếu")])
        cw.kiem_tra_va_ap_dung()
        self.assertEqual(self.nap_lai, [])

    def test_loi_mang_thi_giu_nguyen(self):
        import sheet_config
        def no(*a): raise sheet_config.LoiDocSheet("503")
        with mock.patch.object(sheet_config, "nap", no):
            cw.kiem_tra_va_ap_dung()
        self.assertEqual(self.nap_lai, [])

    def test_vua_khoi_dong_thi_chua_nap(self):
        import time as _t
        cw._bat_dau = _t.time()
        self.bang = ("", {"kh_a": muc(default_sl_rate_layer_1="3")}, [])
        cw.kiem_tra_va_ap_dung()
        self.assertEqual(self.nap_lai, [], "chống bật/tắt liên tục")


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
