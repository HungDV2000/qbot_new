import ccxt
from binance_futures_direct import resync_exchange_time  # [Fix1] chống clock drift -1021
import cst
import gg_sheet_factory
import logging
import time
from datetime import datetime
from pathlib import Path
import utils
import telegram_factory
import os
from binance_order_helper import cancel_all_open_orders_with_retry, BinanceOrderHelper
from cascade_manager import get_cascade_manager
from order_state_tracker import get_tracker
from notification_manager import get_notification_manager

file_name = os.path.basename(os.path.abspath(__file__))  
os.system(f"title {file_name} - {cst.key_name}")

# Tạo thư mục logs/ nếu chưa có
logs_dir = cst.account_dir('logs')  # [MULTI-ACC] tách theo tài khoản
logs_dir.mkdir(exist_ok=True)

# Tạo tên file log với timestamp: hd_alert_possition_and_open_order_dd_mm_yyyy_H_M_S.txt
log_timestamp = datetime.now().strftime('%d_%m_%Y_%H_%M_%S')
log_filename = logs_dir / f'hd_alert_possition_and_open_order_{log_timestamp}.txt'

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    encoding='utf-8'
)
logger = logging.getLogger(__name__)

# Tạo file handler với tên file động
file_handler = logging.FileHandler(log_filename, encoding='utf-8')
file_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
file_handler.setLevel(logging.INFO)
logger.addHandler(file_handler)

exchange_id = 'binance'
exchange_class = getattr(ccxt, exchange_id)
exchange = exchange_class({
    'enableRateLimit': True,  
    'apiKey': cst.key_binance,
    'secret': cst.secret_binance,
    'options': {
        'defaultType': 'future',
        'fetchCurrencies': False,          # [A2] tránh gọi /sapi getall (signed) khi load_markets
        'adjustForTimeDifference': True,   # [A2] tự đồng bộ clock -> hết lỗi -1021
        'recvWindow': 60000,               # [A2+Fix2] nới cửa sổ timestamp lên max 60s
    }
})
exchange.setSandboxMode(False)

# Khởi tạo order helper, cascade manager và notification manager
order_helper = BinanceOrderHelper(exchange)
cascade_mgr = get_cascade_manager(exchange, order_helper)
notif_mgr = get_notification_manager(cst.chat_id)



def get_all_open_orders_with_single_order():
    res = []
    
    for sym in  utils.get_all_open_orders_symbol_local():
        print(sym, flush=True)
        
        
        orders = exchange.fetch_open_orders(symbol=sym)
        if len(orders) == 1:
            res.append(orders[0])
        
        for order in orders:
            print(f"Symbol: {order['symbol']}, ID: {order['id']}, Status: {order['status']}, Amount: {order['amount']}, Price: {order['price']}", flush=True)
    return res

