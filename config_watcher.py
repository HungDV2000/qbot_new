# -*- coding: utf-8 -*-
"""
config_watcher — dò cấu hình trên sheet tổng đổi, xác minh, rồi nạp lại bot.

VÌ SAO PHẢI KHỞI ĐỘNG LẠI CHỨ KHÔNG THAY NÓNG
    Mỗi bot dựng `exchange = ccxt.binance({apiKey, secret})` ở CẤP MODULE, chỉ
    tạo một lần. Đổi key giữa chừng thì lệnh đang treo thuộc key CŨ, bot với key
    MỚI không thấy để huỷ → lệnh mồ côi. Khởi động lại thì dựng lại sạch từ đầu.

DÒ LÚC NÀO
    `ngu(giay)` thay cho `time.sleep` ở cuối vòng lặp của MỌI bot: vừa nghỉ vừa
    dò. Tức là chỉ nạp lại khi bot đang NGHỈ giữa hai vòng — không bao giờ cắt
    ngang lúc vừa vào lệnh mà chưa kịp đặt cắt lỗ.
    Chỉ đọc MỘT ô B1 mỗi `config_reload_seconds` (mặc định 300s) nên rất rẻ.

XÁC MINH TRƯỚC KHI NẠP — không bao giờ tự sát vào một cấu hình hỏng
    Thấy B1 đổi, bot đang chạy đọc trọn cấu hình mới và soát trước:
      • đọc sheet lỗi mạng       → giữ nguyên, thử lại lần dò sau
      • dữ liệu sai (sửa dở…)    → giữ nguyên cấu hình đang chạy + báo Telegram
      • API key mới              → THỬ ĐĂNG NHẬP Binance trước; không được → giữ nguyên
      • tài khoản bị tắt / xoá   → dừng hẳn tài khoản này
      • mọi thứ ổn               → nạp lại
    Nếu cứ thoát rồi để bản mới tự đọc sheet: gặp dữ liệu sửa dở là bản mới chết
    ngay lúc khởi động, không còn ai giám sát vị thế đang mở.

HAI CÁCH NẠP LẠI
    • Có tiến trình điều phối trông (QBOT_SUPERVISED=1): THOÁT với mã MA_NAP_LAI,
      để điều phối bật lại. Không tự đẻ tiến trình — tự đẻ thì điều phối mất dấu
      con, và khi điều phối thoát, đường ống màn hình đứt làm con mới chết theo.
    • Chạy lẻ (start_all_bots theo tài khoản, hoặc chạy tay có QBOT_ACCOUNT):
      tự mở tiến trình mới rồi thoát. Tiến trình mới ghi đè <bot>.pid.
"""

import os
import subprocess
import sys
import time

MA_NAP_LAI = 75     # con → điều phối: "cấu hình đổi, bật lại tôi"
MA_BI_TAT = 76      # con → điều phối: "tài khoản của tôi đã tắt/xoá trên sheet"
KHOANG_NGU = 5      # chia giấc ngủ thành đoạn ngắn để kịp dò
# Chống bão khởi động lại (B1 là công thức NOW()…): vừa khởi động chưa đủ
# ngần này giây thì chưa nạp lại. Biến môi trường chỉ để diễn tập cho nhanh.
TOI_THIEU_TRUOC_KHI_NAP_LAI = float(os.environ.get('QBOT_MIN_RESTART_GAP', '120'))

_lan_kiem_cuoi = 0.0
_phien_ban_dau = None
_phien_ban_loi = None      # phiên bản đã biết là dữ liệu hỏng — chờ B1 đổi tiếp
_bat_dau = time.time()
_canh_bao_cuoi = {}


def _log(msg):
    print(f"🔄 [CẤU HÌNH] {msg}", flush=True)


def _canh_bao(msg, moi_bao_lau=1800):
    """In ra và gửi Telegram. Cùng nội dung không gửi lại trong `moi_bao_lau` giây."""
    _log(msg)
    now = time.time()
    if moi_bao_lau and now - _canh_bao_cuoi.get(msg, 0) < moi_bao_lau:
        return
    _canh_bao_cuoi[msg] = now
    try:
        import cst
        import telegram_factory
        if getattr(cst, 'chat_id', '') and getattr(cst, 'bot_token', ''):
            telegram_factory.send_tele(f"⚠️ [{cst.account_name}] {msg}", cst.chat_id, False, False)
    except Exception as e:
        _log(f"(không gửi được Telegram: {e})")


def duoc_giam_sat():
    return os.environ.get('QBOT_SUPERVISED', '') == '1'


def khoi_tao(phien_ban_hien_tai):
    """Ghi nhớ phiên bản lúc bot khởi động, để sau này so sánh."""
    global _phien_ban_dau, _lan_kiem_cuoi, _phien_ban_loi
    _phien_ban_dau = phien_ban_hien_tai
    _phien_ban_loi = None
    _lan_kiem_cuoi = time.time()


def co_thay_doi(bot_id, spreadsheet_id, chu_ky_giay=300):
    """
    Đọc ô phiên bản (nếu đã tới hạn) và cho biết có đổi không → (đã_đổi, mới).

    Chưa tới hạn → (False, None), không gọi mạng. Đọc lỗi → (False, None): dò
    thất bại KHÔNG được làm bot chết. Phiên bản đã biết là hỏng → bỏ qua.
    """
    global _lan_kiem_cuoi
    if _phien_ban_dau is None:
        return False, None
    now = time.time()
    if now - _lan_kiem_cuoi < chu_ky_giay:
        return False, None
    _lan_kiem_cuoi = now
    try:
        import sheet_config
        moi = sheet_config.doc_o_phien_ban(spreadsheet_id, bot_id)
    except Exception as e:
        _log(f"không đọc được ô phiên bản (bỏ qua, thử lại sau): {e}")
        return False, None
    moi = str(moi).strip()
    if moi == str(_phien_ban_dau).strip() or (_phien_ban_loi is not None and moi == _phien_ban_loi):
        return False, None
    return True, moi


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


