"""
Nhận diện lệnh: VÀO / CẮT LỖ (SL) / CHỐT LỜI (TP) — dùng chung cho mọi bot.

Khớp cách hd_order_multi đặt lệnh:
  • SL = STOP_MARKET với closePosition (có khi KHÔNG mang cờ reduceOnly)
  • TP = LIMIT reduceOnly (hoặc trailing / take profit)
Bản cũ chỉ coi TRAILING/TAKE_PROFIT là TP và chỉ xét cờ reduceOnly → cột
"Có TP" luôn N, và tick J (xoá lệnh vào) xoá nhầm cả cắt lỗ.
"""


def _dung(v):
    return v is True or str(v).strip().lower() == 'true'


def _info(o):
    i = o.get('info')
    return i if isinstance(i, dict) else {}


def la_lenh_dong(o):
    """Lệnh ĐÓNG vị thế (SL/TP): reduceOnly HOẶC closePosition, ở gốc hay trong info."""
    for src in (o, _info(o)):
        for k in ('reduceOnly', 'reduce_only', 'closePosition'):
            if _dung(src.get(k)):
                return True
    return False


def kieu(o):
    """Kiểu lệnh viết hoa (LIMIT, STOP_MARKET, TRAILING_STOP_MARKET…)."""
    i = _info(o)
    return str(o.get('orderType') or i.get('orderType') or i.get('origType')
               or o.get('type') or i.get('type') or '').upper()


def mo_ta(o, la_algo=False):
    """Một dòng tóm tắt để soi log: bot xếp lệnh này vào loại nào và VÌ SAO."""
    i = _info(o)
    ro = _dung(o.get('reduceOnly')) or _dung(i.get('reduceOnly'))
    cp = _dung(o.get('closePosition')) or _dung(i.get('closePosition'))
    cb = o.get('callbackRate') or i.get('callbackRate') or 0
    ten = o.get('algoId') or o.get('id') or '?'
    return (f"{phan_loai(o, la_algo)} | kiểu={kieu(o) or '?'} | reduceOnly={ro} "
            f"closePosition={cp} callbackRate={cb} | #{ten}")


def phan_loai(o, la_algo=False):
    """'ENTRY' | 'SL' | 'TP' | 'UNKNOWN' — cho cả lệnh thường lẫn algo."""
    if not la_lenh_dong(o):
        return 'ENTRY'
    t = kieu(o)
    i = _info(o)
    try:
        cb = float(o.get('callbackRate') or i.get('callbackRate') or o.get('priceRate') or 0)
    except (TypeError, ValueError):
        cb = 0.0
    if cb > 0 or 'TRAILING' in t or 'TAKE_PROFIT' in t:
        return 'TP'
    if 'STOP' in t:
        return 'SL'
    if t == 'LIMIT':
        return 'TP'           # hd_order_multi đặt chốt lời bằng LIMIT reduceOnly
    if la_algo and t in ('', 'CONDITIONAL'):
        return 'SL'           # algo điều kiện không trailing = cắt lỗ
    return 'UNKNOWN'
