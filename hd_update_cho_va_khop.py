import giu_cua_so  # PHẢI nạp ĐẦU TIÊN: dừng/lỗi thì giữ cửa sổ Windows để đọc thông báo
import ccxt
import cst
import config_watcher
import cot_nguoi_dung
import gg_sheet_factory
import logging
from datetime import datetime
import os
from googleapiclient.errors import HttpError
from binance_futures_direct import (
    fetch_algo_orders_for_symbol,
    futures_signed_request,
    normalize_algo_orders_response,
    resync_exchange_time,
)
from binance_symbol_row import fetch_all_tickers_24h, get_sheet_col_c_price
from phan_loai_lenh import la_lenh_dong, phan_loai

file_name = os.path.basename(os.path.abspath(__file__))  
os.system(f"title {file_name} - {cst.key_name}")

# Tạo thư mục logs/ nếu chưa có
logs_dir = cst.account_dir('logs')  # [MULTI-ACC] tách theo tài khoản
logs_dir.mkdir(exist_ok=True)

# Tạo tên file log với timestamp: cho_va_khop_dd_mm_yyyy_H_M_S.txt
log_timestamp = datetime.now().strftime('%d_%m_%Y_%H_%M_%S')
log_filename_base = f'cho_va_khop_{log_timestamp}'

# Logging cải thiện với file trong logs/
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S',
    encoding='utf-8'
)
logger = logging.getLogger(__name__)

# File handler cho error log với timestamp (định dạng .txt)
error_log_path = logs_dir / f'{log_filename_base}_error.txt'
error_handler = logging.FileHandler(error_log_path, encoding='utf-8')
error_handler.setLevel(logging.ERROR)
error_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
logger.addHandler(error_handler)

# File handler cho info log với timestamp (định dạng .txt)
info_log_path = logs_dir / f'{log_filename_base}_info.txt'
info_handler = logging.FileHandler(info_log_path, encoding='utf-8')
info_handler.setLevel(logging.INFO)
info_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S'))
logger.addHandler(info_handler)

print(f"📝 Log files: {error_log_path.name} & {info_log_path.name}", flush=True)

exchange_id = 'binance'
exchange_class = getattr(ccxt, exchange_id)
exchange = exchange_class({
    'enableRateLimit': True,  
    'apiKey': cst.key_binance,
    'secret': cst.secret_binance,
    'options': {
        'defaultType': 'future',
        'warnOnFetchOpenOrdersWithoutSymbol': False,  # Suppress warning
        'fetchCurrencies': False,          # [A2] tránh gọi /sapi getall (signed) khi load_markets
        'adjustForTimeDifference': True,   # [A2] tự đồng bộ clock -> hết lỗi -1021
        'recvWindow': 60000,               # [A2+Fix2] nới cửa sổ timestamp lên max 60s
    }
})
exchange.setSandboxMode(False)

logger.info("✅ Khởi tạo Binance exchange thành công")

# Load markets để exchange biết các symbols
try:
    exchange.load_markets(True)  # Force reload
    logger.info("✅ Đã load markets thành công")
except Exception as e:
    logger.warning(f"⚠️ Lỗi load markets: {e}")


def get_algo_orders_for_symbol(symbol):
    """Lấy algo orders (open + 24h). HTTP 400 symbol không có algo → []."""
    try:
        result = fetch_algo_orders_for_symbol(symbol, history_hours=24)
        return result if result is not None else []
    except Exception as e:
        logger.error(f"Lỗi khi lấy algo orders cho {symbol}: {e}", exc_info=True)
        return []


def get_all_open_algo_orders_batch():
    """
    [Bug B FIX] Lấy TẤT CẢ algo orders đang active (NEW) trong 1 API call duy nhất.
    Dùng /fapi/v1/openAlgoOrders (không cần symbol) thay vì loop ~500 symbols.
    Returns: list orders đã được thêm symbol_ccxt, symbol_clean
    """
    try:
        response = futures_signed_request('GET', '/fapi/v1/openAlgoOrders', max_retries=3)
        orders_raw = normalize_algo_orders_response(response, 'openAlgoOrders')
        if orders_raw is None:
            return None

        result = []
        for order in orders_raw:
            sym_clean = order.get('symbol', '')
            # Bỏ qua delivery futures (có '-', ví dụ: BTCUSDT-260626)
            if '-' in sym_clean:
                continue
            # Convert HOMEUSDT → HOME/USDT:USDT
            if sym_clean.endswith('USDT') and '/' not in sym_clean:
                sym_ccxt = sym_clean[:-4] + '/USDT:USDT'
            else:
                sym_ccxt = sym_clean
            order['symbol_ccxt'] = sym_ccxt
            order['symbol_clean'] = sym_clean
            result.append(order)

        print(f"✅ Tổng open algo orders (batch 1 call): {len(result)}", flush=True)
        logger.info(f"Tổng open algo orders (batch): {len(result)}")
        return result

    except Exception as e:
        logger.error(f"Lỗi get_all_open_algo_orders_batch: {e}", exc_info=True)
        return None  # None để caller biết API lỗi


def get_position_leverage_map():
    """
    Lấy leverage thực tế theo symbol từ Binance position risk endpoint.

    Returns:
        dict[str, int] ví dụ {"BTCUSDT": 20, "ETHUSDT": 10}
    """
    leverage_map = {}
    try:
        response = futures_signed_request('GET', '/fapi/v2/positionRisk')
        if response is None:
            logger.warning("Không lấy được /fapi/v2/positionRisk để map leverage")
            return leverage_map

        rows = response if isinstance(response, list) else response.get('data', [])
        for item in rows:
            if not isinstance(item, dict):
                continue
            sym = str(item.get('symbol', '')).strip().upper()
            if not sym or '-' in sym:
                continue
            raw = item.get('leverage', item.get('initialLeverage'))
            if raw in (None, "", 0, "0"):
                continue
            try:
                lev = int(float(str(raw).strip()))
                if lev >= 1:
                    leverage_map[sym] = lev
            except (ValueError, TypeError):
                continue

        logger.info(f"Đã map leverage từ positionRisk cho {len(leverage_map)} symbols")
        if leverage_map:
            preview_items = sorted(leverage_map.items())[:20]
            preview_text = ", ".join([f"{k}:{v}x" for k, v in preview_items])
            logger.info(f"[LEVERAGE MAP PREVIEW] {preview_text}")
        return leverage_map
    except Exception as e:
        logger.warning(f"Lỗi lấy leverage map từ positionRisk: {e}")
        return leverage_map


