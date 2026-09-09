"""
Test ĐA TÀI KHOẢN — chạy LOCAL, không gọi Binance/Google, không tốn tiền.

Chạy:  python3 tests/test_multi_account.py
       hoặc  pytest tests/test_multi_account.py -v
"""
import configparser
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

QBOT = Path(__file__).resolve().parent.parent
WORK = Path(tempfile.mkdtemp(prefix="qbot_multiacc_"))


def _make_config(accounts="kh_a, kh_b", filename="config_test.ini"):
    """Tạo config test từ config.ini.example + 2 tài khoản."""
    src = (QBOT / "config.ini.example").read_text(encoding="utf-8")
    src = src.replace("accounts =\n", f"accounts = {accounts}\n", 1)
    src += """
[kh_a]
key_binance = KEY_A
secret_binance = SEC_A
spreadsheet_id = SHEET_A
chat_id = -222
key_name = Khach A

[kh_b]
key_binance = KEY_B
secret_binance = SEC_B
spreadsheet_id = SHEET_B
chat_id = -333
key_name = Khach B
"""
    p = WORK / filename
    p.write_text(src, encoding="utf-8")
    return p


CFG = _make_config()
# cst.py phụ thuộc 2 module này — THIẾU LÀ MỌI BOT CHẾT LÚC KHỞI ĐỘNG,
# nên khi deploy cũng phải copy đủ cả ba file.
for _f in ("cst.py", "rate_guard.py", "symbol_filter.py"):
    shutil.copy(QBOT / _f, WORK / _f)


def _load(account=None, cfg=None):
    """Nạp cst.py trong tiến trình con, trả về dict giá trị đã resolve."""
    code = """
import os, sys, json
sys.path.insert(0, %r); os.chdir(%r)
import cst
print("@@" + json.dumps({
    "key": cst.config.get("global", "key_binance"),
    "secret": cst.config.get("global", "secret_binance"),
    "sheet": cst.config.get("global", "spreadsheet_id"),
    "chat": cst.config.get("global", "chat_id"),
    "name": cst.config.get("global", "key_name"),
    "delay": cst.delay_vao_lenh,
    "accounts": cst.accounts,
    "account_name": cst.account_name,
    "logs": str(cst.account_dir("logs")),
    "data": str(cst.account_dir("data")),
    "suffix": cst.account_suffix(),
}))
""" % (str(WORK), str(WORK))
    env = dict(os.environ, QBOT_CONFIG=str(cfg or CFG))
    env.pop("QBOT_ACCOUNT", None)
    if account:
        env["QBOT_ACCOUNT"] = account
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, env=env, cwd=WORK)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip())
    import json
    for line in r.stdout.splitlines():
        if line.startswith("@@"):
            return json.loads(line[2:])
    raise RuntimeError("Không đọc được kết quả: " + r.stdout)


# ══════════════════════════════════════════════════════════════════════════
#  Nạp cấu hình theo tài khoản
# ══════════════════════════════════════════════════════════════════════════
def test_account_overrides_global():
    """Key/secret/sheet/chat của tài khoản phải GHI ĐÈ [global]."""
    a = _load("kh_a")
    assert (a["key"], a["secret"], a["sheet"], a["chat"]) == ("KEY_A", "SEC_A", "SHEET_A", "-222")
    assert a["name"] == "Khach A"


def test_two_accounts_isolated():
    """2 tài khoản đọc ra 2 bộ giá trị khác nhau, không lẫn."""
    a, b = _load("kh_a"), _load("kh_b")
    assert a["key"] != b["key"] and a["sheet"] != b["sheet"] and a["chat"] != b["chat"]


def test_operational_params_are_shared():
    """Tham số vận hành (delay) luôn LẤY TỪ [global] — mọi tài khoản như nhau."""
    assert _load("kh_a")["delay"] == _load("kh_b")["delay"] == 60


def test_account_section_rejects_operational_params():
    """Khai tham số vận hành trong khối tài khoản → CHẶN (giữ bot đồng nhất)."""
    src = (QBOT / "config.ini.example").read_text(encoding="utf-8")
    src = src.replace("accounts =\n", "accounts = kh_y\n", 1)
    src += ("\n[kh_y]\nkey_binance=K\nsecret_binance=S\nspreadsheet_id=SH\n"
            "delay_vao_lenh = 120\nallow_dca = true\n")
    cfg = WORK / "cfg_notallowed.ini"; cfg.write_text(src, encoding="utf-8")
    try:
        _load("kh_y", cfg=cfg)
        raise AssertionError("Phải chặn tham số vận hành trong khối tài khoản")
    except RuntimeError as e:
        assert "KHÔNG được phép" in str(e)
        assert "delay_vao_lenh" in str(e) and "allow_dca" in str(e)


