# -*- coding: utf-8 -*-
"""
config_watcher — theo dõi SHEET TỔNG, xác minh, rồi nạp lại / tắt bot.

KHÔNG CẦN ĐỔI Ô B1
    Bot tự đọc lại cả bảng mỗi `config_reload_seconds` giây và SO NỘI DUNG từng
    dòng tài khoản với cấu hình đang chạy. Máy tự bật Y / sửa key là bot tự theo.

AI ĐỌC SHEET — tiết kiệm hạn mức Google (60 lượt đọc/phút, dùng chung)
    • Chế độ ĐIỀU PHỐI (python hd_xxx.py — cha trông các con): CHỈ tiến trình cha
      đọc bảng. Có thay đổi thì cha GHI LỆNH cho con vào file cục bộ
      pids/<tài khoản>/<bot>.lenh; con chỉ nhìn file đó — không tốn lượt Google.
      6 bot = 6 lượt / chu kỳ, bất kể bao nhiêu tài khoản.
    • Chạy lẻ (có QBOT_ACCOUNT, không có cha): tiến trình tự đọc bảng.

VÌ SAO PHẢI KHỞI ĐỘNG LẠI CHỨ KHÔNG THAY NÓNG
    Mỗi bot dựng `exchange = ccxt.binance({apiKey, secret})` ở CẤP MODULE, chỉ
    tạo một lần. Đổi key giữa chừng thì lệnh đang treo thuộc key CŨ, bot với key
    MỚI không thấy để huỷ → lệnh mồ côi. Khởi động lại thì dựng lại sạch từ đầu.

LÀM LÚC NÀO
    Chỉ lúc bot đang NGHỈ giữa hai vòng (ngu / ngu_theo_nhip) — không bao giờ cắt
    ngang lúc vừa vào lệnh mà chưa kịp đặt cắt lỗ.

XÁC MINH TRƯỚC KHI NẠP — không bao giờ tự sát vào một cấu hình hỏng
    • dòng không đổi                     → chạy tiếp
    • dòng đang chạy bị sửa HỎNG         → GIỮ NGUYÊN cấu hình đang chạy + báo Telegram
    • API key mới                        → THỬ ĐĂNG NHẬP Binance trước; không được → giữ nguyên
    • tài khoản Bật = N / bị xoá         → dừng hẳn tài khoản đó
    • dòng MỚI hợp lệ                    → mở bot cho tài khoản đó
    • dòng MỚI có lỗi                    → bỏ RIÊNG dòng đó + báo, dòng khác vẫn chạy
    • đọc sheet lỗi mạng                 → giữ nguyên, thử lại lần sau

HAI CÁCH NẠP LẠI
    • Có tiến trình điều phối (QBOT_SUPERVISED=1): THOÁT với mã MA_NAP_LAI để cha
      bật lại. Không tự đẻ tiến trình — tự đẻ thì cha mất dấu con.
    • Chạy lẻ: tự mở tiến trình mới rồi thoát. Tiến trình mới ghi đè <bot>.pid.
"""

import os
import subprocess
import sys
import time
from pathlib import Path

MA_NAP_LAI = 75     # con → điều phối: "cấu hình đổi, bật lại tôi"
MA_BI_TAT = 76      # con → điều phối: "tài khoản của tôi đã tắt/xoá trên sheet"
KHOANG_NGU = 5      # chia giấc ngủ thành đoạn ngắn để kịp nhận lệnh
# Chống bật/tắt liên tục: vừa mở tài khoản chưa đủ ngần này giây thì chưa nạp
# lại. Biến môi trường chỉ để diễn tập cho nhanh.
TOI_THIEU_TRUOC_KHI_NAP_LAI = float(os.environ.get('QBOT_MIN_RESTART_GAP', '120'))
# Cha ra lệnh mà con không làm (treo) sau ngần này giây → cha buộc dừng con.
CHO_CON_THUC_HIEN = float(os.environ.get('QBOT_COMMAND_TIMEOUT', '600'))
# Key mới đăng nhập Binance thất bại → ngần này giây sau mới thử lại key đó.
THU_LAI_KEY_HONG = 600

