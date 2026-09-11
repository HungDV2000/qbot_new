# 👥 Hướng dẫn CHẠY NHIỀU TÀI KHOẢN trên 1 VPS

> ⚠️ **CÁCH CŨ — khai tài khoản ngay trong `config.ini`.**
> `qbot_new` giờ lấy danh sách tài khoản, API key và cấu hình từng tài khoản từ
> **SHEET TỔNG** — xem **`HUONG_DAN_SHEET_TONG.md`**. `config.ini` chỉ còn thông số
> chung của bot. Cách dưới đây vẫn chạy được (khi để trống `config_spreadsheet_id`),
> giữ lại để tham khảo và gỡ lỗi.

> Nhiều bộ (API key / secret / Google Sheet) chạy từ **cùng 1 thư mục code, cùng 1 file config**.
> Không còn phải copy thư mục hay dựng nhiều VPS.

---

## 1. Thêm tài khoản — 2 bước

### Bước 1: Khai tên tài khoản ở `[global]`

```ini
[global]
accounts = kh_a, kh_b, kh_c        ; ← danh sách, cách nhau dấu phẩy
```

### Bước 2: Thêm section cho từng tài khoản (cuối file `config.ini`)

```ini
[kh_a]
key_binance    = <API key của khách A>
secret_binance = <API secret của khách A>
spreadsheet_id = <ID Google Sheet của khách A>
chat_id        = -1001111111111
key_name       = Khach A

[kh_b]
key_binance    = <API key của khách B>
secret_binance = <API secret của khách B>
spreadsheet_id = <ID Google Sheet của khách B>
chat_id        = -1002222222222
key_name       = Khach B
delay_vao_lenh = 120               ; ← ghi đè riêng (tùy chọn)
```

**Nguyên tắc:**
- Mọi cấu hình ở `[global]` được **dùng chung** cho tất cả tài khoản.
- Section tài khoản chỉ khai **cái khác biệt** — thường là 4 dòng: key, secret, sheet, chat_id.
- Có thể **ghi đè bất kỳ tham số nào** của `[global]` (delay, leg, rate…).

> 🔒 **BẮT BUỘC** mỗi section phải khai đủ 3 dòng: `key_binance`, `secret_binance`,
> `spreadsheet_id`. Thiếu 1 dòng bot sẽ **dừng ngay và báo lỗi** — đây là chốt an toàn
> để tránh trường hợp bot lấy nhầm API key hoặc Google Sheet của khách khác.

> ✅ Thêm khách mới = thêm tên vào `accounts` + 5 dòng section. **Không copy thư mục.**

---

## 2. Chạy bot

### 🍎 Mac / Linux
```bash
./start_all_bots.sh              # chạy TẤT CẢ tài khoản
./start_all_bots.sh kh_a         # chỉ chạy kh_a
./start_all_bots.sh kh_a kh_b    # chạy 2 tài khoản

./status.sh                      # xem tài khoản nào đang chạy
./stop_all_bots.sh               # dừng tất cả
./stop_all_bots.sh kh_a          # dừng riêng kh_a
```

### 🪟 Windows
```
start_all_bots.bat               (chạy tất cả)
start_all_bots.bat kh_a          (chỉ 1 tài khoản)
```
Dừng: đóng các cửa sổ CMD có chữ **QBot [tên tài khoản]**.

### Chọn bot đặt lệnh
```bash
ORDER_BOT_MODE=multi ./start_all_bots.sh
```

---

## 2.0. ⭐ Chạy 1 LỆNH cho TẤT CẢ tài khoản

Cách gọn nhất — chạy thẳng bot, **không cần đặt gì cả**:

```bash
python3 hd_order_multi.py
```

Bot tự đọc danh sách `accounts` rồi **mở một tiến trình riêng cho mỗi tài khoản**:

```
==============================================================
  hd_order_multi — chạy cho 3 tài khoản: kh_a, kh_b, kh_c
  (Ctrl+C để dừng tất cả)
==============================================================
  ▶ [kh_a] đã khởi động (PID 13892)
  ▶ [kh_b] đã khởi động (PID 13893)
  ▶ [kh_c] đã khởi động (PID 13894)
[kh_a] 📌 Trạng thái: LONG
[kh_b] 📌 Trạng thái: SHORT
[kh_c] 📌 Trạng thái: CHỜ
```