def check_sl_tp_orders(symbol, orders):
    """
    Có SL / có TP / tổng số lệnh của 1 mã — quét cả algo lẫn lệnh thường.

    Nhận diện theo phan_loai_lenh, khớp cách hd_order_multi đặt lệnh:
    SL = STOP_MARKET closePosition, TP = LIMIT reduceOnly (hoặc trailing).
    Bản cũ chỉ coi TRAILING/TAKE_PROFIT là TP → cột "Có TP" luôn N.

    Returns: (has_sl, has_tp, order_count)
    """
    try:
        algo_orders = get_algo_orders_for_symbol(symbol)
        # [Bug C FIX] Bắt cả TRIGGERED (TP đã kích hoạt nhưng chưa fill)
        active_algo_orders = [
            o for o in algo_orders
            if str(o.get('algoStatus', '')).upper() in ('NEW', 'TRIGGERED')
        ]
        loai = ([phan_loai(o, la_algo=True) for o in active_algo_orders]
                + [phan_loai(o) for o in orders])
        return 'SL' in loai, 'TP' in loai, len(active_algo_orders) + len(orders)
    except Exception as e:
        logger.error(f"Lỗi khi check SL/TP cho {symbol}: {e}", exc_info=True)
        return False, False, len(orders)


def get_all_entry_algo_orders():
    """
    [Bug B FIX] Lấy TẤT CẢ algo orders đang active (NEW).

    Ưu tiên: /fapi/v1/openAlgoOrders (1 API call).
    Fallback: Loop từng symbol nếu batch endpoint không hỗ trợ.
    """
    # Thử batch endpoint trước (1 call, nhanh, không tốn rate limit)
    batch_result = get_all_open_algo_orders_batch()
    if batch_result is not None:
        # Thành công — log chi tiết để theo dõi
        for algo in batch_result:
            print(f"  📌 Entry algo: {algo.get('symbol_clean')}, Type={algo.get('algoType')}, AlgoId={algo.get('algoId')}", flush=True)
        return batch_result

    # Fallback: batch endpoint lỗi → loop từng symbol (phương án cũ)
    logger.warning("[FALLBACK] /fapi/v1/openAlgoOrders thất bại, fallback sang loop từng symbol")
    print("⚠️ Batch algo endpoint lỗi, chuyển sang loop từng symbol...", flush=True)

    all_entry_algo = []
    try:
        symbols = list(exchange.markets.keys())
        delivery_count = 0
        checked_count = 0

        for sym in symbols:
            try:
                if ':USDT' not in sym:
                    continue
                if '-' in sym:
                    delivery_count += 1
                    continue

                checked_count += 1
                algo_orders = get_algo_orders_for_symbol(sym)
                new_orders = [o for o in algo_orders if o.get('algoStatus', '').upper() == 'NEW']

                for algo in new_orders:
                    algo['symbol_ccxt'] = sym
                    algo['symbol_clean'] = sym.replace('/', '').replace(':USDT', '')
                    all_entry_algo.append(algo)
                    print(f"  📌 Entry algo: {algo['symbol_clean']}, Type={algo.get('algoType')}, AlgoId={algo.get('algoId')}", flush=True)

            except Exception as e:
                logger.warning(f"Lỗi khi lấy algo orders cho {sym}: {e}")
                continue

        print(f"✅ Đã kiểm tra {checked_count} symbols (bỏ qua {delivery_count} delivery futures)", flush=True)
        print(f"✅ Tổng entry algo orders (fallback): {len(all_entry_algo)}", flush=True)
        logger.info(f"Fallback loop: {checked_count} symbols checked, {len(all_entry_algo)} algo orders found")

    except Exception as e:
        print(f"❌ Lỗi khi lấy entry algo orders (fallback): {e}", flush=True)
        logger.error(f"Lỗi get_all_entry_algo_orders fallback: {e}", exc_info=True)

    return all_entry_algo


def get_all_reduce_only_orders_by_symbol():
    """
    [TASK 2] Lấy tất cả reduce_only orders (SL/TP) đang active theo symbol.
    Dùng để phát hiện "vị thế đã đóng" — symbol còn SL/TP treo nhưng không có position.

    Returns: dict {symbol_clean: {'open': [...], 'algo': [...], 'has_sl': bool, 'has_tp': bool, 'count': int, 'side': 'LONG'/'SHORT'/None}}
    """
    result = {}

    # 1) Open orders có reduceOnly=True
    try:
        all_open_orders = exchange.fetch_open_orders()
    except Exception as e:
        logger.warning(f"Lỗi fetch_open_orders trong reduce_only scan: {e}")
        all_open_orders = []

    for order in all_open_orders:
        info = order.get('info', {}) or {}
        if not la_lenh_dong(order):
            continue
        sym_clean = order.get('symbol', '').replace('/', '').replace(':USDT', '')
        if not sym_clean:
            continue
        if sym_clean not in result:
            result[sym_clean] = {'open': [], 'algo': [], 'has_sl': False, 'has_tp': False, 'count': 0, 'side': None}
        result[sym_clean]['open'].append(order)
        # Đoán loại + side ngược (nếu SL SELL reduceOnly → position là LONG)
        loai = phan_loai(order)
        if loai == 'SL':
            result[sym_clean]['has_sl'] = True
        elif loai == 'TP':
            result[sym_clean]['has_tp'] = True
        if result[sym_clean]['side'] is None:
            s = str(order.get('side', info.get('side', ''))).upper()
            if s == 'SELL':
                result[sym_clean]['side'] = 'LONG'
            elif s == 'BUY':
                result[sym_clean]['side'] = 'SHORT'

    # 2) Algo orders reduceOnly + NEW/TRIGGERED
    algo_orders = get_all_open_algo_orders_batch() or []
    for algo in algo_orders:
        info = algo.get('info', {}) or {}
        if not la_lenh_dong(algo):
            continue
        status = str(algo.get('algoStatus', '')).upper()
        if status not in ('NEW', 'TRIGGERED'):
            continue
        sym_clean = algo.get('symbol_clean', algo.get('symbol', '')).replace('/', '').replace(':USDT', '')
        if not sym_clean:
            continue
        if sym_clean not in result:
            result[sym_clean] = {'open': [], 'algo': [], 'has_sl': False, 'has_tp': False, 'count': 0, 'side': None}
        result[sym_clean]['algo'].append(algo)
        loai = phan_loai(algo, la_algo=True)
        if loai == 'SL':
            result[sym_clean]['has_sl'] = True
        elif loai == 'TP':
            result[sym_clean]['has_tp'] = True
        if result[sym_clean]['side'] is None:
            s = str(algo.get('side', info.get('side', ''))).upper()
            if s == 'SELL':
                result[sym_clean]['side'] = 'LONG'
            elif s == 'BUY':
                result[sym_clean]['side'] = 'SHORT'

    # Đếm tổng count
    for sym, data in result.items():
        data['count'] = len(data['open']) + len(data['algo'])

    return result


