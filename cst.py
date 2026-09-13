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


# ══════════════════════════════════════════════════════════════════════════════
# NẠP CẤU HÌNH TỪ SHEET TỔNG (nếu có khai)
#
#   [global]
#   bot_id = QBOT01
#   config_spreadsheet_id = 1AbC...XyZ
#
# Khai đủ hai dòng trên thì danh sách tài khoản, API key và cấu hình từng tài
# khoản lấy từ Google Sheet — khách đổi key không phải mở file trên VPS.
# KHÔNG khai thì chạy y như cũ, đọc hết từ config.ini.
#
# Cách nối: mỗi dòng trên sheet được dựng thành một section trong bộ nhớ, y
# như khai tay trong config.ini. Nhờ vậy toàn bộ phần phía dưới (khớp tên, ghi
# đè lên [global], mở tiến trình con cho từng tài khoản) chạy nguyên, không
# phải sửa dòng nào.
# ══════════════════════════════════════════════════════════════════════════════
bot_id = config.get('global', 'bot_id', fallback='').strip()
config_spreadsheet_id = config.get('global', 'config_spreadsheet_id', fallback='').strip()
config_sheet_version = ''          # ô B1 — chỉ để hiển thị, KHÔNG dùng để dò thay đổi
bo_qua_sheet = []                  # [(tài khoản, lý do)] dòng Bật nhưng có lỗi → không chạy
nap_tu_sheet = bool(config_spreadsheet_id)

if nap_tu_sheet:
    if not bot_id:
        raise SystemExit(
            f"❌ Có khai config_spreadsheet_id nhưng THIẾU bot_id trong {config_file}.\n"
            f"   bot_id là tên TAB trên sheet tổng chứa cấu hình của máy này.")

    import sheet_config
    try:
        config_sheet_version, _bang_tk, bo_qua_sheet = sheet_config.nap(bot_id, config_spreadsheet_id)
    except sheet_config.LoiSheetCauHinh as _e:
        # Theo quyết định của khách: đọc sheet lỗi thì DỪNG HẲN, không dùng
        # giá trị dự phòng — thà không chạy còn hơn chạy bằng cấu hình cũ mà
        # tưởng là đã đổi.
        raise SystemExit(
            f"❌ Không nạp được cấu hình từ sheet tổng (tab '{bot_id}').\n"
            f"   {_e}\n"
            f"   Sheet: {config_spreadsheet_id}\n"
            f"   Bot DỪNG — không chạy bằng cấu hình cũ để tránh dùng nhầm key."
        )

    for _ten, _muc in _bang_tk.items():
        if not config.has_section(_ten):
            config.add_section(_ten)
        for _k, _v in _muc.items():
            if _k.startswith('__'):
                continue          # __ten__, __bat__ là cột điều khiển
            # '%' phải nhân đôi, nếu không configparser hiểu là chuỗi thay thế
            config.set(_ten, _k, str(_v).replace('%', '%%'))
    config.set('global', 'accounts', ', '.join(_bang_tk.keys()))
    print(f"📄 [CẤU HÌNH] Nạp từ sheet tổng — tab '{bot_id}', {len(_bang_tk)} tài khoản "
          f"hợp lệ đang Bật: {', '.join(_bang_tk.keys()) or '(chưa có)'}", flush=True)
    # Dòng lỗi chỉ bị BỎ RIÊNG — các dòng đúng vẫn chạy (máy tự bật Y, một dòng
    # sai không được làm đứng cả hệ). Tiến trình con không in lại cho đỡ rối.
    if bo_qua_sheet and os.environ.get('QBOT_SUPERVISED', '') != '1':
        print(f"⚠️ [CẤU HÌNH] {len(bo_qua_sheet)} dòng bị BỎ QUA, không chạy "
              f"(các dòng khác vẫn chạy):\n{sheet_config.mo_ta_bo_qua(bo_qua_sheet)}", flush=True)


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
_la_file_bot = (os.path.basename(_sys_argv0).startswith('hd_')
                and os.path.basename(_sys_argv0).endswith('.py'))


