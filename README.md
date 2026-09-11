# QBot — bản gọn

Bot giao dịch Binance Futures điều khiển bằng Google Sheet.
Bản này chỉ giữ **5 bot cần thiết** (19 file `.py`), bỏ các bot đã nghỉ.

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

```bash
cp config.ini.example config.ini
```

---

## 2. NĂM BOT

| Bot | Việc | Tắt được? |
|---|---|---|
| `hd_order_multi.py` | Đặt lệnh vào + SL/TP | Không — đây là bot chính |
| `hd_update_cho_va_khop.py` | Cập nhật tab "Chờ và khớp" từ vị thế thật | **🔴 KHÔNG** — xem cảnh báo dưới |
| `hd_update_all.py` | Lấy **số dư** ghi vào **J1:M2** tab ĐẶT LỆNH | Được, chỉ mất số dư trên sheet |
| `hd_alert_possition_and_open_order.py` | Cảnh báo Telegram | Được |
| `hd_cancel_orders_schedule.py` | Hủy lệnh VÀO treo quá lâu | Được, nhưng lệnh treo sẽ tồn mãi |

### 🔴 Đừng tắt `hd_update_cho_va_khop`

Nó **không phải** bot dữ liệu thị trường — nó là **nguồn cấp SL/TP**:

```
config:   leg2_source = cho_va_khop, leg2_col = N   (CẮT LỖ)
          leg3_source = cho_va_khop, leg3_col = O   (CHỐT LỜI)
                              ↓
hd_order_multi đọc tab "Chờ và khớp" để biết đặt SL/TP ở giá nào
                              ↑
chỉ hd_update_cho_va_khop mới điền tab đó từ vị thế thật trên sàn
```

Tắt nó = vào lệnh xong **không có cắt lỗ**.

---

## 3. CHẠY

```bash
./start_all_bots.sh            # tất cả tài khoản khai trong config
./start_all_bots.sh kh_a       # chỉ 1 tài khoản
./status.sh                    # xem bot nào đang chạy
./stop_all_bots.sh             # dừng
```

Chạy lẻ từng bot (khách tự chọn bot cần):

```bash
python3 hd_order_multi.py
python3 hd_update_cho_va_khop.py
python3 hd_update_all.py
python3 hd_alert_possition_and_open_order.py
python3 hd_cancel_orders_schedule.py
```

Chạy `python3 <bot>.py` mà **không đặt** `QBOT_ACCOUNT` thì bot tự chạy cho
**tất cả** tài khoản đang Bật trên sheet tổng, mỗi tài khoản một tiến trình con.

---

## 4. SỐ DƯ TRÊN SHEET — vùng J1:M2

`hd_update_all.py` ghi vào tab **ĐẶT LỆNH**, vùng **J1:M2**:

| | J | K | L | M |
|---|---|---|---|---|
| **1** | Số dư ví | Ký quỹ | Lãi/lỗ mở | Cập nhật lúc |
| **2** | `12345.67` | `2000.50` | `-50.25` | `05/09/2026 14:43:38` |

Mỗi vòng chỉ tốn **1 lượt gọi Binance + 1 lượt ghi Google**, khoảng 1 giây.
Nhịp chạy theo `delay_update_all` (mặc định 120 giây).

Đổi cột bằng `balance_cell = J` trong config.

---

## 5. CẤU HÌNH CẦN BIẾT

Toàn bộ nằm ở `[global]` trong `config.ini`.

### Chế độ chạy hd_update_all

```ini
update_all_mode = balance_only    # chỉ lấy số dư (MẶC ĐỊNH, nhẹ)
```

Đặt `full` sẽ quay lại dựng bảng "100 mã" 58 cột — **chỉ dùng được nếu tab đó
vẫn còn trên sheet**, và tốn 8 lượt gọi Binance **mỗi mã** (100 mã = 800 lượt,
mất 1–3 phút mỗi vòng). Bản gọn không kèm `hd_update_price.py` nên chế độ
`full` sẽ thiếu phần cập nhật giá.

### Chống lỗi 429 (vượt hạn mức Google)

Google chỉ cho **60 lượt đọc/phút**, dùng **chung** cho mọi tài khoản.

```ini
state_cache_ttl_sec = 10          # ô trạng thái B2 chỉ đọc thật mỗi 10 giây
row_cache_ttl_sec = 60            # cột mã nhớ tạm 60 giây
account_start_stagger_sec = 20    # các tài khoản khởi động lệch nhau 20 giây
```

Bấm **DỪNG** trên sheet vẫn có hiệu lực, chậm nhất sau 10 giây.

Số đo thật với 3 tài khoản: **180 → 27 lượt/phút**.

### Tài khoản → SHEET TỔNG

`config.ini` chỉ còn thông số **chung** của bot. Danh sách tài khoản, API key,
Google Sheet riêng, %SL/%TP từng lớp… nằm trên **sheet tổng**:

```ini
bot_id = QBOT01                   # tên tab trên sheet tổng dành cho máy này
config_spreadsheet_id = 1AbC...   # ID sheet tổng
config_reload_seconds = 300       # bao lâu dò ô phiên bản B1 một lần
```

Đổi key / thêm / tắt tài khoản ngay trên sheet rồi **đổi ô B1** — bot tự xác minh
và nạp lại, không cần vào VPS. Dữ liệu sửa dở (key cụt, trùng key giữa hai tài
khoản, gõ chữ vào ô số…) thì bot **giữ nguyên cấu hình đang chạy** và báo Telegram.

Chi tiết: **`HUONG_DAN_SHEET_TONG.md`** (mục 8: sheet bị sửa đột ngột).

