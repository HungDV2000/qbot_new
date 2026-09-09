import ccxt
from binance_futures_direct import resync_exchange_time  # [Fix1] chống clock drift -1021
import cst
from pathlib import Path
import time
import telegram_factory
import logging
import os
import requests
import hmac
import hashlib
import urllib.parse
import gg_sheet_factory
from datetime import datetime

file_name = os.path.basename(os.path.abspath(__file__))  
os.system(f"title {file_name} - {cst.key_name}")

# Tạo thư mục logs/ nếu chưa có
logs_dir = cst.account_dir('logs')  # [MULTI-ACC] tách theo tài khoản
logs_dir.mkdir(exist_ok=True)

# Tạo tên file log với timestamp: hd_cancel_dd_mm_yyyy_H_M_S.txt
log_timestamp = datetime.now().strftime('%d_%m_%Y_%H_%M_%S')
log_filename = logs_dir / f'hd_cancel_{log_timestamp}.txt'

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

# Khởi tạo exchange
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

logger.info("✅ Khởi tạo Binance exchange thành công")


def call_binance_api_direct(method, endpoint, params=None):
    """
    Gọi Binance API trực tiếp bằng requests (để hủy algo orders)
    """
    base_url = 'https://fapi.binance.com'
    url = f"{base_url}{endpoint}"
    
    if params is None:
        params = {}
    
    # Thêm timestamp
    params['timestamp'] = int(time.time() * 1000)
    
    # Tạo query string
    query_string = urllib.parse.urlencode(params)
    
    # Tạo signature
    signature = hmac.new(
        cst.secret_binance.encode('utf-8'),
        query_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    
    params['signature'] = signature
    
    # Headers
    headers = {
        'X-MBX-APIKEY': cst.key_binance
    }
    
    try:
        if method.upper() == 'DELETE':
            response = requests.delete(url, params=params, headers=headers, timeout=10)
        elif method.upper() == 'GET':
            response = requests.get(url, params=params, headers=headers, timeout=10)
        else:
            return None
            
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Lỗi khi gọi Binance API trực tiếp ({method} {endpoint}): {e}")
        return None

def get_algo_orders_for_symbol(symbol):
    """
    Lấy algo orders cho một symbol cụ thể từ Binance API
    """
    try:
        # Binance API yêu cầu symbol format: HOMEUSDT (không có / và :USDT)
        symbol_clean = symbol.replace('/', '').replace(':USDT', '')
        
        params = {
            'symbol': symbol_clean
        }
        
        response = call_binance_api_direct('GET', '/fapi/v1/allAlgoOrders', params)
        
        if not response:
            return []
        
        # Binance trả về có thể là array hoặc dict
        if isinstance(response, list):
            return response
        elif isinstance(response, dict):
            if 'data' in response:
                return response['data']
            elif response.get('code') == 200:
                return response
            else:
                return []
        else:
            return []
        
    except Exception as e:
        logger.error(f"Lỗi khi lấy algo orders cho {symbol}: {e}", exc_info=True)
        return []


# ══════════════════════════════════════════════════════════════════════════════
# BỘ LỌC AN TOÀN (mới)
#
# Trước đây bot này hủy TẤT CẢ lệnh của mọi mã trong tab "Chờ và khớp", mỗi
# `cancel_orders_minutes` phút (mặc định 1 phút). Hệ quả:
#   • SL/TP vừa đặt bị xoá ngay → vị thế KHÔNG được bảo vệ
#   • Các lệnh rải (DCA) chưa kịp khớp cũng bị xoá → "3 lệnh chỉ vào 1"
#
# Nay mặc định:
#   • KHÔNG đụng lệnh reduce_only (SL/TP) — chỉ hủy lệnh VÀO
#   • Chỉ hủy lệnh đã treo quá `cancel_order_after_minutes` phút (mặc định 30)
# Muốn quay lại hành vi cũ: đặt cancel_all_orders = true trong config.ini
# ══════════════════════════════════════════════════════════════════════════════
try:
    CANCEL_ALL_ORDERS = cst.config.getboolean('global', 'cancel_all_orders', fallback=False)
except Exception:
    CANCEL_ALL_ORDERS = False
try:
    CANCEL_AFTER_MINUTES = cst.config.getint('global', 'cancel_order_after_minutes', fallback=30)
except Exception:
    CANCEL_AFTER_MINUTES = 30


def _is_reduce_only(order):
    """Lệnh đóng vị thế (SL/TP) — mặc định KHÔNG được hủy."""
    info = order.get('info', {}) if isinstance(order.get('info'), dict) else {}
    for src in (order, info):
        v = src.get('reduceOnly', src.get('reduce_only'))
        if v is True or str(v).strip().lower() == 'true':
            return True
    if str(info.get('closePosition', '')).strip().lower() == 'true':
        return True
    return False


def _order_age_minutes(order):
    """Tuổi lệnh (phút). None nếu không xác định được thời điểm tạo."""
    ts = (order.get('timestamp')
          or order.get('createTime')
          or (order.get('info', {}) or {}).get('time')
          or (order.get('info', {}) or {}).get('createTime')
          or (order.get('info', {}) or {}).get('bookTime'))
    try:
        ts = float(ts)
    except (TypeError, ValueError):
        return None
    if ts <= 0:
        return None
    return (time.time() * 1000 - ts) / 60000.0


def _should_cancel(order, symbol, kind):
    """
    Quyết định có hủy lệnh này không.
    Trả (True/False, lý_do).
    """
    if CANCEL_ALL_ORDERS:
        return True, "cancel_all_orders=true"

    if _is_reduce_only(order):
        return False, "là lệnh SL/TP (reduce_only) — GIỮ để bảo vệ vị thế"

    age = _order_age_minutes(order)
    if age is None:
        return False, "không xác định được tuổi lệnh — giữ cho an toàn"
    if age < CANCEL_AFTER_MINUTES:
        return False, f"mới treo {age:.1f} phút (< {CANCEL_AFTER_MINUTES}) — chờ khớp"
    return True, f"lệnh VÀO treo {age:.1f} phút (>= {CANCEL_AFTER_MINUTES})"


def cancel_all_open_orders(symbol):
    """
    Hủy TẤT CẢ orders (bao gồm cả TRAILING_STOP/Algo orders và open orders thông thường)
    ✅ NÂNG CẤP: Sử dụng API trực tiếp để hủy algo orders chính xác
    """
    total_cancelled = 0
    total_algo_cancelled = 0
    total_open_cancelled = 0
    
    try:
        # ✅ BƯỚC 1: Hủy Algo Orders (TRAILING_STOP, STOP_MARKET, etc.)
        try:
            algo_orders = get_algo_orders_for_symbol(symbol)
            active_algo_orders = [o for o in algo_orders if o.get('algoStatus', '').upper() == 'NEW']
            
            if active_algo_orders:
                logger.info(f"Tìm thấy {len(active_algo_orders)} Algo Orders cần hủy cho {symbol}")
                
                for order in active_algo_orders:
                    algo_id = order.get('algoId')
                    algo_type = order.get('algoType', 'N/A')

                    ok, ly_do = _should_cancel(order, symbol, 'algo')
                    if not ok:
                        logger.info(f"⏭️  Giữ algo {algo_id} [{algo_type}] {symbol}: {ly_do}")
                        continue

                    if algo_id:
                        # Hủy algo order qua API trực tiếp
                        symbol_clean = symbol.replace('/', '').replace(':USDT', '')
                        params = {
                            'symbol': symbol_clean,
                            'algoId': algo_id
                        }
                        response = call_binance_api_direct('DELETE', '/fapi/v1/algoOrder', params)
                        
                        if response:
                            code = response.get('code')
                            if str(code) == '200':
                                total_algo_cancelled += 1
                                total_cancelled += 1
                                print(f"✅ Hủy Algo order {algo_id} [{algo_type}] cho {symbol}", flush=True)
                                logger.info(f"Đã hủy Algo order {algo_id} [{algo_type}] cho {symbol}")
                            else:
                                logger.warning(f"Không thể hủy algo order {algo_id}: code={code}")
                        else:
                            logger.warning(f"Không nhận được response khi hủy algo order {algo_id}")
        except Exception as e:
            logger.error(f"Lỗi khi hủy algo orders cho {symbol}: {e}", exc_info=True)
        
        # ✅ BƯỚC 2: Hủy Open Orders thông thường
        try:
            open_orders = exchange.fetch_open_orders(symbol)
            
            if open_orders:
                logger.info(f"Tìm thấy {len(open_orders)} Open Orders cần hủy cho {symbol}")
                
                for order in open_orders:
                    try:
                        order_id = order.get('id')

                        ok, ly_do = _should_cancel(order, symbol, 'open')
                        if not ok:
                            logger.info(f"⏭️  Giữ order {order_id} {symbol}: {ly_do}")
                            continue

                        if order_id:
                            cancel_result = exchange.cancel_order(order_id, symbol)
                            total_open_cancelled += 1
                            total_cancelled += 1
                            print(f"✅ Hủy order {order_id} cho {symbol}", flush=True)
                            logger.info(f"Đã hủy order {order_id} cho {symbol}")
                    except Exception as e:
                        logger.error(f"Lỗi khi hủy order {order.get('id', 'N/A')}: {e}")
        except Exception as e:
            logger.error(f"Lỗi khi lấy/hủy open orders cho {symbol}: {e}", exc_info=True)
        
        # Thông báo kết quả
        if total_cancelled > 0:
            msg = f"✅ <b>ĐÃ HỦY LỆNH THEO LỊCH</b>\n\n<b>Mã:</b> {symbol}\n<b>Tổng:</b> {total_cancelled} lệnh\n<b>Algo:</b> {total_algo_cancelled}\n<b>Open:</b> {total_open_cancelled}"
            telegram_factory.send_tele(msg, cst.chat_id, True, True)
            print(f"🧹 Tổng cộng đã hủy {total_cancelled} lệnh cho {symbol} (Algo: {total_algo_cancelled}, Open: {total_open_cancelled})", flush=True)
        else:
            print(f"ℹ️  Không có lệnh nào cần hủy cho {symbol}", flush=True)
            
    except Exception as e:
        logger.error(f"Lỗi tổng quát khi hủy orders cho {symbol}: {e}", exc_info=True)
        print(f"❌ Lỗi khi hủy orders cho {symbol}: {e}", flush=True)


def cancel_orders_scheduled():
    """
    Hàm chính: Đọc danh sách symbols từ sheet và hủy orders
    """
    try:
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"\n{'='*80}", flush=True)
        print(f"[{current_time}] Bắt đầu hủy lệnh theo lịch...", flush=True)
        print(f"{'='*80}\n", flush=True)
        logger.info(f"[{current_time}] Bắt đầu cancel orders theo lịch")
        
        # Đọc danh sách symbols từ sheet "Chờ và khớp" (cột A, hàng 3-100)
        sheet_data = gg_sheet_factory.get_cho_va_khop("A3:A100")
        
        if not sheet_data:
            print("⚠️  Không có dữ liệu từ sheet", flush=True)
            logger.warning("Không có dữ liệu từ sheet 'Chờ và khớp'")
            return
        
        symbols_processed = 0
        symbols_with_orders = 0
        
        for row in sheet_data:
            try:
                if not row or len(row) == 0:
                    continue
                
                symbol_raw = str(row[0]).strip() if row[0] else ""
                
                # Validate symbol (phải chứa USDT)
                if not symbol_raw or "USDT" not in symbol_raw.upper():
                    continue
                
                # Format symbol: "HOME/USDT" hoặc "HOMEUSDT" → "HOME/USDT:USDT" (CCXT format)
                symbol = symbol_raw
                if "/" not in symbol:
                    # "HOMEUSDT" → "HOME/USDT:USDT"
                    symbol = symbol.replace("USDT", "/USDT:USDT")
                elif ":USDT" not in symbol:
                    # "HOME/USDT" → "HOME/USDT:USDT"
                    symbol = f"{symbol}:USDT"
                
                print(f"🔍 Xử lý: {symbol}", flush=True)
                symbols_processed += 1
                
                # Hủy tất cả orders cho symbol này
                cancel_all_open_orders(symbol)
                symbols_with_orders += 1
                
            except Exception as e:
                logger.error(f"Lỗi xử lý dòng sheet: {e}", exc_info=True)
                continue
        
        # Tổng kết
        print(f"\n{'='*80}", flush=True)
        print(f"✅ Hoàn thành! Đã xử lý {symbols_processed} symbols", flush=True)
        print(f"{'='*80}\n", flush=True)
        logger.info(f"Hoàn thành cancel orders - Đã xử lý {symbols_processed} symbols")
        
    except Exception as e:
        print(f"❌ Lỗi trong cancel_orders_scheduled: {e}", flush=True)
        logger.error(f"Lỗi trong cancel_orders_scheduled: {e}", exc_info=True)


