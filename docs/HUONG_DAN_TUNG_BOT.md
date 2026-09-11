# HƯỚNG DẪN TỪNG BOT — bật, tắt, cấu hình, nhiệm vụ

Sheet của mỗi tài khoản chỉ còn **2 tab**: **ĐẶT LỆNH** và **Chờ và khớp**.
Có **6 bot**, bật **riêng từng cái** được. Mỗi bot tự chạy cho mọi tài khoản đang
**Bật = Y** trên sheet tổng.

---

## 0. TRƯỚC KHI BẬT

1. `config.ini`: chép từ `config.ini.example`, điền **2 dòng**:
   ```ini
   bot_id = QBOT01                   ; tên tab của máy này trên sheet tổng
   config_spreadsheet_id = 1AbC...   ; ID sheet tổng
   ```
   API key, sheet riêng, %SL/%TP của từng tài khoản đều nằm trên **sheet tổng**
   (xem `HUONG_DAN_SHEET_TONG.md`).
2. Chép `credentials.json` vào thư mục bot (lấy ở Google Cloud Console →
   Credentials → OAuth client ID loại **Desktop app** → Download JSON).
3. **Đăng nhập Google 1 lần**: bấm đúp `dang_nhap_google.py`. Trình duyệt mở ra →
   chọn tài khoản Google **đã được chia sẻ quyền Editor** các sheet → Cho phép.
   Xong sẽ có `token.json`, mọi bot dùng chung.

   **Đăng nhập là tự động:** quên bước này thì bật bot (hoặc `kiem_tra_cau_hinh.py`)
   cũng tự mở trình duyệt đăng nhập; token hỏng / bị Google thu hồi cũng tự mở lại.
   Từ lần sau bot tự làm mới token, không phải đăng nhập nữa. Riêng bot chạy nền
   (`start_bot.sh`) không mở được trình duyệt → chỉ báo "bấm đúp dang_nhap_google.py".

   ⚠️ Trên Google Cloud Console → **OAuth consent screen**, nếu ứng dụng đang ở
   trạng thái **Testing** thì Google **thu hồi token sau 7 ngày** → mỗi tuần bot
   đòi đăng nhập lại. Bấm **Publish app** (chuyển sang *In production*) để hết.
4. Soát cấu hình — không đặt lệnh, không đụng tiền:
   ```
   python kiem_tra_cau_hinh.py
   ```
   Hết dòng ❌ mới bật bot.

---

## 1. BẬT / TẮT / XEM

### Windows (CMD, mở tại thư mục bot)

| Việc | Lệnh |
|---|---|
| Xem danh sách bot | `chay_bot.bat` |
| Bật 1 bot cho **mọi** tài khoản đang Bật | `chay_bot.bat hd_update_cho_va_khop` |
| Bật 1 bot cho **riêng** 1 tài khoản | `chay_bot.bat hd_order_multi kh_a` |
| Dừng 1 bot | Bấm **Ctrl+C** trong cửa sổ của bot đó (hoặc đóng cửa sổ) |
| Xem bot nào đang chạy | Nhìn các cửa sổ tên **"QBot - …"** trên thanh tác vụ |

Mỗi bot mở **một cửa sổ CMD riêng**. Không có `chay_bot.bat` thì gõ thẳng
`python hd_update_cho_va_khop.py`, hoặc **bấm đúp** file `.py`.

**Cửa sổ không tự đóng khi bot dừng.** Dù bot dừng vì lỗi cấu hình, lỗi chưa lường
trước hay thiếu thư viện, và dù là `kiem_tra_cau_hinh.py` chạy xong, thông báo vẫn
nằm trên màn hình kèm dòng *"⏸ Chương trình đã dừng… nhấn Enter để đóng cửa sổ"*.
Đọc xong nhấn Enter mới đóng. Riêng khi đại ca **bấm Ctrl+C** thì cửa sổ đóng luôn,
không hỏi.

### Linux / macOS / Git Bash

