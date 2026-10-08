"""
Test cot_nguoi_dung — bot CHỈ GHI A–I của tab "Chờ và khớp"; mỗi mã giữ nguyên dòng
nên J–P (của người dùng) đứng yên vẫn đúng mã. Kèm SL/TP mặc định trong bộ nhớ.

    python3 tests/test_cot_nguoi_dung.py
"""
import os, sys, unittest

QBOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, QBOT)
import cot_nguoi_dung as C


def ai(ma, side="LONG", d="Y", gia=100.0):
    return [ma, side, "N", d, gia, 10, "N", "N", 0]


def ap(ma, side="LONG", jp=("", "", "", "", "", "", ""), d="Y"):
    return ai(ma, side, d) + list(jp)


TRONG = [""] * 9


class TestGiuChoDong(unittest.TestCase):
    def test_ma_cu_giu_dung_dong_du_thu_tu_moi_khac(self):
        """BTC chờ khớp ở dòng 5 → khớp lệnh, thứ tự Binance đưa BTC lên đầu: vẫn ở dòng 5."""
        cu = [ap("ETH/USDT"), ap("BTC/USDT", d="N", jp=("", "", "", "", 95, 104, "Y"))]
        ra = C.xep_dong(cu, [ai("BTC/USDT"), ai("ETH/USDT")])
        self.assertEqual([r[0] for r in ra], ["ETH/USDT", "BTC/USDT"])
        self.assertEqual(ra[1][3], "Y", "A–I của BTC phải được cập nhật")

    def test_chi_tra_9_cot_A_den_I(self):
        cu = [ap("BTC/USDT", jp=(True, "", "", "", 95, 104, "Y"))]
        for r in C.xep_dong(cu, [ai("BTC/USDT"), ai("ETH/USDT")]):
            self.assertEqual(len(r), 9, "🔴 bot ghi vượt cột I")

    def test_ma_tam_vang_roi_quay_lai_khong_mat_JP(self):
        """LỖI KHÁCH 08/10: BTC vắng 1 vòng → trước đây J–P bị xoá rồi điền số gợi ý đè lên.
        Nay bot không ghi J–P → SL/TP khách gõ vẫn ở đó; BTC quay lại đúng dòng nếu dòng trống."""
        cu = [ap("BTC/USDT", "SHORT", jp=("", "", "", "", 6900, 5100, "Y")), ap("ETH/USDT")]
        v2 = C.xep_dong(cu, [ai("ETH/USDT")])
        self.assertEqual(v2[0], TRONG, "mã vắng → A–I trống")
        # Sheet sau vòng 2: A–I trống, J–P của khách vẫn nguyên (bot không ghi J–P)
        cu2 = [v2[0] + cu[0][9:], cu[1]]
        v3 = C.xep_dong(cu2, [ai("BTC/USDT", "SHORT"), ai("ETH/USDT")])
        # J–P dòng 4 còn số khách gõ → không cho mã nào vào (không biết số đó của ai)
        self.assertEqual(v3[0], TRONG)
        self.assertEqual(v3[2][0], "BTC/USDT", "BTC sang dòng mới, KHÔNG nhận SL cũ")

    def test_ma_moi_vao_dong_trong_ma_JP_cung_trong(self):
        cu = [ap("BTC/USDT"), [""] * 16, ap("ETH/USDT")]
        ra = C.xep_dong(cu, [ai("BTC/USDT"), ai("ETH/USDT"), ai("SOL/USDT")])
        self.assertEqual([r[0] for r in ra], ["BTC/USDT", "SOL/USDT", "ETH/USDT"])

    def test_ma_moi_KHONG_vao_dong_con_so_nguoi_dung(self):
        """Lỗi thật 09/2026: SL 5008.78/5264.33 của mã cũ rơi sang ETH."""
        cu = [[""] * 9 + ["", "", "", "", 5008.78, 5264.33, "Y"]]
        ra = C.xep_dong(cu, [ai("ETH/USDT")])
        self.assertEqual(ra[0], TRONG)
        self.assertEqual(ra[1][0], "ETH/USDT")

    def test_dong_chi_co_cong_thuc_thi_ma_moi_vao_duoc(self):
        """Công thức (=E4*0.98) tính theo dòng → mã mới vào được, công thức tự đúng."""
        cu = [[""] * 9 + ["", "", "", "", "=IF(A4=\"\",\"\",E4*0.98)", "", ""]]
        ra = C.xep_dong(cu, [ai("ETH/USDT")])
        self.assertEqual(len(ra), 1)
        self.assertEqual(ra[0][0], "ETH/USDT")

    def test_o_tran_tu_IMPORTRANGE_coi_la_du_lieu(self):
        """Ô tràn từ công thức hàng trên đọc ra là SỐ → không cho mã mới vào dòng đó."""
        cu = [[""] * 9 + ["", 0.3, 0.3, "", "", "", ""]]
        ra = C.xep_dong(cu, [ai("ETH/USDT")])
        self.assertEqual(ra[1][0], "ETH/USDT")

    def test_ma_dang_loi_giu_nguyen_A_den_I(self):
        cu = [ap("BTC/USDT"), ap("ETH/USDT")]
        ra = C.xep_dong(cu, [ai("ETH/USDT", gia=55.0)], giu_ma={"btc/usdt"})
        self.assertEqual(ra[0], cu[0][:9], "mã bot lỗi vòng này → giữ dòng cũ, không xoá")
        self.assertEqual(ra[1][4], 55.0)

    def test_bang_ngan_lai_thi_de_trong_dong_thua(self):
        cu = [ap("BTC/USDT"), ap("ETH/USDT"), ap("SOL/USDT")]
        ra = C.xep_dong(cu, [ai("BTC/USDT")])
        self.assertEqual(ra, [ai("BTC/USDT"), TRONG, TRONG])

    def test_cung_ma_LONG_SHORT_hai_dong_phan_biet(self):
        cu = [ap("BTC/USDT", "LONG"), ap("BTC/USDT", "SHORT")]
        ra = C.xep_dong(cu, [ai("BTC/USDT", "SHORT"), ai("BTC/USDT", "LONG")])
        self.assertEqual([r[1] for r in ra], ["LONG", "SHORT"])

    def test_khoa_khong_phan_biet_hoa_thuong_khoang_trang(self):
        cu = [ap(" btc/usdt ", "long")]
        ra = C.xep_dong(cu, [ai("BTC/USDT", "LONG")])
        self.assertEqual(len(ra), 1)

    def test_bang_rong(self):
        self.assertEqual(C.xep_dong([], []), [])
        self.assertEqual(C.xep_dong(None, [ai("BTC/USDT")]), [ai("BTC/USDT")])


