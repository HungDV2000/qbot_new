# -*- coding: utf-8 -*-
"""
symbol_filter — chọn danh sách mã cần lấy dữ liệu.

HAI CHẾ ĐỘ (khai bằng `symbol_mode` trong [global]):

    symbol_mode = list     → (MẶC ĐỊNH) CHỈ lấy đúng các mã khai trong `symbol_list`.
                             Không khai symbol_list thì dùng 6 mã mặc định:
                             BTC, ETH, SOL, XRP, BNB, DOGE
    symbol_mode = all      → top biến động 24h (top_count), vẫn tôn trọng
                             whitelist ở tab Google Sheet "list".

QUY ĐỊNH ĐẶT TÊN MÃ (áp dụng cho `symbol_list`):

    • KHÔNG phân biệt hoa/thường:  btc = BTC = Btc
    • Nhận 4 cách viết, tự quy về một dạng chuẩn:
          BTC              → BTC/USDT:USDT
          BTCUSDT          → BTC/USDT:USDT
          BTC/USDT         → BTC/USDT:USDT
          BTC/USDT:USDT    → giữ nguyên
    • Chỉ hỗ trợ cặp USDT (sàn Futures USDT-M).
    • Trùng nhau thì giữ lần xuất hiện ĐẦU, bỏ các lần sau.
      Ví dụ "BTC, btc, BTCUSDT" → còn đúng 1 mã.
    • Mã sai/không có trên sàn thì BÁO RÕ TÊN, không bỏ im lặng.
"""

MODE_ALL = 'all'
MODE_LIST = 'list'

# MẶC ĐỊNH khi config KHÔNG khai gì: chỉ lấy 6 mã dưới đây.
# (Trước đây mặc định là 'all' = 100 mã theo top biến động.)
MAC_DINH_MODE = MODE_LIST
MAC_DINH_SYMBOL_LIST = "BTC, ETH, SOL, XRP, BNB, DOGE"
_HOP_LE = (MODE_ALL, MODE_LIST)


def normalize_symbol(sym) -> str:
    """Quy mọi cách viết về dạng chuẩn CCXT: 'BTC' → 'BTC/USDT:USDT'."""
    sym = str(sym).strip().upper()
    if not sym:
        return ""
    if sym.endswith(":USDT"):
        return sym
    if sym.endswith("/USDT"):
        return f"{sym}:USDT"
    if "/" not in sym and sym.endswith("USDT"):
        return f"{sym[:-4]}/USDT:USDT"
    if "/" not in sym:
        return f"{sym}/USDT:USDT"
    return sym


def parse_symbol_list(raw):
    """
    Đọc chuỗi "BTC, ETH, btc" → (danh_sách_chuẩn, danh_sách_bị_trùng).

    Giữ nguyên thứ tự khai. Trùng (sau khi chuẩn hoá) thì giữ cái đầu tiên.
    """
    ket_qua, da_co, trung = [], set(), []
    for phan in str(raw or "").replace("\n", ",").split(","):
        phan = phan.strip()
        if not phan:
            continue
        chuan = normalize_symbol(phan)
        if not chuan:
            continue
        if chuan in da_co:
            trung.append((phan, chuan))
            continue
        da_co.add(chuan)
        ket_qua.append(chuan)
    return ket_qua, trung


def read_mode(config):
    """Đọc symbol_mode từ [global]; giá trị lạ thì báo lỗi thay vì đoán."""
    try:
        gt = config.get('global', 'symbol_mode', fallback=MAC_DINH_MODE)
    except Exception:
        gt = MAC_DINH_MODE
    gt = str(gt or "").strip().lower() or MAC_DINH_MODE
    if gt not in _HOP_LE:
        raise SystemExit(
            f"❌ symbol_mode = '{gt}' không hợp lệ. Chỉ nhận: "
            f"{' hoặc '.join(_HOP_LE)}."
        )
    return gt


def read_symbol_list(config):
    """Đọc symbol_list từ [global] → (danh_sách_chuẩn, danh_sách_trùng)."""
    try:
        raw = config.get('global', 'symbol_list', fallback=MAC_DINH_SYMBOL_LIST)
    except Exception:
        raw = MAC_DINH_SYMBOL_LIST
    # Khai khoá nhưng để TRỐNG cũng dùng danh sách mặc định, tránh việc
    # mode=list + list rỗng làm hd_update_all dừng hẳn.
    if not str(raw).strip():
        raw = MAC_DINH_SYMBOL_LIST
    return parse_symbol_list(raw)


def loc_theo_danh_sach(khai_bao, co_tren_san, bo_qua=()):
    """
    Đối chiếu danh sách khai với các mã sàn thực sự có.

    khai_bao     : list mã đã chuẩn hoá (thứ tự người dùng khai)
    co_tren_san  : tập/hoặc dict các mã sàn đang có (dạng chuẩn)
    bo_qua       : các mã đã hiển thị ở chỗ khác (vd mã dẫn đầu) → loại khỏi kết quả

    Trả về (dùng_được, không_có_trên_sàn, đã_bỏ_vì_trùng_mã_dẫn_đầu)
    """
    bo_qua = {normalize_symbol(s) for s in bo_qua}
    dung, thieu, trung_dan_dau = [], [], []
    for s in khai_bao:
        if s not in co_tren_san:
            thieu.append(s)
            continue
        if s in bo_qua:
            trung_dan_dau.append(s)
            continue
        dung.append(s)
    return dung, thieu, trung_dan_dau
