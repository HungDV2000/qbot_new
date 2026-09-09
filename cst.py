"""
Nạp cấu hình cho QBot.

HỖ TRỢ ĐA TÀI KHOẢN (nhiều bộ key/secret/sheetID trong CÙNG 1 file config):

    [global]
    accounts = kh_a, kh_b          ; danh sách tài khoản
    delay_vao_lenh = 60            ; cấu hình DÙNG CHUNG
    ...

    [kh_a]
    key_binance    = ...
    secret_binance = ...
    spreadsheet_id = ...
    chat_id        = ...

Chọn tài khoản khi chạy bằng biến môi trường:
    QBOT_ACCOUNT=kh_a python3 hd_order_multi.py

Cơ chế: giá trị trong [kh_a] được GHI ĐÈ lên [global], nên toàn bộ code cũ
(config.get('global', ...)) tự động lấy đúng cấu hình của tài khoản đang chạy.

TƯƠNG THÍCH NGƯỢC: không khai `accounts` và không set QBOT_ACCOUNT
→ chạy y hệt như trước (đọc config.ini, dùng thẳng [global]).
"""
import configparser
import os
import sys
from pathlib import Path

# ══════════════════════════════════════════════════════════════════════════════
# ÉP MÀN HÌNH DÙNG UTF-8 — PHẢI ĐẶT TRƯỚC MỌI LỆNH print
#
# Trên Windows, cửa sổ lệnh mặc định dùng bảng mã cp1252 (không có tiếng Việt
# đầy đủ, không có emoji). Chỉ cần in một ký tự như 👤 hay ✅ là bot CHẾT NGAY
# với UnicodeEncodeError — chết trước khi kịp tạo file log, nên không thấy log đâu.
#
# cst.py được nạp ĐẦU TIÊN bởi mọi bot, nên sửa ở đây là mọi bot đều an toàn.
# errors='replace': ký tự nào không hiển thị được thì thay bằng '?' thay vì chết.
# ══════════════════════════════════════════════════════════════════════════════
# ── Ép Console Windows dùng codepage UTF-8 (65001) ──────────────────────────
# Không có bước này, CMD vẫn dùng cp1252 → emoji/tiếng Việt hiện thành mojibake
# (ví dụ: 👤 → ðŸ'¤, Tài khoản → TÃ i khoáº£n) dù Python stream đã reconfigure.
import sys as _sys_platform_check
if _sys_platform_check.platform == 'win32':
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        ctypes.windll.kernel32.SetConsoleCP(65001)
    except Exception:
        pass  # Không phải Windows hoặc không có quyền — bỏ qua

for _stream_name in ('stdout', 'stderr'):
    _stream = getattr(sys, _stream_name, None)
    if _stream is None:
        continue
    try:
        _stream.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        # Python cũ hoặc stream đã bị thay thế → thử bọc lại thủ công
        try:
            import io
            setattr(sys, _stream_name,
                    io.TextIOWrapper(_stream.buffer, encoding='utf-8',
                                     errors='replace', line_buffering=True))
        except Exception:
            pass   # không ép được thì vẫn chạy, chỉ là chữ có thể hiển thị sai

# ── File config (đổi được bằng QBOT_CONFIG) ─────────────────────────────────
config_file = os.environ.get('QBOT_CONFIG', 'config.ini').strip() or 'config.ini'

# inline_comment_prefixes=(';',): cho phép ghi chú CÙNG DÒNG bằng dấu ';'
#   delay_vao_lenh = 60      ; quét mỗi 60 giây
# Nếu không bật, giá trị sẽ thành "60      ; quét mỗi 60 giây" → lỗi khó hiểu.
# Chỉ nhận ';' (không nhận '#') vì '#' có thể nằm trong giá trị.
config = configparser.ConfigParser(inline_comment_prefixes=(';',))
with open(config_file, encoding='utf-8') as file:
    config.read_file(file)


def get_accounts():
    """Danh sách tài khoản khai trong [global] accounts. Rỗng = chế độ 1 tài khoản."""
    raw = config.get('global', 'accounts', fallback='').strip()
    return [a.strip() for a in raw.split(',') if a.strip()]


accounts = get_accounts()


