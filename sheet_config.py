# -*- coding: utf-8 -*-
"""
sheet_config — đọc cấu hình từ SHEET TỔNG.

Ý tưởng: `config.ini` trên máy chỉ còn khai MÃ BOT và ID sheet tổng. Toàn bộ
danh sách tài khoản, API key và cấu hình từng tài khoản nằm trên Google Sheet,
để khách đổi key mà không phải mở file trên VPS.

    [global]
    bot_id = QBOT01
    config_spreadsheet_id = 1AbC...XyZ

⚠️ MODULE NÀY KHÔNG ĐƯỢC import cst HAY gg_sheet_factory
    gg_sheet_factory dòng 1 là `import cst`, mà cst chính là nơi gọi module
    này → nạp chéo sẽ thành vòng lặp import. Vì vậy ở đây tự xác thực Google
    bằng credentials.json / token.json, dùng lại đúng token của bot.

BỐ CỤC SHEET TỔNG — mỗi bot MỘT TAB, tên tab đặt đúng bằng bot_id

    Dòng 1 :  A1 = "PHIÊN BẢN"      B1 = <số bất kỳ>
              Sửa bất cứ ô nào bên dưới thì ĐỔI Ô B1. Bot chỉ đọc mỗi ô này
              để biết có gì thay đổi — rẻ, không tốn hạn mức Google.

    Dòng 2 :  tiêu đề cột (xem bảng nhãn bên dưới)
    Dòng 3+:  mỗi dòng một tài khoản

Ví dụ:

    |   | A         | B   | C       | D          | E        | F       | G   | H   | I   |
    | 1 | PHIÊN BẢN | 7   |         |            |          |         |     |     |     |
    | 2 | Tài khoản | Bật | API Key | API Secret | Sheet ID | Chat ID | Lớp | %SL | %TP |
    | 3 | q2pri     | Y   | abc...  | xyz...     | 1AA...   | -100    | 1   | 2   | 3   |
    | 4 | q2pub     | Y   | def...  | uvw...     | 1BB...   | -100    | 2   | 5   | 6   |
    | 5 | q3fu      | N   | ghi...  | rst...     | 1CC...   | -100    | 3   | 10  | 10  |

TIÊU ĐỀ CỘT: dùng nhãn tiếng Việt ở bảng NHAN_COT bên dưới, HOẶC ghi thẳng
tên tham số như trong config.ini (vd `allow_dca`). Cách hai cho phép thêm bất
kỳ tham số nào mà không phải sửa code.
"""

import os
import re

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Nhãn tiếng Việt trên sheet  →  tên tham số trong config
# Khoá bên trái đã bỏ dấu, viết thường, bỏ khoảng trắng (xem _chuan_hoa_nhan).
NHAN_COT = {
    'taikhoan':     '__ten__',        # cột định danh, không phải tham số
    'account':      '__ten__',
    'ten':          '__ten__',
    'bat':          '__bat__',        # Y/N — tắt tài khoản ngay trên sheet
    'enable':       '__bat__',
    'apikey':       'key_binance',
    'keybinance':   'key_binance',
    'apisecret':    'secret_binance',
    'secretbinance': 'secret_binance',
    'sheetid':      'spreadsheet_id',
    'spreadsheetid': 'spreadsheet_id',
    'chatid':       'chat_id',
    'bottoken':     'bot_token',
    'tenhienthi':   'key_name',
    'keyname':      'key_name',
    'prefixchannel': 'prefix_channel',
    'lop':          '__lop__',        # chỉ để ghi log cho dễ đọc
    'layer':        '__lop__',
    'sl':           'default_sl_rate_layer_1',
    'tysl':         'default_sl_rate_layer_1',
    'tp':           'default_tp_rate_layer_1',
    'tytp':         'default_tp_rate_layer_1',
    'cotgia':       'leg1_col',
    'cotgiavao':    'leg1_col',
}

BAT_BUOC = ('key_binance', 'secret_binance', 'spreadsheet_id')


class LoiSheetCauHinh(Exception):
    """Không đọc/hiểu được sheet tổng. Bot phải DỪNG, không đoán."""


