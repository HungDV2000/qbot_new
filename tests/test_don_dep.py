"""
Soát code chết đã dọn: sheet mỗi tài khoản chỉ còn 2 tab (ĐẶT LỆNH, Chờ và khớp).
Kèm test _pid_alive trên Windows (giả lập) — os.kill(pid, 0) ở Windows là GIẾT.

    python3 tests/test_don_dep.py
"""
import ast, glob, io, os, re, sys, types, unittest
from unittest import mock

QBOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(QBOT)

DA_XOA = {"cascade_manager", "order_state_tracker", "notification_manager",
          "utils", "binance_utils", "symbol_filter"}
SAU_BOT = ("hd_update_cho_va_khop", "hd_order_multi", "hd_alert_possition_and_open_order",
           "hd_cancel_selective", "hd_cancel_orders_schedule", "hd_update_all")
# Hàm cấp module không ai gọi nhưng CỐ Ý giữ
GIU_LAI = {"account_suffix",        # API nhỏ của cst, test đa tài khoản dùng
           "invalidate_state_cache"}  # test_rate_limit dùng để xoá cache B2


def _nguon():
    return {os.path.basename(f): io.open(f, encoding="utf-8").read()
            for f in sorted(glob.glob(os.path.join(QBOT, "*.py")))}


class TestDaDon(unittest.TestCase):
    def test_file_da_xoa(self):
        for m in DA_XOA:
            self.assertFalse(os.path.exists(m + ".py"), f"{m}.py vẫn còn")

    def test_khong_con_import_module_da_xoa(self):
        for f, s in _nguon().items():
            for n in ast.walk(ast.parse(s)):
                ten = []
                if isinstance(n, ast.Import):
                    ten = [a.name for a in n.names]
                elif isinstance(n, ast.ImportFrom) and n.module:
                    ten = [n.module]
                for t in ten:
                    with self.subTest(file=f):
                        self.assertNotIn(t, DA_XOA, f"🔴 {f} còn import {t} → bot chết lúc khởi động")

    def test_khong_con_dung_tab_da_bo(self):
        cam = ("get_100_ma", "get_white_list", "tab_list_all_ma", "tab_white_list",
               "cst.symbol_mode", "cst.symbol_list", "cst.top_count")
        for f, s in _nguon().items():
            for c in cam:
                with self.subTest(file=f, chu=c):
                    self.assertNotIn(c, s)

    def test_moi_ham_cap_module_deu_duoc_dung(self):
        src = _nguon()
        tat_ca = "\n".join(src.values())
        chet = []
        for f, s in src.items():
            for n in ast.parse(s).body:
                if not isinstance(n, (ast.FunctionDef, ast.ClassDef)) or n.name in GIU_LAI:
                    continue
                if n.name == "main" or n.name.startswith("test_"):
                    continue
                trong = len(re.findall(r"\b%s\b" % n.name, s)) - 1
                ngoai = len(re.findall(r"\.%s\b|import[^\n]*\b%s\b" % (n.name, n.name),
                                       tat_ca.replace(s, "")))
                if trong + ngoai == 0:
                    chet.append(f"{f}:{n.lineno} {n.name}")
        self.assertEqual(chet, [], f"hàm không ai gọi: {chet}")

    def test_du_6_bot(self):
        for f in ("start_all_bots.sh", "start_bot.sh", "chay_bot.bat"):
            s = io.open(f, encoding="utf-8").read()
            for b in SAU_BOT:
                with self.subTest(script=f, bot=b):
                    self.assertIn(b, s)
        for b in SAU_BOT:
            self.assertTrue(os.path.exists(b + ".py"), b)

    def test_bat_dung_CRLF(self):
        """.bat xuống dòng kiểu Unix thì CMD có lúc nhảy nhầm nhãn (goto)."""
        b = open("chay_bot.bat", "rb").read()
        self.assertEqual(b.count(b"\n"), b.count(b"\r\n"))


class TestPidAliveWindows(unittest.TestCase):
    """_pid_alive trên Windows KHÔNG được gọi os.kill — gọi là giết tiến trình."""

    def _goi(self, ten_os, handle=0, exit_code=0, last_err=0, kill=None):
        tree = ast.parse(io.open("cst.py", encoding="utf-8").read())
        fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_pid_alive")

        def cam_kill(*a):
            raise AssertionError("🔴 os.kill trên Windows = TerminateProcess = GIẾT tiến trình")
        fake_os = types.SimpleNamespace(name=ten_os, kill=kill or cam_kill)

        class K32:
            def OpenProcess(self, quyen, ke_thua, pid): return handle
            def GetExitCodeProcess(self, h, ref): ref.value = exit_code; return 1
            def CloseHandle(self, h): pass

        class CUlong:
            def __init__(self): self.value = 0

        fake_ctypes = types.SimpleNamespace(WinDLL=lambda *a, **k: K32(), c_ulong=CUlong,
                                            byref=lambda x: x, get_last_error=lambda: last_err)
        ns = {"os": fake_os}
        exec(compile(ast.Module(body=[fn], type_ignores=[]), "cst.py", "exec"), ns)
        with mock.patch.dict(sys.modules, {"ctypes": fake_ctypes}):
            return ns["_pid_alive"](1234)

    def test_dang_chay(self):
        self.assertTrue(self._goi("nt", handle=7, exit_code=259))

    def test_da_thoat(self):
        self.assertFalse(self._goi("nt", handle=7, exit_code=0))

    def test_khong_mo_duoc_vi_khac_quyen_van_la_dang_song(self):
        self.assertTrue(self._goi("nt", handle=0, last_err=5))

    def test_pid_khong_ton_tai(self):
        self.assertFalse(self._goi("nt", handle=0, last_err=87))

    def test_linux_van_dung_os_kill(self):
        self.assertTrue(self._goi("posix", kill=lambda *a: None))

        def chet(*a): raise ProcessLookupError
        self.assertFalse(self._goi("posix", kill=chet))


if __name__ == "__main__":
    unittest.main(verbosity=2)
