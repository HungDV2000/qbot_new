"""
Notification Manager - Quản lý thông báo Telegram với format chuẩn
Theo QBot.md Section 6: TELEGRAM NOTIFICATION
"""

import logging
from datetime import datetime
from typing import Dict, Optional, List
import telegram_factory

logger = logging.getLogger(__name__)


class NotificationManager:
    """Quản lý các loại thông báo Telegram"""
    
    def __init__(self, chat_id: str):
        self.chat_id = chat_id
        self.last_balance_report_time = None
        self.last_pnl_percent = 0.0
    
    def send_order_filled(
        self,
        symbol: str,
        order_code: str,  # 1a, 1b, 1c, 2a...
        order_type: str,  # TRAILING STOP Long/Short, STOP LIMIT...
        entry_price: float,
        leverage: int,
        capital: float,
        position_value: float,
        next_orders: List[str] = None  # ['1b', '1c', '2a']
    ):
        """
        6.1.1 Thông báo lệnh khớp
        
        Args:
            symbol: Tên mã
            order_code: Mã lệnh (1a, 1b...)
            order_type: Loại lệnh
            entry_price: Giá vào
            leverage: Đòn bẩy
            capital: Vốn gốc
            position_value: Giá trị position
            next_orders: Danh sách lệnh tiếp theo đã tạo
        """
        next_orders_str = ", ".join(next_orders) if next_orders else "Không có"
        
        msg = f"""✅ <b>LỆNH KHỚP</b>

<b>Mã:</b> {symbol}
<b>Mã lệnh:</b> {order_code}
<b>Loại lệnh:</b> {order_type}
<b>Giá vào:</b> {entry_price:.8f}
<b>Đòn bẩy:</b> {leverage}x
<b>Vốn:</b> ${capital:.2f}
<b>Giá trị position:</b> ${position_value:.2f}
<b>Thời gian:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
<b>Lệnh tiếp theo:</b> {next_orders_str}"""
        
        try:
            telegram_factory.send_tele(msg, self.chat_id, True, True)
            logger.info(f"✅ Đã gửi thông báo lệnh khớp: {symbol} {order_code}")
        except Exception as e:
            logger.error(f"Lỗi gửi thông báo lệnh khớp: {e}")
    
    def send_order_error(
        self,
        symbol: str,
        order_code: str,
        error_code: str,
        error_message: str,
        action_taken: str
    ):
        """
        6.1.2 Thông báo lỗi đặt lệnh
        
        Args:
            symbol: Tên mã
            order_code: Mã lệnh
            error_code: Mã lỗi (VD: -4120)
            error_message: Chi tiết lỗi
            action_taken: Hành động đã thực hiện
        """
        msg = f"""🚨 <b>LỖI ĐẶT LỆNH</b>

<b>Mã:</b> {symbol}
<b>Mã lệnh:</b> {order_code}
<b>Mã lỗi:</b> {error_code}
<b>Chi tiết:</b> {error_message}
<b>Hành động:</b> {action_taken}
<b>Thời gian:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
        
        try:
            telegram_factory.send_tele(msg, self.chat_id, True, True)
            logger.info(f"🚨 Đã gửi thông báo lỗi: {symbol} {error_code}")
        except Exception as e:
            logger.error(f"Lỗi gửi thông báo lỗi đặt lệnh: {e}")
    
    def send_api_blocked(
        self,
        api_key_partial: str,
        blocked_symbol: str,
        reason: str,
        retry_wait_time: int
    ):
        """
        6.1.3 Thông báo API bị chặn
        
        Args:
            api_key_partial: API Key (hiển thị một phần)
            blocked_symbol: Mã bị chặn
            reason: Lý do
            retry_wait_time: Thời gian chờ retry (giây)
        """
        msg = f"""⛔ <b>BINANCE BLOCKED</b>