def detect_closed_positions_with_residual_orders(opened_positions_symbols):
    """
    [TASK 2] Phát hiện các vị thế đã ĐÓNG nhưng còn lệnh reduce_only treo.

    Args:
        opened_positions_symbols: set của symbol_clean (HOMEUSDT) đang có position mở

    Returns: list of dict {symbol, side, has_sl, has_tp, order_count}
    """
    try:
        all_reduce_only = get_all_reduce_only_orders_by_symbol()
    except Exception as e:
        logger.error(f"Lỗi khi lấy reduce_only orders: {e}", exc_info=True)
        return []

    closed_list = []
    for sym_clean, data in all_reduce_only.items():
        if sym_clean in opened_positions_symbols:
            continue  # Còn position → không phải "đóng"
        # Đây là trường hợp còn SL/TP treo nhưng position = 0 → ĐÓNG
        closed_list.append({
            'symbol': sym_clean,
            'side': data.get('side') or '',
            'has_sl': data['has_sl'],
            'has_tp': data['has_tp'],
            'order_count': data['count'],
        })
        logger.info(f"[CLOSED] {sym_clean}: còn {data['count']} reduce_only orders (SL={data['has_sl']}, TP={data['has_tp']}) → Trạng thái ĐÓNG")

    if closed_list:
        print(f"🔴 Phát hiện {len(closed_list)} vị thế đã ĐÓNG nhưng còn lệnh treo: {[c['symbol'] for c in closed_list]}", flush=True)
    else:
        print(f"✅ Không có vị thế ĐÓNG còn lệnh treo", flush=True)

    return closed_list


def _round_price_for_sheet(price, entry_price):
    """Làm tròn giá hiển thị trên sheet theo scale của entry price (khớp hiển thị UI)."""
    if price is None or entry_price is None or entry_price <= 0:
        return price
    # Quy tắc hiển thị: <1 → 6 decimals; <100 → 4; <10000 → 2; else 0
    if entry_price < 1:
        return round(price, 6)
    if entry_price < 100:
        return round(price, 4)
    if entry_price < 10000:
        return round(price, 2)
    return round(price, 1)


def compute_default_sl_tp_prices(side, entry_price):
    """
    [TASK 1] Tính default 3 giá SL + 3 giá TP từ entry price và rates trong config.

    Args:
        side: "LONG" / "SHORT"
        entry_price: float > 0

    Returns:
        (sl_list, tp_list) — mỗi list 3 phần tử (float).
        Nếu entry_price <= 0 hoặc side không hợp lệ → trả về ([None]*3, [None]*3).
    """
    if not entry_price or entry_price <= 0:
        return [None, None, None], [None, None, None]

    is_long = (str(side).upper() == 'LONG')
    sl_rates = [cst.default_sl_rate_layer_1, cst.default_sl_rate_layer_2, cst.default_sl_rate_layer_3]
    tp_rates = [cst.default_tp_rate_layer_1, cst.default_tp_rate_layer_2, cst.default_tp_rate_layer_3]

    sl_prices = []
    tp_prices = []
    for r in sl_rates:
        if is_long:
            p = entry_price * (1 - r / 100.0)
        else:
            p = entry_price * (1 + r / 100.0)
        sl_prices.append(_round_price_for_sheet(p, entry_price) if p > 0 else None)

    for r in tp_rates:
        if is_long:
            p = entry_price * (1 + r / 100.0)
        else:
            p = entry_price * (1 - r / 100.0)
        tp_prices.append(_round_price_for_sheet(p, entry_price) if p > 0 else None)

    return sl_prices, tp_prices


def goi_y_sltp_cho_dong(row_ai):
    """
    Từ 1 dòng A–I, dựng gợi ý [giá SL, giá TP, cho-phép-đặt] cho cột N/O/P.

    Chỉ gợi ý khi dòng đó ĐANG MỞ VỊ THẾ (cột D = 'Y') và có giá vào hợp lệ.
    Dòng đã ĐÓNG hoặc chưa khớp thì trả về rỗng — không bịa số.

    Dùng mức lớp 1 (`default_sl_rate_layer_1` / `default_tp_rate_layer_1`).
    Sheet hiện chỉ có MỘT cột SL (N) và MỘT cột TP (O), không có chỗ cho 3 lớp.
    """
    try:
        side = str(row_ai[1]).strip() if len(row_ai) > 1 else ""
        status_d = str(row_ai[3]).strip().upper() if len(row_ai) > 3 else ""
        entry = float(row_ai[4]) if len(row_ai) > 4 and row_ai[4] else 0
    except (ValueError, TypeError, IndexError):
        return ["", "", ""]

    if status_d != "Y" or entry <= 0:
        return ["", "", ""]

    sl_list, tp_list = compute_default_sl_tp_prices(side, entry)
    sl = sl_list[0] if sl_list and sl_list[0] else ""
    tp = tp_list[0] if tp_list and tp_list[0] else ""
    return [sl, tp, cst.default_allow_order]


