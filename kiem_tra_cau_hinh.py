# -*- coding: utf-8 -*-
"""
Soát cấu hình TRƯỚC khi bật bot — không đặt lệnh, không đụng tiền.

    python3 kiem_tra_cau_hinh.py

In ra: nguồn cấu hình, danh sách tài khoản, tham số của từng tài khoản, và
chỉ rõ chỗ nào thiếu/lệch. Chạy cái này mỗi lần đổi cấu hình trên sheet.
"""
import giu_cua_so  # PHẢI nạp ĐẦU TIÊN: dừng/lỗi thì giữ cửa sổ Windows để đọc thông báo
import os
import sys

os.environ.setdefault('QBOT_NO_LOCK', '1')     # không giành khoá của bot đang chạy
os.environ['QBOT_CHE_DO_SOAT'] = '1'          # xem mọi tài khoản, không bắt chọn 1 tài khoản


def _ngan(v, n=14):
    v = str(v)
    return v if len(v) <= n else v[:n] + '…'


def main():
    print("=" * 72)
    print("  SOÁT CẤU HÌNH QBOT")
    print("=" * 72)

    try:
        import cst
    except SystemExit as e:
        print(f"\n❌ Cấu hình KHÔNG hợp lệ — bot sẽ không khởi động được:\n")
        print(str(e))
        return 1
    except Exception as e:
        print(f"\n❌ Lỗi khi nạp cấu hình: {type(e).__name__}: {e}")
        return 1

    nguon = "SHEET TỔNG" if getattr(cst, 'nap_tu_sheet', False) else "config.ini"
    print(f"\n📄 Nguồn cấu hình : {nguon}")
    print(f"   File config    : {cst.config_file}")
    if getattr(cst, 'nap_tu_sheet', False):
        print(f"   Mã bot (tab)   : {cst.bot_id}")
        print(f"   Sheet tổng     : {cst.config_spreadsheet_id}")
        print(f"   Phiên bản      : {cst.config_sheet_version or '(trống)'}")

    accs = cst.accounts
    loi_global = 0
    if not accs:
        print("\n⚠️  Không khai tài khoản nào → chế độ 1 tài khoản (dùng [global])")
        # Chế độ 1 tài khoản: key nằm thẳng ở [global], phải kiểm ở đây —
        # nếu không sẽ báo "hợp lệ" cho một config rỗng, bot bật lên mới chết.
        for k in ('key_binance', 'secret_binance', 'spreadsheet_id'):
            if not cst.config.get('global', k, fallback='').strip():
                print(f"   ❌ [global] THIẾU {k}")
                loi_global += 1
        if not loi_global:
            print("   ✅ [global] có đủ key_binance / secret_binance / spreadsheet_id")
        accs = []

    print(f"\n👥 {len(accs)} tài khoản: {', '.join(accs) if accs else '(không có)'}")

    loi = loi_global
    for ten in accs:
        that = cst.resolve_section(ten) if hasattr(cst, 'resolve_section') else ten
        print("\n" + "─" * 72)
        if that is None:
            print(f"  ❌ [{ten}] KHÔNG tìm thấy cấu hình")
            loi += 1
            continue
        if that != ten:
            print(f"  ⚠️  [{ten}] khớp với [{that}] (khác chữ hoa/thường — nên sửa cho khớp)")
        print(f"  ✅ [{that}]")

        muc = dict(cst.config.items(that))
        thieu = [k for k in ('key_binance', 'secret_binance', 'spreadsheet_id')
                 if not muc.get(k, '').strip()]
        if thieu:
            print(f"     ❌ THIẾU: {', '.join(thieu)}")
            loi += 1

        for k in ('key_binance', 'secret_binance', 'spreadsheet_id', 'chat_id',
                  'key_name', 'default_sl_rate_layer_1', 'default_tp_rate_layer_1',
                  'leg1_col'):
            if muc.get(k, '').strip():
                che = k in ('key_binance', 'secret_binance')
                print(f"     {k:26} = {_ngan(muc[k]) if che else muc[k]}")

    # Trùng sheet giữa các tài khoản — dấu hiệu chép nhầm, rất nguy hiểm
    print("\n" + "─" * 72)
    theo_sheet = {}
    theo_key = {}
    for ten in accs:
        that = cst.resolve_section(ten) if hasattr(cst, 'resolve_section') else ten
        if not that:
            continue
        muc = dict(cst.config.items(that))
        for kho, khoa in ((theo_sheet, 'spreadsheet_id'), (theo_key, 'key_binance')):
            gt = muc.get(khoa, '').strip()
            if gt:
                kho.setdefault(gt, []).append(that)

    for kho, nhan in ((theo_sheet, 'Google Sheet'), (theo_key, 'API key Binance')):
        for gt, ds in kho.items():
            if len(ds) > 1:
                print(f"  🔴 {nhan} DÙNG CHUNG bởi {', '.join(ds)} — "
                      f"gần như chắc chắn là chép nhầm!")
                loi += 1

    print("\n" + "=" * 72)
    if loi:
        print(f"  ❌ {loi} vấn đề — SỬA XONG rồi hãy bật bot")
    else:
        print("  ✅ Cấu hình hợp lệ, sẵn sàng bật bot")
    print("=" * 72)
    return 1 if loi else 0


if __name__ == '__main__':
    sys.exit(main())
