# QBot — bản gọn

Bot giao dịch Binance Futures điều khiển bằng Google Sheet. Sheet của mỗi tài
khoản chỉ còn **2 tab**: **ĐẶT LỆNH** và **Chờ và khớp**. Có **6 bot**, bật riêng
từng cái được.

📘 **Hướng dẫn chi tiết từng bot** (bật/tắt, cấu hình, ô nào đọc/ghi):
**[docs/HUONG_DAN_TUNG_BOT.md](docs/HUONG_DAN_TUNG_BOT.md)**

---

## 1. CÀI ĐẶT

```bash
pip install -r requirements.txt
```

Chép 3 file vào thư mục này (không có sẵn vì chứa thông tin riêng):

| File | Lấy ở đâu |
|---|---|
| `config.ini` | Chép từ `config.ini.example`, điền `bot_id` + `config_spreadsheet_id`. **API key để trên sheet tổng**, không để ở đây |
| `credentials.json` | Google Cloud Console (OAuth Desktop app) |
| `token.json` | Tự sinh lần chạy đầu, sau khi đăng nhập Google |

Soát cấu hình trước khi bật (không đặt lệnh): `python kiem_tra_cau_hinh.py`

---

## 2. SÁU BOT

| Bot | Việc | Bắt buộc? |
|---|---|---|
| `hd_update_cho_va_khop.py` | Ghi tab "Chờ và khớp" từ vị thế thật, gợi ý giá SL/TP | **🔴 CÓ** — tắt là **không có cắt lỗ** |
| `hd_order_multi.py` | Đặt lệnh vào (tab ĐẶT LỆNH) + SL/TP (tab Chờ và khớp) | **CÓ** |
| `hd_alert_possition_and_open_order.py` | Báo Telegram khi mở/đóng vị thế, dọn lệnh sót khi đóng | Nên có |
| `hd_cancel_selective.py` | Xoá lệnh theo **tick J–M** tab "Chờ và khớp" | Nếu dùng tick |
| `hd_cancel_orders_schedule.py` | Huỷ lệnh VÀO treo quá lâu (không đụng SL/TP) | Tuỳ |
| `hd_update_all.py` | Số dư → tab ĐẶT LỆNH **J1:M2** | Tuỳ |

---

## 3. CHẠY

### Bật từng bot

| | Windows (CMD) | Linux / macOS |
|---|---|---|
| Danh sách bot | `chay_bot.bat` | `./start_bot.sh` |
| Bật cho mọi tài khoản | `chay_bot.bat hd_order_multi` | `./start_bot.sh hd_order_multi` |
| Bật cho 1 tài khoản | `chay_bot.bat hd_order_multi kh_a` | `./start_bot.sh hd_order_multi kh_a` |
| Dừng | Ctrl+C trong cửa sổ bot | `./stop_bot.sh hd_order_multi [kh_a]` |
| Xem | Các cửa sổ "QBot - …" | `./status.sh` |

Chạy cho "mọi tài khoản" = bot tự mở một tiến trình con cho **mỗi tài khoản đang
Bật** trên sheet tổng; thêm/tắt tài khoản trên sheet (đổi ô B1) thì tự theo.

### Bật tất cả một lúc (Linux)

```bash
./start_all_bots.sh     # 6 bot
./stop_all_bots.sh      # dừng tất cả
```

---

## 4. CẤU HÌNH

`config.ini` chỉ chứa thông số **chung** của bot — xem chú thích từng dòng trong
`config.ini.example` và bảng "tham số → bot" ở mục 6 của
[docs/HUONG_DAN_TUNG_BOT.md](docs/HUONG_DAN_TUNG_BOT.md).

Tài khoản (API key, sheet riêng, %SL/%TP, Telegram riêng, Bật/Tắt) nằm trên
**sheet tổng**. Sửa trên sheet rồi **đổi ô B1** — bot tự xác minh và nạp lại, không
cần vào VPS. Dữ liệu sửa dở (key cụt, trùng key, gõ chữ vào ô số…) thì bot **giữ
nguyên cấu hình đang chạy** và báo Telegram. Chi tiết: `docs/HUONG_DAN_SHEET_TONG.md`.

Google chỉ cho **60 lượt đọc/phút**, dùng **chung** mọi tài khoản:
`state_cache_ttl_sec = 10` (ô B2 đọc thật mỗi 10 giây),
`account_start_stagger_sec = 20` (các tài khoản khởi động lệch nhau). Bấm DỪNG
trên sheet vẫn có hiệu lực, chậm nhất sau 10 giây.

Mỗi tài khoản có `logs/<tên>`, `data/<tên>`, `pids/<tên>` riêng.