def xac_minh_cau_hinh_moi(bot_id, spreadsheet_id, ten_tk, key_cu, secret_cu, muc_hien_tai=None):
    """
    → ('nap_lai', pb) | ('khong_doi', pb) | ('bi_tat', pb) | ('giu_nguyen', lý do) | ('thu_lai', lý do)

    'khong_doi': B1 đổi nhưng DÒNG CỦA TÀI KHOẢN NÀY y nguyên → chạy tiếp, không
    khởi động lại. Không có bước này thì đổi key một tài khoản làm CẢ BA khởi
    động lại — thêm rủi ro vô ích (đã thấy khi diễn tập).
    """
    import sheet_config
    try:
        pb, bang = sheet_config.nap(bot_id, spreadsheet_id)
    except sheet_config.LoiDocSheet as e:
        return 'thu_lai', str(e)
    except sheet_config.LoiSheetCauHinh as e:
        return 'giu_nguyen', str(e)

    that = sheet_config.tim_tai_khoan(bang, ten_tk) if ten_tk else None
    if ten_tk and that is None:
        return 'bi_tat', pb
    if that and muc_hien_tai is not None and _loc(bang[that]) == _loc(muc_hien_tai):
        return 'khong_doi', pb
    if that:
        muc = bang[that]
        k, s = muc.get('key_binance', ''), muc.get('secret_binance', '')
        if (k, s) != (key_cu, secret_cu):
            if not _thu_dang_nhap_binance(k, s):
                return 'giu_nguyen', (
                    f"API key mới của [{that}] KHÔNG đăng nhập được Binance — dán thiếu, "
                    f"sai secret, chưa bật quyền Futures, hoặc chưa thêm IP của VPS.")
            _canh_bao(f"API key của [{that}] đã đổi. Nếu key mới thuộc TÀI KHOẢN BINANCE "
                      f"KHÁC, vị thế đang mở ở tài khoản cũ sẽ KHÔNG còn được bot quản lý.", 0)
    return 'nap_lai', pb


def kiem_tra_va_ap_dung():
    """Dò + xác minh + nạp lại. Gọi lúc bot đang NGHỈ. Có thể không trả về."""
    global _phien_ban_loi, _phien_ban_dau
    try:
        import cst
    except Exception:
        return
    if not getattr(cst, 'nap_tu_sheet', False):
        return
    chu_ky = cst.config.getint('global', 'config_reload_seconds', fallback=300)
    doi, moi = co_thay_doi(cst.bot_id, cst.config_spreadsheet_id, chu_ky)
    if not doi:
        return

    if time.time() - _bat_dau < TOI_THIEU_TRUOC_KHI_NAP_LAI:
        _canh_bao(f"Ô phiên bản B1 đổi ngay sau khi vừa khởi động ({_phien_ban_dau} → {moi}). "
                  f"B1 có đang là công thức tự đổi (NOW, RAND…) không? Hãy gõ SỐ bằng tay. "
                  f"Bot chờ thêm rồi mới nạp để tránh khởi động lại liên tục.")
        return

    muc_cu = None
    try:
        import sheet_config
        bang_cu = getattr(cst, '_bang_tk', None) or {}
        t = sheet_config.tim_tai_khoan(bang_cu, cst.account) if bang_cu else None
        muc_cu = bang_cu.get(t) if t else None
    except Exception:
        pass
    kq, chi_tiet = xac_minh_cau_hinh_moi(
        cst.bot_id, cst.config_spreadsheet_id, cst.account, cst.key_binance,
        cst.secret_binance, muc_cu)
    if kq == 'khong_doi':
        _log(f"phiên bản {moi}: dòng của tài khoản này KHÔNG đổi — chạy tiếp, không khởi động lại")
        _phien_ban_dau = moi
        return
    if kq == 'thu_lai':
        _log(f"chưa đọc được sheet để xác minh ({chi_tiet}) — giữ cấu hình hiện tại, thử lại sau")
        return
    if kq == 'giu_nguyen':
        _phien_ban_loi = moi
        _canh_bao(f"Phiên bản cấu hình {moi} có LỖI — bot GIỮ NGUYÊN cấu hình đang chạy "
                  f"(phiên bản {_phien_ban_dau}), KHÔNG nạp.\n{chi_tiet}\n"
                  f"→ Sửa trên sheet rồi ĐỔI Ô B1 thêm lần nữa.", 0)
        return
    if kq == 'bi_tat':
        dung_vi_bi_tat(nha_khoa=cst.nha_khoa)
    khoi_dong_lai(f"phiên bản cấu hình {_phien_ban_dau} → {moi}", nha_khoa=cst.nha_khoa)


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


def dung_vi_bi_tat(nha_khoa=None):
    """Tài khoản không còn Bật trên sheet → dừng hẳn, điều phối KHÔNG bật lại."""
    _canh_bao("Tài khoản đã bị TẮT hoặc XOÁ khỏi sheet tổng → bot dừng cho tài khoản này.", 0)
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
