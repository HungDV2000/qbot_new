"""
Giữ cửa sổ khi bot dừng (Windows) — chạy THẬT trong tiến trình con.

Trên máy này (không phải Windows) ép bật bằng QBOT_GIU_CUA_SO=1 — cùng đường
code như Windows khi đầu vào là bàn phím.

    python3 tests/test_giu_cua_so.py
"""
import ast, io, os, shutil, signal, subprocess, sys, tempfile, time, unittest
from pathlib import Path

QBOT = Path(__file__).resolve().parent.parent
NHAC = "nhấn Enter để đóng"
DIEM_VAO = ("hd_order_multi.py", "hd_update_cho_va_khop.py", "hd_alert_possition_and_open_order.py",
            "hd_cancel_selective.py", "hd_cancel_orders_schedule.py", "hd_update_all.py",
            "kiem_tra_cau_hinh.py")


def _hop_cat(*them):
    d = Path(tempfile.mkdtemp(prefix="qbot_giu_"))
    for f in ("giu_cua_so.py",) + them:
        shutil.copy(QBOT / f, d / f)
    return d


def _env(**k):
    e = dict(os.environ)
    e.pop("QBOT_SUPERVISED", None)
    e["QBOT_GIU_CUA_SO"] = "1"
    e["PYTHONIOENCODING"] = "utf-8"
    e.update(k)
    return e


def _chay(code, env=None, file="s.py", d=None, nhap="\n"):
    d = d or _hop_cat()
    if code is not None:
        (d / file).write_text(code, encoding="utf-8")
    p = subprocess.run([sys.executable, file], cwd=d, input=nhap, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, text=True, encoding="utf-8", timeout=30,
                       env=env or _env())
    shutil.rmtree(d, ignore_errors=True)
    return p.returncode, p.stdout


class TestGiuCuaSo(unittest.TestCase):
    def test_loi_cau_hinh_SystemExit(self):
        rc, out = _chay("import giu_cua_so\nraise SystemExit('❌ Thiếu key_binance')\n")
        self.assertEqual(rc, 1)
        self.assertIn(NHAC, out, "🔴 lỗi cấu hình mà cửa sổ đóng luôn")
        self.assertLess(out.index("Thiếu key_binance"), out.index(NHAC),
                        "thông báo lỗi phải hiện TRƯỚC dòng chờ Enter")

    def test_loi_chua_bat(self):
        rc, out = _chay("import giu_cua_so\n1/0\n")
        self.assertNotEqual(rc, 0)
        self.assertLess(out.index("ZeroDivisionError"), out.index(NHAC))

    def test_chay_xong_cung_giu(self):
        rc, out = _chay("import giu_cua_so\nprint('✅ hợp lệ')\n")
        self.assertEqual(rc, 0)
        self.assertLess(out.index("hợp lệ"), out.index(NHAC))

    def test_that_su_dung_lai_cho_Enter(self):
        d = _hop_cat()
        (d / "s.py").write_text("import giu_cua_so\nraise SystemExit('lỗi')\n", encoding="utf-8")
        p = subprocess.Popen([sys.executable, "s.py"], cwd=d, stdin=subprocess.PIPE,
                             stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=_env())
        try:
            time.sleep(2)
            self.assertIsNone(p.poll(), "🔴 không chờ — cửa sổ sẽ đóng ngay")
            p.communicate(input=b"\n", timeout=10)
            self.assertEqual(p.returncode, 1, "nhấn Enter xong phải thoát, giữ mã lỗi")
        finally:
            if p.poll() is None:
                p.kill()
            shutil.rmtree(d, ignore_errors=True)

    def test_tien_trinh_con_cua_dieu_phoi_khong_cho(self):
        rc, out = _chay("import giu_cua_so\nraise SystemExit(3)\n", env=_env(QBOT_SUPERVISED="1"))
        self.assertEqual(rc, 3)
        self.assertNotIn(NHAC, out, "🔴 tiến trình con chờ Enter → treo, điều phối không bật lại được")

    def test_tu_khoi_dong_lai_khong_cho(self):
        rc, out = _chay("import giu_cua_so\ngiu_cua_so.khong_giu()\nraise SystemExit(0)\n")
        self.assertNotIn(NHAC, out, "🔴 bot cũ chờ Enter → không nhả chỗ cho bot mới")

    def test_config_watcher_goi_khong_giu_khi_tu_khoi_dong_lai(self):
        src = io.open(QBOT / "config_watcher.py", encoding="utf-8").read()
        i = src.index("def khoi_dong_lai")
        self.assertIn("giu_cua_so.khong_giu()", src[i:i + 3000])

    def test_ctrl_c_khong_cho(self):
        for code in ("import giu_cua_so, time\nprint('bat', flush=True)\ntime.sleep(30)\n",
                     # kiểu bot: tự bắt Ctrl+C rồi thoát êm
                     "import giu_cua_so, time\nprint('bat', flush=True)\n"
                     "try:\n    time.sleep(30)\nexcept KeyboardInterrupt:\n    print('dừng')\n"):
            with self.subTest(code=code[-30:]):
                d = _hop_cat()
                (d / "s.py").write_text(code, encoding="utf-8")
                p = subprocess.Popen([sys.executable, "s.py"], cwd=d, stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                     text=True, encoding="utf-8", env=_env())
                try:
                    self.assertEqual(p.stdout.readline().strip(), "bat")
                    p.send_signal(signal.SIGINT)
                    out, _ = p.communicate(timeout=10)
                    self.assertNotIn(NHAC, out, "Ctrl+C là chủ động tắt — không bắt nhấn Enter")
                finally:
                    if p.poll() is None:
                        p.kill()
                    shutil.rmtree(d, ignore_errors=True)

    def test_ngoai_windows_mac_dinh_khong_cho(self):
        if os.name == "nt":
            self.skipTest("máy Windows")
        e = _env(); e.pop("QBOT_GIU_CUA_SO")
        rc, out = _chay("import giu_cua_so\nraise SystemExit('x')\n", env=e)
        self.assertNotIn(NHAC, out)

    def test_tat_bang_bien_moi_truong(self):
        rc, out = _chay("import giu_cua_so\nraise SystemExit('x')\n", env=_env(QBOT_GIU_CUA_SO="0"))
        self.assertNotIn(NHAC, out)