| Đặc điểm | |
|---|---|
| Màn hình | Mỗi dòng gắn sẵn `[tên tài khoản]` → biết ngay của ai |
| Cách ly | Mỗi tài khoản 1 tiến trình riêng — một cái lỗi **không** kéo cái khác chết |
| Tốc độ | Chạy **song song**, không phải chờ lần lượt |
| Dừng | **Ctrl+C** một lần → dừng sạch tất cả tài khoản |
| Log | Vẫn tách riêng `logs/kh_a/`, `logs/kh_b/`… |

Áp dụng cho **mọi bot**, không riêng `hd_order_multi`:
```bash
python3 hd_update_cho_va_khop.py     # cũng tự chạy cho tất cả tài khoản
```

> 💡 Windows: nhấp đúp file `.py` hoặc chạy `python hd_order_multi.py` — giống hệt.

### So sánh 3 cách chạy

| Cách | Lệnh | Khi nào dùng |
|---|---|---|
| **1 bot, tất cả tài khoản** ⭐ | `python3 hd_order_multi.py` | Chỉ cần vài bot chính, muốn gọn |
| **Tất cả bot, tất cả tài khoản** | `./start_all_bots.sh` | Chạy đầy đủ 8 bot, có PID để `status.sh`/`stop_all_bots.sh` quản lý |
| **1 bot, 1 tài khoản** | `QBOT_ACCOUNT=kh_a python3 hd_order_multi.py` | Thử nghiệm / gỡ lỗi 1 khách |

---

## 2.1. Chạy RIÊNG LẺ từng bot (không dùng start_all_bots)

Hoàn toàn được — chỉ cần thêm **`QBOT_ACCOUNT`** phía trước:

```bash
QBOT_ACCOUNT=kh_a python3 hd_order_multi.py
QBOT_ACCOUNT=kh_a python3 hd_update_cho_va_khop.py
QBOT_ACCOUNT=kh_b python3 hd_order_multi.py      # tài khoản khác, chạy song song OK
```

> ⚠️ **Quên `QBOT_ACCOUNT` → bot DỪNG ngay** kèm hướng dẫn, chứ không chạy nhầm
> bằng key ở `[global]`.

### 🔒 Tự động chống chạy trùng

Bot **tự khoá** theo (tên bot + tài khoản). Chạy lần 2 cùng một bot cho cùng
tài khoản sẽ bị chặn:

```
⛔ hd_order_multi ĐANG CHẠY cho tài khoản 'kh_a' (PID 12769).
   Chạy thêm sẽ ĐẶT LỆNH TRÙNG → không khởi động.
   Muốn chạy lại:  kill 12769   rồi thử lại
```

| Tình huống | Kết quả |
|---|---|
| Chạy lần 2 cùng bot, cùng tài khoản | 🚫 **Chặn** — tránh đặt lệnh trùng |
| Cùng bot nhưng **khác tài khoản** | ✅ Chạy song song bình thường |
| Tiến trình cũ đã chết | ✅ Khoá tự dọn, chạy lại được |
| Cần bỏ qua khoá | `QBOT_NO_LOCK=1 python3 <bot>.py` |

Khoá bảo vệ **cả 2 cách chạy** (bằng tay lẫn qua `start_all_bots.sh`).

### Bot tối thiểu cần chạy

| Bot | Vai trò | Bắt buộc? |
|---|---|---|
| `hd_order_multi.py` | Đặt lệnh vào + SL/TP | ✅ |
| `hd_update_cho_va_khop.py` | Ghi tab "Chờ và khớp" — **bot đặt lệnh cần dữ liệu này để đặt SL/TP** | 🔴 ✅ |
| `hd_update_all.py` | Số dư tài khoản → **J1:M2** tab ĐẶT LỆNH | Nên có |
| `hd_cancel_orders_schedule.py` | Dọn lệnh vào treo quá lâu | Tuỳ |
| `hd_alert_possition_and_open_order.py` | Cảnh báo Telegram | Không |

> ⚠️ Chạy tay thì `./status.sh` và `./stop_all_bots.sh` **không quản lý được**
> (vì không sinh file PID). Dừng bằng `Ctrl+C` hoặc `kill <PID>`.

---

## 3. Dữ liệu được tách riêng thế nào

Mỗi tài khoản có thư mục riêng — **cách ly hoàn toàn**:

```
logs/kh_a/hd_order_multi.log     data/kh_a/order_cache_multi.json     order/kh_a/
logs/kh_a/error.log              pids/kh_a/hd_order_multi.pid
logs/kh_b/hd_order_multi.log     data/kh_b/order_cache_multi.json     order/kh_b/
```

→ Tài khoản A lỗi **không ảnh hưởng** tài khoản B.

---

## 4. Xem trạng thái

