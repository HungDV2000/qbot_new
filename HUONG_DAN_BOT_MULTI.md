# 📗 Hướng dẫn Bot ĐA KIỂU LỆNH (hd_order_multi.py)

> Bot này cho phép **tự chọn kiểu lệnh** cho từng "lệnh con" (leg) bằng cách sửa `config.ini`.
> Giá vẫn lấy từ **cột sheet theo dòng**. Phù hợp khi muốn cấu hình linh hoạt (LIMIT / MARKET / STOP / TRAILING).

---

## 1. Ý tưởng

- Mỗi mã coin (1 dòng sheet) có thể có nhiều **leg** (lệnh con): `leg1`, `leg2`, ... tới `leg6`.
- **Kiểu lệnh** của mỗi leg khai báo trong `config.ini` → đổi kiểu chỉ cần sửa config, **không sửa code**.
- **Giá** của mỗi leg lấy từ **cột sheet** bạn chỉ định (theo từng dòng).
- Mỗi leg có **vai trò (role)**:
  - `entry` = mở vị thế (không reduce_only)
  - `exit` = đóng bớt vị thế (reduce_only, chỉ chạy khi ĐÃ có vị thế)

---

## 2. Khai báo leg trong `config.ini` (mục `[global]`)

Kiểu lệnh chọn **THEO TỪNG DÒNG** bằng cột trên sheet (gõ **mã số**):

| Mã gõ trên sheet | Kiểu lệnh |
|------------------|-----------|
| `1` | limit |
| `2` | market |
| `3` | stop_market |
| `4` | stop_limit |
| `5` | trailing |
| (trống) | tắt leg đó cho dòng đó |

```ini
multi_leg_count = 3         ; dùng mấy leg (1..6)

legN_role     = entry       ; entry (mở) | exit (đóng, reduce_only)
legN_type_col = I           ; CỘT chứa MÃ kiểu lệnh (gõ 1..5 theo dòng)
legN_col      = D           ; cột giá chính
legN_aux      = J           ; cột phụ (xem bảng dưới)
legN_pct_col  =             ; (chỉ leg exit) cột % vị thế đóng
```

**Giá chính (`legN_col`) và phụ (`legN_aux`) tùy kiểu lệnh dòng đó:**

| Mã / kiểu | `legN_col` (chính) | `legN_aux` (phụ) |
|-----------|--------------------|------------------|
| 2 market | (bỏ trống) | — |
| 1 limit | giá limit | — |
| 3 stop_market | giá kích hoạt (stop) | — |
| 4 stop_limit | giá stop | giá limit |
| 5 trailing | giá activation | callback % |

> Muốn 1 leg dùng kiểu **cố định** (không đổi theo dòng): bỏ `legN_type_col`, dùng `legN_type = limit` (hoặc market/...).

### Cột phụ (aux) dùng làm gì? Thiếu thì sao?

Một số kiểu lệnh cần **2 con số**, mà 1 ô chỉ chứa 1 số → cột phụ giữ số thứ hai:

- **Stop Limit:** cột chính = giá stop (kích hoạt), **cột phụ = giá limit** (giá khớp).
- **Trailing:** cột chính = giá activation, **cột phụ = callback %** (biên độ trượt).
- **Limit / Market / Stop Market:** chỉ cần 1 số → **không dùng cột phụ**.

**Nếu thiếu cột phụ:**
- Kiểu Limit/Market/Stop Market → không sao (vốn không cần phụ).
- Kiểu Stop Limit/Trailing mà **thiếu cột phụ** → bot **bỏ qua lệnh đó** (log báo `"thiếu cột phụ aux"`), vì không đủ thông tin để đặt.

---

## 3. Cấu hình & cột trên sheet (bản TỐI GIẢN)

