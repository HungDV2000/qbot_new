"""
hd_alert_possition_and_open_order — CẢNH BÁO vị thế qua Telegram.

Mỗi `delay_calert_possition_and_open_order` giây so danh sách vị thế với lần trước:
  • Vị thế MỚI mở   → Telegram "Đã Thêm Vị Thế"
  • Vị thế vừa ĐÓNG → Telegram "Đã Đóng Vị Thế | PNL" rồi HUỶ MỌI LỆNH còn treo
                      của mã đó (SL/TP sót, lệnh vào chưa khớp) — thử lại 3 lần.
Không đọc/ghi Google Sheet.
"""
import giu_cua_so  # PHẢI nạp ĐẦU TIÊN: dừng/lỗi thì giữ cửa sổ Windows để đọc thông báo
import ccxt
from binance_futures_direct import resync_exchange_time  # [Fix1] chống clock drift -1021
import cst
import config_watcher
import logging
from datetime import datetime
import telegram_factory
import os
from binance_order_helper import cancel_all_open_orders_with_retry

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


def _gui(msg):
    try:
        telegram_factory.send_tele(msg, cst.chat_id, True, True)
    except Exception as e:
        logger.error(f"Lỗi gửi Telegram: {e}")


def bao_vi_the_mo(symbol):
    _gui(f"✅ Đã Thêm Vị Thế: {symbol}")


def bao_vi_the_dong(symbol, pnl=None):
    # pnl = lãi/lỗ CHƯA chốt ở lần quét trước khi đóng → chỉ là ước tính
    if pnl is not None:
        emoji = "💰" if pnl >= 0 else "💸"
        _gui(f"{emoji} Đã Đóng Vị Thế: {symbol} | PNL ~ ${pnl:.2f}")
    else:
        _gui(f"Đã Đóng Vị Thế: {symbol}")


def get_opened_possition():
    """
    Lấy tất cả positions đang mở (position_amt != 0)
    ✅ SỬ DỤNG fetch_positions() thay vì fetch_balance() để có entryPrice!
    """
    try:
        positions = exchange.fetch_positions()
        logger.info(f"✅ Đã lấy {len(positions)} positions từ fetch_positions()")
    except Exception as e:
        logger.error(f"Lỗi khi lấy positions: {e}", exc_info=True)
        return []

    opened_possition = []

    for position in positions:
        try:
            # CCXT: 'contracts' luôn dương, 'side' = long/short, symbol = "HOME/USDT:USDT"
            contracts = float(position.get('contracts', 0))
            if contracts == 0:
                continue  # Bỏ qua position rỗng

            side = position.get('side', '').lower()
            symbol_ccxt = position['symbol']  # "HOME/USDT:USDT"

            # Convert về format "HOMEUSDT" để tương thích với code hiện tại
            symbol = symbol_ccxt.replace('/', '').replace(':USDT', '')

            # Convert contracts + side thành position_amt (âm nếu short, dương nếu long)
            position_amt = contracts if side == 'long' else -contracts

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

            unrealized_pnl_raw = position.get('unrealizedPnl', position.get('unrealizedProfit', 0))
            if unrealized_pnl_raw is not None and unrealized_pnl_raw != '':
                try:
                    unrealized_pnl = float(unrealized_pnl_raw)
                except (ValueError, TypeError):
                    unrealized_pnl = 0.0
            else:
                unrealized_pnl = 0.0

            leverage_raw = position.get('leverage')
            if leverage_raw is not None and leverage_raw != '' and leverage_raw != 0:
                try:
                    leverage = int(float(leverage_raw))
                except (ValueError, TypeError):
                    leverage = 1
            else:
                leverage = 1

            opened_possition.append({
                'symbol': symbol,  # Format "HOMEUSDT"
                'positionAmt': str(position_amt),
                'entryPrice': entry_price,
                'unrealizedProfit': unrealized_pnl,
                'leverage': leverage
            })
            print(f"Symbol: {symbol}, Position: {position_amt}, Entry Price: {entry_price}, Unrealized PnL: {unrealized_pnl}, Leverage: {leverage}", flush=True)

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

    # Lần đầu chỉ ghi nhớ, không báo (tránh báo tràn mọi vị thế đang có)
    if is_first_time:
        result_old = res
        is_first_time = False
        return

    ma_moi = {item["symbol"] for item in res}
    ma_cu = {item["symbol"] for item in result_old}

    for item in res:
        if item["symbol"] not in ma_cu:
            symbol = item['symbol']
            logger.info(f"✅ Position mới mở: {symbol} - Entry: {item.get('entryPrice', 'N/A')} - Amount: {item.get('positionAmt', 'N/A')} - Leverage: {item.get('leverage', 'N/A')}")
            bao_vi_the_mo(symbol)

    for item_old in result_old:
        if item_old["symbol"] not in ma_moi:
            symbol = item_old['symbol']
            pnl = float(item_old.get('unrealizedProfit', 0) or 0)
            logger.info(f"🔚 Position đã đóng: {symbol} - Entry: {item_old.get('entryPrice', 'N/A')} - PnL ước tính: {pnl:.2f}")
            bao_vi_the_dong(symbol, pnl)
            # Hủy tất cả lệnh chờ còn sót của mã vừa đóng
            cancel_all_open_orders(symbol)

    result_old = res


cst.bao_nhip('delay_calert_possition_and_open_order', cst.delay_calert_possition_and_open_order)

while True:
    _t0_vong = config_watcher.bat_dau_vong()
    try:
        resync_exchange_time(exchange)  # [Fix1] chống clock drift -> hết -1021
        do_it()
    except Exception as e:
        if '-1021' in str(e) or 'recvWindow' in str(e):
            resync_exchange_time(exchange, min_interval=0)  # [Fix4] ép resync ccxt ngay
        print(f"Tổng Lỗi: {e}", flush=True)
        logger.error(f"Tổng lỗi: {e}", exc_info=True)
    config_watcher.ngu_theo_nhip(_t0_vong, cst.delay_calert_possition_and_open_order,
                                 'delay_calert_possition_and_open_order')