def doc_anh_cu_cho_va_khop():
    """
    Đọc A–P NGAY TRƯỚC khi xoá A–I, để biết J–P đang thuộc mã nào.
    Đọc dạng FORMULA: số giữ nguyên độ chính xác (không bị làm tròn theo định
    dạng hiển thị) và ô công thức giữ nguyên công thức khi ghi lại.
    Trả None nếu lỗi → bước sau để nguyên J–P, không dời/không điền.
    """
    try:
        return gg_sheet_factory.get_cho_va_khop("A4:P1000", value_render_option="FORMULA") or []
    except Exception as e:
        logger.warning(f"Không đọc được A4:P1000 trước khi ghi: {e}")
        print(f"  ⚠️  Không đọc được A–P — lượt này để nguyên J–P: {e}", flush=True)
        return None


def ghi_goi_y_sltp(tab_sltp, rows_ai, anh_cu):
    """
    Ghi lại cột người dùng J–P sau khi A–I đổi:
      • J–M (tick xoá lệnh) và N/O/P (giá SL/TP, cho phép) DỜI THEO MÃ khi thứ
        tự dòng đổi — nếu không, tick/giá của BTC sẽ rơi sang mã khác.
      • N/O/P còn trống thì điền gợi ý — KHÔNG đè số người dùng đã sửa.

    Vì sao cần điền gợi ý: hd_order_multi chỉ đặt SL/TP khi cột D='Y' VÀ cột
    P='Y' VÀ N/O có giá. Trước đây KHÔNG BOT NÀO điền N/O/P nên chúng luôn
    trống → bot bỏ qua mọi dòng → vị thế mở mà không có cắt lỗ.

    (compute_default_sl_tp_prices đã có sẵn trong file này từ lâu nhưng
     không ai gọi — đây là chỗ nối nó vào luồng chạy.)
    """
    if anh_cu is None:
        return          # không đọc được ảnh cũ → không dám dời/ghi đè
    dien = bool(cst.fill_default_cho_va_khop)
    if not dien:
        print("  ⏭️  fill_default_cho_va_khop = false → không điền gợi ý N/O/P", flush=True)

    khoi, co_doi, so_doi_cho = cot_nguoi_dung.can_chinh(anh_cu, rows_ai, tab_sltp, dien)
    if not co_doi:
        print("  ✔️  Cột J–P không cần đổi", flush=True)
        return

    gg_sheet_factory.update_multi(gg_sheet_factory.tab_cho_va_khop, 2, khoi, "J")
    print(f"  ✍️  Cột J–P: ghi {len(khoi)} dòng, dời theo mã {so_doi_cho} dòng "
          f"(số người dùng đã sửa được giữ nguyên)", flush=True)
    logger.info(f"J–P: ghi {len(khoi)} dòng, dời theo mã {so_doi_cho}")


def build_cho_va_khop_row(
    symbol_formatted, side, status_d, entry_price, leverage, has_sl, has_tp, order_count
):
    """
    Dựng row 9 cột A–I cho sheet "Chờ và khớp".

    Bot ghi A–I (trạng thái tự động) và Q (giá hiện tại). Cột J–P do người dùng
    điền — không ghi đè.

    A=Symbol, B=Side, C=Chờ khớp, D=Trạng thái (Y/N/ĐÓNG),
    E=Giá vào, F=Đòn bẩy, G=Có SL, H=Có TP, I=Số orders, Q=Giá hiện tại.
    """
    lenh_ls = "Y" if has_sl else "N"
    lenh_tp = "Y" if has_tp else "N"
    if status_d == "Y":
        cho_khop = "N"
    elif status_d == "N":
        cho_khop = "Y"
    else:
        cho_khop = "N"

    return (
        symbol_formatted,
        side,
        cho_khop,
        status_d,
        entry_price,
        leverage,
        lenh_ls,
        lenh_tp,
        order_count,
    )


def get_all_open_orders_with_single_order():
    """
    Lấy tất cả orders có đúng 1 order pending cho mỗi symbol
    (Sử dụng để track lệnh entry đang chờ khớp)

    ✅ CẬP NHẬT: Lấy CẢ open orders thường VÀ algo orders (entry orders)
    """
    res = []

    try:
        # ✅ BƯỚC 1: Lấy open orders thông thường (LIMIT, MARKET, etc.)
        print("🔍 Đang lấy open orders từ Binance...", flush=True)
        try:
            all_open_orders = exchange.fetch_open_orders()
            print(f"✅ Tổng open orders: {len(all_open_orders)}", flush=True)
            logger.info(f"Tổng open orders: {len(all_open_orders)}")
        except Exception as e:
            print(f"⚠️ Lỗi khi lấy open orders: {e}", flush=True)
            logger.warning(f"Lỗi fetch_open_orders: {e}")
            all_open_orders = []

        # ✅ BƯỚC 2: Lấy TẤT CẢ algo orders từ Binance API trực tiếp
        print("🔍 Đang lấy algo orders từ Binance API...", flush=True)
        all_algo_orders = get_all_entry_algo_orders()
        print(f"✅ Tổng algo orders (NEW): {len(all_algo_orders)}", flush=True)

        # ✅ BƯỚC 3: Nhóm orders theo symbol và lọc symbols có đúng 1 order
        orders_by_symbol = {}

        # Thêm open orders vào dict
        for order in all_open_orders:
            # Convert HOME/USDT:USDT → HOMEUSDT
            sym = order['symbol'].replace('/', '').replace(':USDT', '')
            if sym not in orders_by_symbol:
                orders_by_symbol[sym] = {'open': [], 'algo': []}
            orders_by_symbol[sym]['open'].append(order)

        # Thêm algo orders vào dict
        for algo in all_algo_orders:
            sym = algo.get('symbol_clean', algo.get('symbol', '')).replace('/', '').replace(':USDT', '')
            if sym not in orders_by_symbol:
                orders_by_symbol[sym] = {'open': [], 'algo': []}
            orders_by_symbol[sym]['algo'].append(algo)

        # ✅ BƯỚC 4: Lọc symbols có đúng 1 order (entry orders)
        for sym, orders_data in orders_by_symbol.items():
            open_count = len(orders_data['open'])
            algo_count = len(orders_data['algo'])
            total_count = open_count + algo_count

            if total_count == 1:
                # Lấy order duy nhất
                if orders_data['open']:
                    res.append(orders_data['open'][0])
                    print(f"  📌 {sym}: 1 open order (chờ khớp)", flush=True)
                    order = orders_data['open'][0]
                    print(f"     ID: {order['id']}, Type: {order.get('type', 'N/A')}, Amount: {order['amount']}, Price: {order.get('price', 'N/A')}", flush=True)
                elif orders_data['algo']:
                    res.append(orders_data['algo'][0])
                    print(f"  📌 {sym}: 1 algo order (chờ khớp)", flush=True)
                    algo = orders_data['algo'][0]
                    print(f"     AlgoId: {algo.get('algoId', 'N/A')}, Type: {algo.get('algoType', 'N/A')}, Status: {algo.get('algoStatus', 'N/A')}", flush=True)
            elif total_count > 1:
                print(f"  ⏭️  {sym}: {total_count} orders ({open_count} open + {algo_count} algo) - bỏ qua (nhiều hơn 1)", flush=True)

        print(f"✅ Tìm thấy {len(res)} symbols có đúng 1 order (lệnh entry)", flush=True)
        logger.info(f"Symbols có đúng 1 order: {len(res)}")

    except Exception as e:
        print(f"❌ Lỗi khi lấy orders từ Binance: {e}", flush=True)
        logger.error(f"Lỗi get_all_open_orders_with_single_order: {e}", exc_info=True)

    return res