⚠️ `test_mode` đã bỏ khỏi config — nó **chưa bao giờ có tác dụng**, đặt `true`
bot vẫn đặt lệnh thật.

Mỗi tài khoản có `logs/<tên>`, `data/<tên>`, `pids/<tên>` riêng.

---

## 6. CẤU TRÚC SHEET

### Tab ĐẶT LỆNH

| Ô / cột | Nội dung |
|---|---|
| `B2` | Trạng thái: `LONG` / `SHORT` / `CHỜ` / `STOP` / `XÓA CHỜ` / `XÓA VỊ THẾ` |
| `D1:E2` | Cấu hình vốn |
| **`J1:M2`** | **Số dư (bot ghi)** |
| Dòng 4–53 | Khối mã **tăng giá** (LONG) |
| Dòng 55–104 | Khối mã **giảm giá** (SHORT) |
| `A` `B` `D` `F` `H` | Mã · Đòn bẩy · Giá vào · Kiểu lệnh (1–5) · Vốn |

### Tab "Chờ và khớp"

| Cột | Nội dung |
|---|---|
| `D` | Đã khớp (`Y`) |
| `N` | Giá cắt lỗ |
| `O` | Giá chốt lời |
| `P` | Cho phép đặt lệnh (`Y`) |

Bot chỉ đặt SL/TP khi **cột D = `Y` VÀ cột P = `Y`**. Để trống ô giá thì bỏ
qua lệnh đó.

---

## 7. TEST

Chạy offline hoàn toàn — không mạng, không tiền thật.

```bash
python3 -m pytest tests/ -q
bash tests/demo_2_accounts.sh          # diễn tập 2 tài khoản
bash tests/demo_3_accounts_rate.sh 90  # đo hạn mức Google với 3 tài khoản
```

| Bộ test | Kiểm cái gì |
|---|---|
| `test_hd_order_multi` | Logic đặt lệnh đa kiểu |
| `test_balance_only` | Ghi số dư đúng J1:M2, không đụng tab đã bỏ |
| `test_rate_limit` | Đếm lượt gọi API, chống 429 |
| `test_symbol_filter` | Chọn mã, chuẩn hoá tên, khử trùng |
| `test_account_case` | Tên tài khoản lệch hoa/thường |
| `test_multi_account` | Cách ly giữa các tài khoản |
| `test_cancel_filter` | Không hủy nhầm lệnh SL/TP |
| `test_telegram_factory` | Chống trùng tin nhắn, rò bộ nhớ |

---

## 8. BOT ĐÃ NGHỈ (không có trong thư mục này)

| Bot | Vì sao bỏ |
|---|---|
| `hd_update_price.py` | Chỉ ghi giá vào tab "100 mã" đã bỏ. Giá đã có sẵn ở cột C, và bot đặt lệnh lấy giá thẳng từ Binance |
| `hd_track_30_prices.py` | Ghi 18 mốc giá vào cột I:Z tab ĐẶT LỆNH — **không bot nào đọc lại**. Đây cũng là bot duy nhất kéo theo `pandas` |
| `hd_periodic_report.py` | Chỉ gửi báo cáo Telegram định kỳ |
| `hd_order_123.py` | Bot multi đã tự lo SL/TP |
| `hd_order.py`, `hd_order_limit.py` | Bản đặt lệnh cũ, thay bằng `hd_order_multi.py` |

Bản đầy đủ của chúng nằm ở `qbot_setup/` và `qbot_setup/backup/`.

---

## 9. XỬ LÝ SỰ CỐ

| Hiện tượng | Nguyên nhân |
|---|---|
| `0xc000012d` khi khởi động | Hết RAM / page file Windows. Tăng page file lên 8192 MB rồi khởi động lại máy |
| `429 Too Many Requests` | Vượt hạn mức Google. Tăng `state_cache_ttl_sec` lên 15–20 |
| `ModuleNotFoundError` | Thiếu file khi copy. Thư mục phải đủ **19 file `.py`** |
| Không tìm thấy section `[tên]` | Khai trong `accounts` nhưng thiếu khối tương ứng, hoặc lệch hoa/thường |
| Vào lệnh nhưng không có SL/TP | `hd_update_cho_va_khop` không chạy |
| Đặt lệnh trùng | Hai thư mục bot cùng chạy chung API key. Khoá chống trùng chỉ có tác dụng trong từng thư mục |
| Telegram báo *"GIỮ NGUYÊN cấu hình đang chạy"* | Dữ liệu mới trên sheet có lỗi (xem tin nhắn). Sửa rồi **đổi ô B1 thêm lần nữa** |
| Sửa sheet mà bot không đổi | Quên đổi ô B1 |

Log nằm ở `logs/<tài_khoản>/<tên_bot>.log`, lỗi ở `logs/<tài_khoản>/error.log`.

---

## 10. VỀ VIỆC BUILD `.exe`

**Không nên.** Build không làm bot nhanh hơn hay nhẹ hơn:

- Tốc độ chạy y hệt — cùng bytecode. Bot này 99% thời gian **chờ mạng**, không phải tính toán
- PyInstaller one-file **khởi động chậm hơn** (giải nén ra thư mục tạm mỗi lần)
- RAM không đổi — vẫn nạp đủ `ccxt`, `googleapiclient`
- Sửa 1 dòng phải build lại; Windows Defender hay nhận nhầm `.exe` tự build là virus

Muốn nhẹ thật thì: **bớt tiến trình**, **bớt thư viện nạp thừa**, **bớt lượt gọi API**.