# ══════════════════════════════════════════════════════════════════════════════
# KHỚP TÊN TÀI KHOẢN — BỎ QUA KHÁC BIỆT HOA/THƯỜNG
#
# configparser PHÂN BIỆT hoa/thường ở tên section: [q2Fu] và [q2fu] là HAI thứ
# khác nhau. Rất dễ nhầm: khai `accounts = q2fu` nhưng section viết [q2Fu]
# → bot báo "không tìm thấy section" dù nhìn bằng mắt thấy rõ nó nằm đó.
# (Ngược lại, tên THAM SỐ bên trong thì configparser tự hạ về chữ thường,
#  nên Key_Binance và key_binance là một.)
#
# Ở đây khớp bỏ qua hoa/thường cho dễ dùng, NHƯNG nếu có từ 2 section chỉ khác
# hoa/thường thì DỪNG NGAY — không đoán bừa, vì đoán sai nghĩa là đặt lệnh
# bằng API key của khách khác.
# ══════════════════════════════════════════════════════════════════════════════
def resolve_section(name):
    """Trả về tên section thật khớp `name` (bỏ qua hoa/thường), hoặc None."""
    if not name:
        return None
    if config.has_section(name):
        return name
    trung = [s for s in config.sections() if s.lower() == name.lower()]
    if len(trung) == 1:
        return trung[0]
    if len(trung) > 1:
        raise SystemExit(
            f"❌ Có {len(trung)} section chỉ khác nhau chữ hoa/thường: "
            f"{', '.join('[' + t + ']' for t in trung)}.\n"
            f"   Không thể đoán bạn muốn dùng cái nào — hãy đổi tên cho khác hẳn."
        )
    return None

# ══════════════════════════════════════════════════════════════════════════════
# NHỮNG GÌ ĐƯỢC KHAI RIÊNG TRONG KHỐI [tên_tài_khoản]
#   → Chỉ thông tin NHẬN DẠNG: tài khoản Binance, Google Sheet, Telegram.
#   → Mọi thứ khác (delay, cấu hình lệnh, tỉ lệ…) phải ở [global] cho đồng nhất.
# Muốn nới lỏng: khai ở [global]  →  account_extra_keys = ten_tham_so_1, ten_2
# ══════════════════════════════════════════════════════════════════════════════
ACCOUNT_ALLOWED_KEYS = {
    'key_binance',      # API key Binance
    'secret_binance',   # API secret Binance
    'spreadsheet_id',   # Google Sheet của khách
    'chat_id',          # nhóm Telegram nhận thông báo
    'bot_token',        # bot Telegram riêng (nếu có)
    'prefix_channel',   # tiền tố hiển thị trong tin nhắn
    'key_name',         # tên hiển thị của tài khoản
}

import subprocess
import sys as _sys_mod
import threading
import time

_sys_argv0 = _sys_mod.argv[0] if _sys_mod.argv else ''


