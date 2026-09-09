"""
Test LOGIC cho hd_order_multi.py — chạy LOCAL, KHÔNG gọi Binance, KHÔNG tốn tiền.

Cách chạy:
    cd "qbot_setup"
    python3 tests/test_hd_order_multi.py      # in PASS/FAIL, dễ đọc
    # hoặc:  pytest tests/test_hd_order_multi.py -v

Mỗi nhóm test gắn với 1 yêu cầu của khách hàng (xem tiêu đề [YC ...]).
Toàn bộ Binance/Google/Telegram được "mock" (giả) nên an toàn tuyệt đối.
"""
import os, sys, types, configparser

# ── Trỏ về thư mục bot để import được hd_order_multi ────────────────────────────
QBOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(QBOT)
sys.path.insert(0, QBOT)


# ── MOCK toàn bộ phụ thuộc ngoài (không đụng mạng/tiền thật) ────────────────────
def _mod(name, **attrs):
    m = types.ModuleType(name)
    for k, v in attrs.items():
        setattr(m, k, v)
    sys.modules[name] = m
    return m


class _FakeExchange:
    def __init__(self, *a, **k):
        self.markets = {}
    def setSandboxMode(self, *a, **k): pass
    def load_markets(self, *a, **k): return {}
    def price_to_precision(self, s, v): return v   # test: không làm tròn
    def amount_to_precision(self, s, v): return v


def _install_mocks():
    _mod("ccxt", binance=_FakeExchange)

    cfg = configparser.ConfigParser()
    cfg.read_dict({"global": {
        "multi_leg_count": "3",
        "leg1_type": "limit", "leg1_role": "entry", "leg1_col": "D",
        "leg2_type": "stop_market", "leg2_role": "exit", "leg2_col": "F",
        "leg3_type": "limit", "leg3_role": "exit", "leg3_col": "G", "leg3_pct_col": "I",
    }})
    # mock cst — có cả API đa tài khoản (account_dir/account_suffix) như bản thật
    import tempfile, pathlib as _pl
    _tmp = _pl.Path(tempfile.mkdtemp(prefix="qbot_test_"))
    def _account_dir(base):
        d = _tmp / base
        d.mkdir(parents=True, exist_ok=True)
        return d
    _mod("cst", key_name="TEST", key_binance="x", secret_binance="y", chat_id="0",
         delay_vao_lenh=60, run_tele_command=False, config=cfg,
         accounts=[], account="", account_name="default",
         account_dir=_account_dir, account_suffix=lambda: "")

    class _FakeHelper:
        def __init__(self, *a, **k): pass
    _mod("binance_order_helper", BinanceOrderHelper=_FakeHelper,
         cancel_all_open_orders_with_retry=lambda *a, **k: None)
    _mod("binance_futures_direct",
         fetch_algo_orders_for_symbol=lambda *a, **k: [],
         resync_exchange_time=lambda *a, **k: None)
    _mod("gg_sheet_factory", get_dat_lenh=lambda *a, **k: [], init_sheet_api=lambda *a, **k: None)
    _mod("telegram_factory", send_tele=lambda *a, **k: None)
    _mod("utils")
    _mod("binance_utils", get_price_precision=lambda s: 4)
    gapi = types.ModuleType("googleapiclient")
    errs = types.ModuleType("googleapiclient.errors")
    class HttpError(Exception): pass
    errs.HttpError = HttpError
    gapi.errors = errs
    sys.modules["googleapiclient"] = gapi
    sys.modules["googleapiclient.errors"] = errs


_install_mocks()
import hd_order_multi as M  # noqa: E402  (import sau khi mock là cố ý)


# Cấu hình 3 leg mẫu (limit entry D / stop_market SL F / limit TP G %I) dùng chung
LEGS = [
    {'idx': 1, 'type': 'limit',       'role': 'entry', 'col': 3, 'aux': None, 'pct_col': None},  # D
    {'idx': 2, 'type': 'stop_market', 'role': 'exit',  'col': 5, 'aux': None, 'pct_col': None},  # F
    {'idx': 3, 'type': 'limit',       'role': 'exit',  'col': 6, 'aux': None, 'pct_col': 8},     # G, %=I
]
LAST = 2.083  # giá thị trường giả


