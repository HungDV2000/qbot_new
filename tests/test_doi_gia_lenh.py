"""
Đổi giá trên sheet khi lệnh cũ còn treo — hd_order_multi.py (bug 3 + bug 4, 09/2026).

Bug 3 — khách gặp thật: đặt lệnh 1 (trailing vào) mà mỗi chu kỳ lại sinh thêm 1 lệnh.
  Chống trùng chỉ so CÙNG giá → giá D đổi (sửa tay hoặc công thức tự nhảy) là lệnh cũ
  "không khớp" → đặt thêm. Nay: allow_dca=false thì còn lệnh vào cũ lệch giá → KHÔNG
  đặt, chỉ báo Telegram 1 lần ("tick J để xoá lệnh cũ").

Bug 4 — đổi giá SL/TP (cột N/O): bot không gỡ lệnh cũ.
  SL closePosition → Binance từ chối cái thứ 2 (SL vẫn ở giá cũ); TP → thành 2 lệnh.
  Nay: huỷ lệnh cũ RỒI đặt lệnh mới; mỗi mã giữ đúng 1 SL + 1 TP.

    python3 tests/test_doi_gia_lenh.py
"""
import os, sys
from unittest import mock

QBOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, QBOT)
os.chdir(QBOT)

import tests.test_hd_order_multi as _base  # noqa: E402  (dựng mock Binance/Google/cst)
M = _base.M

SL_LEG = _base.SL_LEG      # stop_market, cột N
TP_LEG = _base.TP_LEG      # limit, cột O
TRAIL_VAO = {'idx': 1, 'type': 'trailing', 'type_col': None, 'role': 'entry',
             'source': 'dat_lenh', 'col': 3, 'aux': 2, 'pct_col': None}   # D kích hoạt, C callback


def _vao_cho(gia, fam='trailing', oid='A1', algo=True):
    return {'family': fam, 'loai': 'ENTRY', 'side': 'buy', 'reduce_only': False, 'price': gia,
            'amount': 41.0, 'id': oid, 'close_position': False, 'algo': algo}


def _sl(gia, oid='SL1', cp=True):
    return {'family': 'stop', 'loai': 'SL', 'side': 'sell', 'reduce_only': True, 'price': gia,
            'amount': None, 'id': oid, 'close_position': cp, 'algo': True}


def _tp(gia, oid='TP1', kl=7.2):
    return {'family': 'limit', 'loai': 'TP', 'side': 'sell', 'reduce_only': True, 'price': gia,
            'amount': kl, 'id': oid, 'close_position': False, 'algo': False}


def _dl(d_gia):
    """Dòng ĐẶT LỆNH: A mã · B đòn bẩy · C callback · D giá kích hoạt · H vốn."""
    return ['ARB/USDT', '20', '1', d_gia, '', '', '', '6']


def _cvk(n, o):
    r = [""] * 17
    r[0] = "ATOM/USDT"; r[1] = "LONG"; r[3] = "Y"; r[13] = n; r[14] = o; r[15] = "Y"
    return r


# ════════════════════════════════════════════════════════════════════════════
#  BUG 3 — giá D đổi, lệnh vào cũ còn treo
# ════════════════════════════════════════════════════════════════════════════
def test_bug3_gia_D_doi_KHONG_dat_them_lenh_vao():
    """Tái hiện đúng log khách: trailing cũ kích hoạt 0.13402, D nhảy sang 0.13390."""
    cb = []
    plans, skips = M.plan_row([TRAIL_VAO], _dl('0.13390'), 0, [_vao_cho(0.13402)], True, 12,
                              0.1411, 'buy', canh_bao_out=cb)
    assert plans == [], f"🔴 vẫn đặt thêm lệnh vào: {plans}"
    assert 'tick J' in skips[0][1]
    assert cb == [(1, 0.1339, 0.13402)], cb


def test_bug3_lenh_vao_cu_limit_cung_chan_trailing_moi():
    """Đổi kiểu lệnh (limit → trailing) cũng không được sinh lệnh thứ 2."""
    plans, _ = M.plan_row([TRAIL_VAO], _dl('0.13390'), 0, [_vao_cho(0.13390, fam='limit', algo=False)],
                          True, 6, 0.1411, 'buy')
    assert plans == []