```ini
multi_leg_count = 3

# Leg 1 — LỆNH VÀO (lệnh 1): tab ĐẶT LỆNH, kiểu theo dòng ở cột F, giá cột D
leg1_role = entry
leg1_source = dat_lenh
leg1_type_col = F
leg1_col = D

# Leg 2 — CẮT LỖ (SL): tab Chờ và khớp, kiểu cố định, giá cột N
leg2_role = exit
leg2_source = cho_va_khop
leg2_type = stop_market
leg2_col = N

# Leg 3 — CHỐT LỜI (TP): tab Chờ và khớp, kiểu cố định, giá cột O
leg3_role = exit
leg3_source = cho_va_khop
leg3_type = limit
leg3_col = O
```

### Tab `ĐẶT LỆNH (100 MÃ)` — chỉ thêm **1 cột (F)**

| Cột | Nội dung | Ghi chú |
|-----|----------|---------|
| A | Mã coin | có sẵn |
| B | Đòn bẩy (`N`/`0` = tắt dòng) | có sẵn |
| **C** | *(callback bot trailing cũ)* | 🔒 **không đụng** |
| D | **Giá vào** | có sẵn |
| **F** | **Mã kiểu VÀO (1–5)** | ⭐ **thêm mới** — để trống = không vào lệnh dòng đó |
| H | Mức vốn | có sẵn |
| **I → Z** | ⚪ Để trống | `hd_track_30_prices` từng ghi 18 mốc giá vào đây. Bản gọn không kèm bot đó nên vùng này rảnh — nhưng vẫn nên tránh dùng để khỏi xung đột nếu sau này bật lại |
| **J1:M2** | 🔵 **Bot ghi số dư** | `hd_update_all` ghi: J=ví, K=ký quỹ, L=lãi/lỗ mở, M=thời điểm. **Đừng gõ tay vào đây** |

### Tab `Chờ và khớp` — **KHÔNG cần thêm cột nào**

Dùng cột đã có sẵn:

| Cột | Nội dung | Ai điền |
|-----|----------|---------|
| A–I | Symbol, LONG/SHORT, **Đã khớp**, Giá vào… | 🤖 Bot tự ghi |
| **N** | **Giá SL** — để trống = không cắt lỗ | 👤 |
| **O** | **Giá TP** — để trống = không chốt lời | 👤 |
| **P** | **ĐẶT LỆNH** — gõ `Y` mới đặt | 👤 |

**Điều kiện đặt SL/TP:** cột **D (ĐÃ KHỚP) = `Y`** VÀ cột **P (ĐẶT LỆNH) = `Y`**. Bot còn kiểm tra vị thế thật trên Binance trước khi đặt.

### Vì sao SL/TP đọc từ tab "Chờ và khớp"?

Tab **ĐẶT LỆNH** là danh sách ứng viên (top tăng/giảm) **thay đổi liên tục** — mã đã khớp sẽ **biến mất** khỏi đó. Tab **Chờ và khớp** mới là nơi theo dõi **vị thế thực tế đang mở**.

**Bot chạy 2 pha mỗi vòng:**
1. **Pha A** — quét tab ĐẶT LỆNH → đặt **lệnh vào** (theo B2 = LONG/SHORT).
2. **Pha B** — quét tab Chờ và khớp → đặt **SL/TP**. Chạy khi B2 = `LONG`/`SHORT`/`CHỜ`; bỏ qua khi `STOP`/`XÓA…`.

> 💡 Kể cả khi B2 = `CHỜ` (ngừng vào lệnh mới), vị thế đang mở **vẫn được đặt SL/TP** bảo vệ.

### Mã kiểu lệnh (cột F)

| Mã | Kiểu | Cần cột phụ? |
|----|------|--------------|
| `1` | Limit | không |
| `2` | Market | không (bỏ trống giá) |
| `3` | Stop Market | không |
| `4` | Stop Limit | **có** (giá limit) |
| `5` | Trailing | **có** (callback %) |
| *(trống)* | **Không vào lệnh** dòng đó | |

