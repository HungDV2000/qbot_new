"""
Nhịp chạy lại của từng bot — lấy từ config.ini, không được hardcode.

Gặp thật: khách điền 60 vào `cancel_orders_minutes` với ý 60 GIÂY, bot hiểu là
60 PHÚT → 1 tiếng mới quét 1 lần, tưởng "config không nhận".

    python3 tests/test_nhip_chay.py
"""
import ast, io, os, shutil, subprocess, sys, tempfile, textwrap, unittest
from pathlib import Path

QBOT = Path(__file__).resolve().parent.parent
BOT_NHIP = {
    "hd_order_multi.py": "delay_vao_lenh",
    "hd_update_cho_va_khop.py": "delay_cho_va_khop",
    "hd_update_all.py": "delay_update_all",
    "hd_alert_possition_and_open_order.py": "delay_calert_possition_and_open_order",
    "hd_cancel_orders_schedule.py": "cancel_orders_seconds",
    "hd_cancel_selective.py": "cancel_selective_seconds",
}

CONFIG = """
[global]
key_name = x
key_binance = K
secret_binance = S
spreadsheet_id = SH
chat_id = -1
bot_token = X
tab_dat_lenh = ĐẶT LỆNH
delay_vao_lenh = 60
delay_cho_va_khop = 600
delay_calert_possition_and_open_order = 120
delay_update_all = 120
cancel_order_after_minutes = 30
{them}
"""


def _hoi_cst(them, hoi="cst.cancel_orders_seconds"):
    d = Path(tempfile.mkdtemp(prefix="qbot_nhip_"))
    try:
        for f in ("cst.py", "rate_guard.py", "config_watcher.py", "sheet_config.py",
                  "giu_cua_so.py"):
            shutil.copy(QBOT / f, d / f)
        (d / "config.ini").write_text(textwrap.dedent(CONFIG.format(them=them)), encoding="utf-8")
        env = dict(os.environ, QBOT_CONFIG=str(d / "config.ini"), QBOT_NO_LOCK="1",
                   QBOT_GIU_CUA_SO="0")
        env.pop("QBOT_ACCOUNT", None)
        r = subprocess.run([sys.executable, "-c", f"import cst; print('KQ=', {hoi})"],
                           cwd=d, env=env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=60)
        return r.stdout + r.stderr
    finally:
        shutil.rmtree(d, ignore_errors=True)


class TestNhipHuyLenh(unittest.TestCase):
    def test_khai_bang_PHUT_nhu_cu(self):
        self.assertIn("KQ= 3600", _hoi_cst("cancel_orders_minutes = 60"))

    def test_khai_bang_GIAY(self):
        self.assertIn("KQ= 60", _hoi_cst("cancel_orders_seconds = 60"))

    def test_khai_ca_hai_thi_GIAY_thang(self):
        out = _hoi_cst("cancel_orders_seconds = 90\ncancel_orders_minutes = 60")
        self.assertIn("KQ= 90", out)

    def test_thieu_ca_hai_thi_bao_ro(self):
        out = _hoi_cst("")
        self.assertIn("cancel_orders_minutes", out)
        self.assertNotIn("KQ=", out, "thiếu cấu hình mà vẫn chạy là sai")

    def test_giay_qua_nho_bi_chan(self):
        out = _hoi_cst("cancel_orders_seconds = 1")
        self.assertIn("phải >=", out)


class TestMoiBotLayNhipTuConfig(unittest.TestCase):
    def _src(self, f):
        return io.open(QBOT / f, encoding="utf-8").read()

    def test_khong_hardcode_nhip_trong_vong_lap(self):
        """config_watcher.ngu(<số>) = nhịp cứng, sửa config vô ích."""
        for f in BOT_NHIP:
            for n in ast.walk(ast.parse(self._src(f))):
                if (isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "ngu"
                        and n.args and isinstance(n.args[0], ast.Constant)):
                    # ngu(60) ở nhánh XỬ LÝ LỖI thì chấp nhận được
                    self.assertLessEqual(n.args[0].value, 60,
                                         f"🔴 {f} dòng {n.lineno}: nhịp cứng {n.args[0].value}s")

    def test_moi_bot_deu_in_nhip_va_file_config(self):
        """Phải in nhịp + đường dẫn config để biết bot có nhận cấu hình mới không."""
        for f in BOT_NHIP:
            with self.subTest(bot=f):
                self.assertIn("cst.bao_nhip(", self._src(f), f"🔴 {f} không in nhịp chạy")

    def test_bao_nhip_in_duong_dan_tuyet_doi(self):
        src = self._src("cst.py")
        i = src.index("def bao_nhip(")
        self.assertIn("os.path.abspath(config_file)", src[i:i + 900])
        self.assertIn("BẬT LẠI", src[i:i + 900], "phải nhắc sửa config xong cần bật lại bot")

    def test_kiem_tra_cau_hinh_in_bang_nhip(self):
        src = self._src("kiem_tra_cau_hinh.py")
        self.assertIn("def in_nhip_chay(", src)
        for khoa in set(BOT_NHIP.values()) | {"config_reload_seconds"}:
            self.assertIn(khoa, src)


if __name__ == "__main__":
    unittest.main(verbosity=2)