# ════════════════════════════════════════════════════════════════════════════
#  [YC2] Đọc kiểu lệnh từ config + cột từ sheet
# ════════════════════════════════════════════════════════════════════════════
def test_load_legs_from_config():
    legs = M.load_legs()
    assert len(legs) == 3
    assert legs[0] == {'idx': 1, 'type': 'limit', 'type_col': None, 'role': 'entry',
                       'source': 'dat_lenh', 'col': 3, 'aux': None, 'pct_col': None}
    assert legs[1]['type'] == 'stop_market' and legs[1]['col'] == 5
    assert legs[2]['pct_col'] == 8  # cột I


def test_col_letter_to_index():
    assert (M._col_to_idx("A"), M._col_to_idx("D"), M._col_to_idx("F"),
            M._col_to_idx("G"), M._col_to_idx("I")) == (0, 3, 5, 6, 8)
    assert M._col_to_idx("") is None


# ════════════════════════════════════════════════════════════════════════════
#  [YC6] Tính vốn: cột H → D1×E2 (min 10) → D2
# ════════════════════════════════════════════════════════════════════════════
def test_capital_priority():
    assert M.compute_capital(['A', '1', '', '2', '', '', '', '25'], 7, 0.01, 10, 1000) == 25   # cột H
    assert M.compute_capital(['A', '1'], 7, 0.01, None, 1000) == 10                            # D1×E2 min 10
    assert M.compute_capital(['A', '1'], 7, 0.03, None, 1000) == 30                            # 3%×1000
    assert M.compute_capital(['A', '1'], 7, None, 10, None) == 10                              # D2
    assert M.compute_capital(['A', '1'], 7, None, None, None) is None                          # không có vốn


# ════════════════════════════════════════════════════════════════════════════
#  [YC4] Role linh hoạt: entry chỉ chạy khi CHƯA có vị thế; exit chỉ khi ĐÃ có
# ════════════════════════════════════════════════════════════════════════════
def test_entry_only_when_no_position():
    d = ['ATOM/USDT', '1', '', '2.0', '', '1.9', '2.5', '10', '50']
    plans, skips = M.plan_row(LEGS, d, 0, [], True, 10, LAST, 'buy')
    assert [p['leg_idx'] for p in plans] == [1]           # chỉ lệnh vào
    assert plans[0]['side'] == 'buy' and plans[0]['reduce_only'] is False


def test_exit_only_when_has_position():
    d = ['ATOM/USDT', '1', '', '2.0', '', '1.9', '2.5', '10', '50']
    plans, skips = M.plan_row(LEGS, d, 5, [], True, 10, LAST, 'buy')
    assert [p['leg_idx'] for p in plans] == [2, 3]        # SL + TP
    assert all(p['reduce_only'] for p in plans)


# ════════════════════════════════════════════════════════════════════════════
#  [YC6] Vốn: mỗi leg entry FULL vốn ; leg exit chia % theo cột
# ════════════════════════════════════════════════════════════════════════════
def test_entry_full_capital():
    d = ['ATOM/USDT', '1', '', '2.0', '', '', '', '10']
    plans, _ = M.plan_row([LEGS[0]], d, 0, [], True, 10, LAST, 'buy')
    assert plans[0]['amount'] == 10 / 2.0                 # vốn / giá = 5


def test_two_entry_legs_each_full_capital():
    # 2 lệnh vào (DCA) — mỗi lệnh FULL vốn
    legs = [
        {'idx': 1, 'type': 'limit', 'role': 'entry', 'col': 3, 'aux': None, 'pct_col': None},  # D=2.0
        {'idx': 2, 'type': 'limit', 'role': 'entry', 'col': 9, 'aux': None, 'pct_col': None},  # J=1.8
    ]
    d = ['ATOM/USDT', '1', '', '2.0', '', '', '', '10', '', '1.8']
    plans, _ = M.plan_row(legs, d, 0, [], True, 10, LAST, 'buy')
    assert len(plans) == 2
    assert plans[0]['amount'] == 10 / 2.0                 # full vốn cho leg1
    assert plans[1]['amount'] == 10 / 1.8                 # full vốn cho leg2