def _run_for_all_accounts(entry_file):
    """
    Mở một tiến trình con cho MỖI tài khoản (chạy lại chính file bot này),
    chuyển tiếp màn hình có gắn tên tài khoản, và dừng sạch khi Ctrl+C.
    Hàm này KHÔNG trả về — kết thúc bằng sys.exit().
    """
    # Kiểm tra TRƯỚC khi mở tiến trình con: tài khoản nào khai mà không có
    # section thì báo NGAY 1 lần, thay vì để từng con chết rải rác khó đọc.
    _thieu = [a for a in accounts if resolve_section(a) is None]
    if _thieu:
        raise SystemExit(
            "❌ Các tài khoản sau khai trong `accounts` nhưng KHÔNG có section "
            f"tương ứng trong {config_file}:\n"
            + "".join(f"     • [{a}]\n" for a in _thieu)
            + f"   Các section đang có: {', '.join('[' + x + ']' for x in config.sections())}\n"
            "   Hãy thêm section cho đủ, hoặc bỏ tên đó khỏi dòng `accounts`.\n"
            "   (Không cho chạy tiếp vì tài khoản thiếu section sẽ dùng nhầm "
            "key trong [global] — tức là key của khách khác.)"
        )

    bot = entry_file[:-3]
    print("=" * 62, flush=True)
    print(f"  {bot} — chạy cho {len(accounts)} tài khoản: {', '.join(accounts)}", flush=True)
    print(f"  (Ctrl+C để dừng tất cả)", flush=True)
    print("=" * 62, flush=True)

    # Giãn giờ khởi động: các tài khoản lệch pha nhau nên không cùng gọi
    # Google Sheets / Binance trong một khoảnh khắc → tránh lỗi 429.
    # Mặc định 20s; chỉnh bằng account_start_stagger_sec trong [global].
    try:
        stagger = config.getfloat('global', 'account_start_stagger_sec', fallback=20.0)
    except Exception:
        stagger = 20.0
    if stagger < 0:
        stagger = 0.0

    procs = {}
    for i, acc in enumerate(accounts):
        if i > 0 and stagger > 0:
            print(f"  ⏳ Chờ {stagger:.0f}s trước khi khởi động [{acc}] (tránh rate limit)...", flush=True)
            time.sleep(stagger)
        env = dict(os.environ, QBOT_ACCOUNT=acc, QBOT_CONFIG=config_file)
        try:
            p = subprocess.Popen(
                [_sys_mod.executable, entry_file],
                env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                # encoding='utf-8' BẮT BUỘC: tiến trình con ghi UTF-8, nếu để mặc
                # định thì trên Windows cha giải mã bằng cp1252 → chữ Việt và emoji
                # hiện thành "TÃ i khoáº£n" (mojibake).
                text=True, encoding='utf-8', errors='replace', bufsize=1,
            )
        except Exception as e:
            print(f"  ❌ Không mở được tiến trình cho [{acc}]: {e}", flush=True)
            continue
        procs[acc] = p
        print(f"  ▶ [{acc}] đã khởi động (PID {p.pid})", flush=True)

    if not procs:
        raise SystemExit("❌ Không khởi động được tài khoản nào.")

    def _relay(acc, proc):
        """In màn hình của tiến trình con, gắn tên tài khoản cho dễ theo dõi."""
        try:
            for line in proc.stdout:
                print(f"[{acc}] {line.rstrip()}", flush=True)
        except Exception:
            pass

    for acc, p in procs.items():
        threading.Thread(target=_relay, args=(acc, p), daemon=True).start()

    try:
        while True:
            time.sleep(2)
            for acc, p in list(procs.items()):
                if p.poll() is not None:      # con đã thoát
                    print(f"  ⚠️ [{acc}] đã dừng (mã thoát {p.returncode})", flush=True)
                    procs.pop(acc, None)
            if not procs:
                print("  ℹ️ Tất cả tài khoản đã dừng.", flush=True)
                break
    except KeyboardInterrupt:
        print("\n  ⏹ Đang dừng tất cả tài khoản...", flush=True)
    finally:
        for acc, p in procs.items():
            try:
                p.terminate()
            except Exception:
                pass
        for acc, p in procs.items():
            try:
                p.wait(timeout=10)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass
            print(f"  ✔ [{acc}] đã dừng", flush=True)
    raise SystemExit(0)


# ── Tài khoản đang chạy ─────────────────────────────────────────────────────
account = os.environ.get('QBOT_ACCOUNT', '').strip()

