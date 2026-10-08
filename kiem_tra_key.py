# -*- coding: utf-8 -*-
"""
KIỂM TRA API KEY BINANCE của MỌI tài khoản — CHỈ ĐỌC, không đặt lệnh, không đụng tiền.

    python kiem_tra_key.py

Dùng khi bot báo -1022 "Signature for this request is not valid" (hoặc -2014 / -2015).
Với từng tài khoản đang Bật trên sheet tổng (hoặc config.ini), in ra:
  • key / secret trông có hợp lệ không (độ dài, ký tự lạ — dấu cách, xuống dòng ẩn…)
  • Thử 1 — tự ký HMAC như bot (đọc số dư /fapi/v2/balance)
  • Thử 2 — qua ccxt, ĐÚNG lệnh hd_update_cho_va_khop đang lỗi (/fapi/v1/leverageBracket)
  • key / secret có bị TRÙNG giữa các tài khoản không (dấu hiệu dán lệch dòng)
và kết luận nên sửa ở đâu.
"""
import giu_cua_so  # PHẢI nạp ĐẦU TIÊN: dừng/lỗi thì giữ cửa sổ Windows để đọc thông báo
import hashlib
import hmac
import os
import platform
import re
import sys
import time
import urllib.parse

os.environ.setdefault('QBOT_NO_LOCK', '1')     # không giành khoá của bot đang chạy
os.environ['QBOT_CHE_DO_SOAT'] = '1'          # xem mọi tài khoản, không bắt chọn 1 tài khoản

FAPI = 'https://fapi.binance.com'
KY_TU_HOP_LE = re.compile(r'^[A-Za-z0-9]+$')


def _che(v):
    v = str(v or '')
    return f"{v[:4]}…{v[-4:]}" if len(v) > 8 else '(quá ngắn)'


def soi_chuoi(ten, v):
    """Các vấn đề nhìn thấy được của key/secret (độ dài, ký tự lạ)."""
    van_de = []
    if not v:
        return ["TRỐNG"]
    if len(v) != 64:
        van_de.append(f"dài {len(v)} ký tự (key HMAC của Binance thường 64)")
    la = sorted({c for c in v if not KY_TU_HOP_LE.match(c)})
    if la:
        mo_ta = ', '.join(repr(c) for c in la[:5])
        van_de.append(f"có ký tự lạ {mo_ta} — thường do copy kèm dấu cách / xuống dòng / ký tự ẩn")
    return van_de


def gio_server(requests):
    try:
        return int(requests.get(f'{FAPI}/fapi/v1/time', timeout=10).json()['serverTime'])
    except Exception:
        return int(time.time() * 1000)


def thu_tu_ky(requests, key, secret):
    """(ok, mô tả) — tự ký HMAC, đọc số dư. Dùng giờ server để loại lỗi lệch giờ."""
    q = urllib.parse.urlencode({'timestamp': gio_server(requests), 'recvWindow': 60000})
    sig = hmac.new(secret.encode('utf-8'), q.encode('utf-8'), hashlib.sha256).hexdigest()
    try:
        r = requests.get(f'{FAPI}/fapi/v2/balance?{q}&signature={sig}',
                         headers={'X-MBX-APIKEY': key}, timeout=15)
    except Exception as e:
        return None, f"lỗi mạng: {e}"
    if r.status_code == 200:
        return True, "OK"
    try:
        j = r.json()
        return False, f"{j.get('code')} {j.get('msg')}"
    except Exception:
        return False, f"HTTP {r.status_code}"


def thu_ccxt(ccxt, key, secret):
    """(ok, mô tả) — ccxt cấu hình y như bot, gọi đúng lệnh đang lỗi."""
    try:
        ex = ccxt.binance({
            'enableRateLimit': True, 'apiKey': key, 'secret': secret,
            'options': {'defaultType': 'future', 'fetchCurrencies': False,
                        'fetchMarkets': {'types': ['linear']}, 'fetchMargins': False,
                        'adjustForTimeDifference': True, 'recvWindow': 60000},
        })
        ex.fapiPrivateGetLeverageBracket()
        return True, "OK"
    except Exception as e:
        m = re.search(r'"code":\s*(-?\d+),\s*"msg":\s*"([^"]*)"', str(e))
        return False, (f"{m.group(1)} {m.group(2)}" if m else f"{type(e).__name__}: {str(e)[:150]}")