def resolve_leverage_from_ccxt_position(symbol_label, position):
    """
    Đọc đòn bẩy từ object position của CCXT (Binance USDT-M).

    CCXT đôi khi để `leverage` trống ở top-level; Binance thường trả trong `info`:
    `leverage`, `initialLeverage` (chuỗi hoặc số).
    """
    candidates = []

    def _add(val):
        if val is None:
            return
        if isinstance(val, str) and not str(val).strip():
            return
        if isinstance(val, (int, float)) and float(val) == 0:
            return
        candidates.append(val)

    _add(position.get('leverage'))
    _add(position.get('initialLeverage'))

    info = position.get('info')
    if isinstance(info, dict):
        _add(info.get('leverage'))
        _add(info.get('initialLeverage'))

    for raw in candidates:
        try:
            val = float(str(raw).strip().replace(',', ''))
            if val >= 1:
                return int(val)
        except (ValueError, TypeError):
            continue

    logger.warning(
        f"{symbol_label}: Không parse được đòn bẩy từ CCXT (fallback 1x). "
        f"info keys (mẫu): {list(info.keys())[:12] if isinstance(info, dict) else 'N/A'}"
    )
    return 1


def get_opened_possition():
    """
    Lấy tất cả positions đang mở (position_amt != 0)
    SỬ DỤNG fetch_positions() thay vì fetch_balance() để có entryPrice!
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
    leverage_map = get_position_leverage_map()
    
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
            
            leverage = leverage_map.get(symbol)
            leverage_source = "positionRisk"
            if leverage is None:
                leverage = resolve_leverage_from_ccxt_position(symbol, position)
                leverage_source = "ccxt_position"

            # Thêm position vào danh sách
            # Lưu cả symbol gốc (CCXT format) và symbol format (để tương thích)
            position['symbol'] = symbol  # Format "HOMEUSDT" để tương thích với code hiện tại
            position['symbol_ccxt'] = symbol_ccxt  # Format "HOME/USDT:USDT" để dùng cho API calls
            position['positionAmt'] = str(position_amt)  # Thêm positionAmt để tương thích
            position['leverage'] = leverage  # Bắt buộc: do_it() đọc key này (trước đây không gán → hay thành 1)
            position['leverage_source'] = leverage_source

            opened_possition.append(position)
            print(f"📊 {symbol}: Pos={position_amt}, Entry={entry_price}, PnL={unrealized_pnl:.2f}, Lev={leverage}x", flush=True)
            logger.info(
                f"Position: {symbol}, Amt={position_amt}, Entry={entry_price}, "
                f"PnL={unrealized_pnl}, Lev={leverage}, source={leverage_source}"
            )
            
            # Debug: Log nếu entry price = 0 (không nên xảy ra với fetch_positions())
            if entry_price == 0.0:
                logger.error(f"❌ {symbol}: Entry price = 0! (Không nên xảy ra với fetch_positions())")
                logger.error(f"   Raw entryPrice: {entry_price_raw} (type: {type(entry_price_raw)})")
                logger.error(f"   FULL RAW POSITION DATA: {position}")
                print(f"    ⚠️  Entry price = 0! Xem log chi tiết.", flush=True)
                    
        except Exception as e:
            logger.error(f"Lỗi khi xử lý position {position.get('symbol', 'N/A')}: {e}", exc_info=True)
            continue
    
    return opened_possition

def do_it():
    current_time = datetime.now()
    print(f"\n{'='*80}", flush=True)
    print(f"🔄 {current_time.strftime('%Y-%m-%d %H:%M:%S')} - Bắt đầu scan 'Chờ và khớp'", flush=True)
    print(f"{'='*80}\n", flush=True)
    logger.info(f"{'='*80}")
    logger.info(f"Bắt đầu scan 'Chờ và khớp'")

    tab_100_ma_2d_arr = []
    tab_q_prices: list = []
    tab_sltp: list = []     # gợi ý [SL, TP, cho-phép] cho cột N/O/P

    print("📡 Lấy giá hiện tại toàn sàn (REST ticker 24h)...", flush=True)
    try:
        tickers_24h = fetch_all_tickers_24h()
        print(f"✅ Đã cache {len(tickers_24h)} ticker futures", flush=True)
    except Exception as e:
        logger.warning(f"Không lấy được ticker 24h: {e}")
        tickers_24h = {}
        print(f"⚠️ Không lấy được ticker 24h — cột Q sẽ trống: {e}", flush=True)

    def _append_row(row_ai, symbol_fmt):
        tab_100_ma_2d_arr.append(row_ai)
        tab_q_prices.append([get_sheet_col_c_price(tickers_24h, symbol_fmt)])
        # row_ai: A=mã, B=side, C=chờ khớp, D=trạng thái, E=giá vào, F=đòn bẩy...
        tab_sltp.append(goi_y_sltp_cho_dong(row_ai))

    # BƯỚC 1: Lấy positions đang mở
    print("📊 BƯỚC 1: Lấy positions đang mở từ Binance...", flush=True)
    res = get_opened_possition()
    print(f"✅ Tổng positions: {len(res)}\n", flush=True)
    logger.info(f"Tổng positions đang mở: {len(res)}")
    
    # BƯỚC 2: Xử lý từng position
    print("🔧 BƯỚC 2: Xử lý từng position...", flush=True)
    for idx, position in enumerate(res, 1):
        try:
            position_amt = float(position['positionAmt'])
            cac_ma = position['symbol']
            
            print(f"\n  [{idx}/{len(res)}] Xử lý {cac_ma}...", flush=True)
            
            # Debug: Log raw position data để kiểm tra
            logger.debug(f"Raw position data for {cac_ma}: {position}")
            
            # Format symbol: HOMEUSDT → HOME/USDT
            symbol_formatted = cac_ma.replace("USDT", "/USDT")
            
            # Xác định LONG/SHORT
            vi_the_short_long = 'LONG' if position_amt > 0 else 'SHORT' if position_amt < 0 else 'Flat'
            
            # Đã khớp (có position)
            cho_khop = "N"  # Không còn chờ
            da_khop_mo_vi_the = "Y"  # Đã mở vị thế
            
            # Entry price và leverage - Parse an toàn
            entry_price_raw = position.get('entryPrice')
            if entry_price_raw is not None and entry_price_raw != '' and entry_price_raw != 0:
                try:
                    gia_vao = float(entry_price_raw)
                except (ValueError, TypeError):
                    gia_vao = 0.0
                    logger.warning(f"{cac_ma}: Lỗi parse entryPrice: {entry_price_raw}")
            else:
                gia_vao = 0.0
                logger.warning(f"{cac_ma}: entryPrice rỗng hoặc = 0, raw: {entry_price_raw}")
            
            leverage_raw = position.get('leverage')
            if leverage_raw is not None and leverage_raw != '' and leverage_raw != 0:
                try:
                    don_bay = int(float(leverage_raw))
                except (ValueError, TypeError):
                    don_bay = 1
            else:
                don_bay = 1
            
            # Lấy orders cho symbol này - dùng symbol_ccxt nếu có (format CCXT chuẩn)
            symbol_for_orders = position.get('symbol_ccxt', cac_ma)
            # Nếu không có symbol_ccxt, convert từ "HOMEUSDT" → "HOME/USDT:USDT"
            if symbol_for_orders == cac_ma and 'symbol_ccxt' not in position:
                symbol_for_orders = cac_ma.replace("USDT", "/USDT:USDT")
            
            try:
                orders = exchange.fetch_open_orders(symbol=symbol_for_orders)
            except Exception as e:
                logger.warning(f"Lỗi khi lấy open orders cho {symbol_for_orders}: {e}")
                orders = []
            
            # ✅ LOGIC MỚI: Phân tích chính xác SL/TP (quét cả algo orders)
            # Truyền symbol để quét algo orders
            has_sl, has_tp, order_count = check_sl_tp_orders(symbol_for_orders, orders)
            
            lenh_ls = "Y" if has_sl else "N"  # Cột G
            lenh_tp = "Y" if has_tp else "N"  # Cột H
            lenh_nguoc = order_count  # Cột I (số lượng orders)
            
            print(f"    ✓ Side: {vi_the_short_long}, Entry: {gia_vao}, Lev: {don_bay}x", flush=True)
            print(f"    ✓ Orders: {order_count} (SL: {lenh_ls}, TP: {lenh_tp})", flush=True)
            
            # ⚠️ VALIDATION: SKIP NẾU ENTRY PRICE = 0
            if gia_vao == 0.0 or gia_vao is None:
                print(f"    ❌ BỎ QUA: Entry price = 0 hoặc None! (Raw: {entry_price_raw})", flush=True)
                logger.error(f"❌ {symbol_formatted}: Entry price không hợp lệ (0 hoặc None). Raw: {entry_price_raw}")
                logger.error(f"   Position data: {position}")
                logger.error(f"   FULL RAW POSITION DATA: {position}")
                logger.error(f"   Position keys: {list(position.keys())}")
                # Log từng field quan trọng để debug
                for key in ['entryPrice', 'positionAmt', 'unrealizedProfit', 'leverage', 'markPrice', 'liquidationPrice', 'notional', 'isolated', 'marginType']:
                    if key in position:
                        logger.error(f"   {key}: {position[key]} (type: {type(position[key])})")
                continue  # Bỏ qua position này
            
            logger.info(f"{symbol_formatted}: {vi_the_short_long}, Entry={gia_vao}, Lev={don_bay}, Orders={order_count}, SL={lenh_ls}, TP={lenh_tp}")
            
            row = build_cho_va_khop_row(
                symbol_formatted=symbol_formatted,
                side=vi_the_short_long,
                status_d="Y",  # Position đang mở
                entry_price=gia_vao,
                leverage=don_bay,
                has_sl=has_sl,
                has_tp=has_tp,
                order_count=order_count,
            )
            _append_row(row, symbol_formatted)
            
        except Exception as e:
            print(f"    ❌ Lỗi xử lý position {cac_ma}: {e}", flush=True)
            logger.error(f"Lỗi xử lý position {cac_ma}: {e}", exc_info=True)
            continue

    # BƯỚC 3: Lấy orders chờ khớp (entry orders)
    print("\n📝 BƯỚC 3: Lấy orders chờ khớp (entry orders)...", flush=True)
    res1 = get_all_open_orders_with_single_order()
    print(f"✅ Tổng orders chờ khớp: {len(res1)}\n", flush=True)
    logger.info(f"Tổng orders chờ khớp: {len(res1)}")

    # BƯỚC 4: Xử lý từng order chờ khớp
    print("🔧 BƯỚC 4: Xử lý orders chờ khớp...", flush=True)
    for idx, order in enumerate(res1, 1):
        try:
            print(f"\n  [{idx}/{len(res1)}] Xử lý order...", flush=True)

            # ✅ Check xem là algo order hay open order
            is_algo_order = 'algoId' in order or 'algoType' in order

            if is_algo_order:
                # === XỬ LÝ ALGO ORDER ===
                algo_id = order.get('algoId', 'N/A')
                algo_type = order.get('algoType', 'N/A')
                algo_status = order.get('algoStatus', 'N/A')

                print(f"    📌 Algo Order: AlgoId={algo_id}, Type={algo_type}, Status={algo_status}", flush=True)
                logger.info(f"Xử lý algo order: AlgoId={algo_id}, Type={algo_type}, Status={algo_status}")

                # Symbol từ order (Binance raw format: 1000CATUSDT)
                order_symbol = order.get('symbol', order.get('symbol_clean', order.get('symbol_ccxt', '')))
                # Chuẩn hóa về format HOMEUSDT để so sánh với position['symbol']
                order_symbol_clean = order_symbol.replace('/', '').replace(':USDT', '')

                # Skip nếu symbol đã có position (tránh dup dữ liệu — giống check ở open orders)
                if next((p for p in res if p.get('symbol', '') == order_symbol_clean), None):
                    print(f"    ⏭️  Bỏ qua algo order (đã có position cho {order_symbol_clean})", flush=True)
                    logger.info(f"Bỏ qua algo order {algo_id} của {order_symbol_clean}: đã có position")
                    continue
                # Convert HOMEUSDT → HOME/USDT
                symbol_formatted = order_symbol.replace("USDT", "/USDT") if order_symbol else ""

                # [Bug A FIX] Raw Binance algo API trả về 'side' ở top-level, không qua 'info'
                algo_info = order.get('info', {})
                side = order.get('side', algo_info.get('side', 'UNKNOWN')).upper()
                vi_the_short_long = 'LONG' if side == "BUY" else 'SHORT'

                # Giá kích hoạt
                gia_vao = order.get('activatePrice', algo_info.get('activatePrice', 0))

                # Đang chờ khớp
                cho_khop = "Y"
                da_khop_mo_vi_the = "N"
                don_bay = "N"
                lenh_ls = "N"
                lenh_tp = "N"
                lenh_nguoc = 0

                print(f"    ✓ Symbol: {symbol_formatted}", flush=True)
                print(f"    ✓ Side: {vi_the_short_long}, Activation: {gia_vao}", flush=True)
                print(f"    ✓ Trạng thái: Chờ khớp (algo)", flush=True)

            else:
                # === XỬ LÝ OPEN ORDER THÔNG THƯỜNG ===
                print(f"  [{idx}/{len(res1)}] Xử lý order {order.get('id', 'N/A')}...", flush=True)

                order_symbol = order['info']['symbol']

                # Skip nếu symbol đã có position (tránh trùng lặp)
                if next((position for position in res if order_symbol == position['symbol']), None):
                    print(f"    ⏭️  Bỏ qua (đã có position)", flush=True)
                    continue

                print(f"    ✓ Symbol: {order['symbol']}, Type: {order.get('type', 'N/A')}", flush=True)

                # Format symbol
                cac_ma = order_symbol
                symbol_formatted = cac_ma.replace("USDT", "/USDT")

                # Xác định side từ order
                side = order['info']['side']
                vi_the_short_long = 'LONG' if side == "BUY" else 'SHORT'

                # Đang chờ khớp (chưa có position)
                cho_khop = "Y"
                da_khop_mo_vi_the = "N"

                # Price và leverage
                gia_vao = order['info'].get('price', 0)
                don_bay = "N"

                # Chưa có SL/TP (chưa vào lệnh)
                lenh_ls = "N"
                lenh_tp = "N"
                lenh_nguoc = 0

                print(f"    ✓ Side: {vi_the_short_long}, Price: {gia_vao}", flush=True)
                print(f"    ✓ Trạng thái: Chờ khớp", flush=True)

            logger.info(f"{symbol_formatted}: {vi_the_short_long}, Activation={gia_vao}, Status=Chờ khớp")
            
            row = build_cho_va_khop_row(
                symbol_formatted=symbol_formatted,
                side=vi_the_short_long,
                status_d="N",  # Chưa khớp
                entry_price=gia_vao,
                leverage=don_bay,
                has_sl=False,
                has_tp=False,
                order_count=lenh_nguoc,
            )
            _append_row(row, symbol_formatted)
            
        except Exception as e:
            print(f"    ❌ Lỗi xử lý order: {e}", flush=True)
            logger.error(f"Lỗi xử lý order {order.get('id', 'N/A')}: {e}", exc_info=True)
            continue

    # [TASK 2] BƯỚC 4.5: Phát hiện vị thế ĐÓNG còn lệnh ngược treo
    print(f"\n🔴 BƯỚC 4.5: Phát hiện vị thế ĐÓNG còn lệnh treo...", flush=True)
    opened_symbols_set = set(p.get('symbol', '') for p in res)
    closed_list = detect_closed_positions_with_residual_orders(opened_symbols_set)

    for closed in closed_list:
        try:
            sym_clean = closed['symbol']
            symbol_formatted = sym_clean.replace("USDT", "/USDT") if sym_clean.endswith("USDT") else sym_clean
            side_str = closed.get('side') or ""
            # Row ĐÓNG: entry=0 (user tick cột M để xóa lệnh ngược)
            row = build_cho_va_khop_row(
                symbol_formatted=symbol_formatted,
                side=side_str,
                status_d="ĐÓNG",
                entry_price=0,
                leverage="N",
                has_sl=closed['has_sl'],
                has_tp=closed['has_tp'],
                order_count=closed['order_count'],
            )
            _append_row(row, symbol_formatted)
            print(f"  📎 Thêm ĐÓNG: {symbol_formatted} (side={side_str}, orders={closed['order_count']})", flush=True)
        except Exception as e:
            logger.error(f"Lỗi tạo row ĐÓNG cho {closed.get('symbol')}: {e}", exc_info=True)

    # BƯỚC 5: Cập nhật lên Google Sheet
    print(f"\n📤 BƯỚC 5: Cập nhật lên Google Sheet...", flush=True)
    print(f"  Tổng dòng dữ liệu: {len(tab_100_ma_2d_arr)} (bao gồm {len(closed_list)} dòng ĐÓNG)", flush=True)
    logger.info(f"Tổng dòng dữ liệu: {len(tab_100_ma_2d_arr)} (ĐÓNG: {len(closed_list)})")
    
    try:
        # Chụp A–P TRƯỚC khi xoá: để J–P (của người dùng) dời theo đúng mã
        anh_cu = doc_anh_cu_cho_va_khop()

        # Clear A–I + Q; cột J–P (user) không xoá — chỉ dời theo mã ở bước cuối
        print("  🗑️  Xóa vùng A4:I1000 và Q4:Q1000 trước khi ghi...", flush=True)
        gg_sheet_factory.clear_multi(gg_sheet_factory.tab_cho_va_khop, 2, "a", end_row=1000, end_column="I")
        gg_sheet_factory.clear_multi(gg_sheet_factory.tab_cho_va_khop, 2, "Q", end_row=1000, end_column="Q")

        timestamp_str = current_time.strftime("%Y-%m-%d %H:%M:%S")
        print(f"  📅 Cập nhật timestamp vào A2: {timestamp_str}", flush=True)
        gg_sheet_factory.update_single_value(gg_sheet_factory.tab_cho_va_khop, "A2", timestamp_str)

        print("  ✍️  Ghi dữ liệu A–I...", flush=True)
        gg_sheet_factory.update_multi(gg_sheet_factory.tab_cho_va_khop, 2, tab_100_ma_2d_arr, "a")

        if tab_q_prices:
            print(f"  ✍️  Ghi cột Q (giá hiện tại) — {len(tab_q_prices)} dòng...", flush=True)
            gg_sheet_factory.update_multi(gg_sheet_factory.tab_cho_va_khop, 2, tab_q_prices, "Q")

        # Gợi ý SL/TP vào N/O/P — chỉ điền ô trống, không đè số người dùng sửa.
        # Không có bước này thì N/O/P luôn trống → hd_order_multi bỏ qua mọi
        # dòng → vị thế mở mà KHÔNG CÓ CẮT LỖ.
        ghi_goi_y_sltp(tab_sltp, tab_100_ma_2d_arr, anh_cu)

        print(f"✅ Hoàn thành! Đã cập nhật {len(tab_100_ma_2d_arr)} dòng (A–I + cột Q)", flush=True)
        logger.info(f"✅ Hoàn thành cập nhật sheet: {len(tab_100_ma_2d_arr)} dòng (A–I + Q)")
        
    except HttpError as e:
        # ✅ Xử lý đặc biệt cho lỗi 403 (Permission denied)
        if e.resp.status == 403:
            error_msg = f"❌ Lỗi 403 - Permission denied khi cập nhật sheet: {e}"
            print(error_msg, flush=True)
            logger.error(error_msg, exc_info=True)
            print("⚠️  Lưu ý: Token có thể đã hết hạn hoặc không có quyền truy cập sheet", flush=True)
            print("   Bot sẽ tự động thử refresh token ở lần scan tiếp theo", flush=True)
            logger.warning("Lỗi 403 - Bot sẽ thử lại ở lần scan tiếp theo sau khi refresh token")
        else:
            error_msg = f"❌ HttpError (status {e.resp.status}) khi cập nhật sheet: {e}"
            print(error_msg, flush=True)
            logger.error(error_msg, exc_info=True)
    except Exception as e:
        print(f"❌ Lỗi khi cập nhật sheet: {e}", flush=True)
        logger.error(f"Lỗi cập nhật sheet: {e}", exc_info=True)
    
    print(f"\n{'='*80}\n", flush=True)

print(f"🚀 Bot hd_update_cho_va_khop khởi động - Scan mỗi {cst.delay_cho_va_khop}s", flush=True)
logger.info(f"Bot khởi động - Scan interval: {cst.delay_cho_va_khop}s")
cst.bao_nhip('delay_cho_va_khop', cst.delay_cho_va_khop)

scan_count = 0

while True:
    try:
        resync_exchange_time(exchange)  # [Fix1] chống clock drift -> hết -1021
        scan_count += 1
        print(f"\n🔄 Scan lần {scan_count}", flush=True)
        logger.info(f"{'='*80}")
        logger.info(f"Scan lần {scan_count}")
        
        do_it()
        
        print(f"⏳ Chờ {cst.delay_cho_va_khop}s trước lần scan tiếp theo...\n", flush=True)
        
    except KeyboardInterrupt:
        print("\n⚠️  Nhận Ctrl+C - Dừng bot...", flush=True)
        logger.info("Bot dừng bởi user (Ctrl+C)")
        break
        
    except Exception as e:
        if '-1021' in str(e) or 'recvWindow' in str(e):
            resync_exchange_time(exchange, min_interval=0)  # [Fix4] ép resync ccxt ngay
        print(f"\n❌ Tổng Lỗi: {e}", flush=True)
        logger.error(f"Tổng lỗi: {e}", exc_info=True)
        import traceback
        traceback.print_exc()
        print(f"⏳ Chờ {cst.delay_cho_va_khop}s trước khi thử lại...\n", flush=True)
    
    config_watcher.ngu(cst.delay_cho_va_khop)   # nghỉ + dò cấu hình trên sheet tổng

print("👋 Bot đã dừng", flush=True)
logger.info("Bot đã dừng")
