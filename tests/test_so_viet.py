"""
Dấu . / , trong ô SỐ trên sheet — hd_order_multi.py.

Gặp thật: khách gõ vốn "13,467" (ý 13.467) vào cột H → bot dừng với lỗi
"could not convert string to float: '13,467'" vì float() của Python không
hiểu dấu phẩy thập phân. Rộng hơn: dấu . đứng một mình cũng mơ hồ — "13.467"
(giá coin, ý 13.467) và "100.000" (vốn, ý một trăm nghìn) NHÌN GIỐNG HỆT
NHAU, không cách nào đoán đúng cả hai bằng cách nhìn chuỗi số.

Tuyến phòng thủ CHÍNH: get_dat_lenh(..., value_render_option='UNFORMATTED_VALUE')
— Google Sheets tự trả về SỐ THẬT bên dưới ô theo đúng định dạng ô đó (Number/
Percent/…), không qua chuỗi hiển thị nên không còn dấu . / , để đoán sai. Chỉ ô
THẬT SỰ là văn bản (Plain text) mới còn cần _so_viet() làm tuyến phòng thủ phụ.

    python3 tests/test_so_viet.py
"""
import io, os, sys
from unittest import mock

QBOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, QBOT)
os.chdir(QBOT)

import tests.test_hd_order_multi as _base  # noqa: E402  (dựng mock Binance/Google/cst)
M = _base.M


def _gia(**hang):
    """gg_sheet_factory.get_dat_lenh giả — trả đúng hàng ứng với range, chấp
    nhận value_render_option (và mọi kwarg khác) như bản thật."""
    def _get(rng, **kw):
        for tien_to, hang_tra in hang.items():
            if rng.startswith(tien_to):
                return hang_tra
        return []
    return type("G", (), {"get_dat_lenh": staticmethod(_get)})()


# ════════════════════════════════════════════════════════════════════════════
#  Tuyến CHÍNH: đọc sheet bằng UNFORMATTED_VALUE — Google tự trả số thật
# ════════════════════════════════════════════════════════════════════════════
def test_doc_D1_E2_bang_UNFORMATTED_VALUE():
    """Không còn đọc chuỗi hiển thị cho vốn D1/D2/E2 — tránh đoán sai dấu câu."""
    src = io.open(os.path.join(QBOT, "hd_order_multi.py"), encoding="utf-8").read()
    assert 'get_dat_lenh("D1:E2", value_render_option="UNFORMATTED_VALUE")' in src


def test_doc_dong_lenh_bang_UNFORMATTED_VALUE():
    """Không còn đọc chuỗi hiển thị cho giá D, đòn bẩy B, callback C/G, vốn H."""
    src = io.open(os.path.join(QBOT, "hd_order_multi.py"), encoding="utf-8").read()
    assert 'value_render_option="UNFORMATTED_VALUE")' in src.split(
        'don_bay = gg_sheet_factory.get_dat_lenh(f"A{start_row}:Z{end_row}"')[1][:80]


def test_get_dat_lenh_that_truyen_dung_tham_so():
    """gg_sheet_factory.get_dat_lenh() thật phải nhận value_render_option và
    CHUYỂN TIẾP thành valueRenderOption sang lệnh gọi Google API — giống hệt
    cách get_cho_va_khop() đã làm từ trước (không phải hàm mới tự chế)."""
    src = io.open(os.path.join(QBOT, "gg_sheet_factory.py"), encoding="utf-8").read()
    dinh_nghia = src[src.index("def get_dat_lenh("):src.index("def get_cho_va_khop(")]
    assert "def get_dat_lenh(range, value_render_option=None):" in dinh_nghia
    assert 'kwargs["valueRenderOption"] = value_render_option' in dinh_nghia
    assert ".get(**kwargs)" in dinh_nghia, "phải truyền kwargs (gồm valueRenderOption) vào lệnh gọi API thật"


# ════════════════════════════════════════════════════════════════════════════
#  D1 (% vốn): ô Percent-format trả THẲNG phân số; ô số trần vẫn kiểu cũ /100
# ════════════════════════════════════════════════════════════════════════════
def test_D1_da_la_phan_so_tu_o_dinh_dang_Percent():
    """Gõ '3%' vào ô D1 → Sheets tự đổi ô thành Percent → UNFORMATTED_VALUE trả
    THẲNG 0.03 (không còn dấu %). KHÔNG được chia 100 lần nữa (mới đúng 3%)."""
    with mock.patch.object(M, "gg_sheet_factory", _gia(**{"D1:E2": [[0.03], [10, 1000]]})):
        d1, d2, e2, loi = M.get_capital_config()
    assert not loi
    assert abs(d1 - 0.03) < 1e-9, f"đọc thành {d1:.4%} thay vì đúng 3%"