| Việc | Lệnh |
|---|---|
| Xem danh sách bot | `./start_bot.sh` |
| Bật 1 bot cho mọi tài khoản | `./start_bot.sh hd_update_cho_va_khop` |
| Bật 1 bot cho riêng 1 tài khoản | `./start_bot.sh hd_order_multi kh_a` |
| Dừng 1 bot (mọi tài khoản) | `./stop_bot.sh hd_update_cho_va_khop` |
| Dừng 1 bot của 1 tài khoản | `./stop_bot.sh hd_order_multi kh_a` |
| Xem bot nào đang chạy | `./status.sh` |
| Xem màn hình 1 bot | `tail -f logs/hd_order_multi.log` |

### Ba quy tắc

- **Không bật chồng.** Bật trùng 1 bot cho cùng tài khoản = **đặt lệnh trùng**.
  Bot tự chặn và báo "ĐANG CHẠY".
- **Chọn 1 trong 2 cách cho mỗi bot**: hoặc chạy cho *mọi tài khoản*, hoặc chạy
  *riêng từng tài khoản* — đừng trộn. `start_bot.sh` chặn việc trộn.
- **Tắt hẳn 1 tài khoản** thì làm trên sheet tổng: để **Bật = N** rồi **đổi ô B1**.
  Mọi bot tự dừng tài khoản đó, không cần vào máy. Dừng lẻ bằng tay thì bot
  **không tự bật lại** cho tới lần khởi động sau.

---

## 2. THỨ TỰ BẬT NÊN THEO

| # | Bot | Bắt buộc? |
|---|---|---|
| 1 | `hd_update_cho_va_khop` | **Có** — không có nó thì **không có cắt lỗ** |
| 2 | `hd_order_multi` | **Có** — bot đặt lệnh |
| 3 | `hd_alert_possition_and_open_order` | Nên có — báo Telegram + dọn lệnh sót khi vị thế đóng |
| 4 | `hd_cancel_selective` | Nếu dùng tick J–M |
| 5 | `hd_cancel_orders_schedule` | Tuỳ — tự huỷ lệnh vào treo lâu |
| 6 | `hd_update_all` | Tuỳ — chỉ để xem số dư trên sheet |

**Lần đầu nên thử**: để ô **B2 = CHỜ** rồi mới bật `hd_order_multi` — bot chỉ đặt
SL/TP cho vị thế đang có, **không vào lệnh mới**. Thấy ổn mới đổi B2 sang LONG/SHORT.

---

## 3. TỪNG BOT

### 3.1 `hd_update_cho_va_khop` — nguồn cấp SL/TP 🔴 BẮT BUỘC

**Nhiệm vụ**: đọc vị thế và lệnh thật trên Binance, ghi lại tab **Chờ và khớp**.

| Đọc | Ghi |
|---|---|
| Binance: vị thế, lệnh chờ, lệnh SL/TP | `A2` giờ cập nhật · `A–I` trạng thái từng mã · `Q` giá hiện tại · `N/O/P` gợi ý (chỉ ô **trống**) |

- Mỗi mã 1 dòng: vị thế đang mở (**D = Y**), lệnh vào đang chờ (**D = N**), vị thế
  đã đóng còn sót lệnh (**D = ĐÓNG**).
- **Gợi ý SL/TP** vào N/O từ giá vào: LONG → N = giá vào × (1 − %SL), O = giá vào × (1 + %TP);
  SHORT ngược lại. **Không bao giờ đè** số người dùng đã sửa.
- Thứ tự dòng đổi (có vị thế mới) thì **J–P đi theo mã** — tick và giá SL/TP không
  rơi sang mã khác. Ô công thức đứng yên tại chỗ.

| Cấu hình | Ở đâu | Mặc định |
|---|---|---|
| `delay_cho_va_khop` — nhịp quét (giây) | config.ini | 600 |
| `fill_default_cho_va_khop` — có điền gợi ý N/O/P không | config.ini | true |
| %SL / %TP gợi ý | cột %SL/%TP trên **sheet tổng** (từng tài khoản) | 2 / 3 |
| `default_sl_rate_layer_1` / `default_tp_rate_layer_1` — %SL/%TP khi sheet tổng để trống | config.ini | 2 / 3 |
| `default_allow_order` — giá trị điền sẵn vào cột P | config.ini | N |