if account:
    _that = resolve_section(account)
    if _that is None:
        raise SystemExit(
            f"❌ Không tìm thấy section [{account}] trong {config_file}.\n"
            f"   Các section đang có: {', '.join('[' + s + ']' for s in config.sections())}\n"
            f"   Các tài khoản đang khai: {', '.join(accounts) if accounts else '(chưa khai accounts)'}"
        )
    if _that != account:
        # Khác chữ hoa/thường — vẫn chạy, nhưng phải báo để đại ca sửa cho khớp
        print(f"⚠️  Tên tài khoản '{account}' khác chữ hoa/thường với section "
              f"[{_that}] trong {config_file} — đang dùng [{_that}]. "
              f"Nên sửa lại cho khớp hẳn.", flush=True)
        account = _that
    if accounts and account.lower() not in {a.lower() for a in accounts}:
        raise SystemExit(
            f"❌ [{account}] chưa được khai trong `accounts` ở [global] của {config_file}.\n"
            f"   Đang khai: {', '.join(accounts)}"
        )

    # ⚠️ AN TOÀN: các thông tin nhận dạng tài khoản BẮT BUỘC khai riêng trong section.
    # Thiếu 1 trong số này, configparser sẽ lấy giá trị của [global] → bot có thể
    # đặt lệnh bằng API key của khách KHÁC hoặc ghi nhầm sang Google Sheet khác.
    _own_keys = set(config[account].keys()) - set(config.defaults().keys())
    _missing = [k for k in ('key_binance', 'secret_binance', 'spreadsheet_id')
                if k not in _own_keys]
    if _missing:
        raise SystemExit(
            f"❌ Section [{account}] trong {config_file} THIẾU: {', '.join(_missing)}\n"
            f"   Bắt buộc khai riêng cho từng tài khoản, nếu không bot sẽ dùng nhầm\n"
            f"   giá trị của [global] (API key / Google Sheet của khách khác).\n"
            f"   Thêm vào section [{account}]:\n"
            + "".join(f"       {k} = <giá trị của {account}>\n" for k in _missing)
        )

    # ══════════════════════════════════════════════════════════════════════
    # CHỈ CHO PHÉP KHAI "DANH TÍNH TÀI KHOẢN" TRONG SECTION RIÊNG
    #
    # Mọi cấu hình VẬN HÀNH (thời gian quét, cấu hình lệnh, tỉ lệ…) phải nằm ở
    # [global] để mọi tài khoản chạy ĐỒNG NHẤT — dễ kiểm soát, dễ hỗ trợ, tránh
    # tình trạng mỗi khách một kiểu rồi không biết vì sao chạy khác nhau.
    # Khai tham số ngoài danh sách dưới đây → bot DỪNG và chỉ rõ dòng sai.
    # ══════════════════════════════════════════════════════════════════════
    _extra = {k.strip().lower() for k in
              config.get('global', 'account_extra_keys', fallback='').split(',') if k.strip()}
    _allowed = ACCOUNT_ALLOWED_KEYS | _extra

    _own_keys = set(config[account].keys()) - set(config.defaults().keys())
    _not_allowed = sorted(k for k in _own_keys if k not in _allowed)
    if _not_allowed:
        raise SystemExit(
            f"❌ Section [{account}] trong {config_file} khai tham số KHÔNG được phép:\n"
            + "".join(f"       {k}\n" for k in _not_allowed)
            + f"   Trong khối tài khoản chỉ được khai thông tin nhận dạng:\n"
            + f"       {', '.join(sorted(ACCOUNT_ALLOWED_KEYS))}\n"
            f"   Các tham số vận hành (thời gian quét, cấu hình lệnh…) phải đặt ở\n"
            f"   [global] để mọi tài khoản chạy giống nhau.\n"
            f"   → Chuyển {len(_not_allowed)} dòng trên lên [global], hoặc xoá đi.\n"
            f"   (Nếu thực sự cần cho phép riêng, khai ở [global]:\n"
            f"        account_extra_keys = {', '.join(_not_allowed)})"
        )

    # Ghi đè [account] lên [global] → code cũ không cần sửa
    for _k, _v in config.items(account):
        config.set('global', _k, _v)
    print(f"👤 [CONFIG] Tài khoản: {account} (file: {config_file})", flush=True)
elif accounts:
    # ══════════════════════════════════════════════════════════════════════════
    # CHẠY 1 LẦN CHO TẤT CẢ TÀI KHOẢN
    #
    # Gõ:  python3 hd_order_multi.py     (không cần đặt QBOT_ACCOUNT)
    # → Tiến trình này thành "điều phối": mở cho MỖI tài khoản một tiến trình
    #   con riêng của chính bot đó, rồi trông coi chúng.
    #
    # Vì sao mỗi tài khoản một tiến trình (không gộp chung vào 1 vòng lặp):
    #   • Cách ly hoàn toàn — tài khoản này lỗi không kéo tài khoản kia chết theo
    #   • Chạy SONG SONG — không phải chờ quét xong khách A mới tới khách B
    #   • Không phải sửa logic bot; mọi biến cấu hình vẫn thuộc đúng 1 tài khoản
    #
    # Ctrl+C ở tiến trình điều phối sẽ dừng sạch toàn bộ tài khoản.
    # ══════════════════════════════════════════════════════════════════════════
    _entry_file = os.path.basename(_sys_argv0 or '')
    if _entry_file.startswith('hd_') and _entry_file.endswith('.py'):
        _run_for_all_accounts(_entry_file)      # spawn + trông coi, xong thì thoát
    else:
        raise SystemExit(
            f"❌ Chưa chọn tài khoản.\n"
            f"   {config_file} đang khai {len(accounts)} tài khoản: {', '.join(accounts)}\n"
            f"   Đặt QBOT_ACCOUNT=<tên> rồi chạy lại."
        )