_lan_kiem_cuoi = 0.0       # chạy lẻ: lần đọc bảng gần nhất
_bat_dau = time.time()
_canh_bao_cuoi = {}
_key_hong = {}             # (key, secret) → lúc thử đăng nhập thất bại


def _log(msg):
    print(f"🔄 [CẤU HÌNH] {msg}", flush=True)


def _canh_bao(msg, moi_bao_lau=1800):
    """In ra và gửi Telegram. Cùng nội dung không gửi lại trong `moi_bao_lau` giây."""
    now = time.time()
    if moi_bao_lau and now - _canh_bao_cuoi.get(msg, 0) < moi_bao_lau:
        return          # cùng một dòng lỗi: không in lại mỗi chu kỳ đọc sheet
    _canh_bao_cuoi[msg] = now
    _log(msg)
    try:
        import cst
        # Tiến trình ĐIỀU PHỐI chạy vòng lặp ngay trong lúc import cst, trước khi
        # cst kịp gán bot_token/chat_id… → bù từ config, nếu không cảnh báo của
        # điều phối (dòng bị BỎ QUA, trùng key…) không bao giờ tới Telegram.
        for _ten, _mac_dinh in (('bot_token', ''), ('chat_id', ''), ('prefix_channel', '')):
            if not hasattr(cst, _ten):
                setattr(cst, _ten, cst.config.get('global', _ten, fallback=_mac_dinh))
        if not hasattr(cst, 'account_name'):
            cst.account_name = 'điều phối'
        import telegram_factory
        if getattr(cst, 'chat_id', '') and getattr(cst, 'bot_token', ''):
            telegram_factory.send_tele(f"⚠️ [{cst.account_name}] {msg}", cst.chat_id, False, False)
    except Exception as e:
        _log(f"(không gửi được Telegram: {e})")


def duoc_giam_sat():
    return os.environ.get('QBOT_SUPERVISED', '') == '1'


def _thu_dang_nhap_binance(key, secret):
    """Gọi thử 1 lệnh đọc số dư bằng key MỚI. True = đăng nhập được."""
    try:
        import binance_futures_direct as bfd
        r = bfd.futures_signed_request('GET', '/fapi/v2/balance', api_key=key,
                                       secret_key=secret, max_retries=1, timeout=10)
        return r is not None
    except Exception as e:
        _log(f"thử đăng nhập Binance lỗi: {e}")
        return False


def _loc(d):
    return {k: v for k, v in (d or {}).items() if not str(k).startswith('__')}


def danh_gia(ten, muc_dang_chay, hop_le, bo_qua):
    """
    So dòng của MỘT tài khoản trên bảng mới với cấu hình đang chạy.
    → ('khong_doi' | 'nap_lai' | 'tat' | 'giu_loi', chi_tiết)

    'giu_loi': dòng đang lỗi, hoặc key mới không đăng nhập được → GIỮ cấu hình cũ.
    """
    import sheet_config
    that = sheet_config.tim_tai_khoan(hop_le, ten) if ten else None
    if that is None:
        loi = [ly_do for t, ly_do in bo_qua if str(t).lower() == str(ten).lower()]
        if loi:
            return 'giu_loi', "\n".join(f"  • {x}" for x in loi)
        return 'tat', "tài khoản không còn Bật (hoặc đã xoá) trên sheet tổng"

    muc = hop_le[that]
    if muc_dang_chay is not None and _loc(muc) == _loc(muc_dang_chay):
        return 'khong_doi', ''

    cu = muc_dang_chay or {}
    cap = (muc.get('key_binance', ''), muc.get('secret_binance', ''))
    if cap != (cu.get('key_binance', ''), cu.get('secret_binance', '')):
        if time.time() - _key_hong.get(cap, 0) < THU_LAI_KEY_HONG or not _thu_dang_nhap_binance(*cap):
            _key_hong.setdefault(cap, time.time())
            return 'giu_loi', ("  • API key mới KHÔNG đăng nhập được Binance — dán thiếu, sai "
                               "secret, chưa bật quyền Futures, hoặc chưa thêm IP của VPS.")
        _key_hong.pop(cap, None)
        _canh_bao(f"API key của [{that}] đã đổi. Nếu key mới thuộc TÀI KHOẢN BINANCE "
                  f"KHÁC, vị thế đang mở ở tài khoản cũ sẽ KHÔNG còn được bot quản lý.", 0)
    return 'nap_lai', "cấu hình trên sheet tổng đã đổi"


