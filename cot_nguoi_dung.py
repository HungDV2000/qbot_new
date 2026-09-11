"""
Giữ cột NGƯỜI DÙNG (J–P) của tab "Chờ và khớp" đi THEO MÃ khi dòng xê dịch.

Vì sao cần:
    hd_update_cho_va_khop xoá rồi ghi lại A–I mỗi vòng. Có vị thế mới mở/đóng
    thì thứ tự dòng đổi: BTC đang ở dòng 5 có thể nhảy xuống dòng 6. Nhưng J–P
    (tick xoá lệnh, giá SL/TP, cờ cho phép) do người dùng điền thì ĐỨNG YÊN
    theo số dòng → tick "xoá lệnh" của BTC rơi sang mã khác, giá SL của BTC
    bị áp cho ETH.

    Hàm ở đây nhận ảnh CŨ (A–P, đọc ngay trước khi xoá) và danh sách dòng MỚI
    (A–I), trả khối J–P đã dời theo đúng mã.

Quy tắc:
    • Khoá mỗi dòng = (mã, chiều, lần xuất hiện thứ mấy) — cùng mã 2 dòng vẫn phân biệt.
    • Ô CÔNG THỨC (bắt đầu bằng "=") KHÔNG dời: công thức kiểu =E5*0.98 tham
      chiếu theo dòng, dời đi là trỏ sai mã. Công thức đứng yên tại chỗ.
    • Mã biến mất khỏi bảng → J–P của nó bị xoá theo (không để tick mồ côi
      rơi vào mã khác đổ vào dòng đó sau này).
    • Dòng CŨ không có mã (cột A trống — vd vòng trước ghi A–I lỗi giữa chừng)
      thì giữ nguyên J–P tại chỗ như trước đây, KHÔNG xoá số người dùng.
    • N/O/P còn trống thì điền gợi ý (nếu bật fill_default_cho_va_khop).
"""

# Cột J..P = chỉ số 9..15 trong dòng A..P
COT_DAU = 9
SO_COT = 7                  # J K L M N O P
VI_TRI_GOI_Y = 4            # N nằm ở vị trí thứ 4 trong khối J–P


def la_cong_thuc(v):
    return isinstance(v, str) and v.strip().startswith("=")


def _o(dong, j):
    return dong[j] if j < len(dong) else ""


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


def can_chinh(cu, moi_ai, goi_y=None, dien_goi_y=True):
    """
    cu      : dòng A–P đang có trên sheet (đọc TRƯỚC khi xoá A–I).
    moi_ai  : dòng A–I bot sắp ghi.
    goi_y   : [[SL, TP, cho-phép], ...] song song với moi_ai (có thể None).

    Trả (khoi, co_doi, so_doi_cho):
        khoi       — các dòng J–P để ghi từ dòng 4 (đã đệm trống tới hết ảnh cũ)
        co_doi     — False nếu khối y hệt cái đang có → khỏi ghi
        so_doi_cho — số dòng có dữ liệu người dùng bị dời sang dòng khác
    """
    cu = cu or []
    goi_y = goi_y or []
    khoa_cu = khoa_cac_dong(cu)
    khoa_moi = khoa_cac_dong(moi_ai)

    theo_khoa = {k: i for i, k in enumerate(khoa_cu) if k is not None}
    # Khoá đã được một dòng MỚI nhận → dòng cũ đó không còn là "mồ côi"
    da_nhan = {k for k in khoa_moi if k is not None and k in theo_khoa}

    so_dong = max(len(cu), len(moi_ai))
    khoi, so_doi_cho = [], 0
    for i in range(so_dong):
        dong_cu_tai_cho = cu[i] if i < len(cu) else []
        k = khoa_moi[i] if i < len(moi_ai) else None
        nguon_i = theo_khoa.get(k) if k is not None else None
        if nguon_i is None and i < len(cu) and khoa_cu[i] is None:
            nguon_i = i                 # dòng cũ không có mã → giữ tại chỗ
        nguon = cu[nguon_i] if nguon_i is not None else []
        if nguon_i is not None and nguon_i != i:
            if any(not _rong(_o(nguon, COT_DAU + j)) and not la_cong_thuc(_o(nguon, COT_DAU + j))
                   for j in range(SO_COT)):
                so_doi_cho += 1

        dong = []
        for j in range(SO_COT):
            tai_cho = _o(dong_cu_tai_cho, COT_DAU + j)
            if la_cong_thuc(tai_cho):
                dong.append(tai_cho)            # công thức đứng yên
                continue
            v = _o(nguon, COT_DAU + j)
            if la_cong_thuc(v):
                v = ""                          # công thức không dời theo mã
            if _rong(v) and dien_goi_y and j >= VI_TRI_GOI_Y and i < len(goi_y):
                g = goi_y[i]
                gj = j - VI_TRI_GOI_Y
                v = g[gj] if gj < len(g) else ""
            dong.append("" if v is None else v)
        khoi.append(dong)

    co_doi = any(
        str(khoi[i][j]).strip() != str(_o(cu[i] if i < len(cu) else [], COT_DAU + j)).strip()
        for i in range(len(khoi)) for j in range(SO_COT)
    )
    return khoi, co_doi, so_doi_cho