```bash
./status.sh
```
```
┌─ 👤 kh_a
│  🟢 hd_order_multi                    PID 12345
│  🟢 hd_update_cho_va_khop             PID 12346
└─ Đang chạy: 8   Đã chết: 0
```
🟢 = đang chạy · 🔴 = đã chết (xem log tìm nguyên nhân)

---

## 5. ⚠️ Lưu ý quan trọng

### Google Sheets — quota dùng chung
Tất cả tài khoản dùng **chung 1 tài khoản Google** (`credentials.json` + `token.json`).

| Việc cần làm | Chi tiết |
|---|---|
| **Share sheet** | Mỗi Google Sheet của khách phải được **share quyền Editor** cho tài khoản Google này |
| **Giới hạn quota** | Google cho **60 lượt đọc/phút**. Chạy nhiều tài khoản dễ chạm trần → bot chờ/lỗi |
| **Cách giảm tải** | Tăng `delay_*` trong `[global]`, ví dụ `delay_cho_va_khop = 900`, `delay_update_all = 300` |

**Số tài khoản khuyến nghị với 1 credentials:** tối đa **3–5**. Nhiều hơn nên tách credentials hoặc giãn delay.

### Tài nguyên VPS
Mỗi tài khoản chạy ~8–9 tiến trình (~1 GB RAM).

| Số tài khoản | Tiến trình | RAM cần | VPS đề xuất |
|---|---|---|---|
| 1 | 8–9 | ~1 GB | 2 GB |
| 3 | ~27 | ~3 GB | 4 GB |
| 5 | ~45 | ~5 GB | 8 GB |

### An toàn
- **Chỉ chạy 1 bot đặt lệnh** mỗi tài khoản (`trailing` / `limit` / `multi`) — chạy nhiều sẽ đặt lệnh **trùng**.
- **Chống khởi động trùng**: chạy `start_all_bots.sh` khi tài khoản đang chạy sẽ bị **chặn**
  (báo `⛔ ĐANG CHẠY`). Muốn khởi động lại: `./stop_all_bots.sh <tài_khoản>` rồi chạy lại.
- Sửa `config.ini` xong phải **khởi động lại** tài khoản đó.
- Test bằng **vốn nhỏ** trước khi chạy thật.

---

## 6. Tương thích ngược

Nếu **để trống** `accounts` (hoặc không khai) → bot chạy **y hệt như trước**:
- Đọc key/sheet trực tiếp từ `[global]`
- Log vào `logs/`, dữ liệu vào `data/` (không có thư mục con)

→ Khách đang chạy **không cần đổi gì**.

---

## 7. Kiểm tra trước khi chạy thật

### 7.1. Test logic (nhanh, ~1 giây)
```bash
python3 tests/test_multi_account.py
```
Kết quả mong đợi: `14 PASS / 0 FAIL`

### 7.2. DIỄN TẬP 2 TÀI KHOẢN — không cần tài khoản Binance thật ⭐
```bash
./tests/demo_2_accounts.sh
```

Dựng sandbox trong `/tmp`, chạy **code thật** (cst.py, hd_order_multi.py, các script
start/stop/status) với Binance–Google–Telegram **giả lập**. An toàn tuyệt đối,
không kết nối mạng, không tốn tiền.

Kiểm chứng 14 điểm:

| Nhóm | Kiểm tra |
|---|---|
| **Cách ly** | log / dữ liệu tách riêng theo tài khoản |
| **Đúng tài khoản** | mỗi bot đọc đúng Sheet, đặt lệnh đúng API key, gửi Telegram đúng chat_id |
| **Không lẫn** | tài khoản A không bao giờ chạm key/sheet của B |
| **Vận hành** | `status.sh` hiển thị đúng; chặn khởi động trùng; dừng riêng 1 tài khoản không ảnh hưởng tài khoản kia |

Kết quả mong đợi: `✅ 14 đạt   ❌ 0 lỗi`

Ví dụ dòng bằng chứng in ra:
```
✅ kh_a đặt lệnh bằng ĐÚNG KEY_CUA_A
   ↳ lệnh kh_a: KEY_CUA_A|ATOM/USDT:USDT|LIMIT|buy|7.2463|1.38|ro=False
✅ kh_b đặt lệnh bằng ĐÚNG KEY_CUA_B
   ↳ lệnh kh_b: KEY_CUA_B|ATOM/USDT:USDT|LIMIT|buy|7.2463|1.38|ro=False
```

Kiểm tra config đọc đúng cho từng tài khoản:
```bash
QBOT_ACCOUNT=kh_a python3 -c "import cst; print(cst.config.get('global','spreadsheet_id'))"
```