def ke_hoach_dieu_phoi(dang_chay, hop_le, bo_qua, lan_mo_cuoi=None, da_ra_lenh=None,
                       chet=None, bay_gio=None):
    """
    Việc tiến trình ĐIỀU PHỐI phải làm sau khi đọc bảng mới — hàm không tự làm gì.

    dang_chay   : {tài khoản: cấu hình đang chạy} — chỉ con CÒN SỐNG
    lan_mo_cuoi : {tài khoản: lúc mở gần nhất}   — chống bật/tắt liên tục
    da_ra_lenh  : {tài khoản: …}                 — đã ra lệnh, đang chờ con làm
    chet        : {tài khoản: cấu hình lúc chết} — con chết vì lỗi: KHÔNG mở lại
                                                   trừ khi dòng trên sheet đổi
    → [('mo', tk) | ('nap_lai', tk, lý do) | ('tat', tk, lý do) | ('canh_bao', nội dung)]
    """
    import sheet_config
    bay_gio = time.time() if bay_gio is None else bay_gio
    lan_mo_cuoi, da_ra_lenh, chet = lan_mo_cuoi or {}, da_ra_lenh or {}, chet or {}
    viec = []

    for tk, muc in dang_chay.items():
        if tk in da_ra_lenh:
            continue
        kq, ct = danh_gia(tk, muc, hop_le, bo_qua)
        if kq == 'khong_doi':
            continue
        if kq == 'giu_loi':
            viec.append(('canh_bao', f"[{tk}] dòng trên sheet tổng đang LỖI — GIỮ NGUYÊN cấu hình "
                                     f"đang chạy, không nạp:\n{ct}\n→ Sửa dòng đó trên sheet, bot tự nhận."))
            continue
        if bay_gio - lan_mo_cuoi.get(tk, 0) < TOI_THIEU_TRUOC_KHI_NAP_LAI:
            continue            # vừa mở — chờ đủ khoảng cách, lần đọc sau làm
        viec.append((kq, tk, ct))

    for tk, muc in hop_le.items():
        if sheet_config.tim_tai_khoan(dang_chay, tk) is not None:
            continue
        c = sheet_config.tim_tai_khoan(chet, tk)
        if c is not None and _loc(chet[c]) == _loc(muc):
            continue            # chết vì lỗi mà dòng chưa sửa → không mở lại liên tục
        viec.append(('mo', tk))

    for tk, ly_do in bo_qua:
        if sheet_config.tim_tai_khoan(dang_chay, tk) is None:
            viec.append(('canh_bao', f"[{tk}] bị BỎ QUA, không chạy: {ly_do}"))
    return viec


# ── Kênh lệnh cha → con (file cục bộ, không tốn lượt Google) ─────────────────

def duong_dan_lenh(bot, tai_khoan):
    return Path('pids') / tai_khoan / f'{bot}.lenh'


def gui_lenh(bot, tai_khoan, lenh, ly_do=''):
    """Cha → con: 'nap_lai' hoặc 'tat'. Con làm lúc đang nghỉ giữa hai vòng."""
    p = duong_dan_lenh(bot, tai_khoan)
    p.parent.mkdir(parents=True, exist_ok=True)
    tam = p.with_name(p.name + '.tmp')
    tam.write_text(f"{lenh}\n{ly_do}", encoding='utf-8')
    os.replace(tam, p)          # ghi nguyên khối — con không đọc phải lệnh dở


def xoa_lenh(bot, tai_khoan):
    try:
        duong_dan_lenh(bot, tai_khoan).unlink()
    except OSError:
        pass


