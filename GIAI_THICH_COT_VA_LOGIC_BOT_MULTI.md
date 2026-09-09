# 📚 Giải thích CỘT sheet & LOGIC bot đa kiểu lệnh (hd_order_multi.py)

Tài liệu tham chiếu: (1) ý nghĩa từng ô/cột trên sheet **`ĐẶT LỆNH (100 MÃ)`**, (2) cách bot đọc và ra quyết định.

---

## PHẦN 1 — GIẢI THÍCH TỪNG CỘT

### 1.1. Ô điều khiển chung (góc trên bảng)

| Ô | Nhãn cạnh nó | Ý nghĩa | Ví dụ |
|----|--------------|---------|-------|
| **B2** | Trạng thái | Trạng thái bot (điều khiển toàn cục) | `LONG` |
| **D1** | C1 = "Tỷ lệ vốn" | % vốn cho mỗi lệnh (so với tổng vốn) | `1%` |
| **D2** | C2 = "Mức vốn/lệnh" | Vốn mặc định mỗi lệnh (tối thiểu 10 USDT) | `10` |
| **E2** | — | Tổng vốn (dùng để tính D1 × E2) | `10` |

**Giá trị hợp lệ của ô B2:**

| Gõ vào B2 | Bot làm |
|-----------|---------|
| `LONG` | Quét danh sách LONG (dòng 4–53), đặt lệnh chiều MUA |
| `SHORT` | Quét danh sách SHORT (dòng 55–104), đặt lệnh chiều BÁN |
| `CHỜ` | Nghỉ, không làm gì |
| `XÓA CHỜ` | Hủy tất cả lệnh chờ, giữ vị thế |
| `XÓA VỊ THẾ` | Đóng tất cả vị thế, giữ lệnh chờ |
| `STOP` | Đóng tất cả vị thế **và** hủy tất cả lệnh chờ |

### 1.2. Bảng danh sách coin (dòng 4→53 LONG, 55→104 SHORT)

> Hàng 3 là **tiêu đề** (label). Bot đọc dữ liệu từ **hàng 4 trở đi**.

| Cột | Index | Nhãn (hàng 3) | Ý nghĩa | Bắt buộc? |
|-----|-------|---------------|---------|-----------|
| **A** | 0 | (Mã) | Mã coin, vd `ATOM/USDT` | ✅ |
| **B** | 1 | (Đòn bẩy) | Đòn bẩy. Gõ `N` hoặc `0` = **tắt dòng** | ✅ |
| C | 2 | — | *(callback cũ — KHÔNG dùng ở bot multi)* | ❌ |
| **D** | 3 | `Giá VÀO` | Giá chính của **lệnh VÀO** (leg1) | tùy leg |
| E | 4 | — | *(trống — chưa gán)* | ❌ |
| **F** | 5 | `SL` | Giá chính của **lệnh CẮT LỖ** (leg2) | tùy leg |
| **G** | 6 | `TP` | Giá chính của **lệnh CHỐT LỜI** (leg3) | tùy leg |
| **H** | 7 | `Mức vốn` | Vốn riêng cho dòng (bỏ trống = dùng D1/D2/E2) | ❌ |
| **I** | 8 | `Kiểu VÀO (1-5)` | **Mã kiểu lệnh** của lệnh vào | ✅* |
| **J** | 9 | `Phụ VÀO` | Tham số phụ của lệnh vào | tùy kiểu |
| **K** | 10 | `Kiểu SL (1-5)` | **Mã kiểu lệnh** của SL | tùy |
| **L** | 11 | `Phụ SL` | Tham số phụ của SL | tùy kiểu |
| **M** | 12 | `Kiểu TP (1-5)` | **Mã kiểu lệnh** của TP | tùy |
| **N** | 13 | `Phụ TP` | Tham số phụ của TP | tùy kiểu |
| **O** | 14 | `% đóng TP` | % vị thế đóng ở TP (trống = 100%) | ❌ |

\* Cột **kiểu (I/K/M) trống → leg đó KHÔNG chạy** cho dòng đó (đây là công tắc bật/tắt từng lệnh theo dòng).

### 1.3. Mã kiểu lệnh (gõ vào cột I / K / M)

| Mã | Kiểu lệnh | Giá chính (D/F/G) | Phụ (J/L/N) |
|----|-----------|-------------------|-------------|
| `1` | Limit | giá limit | — |
| `2` | Market | *(bỏ trống)* | — |
| `3` | Stop Market | giá kích hoạt (stop) | — |
| `4` | Stop Limit | giá stop | **giá limit** |
| `5` | Trailing | giá activation | **callback %** |
| (trống) | Tắt leg này | — | — |

