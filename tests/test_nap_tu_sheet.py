# -*- coding: utf-8 -*-
"""
Chạy THẬT: cst.py nạp cấu hình từ sheet tổng giả, dựng đúng các tài khoản.
Không mạng, không tiền thật.
"""
import os, shutil, subprocess, sys, tempfile, textwrap, unittest
from pathlib import Path

QBOT = Path(__file__).resolve().parent.parent

SHEET_GIA = '''
BANG = [
    ["PHIÊN BẢN", "%s"],
    ["Tài khoản", "Bật", "API Key", "API Secret", "Sheet ID", "Chat ID", "Lớp", "%%SL", "%%TP"],
    ["q2pri", "Y", "KEY_A", "SEC_A", "SHEET_A", "-101", "1", "2", "3"],
    ["q2pub", "Y", "KEY_B", "SEC_B", "SHEET_B", "-102", "2", "5", "6"],
    ["q3fu",  "N", "KEY_C", "SEC_C", "SHEET_C", "-103", "3", "10", "10"],
]
class LoiSheetCauHinh(Exception): pass
def nap(bot_id, sid):
    if "%s" == "LOI":
        raise LoiSheetCauHinh("mô phỏng sheet lỗi")
    import sheet_config_that as t
    pb, bang = t.phan_tich_bang(BANG)
    bang = t.loc_dang_bat(bang); t.kiem_tra_du_khoa(bang)
    return pb, bang
def doc_o_phien_ban(sid, tab): return "%s"
'''

