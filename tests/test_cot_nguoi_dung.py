"""
Test cot_nguoi_dung.can_chinh — cột J–P (tick xoá lệnh, SL/TP) phải đi THEO MÃ
khi hd_update_cho_va_khop ghi lại A–I với thứ tự dòng khác.

    python3 tests/test_cot_nguoi_dung.py
"""
import os, sys, unittest

QBOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, QBOT)
import cot_nguoi_dung as C


def ai(ma, side="LONG"):
    return [ma, side, "N", "Y", 100.0, 10, "N", "N", 0]


def ap(ma, side="LONG", jp=("", "", "", "", "", "", "")):
    return ai(ma, side) + list(jp)


TRONG = ["", "", "", "", "", "", ""]


class TestCanChinh(unittest.TestCase):
    def test_khong_doi_thu_tu_thi_khong_ghi(self):
        cu = [ap("BTC/USDT", jp=("", "", "", "", 95, 104, "Y"))]
        _, co_doi, _ = C.can_chinh(cu, [ai("BTC/USDT")], dien_goi_y=False)
        self.assertFalse(co_doi)

    def test_dong_xe_dich_thi_JP_di_theo_ma(self):
        cu = [ap("BTC/USDT", jp=(True, "", "", "", 95, 104, "Y")), ap("ETH/USDT", "SHORT")]
        khoi, co_doi, so = C.can_chinh(cu, [ai("ETH/USDT", "SHORT"), ai("BTC/USDT")], dien_goi_y=False)
        self.assertTrue(co_doi)
        self.assertEqual(khoi[0], TRONG, "🔴 tick/SL của BTC ở lại cho ETH")
        self.assertEqual(khoi[1], [True, "", "", "", 95, 104, "Y"])
        self.assertEqual(so, 1)

    def test_ma_roi_bang_thi_xoa_JP_cua_no(self):
        cu = [ap("BTC/USDT", jp=("TRUE", "", "", "", 95, 104, "Y"))]
        khoi, co_doi, _ = C.can_chinh(cu, [], dien_goi_y=False)
        self.assertEqual(khoi, [TRONG], "tick mồ côi sẽ rơi vào mã khác đổ vào dòng này sau")
        self.assertTrue(co_doi)

    def test_cong_thuc_dung_yen_khong_doi(self):
        cu = [ap("BTC/USDT", jp=("", "", "", "", "=E4*0.98", "", "")), ap("ETH/USDT", "SHORT")]
        khoi, _, _ = C.can_chinh(cu, [ai("ETH/USDT", "SHORT"), ai("BTC/USDT")], dien_goi_y=False)
        self.assertEqual(khoi[0][4], "=E4*0.98", "công thức phải đứng yên tại dòng")
        self.assertEqual(khoi[1][4], "", "công thức không được dời sang dòng khác")

    def test_dong_cu_khong_co_ma_KHONG_trao_JP_cho_ma_moi(self):
        """🔴 Lỗi thật 09/2026: dòng cũ A trống còn N/O/P = 5008.78/5264.33/N (của mã
        đã đi) → ETH mở vị thế đổ vào dòng đó và NHẬN LUÔN giá SL/TP của mã cũ."""
        cu = [["", "", "", "", "", "", "", "", "", "", "", "", "", 5008.78, 5264.33, "N"]]
        khoi, co_doi, _ = C.can_chinh(cu, [ai("ETH/USDT")], [["2400", "2600", "N"]], True)
        self.assertEqual(khoi[0], ["", "", "", "", "2400", "2600", "N"],
                         "mã mới phải nhận gợi ý của CHÍNH NÓ, không nhận số mồ côi")
        self.assertTrue(co_doi)

    def test_dong_cu_khong_co_ma_tick_mo_coi_khong_roi_vao_ma_moi(self):
        cu = [["", "", "", "", "", "", "", "", "", "TRUE", "", "", "", "", "", ""]]
        khoi, _, _ = C.can_chinh(cu, [ai("BTC/USDT")], dien_goi_y=False)
        self.assertEqual(khoi[0], TRONG, "tick xoá lệnh mồ côi sẽ xoá nhầm lệnh BTC")

    def test_dong_cu_khong_co_ma_va_dong_moi_cung_trong_thi_giu_tai_cho(self):
        """Không có mã mới đổ vào → không có lý do xoá số người dùng."""
        cu = [ap("BTC/USDT"), ["", "", "", "", "", "", "", "", "", "", "", "", "", 95, 104, "Y"]]
        khoi, _, _ = C.can_chinh(cu, [ai("BTC/USDT")], dien_goi_y=False)
        self.assertEqual(khoi[1][4:], [95, 104, "Y"])

    def test_dien_goi_y_chi_vao_o_trong(self):
        cu = [ap("BTC/USDT", jp=("", "", "", "", 95, "", ""))]
        khoi, _, _ = C.can_chinh(cu, [ai("BTC/USDT")], [["98", "103", "N"]], True)
        self.assertEqual(khoi[0][4:], [95, "103", "N"])

    def test_cung_ma_hai_dong_van_phan_biet(self):
        cu = [ap("BTC/USDT", jp=("", "", "", "", 95, "", "")),
              ap("BTC/USDT", jp=("", "", "", "", 90, "", ""))]
        khoi, co_doi, _ = C.can_chinh(cu, [ai("BTC/USDT"), ai("BTC/USDT")], dien_goi_y=False)
        self.assertFalse(co_doi)
        self.assertEqual([khoi[0][4], khoi[1][4]], [95, 90])

    def test_khoa_khong_phan_biet_hoa_thuong_khoang_trang(self):
        cu = [ap(" btc/usdt ", jp=("", "", "", "", 95, "", ""))]
        khoi, _, _ = C.can_chinh(cu, [ai("BTC/USDT")], dien_goi_y=False)
        self.assertEqual(khoi[0][4], 95)


if __name__ == "__main__":
    unittest.main(verbosity=2)
