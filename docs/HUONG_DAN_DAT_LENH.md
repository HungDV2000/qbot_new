# Hướng dẫn ĐẶT LỆNH (ngắn gọn)

## 1. Chọn MỘT kiểu cho mỗi tài khoản

| Kiểu | Bật bot | Lệnh vào | Cắt lỗ | Chốt lời |
|---|---|---|---|---|
| **MỚI** | `hd_order_multi` | Chọn theo cột F | Giá N | **LIMIT** giá O |
| **CŨ** | `hd_order` **+** `hd_order_123` | Luôn **trailing** | Giá N | **Trailing** giá O |

Kiểu nào cũng **phải bật** `hd_update_cho_va_khop`, vì bot này ghi tab "Chờ và khớp";
thiếu nó thì không có cắt lỗ.
⛔ Không bật chung hai kiểu cho cùng một tài khoản: bot bật sau tự dừng và báo "ĐẶT LỆNH TRÙNG".

| | Windows | macOS / Linux |
|---|---|---|
| Bắt buộc | `chay_bot.bat hd_update_cho_va_khop` | `./start_bot.sh hd_update_cho_va_khop` |
| Kiểu MỚI | `chay_bot.bat hd_order_multi` | `./start_bot.sh hd_order_multi` |
| Hoặc kiểu CŨ | `chay_bot.bat hd_order` + `chay_bot.bat hd_order_123` | `./start_bot.sh hd_order` + `./start_bot.sh hd_order_123` |

**Bot phụ** (bật cùng cách, thay tên bot):

| Bot | Cần khi |
|---|---|
| `hd_cancel_selective` | Muốn **xoá lệnh bằng tick J–M**. Không bật thì tick **không có tác dụng** |
| `hd_alert_possition_and_open_order` | **Nên bật**: báo Telegram mở/đóng vị thế + dọn lệnh sót khi vị thế đóng |
| `hd_cancel_orders_schedule` | Tuỳ: tự huỷ **lệnh VÀO** treo quá `cancel_order_after_minutes` (mặc định **30 phút**), không đụng SL/TP. ⚠️ Đặt limit chờ lâu thì tăng số này hoặc đừng bật |
| `hd_update_all` | Tuỳ: ghi số dư vào tab ĐẶT LỆNH `J1:M2` |

---

## 2. Tab ĐẶT LỆNH — lệnh vào

**Vốn mỗi lệnh:** cột **H** của dòng; H trống thì lấy `D1` × `E2` (% × vốn tổng),
không có E2 thì lấy `D2`. ⚠️ **Tối thiểu 10 USDT** — dưới 10 bot bỏ qua dòng.

**Ghi mã:** dòng **4–53** cho LONG, dòng **55–104** cho SHORT.

| Cột | Kiểu MỚI | Kiểu CŨ |
|---|---|---|
| A | Mã (`BTC`, `ATOMUSDT`…) | Mã |
| B | Đòn bẩy (`N`/`0` = bỏ dòng) | Đòn bẩy |
| C | — | **Callback %** |
| D | Giá vào (kiểu 2 market không cần) | **Giá kích hoạt** |
| F | Kiểu lệnh: `1` limit · `2` market · `3` stop market · `4` stop limit · `5` trailing | — |
| G | Kiểu 4 = giá limit · kiểu 5 = callback % | — |
| H | Vốn (USDT) | Vốn |

**Giá đặt đúng phía** (sai phía: bot bỏ qua hoặc Binance từ chối):

| Kiểu | Lệnh MUA (LONG) | Lệnh BÁN (SHORT) |
|---|---|---|
| 1 limit · 5 trailing | **Thấp hơn** giá hiện tại | **Cao hơn** giá hiện tại |
| 3 stop market · 4 stop limit | **Cao hơn** giá hiện tại | **Thấp hơn** giá hiện tại |
| Cột G của kiểu 4 (giá limit) | **Bằng hoặc cao hơn** D (không thì dễ không khớp) | **Bằng hoặc thấp hơn** D |

**Mỗi mã chỉ vào 1 lần** (đã có vị thế thì thôi).

⚠️ **Muốn đổi giá lệnh đang chờ:** tick **J** ở tab Chờ và khớp để xoá lệnh cũ, rồi mới
sửa giá.
- **Kiểu MỚI:** sửa giá D khi lệnh cũ còn treo thì bot đặt **THÊM** một lệnh ở giá mới
  → gấp đôi vốn.
- **Kiểu CŨ:** bot không đặt thêm, nhưng cũng không đổi giá lệnh cũ.

