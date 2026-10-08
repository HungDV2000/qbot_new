import giu_cua_so  # PHẢI nạp ĐẦU TIÊN: dừng/lỗi thì giữ cửa sổ Windows để đọc thông báo
import ccxt
import cst
import config_watcher
import cot_nguoi_dung
import gg_sheet_factory
import logging
import telegram_factory
import time
from datetime import datetime
import os
from googleapiclient.errors import HttpError
from binance_futures_direct import (
    fetch_algo_orders_for_symbol,
    futures_signed_request,
    normalize_algo_orders_response,
    resync_exchange_time,
)
from phan_loai_lenh import la_lenh_dong, mo_ta as mo_ta_lenh, phan_loai

file_name = os.path.basename(os.path.abspath(__file__))  
# Tiến trình con của điều phối dùng CHUNG cửa sổ với cha → đổi tiêu đề là cửa sổ cha
# mang tên tài khoản con mở sau cùng (khách tưởng cửa sổ chỉ chạy 1 tài khoản).
if os.environ.get('QBOT_SUPERVISED', '') != '1':
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
        # Chỉ nạp mã Futures USDⓈ-M. ccxt 4.5 mặc định nạp cả Spot + gọi API Margin
        # (/sapi/v1/margin/allPairs) → key CHỈ bật Futures bị -2015, load_markets hỏng,
        # mọi mã bị coi là 'không tồn tại' → bot âm thầm không đặt lệnh.
        'fetchMarkets': {'types': ['linear']},
        'fetchMargins': False,
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
        loai = []
        for o in active_algo_orders:
            loai.append(phan_loai(o, la_algo=True))
            logger.info(f"   [{symbol}] algo: {mo_ta_lenh(o, True)}")
        for o in orders:
            loai.append(phan_loai(o))
            logger.info(f"   [{symbol}] lệnh: {mo_ta_lenh(o)}")
        return 'SL' in loai, 'TP' in loai, len(active_algo_orders) + len(orders)
    except Exception as e:
        logger.error(f"Lỗi khi check SL/TP cho {symbol}: {e}", exc_info=True)
        return False, False, len(orders)


class LoiLayDuLieu(Exception):
    """Lấy dữ liệu Binance KHÔNG ĐỦ → vòng này KHÔNG ghi sheet.

    Trước đây lỗi mạng/429 bị nuốt và trả danh sách rỗng → bot ghi một bảng THIẾU
    (mọi vị thế 'biến mất') → J–P của khách bị xoá, vòng sau điền số gợi ý đè lên."""


# Mã bot không xử lý được trong vòng hiện tại → giữ nguyên A–I cũ của nó trên sheet
_ma_loi_vong = set()


def _ghi_nho_ma_loi(ma_tho):
    ma = str(ma_tho or '').replace(':USDT', '').replace('/', '').strip().upper()
    if not ma:
        return False
    _ma_loi_vong.add(ma.replace('USDT', '/USDT') if ma.endswith('USDT') else ma)
    return True


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
    so_loi = 0
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
                so_loi += 1
                continue

        print(f"✅ Đã kiểm tra {checked_count} symbols (bỏ qua {delivery_count} delivery futures)", flush=True)
        print(f"✅ Tổng entry algo orders (fallback): {len(all_entry_algo)}", flush=True)
        logger.info(f"Fallback loop: {checked_count} symbols checked, {len(all_entry_algo)} algo orders found")

    except Exception as e:
        print(f"❌ Lỗi khi lấy entry algo orders (fallback): {e}", flush=True)
        logger.error(f"Lỗi get_all_entry_algo_orders fallback: {e}", exc_info=True)
        raise LoiLayDuLieu(f"không lấy được lệnh điều kiện (algo): {e}")
    if so_loi:
        raise LoiLayDuLieu(f"lấy lệnh điều kiện lỗi ở {so_loi} mã")

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
        raise LoiLayDuLieu(f"không lấy được lệnh thường (dò vị thế ĐÓNG): {e}")

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
    algo_orders = get_all_open_algo_orders_batch()
    if algo_orders is None:
        raise LoiLayDuLieu("không lấy được lệnh điều kiện (dò vị thế ĐÓNG)")
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
    except LoiLayDuLieu:
        raise
    except Exception as e:
        logger.error(f"Lỗi khi lấy reduce_only orders: {e}", exc_info=True)
        raise LoiLayDuLieu(f"dò vị thế ĐÓNG lỗi: {e}")

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


# ── Báo Telegram khi bot KHÔNG ghi được sheet (bảng đứng yên, khách không biết) ──
MA_LOI_KEY = ('-1022', '-2014', '-2015', 'Signature for this request', 'API-key format',
              'Invalid API-key')
VONG_BO_GHI_TRUOC_KHI_BAO = 3       # lỗi tạm (mạng, 429) thường tự hết sau 1–2 vòng
NHAC_LAI_GIAY = 3600
_bo_ghi = {"so_vong": 0, "bao_luc": 0.0, "da_bao": False}


