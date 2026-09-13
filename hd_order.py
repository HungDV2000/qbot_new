import giu_cua_so  # PHẢI nạp ĐẦU TIÊN: dừng/lỗi thì giữ cửa sổ Windows để đọc thông báo
# ==============================================================================
# hd_order — ĐẶT LỆNH VÀO kiểu CŨ (như qbot_setup): TRAILING STOP
#
#   Tab ĐẶT LỆNH, ô B2:  LONG → dòng 4–53 MUA  ·  SHORT → dòng 55–104 BÁN
#                        CHỜ / STOP / XÓA CHỜ / XÓA VỊ THẾ → như hd_order_multi
#   A = mã · B = đòn bẩy · C = callback % · D = giá kích hoạt · H = vốn (D1/D2/E2)
#
# Mỗi mã chỉ 1 lệnh vào: đã có vị thế HOẶC đã có lệnh vào đang chờ thì bỏ qua.
# Chạy chung bộ máy với hd_order_multi (chống trùng, sheet tổng, nhiều tài khoản).
# Đi cặp với hd_order_123 (SL/TP).  ⛔ KHÔNG chạy cùng hd_order_multi — bot tự chặn.
# ==============================================================================
import hd_order_multi as dong_co

if __name__ == "__main__":
    dong_co.chay('order')