> Dùng mã 4/5 cho lệnh vào thì phải thêm cột phụ và khai `leg1_aux = <cột>`.

### Ví dụ

**Tab ĐẶT LỆNH** dòng 4: `A`=ATOM/USDT · `B`=10 · `D`=2.083 · **`F`=1** · `H`=10
→ vào lệnh **Limit** mua @2.083, vốn 10 USDT.

**Tab Chờ và khớp** (bot tự tạo dòng sau khi khớp): `N`=1.9 · `O`=2.5 · `P`=`Y`
→ SL **Stop Market** @1.9 · TP **Limit** @2.5 — cả hai đóng 100% vị thế.

### Mở rộng khi cần (không bắt buộc)

| Muốn gì | Làm gì |
|---------|--------|
| SL/TP **đổi kiểu theo từng dòng** | Thêm cột mã kiểu (vd R, U) → khai `leg2_type_col = R` |
| TP dùng **Trailing Stop** | Thêm cột callback% (vd V) → khai `leg3_type = trailing` + `leg3_aux = V` |
| **Đóng từng phần** (TP đóng 50%) | Thêm cột % (vd W) → khai `leg3_pct_col = W` |

---

## 3.3. Rải NHIỀU lệnh VÀO cho cùng 1 mã (DCA)

Muốn "mua thêm khi giá giảm / bán thêm khi giá tăng" — đặt nhiều lệnh vào ở nhiều mức giá.

### Cách làm: điền nhiều dòng cùng mã trên tab ĐẶT LỆNH

| Dòng | A | B | D (giá vào) | F (kiểu) | H (vốn) |
|---|---|---|---|---|---|
| 4 | ATOM/USDT | 10 | **1.38** | 1 | **4** |
| 5 | ATOM/USDT | 10 | **1.35** | 1 | **4** |
| 6 | ATOM/USDT | 10 | **1.32** | 1 | **4** |

### ⚠️ BẮT BUỘC bật `allow_dca` trong `config.ini`

```ini
allow_dca = true
```

**Vì sao:** mặc định bot chỉ cho **1 mã vào 1 lần** — khi 1 lệnh khớp (đã có vị thế),
các lệnh còn lại sẽ bị bỏ với lý do *"đã có vị thế"*. Bật `allow_dca = true` để bot
tiếp tục rải các lệnh còn lại.

### ⚠️ Vốn nhân theo số dòng

Mỗi dòng dùng **trọn vốn** cột H. Muốn tổng vốn vẫn là 12 USDT thì chia:
**3 dòng × 4 USDT** (không phải 3 dòng × 12).

| Số dòng | Cột H mỗi dòng | Tổng vốn thực |
|---|---|---|
| 3 | 4 | 12 USDT |
| 3 | 10 | **30 USDT** ⚠️ |

### Giá các lệnh phải khác nhau

Bot chống đặt trùng bằng cách so **giá**. Hai lệnh chênh nhau dưới
`dedup_price_tolerance_pct` (mặc định **0.02%**) bị coi là **trùng** → chỉ đặt 1.

- ✅ 1.38 / 1.35 / 1.32 — cách xa, đặt đủ 3
- ✅ 1.380 / 1.379 / 1.378 — chênh 0.07% > 0.02%, vẫn đặt đủ 3
- ❌ 1.38 / 1.38 / 1.38 — giống hệt, chỉ đặt 1 (đúng, chống lặp đơn)

---

## 4. Quy tắc khối lượng / vốn

- **Leg entry:** mỗi leg dùng **trọn vốn** của dòng (cột H, hoặc D1×E2 / D2). Nếu có 2 leg entry = 2 lệnh vào, mỗi lệnh full vốn.
- **Leg exit:** đóng theo **% vị thế** lấy từ `legN_pct_col` (trống = 100%). Ví dụ TP1 đóng 50%, TP2 đóng 50% thì mỗi leg trỏ tới 1 cột % riêng.

