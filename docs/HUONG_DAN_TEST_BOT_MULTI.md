# 🧪 Hướng dẫn TEST bot đa kiểu lệnh (hd_order_multi.py)

Test theo 2 bước: **(A) test logic offline** (không tốn tiền) → **(B) test thật vốn nhỏ** trên Binance.

---

## A. TEST LOGIC OFFLINE (làm trước, an toàn 100%)

Bước này kiểm tra bộ não của bot (đọc config, chọn leg, tính vốn, chống trùng...) mà **không kết nối Binance, không tốn tiền**.

### Cách chạy

Mở terminal tại thư mục bot rồi gõ:

```bash
python3 tests/test_hd_order_multi.py
```

Hoặc (nếu có pytest):

```bash
python3 -m pytest tests/test_hd_order_multi.py -v
```

### Kết quả mong đợi

Dòng cuối in ra:

```
===== KẾT QUẢ: 18 PASS / 0 FAIL / 18 test =====
```

Nếu thấy **0 FAIL** là logic đúng. Nếu có `❌` → chụp màn hình gửi kỹ thuật.

### 18 test này kiểm tra gì (khớp yêu cầu khách)

| Nhóm test | Yêu cầu được kiểm tra |
|-----------|------------------------|
| `load_legs`, `col_letter_to_index` | Đọc **kiểu lệnh từ config** + **cột từ sheet** |
| `capital_priority` | Tính vốn: cột H → D1×E2 (min 10) → D2 |
| `entry_only_when_no_position`, `exit_only_when_has_position` | **Role linh hoạt**: entry chỉ khi chưa có vị thế; exit chỉ khi đã có |
| `entry_full_capital`, `two_entry_legs_each_full_capital` | Mỗi lệnh **vào** dùng **full vốn** (kể cả DCA nhiều lệnh vào) |
| `exit_partial_percent` | Lệnh **đóng** chia **% theo cột** (TP từng phần) |
| `type_market/stop_limit/trailing` | 5 **kiểu lệnh** phát sinh đúng tham số (giá chính + cột phụ) |
| `dedup_*` | **Chống trùng** theo loại+chiều+giá; phân biệt TP1/TP2 |
| `entry_limit_wrong_direction`, `short_exit_side` | An toàn: chặn khớp-ngay, đảo chiều đúng khi SHORT |

> 💡 Chạy lại test này **mỗi khi sửa code** để chắc không làm hỏng logic.

---

## B. TEST THẬT trên Binance (vốn nhỏ)

> ⚠️ Bot đặt **lệnh thật bằng tiền thật**. Dùng **~10–15 USDT, 1 mã** để thử. Không có chế độ giả lập.

### B0. Chuẩn bị

1. Có `config.ini` (API key Binance), `credentials.json` (Google Sheets).
2. Cài thư viện: `pip install -r requirements.txt`.
3. **Tắt các bot đặt lệnh khác** để tránh nhiễu (`./stop_all_bots.sh`).
4. Chọn bot multi: sửa file khởi động → `ORDER_BOT_MODE=multi` (xem HUONG_DAN_BOT_MULTI.md).
5. Cấu hình leg trong `config.ini` (dùng ví dụ mặc định: leg1 limit-vào D, leg2 SL-stop_market F, leg3 TP-limit G %I).
6. Sheet: đặt **B2 = CHỜ** trước cho an toàn.

Xem log realtime khi chạy: `tail -f logs/hd_order_multi.log`. Lúc khởi động bot in ra danh sách leg đã nạp — **kiểm tra đúng cấu hình** trước khi cho chạy.

---

### B1. Kịch bản 1 — Lệnh VÀO (LIMIT chờ) + chống trùng

**Mục tiêu:** xác nhận bot đặt đúng lệnh vào và không đặt trùng.

1. Điền 1 dòng (vd ATOM/USDT): B=`1` (đòn bẩy), D=**giá thấp hơn giá thị trường khá nhiều** (để lệnh treo, chưa khớp), H=`10`. Để trống F, G.
2. Đổi B2 = `LONG`.
3. **Kỳ vọng:** trên Binance xuất hiện **1 lệnh LIMIT mua** đúng giá cột D. Telegram báo "LEG 1 (LIMIT / entry)".
4. Chờ bot quét thêm 1–2 vòng → **không đặt thêm lệnh trùng** (log ghi "leg1 bỏ qua: đã có lệnh tương tự").

✔️ Đạt yêu cầu: **vào lệnh LIMIT** + **chống trùng per-mã**.

---

### B2. Kịch bản 2 — TP + SL sau khi vị thế khớp