**Kiểm tra**: sau 1 vòng, ô `A2` có giờ mới, các mã đang có vị thế hiện với D = Y.

### 3.2 `hd_order_multi` — đặt lệnh

**Nhiệm vụ**: 2 pha mỗi vòng.

- **Pha A — lệnh VÀO**, theo ô **B2** tab ĐẶT LỆNH:

  | B2 | Bot làm gì |
  |---|---|
  | `LONG` | Quét dòng **4–53**, đặt lệnh MUA |
  | `SHORT` | Quét dòng **55–104**, đặt lệnh BÁN |
  | `CHỜ` | Không vào lệnh mới (vẫn đặt SL/TP) |
  | `STOP` | ⚠️ **Đóng TẤT CẢ vị thế** bằng lệnh thị trường + **huỷ TẤT CẢ lệnh** |
  | `XÓA CHỜ` | ⚠️ Huỷ **tất cả** lệnh chờ (kể cả SL/TP), giữ vị thế |
  | `XÓA VỊ THẾ` | ⚠️ Đóng **tất cả** vị thế bằng lệnh thị trường, giữ lệnh chờ |

  ⚠️ `STOP` / `XÓA …` **lặp lại mỗi vòng** chừng nào B2 còn giữ giá trị đó, và trong
  lúc đó bot **không đặt SL/TP**. Xong việc đổi B2 về `CHỜ` ngay.

  Mỗi mã chỉ vào **1 lần** (có vị thế rồi thì thôi) — trừ khi bật `allow_dca`.

- **Pha B — SL/TP**, theo tab **Chờ và khớp**: dòng có **D = Y** và **P = Y** thì đặt
  cắt lỗ theo giá **N** và chốt lời theo giá **O**. Đã có lệnh giống thì bỏ qua.

| Cấu hình | Mặc định | Ý nghĩa |
|---|---|---|
| `delay_vao_lenh` | 60 | Nhịp quét (giây) |
| `allow_dca` | false | true = cho rải thêm lệnh vào dù đã có vị thế (mỗi lệnh dùng trọn vốn cột H) |
| `exit_sl_close_position` | true | Cắt lỗ dùng closePosition → vị thế tăng vẫn được bảo vệ đủ |
| `exit_tp_resize` | true | Khối lượng vị thế đổi → đặt lại chốt lời cho khớp |
| `exit_resize_tolerance_pct` | 1.0 | Lệch quá ngần này % mới đặt lại |
| `dedup_price_tolerance_pct` | 0.02 | Hai lệnh chênh dưới ngần này % coi là trùng |
| `state_cache_ttl_sec` | 10 | Ô B2 đọc thật mỗi ngần này giây (chống lỗi 429) |
| `leg1_*` / `leg2_*` / `leg3_*` | xem config | Lệnh vào / cắt lỗ / chốt lời lấy ở cột nào, kiểu gì. **Không cần sửa** |
| `run_tele_command` | false | true = nhận lệnh `/stop` `/long`… qua Telegram (chỉ 1 máy nên bật) |

**Kiểm tra**: màn hình in `📌 Trạng thái: …` mỗi vòng; lệnh đặt được ghi vào
`logs/<tài khoản>/order.log` và báo Telegram.

### 3.3 `hd_alert_possition_and_open_order` — cảnh báo

**Nhiệm vụ**: mỗi vòng so danh sách vị thế với lần trước.

- Vị thế **mới mở** → Telegram *"✅ Đã Thêm Vị Thế"*.
- Vị thế **vừa đóng** → Telegram *"Đã Đóng Vị Thế | PNL ~"* (lãi/lỗ ước tính ở lần quét
  trước) rồi **huỷ mọi lệnh còn treo của mã đó** (SL/TP sót, lệnh vào chưa khớp).
  Không huỷ được sau 3 lần → báo *CẢNH BÁO NGHIÊM TRỌNG*.
- **Không đọc/ghi Google Sheet.**

| Cấu hình | Mặc định |
|---|---|
| `delay_calert_possition_and_open_order` — nhịp (giây) | 120 |
| `chat_id` / `bot_token` Telegram | config.ini, ghi đè được trên sheet tổng |

