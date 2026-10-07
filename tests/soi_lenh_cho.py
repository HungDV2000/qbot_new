# -*- coding: utf-8 -*-
"""
SOI LỆNH CHỜ — bot báo "lệnh vào cũ còn treo" mà trên app không thấy?
Script này in ĐÚNG những gì bot nhìn thấy cho 1 mã, và lệnh nào bot coi là "lệnh vào".

  ✅ CHỈ ĐỌC — không đặt, không huỷ lệnh nào.
  Chạy trên máy có IP được phép dùng key (thường là VPS):

      python tests/soi_lenh_cho.py <tên_tài_khoản> <mã>
      python tests/soi_lenh_cho.py kh_a BTCDOM

  Tài khoản 'default' (không khai accounts) thì gõ: python tests/soi_lenh_cho.py default BTCDOM
"""
import os
import sys
import time
from datetime import datetime

if len(sys.argv) < 3:
    raise SystemExit(__doc__)
_tk, _ma = sys.argv[1].strip(), sys.argv[2].strip()

GOC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(GOC)
sys.path.insert(0, GOC)
if _tk != 'default':
    os.environ['QBOT_ACCOUNT'] = _tk
os.environ['QBOT_NO_LOCK'] = '1'          # không giành khoá của bot đang chạy
sys.argv = [os.path.join(GOC, 'hd_order_multi.py')]   # nạp cấu hình như bot thật

import hd_order_multi as M  # noqa: E402  (dùng ĐÚNG hàm của bot)
from binance_futures_direct import (  # noqa: E402
    clean_futures_symbol, futures_signed_request, normalize_algo_orders_response)


def _gio(ms):
    try:
        return datetime.fromtimestamp(float(ms) / 1000).strftime('%d/%m %H:%M:%S')
    except (TypeError, ValueError):
        return '?'


ok, loi, symbol = M.is_symbol_tradeable(_ma)
if not ok:
    raise SystemExit(f"❌ Mã {_ma}: {loi}")
ma_api = clean_futures_symbol(symbol)
print("=" * 78)
print(f"Tài khoản: {M.cst.account_name} · key ...{str(M.cst.key_binance)[-6:]} · mã {symbol} ({ma_api})")
print(f"Vị thế hiện tại: {M.get_position_amt(symbol)}")
print("=" * 78)

print("\n① Lệnh THƯỜNG đang mở (fetch_open_orders — tab 'Lệnh mở' trên app):")
for o in M.exchange.fetch_open_orders(symbol):
    i = o.get('info') or {}
    print(f"   id={o.get('id')} {i.get('origType') or o.get('type')} {o.get('side')} "
          f"giá={i.get('price')} stop={i.get('stopPrice')} KL={i.get('origQty')} "
          f"reduceOnly={i.get('reduceOnly')} closePosition={i.get('closePosition')} "
          f"tạo {_gio(i.get('time') or o.get('timestamp'))}")

print("\n② Lệnh ĐIỀU KIỆN đang mở (openAlgoOrders — stop/trailing/cắt lỗ):")
mo = normalize_algo_orders_response(
    futures_signed_request('GET', '/fapi/v1/openAlgoOrders', {'symbol': ma_api}), ma_api) or []
id_mo = {str(a.get('algoId')) for a in mo}
for a in mo:
    print(f"   algoId={a.get('algoId')} {a.get('orderType')} {a.get('side')} "
          f"kích hoạt={a.get('activatePrice') or a.get('triggerPrice')} KL={a.get('quantity')} "
          f"reduceOnly={a.get('reduceOnly')} closePosition={a.get('closePosition')} "
          f"trạng thái={a.get('algoStatus')} tạo {_gio(a.get('createTime'))}")

print("\n③ Lịch sử lệnh điều kiện 24h (allAlgoOrders — bot cũng GỘP vào để chống trùng):")
ls = normalize_algo_orders_response(futures_signed_request(
    'GET', '/fapi/v1/allAlgoOrders',
    {'symbol': ma_api, 'startTime': int((time.time() - 86400) * 1000), 'limit': 500}), ma_api) or []
for a in ls:
    canh = ''
    if str(a.get('algoStatus', '')).upper() == 'NEW' and str(a.get('algoId')) not in id_mo:
        canh = '   ⚠️ LỊCH SỬ ghi NEW nhưng KHÔNG có trong danh sách đang mở'
    print(f"   algoId={a.get('algoId')} {a.get('orderType')} {a.get('side')} "
          f"kích hoạt={a.get('activatePrice') or a.get('triggerPrice')} "
          f"trạng thái={a.get('algoStatus')} tạo {_gio(a.get('createTime'))} "
          f"cập nhật {_gio(a.get('updateTime'))}{canh}")

print("\n④ KẾT LUẬN — bot (build_symbol_snapshot) coi các lệnh sau là LỆNH VÀO đang treo:")
snap, algo_ok = M.build_symbol_snapshot(symbol, True)
vao = M.lenh_vao_dang_cho(snap)
if not algo_ok:
    print("   ⚠️ Không đọc được Algo API — bot sẽ không vào lệnh mã này lượt đó")
if not vao:
    print("   (không có) → lúc này bot KHÔNG còn báo 'lệnh vào cũ còn treo' cho mã này")
for s_ in vao:
    nguon = 'THƯỜNG (tab Lệnh mở)'
    if s_.get('algo'):
        nguon = ('ĐIỀU KIỆN (đang mở)' if str(s_.get('id')) in id_mo
                 else '🔴 CHỈ CÓ TRONG LỊCH SỬ — lệnh "ma", app không có')
    print(f"   id={s_.get('id')} {s_['family']} {s_['side']} giá={s_.get('price')} "
          f"KL={s_.get('amount')} · nguồn: {nguon}")
print("=" * 78)