**Bấm chạy bằng ô B2:**

| B2 | Bot làm gì |
|---|---|
| `CHỜ` | Không vào lệnh mới, vẫn đặt SL/TP. **Nên để CHỜ khi đang sửa sheet** |
| `LONG` | Vào lệnh các dòng 4–53 |
| `SHORT` | Vào lệnh các dòng 55–104 |
| `STOP` | ⚠️ Đóng **hết** vị thế + huỷ **hết** lệnh (cả stop / trailing / cắt lỗ) |
| `XÓA CHỜ` | ⚠️ Huỷ **hết** lệnh chờ (cả stop / trailing / cắt lỗ), giữ vị thế |
| `XÓA VỊ THẾ` | ⚠️ Đóng **hết** vị thế, giữ lệnh chờ |

⚠️ `STOP` / `XÓA …` lặp lại **mỗi vòng** → làm xong đổi B2 về `CHỜ` ngay.
Telegram báo *"Còn … lệnh điều kiện chưa huỷ được"* → vào app Binance huỷ tay.

---

## 3. Tab CHỜ VÀ KHỚP — cắt lỗ / chốt lời

Lệnh vào khớp xong, `hd_update_cho_va_khop` ghi mã vào tab này với **D = Y** và tự
điền giá gợi ý vào N/O (chỉ khi ô trống).

| Cột | Ý nghĩa | Bạn làm |
|---|---|---|
| **N** | Giá cắt lỗ — LONG: **thấp hơn** giá hiện tại · SHORT: **cao hơn** | Sửa nếu muốn |
| **O** | Giá chốt lời — LONG: **cao hơn** giá hiện tại · SHORT: **thấp hơn**. Kiểu mới: lệnh **limit**. Kiểu cũ: giá **kích hoạt trailing**, gõ `NGAY` = kích hoạt ngay | Sửa nếu muốn |
| **P** | Cho phép đặt SL/TP | **Gõ `Y`**: không có Y thì bot KHÔNG đặt |
| **N1** | Kiểu cũ: callback % của chốt lời trailing | Gõ số, ví dụ `1` = 1% |

⚠️ **Kiểu mới:** O đặt sai phía (LONG mà O thấp hơn giá) thì lệnh chốt lời limit
**khớp ngay = đóng vị thế**.

⏱️ Từ lúc khớp đến lúc có SL/TP có thể chậm tới `delay_cho_va_khop` (mặc định 600
giây). Muốn nhanh hơn thì giảm số này trong `config.ini` rồi bật lại bot.

**Xoá lệnh** (phải bật `hd_cancel_selective`; bot tự bỏ tick sau khi xoá):

| Tick | Xoá |
|---|---|
| **J** | Lệnh **vào** còn treo — không đụng SL/TP |
| **K** | Cả cắt lỗ và chốt lời (giữ lệnh vào) |
| **L** | Lệnh sót **một** phía (chỉ còn SL hoặc chỉ còn TP) |
| **M** | **Mọi** lệnh của mã — dùng khi D = ĐÓNG |

Tick = ô checkbox, hoặc gõ `Y` / `X` / `1`. Muốn bỏ hẳn SL/TP thì đổi **P = N** trước,
nếu không vòng sau bot đặt lại.

---

## 4. Các bước mỗi lần đặt lệnh

1. Đặt **B2 = CHỜ**.
2. Điền mã, đòn bẩy, giá (đúng phía), kiểu (hoặc callback nếu dùng kiểu cũ), vốn ≥ 10 USDT.
3. Đổi **B2 = LONG** hoặc **SHORT**. Bot vào lệnh ở vòng quét kế tiếp
   (`delay_vao_lenh`, mặc định 60 giây).
4. Lệnh khớp → sang tab Chờ và khớp, kiểm tra N/O rồi gõ **P = Y**.
5. Kiểm tra: Telegram báo, cột G/H (Có SL / Có TP) chuyển thành **Y**.

---

## 5. Thử lệnh thật trước khi chạy bot (tuỳ chọn)

`tests/thu_dat_lenh_that.py` lần lượt đặt từng loại lệnh ở trên, bằng đúng hàm của bot,
rồi **huỷ ngay**. Mặc định chỉ in kế hoạch.

1. Mở file, điền key, mã, vốn.
2. Đổi `CHAY_THAT = True`.
3. Chạy:
   ```
   python tests/thu_dat_lenh_that.py
   ```
4. Xem log ở `logs/thu_dat_lenh_*.txt`.

⚠️ Đã điền key thì **đừng commit/push** file đó.
