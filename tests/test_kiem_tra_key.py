"""kiem_tra_key.py — kết luận đúng nguyên nhân lỗi key. Không gọi mạng.

    python3 tests/test_kiem_tra_key.py
"""
import os, sys, types, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["QBOT_GIU_CUA_SO"] = "0"
import kiem_tra_key as K

KEY = "A" * 64
SEC = "b" * 64


class TestSoiChuoi(unittest.TestCase):
    def test_sach(self):
        self.assertEqual(K.soi_chuoi("k", KEY), [])

    def test_ky_tu_an_va_do_dai(self):
        v = K.soi_chuoi("s", SEC[:-1] + "​")
        self.assertTrue(any("ký tự lạ" in x for x in v))
        self.assertEqual(K.soi_chuoi("s", SEC + " ")[0][:6], "dài 65")

    def test_trong(self):
        self.assertEqual(K.soi_chuoi("s", ""), ["TRỐNG"])


class TestKetLuan(unittest.TestCase):
    def test_ok(self):
        self.assertTrue(K.ket_luan([], (True, "OK"), (True, "OK")).startswith("✅"))

    def test_1022_secret_khong_khop(self):
        kl = K.ket_luan([], (False, "-1022 Signature for this request is not valid."), (False, "-1022 x"))
        self.assertIn("Secret KHÔNG khớp", kl)

    def test_tu_ky_ok_ccxt_loi_thi_do_thu_vien(self):
        kl = K.ket_luan([], (True, "OK"), (False, "-1022 x"))
        self.assertIn("ccxt", kl)
        self.assertIn("không phải do key", kl)

    def test_2015_ip(self):
        self.assertIn("IP", K.ket_luan([], (False, "-2015 Invalid API-key, IP"), (False, "-2015")))


class _Resp:
    def __init__(self, code, body): self.status_code, self._b = code, body
    def json(self): return self._b


class TestThuTuKy(unittest.TestCase):
    def test_ky_dung_chuan_binance(self):
        """Chữ ký phải là HMAC-SHA256(secret, query) — đúng cách bot ký."""
        import hmac, hashlib, urllib.parse
        da_goi = {}

        def get(url, headers=None, timeout=None):
            if url.endswith("/fapi/v1/time"):
                return _Resp(200, {"serverTime": 1791437025589})
            da_goi["url"], da_goi["h"] = url, headers
            return _Resp(200, [])
        req = types.SimpleNamespace(get=get)
        self.assertEqual(K.thu_tu_ky(req, KEY, SEC), (True, "OK"))
        q = urllib.parse.urlencode({"timestamp": 1791437025589, "recvWindow": 60000})
        sig = hmac.new(SEC.encode(), q.encode(), hashlib.sha256).hexdigest()
        self.assertTrue(da_goi["url"].endswith(f"?{q}&signature={sig}"))
        self.assertEqual(da_goi["h"], {"X-MBX-APIKEY": KEY})

    def test_loi_binance(self):
        def get(url, headers=None, timeout=None):
            if url.endswith("/fapi/v1/time"):
                return _Resp(200, {"serverTime": 1})
            return _Resp(400, {"code": -1022, "msg": "Signature for this request is not valid."})
        ok, mt = K.thu_tu_ky(types.SimpleNamespace(get=get), KEY, SEC)
        self.assertFalse(ok)
        self.assertIn("-1022", mt)


if __name__ == "__main__":
    unittest.main(verbosity=2)