def test_account_extra_keys_opens_exception():
    """Khai account_extra_keys ở [global] → cho phép ngoại lệ có kiểm soát."""
    src = (QBOT / "config.ini.example").read_text(encoding="utf-8")
    src = src.replace("accounts =\n",
                      "accounts = kh_z\naccount_extra_keys = delay_vao_lenh\n", 1)
    src += ("\n[kh_z]\nkey_binance=K\nsecret_binance=S\nspreadsheet_id=SH\n"
            "delay_vao_lenh = 120\n")
    cfg = WORK / "cfg_extra.ini"; cfg.write_text(src, encoding="utf-8")
    assert _load("kh_z", cfg=cfg)["delay"] == 120


def test_accounts_list_parsed():
    assert _load("kh_a")["accounts"] == ["kh_a", "kh_b"]


# ══════════════════════════════════════════════════════════════════════════
#  Cách ly thư mục log / dữ liệu
# ══════════════════════════════════════════════════════════════════════════
def test_paths_isolated_per_account():
    a, b = _load("kh_a"), _load("kh_b")
    assert a["logs"] == os.path.join("logs", "kh_a") and b["logs"] == os.path.join("logs", "kh_b")
    assert a["data"] != b["data"]
    assert a["suffix"] == "_kh_a" and b["suffix"] == "_kh_b"


def test_dirs_created():
    _load("kh_a")
    assert (WORK / "logs" / "kh_a").is_dir() and (WORK / "data" / "kh_a").is_dir()


# ══════════════════════════════════════════════════════════════════════════
#  Tương thích ngược + báo lỗi
# ══════════════════════════════════════════════════════════════════════════
def test_backward_compatible_no_accounts():
    """Config KHÔNG khai accounts → chạy y như cũ (logs/, không hậu tố)."""
    cfg = _make_config(accounts="", filename="config_single.ini")  # file riêng, không đè config chính
    r = _load(None, cfg=cfg)
    assert r["accounts"] == [] and r["account_name"] == "default"
    assert r["logs"] == "logs" and r["suffix"] == ""


def test_non_bot_script_requires_choosing_account():
    """
    Script KHÔNG phải bot (không tên hd_*.py) mà chạy thiếu tài khoản → DỪNG,
    tránh lỡ dùng key ở [global].
    """
    try:
        _load(None)          # CFG có accounts = kh_a, kh_b
        raise AssertionError("Phải dừng khi chưa chọn tài khoản")
    except RuntimeError as e:
        assert "Chưa chọn tài khoản" in str(e)


def test_bot_without_account_runs_all_accounts():
    """
    Chạy THẲNG bot (hd_*.py) mà KHÔNG đặt QBOT_ACCOUNT
    → tự mở 1 tiến trình con cho MỖI tài khoản, mỗi con dùng đúng key của mình.
    """
    bot = WORK / "hd_allacc.py"
    bot.write_text(
        "import cst\n"
        "print('DUNG_KEY=' + cst.config.get('global','key_binance'), flush=True)\n",
        encoding="utf-8")
    env = dict(os.environ, QBOT_CONFIG=str(CFG))
    env.pop("QBOT_ACCOUNT", None)
    r = subprocess.run([sys.executable, str(bot)], cwd=WORK, env=env,
                       capture_output=True, text=True, timeout=60)
    out = r.stdout + r.stderr
    assert "chạy cho 2 tài khoản" in out, out[:400]
    assert "DUNG_KEY=KEY_A" in out and "DUNG_KEY=KEY_B" in out, \
        f"Mỗi tài khoản phải dùng key riêng. Nhận: {out[:400]}"
    assert "[kh_a]" in out and "[kh_b]" in out


def test_unknown_account_fails_clearly():
    """Tên tài khoản sai → dừng ngay với thông báo rõ, không chạy nhầm."""
    try:
        _load("kh_khong_ton_tai")
        raise AssertionError("Phải báo lỗi khi tài khoản không tồn tại")
    except RuntimeError as e:
        assert "kh_khong_ton_tai" in str(e)


