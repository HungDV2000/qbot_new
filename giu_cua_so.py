"""
GIỮ CỬA SỔ khi bot / công cụ KẾT THÚC trên Windows — để đọc được thông báo.

Bấm đúp file .py trên Windows: Python mở một cửa sổ riêng và ĐÓNG NGAY khi
chương trình dừng → lỗi cấu hình hiện ra rồi biến mất, không kịp đọc.

Nạp module này ĐẦU TIÊN (trước cả cst — cst có thể dừng ngay lúc nạp vì thiếu
cấu hình). Mọi kiểu kết thúc — chạy xong, SystemExit, lỗi chưa bắt, thiếu thư
viện — đều in xong thông báo rồi CHỜ NHẤN ENTER mới đóng.

KHÔNG chờ khi:
  • không phải Windows (Linux/macOS: chữ vẫn còn trên terminal)
  • tiến trình con do điều phối mở (QBOT_SUPERVISED=1) — không ai bấm Enter được
  • bot đang tự khởi động lại vì đổi cấu hình (config_watcher gọi khong_giu())
  • người dùng bấm Ctrl+C — chủ động tắt
  • đầu vào không phải bàn phím (chạy nền, dịch vụ)
Ép bật / tắt: QBOT_GIU_CUA_SO=1 / QBOT_GIU_CUA_SO=0
"""
import atexit
import os
import signal
import sys

LOI_NHAC = "⏸  Chương trình đã dừng. Đọc thông báo ở trên rồi nhấn Enter để đóng cửa sổ..."

_giu = True
_ctrl_c = False


def khong_giu():
    """Gọi trước khi thoát CỐ Ý không cần người xem (vd tự khởi động lại)."""
    global _giu
    _giu = False


def _nen_giu():
    ep = os.environ.get('QBOT_GIU_CUA_SO', '').strip()
    if ep == '0' or not _giu or _ctrl_c:
        return False
    if os.environ.get('QBOT_SUPERVISED', '') == '1':
        return False
    if ep == '1':
        return True
    if os.name != 'nt':
        return False
    try:
        return sys.stdin is not None and sys.stdin.isatty()
    except Exception:
        return False


def _cho_enter():
    if not _nen_giu():
        return
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception:
        pass
    try:
        print("\n" + "─" * 60 + "\n" + LOI_NHAC, flush=True)
        input()
    except Exception:
        pass


def _nhan_ctrl_c(signum, frame):
    global _ctrl_c
    _ctrl_c = True
    raise KeyboardInterrupt


_hook_goc = sys.excepthook


def _hook(loai, loi, tb):
    global _ctrl_c
    if issubclass(loai, KeyboardInterrupt):
        _ctrl_c = True
    _hook_goc(loai, loi, tb)        # in lỗi ra màn hình TRƯỚC khi chờ Enter


sys.excepthook = _hook
try:
    signal.signal(signal.SIGINT, _nhan_ctrl_c)
except Exception:
    pass                            # không phải luồng chính — bỏ qua
# Đăng ký SỚM NHẤT → chạy SAU CÙNG (atexit chạy ngược thứ tự): các bước dọn dẹp
# khác (nhả khoá chống chạy trùng…) xong hết rồi mới chờ Enter.
atexit.register(_cho_enter)
