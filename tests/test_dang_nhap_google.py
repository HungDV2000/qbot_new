"""
Máy mới chưa có token.json — bot phải CÓ ĐƯỜNG đăng nhập Google.

Lỗi đã gặp trên VPS: "Không có token.json. Chạy bot một lần để đăng nhập…" —
nhưng bot nào cũng đọc sheet tổng trước, thiếu token là dừng → không bao giờ
đăng nhập được. Thư viện Google được giả lập, không mạng.

    python3 tests/test_dang_nhap_google.py
"""
import importlib, json, os, shutil, sys, tempfile, types, unittest
from pathlib import Path
from unittest import mock

QBOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(QBOT))


class _Creds:
    def __init__(self, valid=True): self.valid, self.expired, self.refresh_token = valid, False, None
    def to_json(self): return json.dumps({"token": "T"})


def _gia_google():
    mods = {}
    for ten in ("google", "google.oauth2", "google.auth", "google.auth.transport",
                "googleapiclient", "google_auth_oauthlib"):
        mods[ten] = types.ModuleType(ten)
    c = types.ModuleType("google.oauth2.credentials")
    c.Credentials = types.SimpleNamespace(from_authorized_user_file=lambda p, s: _Creds())
    r = types.ModuleType("google.auth.transport.requests"); r.Request = object
    d = types.ModuleType("googleapiclient.discovery"); d.build = lambda *a, **k: "SERVICE"
    fl = types.ModuleType("google_auth_oauthlib.flow")

    class Flow:
        goi = 0
        @classmethod
        def from_client_secrets_file(cls, path, scopes):
            cls.goi += 1
            return types.SimpleNamespace(run_local_server=lambda port=0: _Creds())
    fl.InstalledAppFlow = Flow
    mods.update({"google.oauth2.credentials": c, "google.auth.transport.requests": r,
                 "googleapiclient.discovery": d, "google_auth_oauthlib.flow": fl})
    return mods, Flow


class TestDangNhap(unittest.TestCase):
    def setUp(self):
        self.d = Path(tempfile.mkdtemp(prefix="qbot_dn_"))
        self.mods, self.Flow = _gia_google()
        self.p = mock.patch.dict(sys.modules, self.mods)
        self.p.start()
        for m in ("sheet_config", "dang_nhap_google"):
            sys.modules.pop(m, None)
        self.sc = importlib.import_module("sheet_config")
        self.dn = importlib.import_module("dang_nhap_google")
        # sheet_config tìm token cạnh chính file của nó → trỏ sang thư mục tạm
        self.sc.__file__ = str(self.d / "sheet_config.py")

    def tearDown(self):
        self.p.stop()
        shutil.rmtree(self.d, ignore_errors=True)

    def _loi(self):
        with self.assertRaises(self.sc.LoiSheetCauHinh) as cm:
            self.sc._lay_service()
        return str(cm.exception)

    def test_thieu_ca_credentials_bao_ro(self):
        with mock.patch.object(self.sc, "_co_nguoi_ngoi_may", lambda: True):
            msg = self._loi()
        self.assertIn("credentials.json", msg)
        self.assertIn("dang_nhap_google.py", msg)
        self.assertNotIn("Chạy bot một lần", msg, "🔴 lời khuyên không làm theo được")

    def test_chay_nen_khong_mo_trinh_duyet_ma_chi_cach_lam(self):
        (self.d / "credentials.json").write_text("{}")
        with mock.patch.object(self.sc, "_co_nguoi_ngoi_may", lambda: False):
            msg = self._loi()
        self.assertIn("dang_nhap_google.py", msg)
        self.assertEqual(self.Flow.goi, 0, "chạy nền mà mở trình duyệt → treo")

    def test_co_nguoi_ngoi_may_thi_tu_dang_nhap_roi_chay_tiep(self):
        (self.d / "credentials.json").write_text("{}")
        with mock.patch.object(self.sc, "_co_nguoi_ngoi_may", lambda: True):
            sv = self.sc._lay_service()
        self.assertEqual(sv, "SERVICE", "đăng nhập xong phải đọc sheet tiếp luôn")
        self.assertEqual(self.Flow.goi, 1)
        self.assertTrue((self.d / "token.json").exists(), "phải ghi token.json cạnh bot")

    def test_tien_trinh_con_cua_dieu_phoi_khong_tinh_la_co_nguoi(self):
        with mock.patch.dict(os.environ, {"QBOT_SUPERVISED": "1"}):
            self.assertFalse(self.sc._co_nguoi_ngoi_may())
        with mock.patch.dict(os.environ, {"QBOT_TU_DANG_NHAP": "0", "QBOT_SUPERVISED": ""}):
            self.assertFalse(self.sc._co_nguoi_ngoi_may())

    def test_dang_nhap_ghi_token(self):
        (self.d / "credentials.json").write_text("{}")
        p = self.dn.dang_nhap(str(self.d))
        self.assertEqual(json.loads(Path(p).read_text()), {"token": "T"})
        self.assertEqual([f for f in os.listdir(self.d) if f.endswith(".tmp")], [], "không để lại file tạm")

    def test_dang_nhap_thieu_credentials(self):
        with self.assertRaises(FileNotFoundError) as cm:
            self.dn.dang_nhap(str(self.d))
        self.assertIn("Desktop app", str(cm.exception))

    def test_da_co_token_thi_khong_dang_nhap_lai(self):
        (self.d / "token.json").write_text("{}")
        self.assertEqual(self.sc._lay_service(), "SERVICE")
        self.assertEqual(self.Flow.goi, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
