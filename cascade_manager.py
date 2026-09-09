"""
Cascade Manager - Quản lý logic cascade đa lớp cho QBot
Xử lý flow: 1a → 1b+1c+2a → 2b+2c+3a → ...
"""

import logging
import ccxt
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from pathlib import Path
import gg_sheet_factory
import cst
import binance_utils
import os
import sys

# --- CẤU HÌNH LOGGING (GHI VÀO 1 FILE DUY NHẤT) ---
# Tạo thư mục logs/ nếu chưa có
logs_dir = Path('logs')
logs_dir.mkdir(exist_ok=True)
log_filename = logs_dir / "cascade_manager.txt"

# Cấu hình logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Kiểm tra handler để tránh duplicate log khi reload
if not logger.handlers:
    try:
        # mode='a': Append (Nối tiếp vào file cũ, không xóa log cũ)
        # encoding='utf-8': Hỗ trợ tiếng Việt
        file_handler = logging.FileHandler(log_filename, mode='a', encoding='utf-8')
        
        # Format: Năm-Tháng-Ngày Giờ:Phút:Giây - Mức độ - Nội dung
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        file_handler.setFormatter(formatter)
        
        logger.addHandler(file_handler)
        print(f"📝 [LOG] Đã kết nối file log: {log_filename}", flush=True)
    except Exception as e:
        print(f"⚠️ [LOG ERROR] Không thể mở file log: {e}", flush=True)


class OrderState:
    """Trạng thái lệnh"""
    WAITING = "CHỜ"         # Lệnh chờ khớp
    FILLED = "KHỚP"         # Lệnh đã khớp
    CANCELLED = "HỦY"       # Lệnh đã hủy
    FAILED = "LỖI"          # Lệnh lỗi


class LayerInfo:
    """Thông tin một lớp lệnh"""
    def __init__(self, layer_num: int, symbol: str):
        self.layer_num = layer_num
        self.symbol = symbol
        self.entry_order = None      # Order 'a' (1a, 2a, 3a...)
        self.sl_order = None          # Order 'b' (1b, 2b, 3b...)
        self.tp_order = None          # Order 'c' (1c, 2c, 3c...)
        self.entry_filled = False
        self.entry_price = None
        self.leverage = None
        self.position_amt = None


