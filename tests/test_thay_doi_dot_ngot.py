# -*- coding: utf-8 -*-
"""
Sheet tổng bị sửa ĐỘT NGỘT / sửa DỞ — bot phải an toàn.

Kịch bản thật: đang dán key thì bot đọc; chép dòng quên sửa key; gõ "2,5";
gõ "Không" vào cột Bật; ô B1 là công thức NOW(); tắt/xoá tài khoản khi bot
đang chạy. Chạy offline, không mạng.
"""
import os, sys, types, unittest
from unittest import mock

QBOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, QBOT)
import sheet_config as sc
import config_watcher as cw

K1, S1 = "A" * 64, "B" * 64
K2, S2 = "C" * 64, "D" * 64


def _bang(**them):
    b = {"kh_a": {"__ten__": "kh_a", "key_binance": K1, "secret_binance": S1, "spreadsheet_id": "SH_A"},
         "kh_b": {"__ten__": "kh_b", "key_binance": K2, "secret_binance": S2, "spreadsheet_id": "SH_B"}}
    for ten, muc in them.items():
        b[ten].update(muc)
    return b


class TestDuLieuSuaDo(unittest.TestCase):
    def test_hop_le_thi_qua(self):
        sc.kiem_tra_du_lieu(_bang())

    def test_trung_api_key_giua_hai_tai_khoan_thi_DUNG(self):
        with self.assertRaises(sc.LoiSheetCauHinh) as e:
            sc.kiem_tra_du_lieu(_bang(kh_b={"key_binance": K1}))
        self.assertIn("ĐẶT LỆNH TRÙNG", str(e.exception))

    def test_trung_sheet_id_thi_DUNG(self):
        with self.assertRaises(sc.LoiSheetCauHinh):
            sc.kiem_tra_du_lieu(_bang(kh_b={"spreadsheet_id": "SH_A"}))

    def test_key_dan_thieu_hoac_dinh_khoang_trang(self):
        for xau in ("abc123", "A" * 30 + " " + "A" * 30, "A" * 32 + "\n"):
            with self.subTest(xau=xau[:10]):
                with self.assertRaises(sc.LoiSheetCauHinh) as e:
                    sc.kiem_tra_du_lieu(_bang(kh_a={"key_binance": xau}))
                self.assertIn("dán thiếu", str(e.exception))

    def test_dau_phay_thap_phan_kieu_Viet(self):
        b = _bang(kh_a={"default_sl_rate_layer_1": "2,5"})
        sc.kiem_tra_du_lieu(b)
        self.assertEqual(b["kh_a"]["default_sl_rate_layer_1"], "2.5")

    def test_so_sai_thi_DUNG(self):
        for gt in ("abc", "150", "0", "-2"):
            with self.subTest(gt=gt):
                with self.assertRaises(sc.LoiSheetCauHinh):
                    sc.kiem_tra_du_lieu(_bang(kh_a={"default_tp_rate_layer_1": gt}))

    def test_ten_cot(self):
        b = _bang(kh_a={"leg1_col": " d "})
        sc.kiem_tra_du_lieu(b)
        self.assertEqual(b["kh_a"]["leg1_col"], "D")
        with self.assertRaises(sc.LoiSheetCauHinh):
            sc.kiem_tra_du_lieu(_bang(kh_a={"leg1_col": "D1"}))

    def test_co_khong_tieng_Viet(self):
        b = _bang(kh_a={"allow_dca": "Có", "default_allow_order": "không"})
        sc.kiem_tra_du_lieu(b)
        self.assertEqual(b["kh_a"]["allow_dca"], "true")
        self.assertEqual(b["kh_a"]["default_allow_order"], "N")


class TestCotBat(unittest.TestCase):
    def test_Khong_la_TAT(self):
        """Lỗi cũ: gõ 'Không' bị hiểu là BẬT."""
        b = sc.loc_dang_bat({"a": {"__bat__": "Không"}, "b": {"__bat__": "Có"}, "c": {}})
        self.assertEqual(sorted(b), ["b", "c"])

    def test_gia_tri_la_thi_DUNG_khong_doan(self):
        with self.assertRaises(sc.LoiSheetCauHinh):
            sc.loc_dang_bat({"a": {"__bat__": "tạm dừng"}})

    def test_nap_tu_bang_chay_du_moi_buoc(self):
        rows = [["PHIÊN BẢN", "3"],
                ["Tài khoản", "Bật", "API Key", "API Secret", "Sheet ID", "%SL"],
                ["kh_a", "Y", K1, S1, "SH_A", "2,5"],
                ["kh_b", "Không", K2, S2, "SH_B", "3"]]
        pb, bang = sc.nap_tu_bang(rows)
        self.assertEqual((pb, list(bang)), ("3", ["kh_a"]))
        self.assertEqual(bang["kh_a"]["default_sl_rate_layer_1"], "2.5")