> Có thể gõ tên chữ thay số cũng được: `limit`, `market`, `stop_market`, `stop_limit`, `trailing`.

### 1.4. Bản đồ cột ↔ config (mặc định)

| Leg | Vai trò | Cột kiểu | Cột giá | Cột phụ | Cột % |
|-----|---------|----------|---------|---------|-------|
| leg1 | entry (VÀO) | I | D | J | — |
| leg2 | exit (SL) | K | F | L | — |
| leg3 | exit (TP) | M | G | N | O |

Cấu hình trong `config.ini`:
```ini
multi_leg_count = 3
leg1_role = entry ; leg1_type_col = I ; leg1_col = D ; leg1_aux = J
leg2_role = exit  ; leg2_type_col = K ; leg2_col = F ; leg2_aux = L
leg3_role = exit  ; leg3_type_col = M ; leg3_col = G ; leg3_aux = N ; leg3_pct_col = O
```

---

## PHẦN 2 — LOGIC HOẠT ĐỘNG CỦA BOT

### 2.1. Vòng lặp chính

Bot chạy vô hạn, mỗi `delay_vao_lenh` giây (mặc định 60s) gọi `do_it()` một lần:

```
Đọc B2 (trạng thái)
 ├─ STOP        → đóng hết vị thế + hủy hết lệnh chờ
 ├─ XÓA CHỜ     → hủy hết lệnh chờ (giữ vị thế)
 ├─ XÓA VỊ THẾ  → đóng hết vị thế (giữ lệnh chờ)
 ├─ CHỜ         → nghỉ
 └─ LONG/SHORT  → QUÉT đặt lệnh (xem 2.2)
```

Trước khi quét: đọc vốn **D1, D2, E2**. Nếu **E2 và D2 đều rỗng** → không đặt lệnh.

### 2.2. Quét đặt lệnh (khi B2 = LONG hoặc SHORT)

- `LONG`  → quét dòng **4–53**, chiều vào = **BUY**.
- `SHORT` → quét dòng **55–104**, chiều vào = **SELL**.

**Với MỖI dòng, bot làm tuần tự:**

1. **Đọc mã (A)** — trống → bỏ dòng.
2. **Đọc đòn bẩy (B)** — `N` / `0` / trống → **bỏ dòng** (tắt).
3. **Kiểm tra symbol** giao dịch được không (còn niêm yết, đang TRADING) + chuẩn hóa tên.
4. **Kiểm tra lại B2** — nếu trạng thái đã đổi giữa chừng → **dừng quét ngay** (an toàn).
5. **Đọc 1 lần** (chống trùng):
   - Vị thế hiện tại của mã (`positionAmt`, có dấu: >0 LONG, <0 SHORT, 0 = chưa có).
   - Toàn bộ lệnh đang mở của mã (+ lệnh trailing/algo nếu có leg trailing) → **snapshot**.
   - *Nếu đọc lỗi (mạng/API) → bỏ qua dòng* để tuyệt đối không đặt trùng.
6. **Tính vốn** cho dòng: ưu tiên **cột H** → nếu không có thì **D1 × E2** (tối thiểu 10) → nếu không thì **D2**.
7. **Lấy giá hiện tại** (ticker) của mã.
8. **Set đòn bẩy** (chỉ khi chưa có vị thế và có leg vào).
9. **Lập kế hoạch lệnh** (`plan_row`) — xem 2.3.
10. **Đặt từng lệnh** trong kế hoạch qua Binance, ghi log + báo Telegram.

### 2.3. Lập kế hoạch cho từng leg (trái tim của bot)

Duyệt lần lượt leg1 → leg2 → leg3 (→...). Với mỗi leg:

```
1. Xác định KIỂU lệnh:
     - Nếu leg có cột kiểu (type_col) → đọc mã ở ô đó (theo dòng). Trống/mã lạ → BỎ leg.
     - Nếu không → dùng kiểu cố định trong config.

2. Xác định VAI TRÒ:
     - entry: CHỈ đặt khi symbol CHƯA có vị thế.  (reduce_only = false)
     - exit : CHỈ đặt khi symbol ĐÃ có vị thế.    (reduce_only = true)
     (leg không đúng điều kiện vị thế → bỏ)

3. Xác định CHIỀU (side):
     - entry: theo trạng thái (LONG→buy, SHORT→sell)
     - exit : ngược dấu vị thế thực tế (LONG→sell, SHORT→buy)

4. Đọc GIÁ chính (cột col). market thì không cần. Cột trống → bỏ leg.
   Đọc PHỤ (cột aux): stop_limit=giá limit; trailing=callback%. Thiếu → bỏ leg.

5. VALIDATE (an toàn):
     - Lệnh VÀO kiểu limit: buy phải < giá hiện tại, sell phải > giá hiện tại
       (tránh khớp ngay lập tức). Sai chiều → bỏ leg.

6. CHỐNG TRÙNG: nếu snapshot đã có lệnh cùng (loại + chiều + reduce_only + GIÁ gần đúng)
   → bỏ leg. (So cả GIÁ nên TP1 và TP2 khác giá KHÔNG bị coi là trùng.)

7. Tính KHỐI LƯỢNG:
     - entry: vốn ÷ giá (mỗi leg vào dùng TRỌN vốn của dòng)
     - exit : |vị thế| × (% ở cột pct, mặc định 100%)

8. Đưa leg vào "kế hoạch" và ghi tạm vào snapshot (chống trùng ngay trong cùng dòng).
```

### 2.4. Đặt lệnh theo kiểu

Sau khi có kế hoạch, bot gọi đúng hàm theo kiểu:

| Kiểu | Hàm Binance | Tham số |
|------|-------------|---------|
| limit | create_limit_order | giá limit |
| market | create_market_order | (không giá) |
| stop_market | create_stop_market_order | giá stop |
| stop_limit | create_stop_limit_order | giá stop + giá limit |
| trailing | create_trailing_stop_order | activation + callback% |

Lệnh **exit** luôn `reduce_only = true` (chỉ đóng bớt vị thế, không mở thêm).

---

## PHẦN 3 — CHỐNG TRÙNG LỆNH (per-mã)

Đây là điểm quan trọng để **không đặt lặp đơn**:

1. Mỗi vòng, mỗi mã bot **đọc 1 lần** vị thế + toàn bộ lệnh mở → dựng "bức tranh" hiện trạng.
2. Trước khi đặt mỗi leg, so khớp với bức tranh theo **4 tiêu chí**: loại lệnh + chiều + reduce_only + **giá (gần đúng ±0.2%)**.
   - Đã có lệnh y hệt → **bỏ**, không đặt lại.
   - Nhờ so **giá**, TP1 (giá 2.5) và TP2 (giá 2.7) được xem là **2 lệnh khác nhau** → cả 2 vẫn đặt được.
3. Nếu lúc đọc bị lỗi API → **bỏ qua dòng** (thà không đặt còn hơn đặt trùng).

---

## PHẦN 4 — VÍ DỤ END-TO-END

**Cấu hình:** mặc định (leg1 vào cột I/D/J, leg2 SL cột K/F/L, leg3 TP cột M/G/N/O).

**Sheet:** B2=`LONG`, D2=`10`. Dòng 4:

| A | B | D | F | G | H | I | K | M | O |
|---|---|---|---|---|---|---|---|---|---|
| ATOM/USDT | 1 | 2.0 | 1.85 | 2.5 | 10 | 1 | 3 | 1 | 50 |

**Bot hiểu:**
- **Vào lệnh:** kiểu `1`=Limit, mua ATOM ở giá **2.0** (cột D), vốn 10 USDT → KL = 10/2.0 = 5.
- Khi lệnh vào khớp (có vị thế 5):
  - **Cắt lỗ:** kiểu `3`=Stop Market ở giá **1.85** (cột F), đóng 100% (5).
  - **Chốt lời:** kiểu `1`=Limit ở giá **2.5** (cột G), đóng **50%** (cột O) = 2.5.

**Dòng khác** có thể gõ `I=2` (vào bằng Market), `I=4` + phụ J (Stop Limit)... → **mỗi dòng một kiểu lệnh khác nhau**.

---

## PHẦN 5 — GHI NHỚ NHANH

- Cột **kiểu (I/K/M)** trống → tắt lệnh đó cho dòng đó.
- Cột **giá (D/F/G)** trống → cũng bỏ lệnh đó (trừ market).
- Lệnh **SL/TP chỉ đặt SAU khi lệnh vào đã khớp** (đã có vị thế).
- Đổi `config.ini` (cột nào map vào leg nào) phải **khởi động lại bot**.
- Chỉ chạy **1 bot đặt lệnh** (multi/limit/trailing) tại một thời điểm — tránh đặt trùng.
- Bot đặt **lệnh thật, tiền thật** — test vốn nhỏ trước (xem HUONG_DAN_TEST_BOT_MULTI.md).