def test_exit_partial_percent():
    d = ['ATOM/USDT', '1', '', '2.0', '', '1.9', '2.5', '10', '50']  # I=50%
    plans, _ = M.plan_row(LEGS, d, 5, [], True, 10, LAST, 'buy')
    sl = next(p for p in plans if p['leg_idx'] == 2)
    tp = next(p for p in plans if p['leg_idx'] == 3)
    assert sl['amount'] == 5.0        # SL không có %-col → 100% = full 5
    assert tp['amount'] == 2.5        # TP 50% của 5


# ════════════════════════════════════════════════════════════════════════════
#  [YC1/YC5] Mỗi kiểu lệnh phát sinh đúng tham số (giá chính + cột phụ)
# ════════════════════════════════════════════════════════════════════════════
def test_type_market_uses_no_price():
    legs = [{'idx': 1, 'type': 'market', 'role': 'entry', 'col': None, 'aux': None, 'pct_col': None}]
    d = ['ATOM/USDT', '1', '', '', '', '', '', '10']
    plans, _ = M.plan_row(legs, d, 0, [], True, 10, LAST, 'buy')
    assert plans[0]['type'] == 'market' and plans[0]['price'] is None
    assert plans[0]['amount'] == 10 / LAST               # market: dùng giá hiện tại


def test_type_stop_limit_two_prices():
    # stop_limit: col=giá stop, aux=giá limit
    legs = [{'idx': 1, 'type': 'stop_limit', 'role': 'exit', 'col': 5, 'aux': 6, 'pct_col': None}]  # F=stop, G=limit
    d = ['ATOM/USDT', '1', '', '2.0', '', '1.9', '1.85', '10']
    plans, _ = M.plan_row(legs, d, 5, [], True, 10, LAST, 'buy')
    assert plans[0]['type'] == 'stop_limit'
    assert plans[0]['price'] == 1.9 and plans[0]['aux'] == 1.85


def test_type_trailing_callback_from_aux():
    # trailing: col=activation, aux=callback%
    legs = [{'idx': 1, 'type': 'trailing', 'role': 'exit', 'col': 6, 'aux': 8, 'pct_col': None}]  # G=act, I=callback
    d = ['ATOM/USDT', '1', '', '2.0', '', '', '2.5', '10', '1']
    plans, _ = M.plan_row(legs, d, 5, [], True, 10, LAST, 'buy')
    assert plans[0]['type'] == 'trailing'
    assert plans[0]['price'] == 2.5 and plans[0]['aux'] == 1.0


def test_stop_limit_missing_aux_skipped():
    legs = [{'idx': 1, 'type': 'stop_limit', 'role': 'exit', 'col': 5, 'aux': 20, 'pct_col': None}]  # aux cột trống
    d = ['ATOM/USDT', '1', '', '2.0', '', '1.9', '', '10']
    plans, skips = M.plan_row(legs, d, 5, [], True, 10, LAST, 'buy')
    assert plans == [] and any('aux' in r for _, r in skips)


# ════════════════════════════════════════════════════════════════════════════
#  [YC7] Chống trùng per-mã: theo loại + chiều + reduce_only + GIÁ
# ════════════════════════════════════════════════════════════════════════════
def test_dedup_existing_tp():
    d = ['ATOM/USDT', '1', '', '2.0', '', '1.9', '2.5', '10', '50']
    snap = [{'family': 'limit', 'side': 'sell', 'reduce_only': True, 'price': 2.5}]  # đã có TP 2.5
    plans, _ = M.plan_row(LEGS, d, 5, snap, True, 10, LAST, 'buy')
    assert [p['leg_idx'] for p in plans] == [2]           # TP bị bỏ, chỉ còn SL


