"""
hd_order / hd_order_123 KIỂU CŨ chạy trên bộ máy hd_order_multi — test LOGIC,
không mạng, không tiền thật.

    python3 tests/test_order_cu.py
"""
import ast, io, os, sys
from unittest import mock

QBOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, QBOT)
os.chdir(QBOT)

import tests.test_hd_order_multi as _base  # noqa: E402  (dựng mock Binance/Google/cst)
M = _base.M

LAST = 2.0


def _dong_dl(act='1.9', cb='1', von='20'):
    """Dòng tab ĐẶT LỆNH: A mã · B đòn bẩy · C callback · D giá kích hoạt · H vốn."""
    return ['ATOM/USDT', '5', cb, act, '', '', '', von]


def _dong_cvk(n=1.8, o=2.3):
    """Dòng tab Chờ và khớp A..P (N = idx 13, O = idx 14, P = idx 15)."""
    return ['ATOM/USDT', 'LONG', 'N', 'Y', 2.0, 5, 'N', 'N', 0, '', '', '', '', n, o, 'Y']


def _k(d, pos=10, gia_vao=2.0, last=2.1, snap=(), algo_ok=True, cb=1.0, sl_pct=2.0):
    return M.ke_hoach_123(d, pos, gia_vao, last, list(snap), algo_ok, cb, sl_pct)


def _theo_kieu(plans, kieu):
    return [p for p in plans if p['type'] == kieu]


# ════════════════════════════════════════════════════════════════════════════
#  hd_order — lệnh VÀO trailing, callback cột C
# ════════════════════════════════════════════════════════════════════════════
def test_hd_order_leg_trailing_D_kich_hoat_C_callback():
    leg = M.legs_hd_order()[0]
    assert leg['type'] == 'trailing' and leg['role'] == 'entry'
    assert leg['col'] == 3 and leg['aux'] == 2          # D, C


def test_hd_order_doi_cot_callback_bang_config():
    M.cst.config.set('global', 'order_callback_col', 'G')
    try:
        assert M.legs_hd_order()[0]['aux'] == 6
    finally:
        M.cst.config.remove_option('global', 'order_callback_col')


def test_hd_order_cot_callback_sai_thi_dung():
    M.cst.config.set('global', 'order_callback_col', 'C1')
    try:
        M.legs_hd_order()
        assert False, "tên cột sai phải dừng"
    except SystemExit as e:
        assert 'order_callback_col' in str(e)
    finally:
        M.cst.config.remove_option('global', 'order_callback_col')


def test_hd_order_dat_trailing_mua_dung_cot():
    plans, _ = M.plan_row(M.legs_hd_order(), _dong_dl(), 0, [], True, 20, LAST, 'buy')
    p = plans[0]
    assert p['type'] == 'trailing' and p['side'] == 'buy' and not p['reduce_only']
    assert p['price'] == 1.9 and p['aux'] == 1.0
    assert abs(p['amount'] - 20 / 1.9) < 1e-9


def test_trailing_vao_sai_phia_gia_bi_bo():
    """MUA chờ giá GIẢM tới điểm kích hoạt; BÁN chờ giá TĂNG — như hd_order cũ."""
    legs = M.legs_hd_order()
    plans, skips = M.plan_row(legs, _dong_dl(act='2.1'), 0, [], True, 20, LAST, 'buy')
    assert plans == [] and any('trailing' in r for _, r in skips)
    plans, _ = M.plan_row(legs, _dong_dl(act='1.9'), 0, [], True, 20, LAST, 'sell')
    assert plans == []
    plans, _ = M.plan_row(legs, _dong_dl(act='2.1'), 0, [], True, 20, LAST, 'sell')
    assert plans and plans[0]['side'] == 'sell'


def test_hd_order_da_co_vi_the_thi_khong_vao():
    plans, _ = M.plan_row(M.legs_hd_order(), _dong_dl(), 3, [], True, 20, LAST, 'buy')
    assert plans == []


def test_hd_order_da_co_lenh_vao_cho_BAT_KE_GIA_thi_thoi():
    """Sửa giá cột D không được sinh thêm lệnh vào thứ hai (gấp đôi vốn)."""
    cho = [{'family': 'trailing', 'side': 'buy', 'reduce_only': False, 'price': 1.7}]
    assert M.co_lenh_vao_dang_cho(cho)
    chi_sl_tp = [{'family': 'stop', 'side': 'sell', 'reduce_only': True, 'price': 1.5}]
    assert not M.co_lenh_vao_dang_cho(chi_sl_tp)
    assert not M.co_lenh_vao_dang_cho([])


# ════════════════════════════════════════════════════════════════════════════
#  hd_order_123 — cắt lỗ giá N + chốt lời trailing giá O, callback ô N1
# ════════════════════════════════════════════════════════════════════════════
def test_123_long_dat_cat_lo_N_va_trailing_O():
    plans, _ = _k(_dong_cvk())
    sl, tp = _theo_kieu(plans, 'stop_market')[0], _theo_kieu(plans, 'trailing')[0]
    assert sl['side'] == 'sell' and sl['price'] == 1.8 and sl['reduce_only']
    assert tp['side'] == 'sell' and tp['price'] == 2.3 and tp['aux'] == 1.0
    assert tp['amount'] == 10 and tp['reduce_only']