class TestSLTPMacDinh(unittest.TestCase):
    def test_LONG(self):
        sl, tp = C.goi_y_sltp("LONG", 100.0, 2, 3)
        self.assertAlmostEqual(sl, 98.0); self.assertAlmostEqual(tp, 103.0)

    def test_SHORT_dao_chieu(self):
        sl, tp = C.goi_y_sltp("SHORT", 100.0, 2, 3)
        self.assertAlmostEqual(sl, 102.0); self.assertAlmostEqual(tp, 97.0)

    def test_gia_vao_hong(self):
        self.assertEqual(C.goi_y_sltp("LONG", 0, 2, 3), (None, None))
        self.assertEqual(C.goi_y_sltp("LONG", "abc", 2, 3), (None, None))

    def test_dien_o_trong(self):
        d = C.dien_mac_dinh_sltp(ap("BTC/USDT"), 2, 3, "Y")
        self.assertEqual(d[13:16], [98.0, 103.0, "Y"])

    def test_KHONG_thay_so_nguoi_dung(self):
        d = C.dien_mac_dinh_sltp(ap("BTC/USDT", jp=("", "", "", "", 95, "", "N")), 2, 3, "Y")
        self.assertEqual(d[13:16], [95, 103.0, "N"], "🔴 đè số / cờ khách đã gõ")

    def test_chi_vi_the_dang_mo(self):
        for trang_thai in ("N", "ĐÓNG", ""):
            with self.subTest(d=trang_thai):
                d = C.dien_mac_dinh_sltp(ap("BTC/USDT", d=trang_thai), 2, 3, "Y")
                self.assertEqual(d[13:16], ["", "", ""])

    def test_dong_ngan_duoc_noi_dai(self):
        d = C.dien_mac_dinh_sltp(ai("BTC/USDT"), 2, 3, "N")
        self.assertEqual(d[13:16], [98.0, 103.0, "N"])

    def test_tra_ban_sao(self):
        goc = ap("BTC/USDT")
        C.dien_mac_dinh_sltp(goc, 2, 3, "Y")
        self.assertEqual(goc[13:16], ["", "", ""], "không được sửa dòng gốc")


if __name__ == "__main__":
    unittest.main(verbosity=2)
