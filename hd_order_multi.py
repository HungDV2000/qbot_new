import cst
from enum import Enum
import gg_sheet_factory
import threading
import logging
import subprocess
import time
import os
import sys
import ccxt
from datetime import datetime
import utils
import binance_utils
import telegram_factory
from pathlib import Path
from binance_order_helper import BinanceOrderHelper, cancel_all_open_orders_with_retry
import requests
import hmac
import hashlib
import urllib.parse
import json
from googleapiclient.errors import HttpError  # ✅ Thêm import HttpError để handle lỗi Google API
from binance_futures_direct import fetch_algo_orders_for_symbol, resync_exchange_time

# Cấu hình stdout để output realtime (unbuffered)
sys.stdout.reconfigure(line_buffering=True) if hasattr(sys.stdout, 'reconfigure') else None
sys.stderr.reconfigure(line_buffering=True) if hasattr(sys.stderr, 'reconfigure') else None

file_name = os.path.basename(os.path.abspath(__file__))  
os.system(f"title {file_name} - {cst.key_name}")

# Tạo thư mục logs/ nếu chưa có
logs_dir = cst.account_dir('logs')  # [MULTI-ACC] tách theo tài khoản
logs_dir.mkdir(exist_ok=True)

# Tạo tên file log với timestamp: hd_order_limit_dd_mm_yyyy_H_M_S.txt
log_timestamp = datetime.now().strftime('%d_%m_%Y_%H_%M_%S')
log_filename = logs_dir / f'hd_order_multi_{log_timestamp}.txt'

# Cải thiện logging với timestamp và UTF-8 encoding
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

