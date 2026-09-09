"""
Test BỘ LỌC của bot hủy lệnh (hd_cancel_orders_schedule.py) — chạy LOCAL, an toàn.

Bảo đảm: bot KHÔNG xoá nhầm SL/TP và KHÔNG xoá lệnh rải còn mới.
    python3 tests/test_cancel_filter.py
"""
import os, sys, types, time, configparser, tempfile, pathlib

QBOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(QBOT); sys.path.insert(0, QBOT)


def _mod(n, **a):
    m = types.ModuleType(n); [setattr(m, k, v) for k, v in a.items()]; sys.modules[n] = m; return m


def _load(cancel_all=False, after_min=30):
    """Nạp lại module hd_cancel_orders_schedule với cấu hình mong muốn."""
    for m in ("hd_cancel_orders_schedule", "cst", "ccxt", "gg_sheet_factory",
              "telegram_factory", "binance_futures_direct"):
        sys.modules.pop(m, None)

    class FE:
        def __init__(s, *a, **k): pass
        def setSandboxMode(s, *a, **k): pass
        def fetch_open_orders(s, sym): return []
    _mod("ccxt", binance=FE)

    cfg = configparser.ConfigParser()
    cfg.read_dict({"global": {"cancel_all_orders": str(cancel_all).lower(),
                              "cancel_order_after_minutes": str(after_min)}})
    tmp = pathlib.Path(tempfile.mkdtemp())
    def ad(b):
        d = tmp / b; d.mkdir(parents=True, exist_ok=True); return d
    _mod("cst", key_name="T", key_binance="x", secret_binance="y", chat_id="0",
         cancel_orders_minutes=1, config=cfg, account_dir=ad, account_suffix=lambda: "",
         accounts=[], account="", account_name="default")
    _mod("gg_sheet_factory", get_cho_va_khop=lambda *a, **k: [], tab_cho_va_khop="x")
    _mod("telegram_factory", send_tele=lambda *a, **k: None)
    _mod("binance_futures_direct", resync_exchange_time=lambda *a, **k: None)

    # chặn vòng lặp chính chạy khi import
    src = open(os.path.join(QBOT, "hd_cancel_orders_schedule.py"), encoding="utf-8").read()
    src = src.split("# Main loop")[0]
    mod = types.ModuleType("hd_cancel_orders_schedule")
    mod.__dict__["__name__"] = "hd_cancel_orders_schedule"
    mod.__dict__["__file__"] = os.path.join(QBOT, "hd_cancel_orders_schedule.py")
    exec(compile(src, "hd_cancel_orders_schedule.py", "exec"), mod.__dict__)
    return mod


NOW_MS = time.time() * 1000
def _order(minutes_old=60, reduce_only=False, oid="1"):
    return {"id": oid, "timestamp": NOW_MS - minutes_old * 60000,
            "reduceOnly": reduce_only, "info": {"reduceOnly": str(reduce_only).lower()}}


# ══════════════════════════════════════════════════════════════════════════
def test_sl_tp_never_cancelled():
    """SL/TP (reduce_only) KHÔNG được hủy, dù treo rất lâu."""
    M = _load()
    ok, ly_do = M._should_cancel(_order(minutes_old=999, reduce_only=True), "ATOM/USDT", "open")
    assert ok is False and "reduce_only" in ly_do


def test_fresh_entry_kept():
    """Lệnh VÀO còn mới (5 phút) được GIỮ để chờ khớp — quan trọng khi rải lệnh."""
    M = _load(after_min=30)
    ok, ly_do = M._should_cancel(_order(minutes_old=5), "ATOM/USDT", "open")
    assert ok is False and "chờ khớp" in ly_do


def test_old_entry_cancelled():
    """Lệnh VÀO treo quá lâu (60 phút) thì mới hủy."""
    M = _load(after_min=30)
    ok, _ = M._should_cancel(_order(minutes_old=60), "ATOM/USDT", "open")
    assert ok is True


def test_unknown_age_kept():
    """Không xác định được tuổi lệnh → giữ (an toàn hơn là xoá nhầm)."""
    M = _load()
    ok, ly_do = M._should_cancel({"id": "9"}, "ATOM/USDT", "open")
    assert ok is False and "tuổi" in ly_do


def test_algo_trailing_reduce_only_kept():
    """Algo (trailing/stop) reduce_only cũng phải được giữ."""
    M = _load()
    o = {"algoId": "7", "algoType": "CONDITIONAL", "createTime": NOW_MS - 120 * 60000,
         "reduceOnly": "true", "info": {}}
    ok, _ = M._should_cancel(o, "ATOM/USDT", "algo")
    assert ok is False


def test_close_position_flag_kept():
    """Lệnh closePosition=true (đóng toàn bộ vị thế) cũng là lệnh bảo vệ → giữ."""
    M = _load()
    o = {"id": "5", "timestamp": NOW_MS - 999 * 60000, "info": {"closePosition": "true"}}
    ok, _ = M._should_cancel(o, "ATOM/USDT", "open")
    assert ok is False


def test_legacy_mode_cancels_everything():
    """cancel_all_orders=true → quay lại hành vi cũ (hủy tất, kể cả SL/TP)."""
    M = _load(cancel_all=True)
    ok, _ = M._should_cancel(_order(minutes_old=1, reduce_only=True), "ATOM/USDT", "open")
    assert ok is True


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    np = nf = 0
    for name, fn in tests:
        try:
            fn(); np += 1; print(f"  ✅ {name}")
        except Exception as e:
            nf += 1; print(f"  ❌ {name} — {e}")
    print(f"\n===== KẾT QUẢ: {np} PASS / {nf} FAIL / {len(tests)} test =====")
    sys.exit(1 if nf else 0)