class TestXacMinhTruocKhiNap(unittest.TestCase):
    """Không bao giờ tự sát vào một cấu hình hỏng."""

    def _chay(self, nap, thu_dang_nhap=True, ten="kh_a", key=K1, sec=S1):
        with mock.patch.object(sc, "nap", nap), \
             mock.patch.object(cw, "_thu_dang_nhap_binance", lambda k, s: thu_dang_nhap), \
             mock.patch.object(cw, "_canh_bao", lambda *a, **k: None):
            return cw.xac_minh_cau_hinh_moi("BOT", "SID", ten, key, sec)

    def test_loi_mang_thi_thu_lai(self):
        def no(*a): raise sc.LoiDocSheet("503")
        self.assertEqual(self._chay(no)[0], "thu_lai")

    def test_du_lieu_hong_thi_GIU_NGUYEN(self):
        def no(*a): raise sc.LoiSheetCauHinh("trùng key")
        self.assertEqual(self._chay(no)[0], "giu_nguyen")

    def test_tai_khoan_bi_xoa_hoac_tat(self):
        self.assertEqual(self._chay(lambda *a: ("8", {"kh_b": _bang()["kh_b"]}))[0], "bi_tat")

    def test_key_moi_khong_dang_nhap_duoc_thi_GIU_NGUYEN(self):
        moi = _bang(kh_a={"key_binance": "E" * 64})
        kq, ly_do = self._chay(lambda *a: ("8", moi), thu_dang_nhap=False)
        self.assertEqual(kq, "giu_nguyen")
        self.assertIn("KHÔNG đăng nhập được Binance", ly_do)

    def test_key_moi_dang_nhap_duoc_thi_nap(self):
        moi = _bang(kh_a={"key_binance": "E" * 64})
        self.assertEqual(self._chay(lambda *a: ("8", moi), thu_dang_nhap=True)[0], "nap_lai")

    def test_dong_cua_minh_khong_doi_thi_KHONG_khoi_dong_lai(self):
        """Đổi key kh_b → kh_a (dòng y nguyên) phải chạy tiếp, không khởi động lại."""
        moi = _bang(kh_b={"key_binance": "E" * 64})
        goi = []
        with mock.patch.object(sc, "nap", lambda *a: ("8", moi)), \
             mock.patch.object(cw, "_thu_dang_nhap_binance", lambda k, s: goi.append(1) or True):
            kq = cw.xac_minh_cau_hinh_moi("BOT", "SID", "kh_a", K1, S1, _bang()["kh_a"])
        self.assertEqual(kq[0], "khong_doi")
        self.assertEqual(goi, [])

    def test_key_khong_doi_thi_KHONG_goi_Binance(self):
        goi = []
        with mock.patch.object(sc, "nap", lambda *a: ("8", _bang())), \
             mock.patch.object(cw, "_thu_dang_nhap_binance", lambda k, s: goi.append(1) or True):
            self.assertEqual(cw.xac_minh_cau_hinh_moi("BOT", "SID", "kh_a", K1, S1)[0], "nap_lai")
        self.assertEqual(goi, [], "đổi %SL mà cũng gọi Binance là thừa")


class _CstGia(types.ModuleType):
    def __init__(self):
        super().__init__("cst")
        self.nap_tu_sheet, self.bot_id, self.config_spreadsheet_id = True, "BOT", "SID"
        self.account, self.key_binance, self.secret_binance = "kh_a", K1, S1
        self.account_name, self.chat_id, self.bot_token = "kh_a", "", ""
        self.config = mock.Mock(getint=lambda *a, **k: 300)
        self.nha_khoa = lambda: None


class TestApDung(unittest.TestCase):
    def setUp(self):
        self._cu = sys.modules.get("cst")
        sys.modules["cst"] = _CstGia()
        cw.khoi_tao("7")
        self.nap_lai = []
        self.p = [mock.patch.object(cw, "co_thay_doi", lambda *a: (True, "8")),
                  mock.patch.object(cw, "_canh_bao", lambda *a, **k: None),
                  mock.patch.object(cw, "khoi_dong_lai", lambda *a, **k: self.nap_lai.append(a))]
        for x in self.p: x.start()

    def tearDown(self):
        for x in self.p: x.stop()
        if self._cu is None: sys.modules.pop("cst", None)
        else: sys.modules["cst"] = self._cu

    def test_vua_khoi_dong_thi_CHUA_nap_chong_bao_B1_cong_thuc(self):
        with mock.patch.object(cw, "_bat_dau", __import__("time").time()), \
             mock.patch.object(cw, "xac_minh_cau_hinh_moi", lambda *a: ("nap_lai", "8")):
            cw.kiem_tra_va_ap_dung()
        self.assertEqual(self.nap_lai, [])

    def test_du_lieu_hong_thi_GIU_va_ghi_nho_phien_ban_loi(self):
        with mock.patch.object(cw, "_bat_dau", 0), \
             mock.patch.object(cw, "xac_minh_cau_hinh_moi", lambda *a: ("giu_nguyen", "x")):
            cw.kiem_tra_va_ap_dung()
        self.assertEqual(self.nap_lai, [])
        self.assertEqual(cw._phien_ban_loi, "8")

    def test_hop_le_thi_nap(self):
        with mock.patch.object(cw, "_bat_dau", 0), \
             mock.patch.object(cw, "xac_minh_cau_hinh_moi", lambda *a: ("nap_lai", "8")):
            cw.kiem_tra_va_ap_dung()
        self.assertEqual(len(self.nap_lai), 1)

    def test_phien_ban_da_biet_hong_thi_khong_doc_lai(self):
        cw.khoi_tao("7"); cw._phien_ban_loi = "8"
        self.p[0].stop()
        cw._lan_kiem_cuoi = 0
        with mock.patch.object(sc, "doc_o_phien_ban", lambda *a: "8"):
            self.assertEqual(cw.co_thay_doi("BOT", "SID", 0), (False, None))
        self.p[0].start()


