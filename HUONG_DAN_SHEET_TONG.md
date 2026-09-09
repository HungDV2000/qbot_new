# Hướng dẫn Sheet tổng quản lý cấu hình

Mục đích: **đổi API key và cấu hình ngay trên Google Sheet**, không phải mở
file trên VPS.

---

## 1. Nguyên tắc

```
config.ini trên VPS   →  chỉ 2 dòng: mã bot + ID sheet tổng
Sheet tổng            →  danh sách tài khoản, API key, cấu hình từng tài khoản
```

Một sheet tổng phục vụ được **nhiều VPS**. Mỗi máy một **tab riêng**, tên tab
đặt đúng bằng `bot_id` của máy đó.

---

## 2. Tạo sheet tổng

Tạo một Google Sheet mới, đặt tên tuỳ ý (ví dụ `QBOT - CẤU HÌNH`).

**Share sheet này cho tài khoản Google mà bot đang dùng** (tài khoản đã tạo
`credentials.json`), quyền **Editor**.

⚠️ Sheet này chứa API key. **Chỉ share cho người thực sự cần**, đừng share
chung nhóm với sheet đặt lệnh của khách.

### Tạo tab

Đặt tên tab **đúng bằng mã bot**, ví dụ `QBOT01`.

| | A | B | C | D | E | F | G | H | I |
|---|---|---|---|---|---|---|---|---|---|
| **1** | `PHIÊN BẢN` | `1` | | | | | | | |
| **2** | Tài khoản | Bật | API Key | API Secret | Sheet ID | Chat ID | Lớp | %SL | %TP |
| **3** | q2pri | Y | `abc…` | `xyz…` | `1AA…` | -100 | 1 | 2 | 3 |
| **4** | q2pub | Y | `def…` | `uvw…` | `1BB…` | -100 | 2 | 5 | 6 |
| **5** | q3fu | N | `ghi…` | `rst…` | `1CC…` | -100 | 3 | 10 | 10 |

**Dòng 1** — ô `B1` là **số phiên bản**. Sửa bất cứ ô nào bên dưới thì **phải
đổi ô này** (tăng lên 1 chẳng hạn). Bot chỉ nhìn ô này để biết có thay đổi.
Không đổi B1 thì **bot không biết là bạn vừa sửa gì**.

**Dòng 2** — tiêu đề cột. **Dòng 3 trở đi** — mỗi dòng một tài khoản.

---

## 3. Các cột

### Bắt buộc

| Cột | Ý nghĩa |
|---|---|
| **Tài khoản** | Tên định danh, ví dụ `q2pri`. Không dấu, không khoảng trắng |
| **API Key** | API key Binance |
| **API Secret** | API secret Binance |
| **Sheet ID** | ID Google Sheet **đặt lệnh** của tài khoản đó (mỗi tài khoản một sheet riêng) |

Thiếu một trong ba cột key/secret/sheet → **bot dừng** và chỉ rõ tài khoản nào
thiếu. Cố ý như vậy: tài khoản thiếu key sẽ dùng nhầm key của tài khoản khác.

### Tuỳ chọn

| Cột | Ý nghĩa |
|---|---|
| **Bật** | `Y` = chạy, `N` = tạm ngưng. Bỏ trống = coi như `Y` |
| **Chat ID** | Nhóm Telegram nhận thông báo |
| **Lớp** | Chỉ để dễ đọc, bot không dùng |
| **%SL** | % cắt lỗ tính từ giá vào |
| **%TP** | % chốt lời tính từ giá vào |

### Thêm tham số khác

Gõ **thẳng tên tham số** như trong `config.ini` làm tiêu đề cột là dùng được
ngay, không cần sửa code. Ví dụ thêm cột tiêu đề `allow_dca`, điền `true`.

Tiêu đề **không phân biệt hoa/thường và không cần dấu**: `Tài khoản`,
`tai khoan`, `TÀI KHOẢN` đều hiểu như nhau.

---

## 4. Cấu hình trên VPS

`config.ini` rút gọn còn:

```ini
[global]
bot_id = QBOT01
config_spreadsheet_id = 1AbC...XyZ
config_reload_seconds = 300
```

Giữ nguyên `credentials.json` và `token.json` — vẫn cần để mở được sheet.

Để trống `config_spreadsheet_id` thì bot chạy **y như cũ**, đọc hết từ `config.ini`.

---

## 5. Soát trước khi bật

```bash
python3 kiem_tra_cau_hinh.py
```

Lệnh này **không đặt lệnh, không đụng tiền**. Nó in ra: nguồn cấu hình, danh
sách tài khoản, tham số từng tài khoản, và cảnh báo nếu:

- Thiếu key/secret/sheet
- Hai tài khoản dùng **chung một API key** hoặc **chung một Sheet ID** (gần
  như chắc chắn là chép nhầm)
- Tên tài khoản lệch hoa/thường

Chạy lệnh này **mỗi lần sửa sheet**.

---

## 6. Đổi key khi bot đang chạy

1. Sửa API Key / Secret trên sheet
2. **Đổi ô B1** (tăng số phiên bản)
3. Chờ tối đa `config_reload_seconds` (mặc định 5 phút)

Bot sẽ tự khởi động lại và chạy bằng key mới. Không cần vào VPS.

### Bot làm gì lúc khởi động lại

Bot chỉ khởi động lại **sau khi quét xong một vòng** — không bao giờ cắt ngang
lúc vừa đặt lệnh vào mà chưa kịp đặt cắt lỗ.

Thứ tự: nhả khoá chống chạy trùng → mở tiến trình mới → tiến trình cũ thoát.
Tiến trình mới chờ 3 giây cho chắc rồi mới giành khoá, nên **không bao giờ có
hai bot cùng chạy**.

Nếu không mở được tiến trình mới (máy hết RAM chẳng hạn), bot cũ **chạy tiếp
bằng cấu hình cũ** thay vì chết — để không mất giám sát vị thế đang mở.

---

## 7. Khi có sự cố

| Hiện tượng | Nguyên nhân |
|---|---|
| `Không nạp được cấu hình từ sheet tổng` | Sai ID sheet, chưa share cho tài khoản Google của bot, hoặc sai tên tab |
| `THIẾU bot_id` | Có khai `config_spreadsheet_id` nhưng quên `bot_id` |
| `Tài khoản '…' trùng với '…'` | Hai dòng cùng tên (kể cả khác hoa/thường). Bot không đoán — đổi tên cho khác hẳn |
| `Dòng 2 thiếu cột 'Tài khoản'` | Tiêu đề dòng 2 sai, hoặc dữ liệu bắt đầu từ dòng khác |
| Sửa sheet mà bot không đổi | **Quên đổi ô B1** |
| `không tài khoản nào đang Bật` | Cột Bật đều là `N` |

**Sheet đọc lỗi thì bot dừng hẳn**, không dùng giá trị dự phòng — theo yêu cầu:
thà không chạy còn hơn chạy bằng key cũ mà tưởng đã đổi. Lệnh SL/TP đã đặt lên
Binance **vẫn nằm nguyên trên sàn** khi bot dừng.
