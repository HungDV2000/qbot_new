# Hướng dẫn ĐẶT LỆNH (ngắn gọn)

## 1. Chọn MỘT kiểu cho mỗi tài khoản

| Kiểu | Bật bot | Lệnh vào | Cắt lỗ | Chốt lời |
|---|---|---|---|---|
| **MỚI** | `hd_order_multi` | Chọn theo cột F | Giá N | **LIMIT** giá O |
| **CŨ** | `hd_order` **+** `hd_order_123` | Luôn **trailing** | Giá N | **Trailing** giá O |

Kiểu nào cũng **phải bật** `hd_update_cho_va_khop`, vì bot này ghi tab "Chờ và khớp";
thiếu nó thì không có cắt lỗ.
⛔ Không bật chung hai kiểu cho cùng một tài khoản: bot tự dừng và báo "ĐẶT LỆNH TRÙNG".

```
chay_bot.bat hd_update_cho_va_khop
chay_bot.bat hd_order_multi              ← kiểu MỚI
chay_bot.bat hd_order    +  chay_bot.bat hd_order_123    ← hoặc kiểu CŨ
```

---

## 2. Tab ĐẶT LỆNH — lệnh vào

**Vốn:** `E2` = vốn tổng, `D1` = % mỗi lệnh, `D2` = vốn mặc định. Cột **H** của dòng
nào có số thì dòng đó dùng số ở H.

**Ghi mã:** dòng **4–53** cho LONG, dòng **55–104** cho SHORT.

| Cột | Kiểu MỚI | Kiểu CŨ |
|---|---|---|
| A | Mã (`BTC`, `ATOMUSDT`…) | Mã |
| B | Đòn bẩy (`N`/`0` = bỏ dòng) | Đòn bẩy |
| C | — | **Callback %** |
| D | Giá vào | **Giá kích hoạt** |
| F | Kiểu lệnh: `1` limit · `2` market · `3` stop market · `4` stop limit · `5` trailing | — |
| G | Kiểu 4 = giá limit · kiểu 5 = callback % | — |
| H | Vốn (USDT), để trống = theo D1/D2/E2 | Vốn |

**Bấm chạy bằng ô B2:**

| B2 | Bot làm gì |
|---|---|
| `CHỜ` | Không vào lệnh mới, vẫn đặt SL/TP. **Nên để CHỜ khi đang sửa sheet** |
| `LONG` | Vào lệnh các dòng 4–53 |
| `SHORT` | Vào lệnh các dòng 55–104 |
| `STOP` | ⚠️ Đóng **hết** vị thế + huỷ **hết** lệnh |
| `XÓA CHỜ` | ⚠️ Huỷ **hết** lệnh chờ, giữ vị thế |
| `XÓA VỊ THẾ` | ⚠️ Đóng **hết** vị thế, giữ lệnh chờ |

⚠️ `STOP` / `XÓA …` lặp lại **mỗi vòng** → làm xong đổi B2 về `CHỜ` ngay.

**Lưu ý giá:**
- Limit / trailing **MUA**: giá phải **thấp hơn** giá hiện tại.
- Limit / trailing **BÁN**: giá phải **cao hơn** giá hiện tại.
- Sai phía thì bot bỏ qua dòng.

---

## 3. Tab CHỜ VÀ KHỚP — cắt lỗ / chốt lời

Lệnh vào khớp xong, `hd_update_cho_va_khop` ghi mã vào tab này với **D = Y** và tự
điền giá gợi ý vào N/O.

| Cột | Ý nghĩa | Bạn làm |
|---|---|---|
| **N** | Giá cắt lỗ | Sửa nếu muốn |
| **O** | Kiểu mới: giá chốt lời **limit**. Kiểu cũ: giá **kích hoạt trailing**; gõ `NGAY` = kích hoạt ngay (ô trống thì bot tự điền giá gợi ý) | Sửa nếu muốn |
| **P** | Cho phép đặt SL/TP | **Gõ `Y`**: không có Y thì bot KHÔNG đặt |
| **N1** | Kiểu cũ: callback % của chốt lời trailing | Gõ số, ví dụ `1` = 1% |

⏱️ Từ lúc khớp đến lúc có SL/TP có thể chậm tới `delay_cho_va_khop` (mặc định 600
giây). Muốn nhanh hơn thì giảm số này trong `config.ini` rồi bật lại bot.

**Xoá lệnh:** tick cột **J** để xoá lệnh vào, **K** để xoá SL/TP, **M** để xoá mọi
lệnh của mã. Muốn bỏ hẳn SL/TP thì đổi **P = N** trước, nếu không vòng sau bot đặt lại.

---

## 4. Các bước mỗi lần đặt lệnh

1. Đặt **B2 = CHỜ**.
2. Điền mã, đòn bẩy, giá, kiểu (hoặc callback nếu dùng kiểu cũ), vốn.
3. Đổi **B2 = LONG** hoặc **SHORT**. Bot vào lệnh ở vòng quét kế tiếp.
4. Lệnh khớp → sang tab Chờ và khớp, kiểm tra N/O rồi gõ **P = Y**.
5. Kiểm tra: Telegram báo, cột G/H (Có SL / Có TP) chuyển thành **Y**.
