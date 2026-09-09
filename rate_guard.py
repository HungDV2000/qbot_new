# -*- coding: utf-8 -*-
"""
rate_guard — chống lỗi 429 (vượt hạn mức Google Sheets).

VẤN ĐỀ:
    Google chỉ cho 60 lượt ĐỌC/phút, tính CHUNG cho MỌI tài khoản dùng cùng
    một credential. Các bot đặt lệnh đọc lại ô trạng thái B2 ở MỖI DÒNG mã,
    nên 50 mã = 50 lượt/vòng/tài khoản. Chạy 3 tài khoản là ~186 lượt/phút,
    vượt hơn 3 lần hạn mức → Google trả về 429.

CÁCH XỬ LÝ:
    Bọc hàm đọc B2 bằng một lớp nhớ tạm (cache) có hạn dùng vài giây.
    Trong 1 vòng quét, B2 chỉ đọc thật vài lần thay vì 50 lần.

AN TOÀN:
    - Người dùng bấm DỪNG trên sheet VẪN có hiệu lực, chậm nhất sau đúng
      `ttl` giây (mặc định 10s) — vẫn kịp trước khi vào lệnh tiếp.
    - Các mốc quan trọng (đầu vòng, chốt cuối vòng) gọi force=True để đọc
      thật, không dùng cache.
"""
import time
from datetime import datetime

DEFAULT_TTL = 10.0
MAX_TTL = 30.0          # trần an toàn: TTL quá dài thì phản ứng DỪNG quá chậm


def read_ttl(config, key='state_cache_ttl_sec', default=DEFAULT_TTL, max_ttl=None):
    """
    Đọc TTL từ [global] của config, kẹp trong khoảng an toàn [0, max_ttl].

    Trần mặc định là MAX_TTL (30s) — dùng cho ô trạng thái B2, vì TTL quá dài
    sẽ khiến bot phản ứng chậm khi người dùng bấm DỪNG.
    Dữ liệu ít đổi (ví dụ cột mã) có thể truyền max_ttl lớn hơn.
    """
    limit = MAX_TTL if max_ttl is None else float(max_ttl)
    try:
        ttl = config.getfloat('global', key, fallback=default)
    except Exception:
        ttl = default
    try:
        ttl = float(ttl)
    except (TypeError, ValueError):
        ttl = default
    return max(0.0, min(ttl, limit))


def new_box():
    """Tạo chỗ nhớ tạm cho một bot (mỗi bot 1 box riêng)."""
    return {'value': None, 'ts': 0.0}


def clear(box):
    box['value'] = None
    box['ts'] = 0.0


def cached_state(box, fetch, ttl, force=False):
    """
    Đọc trạng thái qua lớp nhớ tạm.

        _box = rate_guard.new_box()
        def get_current_state(force=False):
            return rate_guard.cached_state(_box, _fetch_current_state,
                                           STATE_CACHE_TTL, force)

    `fetch` và `ttl` được truyền vào MỖI LẦN GỌI (không đóng băng trong closure)
    nên test có thể thay thế được, và đổi TTL lúc chạy vẫn ăn ngay.
    `fetch` phải trả về (giá_trị, thời_điểm) giống hàm gốc.
    """
    now = time.time()
    if (not force) and box['value'] is not None and (now - box['ts']) < ttl:
        return box['value'], datetime.fromtimestamp(box['ts'])
    value, stamp = fetch()
    box['value'] = value
    box['ts'] = time.time()
    return value, stamp