def test_dedup_distinguish_tp1_tp2_by_price():
    legs = [
        {'idx': 1, 'type': 'limit', 'role': 'exit', 'col': 6, 'aux': None, 'pct_col': None},  # G=2.5
        {'idx': 2, 'type': 'limit', 'role': 'exit', 'col': 9, 'aux': None, 'pct_col': None},  # J=2.7
    ]
    d = ['ATOM/USDT', '1', '', '2.0', '', '1.9', '2.5', '10', '', '2.7']
    plans, _ = M.plan_row(legs, d, 5, [], True, 10, LAST, 'buy')
    assert sorted(p['price'] for p in plans) == [2.5, 2.7]          # 2 giá khác → cả 2 đặt
    snap = [{'family': 'limit', 'side': 'sell', 'reduce_only': True, 'price': 2.5}]
    plans2, _ = M.plan_row(legs, d, 5, snap, True, 10, LAST, 'buy')
    assert [p['price'] for p in plans2] == [2.7]                    # có 2.5 rồi → chỉ đặt 2.7


def test_dedup_same_leg_within_scan():
    # 2 leg trùng hệt (cùng loại/chiều/giá) → chỉ đặt 1
    legs = [
        {'idx': 1, 'type': 'limit', 'role': 'exit', 'col': 6, 'aux': None, 'pct_col': None},
        {'idx': 2, 'type': 'limit', 'role': 'exit', 'col': 6, 'aux': None, 'pct_col': None},
    ]
    d = ['ATOM/USDT', '1', '', '2.0', '', '', '2.5', '10']
    plans, _ = M.plan_row(legs, d, 5, [], True, 10, LAST, 'buy')
    assert len(plans) == 1


def test_trailing_skipped_when_algo_unavailable():
    legs = [{'idx': 1, 'type': 'trailing', 'role': 'exit', 'col': 6, 'aux': 8, 'pct_col': None}]
    d = ['ATOM/USDT', '1', '', '2.0', '', '', '2.5', '10', '1']
    plans, skips = M.plan_row(legs, d, 5, [], False, 10, LAST, 'buy')   # algo_ok=False
    assert plans == [] and any('algo' in r.lower() for _, r in skips)


# ════════════════════════════════════════════════════════════════════════════
#  An toàn: validate chiều giá entry limit + SHORT đảo side
# ════════════════════════════════════════════════════════════════════════════
def test_entry_limit_wrong_direction_skipped():
    d = ['ATOM/USDT', '1', '', '2.5', '', '', '', '10']   # buy limit 2.5 >= giá 2.083
    plans, skips = M.plan_row([LEGS[0]], d, 0, [], True, 10, LAST, 'buy')
    assert plans == [] and any('buy limit' in r for _, r in skips)


def test_short_exit_side_is_buy():
    d = ['ATOM/USDT', '1', '', '2.0', '', '2.2', '1.8', '10', '50']
    plans, _ = M.plan_row(LEGS, d, -5, [], True, 10, LAST, 'sell')   # vị thế SHORT
    assert {p['side'] for p in plans} == {'buy'}          # đóng SHORT = mua vào


# ════════════════════════════════════════════════════════════════════════════
#  [YC MỚI] Kiểu lệnh THEO DÒNG qua cột sheet (mã số 1..5)
# ════════════════════════════════════════════════════════════════════════════
def test_resolve_type_from_code():
    leg = {'idx': 1, 'type': None, 'type_col': 2}  # đọc mã ở cột C (index 2)
    assert M._resolve_leg_type(leg, ['A', 'B', '1']) == 'limit'
    assert M._resolve_leg_type(leg, ['A', 'B', '2']) == 'market'
    assert M._resolve_leg_type(leg, ['A', 'B', '3']) == 'stop_market'
    assert M._resolve_leg_type(leg, ['A', 'B', '4']) == 'stop_limit'
    assert M._resolve_leg_type(leg, ['A', 'B', '5']) == 'trailing'
    assert M._resolve_leg_type(leg, ['A', 'B', '']) is None      # trống → tắt
    assert M._resolve_leg_type(leg, ['A', 'B', '9']) is None      # mã lạ → tắt