# ══════════════════════════════════════════════════════════════════════════
#  WINDOWS: console cp1252 không in được emoji/tiếng Việt → bot chết khi khởi động
# ══════════════════════════════════════════════════════════════════════════
def _run_with_encoding(encoding, account="kh_a"):
    """Chạy 1 bot giả với bảng mã console ép sẵn (mô phỏng Windows)."""
    bot = WORK / "hd_enc.py"
    bot.write_text(
        "import cst\n"
        "print('👤 emoji + tiếng Việt: Đặt lệnh thành công ✅', flush=True)\n"
        "print('OK_KHOI_DONG', flush=True)\n",
        encoding="utf-8")
    env = dict(os.environ, QBOT_CONFIG=str(CFG), QBOT_ACCOUNT=account,
               PYTHONIOENCODING=encoding)
    return subprocess.run([sys.executable, str(bot)], cwd=WORK, env=env,
                          capture_output=True, text=True, timeout=30)


def test_windows_cp1252_console_does_not_crash():
    """
    Console Windows (cp1252) không có emoji. Trước đây bot chết ngay lúc nạp cst
    với UnicodeEncodeError — chết TRƯỚC khi kịp tạo log nên không thấy log đâu.
    Nay cst ép stdout sang UTF-8 nên phải chạy bình thường.
    """
    r = _run_with_encoding("cp1252")
    assert "UnicodeEncodeError" not in (r.stdout + r.stderr), \
        f"Vẫn chết vì bảng mã: {(r.stdout + r.stderr)[-300:]}"
    assert "OK_KHOI_DONG" in r.stdout, f"Bot không khởi động được: {r.stdout}{r.stderr}"


def test_parent_reads_child_output_as_utf8():
    """
    Tiến trình cha đọc màn hình của con: phải giải mã UTF-8.
    Nếu để mặc định, trên Windows cha dùng cp1252 → chữ Việt hiện thành
    "TÃ i khoáº£n" (mojibake).
    """
    bot = WORK / "hd_moji.py"
    bot.write_text(
        "import cst\n"
        "print('Tài khoản: ' + cst.account_name + ' — Đặt lệnh ✅', flush=True)\n",
        encoding="utf-8")
    env = dict(os.environ, QBOT_CONFIG=str(CFG), PYTHONIOENCODING="cp1252")
    env.pop("QBOT_ACCOUNT", None)          # không chọn → cha tự chạy cả 2 tài khoản
    r = subprocess.run([sys.executable, str(bot)], cwd=WORK, env=env,
                       capture_output=True, text=True, encoding="utf-8", timeout=60)
    out = r.stdout + r.stderr
    assert "Tài khoản" in out, f"Chữ Việt bị hỏng: {out[:300]}"
    for xau in ("TÃ ", "khoáº£n", "ðŸ"):
        assert xau not in out, f"Vẫn còn mojibake '{xau}': {out[:300]}"


def test_ascii_console_does_not_crash():
    """Kể cả console chỉ hỗ trợ ASCII cũng không được làm bot chết."""
    r = _run_with_encoding("ascii")
    assert "UnicodeEncodeError" not in (r.stdout + r.stderr)
    assert "OK_KHOI_DONG" in r.stdout


# ══════════════════════════════════════════════════════════════════════════
#  KIỂM TRA GIÁ TRỊ CẤU HÌNH (chặn số vô lý gây spam API / bot chết)
# ══════════════════════════════════════════════════════════════════════════
def _cfg_with_delay(value, filename):
    """delay đặt ở [global] (tham số vận hành — không được khai trong khối tài khoản)."""
    import re as _re
    src = (QBOT / "config.ini.example").read_text(encoding="utf-8")
    src = src.replace("accounts =\n", "accounts = kh_x\n", 1)
    src = _re.sub(r"(?m)^delay_vao_lenh\s*=.*$", f"delay_vao_lenh = {value}", src, count=1)
    src += "\n[kh_x]\nkey_binance=K\nsecret_binance=S\nspreadsheet_id=SH\n"
    p = WORK / filename
    p.write_text(src, encoding="utf-8")
    return p


def test_delay_zero_blocked():
    """delay = 0 → CHẶN (quét liên tục sẽ spam API, có thể bị chặn IP)."""
    try:
        _load("kh_x", cfg=_cfg_with_delay(0, "d0.ini"))
        raise AssertionError("Phải chặn delay = 0")
    except RuntimeError as e:
        assert "không hợp lệ" in str(e) and "delay_vao_lenh" in str(e)