def test_bug3_cung_gia_van_chong_trung_khong_canh_bao():
    cb = []
    plans, skips = M.plan_row([TRAIL_VAO], _dl('0.13402'), 0, [_vao_cho(0.13402)], True, 12,
                              0.1411, 'buy', canh_bao_out=cb)
    assert plans == [] and cb == [] and 'tương tự' in skips[0][1]


def test_bug3_chua_co_lenh_thi_dat_binh_thuong():
    plans, _ = M.plan_row([TRAIL_VAO], _dl('0.13390'), 0, [], True, 12, 0.1411, 'buy')
    assert len(plans) == 1 and plans[0]['price'] == 0.1339


def test_bug3_lenh_SL_TP_khong_tinh_la_lenh_vao():
    """Lệnh reduceOnly (SL/TP của mã) không chặn lệnh vào."""
    plans, _ = M.plan_row([TRAIL_VAO], _dl('0.13390'), 0, [_sl(0.12)], True, 12, 0.1411, 'buy')
    assert len(plans) == 1


def test_bug3_khong_doc_duoc_algo_thi_khong_vao():
    """Không đọc được Algo API = không biết trailing cũ còn không → đứng im."""
    leg = dict(TRAIL_VAO, type='limit')
    plans, skips = M.plan_row([leg], _dl('0.13390'), 0, [], False, 6, 0.1411, 'buy')
    assert plans == [] and 'algo' in skips[0][1]


def test_bug3_allow_dca_bat_thi_van_dat_them():
    """allow_dca=true là người dùng CHỦ ĐỘNG cho rải lệnh — giữ hành vi cũ."""
    plans, _ = M.plan_row([TRAIL_VAO], _dl('0.13390'), 0, [_vao_cho(0.13402)], True, 12,
                          0.1411, 'buy', allow_dca=True)
    assert len(plans) == 1


def test_bug3_canh_bao_telegram_mot_lan_moi_lenh_cu_du_D_nhay():
    """Khách 07/10: D là công thức nhảy theo giá (5330 → 5345…) → trước đây 5 phút 1 tin.
    Nay: 1 tin cho mỗi lệnh cũ; D nhảy tiếp không báo; lệnh cũ KHÁC thì báo; quá 1 giờ nhắc lại."""
    M._DA_CANH_BAO_GIA_D.clear()
    gui = []
    lenh = dict(_vao_cho(0.13402, oid=111))
    with mock.patch.object(M.telegram_factory, 'send_tele', lambda msg, *a, **k: gui.append(msg)):
        assert M.canh_bao_gia_d_doi('ARB/USDT', 0.1339, 0.13402, lenh)
        assert not M.canh_bao_gia_d_doi('ARB/USDT', 0.1339, 0.13402, lenh)   # vòng sau
        assert not M.canh_bao_gia_d_doi('ARB/USDT', 0.1337, 0.13402, lenh)   # D nhảy tiếp
        assert M.canh_bao_gia_d_doi('ARB/USDT', 0.1337, 0.13500, dict(_vao_cho(0.135, oid=222)))
        M._DA_CANH_BAO_GIA_D['ARB/USDT'] = (222, M.time.time() - M.NHAC_LAI_GIA_D_GIAY - 1)
        assert M.canh_bao_gia_d_doi('ARB/USDT', 0.1336, 0.13500, dict(_vao_cho(0.135, oid=222)))
    assert len(gui) == 3 and 'tick cột J' in gui[0]


def test_canh_bao_ghi_du_loai_lenh_id_gio_tao_de_tim_tren_app():
    """Khách 07/10: bot báo 'lệnh cũ @ 5265 còn treo' mà không thấy trên app — tin chỉ có
    giá, không biết tìm lệnh gì. Nay ghi loại lệnh, chiều, KL, nhóm (điều kiện/thường), id, giờ tạo."""
    M._DA_CANH_BAO_GIA_D.clear()
    gui = []
    lenh = dict(_vao_cho(5291.0, oid=4000001952112211), side='sell', amount=7.3,
                kieu='TRAILING_STOP_MARKET', tao=1791338843000)
    with mock.patch.object(M.telegram_factory, 'send_tele', lambda msg, *a, **k: gui.append(msg)):
        M.canh_bao_gia_d_doi('BTCDOM/USDT:USDT', 5277.7, 5291.0, M.tim_lenh_vao([lenh], 5291.0))
    for can in ('TRAILING_STOP_MARKET SELL', 'KL 7.3', 'ĐIỀU KIỆN', 'id=4000001952112211', 'tạo '):
        assert can in gui[0], (can, gui[0])