def ket_luan(van_de, tu_ky, qua_ccxt):
    ok1, mt1 = tu_ky
    ok2, mt2 = qua_ccxt
    if ok1 and ok2:
        return "✅ Key dùng tốt"
    if ok1 and not ok2:
        return ("⚠️ Tự ký OK nhưng ccxt LỖI → không phải do key. Lỗi ở thư viện ccxt / Python trên "
                "VPS (vừa nâng cấp?). Gửi em dòng phiên bản ccxt ở đầu kết quả.")
    if ok1 is None or ok2 is None:
        return "⚠️ Lỗi mạng — chạy lại sau ít phút"
    if '-2015' in mt1:
        return ("❌ -2015: key đúng nhưng BỊ CHẶN — IP của VPS chưa có trong danh sách IP của key, "
                "hoặc key chưa bật quyền Futures. Sửa trên Binance → API Management.")
    if '-2014' in mt1 or '-2008' in mt1:
        return "❌ API Key sai định dạng / không tồn tại → dán lại API Key trên sheet tổng."
    if '-1022' in mt1:
        if van_de:
            return "❌ -1022 do key/secret có vấn đề ở trên (ký tự lạ / độ dài) → dán lại cho sạch."
        return ("❌ -1022: API Secret KHÔNG khớp API Key. Nguyên nhân hay gặp: dán secret của key "
                "khác, cột Secret bị lệch dòng so với cột Key trên sheet tổng (sắp xếp / chèn dòng "
                "chỉ một phần cột), key đã bị xoá / tạo lại trên Binance, hoặc key tạo kiểu "
                "Ed25519 / RSA (bot chỉ dùng được key kiểu HMAC).")
    return f"❌ {mt1}"


def main():
    import requests
    import ccxt
    print("=" * 76)
    print("  KIỂM TRA API KEY BINANCE — chỉ đọc, không đặt lệnh")
    print("=" * 76)
    print(f"  Python {platform.python_version()} · ccxt {getattr(ccxt, '__version__', '?')} · "
          f"requests {getattr(requests, '__version__', '?')}")
    try:
        lech = gio_server(requests) - int(time.time() * 1000)
        print(f"  Giờ VPS lệch giờ Binance: {lech / 1000:+.1f}s"
              + ("  ⚠️ lệch nhiều — nên đồng bộ giờ Windows" if abs(lech) > 5000 else ""))
    except Exception:
        pass

    try:
        import cst
    except SystemExit as e:
        print(f"\n❌ Cấu hình KHÔNG hợp lệ:\n{e}")
        return 1

    accs = list(cst.accounts) or [None]
    ds = []
    for ten in accs:
        if ten is None:
            muc = dict(cst.config.items('global'))
            ten = 'global'
        else:
            that = cst.resolve_section(ten) if hasattr(cst, 'resolve_section') else ten
            if not that:
                print(f"\n❌ [{ten}] không tìm thấy cấu hình")
                continue
            muc = dict(cst.config.items(that))
        ds.append((ten, muc.get('key_binance', '') or '', muc.get('secret_binance', '') or ''))

    so_loi = 0
    for ten, key, secret in ds:
        print("\n" + "─" * 76)
        print(f"  [{ten}]  key {_che(key)} ({len(key)} ký tự) · secret {_che(secret)} ({len(secret)} ký tự)")
        van_de = [f"API Key {x}" for x in soi_chuoi('key', key)] + \
                 [f"API Secret {x}" for x in soi_chuoi('secret', secret)]
        for x in van_de:
            print(f"     ⚠️  {x}")
        if not key or not secret:
            print("     ❌ Thiếu key / secret")
            so_loi += 1
            continue
        tu_ky = thu_tu_ky(requests, key, secret)
        qua_ccxt = thu_ccxt(ccxt, key, secret)
        print(f"     Thử 1 — tự ký (số dư)        : {tu_ky[1]}")
        print(f"     Thử 2 — ccxt (leverageBracket): {qua_ccxt[1]}")
        kl = ket_luan(van_de, tu_ky, qua_ccxt)
        print(f"     → {kl}")
        if not kl.startswith("✅"):
            so_loi += 1

    print("\n" + "─" * 76)
    for nhan, idx in (("API Key", 1), ("API Secret", 2)):
        theo = {}
        for d in ds:
            if d[idx]:
                theo.setdefault(d[idx], []).append(d[0])
        for v, tks in theo.items():
            if len(tks) > 1:
                print(f"  🔴 {nhan} TRÙNG giữa {', '.join(tks)} — gần như chắc chắn dán lệch dòng")
                so_loi += 1

    print("\n" + "=" * 76)
    print(f"  KẾT QUẢ: {len(ds) - min(so_loi, len(ds))}/{len(ds)} tài khoản dùng được key"
          if so_loi else f"  KẾT QUẢ: cả {len(ds)} tài khoản đều dùng được key ✅")
    print("=" * 76)
    return 1 if so_loi else 0


if __name__ == "__main__":
    sys.exit(main())
