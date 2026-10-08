"""
hd_order_multi: N/O/P của tab "Chờ và khớp" TRỐNG → tự tính SL/TP mặc định trong bộ nhớ.

Trước 08/10/2026 hd_update_cho_va_khop ghi gợi ý này lên sheet (và đè số khách gõ khi
mã tạm vắng). Nay bot đó chỉ ghi A–I → hd_order_multi phải tự tính, nếu không vị thế
mới KHÔNG có cắt lỗ.

    python3 tests/test_sltp_mac_dinh_multi.py
"""
import os, sys
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import tests.test_hd_order_multi as _base  # noqa: E402  (dựng mock Binance/Google/cst)
M = _base.M

LEGS = [{'idx': 2, 'type': 'stop_market', 'type_col': None, 'role': 'exit', 'source': 'cho_va_khop',
         'col': 13, 'aux': None, 'pct_col': None},
        {'idx': 3, 'type': 'limit', 'type_col': None, 'role': 'exit', 'source': 'cho_va_khop',
         'col': 14, 'aux': None, 'pct_col': None}]


def _dong(n="", o="", p=""):
    # A..I của bot + J..P của người dùng
    return ["BTC/USDT", "LONG", "N", "Y", 100.0, 10, "N", "N", 0, "", "", "", "", n, o, p]


def _chay(dong, fill=True, allow="N"):
    thay = []

    def _plan_row(legs, d, *a, **k):
        thay.append(list(d))
        return [], []
    with mock.patch.object(M.cst, 'fill_default_cho_va_khop', fill, create=True), \
         mock.patch.object(M.cst, 'default_sl_rate_layer_1', 2.0, create=True), \
         mock.patch.object(M.cst, 'default_tp_rate_layer_1', 3.0, create=True), \
         mock.patch.object(M.cst, 'default_allow_order', allow, create=True), \
         mock.patch.object(M, 'is_symbol_tradeable', lambda s: (True, '', 'BTC/USDT:USDT')), \
         mock.patch.object(M, '_vi_the', lambda s: (1.0, 100.0)), \
         mock.patch.object(M, 'build_symbol_snapshot', lambda s, n: ([], True)), \
         mock.patch.object(M.exchange, 'fetch_ticker', lambda s: {'last': 100.5}, create=True), \
         mock.patch.object(M, 'plan_row', _plan_row), \
         mock.patch.object(M, 'huy_lenh_cu_roi_dat', lambda *a, **k: []):
        M.scan_cho_va_khop_legs(LEGS, rows=[dong])
    return thay


def test_o_trong_thi_tu_tinh_SL_TP():
    d = _chay(_dong(), allow="Y")
    assert d and d[0][13:16] == [98.0, 103.0, "Y"], d


def test_P_trong_va_default_N_thi_khong_dat():
    assert _chay(_dong()) == [], "default_allow_order=N → P trống = không đặt (như trước)"


def test_so_khach_go_giu_nguyen():
    d = _chay(_dong(n=95, p="Y"))
    assert d[0][13:16] == [95, 103.0, "Y"], d[0][13:16]


def test_P_N_thi_khong_dat_du_default_Y():
    assert _chay(_dong(p="N"), allow="Y") == []


def test_tat_fill_default_thi_khong_tu_tinh():
    d = _chay(_dong(p="Y"), fill=False)
    assert d[0][13:15] == ["", ""], "fill_default_cho_va_khop=false → không bịa số"


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    loi = 0
    for n, f in tests:
        try:
            f(); print(f"  ✅ {n}")
        except Exception as e:
            loi += 1; print(f"  ❌ {n} — {type(e).__name__}: {e}")
    print(f"\n===== KẾT QUẢ: {len(tests) - loi} PASS / {loi} FAIL =====")
    sys.exit(1 if loi else 0)
