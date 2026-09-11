import giu_cua_so  # PHẢI nạp ĐẦU TIÊN: dừng/lỗi thì giữ cửa sổ Windows để đọc thông báo
"""
ĐĂNG NHẬP GOOGLE — chạy 1 LẦN trên máy mới để sinh token.json.

    Bấm đúp file này   (hoặc: python dang_nhap_google.py)

Cần có credentials.json (OAuth client, loại "Desktop app", tải từ Google Cloud
Console) cạnh file này. Trình duyệt sẽ mở ra: chọn tài khoản Google ĐÃ ĐƯỢC CHIA
SẺ quyền Editor sheet tổng và sheet của các tài khoản, bấm Cho phép. Xong thì
token.json được ghi cạnh file này — mọi bot dùng chung.

Vì sao cần file riêng: bot nào khởi động cũng đọc SHEET TỔNG trước tiên; thiếu
token.json thì bot dừng ngay, không bao giờ tới được bước đăng nhập.
"""
import os
import sys
import tempfile

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]
THU_MUC = os.path.dirname(os.path.abspath(__file__))


def dang_nhap(thu_muc=THU_MUC):
    """Mở trình duyệt đăng nhập Google, ghi token.json. Trả đường dẫn token."""
    token_path = os.path.join(thu_muc, 'token.json')
    cred_path = os.path.join(thu_muc, 'credentials.json')
    if not os.path.exists(cred_path):
        raise FileNotFoundError(
            f"Thiếu {cred_path}.\n"
            f"   Tải từ Google Cloud Console → APIs & Services → Credentials →\n"
            f"   OAuth client ID loại \"Desktop app\" → Download JSON, đổi tên thành\n"
            f"   credentials.json rồi chép vào thư mục bot.")
    from google_auth_oauthlib.flow import InstalledAppFlow
    print("🌐 Đang mở trình duyệt để đăng nhập Google...", flush=True)
    print("   Chọn tài khoản Google ĐÃ ĐƯỢC CHIA SẺ quyền Editor các sheet, bấm Cho phép.", flush=True)
    creds = InstalledAppFlow.from_client_secrets_file(cred_path, SCOPES).run_local_server(port=0)

    # Ghi ra file tạm rồi đổi tên — không bao giờ để lại token.json dở dang
    fd, tam = tempfile.mkstemp(dir=thu_muc, prefix=".token_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as f:
            f.write(creds.to_json())
        os.replace(tam, token_path)
    except Exception:
        try:
            os.unlink(tam)
        except OSError:
            pass
        raise
    print(f"✅ Đã lưu {token_path}", flush=True)
    return token_path


def main():
    print("=" * 60)
    print("  ĐĂNG NHẬP GOOGLE CHO QBOT")
    print("=" * 60)
    token_path = os.path.join(THU_MUC, 'token.json')
    if os.path.exists(token_path):
        tl = input(f"Đã có {token_path}.\nĐăng nhập lại (ghi đè)? [y/N] ").strip().lower()
        if tl not in ('y', 'yes', 'c', 'co', 'có'):
            print("Giữ nguyên token.json hiện có.")
            return 0
    try:
        dang_nhap()
    except Exception as e:
        print(f"\n❌ Đăng nhập không xong: {e}")
        return 1
    print("\nXong. Giờ chạy kiem_tra_cau_hinh.py để soát cấu hình.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