def test_123_short_dong_bang_lenh_mua():
    plans, _ = _k(_dong_cvk(n=2.3, o=1.7), pos=-10, last=2.0)
    assert len(plans) == 2 and {p['side'] for p in plans} == {'buy'}


def test_123_N_trong_thi_tinh_tu_phan_tram_SL():
    plans, _ = _k(_dong_cvk(n=''), gia_vao=2.0, sl_pct=5)
    assert abs(_theo_kieu(plans, 'stop_market')[0]['price'] - 1.9) < 1e-9
    plans, _ = _k(_dong_cvk(n=''), pos=-10, gia_vao=2.0, last=1.95, sl_pct=5)
    assert abs(_theo_kieu(plans, 'stop_market')[0]['price'] - 2.1) < 1e-9


def test_123_O_trong_0_NGAY_thi_kich_hoat_ngay():
    for o in ('', 0, '0', 'NGAY', 'now', None):
        plans, _ = _k(_dong_cvk(o=o), last=2.1)
        tp = _theo_kieu(plans, 'trailing')
        assert tp and 2.09 < tp[0]['price'] < 2.1, (o, plans)
    plans, _ = _k(_dong_cvk(n=2.3, o=''), pos=-10, last=2.0)
    assert 2.0 < _theo_kieu(plans, 'trailing')[0]['price'] < 2.01


def test_123_O_chu_la_thi_bo_chot_loi():
    plans, skips = _k(_dong_cvk(o='abc'))
    assert _theo_kieu(plans, 'trailing') == [] and any('cột O' in r for _, r in skips)
    assert _theo_kieu(plans, 'stop_market'), "cắt lỗ vẫn phải đặt"


def test_123_da_co_cat_lo_thi_chi_dat_chot_loi():
    plans, _ = _k(_dong_cvk(), snap=[{'loai': 'SL', 'reduce_only': True}])
    assert [p['type'] for p in plans] == ['trailing']


def test_123_da_co_chot_loi_LIMIT_thi_khong_dat_them_trailing():
    """Chốt lời do hd_order_multi đặt (LIMIT) cũng tính — không đặt lệnh chốt lời thứ hai."""
    plans, _ = _k(_dong_cvk(), snap=[{'loai': 'TP', 'reduce_only': True}])
    assert [p['type'] for p in plans] == ['stop_market']


def test_123_lenh_vao_dang_cho_khong_tinh_la_SL_TP():
    plans, _ = _k(_dong_cvk(), snap=[{'loai': 'ENTRY', 'reduce_only': False}])
    assert len(plans) == 2


def test_123_cat_lo_vuot_gia_hien_tai_bi_bo():
    plans, skips = _k(_dong_cvk(n=2.2), last=2.1)
    assert _theo_kieu(plans, 'stop_market') == [] and any('khớp ngay' in r for _, r in skips)
    plans, _ = _k(_dong_cvk(n=1.9, o=1.7), pos=-10, last=2.0)
    assert _theo_kieu(plans, 'stop_market') == []


def test_123_algo_loi_van_dat_cat_lo():
    plans, skips = _k(_dong_cvk(), algo_ok=False)
    assert [p['type'] for p in plans] == ['stop_market'] and any('algo' in r for _, r in skips)


def test_123_khong_co_vi_the_thi_thoi():
    plans, _ = _k(_dong_cvk(), pos=0)
    assert plans == []


def test_callback_o_N1():
    assert M.doc_callback(1) == 1.0
    assert M.doc_callback('0,5%') == 0.5
    assert M.doc_callback('25') == 10.0, "Binance chỉ nhận tối đa 10%"
    assert M.doc_callback('0.01') == 0.1, "Binance chỉ nhận tối thiểu 0.1%"
    assert M.doc_callback('', 1.5) == 1.5
    assert M.doc_callback('abc', 2) == 2.0


def test_snapshot_gan_loai_lenh():
    """Chống trùng của hd_order_123 dựa vào loại lệnh thật trên Binance."""
    thuong = [{'type': 'stop_market', 'side': 'sell', 'id': '1',
               'info': {'closePosition': 'true', 'origType': 'STOP_MARKET'}},
              {'type': 'limit', 'side': 'buy', 'id': '2', 'info': {}}]
    algo = [{'algoStatus': 'NEW', 'side': 'SELL', 'reduceOnly': True, 'callbackRate': '1',
             'orderType': 'TRAILING_STOP_MARKET', 'activatePrice': '2.3', 'algoId': 9}]
    with mock.patch.object(M.exchange, 'fetch_open_orders', lambda s: thuong, create=True), \
         mock.patch.object(M, 'get_algo_orders_for_symbol', lambda s: algo):
        snap, ok = M.build_symbol_snapshot('ATOM/USDT:USDT', True)
    assert ok and [x['loai'] for x in snap] == ['SL', 'ENTRY', 'TP']


