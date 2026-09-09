# ⚙️ Hướng dẫn CẤU HÌNH NHIỀU TÀI KHOẢN

> Tất cả tài khoản nằm trong **một file `config.ini` duy nhất**.
> Thêm khách mới = thêm vài dòng, không cần copy thư mục.

---

## 1. Nguyên tắc

File `config.ini` chia làm 2 phần:

| Phần | Chứa gì |
|------|---------|
| **`[global]`** | Cấu hình **dùng chung** cho mọi tài khoản (thời gian quét, cấu hình lệnh, rate…) |
| **`[tên_tài_khoản]`** | Thông tin **riêng** của từng khách (API key, Google Sheet, Telegram) |

Giá trị trong khối tài khoản sẽ **ghi đè** giá trị cùng tên ở `[global]`.

---

## 2. Thêm một tài khoản — 2 bước

### Bước 1: Khai tên vào dòng `accounts` (ở đầu `[global]`)

```ini
[global]
accounts = kh_a, kh_b, kh_c
```

- Các tên cách nhau bằng **dấu phẩy**
- Tên tự đặt (nên viết liền, không dấu): `kh_a`, `anh_tuan`, `cty_abc`…
- Để **trống** (`accounts =`) → chạy chế độ 1 tài khoản như cũ

### Bước 2: Thêm khối tài khoản vào **cuối file**

```ini
[kh_a]
key_binance    = abc123...          ; API key Binance của khách A
secret_binance = xyz789...          ; API secret Binance của khách A
spreadsheet_id = 1AbC...XyZ         ; ID Google Sheet của khách A
chat_id        = -1001111111111     ; nhóm Telegram nhận thông báo
key_name       = Khach A            ; tên hiển thị (tuỳ chọn)
```

> Tên trong ngoặc vuông `[kh_a]` phải **trùng khớp** với tên đã khai ở `accounts`.

---

## 3. Cái gì để đâu?

### ✅ Được khai trong khối `[tên_tài_khoản]` — CHỈ 7 dòng

| Dòng | Ý nghĩa | Bắt buộc |
|------|---------|----------|
| `key_binance` | API key Binance của khách | ✅ |
| `secret_binance` | API secret Binance của khách | ✅ |
| `spreadsheet_id` | ID Google Sheet của khách | ✅ |
| `chat_id` | Nhóm Telegram nhận thông báo | Nên có |
| `bot_token` | Bot Telegram riêng (nếu khách dùng bot riêng) | Tuỳ chọn |
| `prefix_channel` | Tiền tố hiển thị trong tin nhắn | Tuỳ chọn |
| `key_name` | Tên hiển thị của tài khoản | Tuỳ chọn |

Đây là **thông tin nhận dạng** — mỗi khách một bộ riêng.

### ⛔ KHÔNG được khai trong khối tài khoản

Mọi tham số **vận hành** phải nằm ở `[global]`:

- `delay_*` (thời gian quét)
- `allow_dca`, `dedup_price_tolerance_pct`
- `multi_leg_count`, `legN_*` (cấu hình lệnh)
- `cancel_*`, `lenh*_rate_*`, `default_*`
- …và mọi tham số còn lại

**Vì sao:** để tất cả tài khoản chạy **đồng nhất** — cùng một cách hoạt động, dễ kiểm soát, dễ hỗ trợ. Tránh tình trạng mỗi khách một kiểu rồi không rõ vì sao chạy khác nhau.

Khai sai, bot **dừng ngay** và chỉ rõ dòng cần chuyển:

```
❌ Section [kh_a] khai tham số KHÔNG được phép:
       delay_vao_lenh
       allow_dca
   Trong khối tài khoản chỉ được khai thông tin nhận dạng:
       bot_token, chat_id, key_binance, key_name,
       prefix_channel, secret_binance, spreadsheet_id
   Các tham số vận hành (thời gian quét, cấu hình lệnh…) phải đặt ở
   [global] để mọi tài khoản chạy giống nhau.
   → Chuyển 2 dòng trên lên [global], hoặc xoá đi.
```

### 🔒 3 dòng bắt buộc

`key_binance`, `secret_binance`, `spreadsheet_id` phải khai **riêng trong từng khối**.
Thiếu một dòng, bot dừng ngay — chốt chặn để **không bao giờ đặt lệnh nhầm tài khoản**.

---

## 4. Trường hợp thật sự cần ngoại lệ

Nếu có lý do chính đáng để một tham số được khai riêng, mở ngoại lệ **có kiểm soát** ở `[global]`:

```ini
[global]
accounts = kh_a, kh_b
account_extra_keys = delay_vao_lenh        ; ← chỉ mở đúng tham số này

[kh_b]
key_binance    = ...
secret_binance = ...
spreadsheet_id = ...
delay_vao_lenh = 120                        ; ← giờ mới được phép
```

> Nên hạn chế dùng. Mở càng ít, các tài khoản càng đồng nhất và dễ hỗ trợ.

---

## 4.1. Giá trị hợp lệ cho các mốc thời gian

