"""
Tab "Chờ và khớp": bot CHỈ GHI A–I, cột NGƯỜI DÙNG (J–P) bot KHÔNG BAO GIỜ ghi.

Vì sao (khách 07–08/10/2026):
    Trước đây bot dựng lại cả bảng mỗi vòng theo thứ tự (vị thế mở → lệnh chờ → ĐÓNG)
    rồi ghi lại cả khối J4:P để J–P "đi theo mã". Hai lỗi:
      • Mã TẠM VẮNG một vòng (Binance lỗi mạng/429 trả danh sách rỗng, mã chờ khớp có
        2 lệnh…) → J–P của nó bị xoá; vòng sau quay lại thì nhận SỐ GỢI Ý đè lên SL/TP
        khách đã gõ → hd_order_multi huỷ SL/TP của khách, đặt lại theo giá mặc định.
      • Ghi lại cả khối J4:P đè lên ô do IMPORTRANGE / ARRAYFORMULA tràn xuống
        (đọc dạng FORMULA thì ô tràn trông như số thường) → công thức gốc #REF!.

Cách mới — GIỮ CHỖ DÒNG THEO MÃ (xep_dong):
    • Mã đã có dòng → giữ ĐÚNG dòng đó, chỉ cập nhật A–I. J–P đứng yên vẫn đúng mã.
    • Mã mới → vào dòng trống mà J–P KHÔNG còn số người dùng gõ (ô công thức thì được,
      vì công thức tính theo dòng); không có thì thêm xuống cuối. Mã mới không bao giờ
      nhận SL/tick của mã cũ (lỗi thật 09/2026: SL 5008.78/5264.33 rơi sang ETH).
    • Mã biến mất → xoá trống A–I của dòng đó, J–P để nguyên cho người dùng tự dọn.
    • Mã bot không xử lý được vòng này (giu_ma) → giữ nguyên A–I cũ của nó.

SL/TP mặc định (dien_mac_dinh_sltp):
    Trước đây bot ghi gợi ý vào N/O/P. Nay hd_order_multi tự tính TRONG BỘ NHỚ khi ô
    trống — cùng công thức, không ghi lên sheet. Ô người dùng gõ / đặt công thức thì
    dùng đúng giá trị đó.
"""

# Cột J..P = chỉ số 9..15 trong dòng A..P
COT_DAU = 9
SO_COT = 7                  # J K L M N O P
COT_SL, COT_TP, COT_P = 13, 14, 15   # N, O, P
SO_COT_BOT = 9              # A..I — vùng DUY NHẤT bot được ghi


def la_cong_thuc(v):
    return isinstance(v, str) and v.strip().startswith("=")


def _o(dong, j):
    return dong[j] if dong is not None and j < len(dong) else ""


def _rong(v):
    return v is None or str(v).strip() == ""


def khoa_cac_dong(rows):
    """[(mã, chiều, lần_thứ) | None] cho từng dòng."""
    dem, khoa = {}, []
    for d in rows:
        ma = str(_o(d, 0)).strip().upper() if d else ""
        if not ma:
            khoa.append(None)
            continue
        chieu = str(_o(d, 1)).strip().upper()
        k = (ma, chieu)
        dem[k] = dem.get(k, 0) + 1
        khoa.append((ma, chieu, dem[k]))
    return khoa


def jp_co_du_lieu(dong):
    """J–P của dòng còn số/chữ người dùng GÕ (bỏ qua ô trống và ô công thức)."""
    return any(not _rong(_o(dong, COT_DAU + j)) and not la_cong_thuc(_o(dong, COT_DAU + j))
               for j in range(SO_COT))


