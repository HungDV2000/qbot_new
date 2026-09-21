"""
Dấu phẩy kiểu Việt trong ô sheet — hd_order_multi.py.

Gặp thật: khách gõ vốn "13,467" (ý 13.467) vào cột H → bot dừng với lỗi
"could not convert string to float: '13,467'" vì float() của Python không
hiểu dấu phẩy thập phân. sheet_config.py (sheet tổng) đã đổi phẩy→chấm từ
trước; hd_order_multi.py đọc tab ĐẶT LỆNH / Chờ và khớp (giá D/N/O, callback G,
vốn D1/D2/E2/H) thì chưa — vá qua hàm dùng chung _so_viet().

    python3 tests/test_so_viet.py
"""
import io, os, sys

QBOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, QBOT)
os.chdir(QBOT)

import tests.test_hd_order_multi as _base  # noqa: E402  (dựng mock Binance/Google/cst)
M = _base.M


def test_so_viet_doi_phay_thanh_cham():
    assert M._so_viet("13,467") == 13.467
    assert M._so_viet(" 2,5 ") == 2.5
    assert M._so_viet("13.467") == 13.467      # kiểu US vẫn đọc được
    assert M._so_viet(13.467) == 13.467        # số thật (không phải chuỗi) từ Sheet


def test_is_number_nhan_dau_phay():
    assert M.is_number("13,467")
    assert M.is_number("2,5")
    assert not M.is_number("abc")
    assert not M.is_number("")


def test_read_cell_number_gia_va_callback_dau_phay():
    d = ["ATOM/USDT", "1", "", "13,467", "", "1,9", "2,5", "10"]
    assert M._read_cell_number(d, 3) == 13.467   # cột D — giá vào
    assert M._read_cell_number(d, 5) == 1.9       # cột F — cắt lỗ / callback
    assert M._read_cell_number(d, 6) == 2.5       # cột G


def test_von_cot_H_dau_phay():
    d = ["ATOM/USDT", "1", "", "2.0", "", "", "", "13,467"]  # H = idx 7
    assert M.compute_capital(d, 7, None, None, None) == 13.467


def test_von_D1_D2_E2_dau_phay(monkeypatch):
    monkeypatch.setattr(M, "gg_sheet_factory",
                        type("G", (), {"get_dat_lenh": staticmethod(
                            lambda rng: [["3,5%"], ["10,5", "1000,25"]])})())
    d1, d2, e2, loi = M.get_capital_config()
    assert not loi
    assert abs(d1 - 0.035) < 1e-9
    assert d2 == 10.5
    assert e2 == 1000.25


def test_don_bay_dau_phay_khong_crash_nua():
    """Trước đây is_number() (đã hiểu dấu phẩy) đi qua được, nhưng dòng SAU ĐÓ
    còn gọi float(lev_str) THẲNG (không đổi phẩy) → crash ngay dòng kế tiếp.
    Đòn bẩy '5,5' phải nhất quán với is_number: qua được cả hai bước."""
    assert M.is_number("5,5")
    assert M._so_viet("5,5") == 5.5
    try:
        float("5,5")
        assert False, "float() gốc của Python phải KHÔNG hiểu dấu phẩy (nếu ra thì Python đã đổi)"
    except ValueError:
        pass  # đúng như mong đợi — chứng minh nếu code còn gọi float() thẳng sẽ crash


def test_khong_con_cho_nao_goi_float_lev_str_thang():
    """Soát lại nguồn: is_number(lev_str) dùng _so_viet, các bước xử lý lev_str
    sau đó phải cũng dùng _so_viet, không được còn float(lev_str) trần trụi."""
    src = io.open(os.path.join(QBOT, "hd_order_multi.py"), encoding="utf-8").read()
    assert "float(lev_str)" not in src, "còn chỗ gọi float(lev_str) thẳng — sẽ crash với đòn bẩy kiểu '5,5'"
    assert src.count("_so_viet(lev_str)") == 2, "đòn bẩy phải đổi phẩy ở CẢ bước kiểm tra lẫn bước setLeverage"


def test_plan_row_gia_dau_phay_dat_dung_lenh():
    legs = [{'idx': 1, 'type': 'limit', 'role': 'entry', 'col': 3, 'aux': None, 'pct_col': None}]
    d = ['ATOM/USDT', '1', '', '1,9', '', '', '', '10']  # D = "1,9" < giá hiện tại 2.083
    plans, skips = M.plan_row(legs, d, 0, [], True, 10, 2.083, 'buy')
    assert plans and plans[0]['price'] == 1.9, (plans, skips)


if __name__ == "__main__":
    import unittest.mock as mock

    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    npass = nfail = 0
    for name, fn in tests:
        try:
            if name == "test_von_D1_D2_E2_dau_phay":
                with mock.patch.object(M, "gg_sheet_factory",
                                       type("G", (), {"get_dat_lenh": staticmethod(
                                           lambda rng: [["3,5%"], ["10,5", "1000,25"]])})()):
                    d1, d2, e2, loi = M.get_capital_config()
                    assert not loi
                    assert abs(d1 - 0.035) < 1e-9
                    assert d2 == 10.5
                    assert e2 == 1000.25
            else:
                fn()
            npass += 1
            print(f"  ✅ {name}")
        except AssertionError as e:
            nfail += 1
            print(f"  ❌ {name}  — {e}")
        except Exception as e:
            nfail += 1
            print(f"  💥 {name}  — LỖI: {type(e).__name__}: {e}")
    print(f"\n===== KẾT QUẢ: {npass} PASS / {nfail} FAIL / {len(tests)} test =====")
    sys.exit(1 if nfail else 0)