def _run_for_all_accounts(entry_file):
    """
    Mở một tiến trình con cho MỖI tài khoản (chạy lại chính file bot này),
    chuyển tiếp màn hình có gắn tên tài khoản, và dừng sạch khi Ctrl+C.

    Chế độ sheet tổng: CHỈ tiến trình này đọc bảng, mỗi `config_reload_seconds` —
    so nội dung từng dòng (KHÔNG cần đổi ô B1), tự mở tài khoản mới Bật, ra lệnh
    nạp lại / tắt cho con qua file pids/<tk>/<bot>.lenh. Hết tài khoản Bật thì
    KHÔNG thoát — ngồi chờ tài khoản được Bật lại.
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
    print(f"  {bot} — chạy cho {len(accounts)} tài khoản: {', '.join(accounts) or '(chưa có)'}", flush=True)
    if nap_tu_sheet:
        print(f"  Tự đọc lại sheet tổng mỗi config_reload_seconds — KHÔNG cần đổi ô B1", flush=True)
    print(f"  (Ctrl+C để dừng tất cả)", flush=True)
    print("=" * 62, flush=True)

    # Giãn giờ khởi động: các tài khoản lệch pha nhau nên không cùng gọi
    # Google Sheets / Binance trong một khoảnh khắc → tránh lỗi 429.
    try:
        stagger = config.getfloat('global', 'account_start_stagger_sec', fallback=20.0)
    except Exception:
        stagger = 20.0
    if stagger < 0:
        stagger = 0.0

    import config_watcher as _cw
    from config_watcher import MA_NAP_LAI, MA_BI_TAT

    procs = {}          # tk → Popen (chỉ con CÒN SỐNG)
    muc_chay = {}       # tk → dòng sheet con đang chạy (lúc mở)
    lan_mo = {}         # tk → lúc mở gần nhất
    da_ra_lenh = {}     # tk → (lệnh, lúc gửi) — chờ con thực hiện
    chet = {}           # tk → dòng sheet lúc con chết vì lỗi (không tự mở lại)
    bang = dict(_bang_tk) if nap_tu_sheet else {}

    def _relay(acc, proc):
        """In màn hình của tiến trình con, gắn tên tài khoản cho dễ theo dõi."""
        try:
            for line in proc.stdout:
                print(f"[{acc}] {line.rstrip()}", flush=True)
        except Exception:
            pass

    def _mo(acc):
        # Lệnh cũ còn sót trong file không được áp cho tiến trình con MỚI
        _cw.xoa_lenh(bot, acc)
        # QBOT_SUPERVISED=1 báo cho con biết có điều phối trông: con KHÔNG tự đọc
        # sheet, chỉ nhận lệnh; cần nạp lại thì THOÁT mã MA_NAP_LAI để cha bật lại.
        env = dict(os.environ, QBOT_ACCOUNT=acc, QBOT_CONFIG=config_file, QBOT_SUPERVISED='1')
        try:
            p = subprocess.Popen(
                [_sys_mod.executable, entry_file],
                env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                # encoding='utf-8' BẮT BUỘC: không có thì trên Windows cha giải mã
                # bằng cp1252 → chữ Việt và emoji thành mojibake.
                text=True, encoding='utf-8', errors='replace', bufsize=1,
            )
        except Exception as e:
            print(f"  ❌ Không mở được tiến trình cho [{acc}]: {e}", flush=True)
            return False
        procs[acc] = p
        muc_chay[acc] = dict(bang.get(acc) or {})
        lan_mo[acc] = time.time()
        chet.pop(acc, None)
        threading.Thread(target=_relay, args=(acc, p), daemon=True).start()
        print(f"  ▶ [{acc}] đã khởi động (PID {p.pid})", flush=True)
        return True

    for i, acc in enumerate(accounts):
        if i > 0 and stagger > 0:
            print(f"  ⏳ Chờ {stagger:.0f}s trước khi khởi động [{acc}] (tránh rate limit)...", flush=True)
            time.sleep(stagger)
        _mo(acc)
    for tk, ly_do in bo_qua_sheet:
        _cw._canh_bao(f"[{tk}] bị BỎ QUA, không chạy: {ly_do}")

    if not procs and not nap_tu_sheet:
        raise SystemExit("❌ Không khởi động được tài khoản nào.")

    # SIGTERM (lệnh `kill`, chính là cái stop_all_bots dùng) mặc định giết tiến
    # trình NGAY, không chạy khối finally → các con bị bỏ lại chạy mồ côi (đã tái
    # hiện). Đổi SIGTERM thành KeyboardInterrupt để dọn con giống như Ctrl+C.
    import signal as _signal
    def _nhan_sigterm(signum, frame):
        raise KeyboardInterrupt
    try:
        _signal.signal(_signal.SIGTERM, _nhan_sigterm)
    except Exception:
        pass

    try:
        _chu_ky = config.getint('global', 'config_reload_seconds', fallback=60)
    except Exception:
        _chu_ky = 60
    lan_doc = time.time()
    doc_ngay = False
    da_bao_trong = False

    try:
        while True:
            time.sleep(2)

            # 1) Con nào đã thoát, vì sao
            for acc, p in list(procs.items()):
                rc = p.poll()
                if rc is None:
                    lenh = da_ra_lenh.get(acc)
                    if lenh and time.time() - lenh[1] > _cw.CHO_CON_THUC_HIEN:
                        print(f"  ⚠️ [{acc}] không thực hiện lệnh '{lenh[0]}' sau "
                              f"{_cw.CHO_CON_THUC_HIEN:g}s — buộc dừng", flush=True)
                        try:
                            p.terminate()
                        except Exception:
                            pass
                    continue
                procs.pop(acc, None)
                lenh = da_ra_lenh.pop(acc, None)
                muc = muc_chay.pop(acc, {})
                if rc == MA_NAP_LAI:
                    print(f"  🔄 [{acc}] nạp lại cấu hình từ sheet tổng", flush=True)
                    doc_ngay = True
                elif rc == MA_BI_TAT:
                    print(f"  ⏹ [{acc}] đã TẮT/XOÁ trên sheet — không bật lại", flush=True)
                elif lenh:
                    doc_ngay = True         # cha buộc dừng sau khi ra lệnh
                else:
                    # Chết vì lỗi khác: KHÔNG tự bật lại — chỉ mở lại khi dòng của
                    # nó trên sheet đổi (người dùng đã sửa gì đó).
                    chet[acc] = muc
                    print(f"  ⚠️ [{acc}] đã dừng (mã thoát {rc})", flush=True)

            # 2) Đọc lại bảng → so nội dung → làm theo kế hoạch
            if nap_tu_sheet and (doc_ngay or time.time() - lan_doc >= _chu_ky):
                doc_ngay = False
                lan_doc = time.time()
                bang_moi = None
                try:
                    import sheet_config as _sc
                    _pb, bang_moi, bo_qua_moi = _sc.nap(bot_id, config_spreadsheet_id)
                except Exception as e:
                    if type(e).__name__ == 'LoiDocSheet':
                        print(f"  ⚠️ Chưa đọc được sheet tổng ({e}) — giữ nguyên, thử lại sau", flush=True)
                    else:
                        _cw._canh_bao(f"Sheet tổng đang LỖI — giữ nguyên mọi tài khoản đang chạy:\n{e}")
                if bang_moi is not None:
                    bang = bang_moi
                    for viec in _cw.ke_hoach_dieu_phoi(muc_chay, bang, bo_qua_moi,
                                                        lan_mo, da_ra_lenh, chet):
                        if viec[0] == 'mo':
                            tk = viec[1]
                            if tk in lan_mo:
                                print(f"  🔁 [{tk}] mở lại với cấu hình mới trên sheet tổng", flush=True)
                            else:
                                print(f"  ➕ [{tk}] tài khoản MỚI trên sheet tổng — khởi động", flush=True)
                            _mo(tk)
                        elif viec[0] in ('nap_lai', 'tat'):
                            _, tk, ly_do = viec
                            _cw.gui_lenh(bot, tk, viec[0], ly_do)
                            da_ra_lenh[tk] = (viec[0], time.time())
                            nhan = 'NẠP LẠI' if viec[0] == 'nap_lai' else 'TẮT'
                            print(f"  📨 [{tk}] ra lệnh {nhan}: {ly_do}", flush=True)
                        elif viec[0] == 'canh_bao':
                            _cw._canh_bao(viec[1])

            # 3) Hết con
            if not procs:
                if not nap_tu_sheet:
                    print("  ℹ️ Tất cả tài khoản đã dừng.", flush=True)
                    break
                if not da_bao_trong:
                    print("  ℹ️ Không còn tài khoản nào chạy — chờ tài khoản được Bật trên sheet tổng.",
                          flush=True)
                    da_bao_trong = True
            else:
                da_bao_trong = False
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
# kiem_tra_cau_hinh đặt cờ này: xem MỌI tài khoản mà không chạy tài khoản nào
CHE_DO_SOAT = os.environ.get('QBOT_CHE_DO_SOAT', '').strip() == '1'

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

    # Danh sách khoá hạn chế này sinh ra để chặn việc khai tham số vận hành
    # lung tung trong config.ini. Khi cấu hình đến TỪ SHEET TỔNG thì chính
    # sheet là nơi khai có chủ đích (mỗi tài khoản một lớp, %SL/%TP riêng),
    # nên bỏ qua hạn chế — nếu không sẽ chặn đúng thứ đang cần.
    # Ba khoá bắt buộc key/secret/sheet VẪN được kiểm ở trên, không nới.
    if nap_tu_sheet:
        _allowed = _allowed | set(config[account].keys())

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
elif accounts or (nap_tu_sheet and _la_file_bot and not CHE_DO_SOAT):
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
    elif CHE_DO_SOAT:
        pass    # kiem_tra_cau_hinh: xem MỌI tài khoản, không chạy tài khoản nào
    else:
        _nguon = (f"Sheet tổng (tab '{bot_id}')" if nap_tu_sheet else config_file)
        raise SystemExit(
            f"❌ Chưa chọn tài khoản.\n"
            f"   {_nguon} đang có {len(accounts)} tài khoản: {', '.join(accounts)}\n"
            f"   Bật bot bằng file hd_*.py (tự chạy cho mọi tài khoản đang Bật),\n"
            f"   hoặc đặt QBOT_ACCOUNT=<tên> để chạy riêng 1 tài khoản."
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
    """
    PID còn sống không.

    ⚠️ Trên Windows KHÔNG được dùng os.kill(pid, 0): Python gọi TerminateProcess
    với mọi signal khác CTRL_C/CTRL_BREAK → GIẾT LUÔN tiến trình đang hỏi thăm.
    Bật trùng một bot sẽ giết bot đang chạy, hoặc giết nhầm chương trình khác
    được Windows cấp lại PID cũ.
    """
    if os.name == 'nt':
        import ctypes
        k32 = ctypes.WinDLL('kernel32', use_last_error=True)
        h = k32.OpenProcess(0x1000, False, int(pid))    # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return ctypes.get_last_error() == 5          # ACCESS_DENIED → vẫn đang tồn tại
        try:
            code = ctypes.c_ulong()
            if not k32.GetExitCodeProcess(h, ctypes.byref(code)):
                return False
            return code.value == 259                     # STILL_ACTIVE
        finally:
            k32.CloseHandle(h)
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
                f"   Muốn chạy lại: đóng cửa sổ bot đó (Windows) / kill {old_pid} (Linux) rồi thử lại\n"
                f"   (hoặc QBOT_NO_LOCK=1 để bỏ qua khoá — chỉ khi chắc chắn)\n"
            )
        # PID cũ đã chết → khoá mồ côi, ghi đè được

    try:
        lock_file.write_text(str(os.getpid()))
    except OSError as e:
        print(f"⚠️ Không ghi được khoá {lock_file}: {e} — vẫn chạy tiếp", flush=True)
        return None

    # Ghi luôn <bot>.pid = PID THẬT. start_all_bots / stop_all_bots / status theo
    # dõi bằng file .pid. Bot tự khởi động lại (đổi cấu hình trên sheet) thì PID
    # đổi — không ghi đè ở đây thì stop_all_bots giết nhầm PID cũ đã chết và KHÔNG
    # dừng được bot đang chạy thật (đã tái hiện được lỗi này).
    try:
        (lock_dir / f'{bot_name}.pid').write_text(str(os.getpid()))
    except OSError:
        pass

    def _release():
        try:
            if lock_file.exists() and lock_file.read_text().strip() == str(os.getpid()):
                lock_file.unlink()
        except OSError:
            pass
    atexit.register(_release)
    # Giữ lại để khởi động lại chủ động có thể NHẢ KHOÁ TRƯỚC khi mở tiến
    # trình mới — sai thứ tự là hai bot cùng chạy → đặt lệnh trùng.
    global nha_khoa
    nha_khoa = _release
    return lock_file


def nha_khoa():
    """Nhả khoá chống chạy trùng. Được gán lại khi thực sự giành được khoá."""
    pass


# Tự động khoá khi chạy trực tiếp một bot (file hd_*.py) — không cần sửa bot nào.
# Test / script phụ / import gián tiếp KHÔNG bị ảnh hưởng.
try:
    _entry = os.path.basename(_sys.argv[0] or '')
    if _entry.startswith('hd_') and _entry.endswith('.py'):
        # Nếu tiến trình này vừa được sinh ra do đổi cấu hình, chờ tiến trình
        # cũ thoát hẳn rồi mới giành khoá.
        try:
            import config_watcher as _cw
            _cw.cho_neu_vua_khoi_dong_lai()
        except Exception as _e:
            print(f"⚠️ config_watcher: {_e}", flush=True)
        acquire_single_instance_lock(_entry[:-3])
except SystemExit:
    raise
except Exception as _e:
    print(f"⚠️ Bỏ qua khoá chống chạy trùng: {_e}", flush=True)


def account_suffix() -> str:
    """Hậu tố gắn vào tên file riêng theo tài khoản ('' nếu chế độ 1 tài khoản)."""
    return f"_{account}" if account else ""

# Telegram: khai chung ở [global] làm mặc định; sheet tổng ghi đè được theo tài khoản
bot_token = config.get('global', 'bot_token', fallback='')
chat_id = config.get('global', 'chat_id', fallback='')
prefix_channel = config.get('global', 'prefix_channel', fallback='')

# Thông tin TÀI KHOẢN — lấy từ sheet tổng (hoặc [global] nếu không dùng sheet)
key_name = config.get('global', 'key_name', fallback='') or account_name
key_binance = config.get('global', 'key_binance', fallback='').strip()
secret_binance = config.get('global', 'secret_binance', fallback='').strip()
spreadsheet_id = config.get('global', 'spreadsheet_id', fallback='').strip()
# Chế độ soát có nhiều tài khoản: chưa chọn tài khoản nào nên [global] không có
# key — kiem_tra_cau_hinh tự soát key của TỪNG tài khoản.
if not (key_binance and secret_binance and spreadsheet_id) and not (CHE_DO_SOAT and (accounts or nap_tu_sheet)):
    raise SystemExit(
        f"❌ Chưa có API key / Google Sheet cho tài khoản '{account_name}'.\n"
        f"   qbot_new lấy thông tin tài khoản từ SHEET TỔNG — khai trong {config_file}:\n"
        f"       bot_id = <tên tab trên sheet tổng>\n"
        f"       config_spreadsheet_id = <ID sheet tổng>\n"
        f"   (Xem HUONG_DAN_SHEET_TONG.md)")
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
delay_cho_va_khop = _get_time_setting('delay_cho_va_khop', minimum=1, warn_below=30)
delay_update_all = _get_time_setting('delay_update_all', minimum=1, warn_below=15)
delay_calert_possition_and_open_order = _get_time_setting('delay_calert_possition_and_open_order', minimum=1, warn_below=15)

# Bot huỷ lệnh treo: khai bằng GIÂY (cancel_orders_seconds) hoặc PHÚT
# (cancel_orders_minutes — cách cũ). Rất dễ nhầm: điền 60 vào dòng PHÚT với ý
# "60 giây" thì bot 1 TIẾNG mới quét 1 lần. Khai cả hai thì GIÂY thắng.
if config.get('global', 'cancel_orders_seconds', fallback='').strip():
    cancel_orders_seconds = _get_time_setting('cancel_orders_seconds', minimum=5,
                                              warn_below=30)
    cancel_orders_minutes = cancel_orders_seconds / 60.0
else:
    cancel_orders_minutes = _get_time_setting('cancel_orders_minutes', minimum=1, unit='phút')
    cancel_orders_seconds = cancel_orders_minutes * 60


def bao_nhip(ten_tham_so, giay):
    """In rõ nhịp chạy + FILE CONFIG đang dùng.

    Hay gặp: sửa config.ini mà bot "không nhận" — vì sửa nhầm thư mục khác, hoặc
    vì bot đang chạy (config.ini chỉ đọc lúc khởi động).
    """
    print(f"⏱️  Nhịp chạy: {giay:g} giây  ({ten_tham_so})", flush=True)
    print(f"   Config đang dùng: {os.path.abspath(config_file)}", flush=True)
    print(f"   Sửa config.ini xong phải TẮT rồi BẬT LẠI bot mới có tác dụng.", flush=True)

# Telegram command bot: True = folder này chạy listener (nhận lệnh); False = chỉ chạy hd_order, không nhận lệnh
# Mặc định False: nếu config.ini chưa có run_tele_command thì không chạy (tránh bật nhầm)
run_tele_command = config.getboolean('global', 'run_tele_command', fallback=False)


# ─────────────────────────────────────────────────────────────────────────────
# [TASK 1] Default values cho sheet "Chờ và khớp" (cột J-S)
# Tất cả đều có fallback cứng — file config.ini cũ vẫn chạy được.
# ─────────────────────────────────────────────────────────────────────────────

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