# Tên dùng cho log/thư mục. Không có tài khoản → 'default' (giữ đường dẫn cũ).
account_name = account or 'default'


def account_dir(base: str) -> Path:
    """
    Thư mục riêng theo tài khoản, tự tạo nếu chưa có.
      - Có tài khoản : logs/kh_a , data/kh_a , order/kh_a
      - Không (cũ)   : logs , data , order        ← giữ nguyên như trước
    """
    p = Path(base) / account if account else Path(base)
    p.mkdir(parents=True, exist_ok=True)
    return p


# ══════════════════════════════════════════════════════════════════════════════
# KHOÁ CHỐNG CHẠY TRÙNG (single instance)
#
# Chạy 2 lần cùng một bot cho cùng một tài khoản = 2 tiến trình cùng quét 1 sheet
# → ĐẶT LỆNH TRÙNG → mất tiền. Script start_all_bots.sh đã chặn, nhưng chạy TAY
#   (QBOT_ACCOUNT=kh_a python3 hd_order_multi.py) thì không có gì chặn.
#
# Khoá này nằm ngay trong bot nên bảo vệ CẢ HAI cách chạy.
# Tắt khi cần: QBOT_NO_LOCK=1 python3 <bot>.py
# ══════════════════════════════════════════════════════════════════════════════
import atexit
import sys as _sys


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError, PermissionError):
        return False


def acquire_single_instance_lock(bot_name: str):
    """
    Giữ khoá cho (bot_name + tài khoản). Đang chạy rồi → DỪNG thay vì chạy chồng.
    Trả về đường dẫn file khoá, hoặc None nếu bỏ qua.
    """
    if os.environ.get('QBOT_NO_LOCK', '').strip() in ('1', 'true', 'yes'):
        return None

    lock_dir = account_dir('pids')
    lock_file = lock_dir / f'{bot_name}.lock'

    if lock_file.exists():
        try:
            old_pid = int(lock_file.read_text().strip() or 0)
        except (ValueError, OSError):
            old_pid = 0
        if old_pid and old_pid != os.getpid() and _pid_alive(old_pid):
            raise SystemExit(
                f"\n⛔ {bot_name} ĐANG CHẠY cho tài khoản '{account_name}' (PID {old_pid}).\n"
                f"   Chạy thêm sẽ ĐẶT LỆNH TRÙNG → không khởi động.\n"
                f"   Muốn chạy lại:  kill {old_pid}   rồi thử lại\n"
                f"   (hoặc QBOT_NO_LOCK=1 để bỏ qua khoá — chỉ khi chắc chắn)\n"
            )
        # PID cũ đã chết → khoá mồ côi, ghi đè được

    try:
        lock_file.write_text(str(os.getpid()))
    except OSError as e:
        print(f"⚠️ Không ghi được khoá {lock_file}: {e} — vẫn chạy tiếp", flush=True)
        return None

    def _release():
        try:
            if lock_file.exists() and lock_file.read_text().strip() == str(os.getpid()):
                lock_file.unlink()
        except OSError:
            pass
    atexit.register(_release)
    return lock_file


# Tự động khoá khi chạy trực tiếp một bot (file hd_*.py) — không cần sửa bot nào.
# Test / script phụ / import gián tiếp KHÔNG bị ảnh hưởng.
try:
    _entry = os.path.basename(_sys.argv[0] or '')
    if _entry.startswith('hd_') and _entry.endswith('.py'):
        acquire_single_instance_lock(_entry[:-3])
except SystemExit:
    raise
except Exception as _e:
    print(f"⚠️ Bỏ qua khoá chống chạy trùng: {_e}", flush=True)


def account_suffix() -> str:
    """Hậu tố gắn vào tên file riêng theo tài khoản ('' nếu chế độ 1 tài khoản)."""
    return f"_{account}" if account else ""

is_print_mode = config.getboolean('global', 'is_print_mode')
top_count = config.getint('global', 'top_count')

