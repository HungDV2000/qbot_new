"""
Order State Tracker - Tracking trạng thái lệnh vào Google Sheet
Cập nhật các cột C,D,E,F,G theo từng sự kiện khớp lệnh
"""

import logging
import time
from datetime import datetime
from typing import Optional, Dict
import gg_sheet_factory
import cst
import rate_guard

# CHỐNG 429: thời gian nhớ tạm cột mã (A). Danh sách mã hầu như không đổi nên
# 60s là an toàn; các thao tác GHI vẫn luôn đọc lại thật (fresh=True).
ROW_CACHE_TTL = rate_guard.read_ttl(cst.config, 'row_cache_ttl_sec', 60.0, max_ttl=300.0)

logger = logging.getLogger(__name__)


class OrderStateTracker:
    """Tracking và cập nhật trạng thái lệnh vào Google Sheet"""
    
    def __init__(self, sheet_name: str):
        self.sheet_name = sheet_name
        self._row_cache = {}   # {(dòng_đầu, dòng_cuối): (thời_điểm, dữ_liệu)}
    
    def find_symbol_row(self, symbol: str, start_row: int = 4, end_row: int = 104,
                        fresh: bool = False) -> Optional[int]:
        """
        Tìm hàng của symbol trong sheet
        
        Args:
            symbol: Tên mã cần tìm
            start_row: Hàng bắt đầu tìm
            end_row: Hàng kết thúc tìm
            
        Returns:
            Số hàng (1-indexed) hoặc None nếu không tìm thấy
        """
        try:
            # CHỐNG 429: cột mã (A) hầu như không đổi, nên nhớ tạm vài chục giây.
            # Trước đây mỗi lần tra 1 mã là 1 lượt gọi API — vòng lặp qua N vị thế
            # tốn N lượt, cộng dồn 3 tài khoản là vượt hạn mức 60 lượt/phút.
            # fresh=True (các hàm GHI dùng) luôn đọc lại thật để không ghi nhầm dòng.
            ck = (start_row, end_row)
            now = time.time()
            hit = self._row_cache.get(ck)
            if (not fresh) and hit and (now - hit[0]) < ROW_CACHE_TTL:
                data = hit[1]
            else:
                data = gg_sheet_factory.get_dat_lenh(f"A{start_row}:A{end_row}")
                self._row_cache[ck] = (now, data)

            for idx, row in enumerate(data):
                if row and row[0] == symbol:
                    return start_row + idx
            return None
        except Exception as e:
            logger.error(f"Lỗi tìm symbol {symbol}: {e}")
            return None
    
    def update_order_filled(
        self,
        symbol: str,
        order_code: str,  # 1a, 1b, 1c, 2a...
        order_type: str,  # TRAILING STOP Long/Short, STOP LIMIT Long/Short...
        leverage: int,
        entry_price: float,
        order_id: str,
        start_row: int = 4,
        end_row: int = 104
    ) -> bool:
        """
        Cập nhật trạng thái khi lệnh khớp
        
        Updates:
            - Cột C: Lệnh vừa khớp (timestamp + Order ID)
            - Cột D: Mã lệnh hiện tại (1a, 1b, 1c...)
            - Cột E: Loại lệnh hiện tại
            - Cột F: Đòn bẩy đã khớp
            - Cột G: Giá vào đã khớp
            
        Returns:
            True nếu update thành công
        """
        try:
            # Tìm hàng của symbol
            row_num = self.find_symbol_row(symbol, start_row, end_row, fresh=True)
            if not row_num:
                logger.warning(f"Không tìm thấy {symbol} trong sheet")
                return False
            
            # Tạo timestamp
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            filled_info = f"{timestamp} | {order_id}"
            
            # Update từng cột
            updates = [
                (f"C{row_num}", filled_info),      # Cột C: Lệnh vừa khớp
                (f"D{row_num}", order_code),        # Cột D: Mã lệnh (1a, 1b...)
                (f"E{row_num}", order_type),        # Cột E: Loại lệnh
                (f"F{row_num}", str(leverage)),     # Cột F: Leverage
                (f"G{row_num}", str(entry_price))   # Cột G: Giá vào
            ]
            
            for cell, value in updates:
                gg_sheet_factory.update_single_value(self.sheet_name, cell, value)
            
            logger.info(f"✅ Đã cập nhật trạng thái cho {symbol} tại hàng {row_num}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Lỗi cập nhật trạng thái cho {symbol}: {e}")
            return False
    
    def update_next_order(
        self,
        symbol: str,
        next_order_code: str,  # 1b, 1c, 2a...
        next_order_type: str,
        start_row: int = 4,
        end_row: int = 104
    ) -> bool:
        """
        Cập nhật lệnh tiếp theo (cột H, I)
        
        Args:
            symbol: Tên mã
            next_order_code: Mã lệnh tiếp theo
            next_order_type: Loại lệnh tiếp theo
            
        Returns:
            True nếu update thành công
        """
        try:
            row_num = self.find_symbol_row(symbol, start_row, end_row, fresh=True)
            if not row_num:
                logger.warning(f"Không tìm thấy {symbol} trong sheet")
                return False
            
            updates = [
                (f"H{row_num}", next_order_code),    # Cột H: Mã lệnh tiếp theo
                (f"I{row_num}", next_order_type)     # Cột I: Loại lệnh tiếp theo
            ]
            
            for cell, value in updates:
                gg_sheet_factory.update_single_value(self.sheet_name, cell, value)
            
            logger.info(f"✅ Đã cập nhật lệnh tiếp theo cho {symbol}: {next_order_code}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Lỗi cập nhật lệnh tiếp theo cho {symbol}: {e}")
            return False
    
    def clear_filled_order(
        self,
        symbol: str,
        start_row: int = 4,
        end_row: int = 104
    ) -> bool:
        """
        Xóa thông tin lệnh vừa khớp (cột C) sau khi đã xử lý
        
        Returns:
            True nếu xóa thành công
        """
        try:
            row_num = self.find_symbol_row(symbol, start_row, end_row, fresh=True)
            if not row_num:
                return False
            
            gg_sheet_factory.update_single_value(self.sheet_name, f"C{row_num}", "")
            logger.info(f"✅ Đã xóa thông tin lệnh khớp cho {symbol}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Lỗi xóa thông tin lệnh khớp cho {symbol}: {e}")
            return False
    
    def get_current_state(
        self,
        symbol: str,
        start_row: int = 4,
        end_row: int = 104
    ) -> Optional[Dict]:
        """
        Lấy trạng thái hiện tại của một symbol
        
        Returns:
            Dict với keys: order_code, order_type, leverage, entry_price, filled_info
            hoặc None nếu không tìm thấy
        """
        try:
            row_num = self.find_symbol_row(symbol, start_row, end_row)
            if not row_num:
                return None
            
            # Đọc các cột C,D,E,F,G
            data = gg_sheet_factory.get_dat_lenh(f"C{row_num}:G{row_num}")
            if not data or not data[0]:
                return None
            
            row_data = data[0]
            return {
                'filled_info': row_data[0] if len(row_data) > 0 else "",      # Cột C
                'order_code': row_data[1] if len(row_data) > 1 else "",       # Cột D
                'order_type': row_data[2] if len(row_data) > 2 else "",       # Cột E
                'leverage': row_data[3] if len(row_data) > 3 else "",         # Cột F
                'entry_price': row_data[4] if len(row_data) > 4 else ""       # Cột G
            }
            
        except Exception as e:
            logger.error(f"❌ Lỗi lấy trạng thái cho {symbol}: {e}")
            return None
    
    def update_layer_num(
        self,
        symbol: str,
        layer_num: int,
        start_row: int = 4,
        end_row: int = 104
    ) -> bool:
        """
        Cập nhật số lớp hiện tại (cột B)
        
        Returns:
            True nếu update thành công
        """
        try:
            row_num = self.find_symbol_row(symbol, start_row, end_row, fresh=True)
            if not row_num:
                return False
            
            gg_sheet_factory.update_single_value(self.sheet_name, f"B{row_num}", str(layer_num))
            logger.info(f"✅ Đã cập nhật layer_num={layer_num} cho {symbol}")
            return True
            
        except Exception as e:
            logger.error(f"❌ Lỗi cập nhật layer_num cho {symbol}: {e}")
            return False


# Singleton instances
_tracker_long = None
_tracker_short = None

def get_tracker(side: str) -> OrderStateTracker:
    """
    Get singleton tracker instance cho LONG hoặc SHORT
    
    Args:
        side: "LONG" hoặc "SHORT"
        
    Returns:
        OrderStateTracker instance
    """
    global _tracker_long, _tracker_short
    
    if side == "LONG":
        if _tracker_long is None:
            _tracker_long = OrderStateTracker(gg_sheet_factory.tab_dat_lenh)
        return _tracker_long
    else:  # SHORT
        if _tracker_short is None:
            _tracker_short = OrderStateTracker(gg_sheet_factory.tab_dat_lenh)
        return _tracker_short

