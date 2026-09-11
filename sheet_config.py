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

    |   | A         | B   | C       | D          | E        | F       | G   | H   |
    | 1 | PHIÊN BẢN | 7   |         |            |          |         |     |     |
    | 2 | Tài khoản | Bật | API Key | API Secret | Sheet ID | Chat ID | %SL | %TP |
    | 3 | q2pri     | Y   | abc...  | xyz...     | 1AA...   | -100    | 2   | 3   |
    | 4 | q2pub     | Y   | def...  | uvw...     | 1BB...   | -100    | 5   | 6   |
    | 5 | q3fu      | N   | ghi...  | rst...     | 1CC...   | -100    | 10  | 10  |

    Số LỚP = số dòng đang Bật (mỗi tài khoản chạy đúng 1 lớp). Không có cột
    "Lớp" — sheet cũ còn cột đó thì bot tự bỏ qua.

TIÊU ĐỀ CỘT: dùng nhãn tiếng Việt ở bảng NHAN_COT bên dưới, HOẶC ghi thẳng
tên tham số như trong config.ini (vd `allow_dca`). Cách hai cho phép thêm bất
kỳ tham số nào mà không phải sửa code.
"""

import os
import re
import sys

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


class LoiDocSheet(LoiSheetCauHinh):
    """Lỗi MẠNG / Google khi đọc sheet — thường tạm thời, nên thử lại sau.

    Tách khỏi lỗi dữ liệu để bot đang chạy không đánh dấu nhầm một phiên bản
    cấu hình là "hỏng" chỉ vì Google chập chờn đúng lúc đọc.
    """


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


GIA_TRI_BAT = {'y', 'yes', 'co', '1', 'true', 'x', 'on', 'bat'}
GIA_TRI_TAT = {'n', 'no', 'khong', '0', 'false', 'off', 'tat'}


def _hieu_bat_tat(gt):
    """'Có'/'Y' → True, 'Không'/'N' → False, rỗng → None, lạ → ValueError."""
    chuan = _chuan_hoa_nhan(gt)
    if chuan == '':
        return None
    if chuan in GIA_TRI_BAT:
        return True
    if chuan in GIA_TRI_TAT:
        return False
    raise ValueError(gt)


def loc_dang_bat(bang):
    """
    Bỏ các tài khoản có cột 'Bật' = tắt. Không khai / để trống = coi như bật.

    ⚠️ Trước đây chỉ nhận N/NO/FALSE/0/TẮT là tắt — gõ "Không" (cách người Việt
    hay gõ) lại bị hiểu là BẬT. Nay hiểu cả tiếng Việt có/không dấu, và giá trị
    lạ (vd "tạm dừng") thì DỪNG thay vì đoán — đoán sai là bật nhầm tài khoản.
    """
    ra, la = {}, []
    for ten, muc in bang.items():
        try:
            bat = _hieu_bat_tat(muc.get('__bat__', ''))
        except ValueError:
            la.append(f"  • [{ten}] cột Bật = '{muc.get('__bat__')}'")
            continue
        if bat is False:
            continue
        ra[ten] = muc
    if la:
        raise LoiSheetCauHinh(
            "Cột 'Bật' có giá trị không hiểu được:\n" + "\n".join(la)
            + "\n   Chỉ dùng: Y / N (hoặc Có / Không). Để trống = bật.")
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


KHOA_BAT_TAT = {'allow_dca', 'exit_sl_close_position', 'exit_tp_resize',
                'fill_default_cho_va_khop', 'cancel_all_orders', 'run_tele_command'}


def _so(v):
    """'2,5' → 2.5 (dấu phẩy thập phân kiểu Việt). Không phải số → ValueError."""
    t = str(v).strip().replace(' ', '')
    if ',' in t and '.' not in t:
        t = t.replace(',', '.')
    try:
        return float(t)
    except ValueError:
        raise ValueError("phải là SỐ")


def _chuan_hoa_gia_tri(k, v):
    """Kiểm + chuẩn hoá một ô theo loại tham số. Sai → ValueError kèm lý do."""
    v = str(v).strip()
    if k.startswith(('default_sl_rate', 'default_tp_rate')):
        x = _so(v)
        if not 0 < x < 100:
            raise ValueError("phải là % trong khoảng 0 – 100 (vd 2 hoặc 2.5)")
        return str(int(x)) if x == int(x) else repr(x)
    if k.endswith('_pct'):
        x = _so(v)
        if x < 0:
            raise ValueError("không được âm")
        return repr(x)
    if k.startswith('delay_') or k.endswith(('_minutes', '_seconds', '_sec')):
        x = _so(v)
        if x != int(x) or x < 1:
            raise ValueError("phải là SỐ NGUYÊN dương")
        return str(int(x))
    if k.endswith(('_col', '_aux')):
        u = v.upper()
        if not re.fullmatch(r'[A-Z]{1,2}', u):
            raise ValueError("phải là CHỮ CÁI tên cột, vd D hoặc AA")
        return u
    if k in KHOA_BAT_TAT or k == 'default_allow_order':
        b = _hieu_bat_tat(v)
        if b is None:
            raise ValueError("đang để trống")
        if k == 'default_allow_order':
            return 'Y' if b else 'N'
        return 'true' if b else 'false'
    return v


def kiem_tra_du_lieu(bang):
    """
    Soát dữ liệu từng ô — bắt các lỗi hay gặp khi SỬA DỞ trên sheet:
      • API key dán thiếu / dính khoảng trắng
      • hai tài khoản trùng API key hoặc trùng Sheet ID (chép dòng quên sửa)
        → hai tiến trình cùng giao dịch MỘT tài khoản = ĐẶT LỆNH TRÙNG
      • số gõ kiểu Việt "2,5", chữ trong ô số, tên cột sai
    Chuẩn hoá tại chỗ ("2,5" → "2.5"). Có lỗi → LoiSheetCauHinh, không đoán.
    """
    loi = []
    for ten, muc in bang.items():
        for k in ('key_binance', 'secret_binance'):
            v = muc.get(k, '')
            co_trang = bool(re.search(r'\s', v))
            if v and (co_trang or len(v) < 16):
                them = ', có khoảng trắng' if co_trang else ''
                loi.append(f"  • [{ten}] {k} trông không hợp lệ ({len(v)} ký tự{them}) — dán thiếu?")
        for k in list(muc):
            if k.startswith('__') or k in ('key_binance', 'secret_binance'):
                continue
            try:
                muc[k] = _chuan_hoa_gia_tri(k, muc[k])
            except ValueError as e:
                loi.append(f"  • [{ten}] {k} = '{muc[k]}': {e}")
    for khoa, nhan in (('key_binance', 'API Key'), ('spreadsheet_id', 'Sheet ID')):
        gom = {}
        for ten, muc in bang.items():
            if muc.get(khoa):
                gom.setdefault(muc[khoa], []).append(ten)
        for ds in gom.values():
            if len(ds) > 1:
                loi.append(f"  • {nhan} DÙNG CHUNG bởi {', '.join(ds)} — hai tiến trình "
                           f"sẽ cùng giao dịch MỘT tài khoản → ĐẶT LỆNH TRÙNG")
    if loi:
        raise LoiSheetCauHinh("Dữ liệu trên sheet tổng không hợp lệ:\n" + "\n".join(loi))


def tim_tai_khoan(bang, ten):
    """Tìm tài khoản theo tên, BỎ QUA hoa/thường (giống cách khớp section config.ini)."""
    if ten in bang:
        return ten
    trung = [t for t in bang if t.lower() == ten.lower()]
    if len(trung) == 1:
        return trung[0]
    return None


# ── Phần gọi mạng ───────────────────────────────────────────────────────────

_LENH_DANG_NHAP = "dang_nhap_google.py"


def _dang_nhap(thu_muc):
    """Mở trình duyệt đăng nhập Google, ghi token.json. Lỗi → LoiSheetCauHinh."""
    try:
        import dang_nhap_google
        dang_nhap_google.dang_nhap(thu_muc)
    except Exception as e:
        raise LoiSheetCauHinh(
            f"Đăng nhập Google không xong: {e}\n"
            f"   Thử lại bằng cách bấm đúp {_LENH_DANG_NHAP}.")


def _co_nguoi_ngoi_may():
    """Có người trước bàn phím để đăng nhập trên trình duyệt không.
    Tiến trình con của điều phối / chạy nền thì KHÔNG — mở trình duyệt sẽ treo."""
    if os.environ.get('QBOT_SUPERVISED', '') == '1':
        return False
    if os.environ.get('QBOT_TU_DANG_NHAP', '').strip() == '0':
        return False
    try:
        return sys.stdin is not None and sys.stdin.isatty()
    except Exception:
        return False


def _lay_service():
    """Dựng service Google Sheets bằng token.json / credentials.json cạnh file này."""
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    from google.auth.exceptions import RefreshError
    from googleapiclient.discovery import build

    thu_muc = os.path.dirname(os.path.abspath(__file__))
    token_path = os.path.join(thu_muc, 'token.json')
    cred_path = os.path.join(thu_muc, 'credentials.json')

    # Trước đây báo "chạy bot một lần để đăng nhập" — nhưng bot nào cũng đọc sheet
    # tổng TRƯỚC, thiếu token là dừng luôn → máy mới không bao giờ đăng nhập được.
    if not os.path.exists(token_path):
        if not os.path.exists(cred_path):
            raise LoiSheetCauHinh(
                f"Chưa đăng nhập Google: thiếu cả token.json lẫn credentials.json trong {thu_muc}.\n"
                f"   Chép credentials.json (OAuth client loại Desktop app) vào thư mục bot,\n"
                f"   rồi bấm đúp {_LENH_DANG_NHAP} để đăng nhập 1 lần.")
        if not _co_nguoi_ngoi_may():
            raise LoiSheetCauHinh(
                f"Chưa đăng nhập Google (không có {token_path}).\n"
                f"   Bấm đúp {_LENH_DANG_NHAP} (hoặc: python {_LENH_DANG_NHAP}) để đăng nhập 1 lần.")
        print("🔑 Chưa có token.json → mở trình duyệt đăng nhập Google (chỉ 1 lần)...", flush=True)
        _dang_nhap(thu_muc)

    # Token hỏng / bị Google thu hồi → có người trước máy thì TỰ đăng nhập lại 1 lần.
    # Lỗi MẠNG lúc làm mới token thì KHÔNG bắt đăng nhập — chỉ là mạng chập chờn.
    for lan in (1, 2):
        try:
            creds = Credentials.from_authorized_user_file(token_path, SCOPES)
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            loi = None if (creds and creds.valid) else "token không còn hiệu lực"
        except RefreshError as e:
            loi = f"Google từ chối token ({e})"
        except (ValueError, KeyError) as e:
            loi = f"token.json hỏng ({e})"
        except Exception as e:
            raise LoiDocSheet(f"Không làm mới được token Google (mạng?): {e}")
        if loi is None:
            break
        if lan == 1 and os.path.exists(cred_path) and _co_nguoi_ngoi_may():
            print(f"🔑 {loi} → mở trình duyệt đăng nhập lại...", flush=True)
            _dang_nhap(thu_muc)
            continue
        raise LoiSheetCauHinh(
            f"Token Google không dùng được: {loi}\n"
            f"   Bấm đúp {_LENH_DANG_NHAP} để đăng nhập lại.")

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
        raise LoiDocSheet(f"Không đọc được ô phiên bản '{tab}'!B1: {e}")


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
        raise LoiDocSheet(f"Không đọc được tab '{tab}' của sheet tổng: {e}")


def nap_tu_bang(rows, bot_id=''):
    """Bảng thô → (phiên_bản, tài khoản đang Bật) đã qua MỌI bước kiểm. Không gọi mạng."""
    phien_ban, bang = phan_tich_bang(rows)
    bang = loc_dang_bat(bang)
    if not bang:
        raise LoiSheetCauHinh(
            f"Tab '{bot_id}': không tài khoản nào đang Bật (cột 'Bật' đều là N)")
    kiem_tra_du_khoa(bang)
    kiem_tra_du_lieu(bang)
    return phien_ban, bang


def nap(bot_id, spreadsheet_id):
    """
    Đọc trọn cấu hình cho một mã bot.

    Trả về (phiên_bản, {tên: {tham_số: giá_trị}}) — đã lọc tài khoản tắt, đã
    kiểm đủ khoá bắt buộc và soát dữ liệu từng ô.

    Lỗi thì NÉM LoiSheetCauHinh (lỗi mạng là LoiDocSheet — lớp con) để bot
    dừng hẳn lúc khởi động. Theo quyết định của khách: thà không chạy còn hơn
    chạy bằng cấu hình cũ mà tưởng là mới.
    """
    return nap_tu_bang(doc_bang_tho(spreadsheet_id, bot_id), bot_id)