def test_resolve_type_accepts_text():
    leg = {'idx': 1, 'type': None, 'type_col': 2}
    assert M._resolve_leg_type(leg, ['A', 'B', 'trailing']) == 'trailing'
    assert M._resolve_leg_type(leg, ['A', 'B', 'MARKET']) == 'market'


def test_resolve_type_fixed_when_no_type_col():
    leg = {'idx': 1, 'type': 'limit', 'type_col': None}
    assert M._resolve_leg_type(leg, ['A', 'B', 'C']) == 'limit'   # dùng type cố định


def test_per_row_different_types_same_leg_config():
    # 1 leg entry, kiểu đọc từ cột C (index 2), giá cột D (3), aux cột E (4)
    leg = {'idx': 1, 'type': None, 'type_col': 2, 'role': 'entry', 'col': 3, 'aux': 4, 'pct_col': None}
    # Dòng A: mã 1 = limit @2.0
    dA = ['ATOM/USDT', '1', '1', '2.0', '']
    pA, _ = M.plan_row([leg], dA, 0, [], True, 10, LAST, 'buy')
    assert pA[0]['type'] == 'limit' and pA[0]['price'] == 2.0
    # Dòng B: mã 2 = market (không cần giá)
    dB = ['SOL/USDT', '1', '2', '', '']
    pB, _ = M.plan_row([leg], dB, 0, [], True, 10, LAST, 'buy')
    assert pB[0]['type'] == 'market' and pB[0]['price'] is None
    # Dòng C: mã 4 = stop_limit (giá D=stop, aux E=limit) — dùng làm entry
    dC = ['BID/USDT', '1', '4', '2.2', '2.25']
    pC, _ = M.plan_row([leg], dC, 0, [], True, 10, LAST, 'buy')
    assert pC[0]['type'] == 'stop_limit' and pC[0]['price'] == 2.2 and pC[0]['aux'] == 2.25


def test_per_row_type_empty_disables_leg():
    leg = {'idx': 1, 'type': None, 'type_col': 2, 'role': 'entry', 'col': 3, 'aux': 4, 'pct_col': None}
    d = ['ATOM/USDT', '1', '', '2.0', '']   # cột kiểu trống → leg tắt
    plans, skips = M.plan_row([leg], d, 0, [], True, 10, LAST, 'buy')
    assert plans == [] and any('kiểu' in r for _, r in skips)


def test_per_row_exit_type_and_percent():
    # Leg exit: kiểu theo cột C, giá cột G(6), % cột I(8)
    leg = {'idx': 3, 'type': None, 'type_col': 2, 'role': 'exit', 'col': 6, 'aux': 7, 'pct_col': 8}
    d = ['ATOM/USDT', '1', '3', '2.0', '', '', '1.9', '', '50']  # mã3=stop_market, G(6)=1.9, I(8)=50
    plans, _ = M.plan_row([leg], d, 5, [], True, 10, LAST, 'buy')
    assert plans[0]['type'] == 'stop_market' and plans[0]['side'] == 'sell'
    assert plans[0]['price'] == 1.9 and plans[0]['amount'] == 2.5  # 50% của 5


def test_load_legs_reads_type_col():
    import configparser as _cp, sys as _sys
    cfg = _cp.ConfigParser()
    cfg.read_dict({"global": {
        "multi_leg_count": "1",
        "leg1_role": "entry", "leg1_type_col": "C", "leg1_col": "D", "leg1_aux": "E",
    }})
    old = _sys.modules["cst"].config
    _sys.modules["cst"].config = cfg
    try:
        legs = M.load_legs()
    finally:
        _sys.modules["cst"].config = old
    assert len(legs) == 1
    assert legs[0]['type_col'] == 2 and legs[0]['type'] is None  # C=index2, không có type cố định
    assert legs[0]['col'] == 3 and legs[0]['aux'] == 4


