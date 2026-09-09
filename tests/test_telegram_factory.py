"""
Test telegram_factory — KHÔNG gửi Telegram thật, chỉ kiểm tra logic.
    python3 tests/test_telegram_factory.py
"""
import os, sys, types, time

QBOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(QBOT); sys.path.insert(0, QBOT)

SENT = []


def _load():
    for m in ("telegram_factory", "cst", "telegram", "telegram.constants"):
        sys.modules.pop(m, None)
    tg = types.ModuleType("telegram"); tg.Bot = object; sys.modules["telegram"] = tg
    tc = types.ModuleType("telegram.constants")
    tc.ParseMode = types.SimpleNamespace(HTML="HTML")
    sys.modules["telegram.constants"] = tc
    c = types.ModuleType("cst"); c.bot_token = "x"; c.prefix_channel = ""
    sys.modules["cst"] = c
    import telegram_factory as T
    SENT.clear()
    T.send = lambda chat_id, text, is_html, prev: SENT.append((chat_id, text))
    return T


# ══════════════════════════════════════════════════════════════════════════
def test_send_tele_always_sends():
    """send_tele KHÔNG chặn trùng — gửi bao nhiêu lần cũng đi."""
    T = _load()
    for _ in range(3):
        T.send_tele("Cùng một tin", "-100", True, True)
    assert len(SENT) == 3


def test_send_tele_no_memory_growth():
    """send_tele KHÔNG tích tin vào bộ nhớ (trước đây rò rỉ)."""
    T = _load()
    for i in range(200):
        T.send_tele(f"tin {i}", "-100", True, True)
    assert len(T._recent_messages) == 0, "send_tele không được ghi vào _recent_messages"


def test_limit_blocks_duplicate_within_hour():
    """Cùng nội dung trong vòng 1 giờ → chỉ gửi 1 lần."""
    T = _load()
    for _ in range(3):
        T.send_tele_with_limit_per_hour("Cảnh báo ATOM", "-100", True, True, 5)
    assert len(SENT) == 1


def test_limit_allows_again_after_ttl():
    """Sau 1 giờ, tin cũ được QUÊN → gửi lại được (trước đây chặn vĩnh viễn)."""
    T = _load()
    T.send_tele_with_limit_per_hour("Cảnh báo ATOM", "-100", True, True, 5)
    assert len(SENT) == 1
    # tua thời gian: coi như tin đã gửi từ 2 giờ trước
    for k in list(T._recent_messages):
        T._recent_messages[k] = time.time() - 7200
    for u in T.sent_messages.values():
        u['last_sent_time'] = int(time.time()) - 7200
    T.send_tele_with_limit_per_hour("Cảnh báo ATOM", "-100", True, True, 5)
    assert len(SENT) == 2, "Sau 1 giờ phải gửi lại được"


def test_send_tele_does_not_swallow_limited():
    """
    send_tele gửi tin X trước, sau đó send_tele_with_limit_per_hour gửi X
    → VẪN phải gửi (bản cũ nuốt mất vì dùng chung danh sách).
    """
    T = _load()
    T.send_tele("Tin quan trọng", "-100", True, True)
    T.send_tele_with_limit_per_hour("Tin quan trọng", "-100", True, True, 5)
    assert len(SENT) == 2


def test_rate_limit_per_hour_enforced():
    """Quá số tin/giờ cho cùng nhóm (dòng đầu giống nhau) → chặn."""
    T = _load()
    for i in range(5):
        T.send_tele_with_limit_per_hour(f"NHOM A\nchi tiết {i}", "-100", True, True, 3)
    assert len(SENT) == 3, f"Phải chặn ở tin thứ 4, thực tế gửi {len(SENT)}"


def test_prune_keeps_memory_bounded():
    """Tin quá hạn bị dọn → bộ nhớ không phình vô hạn."""
    T = _load()
    old = time.time() - 7200
    for i in range(500):
        T._recent_messages[f"cũ {i}"] = old
    T._prune_recent()
    assert len(T._recent_messages) == 0


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