---

## 5. Chống trùng lệnh (per-mã)

Mỗi vòng quét, với mỗi mã bot **đọc 1 lần** vị thế + toàn bộ lệnh đang mở, rồi so khớp theo **(loại lệnh + chiều + reduce_only + giá)**. Nhờ so cả **giá** nên phân biệt được TP1 và TP2 (không đè nhau, không đặt trùng). Nếu API lỗi lúc đọc → **bỏ qua dòng** để tuyệt đối không đặt trùng.

---

## 6. Chạy bot

Bot chọn qua công tắc `ORDER_BOT_MODE` trong file khởi động (chỉ chạy 1 bot vào lệnh tại một thời điểm).

- **Windows:** mở `start_all_bots.bat` bằng Notepad, đổi `set ORDER_BOT_MODE=limit` → `set ORDER_BOT_MODE=multi`, lưu, nhấp đúp chạy.
- **Mac/Linux:**
```bash
ORDER_BOT_MODE=multi ./start_all_bots.sh
```

> ⚠️ **Dừng bot cũ trước khi chạy** (`./stop_all_bots.sh`). Không chạy đồng thời `limit`/`trailing`/`multi` — sẽ đặt lệnh trùng.

Xem log: `tail -f logs/hd_order_multi.log`. Lúc khởi động bot in ra danh sách leg đã nạp để bạn kiểm tra.

---

## 7. Lưu ý

- Sửa `config.ini` xong phải **khởi động lại bot** thì cấu hình leg mới có hiệu lực (đọc 1 lần lúc chạy).
- **Trạng thái B2, vốn D1/D2/E2, cột B (đòn bẩy), cột A (mã)** dùng như các bot khác.
- Leg exit chỉ đặt **sau khi có vị thế**. Cột giá của leg để trống thì leg đó không chạy.
- Khi 1 lệnh đóng (TP/SL) khớp làm đóng vị thế, các lệnh đóng còn lại có thể treo — bot hủy lệnh riêng sẽ dọn.
- Bot đọc giá thật, đặt lệnh thật — test bằng vốn nhỏ (10 USDT), 1 mã trước.

---

## 8. Triển khai trên VPS (cần chuẩn bị gì)

Nếu VPS đã chạy bot cũ thì hầu như đã sẵn sàng. Chỉ cần 3 việc:

| # | Việc | Ghi chú |
|---|------|---------|
| 1 | **Dán khối cấu hình leg vào `config.ini`** (mục `[global]`) | Copy từ `config.ini.example`. **Dễ quên nhất** — thiếu khối này bot báo *"Chưa cấu hình leg nào → không đặt lệnh"* |
| 2 | **Thêm cột trên sheet** (I/K/M + J/L/N/O nếu cần) và điền mã kiểu | Xem mục 3 |
| 3 | **Chạy** `ORDER_BOT_MODE=multi` (hoặc `python3 hd_order_multi.py`) | Dừng bot đặt lệnh cũ trước |

**Khối cấu hình leg cần dán vào `config.ini`:**
```ini
multi_leg_count = 3
leg1_role = entry ; leg1_type_col = I ; leg1_col = D ; leg1_aux = J
leg2_role = exit  ; leg2_type_col = K ; leg2_col = F ; leg2_aux = L
leg3_role = exit  ; leg3_type_col = M ; leg3_col = G ; leg3_aux = N ; leg3_pct_col = O
```
*(Mỗi dòng có thể tách thành nhiều dòng riêng nếu muốn dễ đọc.)*

**Thư viện:** KHÔNG cần cài thêm gì. Bot multi dùng đúng thư viện như bot cũ (ccxt, google-api, telegram, requests). VPS cũ chạy bot cũ được là chạy được bot multi.

**Key Binance:** dùng key sẵn có trên VPS — chỉ cần key đã bật quyền **Futures + Trading**.
