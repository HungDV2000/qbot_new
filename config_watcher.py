# -*- coding: utf-8 -*-
"""
config_watcher — dò cấu hình trên sheet tổng đổi, rồi tự khởi động lại bot.

VÌ SAO PHẢI KHỞI ĐỘNG LẠI CHỨ KHÔNG THAY NÓNG
    Mỗi bot dựng đối tượng `exchange = ccxt.binance({apiKey, secret})` ở CẤP
    MODULE, tức chỉ tạo một lần lúc khởi động (hd_order_multi.py dòng 65).
    Muốn đổi key giữa chừng phải dựng lại đối tượng đó cùng mọi thứ đang giữ
    tham chiếu tới nó — và nguy hiểm hơn: lệnh đang treo thuộc key CŨ, bot với
    key MỚI không thấy để huỷ, thành lệnh mồ côi trên sàn.
    Khởi động lại thì mọi thứ dựng lại từ đầu, không có trạng thái nửa vời.

CÁCH DÒ RẺ
    Chỉ đọc MỘT ô B1 (phiên bản) mỗi `config_reload_seconds` giây, mặc định
    300s. 15 tiến trình chia cho 5 phút ≈ 3 lượt/phút — không đáng kể so với
    hạn mức 60 lượt/phút của Google.

CHỐT AN TOÀN
    Bot chỉ thoát khi KHÔNG còn việc dở. Thoát đúng lúc vừa đặt lệnh vào mà
    chưa kịp đặt cắt lỗ là tình huống tệ nhất — nên hàm `co_the_thoat` do
    từng bot cung cấp, mặc định là "chờ hết vòng quét".
"""

import os
import subprocess
import sys
import time

_lan_kiem_cuoi = 0.0
_phien_ban_dau = None


def _log(msg):
    print(f"🔄 [CẤU HÌNH] {msg}", flush=True)


def khoi_tao(phien_ban_hien_tai):
    """Ghi nhớ phiên bản lúc bot khởi động, để sau này so sánh."""
    global _phien_ban_dau, _lan_kiem_cuoi
    _phien_ban_dau = phien_ban_hien_tai
    _lan_kiem_cuoi = time.time()


def co_thay_doi(bot_id, spreadsheet_id, chu_ky_giay=300):
    """
    Đọc ô phiên bản (nếu đã tới hạn) và cho biết có đổi không.

    Trả về (đã_đổi, phiên_bản_mới). Chưa tới hạn thì trả (False, None) mà
    không gọi mạng. Đọc lỗi cũng trả (False, None) — dò thay đổi thất bại
    KHÔNG được làm bot chết; bot chỉ dừng khi nạp cấu hình thật sự lỗi.
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

    if str(moi).strip() != str(_phien_ban_dau).strip():
        return True, moi
    return False, None


def khoi_dong_lai(ly_do="cấu hình trên sheet đã đổi", nha_khoa=None):
    """
    Mở một tiến trình mới chạy đúng bot này, rồi thoát.

    THỨ TỰ BẮT BUỘC — sai là hai bot cùng chạy → ĐẶT LỆNH TRÙNG:
        1. Nhả khoá chống chạy trùng (PID của tiến trình cũ)
        2. Mở tiến trình mới
        3. Thoát tiến trình cũ

    Tiến trình mới ngủ một nhịp ngắn rồi mới giành khoá, để tiến trình cũ kịp
    thoát hẳn.
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

    try:
        env = dict(os.environ, QBOT_RESTART_DELAY='3')
        subprocess.Popen([sys.executable] + sys.argv, env=env,
                         start_new_session=True)
        _log(f"đã mở tiến trình mới: {' '.join([os.path.basename(sys.executable)] + sys.argv)}")
    except Exception as e:
        _log(f"❌ KHÔNG mở được tiến trình mới: {e}")
        _log("   Bot cũ vẫn chạy tiếp bằng cấu hình cũ để không mất giám sát.")
        return False

    _log("tiến trình cũ thoát")
    raise SystemExit(0)


def cho_neu_vua_khoi_dong_lai():
    """
    Tiến trình vừa được sinh ra sẽ ngủ vài giây, đợi tiến trình cũ thoát hẳn
    rồi mới giành khoá. Gọi hàm này TRƯỚC khi lấy khoá.
    """
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