Các tham số `delay_*`, `cancel_orders_minutes` phải là **số nguyên dương**.
Điền sai, bot **dừng ngay và báo lỗi bằng tiếng Việt** (không chạy sai âm thầm).

| Điền | Kết quả |
|------|---------|
| `60` | ✅ Chạy bình thường |
| `5` | ⚠️ Chạy, kèm cảnh báo *"khá ngắn, dễ chạm giới hạn API"* |
| `999999` | ⚠️ Chạy, kèm cảnh báo *"rất dài, bot sẽ hiếm khi chạy"* |
| `0` | ❌ **CHẶN** — quét liên tục sẽ spam API, có thể bị Binance/Google chặn IP |
| `-5` | ❌ **CHẶN** — số âm làm bot chết giữa chừng |
| `abc` | ❌ **CHẶN** — phải là số |
| `1.5` | ❌ **CHẶN** — phải là số nguyên, không dùng số lẻ |
| *(để trống)* | ❌ **CHẶN** — báo thiếu dòng nào, cần thêm gì |

Ví dụ thông báo khi điền sai:
```
❌ `delay_vao_lenh = 0` không hợp lệ [kh_a] — phải >= 1.
   Đặt 0 hoặc số âm sẽ khiến bot quét liên tục không nghỉ,
   gây spam API và có thể bị Binance/Google chặn.
   Ví dụ đúng:  delay_vao_lenh = 60
```

### Khuyến nghị theo số tài khoản

| Số tài khoản | `delay_vao_lenh` |
|---|---|
| 1–2 | 60 giây |
| 3–5 | 60–120 giây |
| trên 5 | từ 120 giây |

> Google giới hạn **60 lượt đọc/phút** dùng chung cho mọi tài khoản.
> Delay càng nhỏ càng dễ chạm trần.

---

## 5. Ví dụ hoàn chỉnh

```ini
[global]
accounts = kh_a, kh_b

# ── Dùng chung cho mọi khách ──
delay_vao_lenh = 60
delay_cho_va_khop = 600
allow_dca = false
cancel_order_after_minutes = 30
tab_dat_lenh = ĐẶT LỆNH (100 MÃ)
bot_token = 8431813976:AAH...        ; bot Telegram dùng chung

# ── Để trống: mỗi khách khai riêng bên dưới ──
key_binance =
secret_binance =
spreadsheet_id =

# ══════════════ CÁC TÀI KHOẢN ══════════════

[kh_a]
key_binance    = AAAA1111...
secret_binance = BBBB2222...
spreadsheet_id = 1AbCdEf_SheetCuaKhachA
chat_id        = -1001111111111
key_name       = Khach A

[kh_b]
key_binance    = CCCC3333...
secret_binance = DDDD4444...
spreadsheet_id = 1XyZgHi_SheetCuaKhachB
chat_id        = -1002222222222
key_name       = Khach B
delay_vao_lenh = 120
```

---

## 6. Bật / tắt một tài khoản

Chỉ cần sửa dòng `accounts`, **giữ nguyên khối bên dưới**:

```ini
accounts = kh_a, kh_b, kh_c      ; chạy cả 3
accounts = kh_a, kh_c            ; tạm ngưng kh_b (thông tin vẫn còn)
accounts = kh_a                  ; chỉ chạy kh_a
```

---

## 6.1. Các bot trong hệ thống

Hệ thống gồm nhiều bot nhỏ, mỗi bot làm một việc. **Mỗi tài khoản chạy một bộ bot riêng.**

### 🔹 Nhóm 1 — ĐẶT LỆNH

| Bot | Làm gì | Ghi chú |
|-----|--------|---------|
| **`hd_order_multi.py`** ⭐ | Đặt **lệnh vào + SL + TP**. Chọn được 5 kiểu lệnh (Limit / Market / Stop Market / Stop Limit / Trailing) theo từng dòng sheet | Bot đặt lệnh duy nhất trong bản gọn |

> ⚠️ **Chỉ chạy 1 bot đặt lệnh** cho mỗi tài khoản. Chạy 2 bộ bot cùng key
> (kể cả ở hai thư mục khác nhau) sẽ **đặt lệnh trùng** — khoá chống trùng chỉ
> có tác dụng trong từng thư mục.

### 🔹 Nhóm 2 — CẬP NHẬT DỮ LIỆU lên Google Sheet

| Bot | Làm gì | Bắt buộc? |
|-----|--------|-----------|
| **`hd_update_cho_va_khop.py`** | Ghi tab **"Chờ và khớp"** — theo dõi vị thế đang mở, mã nào đã khớp | 🔴 **BẮT BUỘC** — bot đặt lệnh đọc tab này để biết đặt SL/TP ở giá nào. Tắt nó = vào lệnh xong **không có cắt lỗ** |
| `hd_update_all.py` | Lấy **số dư tài khoản** ghi vào **J1:M2** tab ĐẶT LỆNH | Nên có — tắt thì chỉ mất số dư hiển thị trên sheet |

**Vùng J1:M2 trên tab ĐẶT LỆNH:**