Lần chạy đầu chỉ ghi nhớ, **không báo** (tránh báo tràn mọi vị thế đang có).

### 3.4 `hd_cancel_selective` — xoá lệnh theo tick J–M

**Nhiệm vụ**: đọc tick ở cột **J–M** tab Chờ và khớp, xoá lệnh tương ứng của mã
đó, **tự bỏ tick**, cập nhật lại G/H/I, báo Telegram.

| Tick cột | Xoá |
|---|---|
| **J** ENTRY | Lệnh **vào** còn treo — **không đụng** SL/TP |
| **K** SL/TP | Cả cắt lỗ và chốt lời (giữ lệnh vào) |
| **L** LỆNH SÓT | Chỉ khi còn sót **một** phía (chỉ SL hoặc chỉ TP) |
| **M** LỆNH NGƯỢC | **Mọi** lệnh của mã — dùng khi D = ĐÓNG |

Giá trị tick được nhận: ô checkbox (TRUE), `Y`, `X`, `1`, `✓`. N / FALSE / trống = không.

⚠️ Xoá SL/TP (K/M) mà **P = Y** thì `hd_order_multi` sẽ **đặt lại** ở vòng sau.
Muốn bỏ hẳn: đổi P = N trước rồi mới tick.

| Cấu hình | Mặc định |
|---|---|
| `cancel_selective_seconds` — bao lâu đọc tick 1 lần (giây, tối thiểu 15) | 60 |

### 3.5 `hd_cancel_orders_schedule` — huỷ lệnh vào treo lâu

**Nhiệm vụ**: định kỳ lấy danh sách mã ở cột **A** tab Chờ và khớp, huỷ **lệnh vào**
đã treo quá lâu. **Không bao giờ huỷ SL/TP** (trừ khi bật `cancel_all_orders`).

| Cấu hình | Mặc định | Ý nghĩa |
|---|---|---|
| `cancel_orders_minutes` | 60 | Bao lâu quét 1 lần (**phút**) |
| `cancel_order_after_minutes` | 30 | Chỉ huỷ lệnh vào treo quá ngần này phút |
| `cancel_all_orders` | false | ⚠️ true = huỷ **tất cả**, kể cả SL/TP → vị thế mất bảo vệ |

Không muốn lệnh chờ bị tự huỷ (vd lệnh limit đặt xa, chờ lâu) thì **đừng bật** bot này.

### 3.6 `hd_update_all` — số dư

**Nhiệm vụ**: ghi số dư vào tab **ĐẶT LỆNH**, vùng **J1:M2**. 1 lượt gọi Binance +
1 lượt ghi Google mỗi vòng.

| | J | K | L | M |
|---|---|---|---|---|
| **1** | Số dư ví | Ký quỹ | Lãi/lỗ mở | Cập nhật lúc |
| **2** | 12345.67 | 2000.50 | -50.25 | 05/09/2026 14:43:38 |

| Cấu hình | Mặc định |
|---|---|
| `delay_update_all` — nhịp (giây) | 120 |
| `balance_cell` — cột bắt đầu | J |

---

## 4. TAB "ĐẶT LỆNH" — ô nào bot đọc

| Ô / cột | Nội dung | Ai điền |
|---|---|---|
| `B2` | Trạng thái (mục 3.2) | Người dùng |
| `D1` | Tỷ lệ vốn (%) | Người dùng |
| `D2` | Mức vốn / lệnh mặc định (USDT) | Người dùng |
| `E2` | Vốn tổng (USDT) | Người dùng |
| `J1:M2` | Số dư | **Bot** (`hd_update_all`) |
| Dòng **4–53** | Mã khi B2 = LONG | Người dùng |
| Dòng **55–104** | Mã khi B2 = SHORT | Người dùng |

Từng dòng mã:

| Cột | Nội dung |
|---|---|
| **A** | Mã (`BTC`, `BTC/USDT`…) |
| **B** | Đòn bẩy. `N` / `0` / trống = **bỏ qua dòng** |
| **D** | Giá vào |
| **F** | Kiểu vào: `1` limit · `2` market · `3` stop market · `4` stop limit · `5` trailing |
| **G** | Phụ: kiểu 4 = giá limit · kiểu 5 = callback % |
| **H** | Mức vốn (USDT). Trống → D1 × E2 (tối thiểu 10) → D2 |

- Kiểu 1 (limit): LONG phải **thấp hơn** giá hiện tại, SHORT phải **cao hơn** — sai
  thì bot bỏ qua dòng. Kiểu 2 (market) không cần D.
- Vốn dưới 10 USDT hoặc giá trị lệnh dưới 5 USDT → bỏ qua.
- Cột **C** ("Callback (lệnh 5)") và **E** **không được đọc** — callback lấy ở **G**.
  Ô **B1** ("Số mã đạt") bot cũng không đọc.

---

## 5. TAB "CHỜ VÀ KHỚP" — ô nào bot đọc/ghi

| Cột | Nội dung | Ai điền |
|---|---|---|
| `A2` | Giờ cập nhật | Bot |
| **A** | Mã | Bot |
| **B** | LONG / SHORT | Bot |
| **C** | Chờ khớp (Y/N) | Bot |
| **D** | `Y` đã khớp · `N` đang chờ · `ĐÓNG` đã đóng còn sót lệnh | Bot |
| **E / F** | Giá vào / đòn bẩy | Bot |
| **G / H** | Có SL / có TP (Y/N) | Bot |
| **I** | Số lệnh đang treo | Bot |
| **J–M** | Tick xoá lệnh (mục 3.4) | Người dùng |
| **N** | Giá **cắt lỗ** | Bot gợi ý khi trống, người dùng sửa được |
| **O** | Giá **chốt lời** | Bot gợi ý khi trống, người dùng sửa được |
| **P** | Cho phép đặt SL/TP (`Y`/`N`) | Người dùng (bot điền sẵn theo `default_allow_order`) |
| **Q** | Giá hiện tại | Bot |

⚠️ **Tiêu đề trên sheet đang lệch với cách bot chạy** (tiêu đề của bot cũ):

| Cột | Tiêu đề hiện tại | Bot dùng làm | Nên đổi tiêu đề thành |
|---|---|---|---|
| N | STOP LIMIT | Giá **cắt lỗ** (stop market, đóng toàn bộ vị thế) | CẮT LỖ |
| O | TRAILING STOP | Giá **chốt lời** (lệnh limit) | CHỐT LỜI |

Dòng 1 (`E1`, `I1`, các số `0.3 / 0.6 / 1` ở `J1:N1`) **không bot nào đọc** — là
cấu hình của bot cũ, để hay xoá đều được.

---

## 6. THAM SỐ `config.ini` → BOT NÀO DÙNG

| Tham số | Bot |
|---|---|
| `bot_id`, `config_spreadsheet_id`, `config_reload_seconds` | Tất cả |
| `bot_token`, `chat_id` | Tất cả (gửi Telegram) |
| `tab_dat_lenh` | Tên tab ĐẶT LỆNH trên sheet |
| `state_cache_ttl_sec`, `account_start_stagger_sec` | Chống lỗi 429 — tất cả |
| `delay_vao_lenh`, `allow_dca`, `exit_*`, `dedup_*`, `leg*`, `multi_leg_count`, `run_tele_command` | `hd_order_multi` |
| `delay_cho_va_khop`, `fill_default_cho_va_khop`, `default_sl/tp_rate_layer_1`, `default_allow_order` | `hd_update_cho_va_khop` |
| `delay_calert_possition_and_open_order` | `hd_alert_possition_and_open_order` |
| `cancel_selective_seconds` | `hd_cancel_selective` |
| `cancel_orders_minutes`, `cancel_order_after_minutes`, `cancel_all_orders` | `hd_cancel_orders_schedule` |
| `delay_update_all`, `balance_cell` | `hd_update_all` |

Sửa `config.ini` thì phải **tắt rồi bật lại** bot liên quan. Sửa trên **sheet tổng**
thì chỉ cần **đổi ô B1** — bot tự nạp lại.