def get_opened_possition():
    """
    Lấy tất cả positions đang mở (position_amt != 0)
    ✅ SỬ DỤNG fetch_positions() thay vì fetch_balance() để có entryPrice!
    """
    try:
        # ✅ FIX: Dùng fetch_positions() thay vì fetch_balance()['info']['positions']
        # Vì fetch_balance() KHÔNG trả về entryPrice trong raw data!
        positions = exchange.fetch_positions()
        logger.info(f"✅ Đã lấy {len(positions)} positions từ fetch_positions()")
    except Exception as e:
        logger.error(f"Lỗi khi lấy positions: {e}", exc_info=True)
        return []
    
    opened_possition = []
    
    for position in positions:
        try:
            # CCXT fetch_positions() trả về format khác:
            # - 'contracts' (luôn dương) thay vì 'positionAmt' (có thể âm/dương)
            # - 'side' = "long" hoặc "short"
            # - 'symbol' = "HOME/USDT:USDT" (đã format sẵn)
            # - CÓ 'entryPrice' và 'leverage'!
            
            contracts = float(position.get('contracts', 0))
            if contracts == 0:
                continue  # Bỏ qua position rỗng
            
            side = position.get('side', '').lower()
            symbol_ccxt = position['symbol']  # "HOME/USDT:USDT"
            
            # Convert về format "HOMEUSDT" để tương thích với code hiện tại
            symbol = symbol_ccxt.replace('/', '').replace(':USDT', '')
            
            # Convert contracts + side thành position_amt (âm nếu short, dương nếu long)
            position_amt = contracts if side == 'long' else -contracts
            
            # Parse entry price - fetch_positions() CÓ entryPrice!
            entry_price_raw = position.get('entryPrice')
            if entry_price_raw is not None and entry_price_raw != '' and entry_price_raw != 0:
                try:
                    entry_price = float(entry_price_raw)
                except (ValueError, TypeError):
                    entry_price = 0.0
                    logger.warning(f"{symbol}: Lỗi parse entryPrice: {entry_price_raw}")
            else:
                entry_price = 0.0
                logger.warning(f"{symbol}: entryPrice rỗng hoặc = 0, raw: {entry_price_raw}")
            
            # Parse unrealized PnL
            unrealized_pnl_raw = position.get('unrealizedPnl', position.get('unrealizedProfit', 0))
            if unrealized_pnl_raw is not None and unrealized_pnl_raw != '':
                try:
                    unrealized_pnl = float(unrealized_pnl_raw)
                except (ValueError, TypeError):
                    unrealized_pnl = 0.0
            else:
                unrealized_pnl = 0.0
            
            # Parse leverage - fetch_positions() CÓ leverage!
            leverage_raw = position.get('leverage')
            if leverage_raw is not None and leverage_raw != '' and leverage_raw != 0:
                try:
                    leverage = int(float(leverage_raw))
                except (ValueError, TypeError):
                    leverage = 1
            else:
                leverage = 1
            
            # Tạo position dict với format tương thích với code hiện tại
            position_dict = {
                'symbol': symbol,  # Format "HOMEUSDT"
                'positionAmt': str(position_amt),
                'entryPrice': entry_price,
                'unrealizedProfit': unrealized_pnl,
                'leverage': leverage
            }
            
            opened_possition.append(position_dict)
            print(f"Symbol: {symbol}, Position: {position_amt}, Entry Price: {entry_price}, Unrealized PnL: {unrealized_pnl}, Leverage: {leverage}", flush=True)
            logger.debug(f"Position: {symbol}, Amt={position_amt}, Entry={entry_price}, PnL={unrealized_pnl}, Lev={leverage}")
            
        except Exception as e:
            logger.error(f"Lỗi khi xử lý position {position.get('symbol', 'N/A')}: {e}", exc_info=True)
            continue
            
    return opened_possition

result_old = []
is_first_time = True

def cancel_all_open_orders(symbol):
    """
    Hủy tất cả lệnh chờ với retry mechanism
    """
    logger.info(f"Bắt đầu hủy lệnh chờ cho {symbol}...")
    
    success, remaining = cancel_all_open_orders_with_retry(
        exchange=exchange,
        symbol=symbol,
        max_retries=3,
        delay=2
    )
    
    if success:
        msg = f"✅ <b>ĐÃ HỦY LỆNH CHỜ</b>\n\n<b>Mã:</b> {symbol}\n<b>Trạng thái:</b> Đã xóa sạch tất cả lệnh"
        telegram_factory.send_tele(msg, cst.chat_id, True, True)
        logger.info(f"✅ Hủy lệnh thành công cho {symbol}")
    else:
        msg = f"🔴 <b>CẢNH BÁO NGHIÊM TRỌNG</b>\n\n<b>Mã:</b> {symbol}\n<b>Vấn đề:</b> Không thể xóa lệnh Reduce Only sau 3 lần thử\n<b>Lệnh còn sót:</b> {remaining if remaining > 0 else 'Không xác định'}\n<b>Yêu cầu:</b> Can thiệp thủ công!"
        telegram_factory.send_tele(msg, cst.chat_id, True, True)
        logger.critical(f"🔴 Không thể hủy lệnh cho {symbol}!")