def test_D1_so_tran_kieu_cu_van_chia_100():
    """Ô D1 KHÔNG định dạng Percent, gõ số trần '3' ý là '3%' (quy ước cũ của
    tài liệu) → vẫn phải chia 100 như trước, không đổi hành vi cũ."""
    with mock.patch.object(M, "gg_sheet_factory", _gia(**{"D1:E2": [[3], [10, 1000]]})):
        d1, d2, e2, loi = M.get_capital_config()
    assert not loi
    assert abs(d1 - 0.03) < 1e-9


def test_D1_dau_phay_kieu_Viet_van_doc_dung():
    """Ô D1 là văn bản (hiếm) gõ '3,5%' — vẫn qua được nhờ _so_viet (tuyến phụ)."""
    with mock.patch.object(M, "gg_sheet_factory", _gia(**{"D1:E2": [["3,5%"], ["10,5", "1000,25"]]})):
        d1, d2, e2, loi = M.get_capital_config()
    assert not loi
    assert abs(d1 - 0.035) < 1e-9
    assert d2 == 10.5
    assert e2 == 1000.25


# ════════════════════════════════════════════════════════════════════════════
#  _so_viet — tuyến phòng thủ PHỤ, cho ô THẬT SỰ là văn bản
# ════════════════════════════════════════════════════════════════════════════
def test_so_viet_doi_phay_thanh_cham():
    assert M._so_viet("13,467") == 13.467
    assert M._so_viet(" 2,5 ") == 2.5
    assert M._so_viet("13.467") == 13.467      # kiểu US vẫn đọc được
    assert M._so_viet(13.467) == 13.467        # số thật (int/float) từ Sheets — không phải chuỗi


def test_is_number_nhan_dau_phay():
    assert M.is_number("13,467")
    assert M.is_number("2,5")
    assert not M.is_number("abc")
    assert not M.is_number("")


def test_dau_cham_dung_mot_minh_van_mo_ho_ghi_nhan():
    """Không có cách nào phân biệt máy móc '13.467' (giá, ý 13.467) với
    '100.000' (vốn, ý 100 nghìn) — cùng hình thức. _so_viet CỐ Ý giữ dấu chấm
    đơn là số thập phân (khớp giá coin kiểu Binance): không tự đoán thành hàng
    nghìn vì đoán sai còn nguy hiểm hơn — ĐÂY LÀ LÝ DO tuyến UNFORMATTED_VALUE
    ở trên phải là tuyến chính, _so_viet chỉ nên là lưới an toàn cuối."""
    assert M._so_viet("13.467") == 13.467
    assert M._so_viet("100.000") == 100.0


def test_dau_cham_va_phay_cung_luc_bao_loi_ro_khong_doan_lieu():
    """'13.467,55' (đủ cả . và ,) — _so_viet KHÔNG đoán bừa, báo lỗi rõ để dòng
    đó bị bỏ qua thay vì đặt lệnh với số sai."""
    try:
        M._so_viet("13.467,55")
        assert False, "phải báo lỗi, không được đoán ra một số nào đó"
    except ValueError:
        pass
    assert not M.is_number("13.467,55")


def test_read_cell_number_gia_va_callback_dau_phay():
    d = ["ATOM/USDT", "1", "", "13,467", "", "1,9", "2,5", "10"]
    assert M._read_cell_number(d, 3) == 13.467   # cột D — giá vào
    assert M._read_cell_number(d, 5) == 1.9       # cột F — cắt lỗ / callback
    assert M._read_cell_number(d, 6) == 2.5       # cột G


def test_von_cot_H_dau_phay():
    d = ["ATOM/USDT", "1", "", "2.0", "", "", "", "13,467"]  # H = idx 7
    assert M.compute_capital(d, 7, None, None, None) == 13.467


def test_von_cot_H_so_that_tu_UNFORMATTED_VALUE():
    """Với UNFORMATTED_VALUE, ô Number trả về int/float THẬT, không phải chuỗi
    — compute_capital phải nhận đúng, không cần round-trip qua chuỗi."""
    d = ["ATOM/USDT", "1", "", "2.0", "", "", "", 13467.55]  # H = idx 7, số thật
    assert M.compute_capital(d, 7, None, None, None) == 13467.55


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
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    npass = nfail = 0
    for name, fn in tests:
        try:
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