def _chuan_hoa_nhan(s):
    """'Tài khoản' → 'taikhoan'. Bỏ dấu, viết thường, bỏ mọi ký tự không phải chữ/số."""
    s = str(s or '').strip().lower()
    for dau, khong in (('àáảãạăằắẳẵặâầấẩẫậ', 'a'), ('èéẻẽẹêềếểễệ', 'e'),
                       ('ìíỉĩị', 'i'), ('òóỏõọôồốổỗộơờớởỡợ', 'o'),
                       ('ùúủũụưừứửữự', 'u'), ('ỳýỷỹỵ', 'y'), ('đ', 'd')):
        for c in dau:
            s = s.replace(c, khong)
    return re.sub(r'[^a-z0-9]', '', s)


def _khoa_tu_tieu_de(o):
    """
    Tiêu đề cột → tên tham số.

    Ưu tiên nhãn tiếng Việt trong NHAN_COT. Không khớp thì nếu ô đó nhìn như
    tên tham số (chữ thường + gạch dưới) sẽ dùng thẳng — nhờ vậy thêm cột
    `allow_dca` là dùng được ngay, không cần sửa code.
    """
    tho = str(o or '').strip()
    if not tho:
        return None
    chuan = _chuan_hoa_nhan(tho)
    if chuan in NHAN_COT:
        return NHAN_COT[chuan]
    if re.fullmatch(r'[a-z][a-z0-9_]*', tho.lower().strip()):
        return tho.lower().strip()
    return None


def phan_tich_bang(rows):
    """
    Bảng thô từ sheet → (phiên_bản, {tên_tài_khoản: {tham_số: giá_trị}}).

    Chỉ tách dữ liệu, KHÔNG gọi mạng — nhờ vậy test được offline.
    """
    if not rows:
        raise LoiSheetCauHinh("Tab cấu hình rỗng")

    phien_ban = ''
    if len(rows) > 0 and len(rows[0]) > 1:
        phien_ban = str(rows[0][1]).strip()

    if len(rows) < 3:
        raise LoiSheetCauHinh(
            "Sheet phải có ít nhất 3 dòng: dòng 1 phiên bản, dòng 2 tiêu đề, "
            "dòng 3 trở đi là tài khoản")

    tieu_de = [_khoa_tu_tieu_de(o) for o in rows[1]]
    if '__ten__' not in tieu_de:
        raise LoiSheetCauHinh(
            "Dòng 2 thiếu cột 'Tài khoản'. Các tiêu đề đọc được: "
            + ', '.join(repr(o) for o in rows[1][:12]))

    cot_ten = tieu_de.index('__ten__')
    ket_qua, thu_tu = {}, []

    for so_dong, dong in enumerate(rows[2:], start=3):
        if not dong or cot_ten >= len(dong):
            continue
        ten = str(dong[cot_ten]).strip()
        if not ten:
            continue

        # Trùng tên (bỏ qua hoa/thường) → DỪNG, không đoán: chọn nhầm dòng
        # nghĩa là chạy sai key, sai vốn.
        trung = [t for t in thu_tu if t.lower() == ten.lower()]
        if trung:
            raise LoiSheetCauHinh(
                f"Tài khoản '{ten}' (dòng {so_dong}) trùng với '{trung[0]}' đã khai "
                f"phía trên. Không thể đoán dùng dòng nào — hãy đổi tên cho khác hẳn.")

        muc = {}
        for i, khoa in enumerate(tieu_de):
            if not khoa or khoa == '__ten__':
                continue
            gt = str(dong[i]).strip() if i < len(dong) else ''
            if gt:
                muc[khoa] = gt
        muc['__ten__'] = ten
        ket_qua[ten] = muc
        thu_tu.append(ten)

    if not ket_qua:
        raise LoiSheetCauHinh("Không có dòng tài khoản nào (từ dòng 3 trở xuống)")

    return phien_ban, ket_qua


def loc_dang_bat(bang):
    """Bỏ các tài khoản có cột 'Bật' = N. Không khai cột Bật = coi như bật."""
    ra = {}
    for ten, muc in bang.items():
        bat = str(muc.get('__bat__', 'Y')).strip().upper()
        if bat in ('N', 'NO', 'FALSE', '0', 'TAT', 'TẮT'):
            continue
        ra[ten] = muc
    return ra


