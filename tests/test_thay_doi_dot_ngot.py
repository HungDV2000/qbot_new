# -*- coding: utf-8 -*-
"""
Sheet tổng bị sửa ĐỘT NGỘT / sửa DỞ — bot phải an toàn.

Kịch bản thật: đang dán key thì bot đọc; chép dòng quên sửa key; gõ "2,5";
gõ "Không" vào cột Bật; một dòng sai giữa nhiều dòng đúng; tắt/xoá tài khoản khi bot
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


def _ten_loi(loi):
    return {t for t, _ in loi}


def _chu(loi):
    return "\n".join(m for _, m in loi)


class TestDuLieuSuaDo(unittest.TestCase):
    """Dòng sai chỉ bị BỎ RIÊNG — không ném lỗi chặn cả bảng."""

    def test_hop_le_thi_khong_loi(self):
        self.assertEqual(sc.kiem_tra_du_lieu(_bang()), [])

    def test_trung_api_key_thi_bo_CA_HAI_dong(self):
        loi = sc.kiem_tra_du_lieu(_bang(kh_b={"key_binance": K1}))
        self.assertEqual(_ten_loi(loi), {"kh_a", "kh_b"}, "không biết dòng nào đúng → bỏ cả hai")
        self.assertIn("ĐẶT LỆNH TRÙNG", _chu(loi))

    def test_trung_key_ma_secret_khac_thi_bao_DAN_NHAM(self):
        """Ca thật: q3trust và q2Bio cùng Key, khác Secret — khách chép nhầm Key."""
        loi = sc.kiem_tra_du_lieu(_bang(kh_b={"key_binance": K1}))
        self.assertIn("DÁN NHẦM", _chu(loi))
        self.assertIn("sub-account", _chu(loi))

    def test_trung_sheet_id_thi_bo_ca_hai(self):
        loi = sc.kiem_tra_du_lieu(_bang(kh_b={"spreadsheet_id": "SH_A"}))
        self.assertEqual(_ten_loi(loi), {"kh_a", "kh_b"})

    def test_key_dan_thieu_hoac_dinh_khoang_trang(self):
        for xau in ("abc123", "A" * 30 + " " + "A" * 30, "A" * 32 + "\n"):
            with self.subTest(xau=xau[:10]):
                loi = sc.kiem_tra_du_lieu(_bang(kh_a={"key_binance": xau}))
                self.assertEqual(_ten_loi(loi), {"kh_a"})
                self.assertIn("dán thiếu", _chu(loi))

    def test_dau_phay_thap_phan_kieu_Viet(self):
        b = _bang(kh_a={"default_sl_rate_layer_1": "2,5"})
        self.assertEqual(sc.kiem_tra_du_lieu(b), [])
        self.assertEqual(b["kh_a"]["default_sl_rate_layer_1"], "2.5")

    def test_so_sai_thi_bo_dong(self):
        for gt in ("abc", "150", "0", "-2"):
            with self.subTest(gt=gt):
                loi = sc.kiem_tra_du_lieu(_bang(kh_a={"default_tp_rate_layer_1": gt}))
                self.assertEqual(_ten_loi(loi), {"kh_a"})

    def test_ten_cot(self):
        b = _bang(kh_a={"leg1_col": " d "})
        self.assertEqual(sc.kiem_tra_du_lieu(b), [])
        self.assertEqual(b["kh_a"]["leg1_col"], "D")
        self.assertEqual(_ten_loi(sc.kiem_tra_du_lieu(_bang(kh_a={"leg1_col": "D1"}))), {"kh_a"})

    def test_co_khong_tieng_Viet(self):
        b = _bang(kh_a={"allow_dca": "Có", "default_allow_order": "không"})
        self.assertEqual(sc.kiem_tra_du_lieu(b), [])
        self.assertEqual(b["kh_a"]["allow_dca"], "true")
        self.assertEqual(b["kh_a"]["default_allow_order"], "N")


class TestCotBat(unittest.TestCase):
    def test_Khong_la_TAT(self):
        """Lỗi cũ: gõ 'Không' bị hiểu là BẬT."""
        b, bo_qua = sc.loc_dang_bat({"a": {"__bat__": "Không"}, "b": {"__bat__": "Có"}, "c": {}})
        self.assertEqual(sorted(b), ["b", "c"])
        self.assertEqual(bo_qua, [])

    def test_gia_tri_la_thi_bo_rieng_dong_do(self):
        b, bo_qua = sc.loc_dang_bat({"a": {"__bat__": "tạm dừng"}, "b": {"__bat__": "Y"}})
        self.assertEqual(list(b), ["b"], "không đoán, nhưng dòng khác vẫn chạy")
        self.assertEqual(_ten_loi(bo_qua), {"a"})

    def test_nap_tu_bang_chay_du_moi_buoc(self):
        rows = [["PHIÊN BẢN", "3"],
                ["Tài khoản", "Bật", "API Key", "API Secret", "Sheet ID", "%SL"],
                ["kh_a", "Y", K1, S1, "SH_A", "2,5"],
                ["kh_b", "Không", K2, S2, "SH_B", "3"]]
        pb, bang, bo_qua = sc.nap_tu_bang(rows)
        self.assertEqual((pb, list(bang), bo_qua), ("3", ["kh_a"], []))
        self.assertEqual(bang["kh_a"]["default_sl_rate_layer_1"], "2.5")

    def test_MOT_dong_loi_KHONG_lam_dung_ca_bang(self):
        """Máy tự bật Y: một dòng sai không được chặn các tài khoản khác."""
        rows = [["PHIÊN BẢN", "3"],
                ["Tài khoản", "Bật", "API Key", "API Secret", "Sheet ID"],
                ["kh_a", "Y", K1, S1, "SH_A"],
                ["kh_b", "Y", "abc", S2, "SH_B"],          # key cụt
                ["kh_c", "tạm dừng", K2, S2, "SH_C"],      # Bật lạ
                ["kh_d", "Y", K1, S2, "SH_D"]]             # trùng key kh_a
        _, bang, bo_qua = sc.nap_tu_bang(rows)
        self.assertEqual(list(bang), [], "kh_a trùng key với kh_d → cả hai bị bỏ")
        self.assertEqual(_ten_loi(bo_qua), {"kh_a", "kh_b", "kh_c", "kh_d"})
        rows[5][2] = "E" * 64                              # sửa kh_d
        _, bang, bo_qua = sc.nap_tu_bang(rows)
        self.assertEqual(sorted(bang), ["kh_a", "kh_d"])
        self.assertEqual(_ten_loi(bo_qua), {"kh_b", "kh_c"})

    def test_khong_con_tai_khoan_nao_Bat_thi_khong_nem(self):
        rows = [["PHIÊN BẢN", "3"], ["Tài khoản", "Bật", "API Key", "API Secret", "Sheet ID"],
                ["kh_a", "N", K1, S1, "SH_A"]]
        self.assertEqual(sc.nap_tu_bang(rows)[1:], ({}, []),
                         "tắt hết không phải lỗi — điều phối ngồi chờ tài khoản được Bật lại")


class TestDanhGiaKhiSheetSuaDotNgot(unittest.TestCase):
    """Không bao giờ tự sát vào một cấu hình hỏng."""

    def setUp(self):
        cw._key_hong.clear()

    def _chay(self, hop_le, bo_qua=(), thu_dang_nhap=True, goi=None):
        goi = [] if goi is None else goi
        with mock.patch.object(cw, "_thu_dang_nhap_binance", lambda k, s: goi.append(1) or thu_dang_nhap), \
             mock.patch.object(cw, "_canh_bao", lambda *a, **k: None):
            return cw.danh_gia("kh_a", _bang()["kh_a"], hop_le, list(bo_qua))

    def test_du_lieu_hong_thi_GIU_NGUYEN(self):
        self.assertEqual(self._chay({}, [("kh_a", "trùng key")])[0], "giu_loi")

    def test_tai_khoan_bi_xoa_hoac_tat(self):
        self.assertEqual(self._chay({"kh_b": _bang()["kh_b"]})[0], "tat")

    def test_key_moi_khong_dang_nhap_duoc_thi_GIU_NGUYEN(self):
        kq, ly_do = self._chay(_bang(kh_a={"key_binance": "E" * 64}), thu_dang_nhap=False)
        self.assertEqual(kq, "giu_loi")
        self.assertIn("KHÔNG đăng nhập được Binance", ly_do)

    def test_key_moi_dang_nhap_duoc_thi_nap(self):
        self.assertEqual(self._chay(_bang(kh_a={"key_binance": "E" * 64}))[0], "nap_lai")

    def test_dong_cua_minh_khong_doi_thi_KHONG_khoi_dong_lai(self):
        """Đổi key kh_b → kh_a (dòng y nguyên) phải chạy tiếp, không khởi động lại."""
        goi = []
        kq = self._chay(_bang(kh_b={"key_binance": "E" * 64}), goi=goi)
        self.assertEqual(kq[0], "khong_doi")
        self.assertEqual(goi, [])

    def test_key_khong_doi_thi_KHONG_goi_Binance(self):
        goi = []
        self.assertEqual(self._chay(_bang(kh_a={"default_sl_rate_layer_1": "3"}), goi=goi)[0], "nap_lai")
        self.assertEqual(goi, [], "đổi %SL mà cũng gọi Binance là thừa")

    def test_B1_la_cong_thuc_tu_doi_KHONG_lam_khoi_dong_lai(self):
        """Bản cũ dò bằng B1 → B1 = NOW() làm bot khởi động lại liên tục. Nay so nội dung."""
        for _ in range(3):
            self.assertEqual(self._chay(_bang())[0], "khong_doi")


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