class TestMoiBotDeuGiu(unittest.TestCase):
    def test_nap_dau_tien(self):
        """Nạp sau cst là vô ích: cst dừng ngay lúc nạp khi thiếu cấu hình."""
        for f in DIEM_VAO:
            t = ast.parse(io.open(QBOT / f, encoding="utf-8").read())
            dau = next(n for n in t.body if isinstance(n, (ast.Import, ast.ImportFrom))
                       and not (isinstance(n, ast.ImportFrom) and n.module == "__future__"))
            with self.subTest(file=f):
                self.assertTrue(isinstance(dau, ast.Import) and dau.names[0].name == "giu_cua_so",
                                f"🔴 {f}: import đầu tiên phải là giu_cua_so")

    def test_bot_that_thieu_thu_vien_van_giu_de_doc_loi(self):
        """Chép RIÊNG từng bot (thiếu cst, config…) → lỗi nạp phải còn trên màn hình."""
        for f in DIEM_VAO:
            with self.subTest(bot=f):
                d = _hop_cat(f)
                rc, out = _chay(None, file=f, d=d)
                self.assertIn(NHAC, out, f"🔴 {f}: lỗi hiện rồi cửa sổ đóng mất")
                self.assertTrue("Error" in out or "❌" in out, out[-400:])
                self.assertLess(max(out.rfind("Error"), out.rfind("❌")), out.index(NHAC))

    def test_kiem_tra_cau_hinh_that_voi_config_rong(self):
        d = _hop_cat("kiem_tra_cau_hinh.py", "cst.py", "rate_guard.py", "sheet_config.py",
                     "config_watcher.py")
        (d / "telegram_factory.py").write_text("def send_tele(*a, **k): pass\n", encoding="utf-8")
        (d / "config.ini").write_text("[global]\n", encoding="utf-8")
        rc, out = _chay(None, file="kiem_tra_cau_hinh.py", d=d)
        self.assertEqual(rc, 1)
        self.assertIn("❌", out)
        self.assertLess(out.rindex("❌"), out.index(NHAC),
                        "🔴 kiem_tra_cau_hinh báo lỗi rồi cửa sổ đóng mất")


if __name__ == "__main__":
    unittest.main(verbosity=2)