class CascadeManager:
    """Quản lý logic cascade đa lớp"""
    
    def __init__(self, exchange: ccxt.binance, order_helper):
        self.exchange = exchange
        self.order_helper = order_helper
        self.layers = {}  # {symbol: {layer_num: LayerInfo}}
    
    def get_tick_size_from_filter(self, symbol: str) -> float:
        """
        Lấy tick size (bước giá tối thiểu) từ Binance
        
        ⚠️ LƯU Ý: 
        - CCXT precision['price'] = TICK SIZE (bước giá, VD: 0.001, 0.01, 0.1)
        - limits['price']['min'] = MIN PRICE (giá tối thiểu giao dịch, VD: 0.01, 556.8)
        → KHÔNG NÊN LẤY limits['price']['min'] làm tick_size!
        
        Returns:
            float: Tick size (bước giá), mặc định 0.001 nếu không tìm thấy
        """
        try:
            # Kiểm tra exchange type
            is_futures = self.exchange.options.get('defaultType') == 'future'
            
            logger.info(f"   🔍 Tìm tick_size cho: {symbol} (Exchange type: {'Futures' if is_futures else 'Spot'})")
            
            symbol_to_check = symbol
            
            # NÊU LÀ FUTURES: ƯU TIÊN tìm version có :USDT (XXX/USDT:USDT)
            if is_futures:
                # Nếu symbol chưa có :USDT, thử thêm vào
                if ':USDT' not in symbol and symbol.endswith('/USDT'):
                    futures_symbol = f"{symbol}:USDT"
                    if futures_symbol in self.exchange.markets:
                        symbol_to_check = futures_symbol
                        logger.info(f"   ✅ Tìm thấy Futures market: {symbol_to_check}")
                    else:
                        logger.info(f"   ⚠️ Không có {futures_symbol}, dùng {symbol}")
                # Nếu symbol đã có :USDT, giữ nguyên
                elif ':USDT' in symbol:
                    if symbol in self.exchange.markets:
                        symbol_to_check = symbol
                        logger.info(f"   ✅ Dùng Futures market: {symbol_to_check}")
                    else:
                        # Thử bỏ :USDT
                        spot_symbol = symbol.replace(':USDT', '')
                        if spot_symbol in self.exchange.markets:
                            symbol_to_check = spot_symbol
                            logger.warning(f"   ⚠️ Không có {symbol}, fallback sang Spot: {symbol_to_check}")
                # Nếu symbol không có /USDT, thử thêm
                else:
                    if symbol in self.exchange.markets:
                        symbol_to_check = symbol
                        logger.info(f"   ✅ Dùng market: {symbol_to_check}")
            else:
                # SPOT: Ưu tiên version không có :USDT
                if ':USDT' in symbol:
                    spot_symbol = symbol.replace(':USDT', '')
                    if spot_symbol in self.exchange.markets:
                        symbol_to_check = spot_symbol
                        logger.info(f"   ✅ Dùng Spot market: {symbol_to_check}")
                    elif symbol in self.exchange.markets:
                        symbol_to_check = symbol
                        logger.info(f"   ✅ Dùng market: {symbol_to_check}")
                else:
                    if symbol in self.exchange.markets:
                        symbol_to_check = symbol
                        logger.info(f"   ✅ Dùng market: {symbol_to_check}")
            
            # Kiểm tra cuối cùng
            if symbol_to_check not in self.exchange.markets:
                logger.warning(f"   ❌ Không tìm thấy {symbol_to_check} trong markets")
                logger.warning(f"   📋 Markets mẫu: {list(self.exchange.markets.keys())[:5]}...")
                return 0.001
            
            market = self.exchange.markets[symbol_to_check]
            logger.info(f"   📊 Sử dụng market: {symbol_to_check}")
            
            # ƯU TIÊN 1: Lấy từ CCXT precision['price'] 
            # → Đây chính là TICK SIZE từ Binance, đã được CCXT parse sẵn
            tick_size = market.get('precision', {}).get('price')
            if tick_size and tick_size > 0:
                logger.info(f"   📍 ✅ Tick size từ CCXT precision['{symbol_to_check}']: {tick_size}")
                return float(tick_size)
            
            # FALLBACK: Lấy từ PRICE_FILTER trong info (raw data từ Binance)
            info = market.get('info', {})
            filters = info.get('filters', [])
            
            for f in filters:
                if f.get('filterType') == 'PRICE_FILTER':
                    tick_size_raw = f.get('tickSize')
                    if tick_size_raw:
                        tick_size = float(tick_size_raw)
                        if tick_size > 0:
                            logger.info(f"   📍 ✅ Tick size từ PRICE_FILTER['{symbol_to_check}']: {tick_size}")
                            return tick_size
            
            logger.warning(f"   ⚠️ Không tìm thấy tick_size cho {symbol_to_check} → Dùng mặc định 0.001")
            logger.warning(f"   📊 Market info: {market.get('info', {}).get('symbol', 'N/A')}")
            return 0.001
            
        except Exception as e:
            logger.warning(f"⚠️ Lỗi lấy tick_size cho {symbol}: {e} → Dùng mặc định = 0.001")
            import traceback
            logger.warning(traceback.format_exc())
            return 0.001
    
    def get_price_precision(self, symbol: str) -> int:
        """
        Lấy độ chính xác giá từ tick_size
        """
        try:
            tick_size = self.get_tick_size_from_filter(symbol)
            
            # Đếm số chữ số thập phân
            tick_str = f"{tick_size:.10f}".rstrip('0').rstrip('.')
            if '.' in tick_str:
                precision = len(tick_str.split('.')[1])
            else:
                precision = 0
            
            return precision
        except Exception as e:
            logger.warning(f"⚠️ Không tính được precision: {e} → Dùng mặc định = 3")
            return 3
    
    def smart_round_price(self, price: float, symbol: str, is_sl: bool, is_long: bool) -> float:
        """
        Làm tròn giá thông minh dựa trên tick_size
        
        Args:
            price: Giá cần làm tròn
            symbol: Mã coin
            is_sl: True = Stop Loss, False = Take Profit
            is_long: True = LONG, False = SHORT
        
        Returns:
            Giá đã làm tròn
        """
        from decimal import Decimal, ROUND_DOWN, ROUND_UP, ROUND_HALF_UP
        
        tick_size = self.get_tick_size_from_filter(symbol)
        precision = self.get_price_precision(symbol)
        
        logger.info(f"   📏 Tick Size: {tick_size}, Precision: {precision}")
        
        # Chuyển sang Decimal để tránh lỗi floating point
        price_decimal = Decimal(str(price))
        tick_decimal = Decimal(str(tick_size))
        
        # --- LOGIC: LUÔN ÁP DỤNG SMART ROUNDING CHO SL ---
        if is_sl:
            # STOP LOSS: Làm tròn để CẮT LỖ SỚM HƠN (bảo vệ vốn)
            if is_long:
                # LONG SL: Làm tròn XUỐNG (giá thấp hơn → trigger sớm hơn)
                rounded_decimal = (price_decimal / tick_decimal).quantize(Decimal('1'), rounding=ROUND_DOWN) * tick_decimal
                method = "FLOOR (LONG SL - Bảo vệ vốn)"
            else:
                # SHORT SL: Làm tròn LÊN (giá cao hơn → trigger sớm hơn)
                rounded_decimal = (price_decimal / tick_decimal).quantize(Decimal('1'), rounding=ROUND_UP) * tick_decimal
                method = "CEIL (SHORT SL - Bảo vệ vốn)"
            logger.info(f"   🎯 [SL ROUNDING] Precision={precision} → {method}")
        else:
            # TAKE PROFIT: Làm tròn GẦN NHẤT (activation gần với strategy, trailing sẽ tối ưu lời)
            rounded_decimal = (price_decimal / tick_decimal).quantize(Decimal('1'), rounding=ROUND_HALF_UP) * tick_decimal
            method = "NEAREST (TP - Gần strategy)"
            logger.info(f"   🎯 [TP ROUNDING] Precision={precision} → {method}")
        
        rounded = float(rounded_decimal)
        
        # Tính % chênh lệch
        diff_percent = abs((rounded - price) / price * 100) if price > 0 else 0
        
        logger.info(f"   📊 Giá gốc: {price:.8f} → Giá sau làm tròn: {rounded:.8f} (Chênh lệch: {diff_percent:.4f}%)")
        
        return rounded

    def get_mark_or_last_price(self, symbol: str) -> tuple:
        """Ưu tiên markPrice (Futures), fallback last."""
        ticker = self.exchange.fetch_ticker(symbol)
        info = ticker.get('info') or {}
        for key in ('markPrice', 'indexPrice', 'lastPrice'):
            raw = info.get(key)
            if raw is not None and str(raw).strip() not in ('', '0'):
                try:
                    p = float(raw)
                    if p > 0:
                        return p, key
                except (TypeError, ValueError):
                    pass
        last = ticker.get('last')
        if last is not None and float(last) > 0:
            return float(last), 'last'
        raise ValueError(f'Không lấy được mark/last cho {symbol}')

    def clamp_binance_callback_rate(self, callback_rate: float) -> float:
        """Binance TRAILING_STOP: callbackRate 0.1–10 (1 = 1%)."""
        r = float(callback_rate)
        if r <= 0:
            r = 1.0
        if r < 0.1:
            logger.warning(f'callback_rate {r} < 0.1 → clamp 0.1')
            r = 0.1
        if r > 10:
            logger.warning(f'callback_rate {r} > 10 → clamp 10')
            r = 10.0
        return r

    def resolve_trailing_activation_immediate(self, symbol: str, side: str) -> float:
        """
        Giá kích hoạt TP trailing ngay (phương án A).
        LONG (đóng SELL): activation <= mark → dùng mark - 1 tick.
        SHORT (đóng BUY): activation >= mark → dùng mark + 1 tick.
        """
        mark, src = self.get_mark_or_last_price(symbol)
        tick = self.get_tick_size_from_filter(symbol)
        is_long = side == 'LONG'
        if is_long:
            raw = max(tick, mark - tick)
        else:
            raw = mark + tick
        activation = self.smart_round_price(
            price=raw, symbol=symbol, is_sl=False, is_long=is_long,
        )
        logger.info(
            f'   [TP NGAY] {symbol} {side}: {src}={mark} → activatePrice={activation} (tick={tick})'
        )
        return activation
    
    def get_or_create_layer(self, symbol: str, layer_num: int) -> LayerInfo:
        """Lấy hoặc tạo mới LayerInfo"""
        if symbol not in self.layers:
            self.layers[symbol] = {}
        
        if layer_num not in self.layers[symbol]:
            self.layers[symbol][layer_num] = LayerInfo(layer_num, symbol)
        
        return self.layers[symbol][layer_num]
    
    def on_entry_filled(
        self,
        symbol: str,
        layer_num: int,
        entry_price: float,
        leverage: int,
        position_amt: float,
        side: str,  # 'LONG' or 'SHORT'
        max_layers: int,
        lenh2_rate: float,
        lenh3_rate: float,
        lenh3_callback_rate: float,
        next_layer_config: Optional[Dict] = None
    ) -> Dict:
        """
        Xử lý khi lệnh entry (1a, 2a, 3a...) được khớp
        Tự động tạo SL + TP + Entry lớp tiếp theo
        """
        logger.info(f"🎯 Entry lớp {layer_num} đã khớp: {symbol} @ {entry_price}")
        
        # Lưu thông tin lớp
        layer = self.get_or_create_layer(symbol, layer_num)
        layer.entry_filled = True
        layer.entry_price = entry_price
        layer.leverage = leverage
        layer.position_amt = position_amt
        
        result = {
            'sl_order': None,
            'tp_order': None,
            'next_entry_order': None
        }
        
        # 1. Tạo Stop Loss (lệnh b: 1b, 2b, 3b...)
        try:
            sl_order = self._create_stop_loss(
                symbol, layer_num, entry_price, position_amt, 
                side, leverage, lenh2_rate
            )
            layer.sl_order = sl_order
            result['sl_order'] = sl_order
            logger.info(f"✅ Đã tạo SL lớp {layer_num}: Order ID {sl_order.get('id')}")
        except Exception as e:
            logger.error(f"❌ Lỗi tạo SL lớp {layer_num}: {e}", exc_info=True)
            import traceback
            logger.error(f"❌ Traceback SL lớp {layer_num}:\n{traceback.format_exc()}")
        
        # 2. Tạo Take Profit (lệnh c: 1c, 2c, 3c...)
        try:
            tp_order = self._create_take_profit(
                symbol, layer_num, entry_price, position_amt,
                side, leverage, lenh3_rate, lenh3_callback_rate
            )
            layer.tp_order = tp_order
            result['tp_order'] = tp_order
            logger.info(f"✅ Đã tạo TP lớp {layer_num}: Order ID {tp_order.get('id')}")
        except Exception as e:
            import traceback as tb
            logger.error(f"❌ Lỗi tạo TP lớp {layer_num}: {e}")
            logger.error(f"❌ Traceback TP lớp {layer_num}:\n{tb.format_exc()}")
        
        # 3. Tạo Entry lớp tiếp theo (nếu chưa đạt max_layers)
        next_layer_num = layer_num + 1
        if next_layer_num <= max_layers and next_layer_config:
            try:
                next_entry = self._create_next_entry(
                    symbol, next_layer_num, side, next_layer_config
                )
                result['next_entry_order'] = next_entry
                logger.info(f"✅ Đã tạo Entry lớp {next_layer_num}: Order ID {next_entry.get('id')}")
            except Exception as e:
                logger.error(f"❌ Lỗi tạo Entry lớp {next_layer_num}: {e}")
        else:
            logger.info(f"⚠️ Không tạo lớp {next_layer_num} (max_layers={max_layers})")
        
        # [LOG TỔNG HỢP KẾT QUẢ]
        logger.info(f"=" * 50)
        logger.info(f"🎯 [TỔNG KẾT CASCADE LỚP {layer_num}] {symbol}")
        logger.info(f"   Entry Price: {entry_price}")
        logger.info(f"   Position Amount: {position_amt}")
        logger.info(f"   Side: {side}")
        logger.info(f"   SL Order: {'✅ ' + str(result['sl_order'].get('id')) if result['sl_order'] else '❌ Thất bại'}")
        logger.info(f"   TP Order: {'✅ ' + str(result['tp_order'].get('id')) if result['tp_order'] else '❌ Thất bại'}")
        if result['next_entry_order']:
            logger.info(f"   Next Entry: ✅ {result['next_entry_order'].get('id')}")
        logger.info(f"=" * 50)
        
        return result
    
    def _create_stop_loss(
        self,
        symbol: str,
        layer_num: int,
        entry_price: float,
        position_amt: float,
        side: str,
        leverage: int,
        lenh2_rate: float
    ) -> Dict:
        """Tạo lệnh Stop Loss (reduce only)"""
        is_long = (side == 'LONG')
        
        # --- [LOG DEBUG CHI TIẾT VÀO FILE] ---
        logger.info(f"--------------------------------------------------")
        logger.info(f"📐 [TÍNH TOÁN STOP LOSS] {symbol} ({side})")
        logger.info(f"   - Entry Price: {entry_price}")
        logger.info(f"   - Tỷ lệ SL (lenh2_rate): {lenh2_rate}")
        
        # Tính stop price
        if is_long:
            stop_price_raw = entry_price * (1 - lenh2_rate)
            order_side = 'sell'
            logger.info(f"   - Công thức LONG: {entry_price} * (1 - {lenh2_rate}) = {stop_price_raw}")
        else:
            stop_price_raw = entry_price * (1 + lenh2_rate)
            order_side = 'buy'
            logger.info(f"   - Công thức SHORT: {entry_price} * (1 + {lenh2_rate}) = {stop_price_raw}")
        
        # Validate giá trước khi làm tròn
        if stop_price_raw <= 0:
            logger.error(f"   ❌ Lỗi: Giá SL tính ra <= 0 ({stop_price_raw})")
            raise ValueError(f"Stop price tính được = {stop_price_raw} (phải > 0). Entry: {entry_price}, Rate: {lenh2_rate}")
        
        # [NEW] Làm tròn THÔNG MINH
        stop_price = self.smart_round_price(
            price=stop_price_raw,
            symbol=symbol,
            is_sl=True,  # Đây là Stop Loss
            is_long=is_long
        )
        
        if stop_price <= 0:
            raise ValueError(f"Stop price sau khi làm tròn = {stop_price} (phải > 0). Giá gốc: {stop_price_raw}")
        
        # [VALIDATION] Kiểm tra logic so với giá hiện tại
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            logger.info(f"   - Giá hiện tại (current): {current_price}")
            
            # LONG: stop_price phải < current_price (chờ giá giảm xuống)
            # SHORT: stop_price phải > current_price (chờ giá tăng lên)
            if is_long:
                if stop_price >= current_price:
                    logger.error(f"   ❌ SL LONG: stop_price={stop_price} >= current={current_price} → Trigger ngay!")
                    raise ValueError(f"SL LONG sai logic: stop_price={stop_price} phải < current_price={current_price}")
            else:
                if stop_price <= current_price:
                    logger.error(f"   ❌ SL SHORT: stop_price={stop_price} <= current={current_price} → Trigger ngay!")
                    raise ValueError(f"SL SHORT sai logic: stop_price={stop_price} phải > current_price={current_price}")
            
            logger.info(f"   ✅ Validation OK: SL logic đúng với giá hiện tại")
        except ccxt.NetworkError as e:
            logger.warning(f"   ⚠️ Không lấy được giá hiện tại: {e} - Bỏ qua validation")
        
        # [A1] STOP_MARKET đảm bảo cắt lỗ LUÔN khớp khi giá gap/biến động mạnh
        logger.info(f"   -> Đang gửi lệnh STOP_MARKET {order_side} giá trigger {stop_price}")

        # [LOG DATA GỬI LÊN BINANCE]
        logger.info(f"📤 [DATA GỬI - STOP LOSS]")
        logger.info(f"   Symbol: {symbol}")
        logger.info(f"   Side: {order_side}")
        logger.info(f"   Amount: {abs(position_amt)}")
        logger.info(f"   Stop Price (trigger): {stop_price}")
        logger.info(f"   Reduce Only: True")
        logger.info(f"   Type: STOP_MARKET")

        order = self.order_helper.create_stop_market_order(
            symbol=symbol,
            side=order_side,
            amount=abs(position_amt),
            stop_price=stop_price,
            reduce_only=True
        )
        
        logger.info(f"✅ [RESPONSE - STOP LOSS] Order ID: {order.get('id')}, Status: {order.get('status')}")
        
        return order
    
    def _create_take_profit(
        self,
        symbol: str,
        layer_num: int,
        entry_price: float,
        position_amt: float,
        side: str,
        leverage: int,
        lenh3_rate: float,
        callback_rate: float
    ) -> Dict:
        """Tạo lệnh Take Profit (reduce only, trailing stop)"""
        is_long = (side == 'LONG')
        
        # --- [LOG DEBUG CHI TIẾT VÀO FILE] ---
        logger.info(f"--------------------------------------------------")
        logger.info(f"📐 [TÍNH TOÁN TAKE PROFIT] {symbol} ({side})")
        logger.info(f"   - Entry Price: {entry_price}")
        logger.info(f"   - Tỷ lệ TP (lenh3_rate): {lenh3_rate}")
        
        # Tính activation price
        if is_long:
            activation_price_raw = entry_price * (1 + lenh3_rate)
            order_side = 'sell'
            logger.info(f"   - Công thức LONG: {entry_price} * (1 + {lenh3_rate}) = {activation_price_raw}")
        else:
            activation_price_raw = entry_price * (1 - lenh3_rate)
            order_side = 'buy'
            logger.info(f"   - Công thức SHORT: {entry_price} * (1 - {lenh3_rate}) = {activation_price_raw}")
        
        # Validate
        if activation_price_raw <= 0:
            logger.error(f"   ❌ Lỗi: Giá TP tính ra <= 0 ({activation_price_raw})")
            raise ValueError(f"Activation price tính được = {activation_price_raw} (phải > 0). Entry: {entry_price}, Rate: {lenh3_rate}")
        
        # [NEW] Làm tròn THÔNG MINH
        activation_price = self.smart_round_price(
            price=activation_price_raw,
            symbol=symbol,
            is_sl=False,  # Đây là Take Profit
            is_long=is_long
        )
        
        if activation_price <= 0:
            raise ValueError(f"Activation price sau khi làm tròn = {activation_price} (phải > 0). Giá gốc: {activation_price_raw}")
        
        # [VALIDATION] Kiểm tra logic so với giá hiện tại
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            current_price = ticker['last']
            logger.info(f"   - Giá hiện tại (current): {current_price}")
            
            # LONG: activation_price phải > current_price (chờ giá tăng lên)
            # SHORT: activation_price phải < current_price (chờ giá giảm xuống)
            if is_long:
                if activation_price <= current_price:
                    logger.error(f"   ❌ TP LONG: activation={activation_price} <= current={current_price} → Trigger ngay!")
                    raise ValueError(f"TP LONG sai logic: activation_price={activation_price} phải > current_price={current_price}")
            else:
                if activation_price >= current_price:
                    logger.error(f"   ❌ TP SHORT: activation={activation_price} >= current={current_price} → Trigger ngay!")
                    raise ValueError(f"TP SHORT sai logic: activation_price={activation_price} phải < current_price={current_price}")
            
            logger.info(f"   ✅ Validation OK: TP logic đúng với giá hiện tại")
        except ccxt.NetworkError as e:
            logger.warning(f"   ⚠️ Không lấy được giá hiện tại: {e} - Bỏ qua validation")
        
        logger.info(f"   -> Đang gửi lệnh TRAILING_STOP {order_side} giá {activation_price}, callback {callback_rate}%")
        
        # [LOG DATA GỬI LÊN BINANCE]
        logger.info(f"📤 [DATA GỬI - TAKE PROFIT]")
        logger.info(f"   Symbol: {symbol}")
        logger.info(f"   Side: {order_side}")
        logger.info(f"   Amount: {abs(position_amt)}")
        logger.info(f"   Activation Price: {activation_price}")
        logger.info(f"   Callback Rate: {callback_rate}%")
        logger.info(f"   Reduce Only: True")
        logger.info(f"   Type: TRAILING_STOP_MARKET")
        
        order = self.order_helper.create_trailing_stop_order(
            symbol=symbol,
            side=order_side,
            amount=abs(position_amt),
            activation_price=activation_price,
            callback_rate=callback_rate,
            reduce_only=True
        )
        
        logger.info(f"✅ [RESPONSE - TAKE PROFIT] Order ID: {order.get('id')}, Status: {order.get('status')}")
        
        return order
    
    def _create_next_entry(
        self,
        symbol: str,
        layer_num: int,
        side: str,
        config: Dict
    ) -> Dict:
        """Tạo lệnh Entry cho lớp tiếp theo"""
        # Đọc config cho lớp mới
        order_type = config.get('order_type', 'TRAILING_STOP')
        leverage = config.get('leverage', 10)
        callback_rate = config.get('callback_rate', 1.0)
        activation_price = config.get('activation_price')
        stop_price = config.get('stop_price')
        limit_price = config.get('limit_price')
        capital = config.get('capital', 100)
        
        # Set leverage
        try:
            self.exchange.setLeverage(leverage, symbol)
        except Exception as e:
            logger.warning(f"Không thể set leverage: {e}")
        
        # Tính amount
        ticker = self.exchange.fetch_ticker(symbol)
        last_price = ticker['last']
        amount = capital / last_price
        
        order_side = 'buy' if side == 'LONG' else 'sell'
        
        logger.info(f"Tạo Entry {layer_num}a: {symbol} {order_type} {order_side}")
        
        # [LOG DATA GỬI - NEXT ENTRY]
        logger.info(f"📤 [DATA GỬI - ENTRY LỚP {layer_num}]")
        logger.info(f"   Symbol: {symbol}")
        logger.info(f"   Side: {order_side}")
        logger.info(f"   Amount: {amount}")
        logger.info(f"   Type: {order_type}")
        logger.info(f"   Leverage: {leverage}")
        if order_type == 'TRAILING_STOP':
            logger.info(f"   Activation Price: {activation_price}")
            logger.info(f"   Callback Rate: {callback_rate}%")
        elif order_type == 'STOP_LIMIT':
            logger.info(f"   Stop Price: {stop_price}")
            logger.info(f"   Limit Price: {limit_price}")
        elif order_type == 'LIMIT':
            logger.info(f"   Limit Price: {limit_price}")
        logger.info(f"   Reduce Only: False")
        
        # Tạo lệnh theo loại
        if order_type == 'TRAILING_STOP':
            order = self.order_helper.create_trailing_stop_order(
                symbol=symbol,
                side=order_side,
                amount=amount,
                activation_price=activation_price,
                callback_rate=callback_rate,
                reduce_only=False
            )
        elif order_type == 'STOP_LIMIT':
            order = self.order_helper.create_stop_limit_order(
                symbol=symbol,
                side=order_side,
                amount=amount,
                stop_price=stop_price,
                limit_price=limit_price,
                reduce_only=False
            )
        elif order_type == 'LIMIT':
            order = self.order_helper.create_limit_order(
                symbol=symbol,
                side=order_side,
                amount=amount,
                limit_price=limit_price,
                reduce_only=False
            )
        else:  # MARKET
            order = self.order_helper.create_market_order(
                symbol=symbol,
                side=order_side,
                amount=amount,
                reduce_only=False
            )
        
        logger.info(f"✅ [RESPONSE - ENTRY {layer_num}] Order ID: {order.get('id')}, Status: {order.get('status')}")
        
        return order
    
    # ──────────────────────────────────────────────────────────────────────
    # [TASK 1] Multi-layer SL/TP (3 lớp với tỉ lệ 40/40/20 chia từ sheet)
    # ──────────────────────────────────────────────────────────────────────

    def on_entry_filled_multi_layer(
        self,
        symbol: str,
        entry_price: float,
        leverage: int,
        position_amt: float,
        side: str,
        sl_prices: list,    # [sl1, sl2, sl3] - giá kích hoạt, có thể None nếu user để trống
        tp_prices: list,    # [tp1, tp2, tp3]
        ratios: list,       # [0.4, 0.4, 0.2] hoặc [40, 40, 20] (sẽ normalize)
        callback_rate: float = 1.0,
        skip_sl: bool = False,  # True nếu đã có SL, bỏ qua
        skip_tp: bool = False,  # True nếu đã có TP, bỏ qua
        tp_immediate_flags: list = None,  # [True,False,False] = O trống → kích hoạt ngay
    ) -> Dict:
        """
        [TASK 1] Tạo 3 cặp lệnh SL/TP theo tỉ lệ qty (40/40/20).

        Logic:
          - position_amt tổng được chia thành 3 phần theo ratios
          - SL tạo STOP_LIMIT reduceOnly với số lượng = qty * ratio
          - TP tạo TRAILING_STOP reduceOnly với activation_price = tp_prices[i]
          - Nếu giá SL/TP nào rỗng (None) → bỏ qua lớp đó

        Returns:
          dict {
            'sl_orders': [order1, order2, order3] (None nếu skip hoặc lỗi),
            'tp_orders': [order1, order2, order3] (None nếu skip hoặc lỗi),
            'errors': [ ...chi tiết lỗi... ]
          }
        """
        result = {
            'sl_orders': [None, None, None],
            'tp_orders': [None, None, None],
            'tp_activation_prices': [None, None, None],
            'errors': [],
        }
        tp_immediate_flags = tp_immediate_flags or [False, False, False]
        callback_rate = self.clamp_binance_callback_rate(callback_rate)

        # Normalize ratios: cho phép [40, 40, 20] hoặc [0.4, 0.4, 0.2]
        rs = [float(r) if r is not None else 0.0 for r in ratios]
        tot = sum(rs)
        if tot <= 0:
            result['errors'].append(f"Tổng tỉ lệ = 0, không thể chia qty")
            return result
        # Nếu tổng > 1.5 → cho là phần trăm (%), convert sang decimal
        if tot > 1.5:
            rs = [r / 100.0 for r in rs]
            tot = sum(rs)
        # Renormalize để đảm bảo tổng = 1.0 (chính xác khi user nhập lẻ)
        if abs(tot - 1.0) > 0.01:
            logger.warning(f"{symbol}: Tổng ratios = {tot:.3f} ≠ 1.0, renormalize")
            rs = [r / tot for r in rs]

        abs_total_qty = abs(float(position_amt))

        # Tính qty từng lớp + đảm bảo tổng không vượt qty tổng (rounding)
        qty_per_layer = []
        running_qty = 0.0
        for i, r in enumerate(rs):
            if i < len(rs) - 1:
                q_raw = abs_total_qty * r
                try:
                    q_round = float(self.exchange.amount_to_precision(symbol, q_raw))
                except Exception:
                    q_round = q_raw
                qty_per_layer.append(q_round)
                running_qty += q_round
            else:
                # Lớp cuối: lấy phần còn lại để không bị lệch (tổng = total)
                last_q = abs_total_qty - running_qty
                try:
                    last_q = float(self.exchange.amount_to_precision(symbol, last_q))
                except Exception:
                    pass
                qty_per_layer.append(max(0.0, last_q))

        logger.info(f"🎯 [MULTI-LAYER] {symbol} ({side}) qty={abs_total_qty} chia 3 lớp: {qty_per_layer} (ratios={rs})")

        # ── SL: 3 lớp STOP_LIMIT ───────────────────────────────────────
        if not skip_sl:
            for i in range(3):
                raw_price = sl_prices[i] if i < len(sl_prices) else None
                qty_i = qty_per_layer[i] if i < len(qty_per_layer) else 0
                if raw_price is None or qty_i <= 0:
                    logger.info(f"   SL lớp {i+1}: bỏ qua (price={raw_price}, qty={qty_i})")
                    continue
                try:
                    stop_price = self.smart_round_price(
                        price=float(raw_price),
                        symbol=symbol,
                        is_sl=True,
                        is_long=(side == 'LONG'),
                    )
                    if stop_price <= 0:
                        raise ValueError(f"stop_price={stop_price} ≤ 0")
                    order_side = 'sell' if side == 'LONG' else 'buy'

                    # Validate so với giá hiện tại (bỏ qua nếu không fetch được)
                    try:
                        cur = self.exchange.fetch_ticker(symbol).get('last')
                        if cur:
                            if side == 'LONG' and stop_price >= cur:
                                logger.warning(f"   ⚠️ SL{i+1} LONG: {stop_price} >= current {cur} → trigger ngay")
                            elif side == 'SHORT' and stop_price <= cur:
                                logger.warning(f"   ⚠️ SL{i+1} SHORT: {stop_price} <= current {cur} → trigger ngay")
                    except Exception:
                        pass

                    # [A1] STOP_MARKET đảm bảo cắt lỗ LUÔN khớp khi giá gap/biến động mạnh
                    # (STOP_LIMIT với limit=stop có thể không khớp nếu giá nhảy qua limit)
                    logger.info(f"   📤 SL{i+1}: STOP_MARKET {order_side} @ {stop_price}, qty={qty_i}")
                    order = self.order_helper.create_stop_market_order(
                        symbol=symbol,
                        side=order_side,
                        amount=qty_i,
                        stop_price=stop_price,
                        reduce_only=True,
                    )
                    result['sl_orders'][i] = order
                    logger.info(f"   ✅ SL{i+1} order ID: {order.get('id')}")
                except Exception as e:
                    err = f"SL{i+1} lỗi: {e}"
                    logger.error(f"   ❌ {err}", exc_info=True)
                    result['errors'].append(err)

        # ── TP: 3 lớp TRAILING_STOP ───────────────────────────────────
        if not skip_tp:
            for i in range(3):
                raw_price = tp_prices[i] if i < len(tp_prices) else None
                immediate = tp_immediate_flags[i] if i < len(tp_immediate_flags) else False
                qty_i = qty_per_layer[i] if i < len(qty_per_layer) else 0
                if qty_i <= 0:
                    logger.info(f"   TP lớp {i+1}: bỏ qua (qty={qty_i})")
                    continue
                if immediate:
                    try:
                        activation_price = self.resolve_trailing_activation_immediate(symbol, side)
                    except Exception as e:
                        err = f"TP{i+1} immediate: {e}"
                        logger.error(f"   ❌ {err}", exc_info=True)
                        result['errors'].append(err)
                        continue
                elif raw_price is None:
                    logger.info(f"   TP lớp {i+1}: bỏ qua (price=None, qty={qty_i})")
                    continue
                else:
                    try:
                        activation_price = self.smart_round_price(
                            price=float(raw_price),
                            symbol=symbol,
                            is_sl=False,
                            is_long=(side == 'LONG'),
                        )
                    except Exception as e:
                        err = f"TP{i+1} round price: {e}"
                        logger.error(f"   ❌ {err}", exc_info=True)
                        result['errors'].append(err)
                        continue
                try:
                    if activation_price <= 0:
                        raise ValueError(f"activation_price={activation_price} ≤ 0")
                    order_side = 'sell' if side == 'LONG' else 'buy'
                    result['tp_activation_prices'][i] = activation_price

                    try:
                        cur, _ = self.get_mark_or_last_price(symbol)
                        if side == 'LONG' and activation_price <= cur:
                            logger.info(f"   TP{i+1} LONG: activate {activation_price} <= mark {cur} → trailing active")
                        elif side == 'SHORT' and activation_price >= cur:
                            logger.info(f"   TP{i+1} SHORT: activate {activation_price} >= mark {cur} → trailing active")
                    except Exception:
                        pass

                    mode = 'NGAY' if immediate else 'CHỜ GIÁ O'
                    logger.info(
                        f"   📤 TP{i+1} ({mode}): TRAILING_STOP {order_side} @ {activation_price}, "
                        f"qty={qty_i}, callback={callback_rate}%"
                    )
                    order = self.order_helper.create_trailing_stop_order(
                        symbol=symbol,
                        side=order_side,
                        amount=qty_i,
                        activation_price=activation_price,
                        callback_rate=callback_rate,
                        reduce_only=True,
                    )
                    result['tp_orders'][i] = order
                    logger.info(f"   ✅ TP{i+1} order ID: {order.get('id')}")
                except Exception as e:
                    err = f"TP{i+1} lỗi: {e}"
                    logger.error(f"   ❌ {err}", exc_info=True)
                    result['errors'].append(err)

        sl_ok = sum(1 for o in result['sl_orders'] if o is not None)
        tp_ok = sum(1 for o in result['tp_orders'] if o is not None)
        logger.info(f"[MULTI-LAYER DONE] {symbol}: SL={sl_ok}/3, TP={tp_ok}/3, errors={len(result['errors'])}")
        return result


    def on_tp_filled(self, symbol: str, layer_num: int) -> List[str]:
        """
        Xử lý khi Take Profit khớp
        Hủy SL cùng lớp + Entry lớp tiếp theo
        """
        logger.info(f"💰 TP lớp {layer_num} đã khớp: {symbol}")
        
        cancelled_orders = []
        
        # 1. Hủy SL cùng lớp
        try:
            layer = self.layers.get(symbol, {}).get(layer_num)
            if layer and layer.sl_order:
                sl_id = layer.sl_order.get('id')
                self.exchange.cancel_order(sl_id, symbol)
                cancelled_orders.append(f"{layer_num}b")
                logger.info(f"✅ Đã hủy SL {layer_num}b")
        except Exception as e:
            logger.error(f"❌ Lỗi hủy SL {layer_num}b: {e}")
        
        # 2. Hủy Entry lớp tiếp theo (nếu có)
        next_layer_num = layer_num + 1
        try:
            next_layer = self.layers.get(symbol, {}).get(next_layer_num)
            if next_layer and next_layer.entry_order and not next_layer.entry_filled:
                entry_id = next_layer.entry_order.get('id')
                self.exchange.cancel_order(entry_id, symbol)
                cancelled_orders.append(f"{next_layer_num}a")
                logger.info(f"✅ Đã hủy Entry {next_layer_num}a")
        except Exception as e:
            logger.error(f"❌ Lỗi hủy Entry {next_layer_num}a: {e}")
        
        return cancelled_orders
    
    def on_sl_filled(self, symbol: str, layer_num: int) -> List[str]:
        """
        Xử lý khi Stop Loss khớp
        Hủy TP cùng lớp, KHÔNG hủy Entry lớp tiếp theo
        """
        logger.info(f"🛑 SL lớp {layer_num} đã khớp: {symbol}")
        
        cancelled_orders = []
        
        # Hủy TP cùng lớp
        try:
            layer = self.layers.get(symbol, {}).get(layer_num)
            if layer and layer.tp_order:
                tp_id = layer.tp_order.get('id')
                self.exchange.cancel_order(tp_id, symbol)
                cancelled_orders.append(f"{layer_num}c")
                logger.info(f"✅ Đã hủy TP {layer_num}c")
        except Exception as e:
            logger.error(f"❌ Lỗi hủy TP {layer_num}c: {e}")
        
        # KHÔNG hủy Entry lớp tiếp theo - vẫn có thể entry lại
        logger.info(f"ℹ️ Giữ nguyên Entry lớp {layer_num + 1} (vẫn có thể entry)")
        
        return cancelled_orders
    
    def get_layer_info(self, symbol: str, layer_num: int) -> Optional[LayerInfo]:
        """Lấy thông tin một lớp"""
        return self.layers.get(symbol, {}).get(layer_num)
    
    def get_all_layers(self, symbol: str) -> Dict[int, LayerInfo]:
        """Lấy tất cả lớp của một symbol"""
        return self.layers.get(symbol, {})
    
    def clear_symbol(self, symbol: str):
        """Xóa tất cả tracking cho một symbol"""
        if symbol in self.layers:
            del self.layers[symbol]
            logger.info(f"🗑️ Đã xóa tracking cho {symbol}")
    
    def get_max_layer(self, symbol: str) -> int:
        """Lấy số lớp cao nhất đang active"""
        layers = self.layers.get(symbol, {})
        return max(layers.keys()) if layers else 0


# Singleton instance
_cascade_manager = None

def get_cascade_manager(exchange: ccxt.binance, order_helper) -> CascadeManager:
    """Get singleton instance"""
    global _cascade_manager
    if _cascade_manager is None:
        _cascade_manager = CascadeManager(exchange, order_helper)
    return _cascade_manager