---

## 5. TEST

Chạy offline hoàn toàn — không mạng, không tiền thật.

```bash
for t in tests/test_*.py; do python3 "$t"; done
bash tests/demo_tung_bot.sh            # bật/tắt từng bot
bash tests/demo_2_accounts.sh          # diễn tập 2 tài khoản
bash tests/demo_3_accounts_rate.sh 90  # đo hạn mức Google với 3 tài khoản
bash tests/demo_sheet_dot_ngot.sh      # sheet tổng bị sửa đột ngột
bash tests/demo_doi_key.sh             # đổi key trên sheet tổng
```

| Bộ test | Kiểm cái gì |
|---|---|
| `test_hd_order_multi` | Logic đặt lệnh đa kiểu |
| `test_cancel_selective` | Tick J–M: không xoá nhầm SL, xoá đúng dòng khi dòng xê dịch |
| `test_cot_nguoi_dung` | Cột J–P đi theo mã |
| `test_sltp_goi_y` | Gợi ý SL/TP vào N/O/P, không đè số người dùng |
| `test_cancel_filter` | Bot huỷ theo lịch không huỷ nhầm SL/TP |
| `test_balance_only` | Ghi số dư đúng J1:M2 |
| `test_don_dep` | Không còn code/tab đã bỏ; khoá chống chạy trùng an toàn trên Windows |
| `test_rate_limit` | Chống lỗi 429 |
| `test_sheet_config`, `test_nap_tu_sheet`, `test_config_watcher`, `test_thay_doi_dot_ngot` | Sheet tổng, tự nạp lại cấu hình |
| `test_account_case`, `test_multi_account` | Cách ly giữa các tài khoản |
| `test_telegram_factory` | Chống trùng tin nhắn, rò bộ nhớ |
| `test_bo_numpy` | Không nạp numpy |

---

## 6. ĐÃ BỎ (không có trong thư mục này)

| Bot / module | Vì sao bỏ |
|---|---|
| `hd_update_price.py`, chế độ `full` của `hd_update_all` | Chỉ phục vụ tab "100 mã" đã xoá |
| `hd_track_30_prices.py` | Ghi mốc giá mà không bot nào đọc lại |
| `hd_periodic_report.py` | Chỉ gửi báo cáo Telegram định kỳ |
| `hd_order_123.py`, `hd_order.py`, `hd_order_limit.py` | Thay bằng `hd_order_multi.py` |
| `cascade_manager.py`, `order_state_tracker.py` | Cơ chế "chuỗi lớp" đời cũ — không nơi nào kích hoạt; nay mỗi tài khoản là 1 lớp |
| `symbol_filter.py`, `utils.py`, `binance_utils.py`, `notification_manager.py` | Chỉ phục vụ phần đã bỏ ở trên |

Bản đầy đủ của chúng nằm ở `qbot_setup/`.

---

## 7. XỬ LÝ SỰ CỐ

| Hiện tượng | Nguyên nhân |
|---|---|
| `0xc000012d` khi khởi động | Hết RAM / page file Windows. Tăng page file lên 8192 MB rồi khởi động lại máy |
| `429 Too Many Requests` | Vượt hạn mức Google. Tăng `state_cache_ttl_sec` lên 15–20 |
| `ModuleNotFoundError` | Thiếu file khi copy — chép **toàn bộ** thư mục |
| "⛔ … ĐANG CHẠY" | Bot đó đã chạy cho tài khoản này — đóng cửa sổ/dừng bản cũ trước |
| Vào lệnh nhưng không có SL/TP | `hd_update_cho_va_khop` không chạy, hoặc cột P ≠ Y |
| Đặt lệnh trùng | Hai thư mục bot cùng chạy chung API key. Khoá chống trùng chỉ có tác dụng trong từng thư mục |
| Telegram báo *"GIỮ NGUYÊN cấu hình đang chạy"* | Dữ liệu mới trên sheet tổng có lỗi (xem tin nhắn). Sửa rồi **đổi ô B1 thêm lần nữa** |
| Sửa sheet tổng mà bot không đổi | Quên đổi ô B1 |

Log: `logs/<tài_khoản>/`, lỗi ở `logs/<tài_khoản>/error.log`.

---

## 8. VỀ VIỆC BUILD `.exe`

**Không nên.** Build không làm bot nhanh hơn hay nhẹ hơn: cùng bytecode, cùng
thư viện nạp vào RAM; bản one-file còn khởi động chậm hơn, sửa 1 dòng phải build
lại, và Windows Defender hay nhận nhầm `.exe` tự build là virus.