# ── Chọn mã lấy dữ liệu (xem symbol_filter.py) ──────────────────────────────
#   symbol_mode = all   → top biến động như cũ (top_count)
#   symbol_mode = list  → chỉ lấy các mã khai trong symbol_list
import symbol_filter
symbol_mode = symbol_filter.read_mode(config)
symbol_list, _symbol_trung = symbol_filter.read_symbol_list(config)
for _goc, _chuan in _symbol_trung:
    print(f"⚠️  symbol_list: '{_goc}' trùng với mã đã khai ({_chuan}) — bỏ qua.", flush=True)

# Cột ghi giá của hd_update_price. Mặc định C = "Giá trị hiện thời".
# TRƯỚC ĐÂY ghi nhầm vào cột Y (= "% đến BB1h dưới" của hd_update_all),
# khiến hai bot ghi đè lên nhau mỗi vòng.
price_column = (config.get('global', 'price_column', fallback='C') or 'C').strip().upper()
time_gap_do_it = config.getint('global', 'time_gap_do_it')
bot_token = config.get('global', 'bot_token')
chat_id = config.get('global', 'chat_id')
prefix_channel = config.get('global', 'prefix_channel', fallback='')

key_name = config.get('global', 'key_name')
key_binance = config.get('global', 'key_binance')
secret_binance = config.get('global', 'secret_binance')
test_mode = config.getboolean('global', 'test_mode')
spreadsheet_id = config.get('global', 'spreadsheet_id')
tab_dat_lenh = config.get('global', 'tab_dat_lenh')

# ══════════════════════════════════════════════════════════════════════════════
# KIỂM TRA GIÁ TRỊ CẤU HÌNH
#
# Các mốc thời gian phải là số nguyên DƯƠNG. Điền sai sẽ gây hậu quả thật:
#   • 0 hoặc số âm → bot quét liên tục không nghỉ → spam API → Binance/Google
#                     chặn IP, hoặc time.sleep(số âm) làm bot chết giữa chừng
#   • chữ / số lẻ  → bot chết ngay lúc khởi động với lỗi khó hiểu
#   • số quá lớn   → bot gần như không chạy (ngủ nhiều ngày)
# Nên bắt lỗi tại đây, báo bằng tiếng Việt kèm cách sửa.
# ══════════════════════════════════════════════════════════════════════════════
def _get_time_setting(key, minimum=1, warn_below=None, warn_above=None, unit='giây'):
    raw = config.get('global', key, fallback='').strip()
    who = f"[{account}]" if account else "[global]"

    if raw == '':
        raise SystemExit(
            f"❌ Thiếu `{key}` trong {config_file} {who}.\n"
            f"   Thêm dòng:  {key} = 60"
        )
    try:
        val = int(raw)
    except ValueError:
        raise SystemExit(
            f"❌ `{key} = {raw}` không hợp lệ {who} — phải là SỐ NGUYÊN ({unit}).\n"
            f"   Ví dụ đúng:  {key} = 60      (không dùng chữ, không dùng số lẻ như 1.5)"
        )
    if val < minimum:
        raise SystemExit(
            f"❌ `{key} = {val}` không hợp lệ {who} — phải >= {minimum}.\n"
            f"   Đặt 0 hoặc số âm sẽ khiến bot quét liên tục không nghỉ,\n"
            f"   gây spam API và có thể bị Binance/Google chặn.\n"
            f"   Ví dụ đúng:  {key} = 60"
        )
    if warn_below is not None and val < warn_below:
        print(f"⚠️ [CONFIG] {who} {key} = {val} {unit} — khá ngắn, dễ chạm giới hạn "
              f"API khi chạy nhiều tài khoản (khuyến nghị >= {warn_below}).", flush=True)
    if warn_above is not None and val > warn_above:
        print(f"⚠️ [CONFIG] {who} {key} = {val} {unit} — rất dài, bot sẽ hiếm khi chạy.",
              flush=True)
    return val


delay_vao_lenh = _get_time_setting('delay_vao_lenh', minimum=1, warn_below=15, warn_above=3600)
delay_vao_lenh_123 = _get_time_setting('delay_vao_lenh_123', minimum=1, warn_below=15)
delay_cho_va_khop = _get_time_setting('delay_cho_va_khop', minimum=1, warn_below=30)
delay_update_price = _get_time_setting('delay_update_price', minimum=1, warn_below=15)
delay_update_all = _get_time_setting('delay_update_all', minimum=1, warn_below=15)
delay_calert_possition_and_open_order = _get_time_setting('delay_calert_possition_and_open_order', minimum=1, warn_below=15)