# ════════════════════════════════════════════════════════════════════════════
#  Chống trộn kiểu cũ và kiểu mới trên cùng một tài khoản
# ════════════════════════════════════════════════════════════════════════════
def _khoa(ten, pid):
    p = M.cst.account_dir('pids') / f'{ten}.lock'
    p.write_text(str(pid))
    return p


def _thu(che_do, song=True):
    with mock.patch.object(M.cst, '_pid_alive', lambda pid: song, create=True):
        try:
            M.kiem_tra_xung_dot(che_do)
            return None
        except SystemExit as e:
            return str(e)


def test_kieu_cu_gap_multi_dang_chay_thi_dung():
    p = _khoa('hd_order_multi', 424242)
    try:
        for cd in ('order', '123'):
            loi = _thu(cd)
            assert loi and 'TRÙNG' in loi and 'hd_order_multi' in loi, cd
        assert _thu('multi') is None, "khoá của CHÍNH nó không phải xung đột"
        assert _thu('order', song=False) is None, "khoá mồ côi (PID đã chết) thì chạy được"
    finally:
        p.unlink()


def test_multi_gap_kieu_cu_dang_chay_thi_dung():
    for ten in ('hd_order', 'hd_order_123'):
        p = _khoa(ten, 424242)
        try:
            loi = _thu('multi')
            assert loi and ten in loi, ten
        finally:
            p.unlink()


def test_bat_cung_luc_chi_bot_bat_SAU_nhuong():
    """Hai bot xung đột bật cùng lúc: cả hai thấy khoá của nhau — không được cùng chết."""
    toi = _khoa('hd_order', os.getpid())
    kia = _khoa('hd_order_multi', 424242)
    try:
        os.utime(toi, ns=(1_000_000_000, 1_000_000_000))      # hd_order giành khoá TRƯỚC
        os.utime(kia, ns=(2_000_000_000, 2_000_000_000))
        assert _thu('order') is None, "bot bật trước phải chạy tiếp"
        os.utime(toi, ns=(3_000_000_000, 3_000_000_000))      # hd_order giành khoá SAU
        assert _thu('order'), "bot bật sau phải nhường"
    finally:
        toi.unlink(); kia.unlink()


def test_hd_order_va_hd_order_123_chay_chung_duoc():
    p = _khoa('hd_order', 424242)
    try:
        assert _thu('123') is None
    finally:
        p.unlink()


# ════════════════════════════════════════════════════════════════════════════
#  Nối vào hệ thống: file khởi động, nhịp, script bật bot
# ════════════════════════════════════════════════════════════════════════════
def test_file_khoi_dong_goi_dung_che_do():
    for f, cd in (('hd_order.py', 'order'), ('hd_order_123.py', '123')):
        src = io.open(os.path.join(QBOT, f), encoding='utf-8').read()
        dau = next(n for n in ast.parse(src).body if isinstance(n, (ast.Import, ast.ImportFrom)))
        assert isinstance(dau, ast.Import) and dau.names[0].name == 'giu_cua_so', f
        assert f"dong_co.chay('{cd}')" in src, f
        assert M.CHE_DO[cd]['bot'] == f[:-3]


def test_moi_che_do_nghi_dung_nhip_cua_no():
    assert M.CHE_DO['order']['nhip'] == 'delay_vao_lenh'
    assert M.CHE_DO['123']['nhip'] == 'delay_vao_lenh_123'
    src = io.open(os.path.join(QBOT, 'hd_order_multi.py'), encoding='utf-8').read()
    assert "config_watcher.ngu_theo_nhip(_t0_vong, nhip, cd['nhip'])" in src
    for f in ('cst.py', 'kiem_tra_cau_hinh.py', 'config.ini.example'):
        assert 'delay_vao_lenh_123' in io.open(os.path.join(QBOT, f), encoding='utf-8').read(), f


def test_bat_duoc_tung_bot_nhung_KHONG_bat_mac_dinh():
    for f in ('start_bot.sh', 'chay_bot.bat'):
        s = io.open(os.path.join(QBOT, f), encoding='utf-8').read()
        assert 'hd_order_123' in s and 'hd_order ' in s, f
    lenh = [l.split()[1] for l in io.open(os.path.join(QBOT, 'start_all_bots.sh'), encoding='utf-8')
            if l.strip().startswith('run_bot ')]
    assert 'hd_order_multi.py' in lenh
    assert 'hd_order.py' not in lenh and 'hd_order_123.py' not in lenh, \
        "bật tất cả mà chạy cả kiểu cũ lẫn kiểu mới → đặt lệnh trùng"


def test_ten_bot_theo_file_da_bat():
    assert M.TEN_BOT == 'hd_order_multi'   # chạy từ file test → mặc định


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