def _nhan_lenh():
    """Con: đọc + xoá lệnh cha gửi → (lệnh, lý do) hoặc (None, '')."""
    try:
        import cst
        bot = os.path.basename(sys.argv[0] or '')[:-3]
        p = cst.account_dir('pids') / f'{bot}.lenh'
        if not p.exists():
            return None, ''
        phan = p.read_text(encoding='utf-8').split('\n', 1)
        p.unlink()
        return phan[0].strip(), (phan[1] if len(phan) > 1 else '')
    except Exception as e:
        _log(f"không đọc được lệnh của điều phối: {e}")
        return None, ''


def kiem_tra_va_ap_dung():
    """Nhận lệnh (có cha) / tự dò (chạy lẻ) + xác minh + nạp lại. Gọi lúc NGHỈ."""
    global _lan_kiem_cuoi
    try:
        import cst
    except Exception:
        return
    if not getattr(cst, 'nap_tu_sheet', False):
        return

    if duoc_giam_sat():
        lenh, ly_do = _nhan_lenh()
        if lenh == 'tat':
            dung_vi_bi_tat(nha_khoa=cst.nha_khoa, ly_do=ly_do)
        elif lenh == 'nap_lai':
            khoi_dong_lai(ly_do or "cấu hình trên sheet tổng đã đổi", nha_khoa=cst.nha_khoa)
        return

    # Chạy lẻ — không có cha → tự đọc bảng
    chu_ky = cst.config.getint('global', 'config_reload_seconds', fallback=60)
    now = time.time()
    if now - _lan_kiem_cuoi < chu_ky:
        return
    _lan_kiem_cuoi = now
    import sheet_config
    try:
        _pb, hop_le, bo_qua = sheet_config.nap(cst.bot_id, cst.config_spreadsheet_id)
    except sheet_config.LoiDocSheet as e:
        _log(f"chưa đọc được sheet tổng ({e}) — giữ cấu hình hiện tại, thử lại sau")
        return
    except sheet_config.LoiSheetCauHinh as e:
        _canh_bao(f"Sheet tổng đang LỖI — GIỮ NGUYÊN cấu hình đang chạy:\n{e}")
        return

    bang_cu = getattr(cst, '_bang_tk', None) or {}
    t = sheet_config.tim_tai_khoan(bang_cu, cst.account) if bang_cu else None
    kq, ct = danh_gia(cst.account, bang_cu.get(t) if t else None, hop_le, bo_qua)
    if kq == 'khong_doi':
        return
    if kq == 'giu_loi':
        _canh_bao(f"Dòng [{cst.account}] trên sheet tổng đang LỖI — GIỮ NGUYÊN cấu hình "
                  f"đang chạy, không nạp:\n{ct}")
        return
    if now - _bat_dau < TOI_THIEU_TRUOC_KHI_NAP_LAI:
        _log(f"cấu hình đổi ngay sau khi vừa khởi động — chờ đủ "
             f"{TOI_THIEU_TRUOC_KHI_NAP_LAI:g}s rồi mới nạp (chống bật/tắt liên tục)")
        return
    if kq == 'tat':
        dung_vi_bi_tat(nha_khoa=cst.nha_khoa, ly_do=ct)
    khoi_dong_lai(ct, nha_khoa=cst.nha_khoa)


def ngu(giay):
    """Thay cho time.sleep ở cuối vòng lặp mỗi bot: vừa nghỉ vừa dò cấu hình."""
    het = time.time() + max(0.0, float(giay))
    while True:
        con = het - time.time()
        if con <= 0:
            break
        time.sleep(min(KHOANG_NGU, con))
        try:
            kiem_tra_va_ap_dung()
        except SystemExit:
            raise
        except Exception as e:
            _log(f"dò cấu hình lỗi (bỏ qua): {e}")


def bat_dau_vong():
    """Mốc thời gian ĐẦU vòng — truyền cho ngu_theo_nhip."""
    return time.time()


