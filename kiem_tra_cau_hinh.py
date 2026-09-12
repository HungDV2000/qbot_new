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


def in_nhip_chay(cst):
    """Nhịp chạy THỰC TẾ của từng bot (giây) — soi xem config có được nhận không."""
    print("\n" + "─" * 72)
    print("  ⏱️  Nhịp chạy của từng bot (giây)")
    bang = [
        ("hd_order_multi", "delay_vao_lenh", cst.delay_vao_lenh),
        ("hd_update_cho_va_khop", "delay_cho_va_khop", cst.delay_cho_va_khop),
        ("hd_alert_possition...", "delay_calert_possition_and_open_order",
         cst.delay_calert_possition_and_open_order),
        ("hd_update_all", "delay_update_all", cst.delay_update_all),
        ("hd_cancel_orders_schedule", "cancel_orders_seconds", cst.cancel_orders_seconds),
        ("hd_cancel_selective", "cancel_selective_seconds",
         max(15, cst.config.getint('global', 'cancel_selective_seconds', fallback=60))),
    ]
    for bot, khoa, giay in bang:
        print(f"     {bot:26} {giay:>8.0f}s   ({khoa})")
    print(f"     {'dò ô B1 sheet tổng':26} "
          f"{cst.config.getint('global', 'config_reload_seconds', fallback=300):>8}s   (config_reload_seconds)")
    print("     ⚠️  Sửa config.ini xong phải TẮT rồi BẬT LẠI bot mới có tác dụng.")


def soat_tab_tung_tai_khoan(cst, accs):
    """Mở sheet riêng của từng tài khoản, kiểm có đủ tab bắt buộc. Trả số lỗi."""
    print("\n" + "─" * 72)
    print("  📑 Tab trên sheet riêng của từng tài khoản")
    can = [cst.tab_dat_lenh, "Chờ và khớp"]
    try:
        import sheet_config
        sv = sheet_config._lay_service()
    except Exception as e:
        print(f"  ⚠️  Bỏ qua (không kết nối được Google): {e}")
        return 0

    muc_tieu = []
    for ten in accs:
        that = cst.resolve_section(ten) if hasattr(cst, 'resolve_section') else ten
        if not that:
            continue
        sid = dict(cst.config.items(that)).get('spreadsheet_id', '').strip()
        if sid:
            muc_tieu.append((ten, sid))
    if not accs:
        sid = cst.config.get('global', 'spreadsheet_id', fallback='').strip()
        if sid:
            muc_tieu.append(('(1 tài khoản)', sid))
    if not muc_tieu:
        print("  ⚠️  Không có Sheet ID nào để kiểm")
        return 0

    loi = 0
    for ten, sid in muc_tieu:
        try:
            meta = sv.spreadsheets().get(spreadsheetId=sid,
                                         fields='sheets.properties.title').execute()
            ds = [m['properties']['title'] for m in meta.get('sheets', [])
                  if isinstance(m, dict) and m.get('properties', {}).get('title')]
        except Exception as e:
            txt = str(e)
            if '404' in txt:
                vi_sao = "không tìm thấy sheet (Sheet ID sai?)"
            elif '403' in txt:
                vi_sao = "tài khoản Google đang đăng nhập KHÔNG có quyền (chia sẻ Editor cho nó)"
            else:
                vi_sao = txt
            print(f"  ❌ [{ten}] không mở được sheet {sid}: {vi_sao}")
            loi += 1
            continue
        thieu = [t for t in can if t not in ds]
        if thieu:
            print(f"  ❌ [{ten}] THIẾU tab: {', '.join(repr(t) for t in thieu)}")
            print(f"       Sheet đang có: {', '.join(repr(t) for t in ds) or '(không có tab nào)'}")
            print(f"       Tên tab phải khớp TỪNG KÝ TỰ (dấu tiếng Việt, khoảng trắng).")
            loi += 1
        else:
            print(f"  ✅ [{ten}] đủ tab: {', '.join(repr(t) for t in can)}")
    return loi


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

    in_nhip_chay(cst)

    # Sheet RIÊNG của từng tài khoản có đủ tab không — bắt lỗi sai tên tab
    # TRƯỚC khi bật bot, thay vì để bot chạy rồi chết với lỗi thô của Google.
    loi += soat_tab_tung_tai_khoan(cst, accs)

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
