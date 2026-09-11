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


class RefreshError(Exception):
    pass


class _Creds:
    """Nội dung token.json quyết định trạng thái: HONG / HET_HAN / MANG_LOI / khác = tốt."""
    def __init__(self, kieu="tot"):
        self.kieu = kieu
        self.valid = kieu == "tot"
        self.expired = kieu in ("HET_HAN", "MANG_LOI")
        self.refresh_token = "r" if self.expired else None

    def refresh(self, req):
        if self.kieu == "HET_HAN":
            raise RefreshError("invalid_grant: Token has been expired or revoked.")
        raise OSError("mất mạng")

    def to_json(self): return json.dumps({"token": "T"})


def _doc_token(path, scopes):
    txt = open(path).read()
    if txt == "HONG":
        raise ValueError("không phải JSON")
    return _Creds(txt if txt in ("HET_HAN", "MANG_LOI") else "tot")


def _gia_google():
    mods = {}
    for ten in ("google", "google.oauth2", "google.auth", "google.auth.transport",
                "googleapiclient", "google_auth_oauthlib"):
        mods[ten] = types.ModuleType(ten)
    c = types.ModuleType("google.oauth2.credentials")
    c.Credentials = types.SimpleNamespace(from_authorized_user_file=_doc_token)
    ex = types.ModuleType("google.auth.exceptions"); ex.RefreshError = RefreshError
    mods["google.auth.exceptions"] = ex
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

    # ── Token cũ hỏng / bị thu hồi → tự đăng nhập lại ─────────────────────────
    def _co_token(self, noi_dung):
        (self.d / "credentials.json").write_text("{}")
        (self.d / "token.json").write_text(noi_dung)

    def test_token_hong_thi_tu_dang_nhap_lai(self):
        self._co_token("HONG")
        with mock.patch.object(self.sc, "_co_nguoi_ngoi_may", lambda: True):
            self.assertEqual(self.sc._lay_service(), "SERVICE")
        self.assertEqual(self.Flow.goi, 1)

    def test_token_bi_google_thu_hoi_thi_tu_dang_nhap_lai(self):
        self._co_token("HET_HAN")
        with mock.patch.object(self.sc, "_co_nguoi_ngoi_may", lambda: True):
            self.assertEqual(self.sc._lay_service(), "SERVICE")
        self.assertEqual(self.Flow.goi, 1)

    def test_mat_mang_luc_lam_moi_KHONG_bat_dang_nhap(self):
        self._co_token("MANG_LOI")
        with mock.patch.object(self.sc, "_co_nguoi_ngoi_may", lambda: True):
            with self.assertRaises(self.sc.LoiDocSheet):
                self.sc._lay_service()
        self.assertEqual(self.Flow.goi, 0, "mạng chập chờn mà bắt đăng nhập lại là phiền vô ích")

    def test_token_hong_luc_chay_nen_thi_bao_cach_lam(self):
        self._co_token("HET_HAN")
        with mock.patch.object(self.sc, "_co_nguoi_ngoi_may", lambda: False):
            msg = self._loi()
        self.assertIn("dang_nhap_google.py", msg)
        self.assertEqual(self.Flow.goi, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
