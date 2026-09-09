# -*- coding: utf-8 -*-
"""
Tên tài khoản lệch chữ hoa/thường — [q2Fu] vs accounts = q2fu.

configparser PHÂN BIỆT hoa/thường ở tên section, nên đây là lỗi rất dễ mắc
và thông báo cũ ("không tìm thấy section") gây hiểu nhầm là thiếu section.
"""
import os, subprocess, sys, tempfile, textwrap, unittest
from pathlib import Path

QBOT = Path(__file__).resolve().parent.parent


def _viet_config(thu_muc, noi_dung):
    f = thu_muc / "config.ini"
    f.write_text(textwrap.dedent(noi_dung), encoding="utf-8")
    return f


GLOBAL = """
    [global]
    accounts = {acc}
    key_binance =
    secret_binance =
    spreadsheet_id =
    key_name = test
    chat_id = -100
    bot_token = X
    is_print_mode = false
    test_mode = false
    tab_dat_lenh = ĐẶT LỆNH
    top_count = 50
    time_gap_do_it = 5
    max_increase_decrease_4h_day_count = 3
    lenh2_rate_long = 1
    lenh2_rate_short = 1
    lenh3_rate_long = 1
    lenh3_rate_short = 1
    lenh3_callback_rate = 1
    delay_vao_lenh = 60
    delay_vao_lenh_123 = 300
    delay_cho_va_khop = 600
    delay_calert_possition_and_open_order = 120
    delay_update_price = 120
    delay_update_all = 120
    delay_track_30_prices = 60
    delay_periodic_report = 300
    cancel_orders_minutes = 60
    cancel_order_after_minutes = 30
    """


class TestKhopHoaThuong(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="qbot_case_"))
        (self.tmp / "bot.py").write_text(
            "import cst\nprint('DUNG_SECTION=' + cst.account)\n", encoding="utf-8")

    def _chay(self, noi_dung, acc_env):
        _viet_config(self.tmp, noi_dung)
        env = dict(os.environ, QBOT_CONFIG=str(self.tmp / "config.ini"),
                   QBOT_ACCOUNT=acc_env, PYTHONPATH=str(QBOT))
        return subprocess.run([sys.executable, str(self.tmp / "bot.py")],
                              cwd=self.tmp, env=env, capture_output=True,
                              text=True, encoding="utf-8", errors="replace", timeout=60)

    def test_lech_hoa_thuong_van_chay_va_co_canh_bao(self):
        """accounts = q2fu, section [q2Fu] → chạy được, dùng đúng [q2Fu], có cảnh báo."""
        r = self._chay(GLOBAL.format(acc="q2pri, q2fu") + textwrap.dedent("""
            [q2pri]
            key_binance = A
            secret_binance = A
            spreadsheet_id = A

            [q2Fu]
            key_binance = KEY_FU
            secret_binance = SEC_FU
            spreadsheet_id = SHEET_FU
            """), "q2fu")
        out = r.stdout + r.stderr
        self.assertIn("DUNG_SECTION=q2Fu", out, f"không khớp được:\n{out[:400]}")
        self.assertIn("khác chữ hoa/thường", out, "phải cảnh báo để người dùng sửa")

    def test_dung_key_cua_dung_tai_khoan(self):
        """Khớp xong phải lấy ĐÚNG key của section đó, không phải của [global]."""
        (self.tmp / "bot.py").write_text(
            "import cst\nprint('KEY=' + cst.key_binance)\n", encoding="utf-8")
        r = self._chay(GLOBAL.format(acc="q2Fu") + textwrap.dedent("""
            [q2Fu]
            key_binance = KEY_FU
            secret_binance = SEC_FU
            spreadsheet_id = SHEET_FU
            """), "q2fu")
        self.assertIn("KEY=KEY_FU", r.stdout + r.stderr)

    def test_hai_section_chi_khac_hoa_thuong_thi_DUNG(self):
        """[q2fu] và [q2Fu] cùng tồn tại → không được đoán, phải dừng."""
        r = self._chay(GLOBAL.format(acc="q2fu") + textwrap.dedent("""
            [q2fu]
            key_binance = KEY_1
            secret_binance = S1
            spreadsheet_id = SH1

            [q2Fu]
            key_binance = KEY_2
            secret_binance = S2
            spreadsheet_id = SH2
            """), "q2FU")
        out = r.stdout + r.stderr
        self.assertNotEqual(r.returncode, 0, "phải dừng, không được đoán bừa")
        self.assertIn("khác nhau chữ hoa/thường", out)

    def test_thieu_han_section_thi_bao_ro(self):
        """Khai q2fu nhưng không có section nào → báo lỗi kèm danh sách section."""
        r = self._chay(GLOBAL.format(acc="q2pri, q2fu") + textwrap.dedent("""
            [q2pri]
            key_binance = A
            secret_binance = A
            spreadsheet_id = A
            """), "q2fu")
        out = r.stdout + r.stderr
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Không tìm thấy section", out)
        self.assertIn("[q2pri]", out, "phải liệt kê section đang có để dễ đối chiếu")


if __name__ == "__main__":
    unittest.main(verbosity=2)