# ════════════════════════════════════════════════════════════════════════════
#  BUG 4 — đổi giá SL/TP ở cột N/O
# ════════════════════════════════════════════════════════════════════════════
def test_bug4_doi_N_O_thi_huy_lenh_cu_roi_dat_moi():
    """Tái hiện: SL 1.30 (closePosition) + TP 1.50 → người dùng sửa N=1.32, O=1.55."""
    huy = []
    plans, _ = M.plan_row([SL_LEG, TP_LEG], _cvk(1.32, 1.55), 7.2, [_sl(1.30), _tp(1.50)], True,
                          None, 1.413, 'buy', allow_close_position=True, resize_exits=True,
                          cancel_out=huy)
    assert sorted(h[0] for h in huy) == ['SL1', 'TP1'], f"🔴 không huỷ lệnh cũ: {huy}"
    assert all(h[4] == 'gia' for h in huy)
    assert sorted(p['price'] for p in plans) == [1.32, 1.55]


def test_bug4_khong_doi_gia_thi_khong_dung_vao():
    huy = []
    plans, _ = M.plan_row([SL_LEG, TP_LEG], _cvk(1.30, 1.50), 7.2, [_sl(1.30), _tp(1.50)], True,
                          None, 1.413, 'buy', allow_close_position=True, resize_exits=True,
                          cancel_out=huy)
    assert plans == [] and huy == []


def test_bug4_TP_trung_doi_tu_truoc_thi_don_bot_1():
    """Khách đang có 2 TP giống nhau (hậu quả bug cũ) → giữ 1, huỷ lệnh thừa."""
    huy = []
    plans, _ = M.plan_row([TP_LEG], _cvk(1.30, 1.50), 7.2, [_tp(1.50, 'TP1'), _tp(1.50, 'TP2')],
                          True, None, 1.413, 'buy', resize_exits=True, cancel_out=huy)
    assert [h[0] for h in huy] == ['TP2'] and plans == []


def test_bug4_SL_moi_vuot_gia_hien_tai_thi_giu_SL_cu():
    """LONG, giá 1.413 mà gõ N=1.45 → SL mới sẽ bị Binance từ chối. KHÔNG được huỷ
    SL cũ rồi để vị thế trần trụi."""
    huy = []
    plans, skips = M.plan_row([SL_LEG], _cvk(1.45, ''), 7.2, [_sl(1.30)], True, None, 1.413,
                              'buy', allow_close_position=True, cancel_out=huy)
    assert plans == [] and huy == [] and 'giữ lệnh cũ' in skips[0][1]


def test_bug4_pha_khong_huy_duoc_thi_khong_dat_chong():
    """cancel_out=None (caller không huỷ được) → bỏ leg, không đặt chồng lên lệnh cũ."""
    plans, _ = M.plan_row([TP_LEG], _cvk(1.30, 1.55), 7.2, [_tp(1.50)], True, None, 1.413, 'buy')
    assert plans == []


def test_bug4_nhieu_nac_TP_chi_go_nac_bi_doi():
    """2 leg TP limit (O=1.52 — vừa sửa từ 1.50, P=1.60 — giữ nguyên): chỉ gỡ lệnh 1.50."""
    tp2 = dict(TP_LEG, idx=4, col=16)
    d = _cvk(1.30, 1.52) ; d[16] = 1.60
    huy = []
    plans, _ = M.plan_row([TP_LEG, tp2], d, 7.2, [_tp(1.50, 'TPa'), _tp(1.60, 'TPb')], True,
                          None, 1.413, 'buy', cancel_out=huy)
    assert [h[0] for h in huy] == ['TPa'], huy
    assert [p['price'] for p in plans] == [1.52]


def test_bug4_short_doi_SL():
    huy = []
    sl_short = dict(_sl(1.50), side='buy')
    plans, _ = M.plan_row([SL_LEG], _cvk(1.48, ''), -7.2, [sl_short], True, None, 1.413, 'sell',
                          allow_close_position=True, cancel_out=huy)
    assert [h[0] for h in huy] == ['SL1'] and plans[0]['price'] == 1.48 and plans[0]['side'] == 'buy'


# ── thực thi: huỷ đúng API rồi mới đặt ──────────────────────────────────────
class _Ex:
    def __init__(self, loi=False):
        self.huy, self.loi = [], loi
    def cancel_order(self, oid, sym):
        if self.loi:
            raise RuntimeError("Unknown order")
        self.huy.append(oid)