lenh2_rate_long = config.getfloat('global', 'lenh2_rate_long')
lenh2_rate_short = config.getfloat('global', 'lenh2_rate_short')
lenh3_rate_long = config.getfloat('global', 'lenh3_rate_long')
lenh3_rate_short = config.getfloat('global', 'lenh3_rate_short')
lenh3_callback_rate = config.getfloat('global', 'lenh3_callback_rate')
# O trống / NGAY → TP trailing kích hoạt ngay tại giá mark/last (phương án A)
lenh3_o_empty_immediate = config.getboolean('global', 'lenh3_o_empty_immediate', fallback=True)
cancel_orders_minutes = _get_time_setting('cancel_orders_minutes', minimum=1, unit='phút')
max_increase_decrease_4h_day_count = config.getint('global', 'max_increase_decrease_4h_day_count')

# Phase 3 & 4 delays
delay_track_30_prices = _get_time_setting('delay_track_30_prices', minimum=1, warn_below=15)
delay_periodic_report = _get_time_setting('delay_periodic_report', minimum=1, warn_below=30)

# Telegram command bot: True = folder này chạy listener (nhận lệnh); False = chỉ chạy hd_order, không nhận lệnh
# Mặc định False: nếu config.ini chưa có run_tele_command thì không chạy (tránh bật nhầm)
run_tele_command = config.getboolean('global', 'run_tele_command', fallback=False)

# hd_update_all: ghi logs/column_audit_LAST.json (+ file theo timestamp) cho đúng 1 mã — để đối chiếu từng cột (để trống = tắt)
debug_column_audit_symbol = config.get('global', 'debug_column_audit_symbol', fallback='').strip()

# hd_update_all: ghi log [PROFILE] thời gian từng phase (fetch_tickers, batch get_row, sheet…). false = log gọn hơn
profile_do_it = config.getboolean('global', 'profile_do_it', fallback=True)

# ─────────────────────────────────────────────────────────────────────────────
# [TASK 1] Default values cho sheet "Chờ và khớp" (cột J-S)
# Tất cả đều có fallback cứng — file config.ini cũ vẫn chạy được.
# ─────────────────────────────────────────────────────────────────────────────

# % phân bổ qty theo 3 lớp (tổng phải = 100, mặc định 40/40/20)
default_ratio_layer_1 = config.getfloat('global', 'default_ratio_layer_1', fallback=40.0)
default_ratio_layer_2 = config.getfloat('global', 'default_ratio_layer_2', fallback=40.0)
default_ratio_layer_3 = config.getfloat('global', 'default_ratio_layer_3', fallback=20.0)

# % SL (cắt lỗ) cho 3 lớp — tính từ entry price
# LONG: SL_price = entry × (1 - rate/100);  SHORT: SL_price = entry × (1 + rate/100)
default_sl_rate_layer_1 = config.getfloat('global', 'default_sl_rate_layer_1', fallback=2.0)
default_sl_rate_layer_2 = config.getfloat('global', 'default_sl_rate_layer_2', fallback=5.0)
default_sl_rate_layer_3 = config.getfloat('global', 'default_sl_rate_layer_3', fallback=10.0)

# % TP (chốt lời) cho 3 lớp — tính từ entry price
# LONG: TP_price = entry × (1 + rate/100);  SHORT: TP_price = entry × (1 - rate/100)
default_tp_rate_layer_1 = config.getfloat('global', 'default_tp_rate_layer_1', fallback=3.0)
default_tp_rate_layer_2 = config.getfloat('global', 'default_tp_rate_layer_2', fallback=6.0)
default_tp_rate_layer_3 = config.getfloat('global', 'default_tp_rate_layer_3', fallback=10.0)

# Cột S "Cho phép đặt lệnh" — mặc định N (user phải chủ động đổi sang Y)
default_allow_order = config.get('global', 'default_allow_order', fallback='N').strip().upper()
# Bật/tắt tính năng auto-fill default (tắt → cột J-S luôn rỗng như trước)
fill_default_cho_va_khop = config.getboolean('global', 'fill_default_cho_va_khop', fallback=True)