CONFIG = """
[global]
bot_id = QBOT01
config_spreadsheet_id = SHEET_TONG
config_reload_seconds = 300
key_name = x
key_binance =
secret_binance =
spreadsheet_id =
chat_id = -1
bot_token = X
is_print_mode = false
test_mode = false
tab_dat_lenh = ĐẶT LỆNH
top_count = 50
time_gap_do_it = 0
max_increase_decrease_4h_day_count = 60
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


def _hop_cat(phien_ban="7"):
    d = Path(tempfile.mkdtemp(prefix="qbot_sheet_"))
    for f in ("cst.py", "rate_guard.py", "config_watcher.py"):
        shutil.copy(QBOT / f, d / f)
    shutil.copy(QBOT / "sheet_config.py", d / "sheet_config_that.py")
    (d / "sheet_config.py").write_text(SHEET_GIA % (phien_ban, phien_ban, phien_ban),
                                       encoding="utf-8")
    (d / "config.ini").write_text(textwrap.dedent(CONFIG), encoding="utf-8")
    return d


def _chay(d, ma, acc=None):
    (d / "thu.py").write_text(ma, encoding="utf-8")
    env = dict(os.environ, QBOT_CONFIG=str(d / "config.ini"), QBOT_NO_LOCK="1")
    env.pop("QBOT_ACCOUNT", None)
    if acc:
        env["QBOT_ACCOUNT"] = acc
    r = subprocess.run([sys.executable, str(d / "thu.py")], cwd=d, env=env,
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=60)
    return r.stdout + r.stderr


class TestNapTuSheet(unittest.TestCase):
    def setUp(self):
        self.d = _hop_cat()

    def tearDown(self):
        shutil.rmtree(self.d, ignore_errors=True)

    def test_lay_dung_danh_sach_tai_khoan_da_loc(self):
        # phải đặt QBOT_ACCOUNT vì file chạy không phải hd_*.py nên cst không
        # tự mở tiến trình con — chốt an toàn này là đúng, không phải lỗi
        out = _chay(self.d, "import cst\nprint('TK=' + ','.join(cst.accounts))\n",
                    acc="q2pri")
        self.assertIn("TK=q2pri,q2pub", out, f"q3fu để Bật=N phải bị loại:\n{out[:500]}")
        self.assertNotIn("q3fu", out.split("TK=")[1].split("\n")[0])

    def test_moi_tai_khoan_lay_dung_key_cua_minh(self):
        out = _chay(self.d, "import cst\nprint('K=' + cst.key_binance + '|S=' + cst.spreadsheet_id)\n",
                    acc="q2pub")
        self.assertIn("K=KEY_B|S=SHEET_B", out, f"lấy nhầm key:\n{out[:500]}")

    def test_tham_so_van_hanh_rieng_tung_tai_khoan_co_hieu_luc(self):
        """Mỗi tài khoản một lớp → %SL/%TP khác nhau, KHÔNG bị chặn bởi whitelist."""
        out = _chay(self.d, "import cst\nprint('SL=' + str(cst.default_sl_rate_layer_1))\n",
                    acc="q2pub")
        self.assertIn("SL=5", out, f"tham số lớp bị chặn hoặc không áp:\n{out[:600]}")

    def test_kiem_tra_cau_hinh_xem_duoc_moi_tai_khoan_khong_can_chon(self):
        """Lỗi trên VPS: kiem_tra_cau_hinh báo "Chưa chọn tài khoản… Đặt QBOT_ACCOUNT"
        dù tài khoản khai đúng trên sheet tổng. Công cụ soát phải xem MỌI tài khoản."""
        for f in ("kiem_tra_cau_hinh.py", "giu_cua_so.py"):
            shutil.copy(QBOT / f, self.d / f)
        env = dict(os.environ, QBOT_CONFIG=str(self.d / "config.ini"), QBOT_GIU_CUA_SO="0")
        env.pop("QBOT_ACCOUNT", None); env.pop("QBOT_CHE_DO_SOAT", None)
        r = subprocess.run([sys.executable, "kiem_tra_cau_hinh.py"], cwd=self.d, env=env,
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=60)
        out = r.stdout + r.stderr
        self.assertNotIn("Chưa chọn tài khoản", out, f"🔴 công cụ soát bắt chọn tài khoản:\n{out[:800]}")
        self.assertIn("[q2pri]", out); self.assertIn("[q2pub]", out)
        self.assertIn("Cấu hình hợp lệ", out, out[-800:])
        self.assertEqual(r.returncode, 0)

    def test_chay_file_khac_khong_chon_tai_khoan_bao_dung_nguon(self):
        out = _chay(self.d, "import cst\n")
        self.assertIn("Chưa chọn tài khoản", out)
        self.assertIn("Sheet tổng", out, "tài khoản khai ở sheet tổng — đừng báo là config.ini")
        self.assertNotIn("config.ini đang khai", out)

    def test_bao_ro_nguon_cau_hinh(self):
        out = _chay(self.d, "import cst\n")
        self.assertIn("Nạp từ sheet tổng", out)
        self.assertIn("QBOT01", out)

    def test_thieu_bot_id_thi_dung(self):
        cfg = (self.d / "config.ini").read_text(encoding="utf-8").replace("bot_id = QBOT01", "bot_id =")
        (self.d / "config.ini").write_text(cfg, encoding="utf-8")
        out = _chay(self.d, "import cst\n")
        self.assertIn("THIẾU bot_id", out)

    def test_sheet_loi_thi_DUNG_HAN_khong_dung_du_phong(self):
        d = _hop_cat(phien_ban="LOI")
        try:
            out = _chay(d, "import cst\nprint('KHONG_NEN_TOI_DAY')\n")
            self.assertNotIn("KHONG_NEN_TOI_DAY", out, "🔴 sheet lỗi mà bot vẫn chạy tiếp!")
            self.assertIn("Bot DỪNG", out)
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_khong_khai_sheet_thi_chay_y_nhu_cu(self):
        """Tương thích ngược: bỏ config_spreadsheet_id → đọc hết từ config.ini."""
        cfg = (self.d / "config.ini").read_text(encoding="utf-8")
        cfg = cfg.replace("config_spreadsheet_id = SHEET_TONG", "")
        cfg = cfg.replace("key_binance =", "key_binance = TU_FILE")
        cfg = cfg.replace("secret_binance =", "secret_binance = SEC_FILE")
        cfg = cfg.replace("\nspreadsheet_id =", "\nspreadsheet_id = SHEET_FILE")
        (self.d / "config.ini").write_text(cfg, encoding="utf-8")
        out = _chay(self.d, "import cst\nprint('NGUON=' + ('sheet' if cst.nap_tu_sheet else 'file'))\n"
                            "print('K=' + cst.key_binance)\n")
        self.assertIn("NGUON=file", out)
        self.assertIn("K=TU_FILE", out)


if __name__ == "__main__":
    unittest.main(verbosity=2)
