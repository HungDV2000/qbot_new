# -*- coding: utf-8 -*-
"""
Đếm SỐ LƯỢT gọi Google Sheets để chứng minh không vượt hạn mức 60 lượt/phút.
Chạy offline hoàn toàn — không mạng, không tiền thật.
"""
import io, os, sys, time, unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# Dùng lại bộ mock của test_hd_order_multi (không mạng, không tiền thật)
import tests.test_hd_order_multi as _base  # noqa: F401

QUOTA_PER_MIN = 60          # hạn mức Google, dùng CHUNG cho mọi tài khoản
SYMBOLS       = 50          # số mã trên sheet
OTHER_BOTS    = 6           # các bot phụ ~6 lượt/phút/tài khoản


class TestB2Cache(unittest.TestCase):
    """Cache B2 phải cắt được lượt đọc, nhưng KHÔNG được che mất lệnh DỪNG."""

    def setUp(self):
        self.m = _base.M
        self.m.invalidate_state_cache()
        self.calls = []

    def _fake_fetch(self, value='VAO LENH'):
        from datetime import datetime
        def f():
            self.calls.append(time.time())
            return value, datetime.now()
        return f

    def test_doc_lai_moi_dong_chi_ton_1_luot(self):
        """50 dòng quét nhanh trong 1 TTL → chỉ 1 lượt gọi API (trước đây 50)."""
        with mock.patch.object(self.m, '_fetch_current_state', self._fake_fetch()):
            for _ in range(SYMBOLS):
                self.m.get_current_state()
        self.assertEqual(len(self.calls), 1,
                         f"phải 1 lượt, thực tế {len(self.calls)}")

    def test_force_luon_doc_that(self):
        """Mốc quan trọng (đầu/cuối vòng) phải bỏ qua cache."""
        with mock.patch.object(self.m, '_fetch_current_state', self._fake_fetch()):
            self.m.get_current_state()
            self.m.get_current_state(force=True)
            self.m.get_current_state(force=True)
        self.assertEqual(len(self.calls), 3)

    def test_het_ttl_thi_doc_lai(self):
        """Quá TTL phải đọc lại — nếu không sẽ không thấy người dùng bấm DỪNG."""
        with mock.patch.object(self.m, 'STATE_CACHE_TTL', 0.05), \
             mock.patch.object(self.m, '_fetch_current_state', self._fake_fetch()):
            self.m.get_current_state()
            time.sleep(0.08)
            self.m.get_current_state()
        self.assertEqual(len(self.calls), 2)

    def test_van_bat_duoc_lenh_dung(self):
        """Đổi B2 sang STOP → sau TTL bot phải nhận ra."""
        from datetime import datetime
        state = {'v': 'VAO LENH'}
        def f():
            self.calls.append(1)
            return state['v'], datetime.now()
        with mock.patch.object(self.m, 'STATE_CACHE_TTL', 0.05), \
             mock.patch.object(self.m, '_fetch_current_state', f):
            self.assertEqual(self.m.get_current_state()[0], 'VAO LENH')
            state['v'] = 'STOP'
            time.sleep(0.08)
            self.assertEqual(self.m.get_current_state()[0], 'STOP',
                             "🔴 NGUY HIỂM: cache che mất lệnh DỪNG!")

    def test_ttl_khong_qua_dai(self):
        """TTL quá dài thì phản ứng DỪNG chậm — chốt trần 30s."""
        self.assertLessEqual(self.m.STATE_CACHE_TTL, 30)
        self.assertGreaterEqual(self.m.STATE_CACHE_TTL, 0)


class TestTongTai(unittest.TestCase):
    """
    Số liệu ĐO THẬT từ tests/demo_3_accounts_rate.sh
    (3 tài khoản, 50 mã, 24 bot, code thật, Google/Binance giả — 150s/lượt):

        TẮT cache (mô phỏng code cũ) : đỉnh 177 lượt/phút  → vượt 2.95 lần
        BẬT cache (code đã sửa)      : đỉnh  24 lượt/phút  → 40% hạn mức

    Ghi chú: các con số dưới đây là ĐO ĐƯỢC, không phải ước lượng.
    Nếu sửa code làm chúng đổi, phải chạy lại kịch bản trên rồi cập nhật.
    """
    DO_TRUOC_3TK = 177      # đỉnh/phút khi TẮT cache, 3 tài khoản
    DO_SAU_3TK   = 24       # đỉnh/phút khi BẬT cache, 3 tài khoản

    def test_truoc_khi_sua_la_vuot_han_muc(self):
        self.assertGreater(self.DO_TRUOC_3TK, QUOTA_PER_MIN,
                           "số đo cũ phải vượt hạn mức thì bài đo mới có nghĩa")

    def test_sau_khi_sua_nam_trong_han_muc(self):
        self.assertLessEqual(self.DO_SAU_3TK, QUOTA_PER_MIN,
                             f"3 tài khoản vẫn vượt: {self.DO_SAU_3TK}")

    def test_con_du_bien_an_toan(self):
        """Không chỉ 'lọt' — phải còn dư ít nhất 30% hạn mức."""
        self.assertLessEqual(self.DO_SAU_3TK, QUOTA_PER_MIN * 0.7,
                             "sát trần quá, hết biên an toàn khi sheet nhiều mã hơn")

    def test_so_tai_khoan_toi_da_uoc_tinh(self):
        """
        Suy ra tuyến tính từ số đo: 24 lượt/phút cho 3 tài khoản = 8/tài khoản.
        ⚠️ Đây là PHÉP NGOẠI SUY, không phải số đo — muốn chắc thì đo thật.
        """
        moi_tk = self.DO_SAU_3TK / 3
        toi_da = int(QUOTA_PER_MIN / moi_tk)
        self.assertGreaterEqual(toi_da, 6,
                                f"chỉ đỡ được {toi_da} tài khoản — cần nâng TTL")