| | J | K | L | M |
|---|---|---|---|---|
| **1** | Số dư ví | Ký quỹ | Lãi/lỗ mở | Cập nhật lúc |
| **2** | `12345.67` | `2000.50` | `-50.25` | `05/09/2026 14:43:38` |

Đổi cột bằng `balance_cell = J`. Nhịp chạy theo `delay_update_all` (mặc định 120 giây).

### 🔹 Nhóm 3 — DỌN DẸP & GIÁM SÁT

| Bot | Làm gì | Bắt buộc? |
|-----|--------|-----------|
| `hd_cancel_orders_schedule.py` | Hủy **lệnh vào** treo quá lâu (mặc định 30 phút). **Không đụng SL/TP** | Nên có |
| `hd_alert_possition_and_open_order.py` | Cảnh báo qua Telegram khi vị thế đóng / có biến động | Tuỳ |

### 🔹 Nhóm 4 — CÔNG CỤ THỦ CÔNG (không chạy tự động)

| Bot | Làm gì |
|-----|--------|
| — | Bản gọn không kèm công cụ thủ công nào. Chúng nằm ở `qbot_setup/` |
| `hd_isolated_crossed_converter.py` | Chuyển đổi chế độ ký quỹ Isolated ↔ Crossed |
| `hd_update_danhmuc.py` | Cập nhật danh mục mã |
| `hd_order_market_price.py` | Đặt lệnh theo giá thị trường (bản thử nghiệm) |
| `hd_update_all_new.py` | Bản thử nghiệm của `hd_update_all` |

Bản gọn không kèm công cụ thủ công. Cần dùng thì lấy từ `qbot_setup/`, nhớ đặt `QBOT_ACCOUNT` để chạy đúng tài khoản:
`QBOT_ACCOUNT=kh_a python3 hd_cancel_selective.py`

---

### 📌 Bộ tối thiểu để giao dịch

```
hd_order_multi.py            ← đặt lệnh vào + SL/TP
hd_update_cho_va_khop.py     ← BẮT BUỘC, cung cấp dữ liệu vị thế cho bot trên
```

Chỉ 2 bot này là giao dịch được. Các bot khác bổ sung dữ liệu và tiện ích.

### 🔗 Bot nào cần bot nào

```
hd_update_all.py  ──ghi──►  tab "100 mã"  ──►  (người dùng chọn mã)
                                                      │
                                                      ▼
                                            tab "ĐẶT LỆNH (100 MÃ)"
                                                      │
                                              hd_order_multi ──đặt lệnh──► Binance
                                                      ▲                      │
                                                      │                      ▼
hd_update_cho_va_khop.py  ──ghi──►  tab "Chờ và khớp" ◄──── đọc vị thế thực tế
                                     (bot đặt lệnh đọc tab này để đặt SL/TP)
```

---

## 7. Chuẩn bị Google Sheet

Tất cả tài khoản dùng **chung 1 tài khoản Google** (chung `credentials.json` + `token.json`).

Với mỗi khách:
1. Tạo Google Sheet riêng (sao chép từ mẫu, giữ nguyên cấu trúc cột)
2. **Chia sẻ** sheet đó cho tài khoản Google mà bot đang dùng — quyền **Editor**
3. Lấy `spreadsheet_id` từ đường dẫn:
   ```
   https://docs.google.com/spreadsheets/d/1AbCdEf_ĐÂY_LÀ_ID/edit
                                          └────────┬───────┘
                                          copy đoạn này
   ```

> ⚠️ Google giới hạn **60 lượt đọc/phút**. Chạy nhiều tài khoản dễ chạm trần —
> khuyến nghị tối đa **3–5 tài khoản**. Nhiều hơn thì tăng các giá trị `delay_*`
> ở `[global]` (ví dụ `delay_cho_va_khop = 900`).

---

## 8. Lỗi thường gặp

| Báo lỗi | Nguyên nhân | Cách sửa |
|---------|-------------|----------|
| `Section [kh_a] THIẾU: key_binance` | Khối tài khoản thiếu dòng bắt buộc | Thêm đủ 3 dòng: key, secret, spreadsheet_id |
| `Không tìm thấy section [kh_a]` | Khai tên trong `accounts` nhưng chưa tạo khối `[kh_a]` | Thêm khối vào cuối file |
| `[kh_la] chưa được khai trong accounts` | Có khối nhưng quên thêm tên vào `accounts` | Thêm tên vào dòng `accounts` |
| Bot chạy nhưng không thấy dữ liệu sheet | Sheet chưa share cho tài khoản Google của bot | Share quyền Editor |

---

## 9. Kiểm tra cấu hình trước khi chạy

```bash
python3 tests/test_multi_account.py
```

Hoặc xem trực tiếp một tài khoản đọc ra giá trị gì:

```bash
QBOT_ACCOUNT=kh_a python3 -c "import cst; print(cst.spreadsheet_id)"
```

---

## 10. Lưu ý khi sửa file trên máy chủ

```bash
cp config.ini config.ini.backup_$(date +%Y%m%d)
```

Luôn sao lưu trước khi sửa. Sửa xong phải **khởi động lại bot** thì cấu hình mới có hiệu lực.