def ngu_theo_nhip(bat_dau, nhip, ten=''):
    """
    Nghỉ sao cho MỖI VÒNG cách nhau đúng `nhip` giây, tính từ lúc BẮT ĐẦU vòng.

    ngu(nhip) là "làm xong rồi nghỉ đủ nhịp" → chu kỳ thật = thời gian làm + nhịp
    (quét 20s, nhịp 60s → 80s/vòng). Ở đây trừ đi thời gian đã làm nên bot chạy
    ĐÚNG nhịp khai trong config. Vòng nào lâu hơn nhịp thì báo rõ và chạy tiếp
    ngay, không dồn nợ thời gian.
    """
    nhip = max(0.0, float(nhip))
    lam = max(0.0, time.time() - float(bat_dau))
    con = nhip - lam
    nhan = f" ({ten})" if ten else ""
    if con <= 0:
        print(f"⚠️  Vòng vừa rồi mất {lam:.1f}s — DÀI HƠN nhịp {nhip:g}s{nhan} → chạy tiếp ngay. "
              f"Nới nhịp lên, hoặc bớt số mã.", flush=True)
        _log(f"vòng {lam:.1f}s > nhịp {nhip:g}s{nhan}")
        try:
            kiem_tra_va_ap_dung()      # không nghỉ thì vẫn phải dò cấu hình
        except SystemExit:
            raise
        except Exception as e:
            _log(f"dò cấu hình lỗi (bỏ qua): {e}")
        return
    print(f"⏳ Vòng {lam:.1f}s — nghỉ {con:.0f}s (nhịp {nhip:g}s{nhan})", flush=True)
    ngu(con)


def dung_vi_bi_tat(nha_khoa=None, ly_do=''):
    """Tài khoản không còn Bật trên sheet → dừng hẳn, điều phối KHÔNG bật lại."""
    _canh_bao("Tài khoản đã bị TẮT hoặc XOÁ khỏi sheet tổng → bot dừng cho tài khoản này."
              + (f" ({ly_do})" if ly_do else ""), 0)
    if nha_khoa:
        try:
            nha_khoa()
        except Exception:
            pass
    raise SystemExit(MA_BI_TAT if duoc_giam_sat() else 0)


def khoi_dong_lai(ly_do="cấu hình trên sheet đã đổi", nha_khoa=None):
    """
    Nạp lại bot. THỨ TỰ BẮT BUỘC — sai là hai bot cùng chạy → ĐẶT LỆNH TRÙNG:
        1. Nhả khoá chống chạy trùng
        2. (có điều phối) thoát mã MA_NAP_LAI  |  (chạy lẻ) mở tiến trình mới
        3. Thoát tiến trình cũ
    """
    _log(f"{ly_do} → khởi động lại để nạp cấu hình mới")

    if nha_khoa:
        try:
            nha_khoa()
            _log("đã nhả khoá chống chạy trùng")
        except Exception as e:
            _log(f"⚠️ không nhả được khoá: {e} — DỪNG, không mở tiến trình mới "
                 f"để tránh hai bot cùng chạy")
            raise SystemExit(1)

    if duoc_giam_sat():
        _log(f"báo tiến trình điều phối bật lại (mã thoát {MA_NAP_LAI})")
        raise SystemExit(MA_NAP_LAI)

    try:
        env = dict(os.environ, QBOT_RESTART_DELAY='3')
        subprocess.Popen([sys.executable] + sys.argv, env=env, start_new_session=True)
        try:
            import giu_cua_so          # tiến trình cũ thoát CỐ Ý → đừng chờ Enter
            giu_cua_so.khong_giu()
        except ImportError:
            pass
        _log(f"đã mở tiến trình mới: {' '.join([os.path.basename(sys.executable)] + sys.argv)}")
    except Exception as e:
        _log(f"❌ KHÔNG mở được tiến trình mới: {e}")
        _log("   Bot cũ vẫn chạy tiếp bằng cấu hình cũ để không mất giám sát.")
        return False

    _log("tiến trình cũ thoát")
    raise SystemExit(0)


def cho_neu_vua_khoi_dong_lai():
    """Tiến trình vừa được tự sinh ra chờ vài giây cho tiến trình cũ thoát hẳn."""
    delay = os.environ.get('QBOT_RESTART_DELAY', '')
    if not delay:
        return
    try:
        giay = float(delay)
    except ValueError:
        return
    if giay > 0:
        _log(f"vừa được khởi động lại — chờ {giay:g}s cho tiến trình cũ thoát hẳn")
        time.sleep(giay)
    os.environ.pop('QBOT_RESTART_DELAY', None)