# ════════════════════════════════════════════════════════════════════════════
#  [YC MỚI] SL/TP đọc từ tab "Chờ và khớp" (legN_source)
# ════════════════════════════════════════════════════════════════════════════
def _legs_with_source(cfg_dict):
    import configparser as _cp, sys as _sys
    cfg = _cp.ConfigParser()
    cfg.read_dict({"global": cfg_dict})
    old = _sys.modules["cst"].config
    _sys.modules["cst"].config = cfg
    try:
        return M.load_legs()
    finally:
        _sys.modules["cst"].config = old


def test_source_defaults_by_role():
    """Không khai source: entry → tab Đặt lệnh; exit → tab Chờ và khớp."""
    legs = _legs_with_source({
        "multi_leg_count": "2",
        "leg1_role": "entry", "leg1_type": "limit", "leg1_col": "D",
        "leg2_role": "exit", "leg2_type": "stop_market", "leg2_col": "N",
    })
    assert legs[0]['source'] == 'dat_lenh'
    assert legs[1]['source'] == 'cho_va_khop'


def test_source_explicit_from_config():
    legs = _legs_with_source({
        "multi_leg_count": "2",
        "leg1_role": "exit", "leg1_type": "limit", "leg1_col": "G", "leg1_source": "dat_lenh",
        "leg2_role": "exit", "leg2_type": "limit", "leg2_col": "O", "leg2_source": "cho_va_khop",
    })
    assert legs[0]['source'] == 'dat_lenh'      # ép về tab Đặt lệnh
    assert legs[1]['source'] == 'cho_va_khop'


def test_source_invalid_falls_back():
    legs = _legs_with_source({
        "multi_leg_count": "1",
        "leg1_role": "exit", "leg1_type": "limit", "leg1_col": "N", "leg1_source": "linh_tinh",
    })
    assert legs[0]['source'] == 'cho_va_khop'   # giá trị lạ → mặc định theo role


def test_plan_row_on_cho_va_khop_row():
    """
    Mô phỏng 1 dòng tab "Chờ và khớp" (vị thế LONG đang mở):
      A=Symbol B=LONG D=Y(đã khớp) N=giá SL O=giá TP P=Y R=kiểu SL U=kiểu TP T/W=% đóng
    """
    legs = [
        # SL: giá cột N(13), kiểu cột R(17), phụ S(18), % cột T(19)
        {'idx': 2, 'type': None, 'type_col': 17, 'role': 'exit', 'source': 'cho_va_khop',
         'col': 13, 'aux': 18, 'pct_col': 19},
        # TP: giá cột O(14), kiểu cột U(20), phụ V(21), % cột W(22)
        {'idx': 3, 'type': None, 'type_col': 20, 'role': 'exit', 'source': 'cho_va_khop',
         'col': 14, 'aux': 21, 'pct_col': 22},
    ]
    d = [""] * 23
    d[0] = "ATOM/USDT"; d[1] = "LONG"; d[3] = "Y"      # A, B, D
    d[13] = "1.9"; d[14] = "2.5"                        # N=giá SL, O=giá TP
    d[15] = "Y"                                         # P = ĐẶT LỆNH
    d[17] = "3"                                         # R = kiểu SL = stop_market
    d[19] = "100"                                       # T = % đóng SL
    d[20] = "1"                                         # U = kiểu TP = limit
    d[22] = "50"                                        # W = % đóng TP

    plans, skips = M.plan_row(legs, d, 5, [], True, None, 2.083, "buy")
    assert len(plans) == 2
    sl = next(p for p in plans if p['leg_idx'] == 2)
    tp = next(p for p in plans if p['leg_idx'] == 3)
    assert sl['type'] == 'stop_market' and sl['price'] == 1.9 and sl['amount'] == 5.0
    assert tp['type'] == 'limit' and tp['price'] == 2.5 and tp['amount'] == 2.5   # 50%
    assert sl['side'] == 'sell' and tp['side'] == 'sell'   # đóng LONG = bán
    assert sl['reduce_only'] and tp['reduce_only']