def _gui_tele(msg):
    try:
        telegram_factory.send_tele(msg, cst.chat_id, True, True)
    except Exception as e:
        logger.error(f"Lỗi gửi Telegram: {e}")


def la_loi_key(loi):
    return any(m in str(loi) for m in MA_LOI_KEY)


def bao_bo_ghi(loi, bay_gio=None):
    """Gọi mỗi vòng BỎ GHI. Key sai → báo ngay; lỗi khác → báo khi bỏ ≥ 3 vòng liền.
    Nhắc lại tối đa 1 giờ/lần. Trả True nếu vừa gửi tin."""
    bay_gio = time.time() if bay_gio is None else bay_gio
    _bo_ghi["so_vong"] += 1
    key_sai = la_loi_key(loi)
    if not key_sai and _bo_ghi["so_vong"] < VONG_BO_GHI_TRUOC_KHI_BAO:
        return False
    if _bo_ghi["da_bao"] and bay_gio - _bo_ghi["bao_luc"] < NHAC_LAI_GIAY:
        return False
    if key_sai:
        msg = (f"🔑 <b>[{cst.account_name}] API KEY / SECRET KHÔNG HỢP LỆ</b>\n"
               f"Binance từ chối chữ ký ({str(loi)[:160]}).\n"
               f"Thường do <b>API Secret dán sai / không khớp API Key</b>, hoặc key đã bị xoá / "
               f"tạo lại trên Binance. Sửa dòng [{cst.account_name}] trên SHEET TỔNG — bot tự nhận.\n"
               f"Trong lúc này tab Chờ và khớp KHÔNG được cập nhật và bot không đặt được lệnh.")
    else:
        msg = (f"⚠️ <b>[{cst.account_name}] Chờ và khớp chưa cập nhật {_bo_ghi['so_vong']} vòng liền</b>\n"
               f"Lấy dữ liệu Binance lỗi: {str(loi)[:200]}\n"
               f"Bot giữ nguyên bảng cũ (không xoá dữ liệu của bạn), tự thử lại mỗi vòng.")
    _bo_ghi.update(bao_luc=bay_gio, da_bao=True)
    _gui_tele(msg)
    return True


def bao_da_ghi_lai():
    """Ghi sheet thành công: nếu trước đó đã báo lỗi thì báo đã hồi phục."""
    if _bo_ghi["da_bao"]:
        _gui_tele(f"✅ [{cst.account_name}] Chờ và khớp đã cập nhật lại bình thường "
                  f"(sau {_bo_ghi['so_vong']} vòng bỏ ghi).")
    _bo_ghi.update(so_vong=0, bao_luc=0.0, da_bao=False)


def doc_anh_cu_cho_va_khop():
    """
    Đọc A–P NGAY TRƯỚC khi ghi: cột A/B cho biết mã nào đang ở dòng nào (giữ chỗ),
    J–P cho biết dòng trống nào còn số người dùng (không cho mã mới vào).
    Dạng FORMULA: ô công thức hiện là công thức → phân biệt được với số gõ tay.
    Trả None nếu lỗi → vòng này KHÔNG ghi (không biết dòng nào của mã nào).
    """
    try:
        return gg_sheet_factory.get_cho_va_khop("A4:P1000", value_render_option="FORMULA") or []
    except Exception as e:
        logger.warning(f"Không đọc được A4:P1000 trước khi ghi: {e}")
        print(f"  ⚠️  Không đọc được bảng hiện tại — vòng này KHÔNG ghi: {e}", flush=True)
        return None


DONG_DAU_CVK = 4          # dòng dữ liệu đầu tiên — hàng 1–3 là tiêu đề của NGƯỜI DÙNG