<b>API Key:</b> ...{api_key_partial[-8:]}
<b>Mã bị chặn:</b> {blocked_symbol}
<b>Lý do:</b> {reason}
<b>Retry sau:</b> {retry_wait_time}s
<b>Thời gian:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
        
        try:
            telegram_factory.send_tele(msg, self.chat_id, True, True)
            logger.info(f"⛔ Đã gửi thông báo API blocked: {blocked_symbol}")
        except Exception as e:
            logger.error(f"Lỗi gửi thông báo API blocked: {e}")
    
    def send_balance_report(
        self,
        wallet_balance: float,
        margin_balance: float,
        unrealized_pnl: float,
        unrealized_pnl_percent: float,
        open_positions_count: int,
        pending_orders_count: int,
        force_send: bool = False
    ):
        """
        6.1.4 Báo cáo số dư định kỳ
        
        Gửi khi:
        - 1 giờ/lần
        - PNL thay đổi > 5%
        - force_send = True
        
        Args:
            wallet_balance: Wallet Balance
            margin_balance: Margin Balance
            unrealized_pnl: Unrealized PNL (số tiền)
            unrealized_pnl_percent: Unrealized PNL (%)
            open_positions_count: Số vị thế đang mở
            pending_orders_count: Số lệnh chờ
            force_send: Bắt buộc gửi
        """
        # Kiểm tra điều kiện gửi
        should_send = force_send
        
        # Check 1h interval
        current_time = datetime.now()
        if self.last_balance_report_time:
            time_diff = (current_time - self.last_balance_report_time).total_seconds()
            if time_diff >= 3600:  # 1 hour
                should_send = True
        else:
            should_send = True
        
        # Check PNL change > 5%
        pnl_change = abs(unrealized_pnl_percent - self.last_pnl_percent)
        if pnl_change > 5.0:
            should_send = True
        
        if not should_send:
            return
        
        pnl_emoji = "📈" if unrealized_pnl >= 0 else "📉"
        
        msg = f"""📊 <b>BÁO CÁO SỐ DƯ</b>

<b>Wallet Balance:</b> ${wallet_balance:.2f}
<b>Margin Balance:</b> ${margin_balance:.2f}
<b>Unrealized PNL:</b> {pnl_emoji} ${unrealized_pnl:.2f} ({unrealized_pnl_percent:+.2f}%)
<b>Vị thế đang mở:</b> {open_positions_count}
<b>Lệnh chờ:</b> {pending_orders_count}
<b>Thời gian:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
        
        try:
            telegram_factory.send_tele(msg, self.chat_id, True, True)
            logger.info(f"📊 Đã gửi báo cáo số dư")
            
            # Update tracking
            self.last_balance_report_time = current_time
            self.last_pnl_percent = unrealized_pnl_percent
        except Exception as e:
            logger.error(f"Lỗi gửi báo cáo số dư: {e}")
    
    def send_stop_trigger(
        self,
        open_positions_count: int,
        pending_orders_count: int,
        current_pnl: float
    ):
        """
        6.1.5 Kích hoạt lệnh STOP
        
        Args:
            open_positions_count: Số vị thế đang mở
            pending_orders_count: Số lệnh chờ
            current_pnl: PNL hiện tại
        """
        msg = f"""🛑 <b>LỆNH STOP KÍCH HOẠT</b>

<b>Trạng thái:</b> Đang xử lý...
<b>Vị thế đang mở:</b> {open_positions_count}
<b>Lệnh chờ:</b> {pending_orders_count}
<b>PNL hiện tại:</b> ${current_pnl:.2f}
<b>Thời gian:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

<i>Đang đóng tất cả vị thế và hủy tất cả lệnh...</i>"""
        
        try:
            telegram_factory.send_tele(msg, self.chat_id, True, True)
            logger.info(f"🛑 Đã gửi thông báo STOP trigger")
        except Exception as e:
            logger.error(f"Lỗi gửi thông báo STOP trigger: {e}")
    
    def send_stop_completed(
        self,
        closed_positions_count: int,
        cancelled_orders_count: int,
        final_balance: float,
        total_pnl: float
    ):
        """
        6.1.6 Xác nhận hoàn tất STOP
        
        Args:
            closed_positions_count: Số vị thế đã đóng
            cancelled_orders_count: Số lệnh đã hủy
            final_balance: Số dư cuối
            total_pnl: Tổng lãi/lỗ
        """
        pnl_emoji = "💰" if total_pnl >= 0 else "💸"
        
        msg = f"""✅ <b>HOÀN TẤT STOP</b>

<b>Vị thế đã đóng:</b> {closed_positions_count}
<b>Lệnh đã hủy:</b> {cancelled_orders_count}
<b>Số dư cuối:</b> ${final_balance:.2f}
<b>Tổng lãi/lỗ:</b> {pnl_emoji} ${total_pnl:.2f}
<b>Thời gian:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