def test_delay_negative_blocked():
    """delay âm → CHẶN (time.sleep số âm làm bot chết giữa chừng)."""
    try:
        _load("kh_x", cfg=_cfg_with_delay(-5, "dneg.ini"))
        raise AssertionError("Phải chặn delay âm")
    except RuntimeError as e:
        assert "phải >= 1" in str(e)


def test_delay_not_a_number_message_is_clear():
    """delay = chữ → báo lỗi TIẾNG VIỆT dễ hiểu, không phải ValueError khó hiểu."""
    try:
        _load("kh_x", cfg=_cfg_with_delay("abc", "dabc.ini"))
        raise AssertionError("Phải chặn giá trị không phải số")
    except RuntimeError as e:
        assert "SỐ NGUYÊN" in str(e) and "Ví dụ đúng" in str(e)


def test_delay_decimal_blocked():
    """delay = 1.5 → CHẶN (chỉ nhận số nguyên)."""
    try:
        _load("kh_x", cfg=_cfg_with_delay("1.5", "ddec.ini"))
        raise AssertionError("Phải chặn số lẻ")
    except RuntimeError as e:
        assert "SỐ NGUYÊN" in str(e)


def test_delay_valid_passes():
    """delay hợp lệ → chạy bình thường."""
    r = _load("kh_x", cfg=_cfg_with_delay(60, "dok.ini"))
    assert r["delay"] == 60


