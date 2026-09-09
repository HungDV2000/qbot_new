import datetime
from pathlib import Path

def convert_unix_timestamp(timestamp):
    
    dt_object = datetime.datetime.fromtimestamp(timestamp)

    
    formatted_time = dt_object.strftime("%m/%d/%Y %H:%M:%S")

    return formatted_time









def get_all_open_orders_symbol_local():
    """
    Lấy danh sách symbols từ thư mục 'order' local (nếu có)
    Nếu thư mục không tồn tại, return empty list (không crash)
    """
    fn = 'order'
    res = []
    
    # Fix: Kiểm tra thư mục tồn tại trước khi đọc
    order_path = Path(fn)
    if not order_path.exists() or not order_path.is_dir():
        # Thư mục không tồn tại, return empty list (không crash)
        return res
    
    try:
        for folder in order_path.iterdir():
            if folder.is_dir():
                subfolders = [subfolder for subfolder in folder.iterdir() if subfolder.is_dir()]
                for subfolder in subfolders:
                    # Fix: Dùng pathlib để cross-platform
                    symbol = str(subfolder).replace(f"{fn}/", "").replace(f"{fn}\\", "").replace("\\", "/")
                    res.append(symbol)
    except (OSError, PermissionError) as e:
        # Nếu có lỗi khi đọc, return empty list thay vì crash
        print(f"Warning: Không thể đọc thư mục 'order': {e}")
        return res
    
    return res