def _chay(snap, can_huy, plans, ex, algo_ok=True, dat_ok=True):
    algo_huy, dat, tele = [], [], []
    bfd = sys.modules['binance_futures_direct']
    with mock.patch.object(M, 'exchange', ex), \
         mock.patch.object(bfd, 'cancel_algo_order',
                           lambda s, i: algo_huy.append(i) or algo_ok, create=True), \
         mock.patch.object(M, '_place_order', lambda s, p, tag='': dat.append(p['price']) or dat_ok), \
         mock.patch.object(M.telegram_factory, 'send_tele', lambda m, *a, **k: tele.append(m)):
        M.huy_lenh_cu_roi_dat('ATOM/USDT', snap, can_huy, plans)
    return algo_huy, dat, tele


def test_bug4_SL_algo_huy_qua_Algo_API_TP_qua_ccxt():
    snap = [_sl(1.30), _tp(1.50)]
    can = [('SL1', 2, 1.30, 1.32, 'gia'), ('TP1', 3, 1.50, 1.55, 'gia')]
    plans = [{'leg_idx': 2, 'price': 1.32}, {'leg_idx': 3, 'price': 1.55}]
    ex = _Ex()
    algo_huy, dat, tele = _chay(snap, can, plans, ex)
    assert algo_huy == ['SL1'] and ex.huy == ['TP1'] and dat == [1.32, 1.55] and tele == []


def test_bug4_huy_loi_thi_khong_dat_lenh_moi_cua_leg_do():
    snap = [_tp(1.50)]
    algo_huy, dat, _ = _chay(snap, [('TP1', 3, 1.50, 1.55, 'gia')],
                             [{'leg_idx': 3, 'price': 1.55}], _Ex(loi=True))
    assert dat == [], "🔴 huỷ lỗi mà vẫn đặt → 2 TP"


def test_bug4_da_huy_ma_dat_moi_loi_thi_bao_gap():
    snap = [_sl(1.30)]
    _, dat, tele = _chay(snap, [('SL1', 2, 1.30, 1.32, 'gia')], [{'leg_idx': 2, 'price': 1.32}],
                         _Ex(), dat_ok=False)
    assert dat == [1.32] and tele and 'KHÔNG CÓ' in tele[0]


# ── hd_order_123 (SL stop N + TP trailing O) ────────────────────────────────
def _k(n, o, snap, huy):
    d = ['ATOM/USDT', 'LONG', 'N', 'Y', 2.0, 5, 'N', 'N', 0, '', '', '', '', n, o, 'Y']
    return M.ke_hoach_123(d, 10, 2.0, 2.1, snap, True, 1.0, 2.0, cancel_out=huy)


def _tp_trail(gia, oid='TR1'):
    return {'family': 'trailing', 'loai': 'TP', 'side': 'sell', 'reduce_only': True, 'price': gia,
            'amount': 10, 'id': oid, 'close_position': False, 'algo': True}


def test_bug4_123_doi_N_O_thi_dat_lai():
    huy = []
    plans, _ = _k(1.85, 2.4, [_sl(1.8), _tp_trail(2.3)], huy)
    assert sorted(h[0] for h in huy) == ['SL1', 'TR1']
    assert sorted((p['type'], p['price']) for p in plans) == [('stop_market', 1.85), ('trailing', 2.4)]


def test_bug4_123_giu_nguyen_khi_khong_doi():
    huy = []
    plans, _ = _k(1.8, 2.3, [_sl(1.8), _tp_trail(2.3)], huy)
    assert plans == [] and huy == []


def test_bug4_123_N_trong_hoac_O_NGAY_thi_khong_dung():
    """N trống (SL tính từ %SL) / O = NGAY (kích hoạt theo giá chạy) → không có giá
    cố định để so → giữ lệnh cũ như trước."""
    huy = []
    plans, _ = _k('', 'NGAY', [_sl(1.8), _tp_trail(2.3)], huy)
    assert plans == [] and huy == []


def test_bug4_123_N_moi_vuot_gia_thi_giu_SL_cu():
    huy = []
    plans, _ = _k(2.2, 2.3, [_sl(1.8), _tp_trail(2.3)], huy)   # LONG, giá 2.1, N=2.2
    assert plans == [] and huy == []


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