<i>Bot đã dừng hoạt động.</i>"""
        
        try:
            telegram_factory.send_tele(msg, self.chat_id, True, True)
            logger.info(f"✅ Đã gửi thông báo STOP completed")
        except Exception as e:
            logger.error(f"Lỗi gửi thông báo STOP completed: {e}")
    
    def send_reduce_only_warning(
        self,
        symbol: str,
        remaining_orders_count: int,
        order_ids: List[str],
        retry_attempt: int,
        max_retries: int
    ):
        """
        6.1.7 Cảnh báo Reduce Only sót
        
        Args:
            symbol: Tên mã
            remaining_orders_count: Số lệnh sót
            order_ids: Danh sách Order IDs
            retry_attempt: Lần retry hiện tại
            max_retries: Số lần retry tối đa
        """
        order_ids_str = "\n".join([f"  • {oid}" for oid in order_ids[:5]])  # Max 5 orders
        if len(order_ids) > 5:
            order_ids_str += f"\n  • ... và {len(order_ids) - 5} lệnh khác"
        
        msg = f"""⚠️ <b>REDUCE ONLY SÓT</b>

<b>Mã:</b> {symbol}
<b>Số lệnh sót:</b> {remaining_orders_count}
<b>Order IDs:</b>
{order_ids_str}
<b>Trạng thái:</b> Đang retry {retry_attempt}/{max_retries}
<b>Thời gian:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
        
        try:
            telegram_factory.send_tele(msg, self.chat_id, True, True)
            logger.info(f"⚠️ Đã gửi cảnh báo Reduce Only sót: {symbol}")
        except Exception as e:
            logger.error(f"Lỗi gửi cảnh báo Reduce Only sót: {e}")
    
    def send_critical_warning(
        self,
        issue_description: str,
        manual_intervention_needed: bool,
        related_symbols: List[str] = None,
        related_order_ids: List[str] = None
    ):
        """
        6.1.8 Cảnh báo nghiêm trọng
        
        Args:
            issue_description: Mô tả vấn đề
            manual_intervention_needed: Yêu cầu can thiệp thủ công
            related_symbols: Các mã liên quan
            related_order_ids: Các Order IDs liên quan
        """
        symbols_str = ", ".join(related_symbols) if related_symbols else "N/A"
        orders_str = "\n".join([f"  • {oid}" for oid in (related_order_ids or [])[:5]])
        if related_order_ids and len(related_order_ids) > 5:
            orders_str += f"\n  • ... và {len(related_order_ids) - 5} lệnh khác"
        
        intervention_text = "⚠️ CẦN CAN THIỆP THỦ CÔNG NGAY!" if manual_intervention_needed else ""
        
        msg = f"""🔴 <b>CẢNH BÁO NGHIÊM TRỌNG</b>

<b>Vấn đề:</b> {issue_description}
{intervention_text}

<b>Mã liên quan:</b> {symbols_str}
<b>Order IDs:</b>
{orders_str if orders_str else "  N/A"}
<b>Thời gian:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
        
        try:
            telegram_factory.send_tele(msg, self.chat_id, True, True)
            logger.critical(f"🔴 Đã gửi cảnh báo nghiêm trọng: {issue_description}")
        except Exception as e:
            logger.error(f"Lỗi gửi cảnh báo nghiêm trọng: {e}")
    
    def send_position_opened(self, symbol: str):
        """Thông báo đã thêm vị thế (đã có sẵn, giữ nguyên)"""
        msg = f"✅ Đã Thêm Vị Thế: {symbol}"
        try:
            telegram_factory.send_tele(msg, self.chat_id, True, True)
        except Exception as e:
            logger.error(f"Lỗi gửi thông báo vị thế mở: {e}")
    
    def send_position_closed(self, symbol: str, pnl: float = None):
        """Thông báo đã đóng vị thế (đã có sẵn, giữ nguyên)"""
        if pnl is not None:
            emoji = "💰" if pnl >= 0 else "💸"
            msg = f"{emoji} Đã Đóng Vị Thế: {symbol} | PNL: ${pnl:.2f}"
        else:
            msg = f"Đã Đóng Vị Thế: {symbol}"
        
        try:
            telegram_factory.send_tele(msg, self.chat_id, True, True)
        except Exception as e:
            logger.error(f"Lỗi gửi thông báo vị thế đóng: {e}")
    
    def send_bot_status(self, status: str, details: str = ""):
        """Thông báo trạng thái bot"""
        msg = f"""ℹ️ <b>TRẠNG THÁI BOT</b>

<b>Status:</b> {status}
<b>Chi tiết:</b> {details if details else 'N/A'}
<b>Thời gian:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
        
        try:
            telegram_factory.send_tele(msg, self.chat_id, True, True)
            logger.info(f"ℹ️ Đã gửi trạng thái bot: {status}")
        except Exception as e:
            logger.error(f"Lỗi gửi trạng thái bot: {e}")


# Singleton instance
_notification_manager = None

def get_notification_manager(chat_id: str) -> NotificationManager:
    """Get singleton instance"""
    global _notification_manager
    if _notification_manager is None:
        _notification_manager = NotificationManager(chat_id)
    return _notification_manager