def do_it():
    global result_old, is_first_time  

    print(f"{datetime.now()}. hd_alert_possition_and_open_order----------------------------------------------------", flush=True)

    res = get_opened_possition()
    print(f"Tổng Lệnh: {len(res)}", flush=True)
    print(res, flush=True)

    
    
    

    if is_first_time:
        result_old = res
        is_first_time = False
        return

        
    


    
    for item in res:
        is_contain = False
        for item_old in result_old:
            if item["symbol"] == item_old["symbol"]:
                is_contain = True
                break

        if not is_contain:
            print(f"phần tử mới được thêm vào: {item}", flush=True)
            symbol = item['symbol']
            logger.info(f"✅ Position mới mở: {symbol} - Entry: {item.get('entryPrice', 'N/A')} - Amount: {item.get('positionAmt', 'N/A')} - Leverage: {item.get('leverage', 'N/A')}")
            notif_mgr.send_position_opened(symbol)


    
    for item_old in result_old:
        is_contain = False
        for item in res:
            if item["symbol"] == item_old["symbol"]:
                is_contain = True
                break

        if not is_contain:
            print(f"phần tử cũ được bỏ đi: {item_old}", flush=True)
            symbol = item_old['symbol']
            
            # Detect TP hay SL bằng cách check PnL
            pnl = float(item_old.get('unrealizedProfit', 0))
            is_tp = pnl > 0  # Profit = TP, Loss = SL
            
            # Lấy state hiện tại từ sheet để biết đang ở lớp nào
            try:
                # Xác định side dựa trên position_amt
                position_amt = float(item_old.get('positionAmt', 0))
                side = "LONG" if position_amt > 0 else "SHORT"
                
                tracker = get_tracker(side)
                state = tracker.get_current_state(
                    symbol=symbol,
                    # Bố cục sheet: KHỐI TRÊN (4-53) = LONG, KHỐI DƯỚI (55-104) = SHORT.
                    # Trước đây đảo ngược → tìm sai vùng, get_current_state luôn rỗng
                    # nên nhánh cascade TP/SL không bao giờ chạy.
                    start_row=4 if side == "LONG" else 55,
                    end_row=53 if side == "LONG" else 104
                )
                
                if state and state.get('order_code'):
                    order_code = state['order_code']
                    # Parse layer từ order_code (VD: "1a" -> layer 1)
                    try:
                        layer_num = int(order_code[0])
                    except:
                        layer_num = 1
                    
                    # Xử lý theo TP/SL
                    if is_tp:
                        logger.info(f"💰 TP khớp cho {symbol} lớp {layer_num} - Entry: {item_old.get('entryPrice', 'N/A')} - PnL: {pnl:.2f}")
                        cascade_mgr.on_tp_filled(symbol, layer_num)
                    else:
                        logger.info(f"🛑 SL khớp cho {symbol} lớp {layer_num} - Entry: {item_old.get('entryPrice', 'N/A')} - PnL: {pnl:.2f}")
                        cascade_mgr.on_sl_filled(symbol, layer_num)
                    
                    # Gửi thông báo đóng vị thế
                    notif_mgr.send_position_closed(symbol, pnl)
                    
                else:
                    # Không có state, chỉ báo đóng position thông thường
                    notif_mgr.send_position_closed(symbol)
                    
            except Exception as e:
                logger.error(f"Lỗi xử lý TP/SL cho {symbol}: {e}", exc_info=True)
                notif_mgr.send_position_closed(symbol)

            # Hủy tất cả lệnh chờ
            cancel_all_open_orders(symbol)


    result_old = res


    
    
    
    

    
    
    
    
    
    
    

    
    
    
    
    
    
    
    
    
    
    
    
    

    
    
    

    
    
    
    
    
    
    

    
    
    
    
    
    
    
    
    
    
    
    
    
    
    

    
    

while True:
    try:
        resync_exchange_time(exchange)  # [Fix1] chống clock drift -> hết -1021
        do_it()
    except Exception as e:
        if '-1021' in str(e) or 'recvWindow' in str(e):
            resync_exchange_time(exchange, min_interval=0)  # [Fix4] ép resync ccxt ngay
        print(f"Tổng Lỗi: {e}", flush=True)
        logger.error(f"Tổng lỗi: {e}", exc_info=True)
        import traceback
        traceback.print_exc()

    time.sleep(cst.delay_calert_possition_and_open_order)