def ke_hoach_ghi_cho_va_khop(rows_ai, anh_cu, timestamp_str, giu_ma=()):
    """
    MỘT lệnh ghi (values.batchUpdate): A2 (giờ quét) + A4:I (trạng thái).
    Bot KHÔNG ghi gì ngoài A–I: J–P là của người dùng, mỗi mã giữ nguyên dòng của nó
    (cot_nguoi_dung.xep_dong) nên J–P đứng yên vẫn đúng mã.
    Dòng thừa của bảng cũ → ô trống A–I trong cùng lệnh (không xoá trước).
    anh_cu None (đọc lỗi) → trả None: KHÔNG ghi.
    """
    if anh_cu is None:
        return None
    bang = cot_nguoi_dung.xep_dong(anh_cu, rows_ai, giu_ma) or [[""] * 9]
    cuoi = DONG_DAU_CVK + len(bang) - 1
    return [
        ("A2", [[timestamp_str]]),
        (f"A{DONG_DAU_CVK}:I{cuoi}", bang),
    ]


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
            raise LoiLayDuLieu(f"không lấy được lệnh chờ: {e}")

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

    except LoiLayDuLieu:
        raise
    except Exception as e:
        print(f"❌ Lỗi khi lấy orders từ Binance: {e}", flush=True)
        logger.error(f"Lỗi get_all_open_orders_with_single_order: {e}", exc_info=True)
        raise LoiLayDuLieu(f"lỗi xử lý lệnh chờ: {e}")

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
        raise LoiLayDuLieu(f"không lấy được vị thế: {e}")
    
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
            if not _ghi_nho_ma_loi(position.get('symbol')):
                raise LoiLayDuLieu(f"lỗi xử lý một vị thế không rõ mã: {e}")
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
    _ma_loi_vong.clear()

    def _append_row(row_ai, symbol_fmt):
        # row_ai: A=mã, B=side, C=chờ khớp, D=trạng thái, E=giá vào, F=đòn bẩy...
        tab_100_ma_2d_arr.append(row_ai)

    def _thu_thap():
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
                    _ghi_nho_ma_loi(cac_ma)   # dữ liệu tạm lỗi → giữ dòng cũ, không xoá
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
                print(f"    ❌ Lỗi xử lý position {position.get('symbol')}: {e}", flush=True)
                logger.error(f"Lỗi xử lý position {position.get('symbol')}: {e}", exc_info=True)
                if not _ghi_nho_ma_loi(position.get('symbol')):
                    raise LoiLayDuLieu(f"lỗi xử lý một vị thế không rõ mã: {e}")
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
                ma = order.get('symbol_clean') or (order.get('info') or {}).get('symbol') or order.get('symbol')
                if not _ghi_nho_ma_loi(ma):
                    raise LoiLayDuLieu(f"lỗi xử lý một lệnh chờ không rõ mã: {e}")
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
                if not _ghi_nho_ma_loi(closed.get('symbol')):
                    raise LoiLayDuLieu(f"lỗi tạo dòng ĐÓNG không rõ mã: {e}")
        return closed_list

    try:
        closed_list = _thu_thap()
    except LoiLayDuLieu as e:
        # Thiếu dữ liệu → ghi là ghi một bảng THIẾU → J–P mất chỗ dựa. Bỏ cả vòng.
        print(f"\n⛔ Lấy dữ liệu Binance KHÔNG ĐỦ ({e}) — vòng này KHÔNG ghi sheet, "
              f"giữ nguyên bảng cũ. Thử lại vòng sau.", flush=True)
        logger.error(f"Bỏ ghi vòng này — dữ liệu Binance không đủ: {e}")
        if la_loi_key(e):
            print(f"🔑 Lỗi KEY: API Secret sai / không khớp API Key của [{cst.account_name}] — "
                  f"sửa trên SHEET TỔNG.", flush=True)
        bao_bo_ghi(e)
        return

    # BƯỚC 5: Cập nhật lên Google Sheet
    print(f"\n📤 BƯỚC 5: Cập nhật lên Google Sheet...", flush=True)
    print(f"  Tổng dòng dữ liệu: {len(tab_100_ma_2d_arr)} (bao gồm {len(closed_list)} dòng ĐÓNG)", flush=True)
    logger.info(f"Tổng dòng dữ liệu: {len(tab_100_ma_2d_arr)} (ĐÓNG: {len(closed_list)})")
    
    try:
        # Chụp A–P TRƯỚC khi ghi: mã nào đang ở dòng nào → giữ nguyên dòng đó
        anh_cu = doc_anh_cu_cho_va_khop()

        timestamp_str = current_time.strftime("%Y-%m-%d %H:%M:%S")
        # CHỈ A2 + A4:I trong MỘT lệnh. Bot không ghi J–P / Q nữa: J–P là của người
        # dùng; SL/TP mặc định khi N/O/P trống do hd_order_multi tự tính trong bộ nhớ.
        ke_hoach = ke_hoach_ghi_cho_va_khop(tab_100_ma_2d_arr, anh_cu, timestamp_str,
                                            giu_ma=_ma_loi_vong)
        if ke_hoach is None:
            return
        if _ma_loi_vong:
            print(f"  ⚠️  Giữ nguyên dòng cũ của mã lỗi vòng này: {sorted(_ma_loi_vong)}", flush=True)
        vung = ke_hoach[1][0]
        print(f"  ✍️  Ghi A2 ({timestamp_str}) + {vung} vào sheet {gg_sheet_factory.spreadsheetId} "
              f"· tab '{gg_sheet_factory.tab_cho_va_khop}' (1 lệnh, KHÔNG đụng J–P)", flush=True)
        gg_sheet_factory.batch_update_values(gg_sheet_factory.tab_cho_va_khop, ke_hoach)
        bao_da_ghi_lai()

        print(f"✅ Hoàn thành! Đã cập nhật {len(tab_100_ma_2d_arr)} mã (chỉ A–I)", flush=True)
        logger.info(f"✅ Hoàn thành cập nhật sheet {gg_sheet_factory.spreadsheetId} "
                    f"tab '{gg_sheet_factory.tab_cho_va_khop}': {len(tab_100_ma_2d_arr)} mã, vùng {vung}")
        
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
    _t0_vong = config_watcher.bat_dau_vong()
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
    
    config_watcher.ngu_theo_nhip(_t0_vong, cst.delay_cho_va_khop, 'delay_cho_va_khop')

print("👋 Bot đã dừng", flush=True)
logger.info("Bot đã dừng")