def test_cho_va_khop_short_position_closes_with_buy():
    legs = [{'idx': 2, 'type': None, 'type_col': 17, 'role': 'exit', 'source': 'cho_va_khop',
             'col': 13, 'aux': 18, 'pct_col': None}]
    d = [""] * 20
    d[0] = "ATOM/USDT"; d[1] = "SHORT"; d[3] = "Y"; d[13] = "2.3"; d[15] = "Y"; d[17] = "3"
    plans, _ = M.plan_row(legs, d, -5, [], True, None, 2.083, "sell")
    assert plans[0]['side'] == 'buy'          # đóng SHORT = mua
    assert plans[0]['amount'] == 5.0


# ════════════════════════════════════════════════════════════════════════════
#  [BUG FIX] Rải nhiều lệnh VÀO cho 1 mã (khách báo: "lên 3 lệnh chỉ vào 1")
# ════════════════════════════════════════════════════════════════════════════
def _entry_leg(idx, col):
    return {'idx': idx, 'type': 'limit', 'type_col': None, 'role': 'entry',
            'source': 'dat_lenh', 'col': col, 'aux': None, 'pct_col': None}


def test_spread_orders_close_prices_not_merged():
    """
    Rải 3 lệnh giá SÁT nhau (1.380/1.379/1.378 — chênh 0.07%).
    Dung sai cũ 0.2% gộp nhầm thành 1 lệnh; nay phải đặt đủ 3.
    """
    legs = [_entry_leg(1, 3), _entry_leg(2, 4), _entry_leg(3, 5)]
    d = ['ATOM/USDT', '10', '', '1.380', '1.379', '1.378', '', '10']
    snap = []
    placed = []
    for leg in legs:                      # mô phỏng đặt lần lượt, snapshot tích lũy
        plans, _ = M.plan_row([leg], d, 0, snap, True, 10, 1.413, 'buy')
        for p in plans:
            placed.append(p['price'])
            snap.append({'family': 'limit', 'side': p['side'],
                         'reduce_only': False, 'price': p['price']})
    assert len(placed) == 3, f"Phải đặt đủ 3 lệnh, thực tế {len(placed)}: {placed}"


def test_identical_prices_still_deduped():
    """Cùng giá y hệt thì VẪN phải chống trùng (chỉ 1 lệnh)."""
    legs = [_entry_leg(1, 3), _entry_leg(2, 4)]
    d = ['ATOM/USDT', '10', '', '1.38', '1.38', '', '', '10']
    snap, placed = [], []
    for leg in legs:
        plans, _ = M.plan_row([leg], d, 0, snap, True, 10, 1.413, 'buy')
        for p in plans:
            placed.append(p['price'])
            snap.append({'family': 'limit', 'side': p['side'],
                         'reduce_only': False, 'price': p['price']})
    assert len(placed) == 1


def test_dca_off_blocks_entry_when_position_exists():
    """allow_dca=False (mặc định): đã có vị thế → KHÔNG vào thêm."""
    legs = [_entry_leg(1, 3)]
    d = ['ATOM/USDT', '10', '', '1.38', '', '', '', '10']
    plans, skips = M.plan_row(legs, d, 7.0, [], True, 10, 1.413, 'buy')
    assert plans == [] and 'đã có vị thế' in skips[0][1]


def test_dca_on_allows_entry_when_position_exists():
    """allow_dca=True: vẫn rải thêm lệnh vào dù đang có vị thế."""
    legs = [_entry_leg(1, 3), _entry_leg(2, 4)]
    d = ['ATOM/USDT', '10', '', '1.35', '1.32', '', '', '10']
    plans, _ = M.plan_row(legs, d, 7.0, [], True, 10, 1.413, 'buy', allow_dca=True)
    assert len(plans) == 2 and sorted(p['price'] for p in plans) == [1.32, 1.35]