**Mục tiêu:** exit legs chỉ chạy sau khi có vị thế, đúng % và đúng loại.

1. Điền thêm: F=**giá SL** (thấp hơn giá vào), G=**giá TP** (cao hơn giá vào), I=`50` (đóng 50% ở TP).
2. Sửa cột D **sát giá thị trường** để lệnh vào khớp → có vị thế.
3. **Kỳ vọng** vòng quét sau:
   - 1 lệnh **STOP_MARKET** (cắt lỗ) ở giá F, khối lượng = **toàn bộ** vị thế.
   - 1 lệnh **LIMIT** (chốt lời) ở giá G, khối lượng = **50%** vị thế.
   - Telegram báo "LEG 2 (STOP_MARKET / exit)" và "LEG 3 (LIMIT / exit)".
4. Để trống G → **không có TP**; để trống F → **không có SL** (kiểm tra bật/tắt từng cái).

✔️ Đạt yêu cầu: **role linh hoạt** + **SL/TP đúng loại** + **% đóng từng phần**.

---

### B3. Kịch bản 3 — MỖI DÒNG MỘT KIỂU LỆNH (điểm mấu chốt)

**Mục tiêu:** chứng minh "mỗi dòng chọn kiểu lệnh riêng bằng cột mã số trên sheet".

Mã kiểu: **1**=limit, **2**=market, **3**=stop_market, **4**=stop_limit, **5**=trailing.

1. `B2 = CHỜ`. Điền 2 dòng khác kiểu (cột **I** = mã kiểu lệnh vào):
   - Dòng ATOM/USDT: `I = 1` (limit), cột D = giá vào.
   - Dòng SOL/USDT: `I = 2` (market), cột D để trống.
2. `B2 = LONG` → **kỳ vọng:**
   - ATOM vào bằng **LIMIT** (lệnh chờ ở giá D).
   - SOL vào bằng **MARKET** (khớp ngay).
3. Đổi `I` của một dòng sang `4` (stop_limit) → nhớ điền **cột phụ J** (giá limit). Vòng sau dòng đó chạy STOP_LIMIT.
4. Tương tự cột **K** đổi kiểu SL, cột **M** đổi kiểu TP theo từng dòng.

✔️ Đạt yêu cầu: **mỗi dòng chạy một kiểu lệnh khác nhau, cấu hình bằng cột sheet**.

---

### B4. Kịch bản 4 — Nhiều lệnh VÀO (DCA) và nhiều TP

1. Thêm `leg4_type = limit`, `leg4_role = entry`, `leg4_col = J` (giá vào thứ 2, thấp hơn). Đặt `multi_leg_count = 4`.
2. **Kỳ vọng:** 2 lệnh LIMIT mua ở 2 mức giá (cột D và J), **mỗi lệnh full vốn**.
3. Tương tự có thể thêm 2 leg TP ở 2 giá khác nhau (cột G và J) → cả 2 cùng đặt, phân biệt theo giá.

✔️ Đạt yêu cầu: **nhiều leg 1..6**, mỗi entry full vốn, TP1/TP2 không đè nhau.

---

### B5. Dừng & dọn

1. `B2 = STOP` (đóng hết vị thế + hủy hết lệnh chờ) hoặc `CHỜ` (nghỉ).
2. `./stop_all_bots.sh`.
3. Kiểm tra trên Binance đã sạch vị thế/lệnh treo (lệnh đối ứng còn lại do bot hủy lệnh dọn, hoặc hủy tay).

---

## ✅ Checklist tổng

- [ ] A. `python3 tests/test_hd_order_multi.py` → 18 PASS / 0 FAIL
- [ ] B1. Lệnh LIMIT vào đúng giá + không đặt trùng
- [ ] B2. TP (LIMIT) + SL (STOP_MARKET) đúng loại, đúng % sau khi khớp
- [ ] B3. Đổi `legN_type` trong config → kiểu lệnh đổi theo
- [ ] B4. Nhiều lệnh vào full vốn; nhiều TP phân biệt theo giá
- [ ] B5. STOP dọn sạch

## Lưu ý an toàn
- Vốn nhỏ (10–15 USDT), 1 mã khi thử.
- Chỉ chạy **1** bot đặt lệnh (multi / limit / trailing) tại một thời điểm — chạy nhiều sẽ **đặt lệnh trùng**.
- Sửa `config.ini` xong phải **khởi động lại bot** mới có hiệu lực.
- Giá điền đúng chiều: mua thấp/bán cao (vào & TP), SL ngược lại (xem HUONG_DAN_BOT_MULTI.md mục 2).