def kiem_tra_du_khoa(bang):
    """Mỗi tài khoản BẮT BUỘC có key/secret/sheet — thiếu là dừng, tránh dùng nhầm key."""
    loi = []
    for ten, muc in bang.items():
        thieu = [k for k in BAT_BUOC if not muc.get(k)]
        if thieu:
            loi.append(f"  • [{ten}] thiếu: {', '.join(thieu)}")
    if loi:
        raise LoiSheetCauHinh(
            "Tài khoản thiếu thông tin bắt buộc trên sheet tổng:\n" + "\n".join(loi)
            + "\n   (Không cho chạy tiếp vì tài khoản thiếu key sẽ dùng nhầm key "
              "của tài khoản khác.)")


def tim_tai_khoan(bang, ten):
    """Tìm tài khoản theo tên, BỎ QUA hoa/thường (giống cách khớp section config.ini)."""
    if ten in bang:
        return ten
    trung = [t for t in bang if t.lower() == ten.lower()]
    if len(trung) == 1:
        return trung[0]
    return None


# ── Phần gọi mạng ───────────────────────────────────────────────────────────

def _lay_service():
    """Dựng service Google Sheets bằng token.json / credentials.json cạnh file này."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    thu_muc = os.path.dirname(os.path.abspath(__file__))
    token_path = os.path.join(thu_muc, 'token.json')
    cred_path = os.path.join(thu_muc, 'credentials.json')

    if not os.path.exists(token_path):
        raise LoiSheetCauHinh(
            f"Không có {token_path}. Chạy bot một lần để đăng nhập Google "
            f"và sinh token.json trước.")
    try:
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    except Exception as e:
        raise LoiSheetCauHinh(f"token.json hỏng: {e}")

    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as e:
            raise LoiSheetCauHinh(f"Không làm mới được token Google: {e}")

    if not creds or not creds.valid:
        raise LoiSheetCauHinh(
            "Token Google không dùng được. Xoá token.json rồi chạy lại để đăng nhập.")

    return build('sheets', 'v4', credentials=creds, cache_discovery=False)


def doc_o_phien_ban(spreadsheet_id, tab):
    """Đọc MỖI ô B1 — dùng để dò thay đổi mà không tốn hạn mức."""
    try:
        sv = _lay_service()
        r = sv.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range=f"'{tab}'!B1:B1").execute()
        gt = r.get('values', [[]])
        return str(gt[0][0]).strip() if gt and gt[0] else ''
    except LoiSheetCauHinh:
        raise
    except Exception as e:
        raise LoiSheetCauHinh(f"Không đọc được ô phiên bản '{tab}'!B1: {e}")


def doc_bang_tho(spreadsheet_id, tab):
    """Đọc trọn vùng cấu hình A1:Z200 của tab."""
    try:
        sv = _lay_service()
        r = sv.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id, range=f"'{tab}'!A1:Z200").execute()
        return r.get('values', [])
    except LoiSheetCauHinh:
        raise
    except Exception as e:
        raise LoiSheetCauHinh(f"Không đọc được tab '{tab}' của sheet tổng: {e}")


def nap(bot_id, spreadsheet_id):
    """
    Đọc trọn cấu hình cho một mã bot.

    Trả về (phiên_bản, {tên: {tham_số: giá_trị}}) — đã lọc tài khoản tắt và
    đã kiểm tra đủ khoá bắt buộc.

    Lỗi thì NÉM LoiSheetCauHinh để bot dừng hẳn. Theo quyết định của khách:
    thà không chạy còn hơn chạy bằng cấu hình cũ mà tưởng là mới.
    """
    rows = doc_bang_tho(spreadsheet_id, bot_id)
    phien_ban, bang = phan_tich_bang(rows)
    bang = loc_dang_bat(bang)
    if not bang:
        raise LoiSheetCauHinh(
            f"Tab '{bot_id}': không tài khoản nào đang Bật (cột 'Bật' đều là N)")
    kiem_tra_du_khoa(bang)
    return phien_ban, bang