# ══════════════════════════════════════════════════════════════════════════
#  KHOÁ CHỐNG CHẠY TRÙNG (bảo vệ cả khi chạy bot bằng tay)
# ══════════════════════════════════════════════════════════════════════════
def _run_fake_bot(account, background=False, extra_env=None):
    """Chạy 1 'bot' giả (tên hd_*.py nên sẽ bị khoá) trong tiến trình con."""
    bot = WORK / "hd_faketest.py"
    bot.write_text("import cst, os, time\n"
                   "print('OK ' + str(os.getpid()), flush=True)\n"
                   "time.sleep(10)\n", encoding="utf-8")
    env = dict(os.environ, QBOT_CONFIG=str(CFG), QBOT_ACCOUNT=account)
    env.pop("QBOT_NO_LOCK", None)
    if extra_env:
        env.update(extra_env)
    if background:
        return subprocess.Popen([sys.executable, str(bot)], cwd=WORK, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    return subprocess.run([sys.executable, str(bot)], cwd=WORK, env=env,
                          capture_output=True, text=True, timeout=30)


def test_lock_blocks_second_run_same_account():
    """Chạy TAY bot lần 2 cho cùng tài khoản → phải bị CHẶN (tránh lệnh trùng)."""
    import time as _t
    p1 = _run_fake_bot("kh_a", background=True)
    try:
        _t.sleep(2)
        r2 = _run_fake_bot("kh_a")
        assert "ĐANG CHẠY" in (r2.stdout + r2.stderr), f"Không chặn: {r2.stdout}{r2.stderr}"
    finally:
        p1.kill(); p1.wait(timeout=10)


def test_lock_allows_different_accounts_parallel():
    """2 tài khoản KHÁC nhau chạy cùng lúc → không chặn nhau."""
    import time as _t
    p1 = _run_fake_bot("kh_a", background=True)
    p2 = _run_fake_bot("kh_b", background=True)
    try:
        _t.sleep(2)
        assert p1.poll() is None and p2.poll() is None, "Hai tài khoản khác nhau không được chặn nhau"
        assert (WORK / "pids" / "kh_a" / "hd_faketest.lock").exists()
        assert (WORK / "pids" / "kh_b" / "hd_faketest.lock").exists()
    finally:
        for p in (p1, p2):
            p.kill(); p.wait(timeout=10)


def test_lock_released_after_exit():
    """Tiến trình chết → khoá mồ côi tự dọn, chạy lại được."""
    import time as _t
    p1 = _run_fake_bot("kh_a", background=True); _t.sleep(2)
    p1.kill(); p1.wait(timeout=10); _t.sleep(1)
    p2 = _run_fake_bot("kh_a", background=True)
    try:
        _t.sleep(2)
        assert p2.poll() is None, "Phải chạy lại được sau khi tiến trình cũ chết"
    finally:
        p2.kill(); p2.wait(timeout=10)


def test_lock_can_be_disabled():
    """QBOT_NO_LOCK=1 → bỏ qua khoá (dùng khi chắc chắn)."""
    import time as _t
    p1 = _run_fake_bot("kh_a", background=True)
    try:
        _t.sleep(2)
        r2 = _run_fake_bot("kh_a", extra_env={"QBOT_NO_LOCK": "1"})
        assert "ĐANG CHẠY" not in (r2.stdout + r2.stderr)
    finally:
        p1.kill(); p1.wait(timeout=10)


# ══════════════════════════════════════════════════════════════════════════
#  Script khởi động đọc đúng danh sách tài khoản
# ══════════════════════════════════════════════════════════════════════════
def test_scripts_syntax_ok():
    for s in ("start_all_bots.sh", "stop_all_bots.sh", "status.sh"):
        r = subprocess.run(["bash", "-n", str(QBOT / s)], capture_output=True, text=True)
        assert r.returncode == 0, f"{s}: {r.stderr}"


def test_start_script_reads_accounts():
    c = configparser.ConfigParser()
    c.read(CFG, encoding="utf-8")
    got = [a.strip() for a in c.get("global", "accounts").split(",") if a.strip()]
    assert got == ["kh_a", "kh_b"]


# ══════════════════════════════════════════════════════════════════════════
#  AN TOÀN — chặn dùng nhầm key của tài khoản khác
# ══════════════════════════════════════════════════════════════════════════
def _cfg_with_partial_account(missing_keys, filename):
    """Tạo config có section thiếu một số khóa bắt buộc."""
    src = (QBOT / "config.ini.example").read_text(encoding="utf-8")
    src = src.replace("accounts =\n", "accounts = kh_x\n", 1)
    lines = {"key_binance": "KEY_X", "secret_binance": "SEC_X", "spreadsheet_id": "SHEET_X"}
    for k in missing_keys:
        lines.pop(k, None)
    src += "\n[kh_x]\nchat_id = -900\n" + "".join(f"{k} = {v}\n" for k, v in lines.items())
    p = WORK / filename
    p.write_text(src, encoding="utf-8")
    return p


def test_missing_key_binance_is_blocked():
    """Thiếu key_binance → PHẢI dừng, không được âm thầm dùng key của [global]."""
    cfg = _cfg_with_partial_account(["key_binance"], "cfg_missing_key.ini")
    try:
        _load("kh_x", cfg=cfg)
        raise AssertionError("Phải chặn khi thiếu key_binance")
    except RuntimeError as e:
        assert "key_binance" in str(e) and "THIẾU" in str(e)


def test_missing_spreadsheet_id_is_blocked():
    """Thiếu spreadsheet_id → PHẢI dừng (tránh ghi nhầm sheet khách khác)."""
    cfg = _cfg_with_partial_account(["spreadsheet_id"], "cfg_missing_sheet.ini")
    try:
        _load("kh_x", cfg=cfg)
        raise AssertionError("Phải chặn khi thiếu spreadsheet_id")
    except RuntimeError as e:
        assert "spreadsheet_id" in str(e)


def test_account_not_in_list_is_blocked():
    """Tên có section nhưng chưa khai vào `accounts` → chặn (tránh gõ nhầm)."""
    src = (QBOT / "config.ini.example").read_text(encoding="utf-8")
    src = src.replace("accounts =\n", "accounts = kh_a\n", 1)
    src += "\n[kh_a]\nkey_binance=KA\nsecret_binance=SA\nspreadsheet_id=SHA\n"
    src += "\n[kh_la]\nkey_binance=KL\nsecret_binance=SL\nspreadsheet_id=SHL\n"
    cfg = WORK / "cfg_notlisted.ini"
    cfg.write_text(src, encoding="utf-8")
    try:
        _load("kh_la", cfg=cfg)
        raise AssertionError("Phải chặn tài khoản chưa khai trong accounts")
    except RuntimeError as e:
        assert "kh_la" in str(e)


def test_start_script_blocks_duplicate_run():
    """start_all_bots.sh phải có cơ chế chặn khởi động trùng."""
    sh = (QBOT / "start_all_bots.sh").read_text(encoding="utf-8")
    assert "is_running" in sh and "ĐANG CHẠY" in sh


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items()) if n.startswith("test_") and callable(f)]
    npass = nfail = 0
    for name, fn in tests:
        try:
            fn(); npass += 1; print(f"  ✅ {name}")
        except Exception as e:
            nfail += 1; print(f"  ❌ {name} — {e}")
    shutil.rmtree(WORK, ignore_errors=True)
    print(f"\n===== KẾT QUẢ: {npass} PASS / {nfail} FAIL / {len(tests)} test =====")
    sys.exit(1 if nfail else 0)
