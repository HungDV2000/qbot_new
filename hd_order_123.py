import giu_cua_so  # PHẢI nạp ĐẦU TIÊN: dừng/lỗi thì giữ cửa sổ Windows để đọc thông báo
# ==============================================================================
# hd_order_123 — SL/TP kiểu CŨ (như qbot_setup) cho vị thế đã khớp
#
#   Tab "Chờ và khớp", dòng có D = Y (đã khớp) và P = Y (cho phép đặt):
#     • CẮT LỖ  : STOP MARKET tại giá cột N   (N trống → giá vào ∓ %SL sheet tổng)
#     • CHỐT LỜI: TRAILING STOP kích hoạt tại giá cột O
#                 O trống / 0 / NGAY → kích hoạt NGAY quanh giá hiện tại
#                 callback % lấy ô N1 (trống → callback_rate_123 trong config)
#   Đã có cắt lỗ / chốt lời (bất kể giá) thì không đặt thêm.
#   B2 = STOP / XÓA … thì bỏ qua (hệ thống đang dọn dẹp).
#
# Nhịp: delay_vao_lenh_123 (không khai → dùng delay_vao_lenh).
# Chạy chung bộ máy với hd_order_multi.  ⛔ KHÔNG chạy cùng hd_order_multi — bot tự chặn.
# ==============================================================================
import hd_order_multi as dong_co

if __name__ == "__main__":
    dong_co.chay('123')