class TestMaThoatChoDieuPhoi(unittest.TestCase):
    def tearDown(self):
        os.environ.pop("QBOT_SUPERVISED", None)

    def test_co_dieu_phoi_thi_thoat_MA_NAP_LAI_khong_tu_de(self):
        os.environ["QBOT_SUPERVISED"] = "1"
        de = []
        with mock.patch.object(cw.subprocess, "Popen", lambda *a, **k: de.append(1)):
            with self.assertRaises(SystemExit) as e:
                cw.khoi_dong_lai("x", nha_khoa=lambda: None)
        self.assertEqual(e.exception.code, cw.MA_NAP_LAI)
        self.assertEqual(de, [], "có điều phối mà vẫn tự đẻ tiến trình → điều phối mất dấu")

    def test_bi_tat(self):
        with mock.patch.object(cw, "_canh_bao", lambda *a, **k: None):
            os.environ["QBOT_SUPERVISED"] = "1"
            with self.assertRaises(SystemExit) as e:
                cw.dung_vi_bi_tat()
            self.assertEqual(e.exception.code, cw.MA_BI_TAT)
            os.environ.pop("QBOT_SUPERVISED")
            with self.assertRaises(SystemExit) as e:
                cw.dung_vi_bi_tat()
            self.assertEqual(e.exception.code, 0)

    def test_cst_va_watcher_dung_chung_ma(self):
        import io
        src = io.open(os.path.join(QBOT, "cst.py"), encoding="utf-8").read()
        self.assertIn("from config_watcher import MA_NAP_LAI, MA_BI_TAT", src)


class TestNgu(unittest.TestCase):
    def test_nghi_du_gio_va_do_nhieu_lan(self):
        dem = []
        ao = {"t": 1000.0}
        with mock.patch.object(cw.time, "time", lambda: ao["t"]), \
             mock.patch.object(cw.time, "sleep", lambda s: ao.__setitem__("t", ao["t"] + s)), \
             mock.patch.object(cw, "kiem_tra_va_ap_dung", lambda: dem.append(1)):
            cw.ngu(60)
        self.assertEqual(ao["t"], 1060.0)
        self.assertEqual(len(dem), 12, "nghỉ 60s chia đoạn 5s → dò 12 lần")

    def test_loi_do_khong_lam_chet_bot(self):
        def no(): raise RuntimeError("x")
        with mock.patch.object(cw.time, "sleep", lambda s: None), \
             mock.patch.object(cw, "kiem_tra_va_ap_dung", no):
            cw.ngu(0.01)

    def test_import_o_CAP_MODULE(self):
        """Lỗi đã gặp: chỉ có `import config_watcher` THỤT LỀ trong khối cũ, xoá
        khối đi là mất import → bot chết NameError ngay sau vòng quét đầu."""
        import ast, io
        for f in ("hd_order_multi.py", "hd_update_cho_va_khop.py", "hd_update_all.py",
                  "hd_alert_possition_and_open_order.py", "hd_cancel_orders_schedule.py",
                  "hd_cancel_selective.py"):
            cay = ast.parse(io.open(os.path.join(QBOT, f), encoding="utf-8").read())
            co = any(isinstance(n, ast.Import) and any(a.name == "config_watcher" for a in n.names)
                     for n in cay.body)
            with self.subTest(bot=f):
                self.assertTrue(co, f"🔴 {f}: thiếu `import config_watcher` ở cấp module")

    def test_ca_6_bot_deu_noi(self):
        import io
        for f in ("hd_order_multi.py", "hd_update_cho_va_khop.py", "hd_update_all.py",
                  "hd_alert_possition_and_open_order.py", "hd_cancel_orders_schedule.py",
                  "hd_cancel_selective.py"):
            src = io.open(os.path.join(QBOT, f), encoding="utf-8").read()
            with self.subTest(bot=f):
                # ngu() hoặc ngu_theo_nhip() đều dò cấu hình trong lúc nghỉ;
                # time.sleep thẳng thì KHÔNG → bot chạy key cũ mãi.
                self.assertTrue("config_watcher.ngu(" in src or "config_watcher.ngu_theo_nhip(" in src,
                                f"🔴 {f} không dò cấu hình → chạy KEY CŨ mãi sau khi đổi trên sheet")
                self.assertNotIn("time.sleep(", src.split("while True:")[-1],
                                 f"🔴 {f} nghỉ bằng time.sleep ở vòng lặp chính → không dò được cấu hình")


if __name__ == "__main__":
    unittest.main(verbosity=2)