def xep_dong(cu, moi_ai, giu_ma=()):
    """
    cu     : dòng A–P đang có trên sheet (từ dòng 4, đọc dạng FORMULA).
    moi_ai : dòng A–I bot vừa lấy từ Binance (thứ tự tuỳ ý).
    giu_ma : mã (A, viết hoa) bot lỗi khi xử lý vòng này → giữ nguyên A–I cũ.

    Trả các dòng A–I để ghi từ dòng 4 — dòng i ứng với dòng sheet 4+i, dài ít nhất
    bằng bảng cũ (dòng thừa = ô trống, thay cho lệnh xoá).
    """
    cu = cu or []
    giu_ma = {str(m).strip().upper() for m in giu_ma}
    khoa_cu = khoa_cac_dong(cu)
    khoa_moi = khoa_cac_dong(moi_ai)
    vi_tri_cu = {k: i for i, k in enumerate(khoa_cu) if k is not None}

    ra = [None] * len(cu)
    chua_co_cho = []
    for j, k in enumerate(khoa_moi):
        i = vi_tri_cu.get(k) if k is not None else None
        if i is not None and ra[i] is None:
            ra[i] = moi_ai[j]
        else:
            chua_co_cho.append(moi_ai[j])

    # Dòng cũ không còn mã nào nhận: mã đang lỗi → giữ A–I cũ; còn lại → trống
    for i, d in enumerate(cu):
        if ra[i] is None and str(_o(d, 0)).strip().upper() in giu_ma:
            ra[i] = list(d[:SO_COT_BOT])

    # Mã mới: dòng trống (không mã, không bị giữ) mà J–P không còn số người dùng
    for dong in chua_co_cho:
        cho = next((i for i in range(len(ra)) if ra[i] is None and not jp_co_du_lieu(cu[i])), None)
        if cho is None:
            ra.append(dong)
        else:
            ra[cho] = dong

    return [_du_cot(r) for r in ra]


def _du_cot(r):
    r = list(r or [])[:SO_COT_BOT]
    return ["" if v is None else v for v in r] + [""] * (SO_COT_BOT - len(r))


# ── SL/TP mặc định khi N/O/P trống (hd_order_multi dùng, KHÔNG ghi lên sheet) ──

def lam_tron_gia(gia, gia_vao):
    """Làm tròn theo độ lớn giá vào (như hiển thị trên app)."""
    if gia is None or not gia_vao or gia_vao <= 0:
        return gia
    if gia_vao < 1:
        return round(gia, 6)
    if gia_vao < 100:
        return round(gia, 4)
    if gia_vao < 10000:
        return round(gia, 2)
    return round(gia, 1)


def goi_y_sltp(chieu, gia_vao, ty_le_sl, ty_le_tp):
    """(giá SL, giá TP) mặc định từ giá vào và % — None nếu không tính được."""
    try:
        gia_vao = float(gia_vao)
    except (TypeError, ValueError):
        return None, None
    if gia_vao <= 0:
        return None, None
    la_long = str(chieu).strip().upper() == 'LONG'
    sl = gia_vao * (1 - ty_le_sl / 100.0) if la_long else gia_vao * (1 + ty_le_sl / 100.0)
    tp = gia_vao * (1 + ty_le_tp / 100.0) if la_long else gia_vao * (1 - ty_le_tp / 100.0)
    return (lam_tron_gia(sl, gia_vao) if sl > 0 else None,
            lam_tron_gia(tp, gia_vao) if tp > 0 else None)


def dien_mac_dinh_sltp(dong, ty_le_sl, ty_le_tp, cho_phep):
    """
    Bản SAO của dòng A–P: N/O trống → SL/TP mặc định, P trống → cho_phep.
    Chỉ với vị thế ĐANG MỞ (D = 'Y') có giá vào hợp lệ — dòng khác giữ nguyên.
    Ô đã có giá trị (người dùng gõ hoặc công thức) KHÔNG bao giờ bị thay.
    """
    d = list(dong or [])
    if str(_o(d, 3)).strip().upper() != 'Y':
        return d
    sl, tp = goi_y_sltp(_o(d, 1), _o(d, 4), ty_le_sl, ty_le_tp)
    if sl is None:
        return d
    d += [""] * (COT_P + 1 - len(d))
    for j, v in ((COT_SL, sl), (COT_TP, tp), (COT_P, cho_phep)):
        if _rong(d[j]) and not _rong(v):
            d[j] = v
    return d
