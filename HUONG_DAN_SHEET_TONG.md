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

| | A | B | C | D | E | F | G | H |
|---|---|---|---|---|---|---|---|---|
| **1** | `PHIÊN BẢN` | `1` | | | | | | |
| **2** | Tài khoản | Bật | API Key | API Secret | Sheet ID | Chat ID | %SL | %TP |
| **3** | q2pri | Y | `abc…` | `xyz…` | `1AA…` | -100 | 2 | 3 |
| **4** | q2pub | Y | `def…` | `uvw…` | `1BB…` | -100 | 5 | 6 |
| **5** | q3fu | N | `ghi…` | `rst…` | `1CC…` | -100 | 10 | 10 |

### Số lớp = số tài khoản đang Bật

Mỗi tài khoản chạy **đúng 1 lớp**. Muốn 1 / 2 / 3 lớp thì để 1 / 2 / 3 dòng có
**Bật = Y**. Không có cột "Lớp" — sheet cũ còn cột đó thì bot tự bỏ qua.

Dù 1, 2 hay 3 lớp, vẫn chạy **cùng 5 bot** bằng `./start_all_bots.sh`. Mỗi bot tự
mở một tiến trình con cho mỗi tài khoản đang Bật (3 lớp = 5 điều phối + 15 con).

⚠️ **Mỗi lớp phải là MỘT TÀI KHOẢN BINANCE RIÊNG** (tài khoản phụ – sub-account
cũng được), **không phải nhiều API key của cùng một tài khoản**. Nếu dùng chung
một tài khoản: ba lệnh vào gộp thành **một vị thế**, và lệnh cắt lỗ của lớp 1
(`closePosition`) sẽ **đóng luôn cả lớp 2 và 3**. Bot chặn được trùng y hệt một
key, nhưng không nhận ra được hai key khác nhau cùng thuộc một tài khoản.

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

---

## 8. Sheet bị sửa ĐỘT NGỘT / sửa DỞ — bot làm gì

Nguyên tắc: **bot không bao giờ tự nạp vào một cấu hình hỏng.** Thấy ô B1 đổi, bot
đang chạy đọc trọn cấu hình mới và **soát trước**; chỉ khi ổn mới nạp lại. Có lỗi
thì **giữ nguyên cấu hình đang chạy** và báo Telegram.

Bot chỉ nạp lại lúc đang **nghỉ giữa hai vòng quét** — không bao giờ cắt ngang lúc
vừa vào lệnh mà chưa kịp đặt cắt lỗ.

| Tình huống trên sheet | Bot làm gì |
|---|---|
| Đổi API key hợp lệ của 1 tài khoản | Bot **thử đăng nhập Binance bằng key mới trước**, được thì **chỉ tài khoản đó** khởi động lại. Tài khoản khác chạy tiếp, không bị động tới |
| Đang dán key thì bot đọc (key cụt, dính khoảng trắng) | Giữ nguyên key đang chạy + báo *"dán thiếu?"* |
| Key mới **không đăng nhập được** Binance (sai secret, chưa bật Futures, chưa thêm IP VPS) | Giữ nguyên + báo *"KHÔNG đăng nhập được Binance"* |
| Chép dòng quên sửa → **hai tài khoản trùng API key** hoặc **trùng Sheet ID** | Giữ nguyên + báo *"ĐẶT LỆNH TRÙNG"*. Trùng key = hai tiến trình cùng giao dịch một tài khoản |
| Gõ `2,5` (dấu phẩy kiểu Việt) | Hiểu là `2.5` |
| Gõ chữ vào ô số, %SL/%TP ngoài khoảng 0–100, tên cột sai (`D1` thay vì `D`) | Giữ nguyên + báo rõ ô nào sai |
| Cột **Bật** gõ `Không` | Tắt tài khoản. *(Bản cũ hiểu nhầm `Không` là BẬT.)* Giá trị lạ như `tạm dừng` → báo lỗi, không đoán |
| **Thêm** một dòng tài khoản | Tự mở bot cho tài khoản mới trong vòng `config_reload_seconds` |
| **Tắt / xoá** một dòng tài khoản | Bot của tài khoản đó tự dừng và không bật lại |
| Ô B1 là **công thức tự đổi** (`NOW()`, `RAND()`…) | Vừa khởi động chưa đủ 2 phút thì chưa nạp + báo. **Hãy gõ số tay** vào B1 |
| Google chập chờn đúng lúc bot dò | Bỏ qua, thử lại lần dò sau |
| Sheet tổng đọc lỗi **lúc bật bot** | **Dừng hẳn** — không có cấu hình nào đáng tin để chạy |

**Sau khi bot báo lỗi**: sửa trên sheet rồi **đổi ô B1 thêm lần nữa**. Bot ghi nhớ
phiên bản đã báo lỗi và không đọc lại nó.

### ⚠️ Đổi sang key của TÀI KHOẢN BINANCE KHÁC

Nếu key mới thuộc **một tài khoản Binance khác** (không phải key mới của cùng tài
khoản), các vị thế và lệnh đang mở ở tài khoản cũ sẽ **không còn bot nào quản lý**
— không cập nhật SL/TP, không huỷ lệnh treo. Bot gửi cảnh báo mỗi lần phát hiện
đổi key. Nên **đóng hết vị thế ở tài khoản cũ trước khi đổi**.

---

## 9. Hai cách chạy bot

**Chế độ sheet tổng** (`config_spreadsheet_id` có khai) — cách khuyên dùng:

```bash
./start_all_bots.sh
```

Mỗi bot là **một tiến trình điều phối**, tự mở tiến trình con cho từng tài khoản
đang Bật trên sheet. Cấu hình đổi thì con xin nạp lại, điều phối bật lại con; có
tài khoản mới thì điều phối tự mở. `./status.sh` hiện cả điều phối lẫn con;
`./stop_all_bots.sh` dừng sạch cả hai.

**Chạy lẻ 1 tài khoản** (gỡ lỗi): `QBOT_ACCOUNT=kh_a python3 hd_order_multi.py`.
Đổi cấu hình thì bot tự mở tiến trình mới rồi thoát, và ghi đè `pids/kh_a/*.pid`
để `stop_all_bots.sh` vẫn dừng được.

---

## 10. config.ini bây giờ chỉ còn thông số CHUNG

Đã bỏ khỏi `config.ini.example` các tham số **không bot nào trong bản gọn dùng** —
để lại chỉ gây nhầm:

| Tham số bỏ | Vì sao |
|---|---|
| `test_mode` | ⚠️ **Không có tác dụng gì** — không bot nào đọc. Đặt `true` tưởng là chạy thử, thực tế **vẫn đặt lệnh thật** |
| `key_binance`, `secret_binance`, `spreadsheet_id`, `key_name`, `accounts`, các khối `[kh_a]` | Thông tin tài khoản → **sheet tổng** |
| `lenh2_*`, `lenh3_*`, `delay_vao_lenh_123` | Của `hd_order_123` — đã nghỉ |
| `delay_update_price`, `price_column` | Của `hd_update_price` — đã nghỉ |
| `delay_track_30_prices`, `delay_periodic_report` | Của 2 bot đã nghỉ |
| `is_print_mode`, `time_gap_do_it`, `max_increase_decrease_4h_day_count`, `debug_column_audit_symbol`, `profile_do_it`, `default_ratio_layer_*` | Không bot nào đọc |

Config cũ còn các dòng này vẫn chạy bình thường — bot chỉ bỏ qua chúng.