# ════════════════════════════════════════════════════════════════════════════
#  [BẢO VỆ VỊ THẾ] SL closePosition + TP tự đặt lại khi vị thế tăng (rải lệnh)
# ════════════════════════════════════════════════════════════════════════════
SL_LEG = {'idx': 2, 'type': 'stop_market', 'type_col': None, 'role': 'exit',
          'source': 'cho_va_khop', 'col': 13, 'aux': None, 'pct_col': None}
TP_LEG = {'idx': 3, 'type': 'limit', 'type_col': None, 'role': 'exit',
          'source': 'cho_va_khop', 'col': 14, 'aux': None, 'pct_col': None}


def _cvk_row(n="1.32", o="1.52"):
    r = [""] * 17
    r[0] = "ATOM/USDT"; r[1] = "LONG"; r[3] = "Y"; r[13] = n; r[14] = o; r[15] = "Y"
    return r


def test_sl_uses_close_position():
    """SL đặt kèm cờ closePosition → tự đóng trọn vị thế, không gắn khối lượng."""
    plans, _ = M.plan_row([SL_LEG], _cvk_row(), 7.2, [], True, None, 1.413, "buy",
                          allow_close_position=True)
    assert plans[0]['close_position'] is True


def test_sl_not_reissued_when_position_grows():
    """Vị thế tăng → KHÔNG cần đặt lại SL (closePosition đã bao trọn)."""
    snap = [{'family': 'stop', 'side': 'sell', 'reduce_only': True, 'price': 1.32,
             'amount': None, 'id': 'SL1', 'close_position': True}]
    huy = []
    plans, skips = M.plan_row([SL_LEG], _cvk_row(), 14.6, snap, True, None, 1.413, "buy",
                              allow_close_position=True, resize_exits=True, cancel_out=huy)
    assert plans == [] and huy == [] and "đã có lệnh tương tự" in skips[0][1]


def test_tp_reissued_when_position_grows():
    """Vị thế 7.2 → 14.6: TP cũ (KL 7.2) phải bị HỦY và đặt lại đúng 14.6."""
    snap = [{'family': 'limit', 'side': 'sell', 'reduce_only': True, 'price': 1.52,
             'amount': 7.2, 'id': 'TP1', 'close_position': False}]
    huy = []
    plans, _ = M.plan_row([TP_LEG], _cvk_row(), 14.6, snap, True, None, 1.413, "buy",
                          resize_exits=True, resize_tol=0.01, cancel_out=huy)
    assert len(huy) == 1 and huy[0][0] == 'TP1'
    assert len(plans) == 1 and plans[0]['amount'] == 14.6


def test_tp_not_reissued_when_amount_matches():
    """Khối lượng đã khớp vị thế → giữ nguyên, không hủy/đặt lại vô ích."""
    snap = [{'family': 'limit', 'side': 'sell', 'reduce_only': True, 'price': 1.52,
             'amount': 7.2, 'id': 'TP1', 'close_position': False}]
    huy = []
    plans, skips = M.plan_row([TP_LEG], _cvk_row(), 7.2, snap, True, None, 1.413, "buy",
                              resize_exits=True, resize_tol=0.01, cancel_out=huy)
    assert plans == [] and huy == []


def test_tp_resize_can_be_disabled():
    """Tắt exit_tp_resize → giữ hành vi cũ, không hủy lệnh nào."""
    snap = [{'family': 'limit', 'side': 'sell', 'reduce_only': True, 'price': 1.52,
             'amount': 7.2, 'id': 'TP1', 'close_position': False}]
    huy = []
    plans, _ = M.plan_row([TP_LEG], _cvk_row(), 14.6, snap, True, None, 1.413, "buy",
                          resize_exits=False, cancel_out=huy)
    assert plans == [] and huy == []


# ════════════════════════════════════════════════════════════════════════════
#  Chạy trực tiếp: python3 tests/test_hd_order_multi.py
# ════════════════════════════════════════════════════════════════════════════
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
            print(f"  💥 {name}  — LỖI: {e}")
    print(f"\n===== KẾT QUẢ: {npass} PASS / {nfail} FAIL / {len(tests)} test =====")
    sys.exit(1 if nfail else 0)