# Tạo order logger riêng để track tất cả orders
order_logger = logging.getLogger('order')
order_logger.setLevel(logging.INFO)
order_log_path = logs_dir / 'order.log'
order_handler = logging.FileHandler(order_log_path, encoding='utf-8')
order_handler.setFormatter(logging.Formatter('%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
order_logger.addHandler(order_handler)

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

# [FIX 1] Bắt buộc tải lại thông tin Precision mới nhất từ Binance để tránh lỗi làm tròn sai
print("⏳ Đang cập nhật thông tin thị trường (Precision/TickSize)...", flush=True)
try:
    exchange.load_markets(True) # True = Force reload
    print("✅ Đã cập nhật xong thông tin thị trường.", flush=True)
except Exception as e:
    print(f"⚠️ Lỗi cập nhật markets: {e}", flush=True)

# Khởi tạo order helper
order_helper = BinanceOrderHelper(exchange)

# ===================================================================
# LOCAL ORDER CACHE - Chống lặp đơn khi Binance API lỗi/timeout
# Cache lưu {symbol: {'algo_id': str, 'placed_at': float}}
# Được persist vào file để giữ qua lần restart bot
# ===================================================================
_order_cache: dict = {}
_cache_lock = threading.Lock()
_CACHE_FILE = cst.account_dir('data') / 'order_cache_multi.json'  # [MULTI-ACC]
_CACHE_TTL_SECONDS = 86400  # 24 giờ - thời gian order còn có thể valid


def _load_order_cache():
    """Load cache từ file JSON khi bot khởi động"""
    global _order_cache
    try:
        _CACHE_FILE.parent.mkdir(exist_ok=True)
        if _CACHE_FILE.exists():
            with open(_CACHE_FILE, 'r', encoding='utf-8') as f:
                _order_cache = json.load(f)
            logger.info(f"[CACHE] Đã load {len(_order_cache)} entries từ {_CACHE_FILE}")
            print(f"✅ [CACHE] Đã load {len(_order_cache)} symbol từ cache file", flush=True)
        else:
            _order_cache = {}
            logger.info("[CACHE] Chưa có cache file, khởi tạo rỗng")
    except Exception as e:
        logger.error(f"[CACHE] Lỗi load cache: {e}", exc_info=True)
        _order_cache = {}


def _save_order_cache():
    """Lưu cache ra file JSON (gọi bên trong _cache_lock)"""
    try:
        _CACHE_FILE.parent.mkdir(exist_ok=True)
        with open(_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(_order_cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"[CACHE] Lỗi save cache: {e}", exc_info=True)


def add_to_order_cache(symbol: str, algo_id: str):
    """Thêm order vừa đặt thành công vào cache"""
    with _cache_lock:
        _order_cache[symbol] = {
            'algo_id': str(algo_id),
            'placed_at': time.time()
        }
        _save_order_cache()
    logger.info(f"[CACHE] Đã thêm {symbol} (algoId={algo_id}) vào cache")


def remove_from_order_cache(symbol: str):
    """Xóa symbol khỏi cache khi API xác nhận không còn order"""
    with _cache_lock:
        if symbol in _order_cache:
            del _order_cache[symbol]
            _save_order_cache()
            logger.info(f"[CACHE] Đã xóa {symbol} khỏi cache (API xác nhận hết order)")


def is_in_order_cache(symbol: str) -> tuple:
    """
    Kiểm tra symbol có trong cache và còn hiệu lực không.
    Returns: (True/False, algo_id hoặc None)
    """
    with _cache_lock:
        if symbol not in _order_cache:
            return False, None
        entry = _order_cache[symbol]
        age = time.time() - entry.get('placed_at', 0)
        if age > _CACHE_TTL_SECONDS:
            del _order_cache[symbol]
            _save_order_cache()
            logger.info(f"[CACHE] {symbol} đã hết hạn cache ({age/3600:.1f}h), xóa")
            return False, None
        return True, entry.get('algo_id')


def is_same_pair(sym1, sym2):
    """
    So sánh 2 symbols có giống nhau không (bỏ qua format)
    VD: HOME/USDT:USDT == HOMEUSDT == HOME/USDT
    """
    # Chuẩn hóa về dạng HOMEUSDT (chỉ giữ base+quote)
    sym1 = sym1.replace("/", "").replace(":USDT", "").upper().strip()
    sym2 = sym2.replace("/", "").replace(":USDT", "").upper().strip()
    return sym1 == sym2

def get_algo_orders_for_symbol(symbol):
    """
    Lấy algo orders (open + lịch sử 24h). openAlgoOrders trước để tránh 400 allAlgoOrders.

    Returns:
        None  → Lỗi mạng/API thật (không parse được)
        []    → Không có order / symbol không có algo
        [..]  → Có danh sách orders
    """
    try:
        return fetch_algo_orders_for_symbol(symbol, history_hours=24)
    except Exception as e:
        logger.error(f"Lỗi khi lấy algo orders cho {symbol}: {e}", exc_info=True)
        return None

def cancel_all_open_orders(symbol):
    open_orders = exchange.fetch_open_orders(symbol)

    if open_orders:
        for order in open_orders:
            order_id = order['id']
            cancel_result = exchange.cancel_order(order_id, symbol)
            print(f"Hủy lệnh {order_id} kết quả: {cancel_result}", flush=True)
            msg = f"Đã Hủy lệnh Chờ: {order['symbol']}"
            telegram_factory.send_tele(msg,cst.chat_id, True , True)
    else:
        print(f"Không có lệnh mở nào cho {symbol}", flush=True)



def normalize_symbol(symbol):
    """
    Chuẩn hóa symbol về format CCXT Binance Futures (có dấu / và :USDT)
    VD: BTCUSDT -> BTC/USDT:USDT, BTC/USDT -> BTC/USDT:USDT
    """
    symbol = symbol.strip().upper()
    
    # Nếu đã có :USDT, giữ nguyên
    if ':USDT' in symbol:
        return symbol
    
    # Nếu có dấu / nhưng chưa có :USDT
    if '/' in symbol:
        # BID/USDT -> BID/USDT:USDT
        if symbol.endswith('/USDT'):
            return f"{symbol}:USDT"
        return symbol
    
    # Tự động thêm /USDT:USDT nếu chưa có
    if symbol.endswith('USDT'):
        base = symbol[:-4]
        return f"{base}/USDT:USDT"
    
    # Fallback: thêm /USDT:USDT vào cuối
    return f"{symbol}/USDT:USDT"

def is_symbol_tradeable(symbol):
    """
    Kiểm tra symbol có cho phép giao dịch không
    Returns: (True/False, error_message, normalized_symbol)
    """
    try:
        # Chuẩn hóa symbol
        original_symbol = symbol
        symbol = normalize_symbol(symbol)
        
        if symbol != original_symbol:
            logger.info(f"Đã chuẩn hóa symbol: {original_symbol} -> {symbol}")
        
        # Kiểm tra symbol có tồn tại trong markets không
        # Vì exchange đã config defaultType='future', nên exchange.markets CHỈ chứa futures
        if symbol not in exchange.markets:
            # Thử tìm các symbol tương tự
            similar = [s for s in exchange.markets.keys() if original_symbol.replace('/', '').upper() in s.replace('/', '').upper()]
            if similar:
                suggestion = f"Có thể bạn muốn: {', '.join(similar[:3])}"
            else:
                suggestion = "Không tìm thấy symbol tương tự trên Binance Futures"
            return False, f"Symbol {symbol} không tồn tại trên Binance Futures. {suggestion}", symbol
        
        market = exchange.markets[symbol]
        
        # Kiểm tra trạng thái active
        if not market.get('active', False):
            return False, f"Symbol {symbol} đang bị tạm ngưng giao dịch (inactive)", symbol
        
        # Kiểm tra info từ Binance (status)
        info = market.get('info', {})
        status = info.get('status', '').upper()
        contract_status = info.get('contractStatus', '').upper()
        
        # TRADING = cho phép giao dịch bình thường
        # Các trạng thái khác: BREAK, HALT, AUCTION_MATCH, PENDING_TRADING...
        if status and status != 'TRADING':
            return False, f"Symbol {symbol} status={status} (không phải TRADING)", symbol
        
        # PENDING_TRADING = chưa mở giao dịch
        # TRADING = đang giao dịch bình thường
        # PRE_DELIVERING, DELIVERING, DELIVERED = đang/đã giao hàng (delisting)
        if contract_status and contract_status not in ['TRADING', '']:
            return False, f"Symbol {symbol} contractStatus={contract_status}", symbol
        
        return True, "", symbol
        
    except Exception as e:
        logger.error(f"Lỗi khi kiểm tra tradeable cho {symbol}: {e}", exc_info=True)
        return False, f"Lỗi kiểm tra: {str(e)}", symbol

def has_position(sym):
    """Kiểm tra symbol đã có vị thế (đã vào lệnh) chưa"""
    try:
        balance = exchange.fetch_balance()
        if not balance or 'info' not in balance:
            logger.warning(f"fetch_balance() trả về dữ liệu không hợp lệ cho {sym}")
            return False
        positions = balance['info'].get('positions', [])
        for position in positions:
            symbol = position.get('symbol', '')
            position_amt = position.get('positionAmt', '0')
            if is_same_pair(symbol, sym) and float(position_amt) != 0:
                return True
        return False
    except Exception as e:
        logger.error(f"Lỗi khi kiểm tra vị thế cho {sym}: {e}", exc_info=True)
        return False

def get_position_amt(sym):
    """
    Trả về positionAmt (signed float) của symbol.
    > 0 = LONG, < 0 = SHORT, 0 = không có vị thế.
    Raise nếu API lỗi → caller sẽ bỏ qua dòng để tránh đặt trùng lệnh.
    """
    balance = exchange.fetch_balance()
    if not balance or 'info' not in balance:
        logger.warning(f"fetch_balance() không hợp lệ cho {sym}")
        raise RuntimeError("fetch_balance trả về dữ liệu không hợp lệ")
    positions = balance['info'].get('positions', [])
    for position in positions:
        symbol = position.get('symbol', '')
        if is_same_pair(symbol, sym):
            return float(position.get('positionAmt', '0') or 0)
    return 0.0

def has_pending_reverse_limit_order(symbol, reverse_side):
    """
    Kiểm tra đã có LỆNH NGƯỢC (LIMIT reduce_only) cùng side chưa.
    reverse_side: side của lệnh ngược (LONG->'sell', SHORT->'buy').
    Raise nếu API lỗi → caller bỏ qua dòng (tránh đặt trùng lệnh ngược).
    """
    open_orders = exchange.fetch_open_orders(symbol)
    if not open_orders:
        return False
    for order in open_orders:
        o_type = str(order.get('type', '')).upper()
        o_side = str(order.get('side', '')).lower()
        info = order.get('info', {}) if isinstance(order.get('info'), dict) else {}
        reduce_only = order.get('reduceOnly', False) or info.get('reduceOnly', False) \
            or str(info.get('reduceOnly', 'false')).lower() == 'true'
        if o_type == 'LIMIT' and o_side == reverse_side.lower() and reduce_only:
            return True
    return False

def has_pending_stop_market_order(symbol, sl_side):
    """
    Kiểm tra đã có LỆNH CẮT LỖ (STOP_MARKET reduce_only) cùng side chưa.
    sl_side: side của lệnh cắt lỗ (LONG->'sell', SHORT->'buy').
    Raise nếu API lỗi → caller bỏ qua để tránh đặt trùng lệnh SL.
    """
    open_orders = exchange.fetch_open_orders(symbol)
    if not open_orders:
        return False
    for order in open_orders:
        o_type = str(order.get('type', '')).upper()
        o_side = str(order.get('side', '')).lower()
        info = order.get('info', {}) if isinstance(order.get('info'), dict) else {}
        reduce_only = order.get('reduceOnly', False) or info.get('reduceOnly', False) \
            or str(info.get('reduceOnly', 'false')).lower() == 'true'
        # STOP_MARKET (CCXT có thể trả 'STOP_MARKET' hoặc 'STOP')
        if 'STOP' in o_type and o_side == sl_side.lower() and reduce_only:
            return True
    return False

def has_pending_limit_order(symbol, side):
    """
    Kiểm tra symbol đã có OPEN LIMIT ORDER (lệnh vào) cùng chiều chưa.

    Lệnh LIMIT là open order thường (không phải algo order), nên phải dùng
    fetch_open_orders() thay vì fetch_algo_orders.

    Chỉ tính lệnh entry (reduceOnly=False) cùng side → bỏ qua lệnh ngược
    reduce_only do bot khác đặt.

    Fail-safe (giống bản trailing stop):
    - API OK + có limit entry cùng side → CHẶN
    - API OK + không có → CHO PHÉP (xóa cache)
    - API lỗi (Exception) + có cache → CHẶN
    - API lỗi (Exception) + không cache → CHO PHÉP (tránh chặn oan do timeout)
    """
    try:
        logger.info(f"[CHECK PENDING] {symbol}: Đang kiểm tra open LIMIT orders (side={side})...")
        open_orders = exchange.fetch_open_orders(symbol)

        # ── API THÀNH CÔNG + KHÔNG CÓ ORDERS ───────────────────────────
        if not open_orders:
            remove_from_order_cache(symbol)  # Xóa cache lỗi thời nếu có
            logger.info(f"[CHECK PENDING] {symbol}: Không có open orders → Cho phép tạo lệnh mới")
            return False

        # ── API THÀNH CÔNG + CÓ ORDERS → Lọc LIMIT entry cùng side ─────
        matched = []
        for order in open_orders:
            o_type = str(order.get('type', '')).upper()
            o_side = str(order.get('side', '')).lower()
            # reduceOnly có thể nằm ở top-level hoặc trong info
            info = order.get('info', {}) if isinstance(order.get('info'), dict) else {}
            reduce_only = order.get('reduceOnly', False) or info.get('reduceOnly', False) \
                or str(info.get('reduceOnly', 'false')).lower() == 'true'

            if o_type == 'LIMIT' and o_side == side.lower() and not reduce_only:
                matched.append(order.get('id', 'N/A'))

        if matched:
            logger.info(f"✅ {symbol} đã có {len(matched)} LIMIT entry order(s) cùng side {side}: {matched}")
            print(f"⏭️  {symbol} đã có {len(matched)} lệnh LIMIT chờ (side={side}), bỏ qua", flush=True)
            return True

        # Có open orders nhưng không phải LIMIT entry cùng side (vd lệnh ngược reduce_only)
        remove_from_order_cache(symbol)
        logger.info(f"[CHECK PENDING] {symbol}: Không có LIMIT entry cùng side {side} → Cho phép tạo lệnh mới")
        return False

    except Exception as e:
        logger.error(f"Lỗi khi kiểm tra open orders cho {symbol}: {e}", exc_info=True)
        in_cache, cached_algo_id = is_in_order_cache(symbol)
        if in_cache:
            logger.warning(f"[CHECK PENDING] {symbol}: API lỗi + có cache (id={cached_algo_id}) → CHẶN")
            print(f"⛔ {symbol}: Lỗi kiểm tra + có cache → CHẶN để tránh lặp đơn", flush=True)
            return True
        logger.warning(f"[CHECK PENDING] {symbol}: API lỗi + không cache → cho phép đặt lệnh")
        return False

def execute_command(commands):
    try:
        
        subprocess.run(commands, shell=True, check=True)
    except Exception as e:
        print(e, flush=True)

def is_number(s):
    try:
        float(s)
        return True
    except ValueError:
        return False
    
STATE_STOP = "STOP"
STATE_SHORT = "SHORT"
STATE_LONG  = "LONG"
STATE_CHO  = "CHỜ"
LENH_CHO = "LỆNH CHỜ"

# ===================================================================
# CHẾ ĐỘ ĐẶT LỆNH NGƯỢC:
#   Không dùng ô công tắc riêng. Cơ chế bật/tắt theo TỪNG DÒNG:
#     - Cột G (TP) CÓ giá  → bot đặt lệnh ngược (chốt lời) cho dòng đó
#     - Cột G (TP) TRỐNG   → bot chỉ đặt lệnh 1 (không đặt lệnh ngược)
# ===================================================================

# ══════════════════════════════════════════════════════════════════════════════
# CACHE TRẠNG THÁI B2 — CHỐNG LỖI 429 (vượt hạn mức Google Sheets)
#
#   Google chỉ cho 60 lượt ĐỌC/phút, dùng CHUNG cho MỌI tài khoản.
#   Trước đây mỗi dòng mã đều đọc lại B2 → 50 mã = 50 lượt/vòng/tài khoản,
#   chạy 3 tài khoản là ~186 lượt/phút → vượt 3 lần → 429.
#
#   Nay B2 chỉ đọc thật mỗi `state_cache_ttl_sec` giây (mặc định 10s),
#   trong khoảng đó các dòng dùng lại giá trị đã đọc.
#   ⇒ Bấm DỪNG trên sheet vẫn có hiệu lực, chậm nhất sau 10 giây.
# ══════════════════════════════════════════════════════════════════════════════
import rate_guard
STATE_CACHE_TTL = rate_guard.read_ttl(cst.config)
_state_box = rate_guard.new_box()

def invalidate_state_cache():
  """Xoá cache để lần gọi sau đọc lại B2 thật."""
  rate_guard.clear(_state_box)

def get_current_state(force=False):
  """
  Đọc trạng thái B2 — CÓ CACHE ngắn hạn để không vượt hạn mức Google Sheets.
  force=True → bỏ qua cache, đọc thật (dùng cho mốc quan trọng: đầu/cuối vòng).
  Returns: (state_value, timestamp)
  """
  return rate_guard.cached_state(_state_box, _fetch_current_state,
                                 STATE_CACHE_TTL, force)

def _fetch_current_state():
  """
  Đọc trạng thái B2 hiện tại từ Google Sheet (GỌI API THẬT — đừng gọi trực tiếp,
  hãy dùng get_current_state() để được cache).
  Returns: (state_value, timestamp)
  """
  try:
    result = gg_sheet_factory.get_dat_lenh("B2:B2")
    
    # ✅ Kiểm tra result có phải là HttpError không (trường hợp version cũ của gg_sheet_factory return HttpError)
    if isinstance(result, HttpError):
      logger.error(f"HttpError được return (không phải raise) từ get_dat_lenh: {result}")
      print(f"❌ Lỗi Google Sheets API: {result}", flush=True)
      return STATE_CHO, datetime.now()
    
    # Kiểm tra result có phải là list hợp lệ không
    if not isinstance(result, list):
      logger.error(f"Result không phải list: type={type(result)}, value={result}")
      print(f"❌ Dữ liệu trả về không hợp lệ (không phải list): {type(result)}", flush=True)
      return STATE_CHO, datetime.now()
    
    # Kiểm tra result có data không
    if len(result) == 0:
      logger.warning("B2 trống hoặc không có dữ liệu")
      return STATE_CHO, datetime.now()
    
    if len(result[0]) == 0:
      logger.warning("B2 không có giá trị")
      return STATE_CHO, datetime.now()
    
    state_value = result[0][0].strip().upper()
    return state_value, datetime.now()
    
  except HttpError as e:
    logger.error(f"HttpError khi đọc trạng thái từ B2: {e}", exc_info=True)
    print(f"❌ Lỗi Google Sheets API khi đọc B2: {e}", flush=True)
    return STATE_CHO, datetime.now()
  except TypeError as e:
    # TypeError: 'HttpError' object has no len() hoặc is not subscriptable
    logger.error(f"TypeError (có thể do HttpError được return thay vì raise): {e}", exc_info=True)
    print(f"❌ TypeError khi xử lý B2: {e}", flush=True)
    return STATE_CHO, datetime.now()
  except (IndexError, KeyError, AttributeError) as e:
    logger.error(f"Lỗi parse dữ liệu B2: {e}", exc_info=True)
    print(f"❌ Lỗi parse dữ liệu B2: {e}", flush=True)
    return STATE_CHO, datetime.now()
  except Exception as e:
    logger.error(f"Lỗi không xác định khi đọc B2: {e}", exc_info=True)
    print(f"❌ Lỗi không xác định khi đọc B2: {e}", flush=True)
    return STATE_CHO, datetime.now()

def get_capital_config():
  """
  Đọc cấu hình vốn từ Google Sheet
  - D1: % tỷ lệ vốn (ví dụ: 3.00%)
  - D2: Vốn mặc định (tối thiểu 10 USDT)
  - E2: Vốn tổng
  
  Returns: (d1_percent, d2_default, e2_total, has_error)
  """
  try:
    # Đọc D1:E2 (2 dòng x 2 cột)
    result = gg_sheet_factory.get_dat_lenh("D1:E2")
    
    # ✅ Kiểm tra result có phải là HttpError không
    if isinstance(result, HttpError):
      logger.error(f"HttpError được return từ get_dat_lenh: {result}")
      print(f"❌ Lỗi Google Sheets API: {result}", flush=True)
      return None, None, None, True
    
    # Kiểm tra result có phải là list hợp lệ không
    if not isinstance(result, list):
      logger.error(f"Result không phải list: type={type(result)}, value={result}")
      print(f"❌ Dữ liệu trả về không hợp lệ: {type(result)}", flush=True)
      return None, None, None, True
    
    # Kiểm tra có đủ 2 dòng không
    if len(result) < 2:
      logger.warning(f"Không đủ dữ liệu (cần 2 dòng D1:E2, chỉ có {len(result)})")
      return None, None, None, True
    
    # Parse D1 (% tỷ lệ vốn)
    d1_percent = None
    try:
      if len(result[0]) > 0 and result[0][0]:
        d1_str = str(result[0][0]).strip().replace("%", "")
        if d1_str and d1_str not in ["#DIV/0!", "#VALUE!", "#ERROR!", "#N/A"]:
          d1_percent = float(d1_str) / 100  # Convert % sang decimal (3.00% -> 0.03)
          logger.info(f"D1 (% vốn): {d1_str}% = {d1_percent}")
    except (ValueError, TypeError) as e:
      logger.warning(f"Không parse được D1: {e}")
    
    # Parse D2 (vốn mặc định)
    d2_default = None
    try:
      if len(result[1]) > 0 and result[1][0]:
        d2_str = str(result[1][0]).strip()
        if d2_str and d2_str not in ["#DIV/0!", "#VALUE!", "#ERROR!", "#N/A"]:
          d2_default = float(d2_str)
          logger.info(f"D2 (vốn mặc định): {d2_default} USDT")
    except (ValueError, TypeError) as e:
      logger.warning(f"Không parse được D2: {e}")
    
    # Parse E2 (vốn tổng)
    e2_total = None
    try:
      if len(result[1]) > 1 and result[1][1]:
        e2_str = str(result[1][1]).strip()
        if e2_str and e2_str not in ["#DIV/0!", "#VALUE!", "#ERROR!", "#N/A"]:
          e2_total = float(e2_str)
          logger.info(f"E2 (vốn tổng): {e2_total} USDT")
    except (ValueError, TypeError) as e:
      logger.warning(f"Không parse được E2: {e}")
    
    return d1_percent, d2_default, e2_total, False
    
  except HttpError as e:
    logger.error(f"HttpError khi đọc cấu hình vốn: {e}", exc_info=True)
    print(f"❌ Lỗi Google Sheets API: {e}", flush=True)
    return None, None, None, True
  except TypeError as e:
    logger.error(f"TypeError khi xử lý cấu hình vốn: {e}", exc_info=True)
    print(f"❌ TypeError: {e}", flush=True)
    return None, None, None, True
  except Exception as e:
    logger.error(f"Lỗi không xác định khi đọc cấu hình vốn: {e}", exc_info=True)
    print(f"❌ Lỗi: {e}", flush=True)
    return None, None, None, True

# ===================================================================
# MULTI-LEG ENGINE: đọc cấu hình leg từ config.ini và tiện ích snapshot
# ===================================================================
_VALID_LEG_TYPES = {'limit', 'market', 'stop_market', 'stop_limit', 'trailing'}

# Mã số kiểu lệnh gõ trên sheet (per-row). Cũng chấp nhận tên chữ.
_CODE_TO_TYPE = {'1': 'limit', '2': 'market', '3': 'stop_market', '4': 'stop_limit', '5': 'trailing'}

def _resolve_leg_type(leg, d):
    """
    Kiểu lệnh hiệu lực của leg tại dòng d:
      - Nếu leg có 'type_col' → đọc mã kiểu từ ô đó (1..5 hoặc tên chữ).
        Ô trống/mã lạ → None (leg này TẮT cho dòng đó).
      - Nếu không có 'type_col' → dùng type cố định trong config.
    """
    tc = leg.get('type_col')
    if tc is not None:
        if tc < 0 or len(d) <= tc:
            return None
        raw = str(d[tc]).strip().lower()
        if not raw:
            return None
        if raw in _CODE_TO_TYPE:
            return _CODE_TO_TYPE[raw]
        if raw in _VALID_LEG_TYPES:
            return raw
        return None  # mã lạ → tắt leg cho dòng này
    return leg.get('type')

def _col_to_idx(letter):
    """'A'->0, 'D'->3, 'AA'->26. None nếu rỗng/không hợp lệ."""
    letter = str(letter).strip().upper()
    if not letter:
        return None
    idx = 0
    for ch in letter:
        if not ('A' <= ch <= 'Z'):
            return None
        idx = idx * 26 + (ord(ch) - ord('A') + 1)
    return idx - 1

def load_legs():
    """
    Đọc cấu hình leg từ [global]:
      legN_role, legN_col, legN_aux, legN_pct_col,
      legN_type      = kiểu cố định (limit/market/stop_market/stop_limit/trailing) — dùng khi KHÔNG có type_col
      legN_type_col  = cột sheet chứa MÃ kiểu lệnh theo dòng (1..5) → per-row type
      legN_source    = tab nguồn: 'dat_lenh' (ĐẶT LỆNH 100 MÃ) | 'cho_va_khop' (Chờ và khớp)
                       Mặc định: entry → dat_lenh ; exit → cho_va_khop
    Leg hợp lệ nếu có type_col HOẶC có type cố định hợp lệ.
    """
    legs = []
    try:
        count = cst.config.getint('global', 'multi_leg_count', fallback=0)
    except Exception:
        count = 0
    for i in range(1, count + 1):
        type_col = _col_to_idx(cst.config.get('global', f'leg{i}_type_col', fallback=''))
        t = cst.config.get('global', f'leg{i}_type', fallback='off').strip().lower()
        if type_col is None and t not in _VALID_LEG_TYPES:
            if t not in ('off', ''):
                logger.warning(f"[LEG] leg{i}: không có type_col và leg{i}_type='{t}' không hợp lệ → bỏ qua")
            continue
        role = cst.config.get('global', f'leg{i}_role', fallback='exit').strip().lower()
        if role not in ('entry', 'exit'):
            role = 'exit'
        # Nguồn dữ liệu: mặc định entry đọc tab "Đặt lệnh", exit đọc tab "Chờ và khớp"
        src = cst.config.get('global', f'leg{i}_source', fallback='').strip().lower()
        if src not in ('dat_lenh', 'cho_va_khop'):
            src = 'dat_lenh' if role == 'entry' else 'cho_va_khop'
        legs.append({
            'idx': i,
            'type': t if t in _VALID_LEG_TYPES else None,
            'type_col': type_col,
            'role': role,
            'source': src,
            'col': _col_to_idx(cst.config.get('global', f'leg{i}_col', fallback='')),
            'aux': _col_to_idx(cst.config.get('global', f'leg{i}_aux', fallback='')),
            'pct_col': _col_to_idx(cst.config.get('global', f'leg{i}_pct_col', fallback='')),
        })
    return legs

# Cho phép đặt THÊM lệnh vào khi mã đã có vị thế (rải lệnh / DCA).
# false (mặc định) = 1 mã chỉ vào 1 lần — an toàn, giữ hành vi cũ.
try:
    ALLOW_DCA = cst.config.getboolean('global', 'allow_dca', fallback=False)
except Exception:
    ALLOW_DCA = False

# SL dùng cờ closePosition của Binance: lệnh tự đóng TOÀN BỘ vị thế khi chạm giá,
# không gắn khối lượng cố định → rải lệnh làm vị thế tăng vẫn được bảo vệ đủ.
try:
    SL_CLOSE_POSITION = cst.config.getboolean('global', 'exit_sl_close_position', fallback=True)
except Exception:
    SL_CLOSE_POSITION = True

# TP là lệnh Limit (cần đúng giá) nên không dùng được closePosition.
# Thay vào đó: khi khối lượng vị thế đổi, HỦY lệnh TP cũ rồi đặt lại cho khớp.
try:
    TP_RESIZE = cst.config.getboolean('global', 'exit_tp_resize', fallback=True)
except Exception:
    TP_RESIZE = True

# Lệch khối lượng bao nhiêu thì coi là "cần cập nhật" (%).
try:
    RESIZE_TOL = cst.config.getfloat('global', 'exit_resize_tolerance_pct', fallback=1.0) / 100.0
except Exception:
    RESIZE_TOL = 0.01


def _read_cell_number(d, idx):
    """Đọc số dương từ ô d[idx] (bỏ %). None nếu rỗng/không hợp lệ/<=0."""
    if idx is None or idx < 0 or len(d) <= idx:
        return None
    raw = str(d[idx]).strip().replace('%', '')
    if not raw or not is_number(raw):
        return None
    v = float(raw)
    return v if v > 0 else None

def compute_capital(d, capital_idx, d1_percent, d2_default, e2_total):
    """Vốn 1 dòng: ưu tiên cột H → D1×E2 (min 10) → D2. None nếu không có."""
    try:
        if len(d) > capital_idx and d[capital_idx]:
            h = str(d[capital_idx]).strip()
            if h and h not in ["#DIV/0!", "#VALUE!", "#ERROR!", "#N/A"]:
                return float(h)
    except (ValueError, TypeError):
        pass
    if e2_total is not None and d1_percent is not None:
        return max(d1_percent * e2_total, 10)
    if d2_default is not None:
        return d2_default
    return None

def _order_type_family(otype):
    o = str(otype).upper()
    if 'TRAILING' in o or 'CONDITIONAL' in o:
        return 'trailing'
    if 'STOP' in o:
        return 'stop'
    if o == 'LIMIT':
        return 'limit'
    if o == 'MARKET':
        return 'market'
    return o.lower()

def _leg_family(t):
    if t == 'trailing':
        return 'trailing'
    if t in ('stop_market', 'stop_limit'):
        return 'stop'
    return t  # limit, market

def build_symbol_snapshot(symbol, need_algo):
    """
    Trả (snapshot_list, algo_ok).
    snapshot_list: [{'family','side','reduce_only','price'}] gộp open orders (+ algo nếu cần).
    algo_ok: True nếu không cần algo hoặc lấy algo thành công; False nếu cần mà API lỗi.
    Raise nếu fetch_open_orders lỗi → caller bỏ qua dòng (tránh đặt trùng).
    """
    snap = []
    for o in exchange.fetch_open_orders(symbol):
        info = o.get('info', {}) if isinstance(o.get('info'), dict) else {}
        ro = o.get('reduceOnly', False) or info.get('reduceOnly', False) \
            or str(info.get('reduceOnly', 'false')).lower() == 'true'
        price = o.get('triggerPrice') or o.get('stopPrice') or o.get('price') \
            or info.get('stopPrice') or info.get('price')
        try:
            price = float(price) if price not in (None, '') else None
        except (ValueError, TypeError):
            price = None
        # Lưu thêm khối lượng + id để so sánh với vị thế và hủy khi cần cập nhật
        amt = o.get('amount') or o.get('remaining') or info.get('origQty')
        try:
            amt = float(amt) if amt not in (None, '') else None
        except (ValueError, TypeError):
            amt = None
        cp = str(info.get('closePosition', '')).strip().lower() == 'true'
        snap.append({
            'family': _order_type_family(o.get('type', '')),
            'side': str(o.get('side', '')).lower(),
            'reduce_only': bool(ro) or cp,
            'price': price,
            'amount': amt,
            'id': o.get('id'),
            'close_position': cp,
        })
    algo_ok = True
    if need_algo:
        algo = get_algo_orders_for_symbol(symbol)  # None nếu lỗi, [] nếu không có
        if algo is None:
            algo_ok = False
        else:
            for a in algo:
                if str(a.get('algoStatus', '')).upper() != 'NEW':
                    continue
                ro = a.get('reduceOnly', False) or str(a.get('reduceOnly', 'false')).lower() == 'true'
                ap = a.get('activatePrice') or a.get('activationPrice')
                try:
                    ap = float(ap) if ap not in (None, '') else None
                except (ValueError, TypeError):
                    ap = None
                snap.append({'family': 'trailing', 'side': str(a.get('side', '')).lower(),
                             'reduce_only': bool(ro), 'price': ap,
                             'amount': None, 'id': a.get('algoId'), 'close_position': False})
    return snap, algo_ok

# Dung sai coi 2 lệnh là "cùng một giá" khi chống trùng.
# Trước đây để 0.002 (0.2%) — quá RỘNG: rải lệnh 1.380/1.379/1.378 (chênh 0.07%)
# bị gộp thành 1. Nay mặc định 0.0002 (0.02%) — chỉ gộp khi thực sự trùng giá.
try:
    _DEDUP_TOL = cst.config.getfloat('global', 'dedup_price_tolerance_pct', fallback=0.02) / 100.0
except Exception:
    _DEDUP_TOL = 0.0002


def _snapshot_find(snap, family, side, reduce_only, price, tol=None):
    """Tìm lệnh đã có khớp (loại + chiều + reduce_only + giá). None nếu chưa có."""
    if tol is None:
        tol = _DEDUP_TOL
    for s_ in snap:
        if s_['family'] == family and s_['side'] == side and s_['reduce_only'] == reduce_only:
            sp = s_.get('price')
            if price is None or sp is None:
                return s_
            if sp > 0 and abs(sp - price) / sp <= tol:
                return s_
    return None


def _snapshot_has(snap, family, side, reduce_only, price, tol=None):
    """Đã có lệnh cùng loại/chiều/reduce_only (và gần đúng giá) trong snapshot chưa."""
    if tol is None:
        tol = _DEDUP_TOL
    for s in snap:
        if s['family'] == family and s['side'] == side and s['reduce_only'] == reduce_only:
            if price is None or s['price'] is None:
                return True
            if s['price'] > 0 and abs(s['price'] - price) / s['price'] <= tol:
                return True
    return False

def plan_row(legs, d, pos_amt, snap, algo_ok, capital, last_price, entry_side,
             round_price=None, round_amount=None, allow_dca=False,
             allow_close_position=False, resize_exits=False, resize_tol=0.01,
             cancel_out=None):
    """
    Thuần logic (KHÔNG gọi API) — quyết định các lệnh cần đặt cho 1 dòng.
    Trả (plans, skips):
      plans: [{'leg_idx','type','role','side','price','aux','amount','reduce_only'}]
      skips: [(leg_idx, lý_do)]  — để log/debug
    round_price/round_amount: hàm làm tròn (None = giữ nguyên) → test không cần exchange.
    """
    rp = round_price if round_price else (lambda x: x)
    ra = round_amount if round_amount else (lambda x: x)
    has_pos = (pos_amt != 0)
    exit_side = "sell" if pos_amt > 0 else "buy"
    work = list(snap)  # bản sao snapshot để chống trùng ngay trong cùng dòng
    plans, skips = [], []
    cancel_ids = cancel_out if cancel_out is not None else []
    for leg in legs:
        # Kiểu lệnh của leg này — theo dòng (type_col) hoặc cố định (config)
        lt = _resolve_leg_type(leg, d)
        if lt is None:
            skips.append((leg['idx'], 'cột kiểu lệnh trống/không hợp lệ')); continue
        fam = _leg_family(lt)
        is_entry = (leg['role'] == 'entry')
        reduce_only = not is_entry

        if is_entry:
            # allow_dca=False (mặc định): 1 mã chỉ vào 1 lần → có vị thế rồi thì dừng.
            # allow_dca=True: cho RẢI LỆNH / DCA — vẫn đặt thêm lệnh vào dù đã có vị thế.
            if has_pos and not allow_dca:
                skips.append((leg['idx'], 'đã có vị thế (bật allow_dca nếu muốn rải lệnh)')); continue
            side = entry_side
        else:
            if not has_pos:
                skips.append((leg['idx'], 'chưa có vị thế')); continue
            side = exit_side

        price = None
        if lt != 'market':
            price = _read_cell_number(d, leg['col'])
            if price is None:
                skips.append((leg['idx'], 'cột giá trống')); continue
            price = rp(price)

        aux = None
        if lt in ('stop_limit', 'trailing'):
            aux = _read_cell_number(d, leg['aux'])
            if aux is None:
                skips.append((leg['idx'], 'thiếu cột phụ aux')); continue
            if lt == 'stop_limit':
                aux = rp(aux)

        if is_entry and lt == 'limit':
            if side == 'buy' and price >= last_price:
                skips.append((leg['idx'], 'buy limit >= giá hiện tại')); continue
            if side == 'sell' and price <= last_price:
                skips.append((leg['idx'], 'sell limit <= giá hiện tại')); continue

        if fam == 'trailing' and not algo_ok:
            skips.append((leg['idx'], 'algo API lỗi, bỏ để tránh trùng')); continue

        # SL kiểu stop_market: dùng closePosition → luôn đóng trọn vị thế,
        # không cần khối lượng nên KHÔNG bao giờ phải đặt lại khi vị thế tăng.
        use_close_position = (not is_entry) and lt == 'stop_market' and allow_close_position

        # Đã có lệnh tương tự chưa? (cùng loại + chiều + reduce_only + giá)
        existing = _snapshot_find(work, fam, side, reduce_only, price)
        if existing is not None:
            # closePosition thì khối lượng vô nghĩa → giữ nguyên, không cần cập nhật
            if use_close_position or existing.get('close_position'):
                skips.append((leg['idx'], 'đã có lệnh tương tự')); continue
            # Lệnh cũ có khối lượng lệch nhiều so với vị thế hiện tại → cần đặt lại
            want = abs(pos_amt) * (_read_cell_number(d, leg['pct_col']) or 100.0) / 100.0
            have = existing.get('amount')
            if (resize_exits and have and want > 0
                    and abs(have - want) / want > resize_tol):
                cancel_ids.append((existing.get('id'), leg['idx'], have, want))
                work.remove(existing)          # coi như đã gỡ, cho phép đặt lại
            else:
                skips.append((leg['idx'], 'đã có lệnh tương tự')); continue

        if is_entry:
            if capital is None or capital < 10:
                skips.append((leg['idx'], f'vốn không hợp lệ ({capital})')); continue
            base = price if price else last_price
            amount = ra(capital / base)
            if amount <= 0:
                skips.append((leg['idx'], 'khối lượng = 0')); continue
            if base * amount < 5:
                skips.append((leg['idx'], 'notional < 5')); continue
        else:
            pct = _read_cell_number(d, leg['pct_col'])
            pct = min(pct, 100.0) if pct else 100.0
            amount = ra(abs(pos_amt) * pct / 100.0)
            if amount <= 0:
                skips.append((leg['idx'], 'khối lượng = 0')); continue

        plans.append({'leg_idx': leg['idx'], 'type': lt, 'role': leg['role'], 'side': side,
                      'price': price, 'aux': aux, 'amount': amount, 'reduce_only': reduce_only,
                      'close_position': use_close_position})
        work.append({'family': fam, 'side': side, 'reduce_only': reduce_only, 'price': price})
    return plans, skips


def _place_order(symbol, p, tag="ORDER"):
    """Đặt 1 lệnh theo kế hoạch p (kết quả plan_row). Dùng chung cho cả 2 pha."""
    lt = p['type']; side = p['side']; amount = p['amount']
    price = p['price']; aux = p['aux']; reduce_only = p['reduce_only']; leg_idx = p['leg_idx']
    try:
        print(f"📤 [{tag}] {symbol} leg{leg_idx} [{lt}/{p['role']}] {side} {amount} @ {price} aux={aux} ro={reduce_only}", flush=True)
        if lt == 'limit':
            od = order_helper.create_limit_order(symbol, side, amount, price, reduce_only)
        elif lt == 'market':
            od = order_helper.create_market_order(symbol, side, amount, reduce_only)
        elif lt == 'stop_market':
            od = order_helper.create_stop_market_order(
                symbol, side, amount, price, reduce_only,
                close_position=p.get('close_position', False))
        elif lt == 'stop_limit':
            od = order_helper.create_stop_limit_order(symbol, side, amount, price, aux, reduce_only)
        elif lt == 'trailing':
            od = order_helper.create_trailing_stop_order(symbol, side, amount, price, aux, reduce_only)
        else:
            return False
        order_logger.info(f"LEG{leg_idx} [{lt}/{p['role']}] | {symbol} | {side} | price={price} aux={aux} | amt={amount} | ro={reduce_only} | id={od.get('id', 'N/A')}")
        printf(symbol, od)
        msg = (f"✅ <b>LEG {leg_idx} ({lt.upper()} / {p['role']})</b>\n\n"
               f"<b>Mã:</b> {symbol}\n<b>Side:</b> {side.upper()}\n"
               f"<b>Giá:</b> {price}\n<b>Aux:</b> {aux}\n<b>KL:</b> {amount}\n<b>reduceOnly:</b> {reduce_only}")
        telegram_factory.send_tele(msg, cst.chat_id, True, True)
        print(f"✅ {symbol} leg{leg_idx} đã đặt", flush=True)
        return True
    except Exception as e:
        print(f"❌ {symbol} leg{leg_idx} lỗi đặt lệnh: {e}", flush=True)
        logger.error(f"{symbol} leg{leg_idx} lỗi: {e}", exc_info=True)
        return False


def scan_cho_va_khop_legs(legs):
    """
    PHA B — Quét tab "Chờ và khớp" để đặt SL/TP cho các vị thế ĐANG MỞ.

    Vì sao dùng tab này (không dùng tab ĐẶT LỆNH): tab ĐẶT LỆNH là danh sách
    ứng viên (top tăng/giảm) thay đổi liên tục — mã đã khớp sẽ biến mất khỏi đó.
    Tab "Chờ và khớp" mới là nơi theo dõi vị thế thực tế (bot hd_update_cho_va_khop ghi).

    Điều kiện dòng (giống hd_order_123): cột D (ĐÃ KHỚP) = 'Y' VÀ cột P (ĐẶT LỆNH) = 'Y'.
    Cột đọc: A=Symbol, B=LONG/SHORT, D=Đã khớp, P=Đặt lệnh.
    Giá/kiểu mỗi leg theo cấu hình legN_col / legN_type_col / legN_aux / legN_pct_col.
    """
    legs = [l for l in legs if l.get('role') == 'exit']
    if not legs:
        return
    try:
        rows = gg_sheet_factory.get_cho_va_khop("A4:Z1000", value_render_option="UNFORMATTED_VALUE")
    except Exception as e:
        print(f"⚠️ Lỗi đọc tab 'Chờ và khớp': {e}", flush=True)
        logger.error(f"Lỗi đọc tab 'Chờ và khớp': {e}", exc_info=True)
        return
    if not isinstance(rows, list) or not rows:
        print("📊 Tab 'Chờ và khớp' chưa có dữ liệu", flush=True)
        return

    print(f"🔁 [SL/TP] Quét tab 'Chờ và khớp': {len(rows)} dòng | {len(legs)} leg exit", flush=True)
    logger.info(f"[SL/TP] Quét Chờ và khớp, legs={[(l['idx'], l['type'], l['type_col']) for l in legs]}")
    need_algo = any(l.get('type') == 'trailing' or l.get('type_col') is not None for l in legs)

    for ri, d in enumerate(rows, start=4):
        try:
            if not d or len(d) == 0 or not str(d[0]).strip():
                continue
            sym = str(d[0]).strip()

            # Cột D (idx 3) = ĐÃ KHỚP → chỉ xử lý 'Y' (vị thế đang mở)
            da_khop = str(d[3]).strip().upper() if len(d) > 3 else ""
            if da_khop != "Y":
                continue

            # Cột P (idx 15) = ĐẶT LỆNH → bắt buộc 'Y'
            allow = str(d[15]).strip().upper() if len(d) > 15 else ""
            if allow != "Y":
                logger.info(f"[SL/TP] {sym} (dòng {ri}): cột P != 'Y' → bỏ qua")
                continue

            is_tradeable, err, normalized = is_symbol_tradeable(sym)
            if not is_tradeable:
                logger.warning(f"[SL/TP] {sym}: {err}")
                continue
            symbol = normalized

            # Vị thế thực tế + lệnh đang mở (chống trùng)
            try:
                pos_amt = get_position_amt(symbol)
                snap, algo_ok = build_symbol_snapshot(symbol, need_algo)
            except Exception as e:
                print(f"⚠️  [SL/TP] {symbol}: lỗi đọc vị thế/lệnh: {e} → bỏ qua dòng", flush=True)
                logger.error(f"[SL/TP] {symbol}: lỗi snapshot: {e}", exc_info=True)
                continue

            if pos_amt == 0:
                logger.info(f"[SL/TP] {symbol}: sheet ghi ĐÃ KHỚP nhưng Binance không còn vị thế → bỏ qua")
                continue

            try:
                last_price = float(exchange.fetch_ticker(symbol)["last"])
            except Exception as e:
                logger.warning(f"[SL/TP] {symbol}: lỗi lấy giá hiện tại: {e}")
                continue

            def _rp(v):
                try:
                    return float(exchange.price_to_precision(symbol, v))
                except Exception:
                    return v

            def _ra(v):
                try:
                    return float(exchange.amount_to_precision(symbol, v))
                except Exception:
                    return v

            # capital=None vì leg exit tính khối lượng theo vị thế, không theo vốn
            can_huy = []
            plans, skips = plan_row(legs, d, pos_amt, snap, algo_ok, None, last_price,
                                    "buy", round_price=_rp, round_amount=_ra,
                                    allow_close_position=SL_CLOSE_POSITION,
                                    resize_exits=TP_RESIZE, resize_tol=RESIZE_TOL,
                                    cancel_out=can_huy)
            for leg_idx, reason in skips:
                logger.info(f"[SL/TP][{symbol}] leg{leg_idx} bỏ qua: {reason}")

            # Vị thế đã đổi (rải lệnh khớp thêm) → hủy lệnh cũ để đặt lại đúng khối lượng
            for oid, leg_idx, cu, moi in can_huy:
                if not oid:
                    continue
                try:
                    exchange.cancel_order(oid, symbol)
                    print(f"♻️  [SL/TP] {symbol} leg{leg_idx}: hủy lệnh cũ "
                          f"(KL {cu} → {round(moi, 6)}) để đặt lại", flush=True)
                    logger.info(f"[SL/TP] {symbol} leg{leg_idx}: hủy {oid}, KL {cu} → {moi}")
                except Exception as e:
                    print(f"⚠️  [SL/TP] {symbol} leg{leg_idx}: không hủy được lệnh cũ {oid}: {e}",
                          flush=True)
                    logger.error(f"[SL/TP] {symbol}: hủy {oid} lỗi: {e}")
                    plans = [x for x in plans if x['leg_idx'] != leg_idx]

            for p in plans:
                _place_order(symbol, p, tag="SL/TP")

        except Exception as e:
            print(f"❌ [SL/TP] Lỗi xử lý dòng {ri}: {e}", flush=True)
            logger.error(f"[SL/TP] Lỗi dòng {ri}: {e}", exc_info=True)
            continue


def _do_entry_phase():
  print(f"{datetime.now()}. Scan Vào Lệnh----------------------------------------------------", flush=True)
  sys.stdout.flush()  # Flush ngay sau khi bắt đầu scan
  logger.info(f"{datetime.now()}. Scan Vào Lệnh----------------------------------------------------")

  # Đọc trạng thái hệ thống từ B2 (theo quy trình thực tế)
  state_value, read_time = get_current_state()
  print(f"📌 Trạng thái: {state_value} (đọc lúc {read_time.strftime('%H:%M:%S')})", flush=True)
  logger.info(f"[SCAN START] Đọc trạng thái từ B2: {state_value} (timestamp: {read_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]})")

  # Đọc cấu hình vốn từ D1, D2, E2
  d1_percent, d2_default, e2_total, has_error = get_capital_config()
  
  if has_error:
    print(f"⚠️ Lỗi đọc cấu hình vốn (D1/D2/E2)", flush=True)
    logger.warning("Lỗi đọc cấu hình vốn, không thể đặt lệnh")
    d1_percent = None
    d2_default = None
    e2_total = None
  
  # Kiểm tra nếu E2 và D2 đều rỗng → KHÔNG đặt lệnh
  if e2_total is None and d2_default is None:
    print(f"⚠️ E2 và D2 đều rỗng → Không đặt lệnh (cần ít nhất 1 trong 2)", flush=True)
    logger.warning("E2 và D2 đều rỗng → Không đặt lệnh")
  else:
    # Log cấu hình
    print(f"💰 Cấu hình vốn:", flush=True)
    if d1_percent is not None:
      print(f"   D1 (% vốn): {d1_percent*100:.2f}%", flush=True)
    else:
      print(f"   D1 (% vốn): Không có", flush=True)
    
    if d2_default is not None:
      print(f"   D2 (vốn mặc định): {d2_default} USDT", flush=True)
    else:
      print(f"   D2 (vốn mặc định): Không có", flush=True)
    
    if e2_total is not None:
      print(f"   E2 (vốn tổng): {e2_total} USDT", flush=True)
    else:
      print(f"   E2 (vốn tổng): Không có", flush=True)
    
    logger.info(f"Cấu hình vốn: D1={d1_percent}, D2={d2_default}, E2={e2_total}")

  if state_value == STATE_STOP:
    logger.warning("🛑 LỆNH STOP ĐƯỢC KÍCH HOẠT!")
    msg = "🛑 <b>LỆNH STOP KÍCH HOẠT</b>\n\n<b>Trạng thái:</b> Đang xử lý..."
    telegram_factory.send_tele(msg, cst.chat_id, True, True)
    
    # Đóng tất cả vị thế
    positions = exchange.fetch_positions()
    closed_positions = 0
    
    for position in positions:
        if float(position['info']['positionAmt']) != 0:
            symbol = position['symbol']
            amount = float(position['info']['positionAmt'])
            if amount != 0:
                try:
                    if amount > 0:
                        order = exchange.create_market_sell_order(symbol, amount)
                        logger.info(f"✅ Đã đóng vị thế LONG cho {symbol}: {order}")
                    elif amount < 0:
                        order = exchange.create_market_buy_order(symbol, abs(amount))
                        logger.info(f"✅ Đã đóng vị thế SHORT cho {symbol}: {order}")
                    closed_positions += 1
                except Exception as e:
                    logger.error(f"❌ Lỗi khi đóng vị thế {symbol}: {e}")
    
    # Hủy tất cả lệnh chờ
    try:
        all_open_orders = exchange.fetch_open_orders()
        cancelled_orders = 0
        for order in all_open_orders:
            try:
                exchange.cancel_order(order['id'], order['symbol'])
                cancelled_orders += 1
            except Exception as e:
                logger.error(f"Lỗi hủy lệnh {order['id']}: {e}")
        
        msg = f"✅ <b>HOÀN TẤT STOP</b>\n\n<b>Vị thế đã đóng:</b> {closed_positions}\n<b>Lệnh đã hủy:</b> {cancelled_orders}\n<b>Thời gian:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        telegram_factory.send_tele(msg, cst.chat_id, True, True)
        logger.warning("✅ Hoàn tất lệnh STOP")
    except Exception as e:
        logger.critical(f"🔴 Lỗi nghiêm trọng khi thực hiện STOP: {e}")

  elif state_value == "XÓA CHỜ":
    logger.info("🔄 Thực hiện lệnh XÓA CHỜ - Hủy tất cả lệnh pending, giữ vị thế")
    
    try:
        all_open_orders = exchange.fetch_open_orders()
        cancelled_count = 0
        
        for order in all_open_orders:
            try:
                exchange.cancel_order(order['id'], order['symbol'])
                cancelled_count += 1
                logger.info(f"Đã hủy lệnh {order['id']} cho {order['symbol']}")
            except Exception as e:
                logger.error(f"Lỗi hủy lệnh {order['id']}: {e}")
        
        msg = f"✅ <b>ĐÃ HỦY TẤT CẢ LỆNH CHỜ</b>\n\n<b>Số lệnh đã hủy:</b> {cancelled_count}\n<b>Vị thế:</b> Giữ nguyên\n<b>Thời gian:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        telegram_factory.send_tele(msg, cst.chat_id, True, True)
        logger.info(f"✅ Đã hủy {cancelled_count} lệnh chờ")
        
    except Exception as e:
        logger.error(f"❌ Lỗi khi thực hiện XÓA CHỜ: {e}")
        msg = f"🚨 <b>LỖI XÓA CHỜ</b>\n\n<b>Lỗi:</b> {str(e)}"
        telegram_factory.send_tele(msg, cst.chat_id, True, True)

  elif state_value == "XÓA VỊ THẾ":
    logger.info("🔄 Thực hiện lệnh XÓA VỊ THẾ - Đóng tất cả positions, giữ lệnh chờ")
    
    try:
        positions = exchange.fetch_positions()
        closed_count = 0
        
        for position in positions:
            if float(position['info']['positionAmt']) != 0:
                symbol = position['symbol']
                amount = float(position['info']['positionAmt'])
                
                try:
                    if amount > 0:
                        order = exchange.create_market_sell_order(symbol, amount)
                        logger.info(f"Đã đóng vị thế LONG: {symbol}")
                    elif amount < 0:
                        order = exchange.create_market_buy_order(symbol, abs(amount))
                        logger.info(f"Đã đóng vị thế SHORT: {symbol}")
                    closed_count += 1
                except Exception as e:
                    logger.error(f"Lỗi đóng vị thế {symbol}: {e}")
        
        msg = f"✅ <b>ĐÃ ĐÓNG TẤT CẢ VỊ THẾ</b>\n\n<b>Số vị thế đã đóng:</b> {closed_count}\n<b>Lệnh chờ:</b> Giữ nguyên\n<b>Thời gian:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        telegram_factory.send_tele(msg, cst.chat_id, True, True)
        logger.info(f"✅ Đã đóng {closed_count} vị thế")
        
    except Exception as e:
        logger.error(f"❌ Lỗi khi thực hiện XÓA VỊ THẾ: {e}")
        msg = f"🚨 <b>LỖI XÓA VỊ THẾ</b>\n\n<b>Lỗi:</b> {str(e)}"
        telegram_factory.send_tele(msg, cst.chat_id, True, True)

  elif state_value == STATE_CHO:
    print("💤 Trạng thái CHỜ - Không làm gì...", flush=True)
    logger.info("Trạng thái CHỜ - Không làm gì...")
  
  # ⚠️ Kiểm tra điều kiện đặt lệnh: E2 và D2 không được đều rỗng
  elif e2_total is None and d2_default is None:
    print("⏭️  Bỏ qua scan - E2 và D2 đều rỗng", flush=True)
    logger.warning("Bỏ qua scan - Không có cấu hình vốn hợp lệ")
  
  else:
    # Bố cục sheet: KHỐI TRÊN = LONG, KHỐI DƯỚI = SHORT
    #   (nhãn "Top 50 tăng giá" ở A3 trên sheet chỉ là mô tả nguồn dữ liệu,
    #    KHÔNG quyết định chiều lệnh — chiều lệnh do B2 quyết định)
    if state_value == STATE_LONG:
      start_row, end_row, type = 4, 53, "BUY"      # khối TRÊN
    elif state_value == STATE_SHORT:
      start_row, end_row, type = 55, 104, "SHORT"  # khối DƯỚI
    else:
      print(f"⏭️  Trạng thái '{state_value}' không phải LONG/SHORT → bỏ qua", flush=True)
      return

    # PHA A chỉ dùng leg đọc từ tab "ĐẶT LỆNH"; leg SL/TP đọc tab "Chờ và khớp" (pha B)
    DL_LEGS = [l for l in LEGS if l.get('source', 'dat_lenh') == 'dat_lenh']
    if not DL_LEGS:
      print("⏭️  Không có leg nào đọc tab 'ĐẶT LỆNH' → bỏ qua pha vào lệnh", flush=True)
      logger.info("Không có leg nguồn dat_lenh → bỏ qua pha A")
      return

    entry_side = "sell" if type in ("SELL", "SHORT") else "buy"
    # Cần đọc algo orders nếu bất kỳ leg nào CÓ THỂ là trailing (cố định hoặc chọn theo dòng)
    need_algo = any(l.get('type') == 'trailing' or l.get('type_col') is not None for l in DL_LEGS)

    don_bay = gg_sheet_factory.get_dat_lenh(f"A{start_row}:Z{end_row}")
    print(f"🔍 Scan {state_value} hàng {start_row}-{end_row} | {len(DL_LEGS)} leg (tab ĐẶT LỆNH)", flush=True)
    logger.info(f"Scan {state_value} {start_row}-{end_row}, legs={[(l['idx'], l['type'], l['role']) for l in DL_LEGS]}")
    print(f"📊 Đã đọc {len(don_bay)} dòng từ sheet", flush=True)

    leverage_idx = 1   # Cột B
    capital_idx = 7    # Cột H

    row_count = 0
    for d in don_bay:
        row_count += 1
        print(f"📝 Dòng {row_count}/{len(don_bay)}", flush=True)
        sys.stdout.flush()
        try:
            # --- Symbol (cột A) ---
            if len(d) == 0 or not d[0] or not str(d[0]).strip():
                continue
            sym = str(d[0]).strip()

            # --- Leverage (cột B): 'N'/'0'/rỗng = tắt dòng ---
            if len(d) <= leverage_idx or not str(d[leverage_idx]).strip():
                continue
            lev_str = str(d[leverage_idx]).strip()
            if lev_str in ('N', '0') or not is_number(lev_str) or float(lev_str) <= 0:
                continue

            # --- Kiểm tra tradeable + chuẩn hóa symbol ---
            is_tradeable, err_msg, normalized = is_symbol_tradeable(sym)
            if not is_tradeable:
                print(f"⏭️  {sym} không giao dịch được: {err_msg}", flush=True)
                continue
            symbol = normalized

            # --- Safety: re-check B2, đổi trạng thái thì dừng ---
            current_state, check_time = get_current_state()
            if current_state != state_value:
                print(f"🛑 B2 đổi '{state_value}' -> '{current_state}', dừng scan (đã xử lý {row_count-1} dòng)", flush=True)
                logger.warning(f"[STATE CHANGED] {state_value} -> {current_state} tại dòng {row_count}")
                break

            # --- Fetch 1 lần: vị thế + toàn bộ lệnh đang mở (chống trùng) ---
            try:
                pos_amt = get_position_amt(symbol)
                snap, algo_ok = build_symbol_snapshot(symbol, need_algo)
            except Exception as e:
                print(f"⚠️  {symbol}: lỗi đọc vị thế/lệnh: {e} → bỏ qua dòng (an toàn)", flush=True)
                logger.error(f"{symbol}: lỗi snapshot: {e}", exc_info=True)
                continue

            has_pos = (pos_amt != 0)
            exit_side = "sell" if pos_amt > 0 else "buy"
            capital = compute_capital(d, capital_idx, d1_percent, d2_default, e2_total)

            # --- Giá hiện tại ---
            try:
                lastPrice = float(exchange.fetch_ticker(symbol)["last"])
            except Exception as e:
                print(f"⚠️  {symbol}: lỗi lấy giá hiện tại: {e}", flush=True)
                continue

            # --- Set leverage (chỉ khi chưa có vị thế và có leg entry) ---
            if not has_pos and any(l['role'] == 'entry' for l in DL_LEGS):
                try:
                    exchange.setLeverage(int(float(lev_str)), symbol)
                except Exception as e:
                    logger.warning(f"{symbol}: không set được leverage: {e}")

            # --- Lập kế hoạch các lệnh cần đặt (logic thuần trong plan_row, dễ test) ---
            def _rp(v):
                try:
                    return float(exchange.price_to_precision(symbol, v))
                except Exception:
                    return v
            def _ra(v):
                try:
                    return float(exchange.amount_to_precision(symbol, v))
                except Exception:
                    return v
            plans, skips = plan_row(DL_LEGS, d, pos_amt, snap, algo_ok, capital, lastPrice,
                                    entry_side, round_price=_rp, round_amount=_ra,
                                    allow_dca=ALLOW_DCA,
                                    allow_close_position=SL_CLOSE_POSITION)
            for leg_idx, reason in skips:
                logger.info(f"[{symbol}] leg{leg_idx} bỏ qua: {reason}")

            # --- Thực thi từng lệnh trong kế hoạch ---
            for p in plans:
                _place_order(symbol, p, tag="ENTRY")

        except Exception as e:
            print(f"❌ Lỗi xử lý dòng {row_count} (symbol: {sym if 'sym' in locals() else 'N/A'}): {e}", flush=True)
            logger.error(f"Lỗi khi xử lý dòng {row_count}: {e}", exc_info=True)
            import traceback
            traceback.print_exc()
            continue

    # Kiểm tra lại B2 sau khi scan xong
    final_state, final_time = get_current_state(force=True)
    print(f"✅ Hoàn thành scan {state_value} - Đã xử lý {row_count}/{len(don_bay)} dòng", flush=True)
    logger.info(f"[SCAN END] Hoàn thành scan {state_value} - {row_count}/{len(don_bay)} dòng")
    if final_state != state_value:
        print(f"⚠️ LƯU Ý: B2 đã thay đổi trong quá trình scan: '{state_value}' -> '{final_state}'", flush=True)
        logger.warning(f"[STATE CHANGED DURING SCAN] B2: '{state_value}' -> '{final_state}'")
    else:
        logger.info(f"[B2 STABLE] Trạng thái B2 không đổi: {state_value}")

def do_it():
    """
    Điều phối 2 pha mỗi vòng quét:
      PHA A — Lệnh VÀO: quét tab "ĐẶT LỆNH (100 MÃ)" theo trạng thái B2 (LONG/SHORT),
              đồng thời xử lý các lệnh điều khiển STOP / XÓA CHỜ / XÓA VỊ THẾ / CHỜ.
      PHA B — SL/TP:    quét tab "Chờ và khớp" (vị thế thực tế đang mở).
              Bỏ qua khi B2 đang STOP/XÓA (lúc đó hệ thống đang dọn dẹp).
    """
    state_value, _ = get_current_state(force=True)

    # PHA A
    _do_entry_phase()

    # PHA B — chỉ chạy ở trạng thái vận hành bình thường
    if state_value in (STATE_LONG, STATE_SHORT, STATE_CHO):
        cvk_legs = [l for l in LEGS if l.get('source') == 'cho_va_khop']
        if cvk_legs:
            try:
                scan_cho_va_khop_legs(cvk_legs)
            except Exception as e:
                print(f"❌ Lỗi pha SL/TP (Chờ và khớp): {e}", flush=True)
                logger.error(f"Lỗi pha SL/TP: {e}", exc_info=True)
    else:
        logger.info(f"[SL/TP] Bỏ qua pha Chờ và khớp (B2={state_value})")


def printf(name, data):
    """Lưu thông tin order vào file"""
    try:
        print(data, flush=True)
        pathDir = str(Path().absolute()).replace("\\", "/")
        
        # Tìm order ID từ nhiều nguồn có thể (theo thứ tự ưu tiên)
        order_id = None
        
        # Ưu tiên 1: data['id'] (CCXT standard)
        if 'id' in data:
            order_id = str(data['id'])
        
        # Ưu tiên 2: data['info']['algoId'] (Binance algo orders)
        elif 'info' in data and isinstance(data['info'], dict):
            if 'algoId' in data['info']:
                order_id = str(data['info']['algoId'])
            elif 'orderId' in data['info']:
                order_id = str(data['info']['orderId'])
            elif 'id' in data['info']:
                order_id = str(data['info']['id'])
            elif 'order_id' in data['info']:
                order_id = str(data['info']['order_id'])
        
        # Nếu không tìm thấy order ID, dùng timestamp
        if not order_id:
            order_id = datetime.now().strftime("%Y%m%d_%H%M%S")
            logger.warning(f"Không tìm thấy order ID trong response cho {name}, dùng timestamp: {order_id}")
        
        filename = str(cst.account_dir("order") / str(name) / (str(order_id) + ".txt"))  # [MULTI-ACC]
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        # Ghi file với UTF-8 encoding
        with open(filename, "w", encoding='utf-8') as f:
            f.write(str(data))
            
    except Exception as e:
        logger.error(f"Lỗi trong printf() cho {name}: {e}", exc_info=True)
        print(f"⚠️ Lỗi khi lưu order file cho {name}: {e}", flush=True)    


if __name__ == "__main__":
    print(f"🚀 Khởi động bot - Chạy mỗi {cst.delay_vao_lenh} giây", flush=True)
    logger.info(f"Khởi động bot - Chạy mỗi {cst.delay_vao_lenh} giây")

    # ✅ Khởi tạo Google Sheets API trước khi bắt đầu
    print("🔄 Đang khởi tạo Google Sheets API...", flush=True)
    try:
        gg_sheet_factory.init_sheet_api()
        print("✅ Google Sheets API đã sẵn sàng", flush=True)
    except Exception as e:
        print(f"⚠️ Lỗi khởi tạo Google Sheets API: {e}", flush=True)
        logger.error(f"Lỗi khởi tạo Google Sheets API: {e}", exc_info=True)

    # ✅ Load order cache từ file (chống lặp đơn qua restart)
    _load_order_cache()

    # ✅ Load cấu hình các leg từ config.ini (đọc 1 lần lúc khởi động - đổi config phải restart)
    LEGS = load_legs()
    if LEGS:
        print(f"🧩 Đã nạp {len(LEGS)} leg:", flush=True)
        for l in LEGS:
            kind = f"type_col={l['type_col']}" if l['type_col'] is not None else f"type={l['type']}"
            col_txt = f"col={l['col']}" + (f",aux={l['aux']}" if l['aux'] is not None else "") + (f",pct={l['pct_col']}" if l['pct_col'] is not None else "")
            print(f"   • leg{l['idx']}: {kind} / {l['role']} ({col_txt})", flush=True)
        logger.info(f"Đã nạp legs: {LEGS}")
    else:
        print("⚠️ Chưa cấu hình leg nào trong config.ini (multi_leg_count / legN_*)! Bot sẽ không đặt lệnh.", flush=True)
        logger.warning("Không có leg nào được cấu hình")

    # ✅ Khởi động Telegram Command Bot (chỉ khi run_tele_command = true; mặc định false nếu chưa cấu hình)
    if getattr(cst, 'run_tele_command', False):
        try:
            import tele_command
            tele_command.start_tele_command_thread()
            print("✅ Telegram command bot đã khởi động", flush=True)
            logger.info("Telegram command bot đã khởi động")
        except Exception as e:
            print(f"⚠️ Lỗi khởi động Telegram command bot: {e}", flush=True)
            logger.error(f"Lỗi khởi động tele_command: {e}", exc_info=True)
    else:
        print("⏭️ Telegram command bot tắt (run_tele_command = false)", flush=True)
        logger.info("Telegram command bot không chạy (run_tele_command = false)")

    while True:
        try:
            resync_exchange_time(exchange)  # [Fix1] chống clock drift -> hết -1021
            do_it()
            print(f"⏳ Chờ {cst.delay_vao_lenh} giây trước lần scan tiếp theo...", flush=True)
            sys.stdout.flush()  # Đảm bảo flush trước khi sleep

        except Exception as e:
            if '-1021' in str(e) or 'recvWindow' in str(e):
                resync_exchange_time(exchange, min_interval=0)  # [Fix4] ép resync ccxt ngay
            print(f"❌ Tổng Lỗi: {e}", flush=True)
            logger.error(f"Tổng lỗi: {e}", exc_info=True)
            import traceback
            traceback.print_exc()
            print(f"⏳ Chờ {cst.delay_vao_lenh} giây trước khi thử lại...", flush=True)
            sys.stdout.flush()

        time.sleep(cst.delay_vao_lenh)