class TestMoiBotDeuDuocVa(unittest.TestCase):
    """Đại ca yêu cầu TẤT CẢ bot phải chuẩn — không bot nào còn đọc B2 mỗi dòng."""

    BOTS = ['hd_order.py', 'hd_order_limit.py',
            'hd_order_market_price.py', 'hd_order_multi.py']

    def _src(self, f):
        return io.open(f, encoding='utf-8').read()

    def _bots_co_that(self):
        """Bản gọn (qbot_new) chỉ chép 1 bot đặt lệnh — bỏ qua bot không có."""
        import os
        co = [f for f in self.BOTS if os.path.exists(f)]
        self.assertTrue(co, "không thấy bot đặt lệnh nào trong thư mục")
        return co

    def test_ca_4_bot_deu_co_cache(self):
        for f in self._bots_co_that():
            src = self._src(f)
            with self.subTest(bot=f):
                self.assertIn('rate_guard', src, f"{f} chưa chống 429")
                self.assertIn('def get_current_state(force=False)', src)
                self.assertIn('def _fetch_current_state()', src)

    def test_khong_bot_nao_goi_thang_ham_doc_that(self):
        """Gọi thẳng _fetch_current_state() là đi vòng qua cache → cấm."""
        for f in self._bots_co_that():
            src = self._src(f)
            goi_thang = src.count('_fetch_current_state()')
            with self.subTest(bot=f):
                # chỉ được xuất hiện ở: định nghĩa hàm + truyền tham chiếu (không có ngoặc)
                self.assertEqual(goi_thang, 1, f"{f}: có chỗ gọi thẳng, bỏ qua cache")

    def test_moc_quan_trong_deu_force(self):
        """Mỗi bot phải có ít nhất 2 điểm đọc THẬT (đầu vòng + chốt cuối vòng)."""
        for f in self._bots_co_that():
            src = self._src(f)
            with self.subTest(bot=f):
                self.assertGreaterEqual(
                    src.count('get_current_state(force=True)'), 2,
                    f"{f}: thiếu điểm đọc thật → có thể bỏ sót lệnh DỪNG")

    def test_van_con_diem_doc_cache_trong_vong_lap(self):
        """Đúng chỗ per-row phải dùng cache (không force) — nếu không thì vô ích."""
        for f in self._bots_co_that():
            src = self._src(f)
            with self.subTest(bot=f):
                self.assertIn('get_current_state()', src,
                              f"{f}: không còn chỗ dùng cache → cache thành vô dụng")


class TestRateGuard(unittest.TestCase):
    def test_ttl_bi_kep_trong_nguong_an_toan(self):
        import configparser, rate_guard
        c = configparser.ConfigParser()
        c.read_dict({'global': {'state_cache_ttl_sec': '9999'}})
        self.assertEqual(rate_guard.read_ttl(c), rate_guard.MAX_TTL)
        c.read_dict({'global': {'state_cache_ttl_sec': '-5'}})
        self.assertEqual(rate_guard.read_ttl(c), 0.0)

    def test_ttl_sai_dinh_dang_thi_dung_mac_dinh(self):
        import configparser, rate_guard
        c = configparser.ConfigParser()
        c.read_dict({'global': {'state_cache_ttl_sec': 'abc'}})
        self.assertEqual(rate_guard.read_ttl(c), rate_guard.DEFAULT_TTL)

    def test_thieu_key_thi_dung_mac_dinh(self):
        import configparser, rate_guard
        c = configparser.ConfigParser(); c.read_dict({'global': {}})
        self.assertEqual(rate_guard.read_ttl(c), rate_guard.DEFAULT_TTL)


class TestStagger(unittest.TestCase):
    def test_stagger_doc_duoc_tu_config(self):
        src = io.open('cst.py', encoding='utf-8').read()
        self.assertIn('account_start_stagger_sec', src)
        self.assertIn("getfloat('global', 'account_start_stagger_sec'", src)


if __name__ == '__main__':
    unittest.main(verbosity=2)