# Main loop
print(f"🚀 Bot hủy lệnh theo lịch khởi động - Chạy mỗi {cst.cancel_orders_minutes} phút", flush=True)
if CANCEL_ALL_ORDERS:
    print("⚠️  CHẾ ĐỘ CŨ: hủy TẤT CẢ lệnh (kể cả SL/TP) — cancel_all_orders=true", flush=True)
else:
    print(f"🛡️  Chế độ an toàn: chỉ hủy lệnh VÀO treo quá {CANCEL_AFTER_MINUTES} phút; "
          f"KHÔNG đụng SL/TP (reduce_only)", flush=True)
logger.info(f"Khởi động cancel orders scheduler - chạy mỗi {cst.cancel_orders_minutes} phút")

# Chạy ngay lần đầu
cancel_orders_scheduled()

# Sau đó chạy theo interval
while True:
    try:
        time.sleep(cst.cancel_orders_minutes * 60)  # Chuyển phút thành giây
        resync_exchange_time(exchange)  # [Fix1] chống clock drift -> hết -1021
        cancel_orders_scheduled()
    except KeyboardInterrupt:
        print("\n⚠️  Nhận Ctrl+C - Dừng bot...", flush=True)
        logger.info("Bot dừng bởi user (Ctrl+C)")
        break
    except Exception as e:
        if '-1021' in str(e) or 'recvWindow' in str(e):
            resync_exchange_time(exchange, min_interval=0)  # [Fix4] ép resync ccxt ngay
        print(f"❌ Lỗi trong vòng lặp cancel orders: {e}", flush=True)
        logger.error(f"Lỗi trong vòng lặp cancel orders: {e}", exc_info=True)
        time.sleep(60)  # Chờ 1 phút trước khi thử lại

print("👋 Bot đã dừng", flush=True)
logger.info("Bot đã dừng")
