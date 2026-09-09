# -*- coding: utf-8 -*-
"""Binance Futures REST — build one sheet row A→BF (shared by hd_update_all / hd_update_all_new)."""
from __future__ import annotations

import json
import logging
import math
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

BASE_FUTURES = "https://fapi.binance.com"
BASE_SPOT = "https://api.binance.com"

_EXCHANGE_FUT_CACHE: Optional[dict] = None
_EXCHANGE_SPOT_CACHE: Optional[dict] = None
_FUT_STATUS_MAP: Optional[Dict[str, str]] = None
_SPOT_STATUS_MAP: Optional[Dict[str, str]] = None
_FUT_STATUS_MAP_LOADED_AT: float = 0.0
_SPOT_STATUS_MAP_LOADED_AT: float = 0.0
_EXCHANGE_INFO_TTL_SEC: float = 6 * 3600  # Refresh mỗi 6 giờ

# 1h≥168 (biên độ 7 ngày); 1d≥400 (AD biên độ ngày 365d + R-S 30d)
_KLINE_LIMITS = (("1h", 168), ("4h", 120), ("1d", 400), ("1w", 20))


def _http_get(base: str, path: str, params: Optional[dict] = None, timeout: int = 12) -> Any:
    import urllib.error
    qs = urllib.parse.urlencode(params or {})
    url = f"{base}{path}" + (f"?{qs}" if qs else "")
    req = urllib.request.Request(url, headers={"User-Agent": "hd-update-all-new/1.0"})
    last_err: Optional[Exception] = None
    max_attempts = 3
    for attempt in range(max_attempts):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                time.sleep(0.05)  # 50ms gap giữa các request, tránh burst rate limit
                return result
        except urllib.error.HTTPError as e:
            last_err = e
            status = e.code
            if status == 429:
                # Rate limit — exponential backoff (5s, 10s, 20s)
                wait = 5 * (2 ** attempt)
                logger.warning(f"Binance 429 rate limit {url}: chờ {wait}s (lần {attempt + 1})")
                time.sleep(wait)
            elif status in (500, 502, 503, 504):
                # Server error tạm thời — backoff ngắn
                wait = 2 ** attempt
                logger.warning(f"Binance HTTP {status} {path}: chờ {wait}s (lần {attempt + 1})")
                time.sleep(wait)
            else:
                raise  # Lỗi client (400, 401, 404...) — không retry
        except Exception as e:
            last_err = e
            if attempt < max_attempts - 1:
                time.sleep(0.5 * (attempt + 1))
    raise last_err  # type: ignore[misc]


def preload_exchange_caches() -> None:
    """Tải exchangeInfo một lần trước vòng lặp 50 mã (tránh đơ ở mã đầu)."""
    _load_futures_exchange_info()
    _load_spot_exchange_info()
    print(
        f"✅ Cache exchangeInfo: Futures {len(_FUT_STATUS_MAP or {})} | "
        f"Spot {len(_SPOT_STATUS_MAP or {})} mã",
        flush=True,
    )


def _load_futures_exchange_info() -> None:
    global _EXCHANGE_FUT_CACHE, _FUT_STATUS_MAP, _FUT_STATUS_MAP_LOADED_AT
    now = time.time()
    if _FUT_STATUS_MAP is not None and (now - _FUT_STATUS_MAP_LOADED_AT) < _EXCHANGE_INFO_TTL_SEC:
        return
    _EXCHANGE_FUT_CACHE = _http_get(BASE_FUTURES, "/fapi/v1/exchangeInfo", timeout=25)
    _FUT_STATUS_MAP = {
        item["symbol"]: item.get("status", "UNKNOWN")
        for item in _EXCHANGE_FUT_CACHE.get("symbols", [])
        if item.get("symbol")
    }
    _FUT_STATUS_MAP_LOADED_AT = now
    logger.info(f"Đã refresh FUT exchangeInfo: {len(_FUT_STATUS_MAP)} symbol")


def _load_spot_exchange_info() -> None:
    global _EXCHANGE_SPOT_CACHE, _SPOT_STATUS_MAP, _SPOT_STATUS_MAP_LOADED_AT
    now = time.time()
    if _SPOT_STATUS_MAP is not None and (now - _SPOT_STATUS_MAP_LOADED_AT) < _EXCHANGE_INFO_TTL_SEC:
        return
    try:
        _EXCHANGE_SPOT_CACHE = _http_get(BASE_SPOT, "/api/v3/exchangeInfo", timeout=25)
        _SPOT_STATUS_MAP = {
            item["symbol"]: item.get("status", "UNKNOWN")
            for item in _EXCHANGE_SPOT_CACHE.get("symbols", [])
            if item.get("symbol")
        }
        _SPOT_STATUS_MAP_LOADED_AT = now
        logger.info(f"Đã refresh SPOT exchangeInfo: {len(_SPOT_STATUS_MAP)} symbol")
    except Exception as e:
        logger.warning(f"Không tải spot exchangeInfo: {e}")
        if _SPOT_STATUS_MAP is None:
            _SPOT_STATUS_MAP = {}


def normalize_symbol(raw: str) -> Tuple[str, str]:
    """
    Chuẩn hóa input → (symbol_binance, pair_display).
    VD: btc, BTC/USDT, BTC/USDT:USDT, BTCUSDT → (BTCUSDT, BTC/USDT)
    """
    s = (raw or "").strip().upper()
    if not s:
        raise ValueError("Symbol không được rỗng")
    s = s.replace(":USDT", "").replace("/", "").replace("-", "").replace("_", "")
    if not s.endswith("USDT"):
        s = f"{s}USDT"
    if not re.fullmatch(r"[A-Z0-9]{2,20}USDT", s):
        raise ValueError(f"Symbol không hợp lệ sau chuẩn hóa: {s}")
    base = s[:-4]
    return s, f"{base}/USDT"


def validate_futures_symbol(symbol_clean: str) -> str:
    """Kiểm tra symbol có trên Binance USDT-M; trả về status hoặc raise."""
    _load_futures_exchange_info()
    status = (_FUT_STATUS_MAP or {}).get(symbol_clean)
    if status is None:
        raise ValueError(f"{symbol_clean} không tồn tại trên Binance Futures USDT-M")
    return status


def get_spot_status(symbol_clean: str) -> str:
    _load_spot_exchange_info()
    if not _SPOT_STATUS_MAP:
        return "Không lấy được spot exchangeInfo"
    return _SPOT_STATUS_MAP.get(symbol_clean, "Không có spot")


def _fetch_klines_bundle(symbol_clean: str) -> Tuple[List[list], List[list], List[list], List[list]]:
    """4 khung thời gian song song — giảm ~3× thời gian chờ so với tuần tự."""
    out: Dict[str, List[list]] = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pool.submit(fetch_klines, symbol_clean, interval, limit): interval
            for interval, limit in _KLINE_LIMITS
        }
        for fut in as_completed(futures):
            interval = futures[fut]
            out[interval] = fut.result()
    return out["1h"], out["4h"], out["1d"], out["1w"]


def _fetch_metrics_bundle(
    symbol_clean: str, price: float
) -> Tuple[Tuple[Optional[float], Optional[float]], Tuple[Optional[float], Optional[float]]]:
    """OI + L/S 5m song song (bỏ thêm 2 request L/S 1h).

    [Fix A] Lỗi 1 nhánh (vd symbol đã delist → HTTP 400 openInterest) chỉ để TRỐNG
    cột đó, KHÔNG làm hỏng cả dòng và KHÔNG spam traceback. Các cột khác vẫn có data.
    """
    def _safe(name, fn):
        try:
            return fn()
        except Exception as e:
            logger.warning(f"[{symbol_clean}] metric {name} bỏ qua (để trống): {e}")
            return (None, None)

    with ThreadPoolExecutor(max_workers=2) as pool:
        f_oi = pool.submit(_safe, "OI", lambda: fetch_oi_usdt_and_delta(symbol_clean, price))
        f_ls = pool.submit(_safe, "L/S", lambda: fetch_ls_ratio(symbol_clean, "5m"))
        return f_oi.result(), f_ls.result()


def fetch_klines(symbol_clean: str, interval: str, limit: int) -> List[list]:
    data = _http_get(
        BASE_FUTURES,
        "/fapi/v1/klines",
        {"symbol": symbol_clean, "interval": interval, "limit": limit},
    )
    if not isinstance(data, list):
        raise RuntimeError(f"Klines {interval} trả về không hợp lệ")
    return data


def fetch_ticker_24h(symbol_clean: str) -> dict:
    data = _http_get(BASE_FUTURES, "/fapi/v1/ticker/24hr", {"symbol": symbol_clean})
    if not isinstance(data, dict):
        raise RuntimeError("ticker/24hr không hợp lệ")
    return data


def fetch_all_tickers_24h() -> dict:
    """
    GET /fapi/v1/ticker/24hr (toàn bộ) — lọc top tăng/giảm.
    Key giống CCXT: BTC/USDT:USDT → {last, percentage, quoteVolume}.
    """
    rows = _http_get(BASE_FUTURES, "/fapi/v1/ticker/24hr")
    if not isinstance(rows, list):
        raise RuntimeError("ticker/24hr all không hợp lệ")
    out: dict = {}
    for t in rows:
        sym = t.get("symbol", "")
        if not sym.endswith("USDT"):
            continue
        base = sym[:-4]
        key = f"{base}/USDT:USDT"
        try:
            out[key] = {
                "last": float(t["lastPrice"]),
                "percentage": float(t["priceChangePercent"]),
                "quoteVolume": float(t.get("quoteVolume", 0)),
            }
        except (KeyError, TypeError, ValueError):
            continue
    return out


def ticker_key_from_pair_display(pair_display: str) -> str:
    """HOME/USDT hoặc HOMEUSDT → HOME/USDT:USDT (key trong fetch_all_tickers_24h)."""
    try:
        _, pair = normalize_symbol(pair_display)
    except ValueError:
        p = str(pair_display or "").strip().upper().replace(":USDT", "")
        if p.endswith("/USDT"):
            pair = p
        elif p.endswith("USDT"):
            pair = f"{p[:-4]}/USDT"
        else:
            pair = f"{p}/USDT"
    if ":USDT" in pair:
        return pair
    return f"{pair}:USDT"


def get_sheet_col_c_price(tickers: dict, pair_display: str) -> Any:
    """
    Giá trị hiện thời — cột C sheet 100 mã (hd_update_all / build_symbol_data):
    last từ ticker 24h REST, round(..., 8). Fallback fetch_ticker_24h từng mã.
    """
    key = ticker_key_from_pair_display(pair_display)
    ti = tickers.get(key) or {}
    last = ti.get("last")
    if last is not None:
        try:
            px = float(last)
            if px > 0:
                return round(px, 8)
        except (TypeError, ValueError):
            pass
    try:
        symbol_clean = key.replace("/", "").replace(":USDT", "")
        t = fetch_ticker_24h(symbol_clean)
        px = float(t["lastPrice"])
        if px > 0:
            return round(px, 8)
    except Exception as e:
        logger.warning(f"get_sheet_col_c_price({pair_display}): {e}")
    return ""


def parse_ohlcv(rows: List[list]) -> dict:
    """CCXT/Binance kline: 0 time, 1 O, 2 H, 3 L, 4 C, 5 base vol, 7 quote vol."""
    o, h, l, c, bv, qv = [], [], [], [], [], []
    for row in rows:
        o.append(float(row[1]))
        h.append(float(row[2]))
        l.append(float(row[3]))
        c.append(float(row[4]))
        bv.append(float(row[5]))
        qv.append(float(row[7]) if len(row) > 7 else float(row[5]) * float(row[4]))
    return {"open": o, "high": h, "low": l, "close": c, "base_vol": bv, "quote_vol": qv}


def _mean(xs: List[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def bb_upper_lower(closes: List[float], period: int = 20, mult: float = 2.0) -> Tuple[Optional[float], Optional[float]]:
    if len(closes) < period:
        return None, None
    window = closes[-period:]
    ma = _mean(window)
    var = sum((x - ma) ** 2 for x in window) / period
    std = math.sqrt(var)
    return ma + mult * std, ma - mult * std


def rsi_series_sma(closes: List[float], period: int = 14) -> List[Optional[float]]:
    """Chuỗi RSI kiểu mẫu chatbot: SMA gain/loss rolling(period) trên từng cửa sổ."""
    n = len(closes)
    out: List[Optional[float]] = [None] * n
    if n < period + 1:
        return out
    for i in range(period, n):
        chunk = [closes[j] - closes[j - 1] for j in range(i - period + 1, i + 1)]
        gains = [max(0.0, x) for x in chunk]
        losses = [max(0.0, -x) for x in chunk]
        ag = _mean(gains)
        al = _mean(losses)
        out[i] = 100.0 if al == 0 else 100.0 - (100.0 / (1.0 + ag / al))
    return out


def rsi_sma_last(closes: List[float], period: int = 14) -> Optional[float]:
    series = rsi_series_sma(closes, period)
    for v in reversed(series):
        if v is not None:
            return float(v)
    return None


def _ewm_pandas(values: List[float], span: int) -> List[float]:
    """pandas.Series.ewm(span=span, adjust=False)"""
    if not values:
        return []
    alpha = 2.0 / (span + 1)
    out = [float(values[0])]
    for i in range(1, len(values)):
        out.append(float(values[i]) * alpha + out[-1] * (1.0 - alpha))
    return out


def compute_macd(closes: List[float], fast: int = 12, slow: int = 26, signal: int = 9):
    """MACD mẫu chatbot: ema12 - ema26, signal = ewm9(macd), adjust=False."""
    if len(closes) < slow + signal:
        return None, None, None
    ema_fast = _ewm_pandas(closes, fast)
    ema_slow = _ewm_pandas(closes, slow)
    macd_line = [ema_fast[i] - ema_slow[i] for i in range(len(closes))]
    sig_line = _ewm_pandas(macd_line, signal)
    m, s = macd_line[-1], sig_line[-1]
    return m, s, m - s


def compute_stoch_rsi(closes: List[float], rsi_period: int = 14, stoch_period: int = 14, k_smooth: int = 3, d_smooth: int = 3):
    """Stoch RSI mẫu chatbot: RSI SMA rolling → stoch → SMA k → SMA d."""
    rsi_arr = rsi_series_sma(closes, rsi_period)
    rsi_clean = [float(x) for x in rsi_arr if x is not None]
    if len(rsi_clean) < stoch_period + k_smooth + d_smooth - 2:
        return None, None
    raw_k: List[Optional[float]] = []
    for i in range(len(rsi_clean)):
        if i < stoch_period - 1:
            raw_k.append(None)
            continue
        window = rsi_clean[i - stoch_period + 1 : i + 1]
        w_min, w_max = min(window), max(window)
        raw_k.append(0.0 if w_max == w_min else (rsi_clean[i] - w_min) / (w_max - w_min) * 100.0)
    k_smoothed: List[Optional[float]] = []
    for i in range(len(raw_k)):
        if raw_k[i] is None or i < k_smooth - 1:
            k_smoothed.append(None)
        else:
            win = [raw_k[j] for j in range(i - k_smooth + 1, i + 1) if raw_k[j] is not None]
            k_smoothed.append(_mean(win) if len(win) == k_smooth else None)
    k_vals = [x for x in k_smoothed if x is not None]
    if len(k_vals) < d_smooth:
        return None, None
    k_now = k_vals[-1]
    d_now = _mean(k_vals[-d_smooth:])
    return k_now, d_now


def compute_stochastic(highs: List[float], lows: List[float], closes: List[float], k_period: int = 14, d_period: int = 3):
    n = min(len(highs), len(lows), len(closes))
    if n < k_period + d_period:
        return None, None
    k_series = []
    for i in range(k_period - 1, n):
        wh = highs[i - k_period + 1 : i + 1]
        wl = lows[i - k_period + 1 : i + 1]
        h_max, l_min = max(wh), min(wl)
        k_series.append(0.0 if h_max == l_min else (closes[i] - l_min) / (h_max - l_min) * 100)
    if len(k_series) < d_period:
        return None, None
    return k_series[-1], _mean(k_series[-d_period:])


def sma_last(values: List[float], period: int) -> Optional[float]:
    if len(values) < period:
        return None
    return _mean(values[-period:])


def max_body_pct_4h(rows: List[list], lookback: int) -> Tuple[Optional[float], Optional[float]]:
    if len(rows) < 2:
        return None, None
    subset = rows[-lookback:] if len(rows) >= lookback else rows
    pcts = []
    for row in subset:
        op, cl = float(row[1]), float(row[4])
        if op > 0:
            pcts.append((cl - op) / op * 100)
    if not pcts:
        return None, None
    return max(pcts), min(pcts)


def _amplitude_range_from_klines(rows: List[list]) -> Tuple[Optional[float], Optional[float]]:
    """
    Max biên độ % nến tăng / giảm trong slice (giống hd_update_all._amplitude_range_from_ohlcv_slice).
    amplitude = (high - low) / ref * 100; ref = min(O,C) nến tăng, max(O,C) nến giảm.
    """
    if not rows:
        return None, None
    max_inc: Optional[float] = None
    max_dec: Optional[float] = None
    for row in rows:
        o, h, l, c = float(row[1]), float(row[2]), float(row[3]), float(row[4])
        change = c - o
        if change > 0:
            ref = min(c, o)
            if ref <= 0:
                continue
            amp = (h - l) / ref * 100
            max_inc = amp if max_inc is None else max(max_inc, amp)
        elif change < 0:
            ref = max(c, o)
            if ref <= 0:
                continue
            amp = (h - l) / ref * 100
            max_dec = amp if max_dec is None else max(max_dec, amp)
    return (
        round(max_inc, 2) if max_inc is not None else None,
        round(max_dec, 2) if max_dec is not None else None,
    )


def _max_daily_volatility_from_klines(rows: List[list], lookback_days: int = 365) -> Tuple[float, str]:
    """AD-AE: biên độ ngày lớn nhất (H-L)/Open % và ngày tương ứng."""
    if not rows:
        return 0.0, "N/A"
    cutoff_ms = int(time.time() * 1000) - lookback_days * 24 * 60 * 60 * 1000
    subset = [r for r in rows if int(r[0]) >= cutoff_ms] or rows
    best_pct = 0.0
    best_ts = 0
    for row in subset:
        ts, o, h, l = int(row[0]), float(row[1]), float(row[2]), float(row[3])
        if o <= 0:
            continue
        vp = (h - l) / o * 100
        if vp >= best_pct:
            best_pct = vp
            best_ts = ts
    if best_ts == 0:
        return 0.0, "N/A"
    return round(best_pct, 2), datetime.fromtimestamp(best_ts / 1000).strftime("%Y-%m-%d")


def _bb_width_3d_and_now(closes_1d: List[float], period: int = 20, std_dev: float = 2.0) -> Tuple[Optional[float], Optional[float]]:
    """
    AF-AG: (BB width 3 phiên trước, width hiện tại) = (U-L)/Mid trên nến 1d đã đóng.
  population std (ddof=0) — khớp hd_update_all / TradingView.
    """
    closed = closes_1d[:-1] if closes_1d and len(closes_1d) > period + 3 else closes_1d
    if not closed or len(closed) < period + 3:
        return None, None
    widths: List[Optional[float]] = []
    for i in range(period - 1, len(closed)):
        window = closed[i - period + 1 : i + 1]
        ma = _mean(window)
        if ma == 0:
            widths.append(None)
            continue
        variance = sum((x - ma) ** 2 for x in window) / period
        std = math.sqrt(variance)
        upper = ma + std_dev * std
        lower = ma - std_dev * std
        widths.append((upper - lower) / ma)
    if len(widths) < 4:
        return None, None
    ago, cur = widths[-4], widths[-1]
    bw_3d = float(ago) if ago is not None and math.isfinite(ago) else None
    bw_now = float(cur) if cur is not None and math.isfinite(cur) else None
    return bw_3d, bw_now


def compute_score(price, ma7, ma25, ma99, macd_val, macd_sig, macd_hist, stoch_k, stoch_d, lsr_acc, lsr_pos, oi_delta):
    score = 0.0
    reasons = []
    if ma7 is not None and ma25 is not None and ma99 is not None:
        if ma7 > ma25 > ma99:
            score += 3
            reasons.append("MA7>25>99(+3)")
        elif ma7 < ma25 < ma99:
            score -= 3
            reasons.append("MA7<25<99(-3)")
    if price and ma25:
        if price > ma25:
            score += 1
            reasons.append("P>MA25(+1)")
        elif price < ma25:
            score -= 1
            reasons.append("P<MA25(-1)")
    if macd_val is not None and macd_sig is not None:
        if macd_val > macd_sig and (macd_hist or 0) > 0:
            score += 2
            reasons.append("MACD>Sig(+2)")
        elif macd_val < macd_sig and (macd_hist or 0) < 0:
            score -= 2
            reasons.append("MACD<Sig(-2)")
    if stoch_k is not None:
        if stoch_k < 20 and (stoch_d is None or stoch_k > stoch_d):
            score += 1.5
            reasons.append("StochRSI<20(+1.5)")
        elif stoch_k > 80 and (stoch_d is None or stoch_k < stoch_d):
            score -= 1.5
            reasons.append("StochRSI>80(-1.5)")
    if lsr_acc is not None and lsr_acc > 3:
        score -= 1
        reasons.append(f"LSR_acc={lsr_acc:.2f}(-1)")
    if lsr_pos is not None and lsr_pos > 2:
        score += 1.5
        reasons.append(f"LSR_pos={lsr_pos:.2f}(+1.5)")
    score = max(-10, min(10, round(score, 1)))
    if score >= 5:
        suggest = "LONG mạnh"
    elif score >= 2:
        suggest = "LONG nhẹ"
    elif score <= -5:
        suggest = "SHORT mạnh"
    elif score <= -2:
        suggest = "SHORT nhẹ"
    else:
        suggest = "Trung tính"
    return score, suggest, "; ".join(reasons)


def fetch_oi_usdt_and_delta(symbol_clean: str, price: float) -> Tuple[Optional[float], Optional[float]]:
    """OI USDT = openInterest×giá; Δ24h từ openInterestHist limit=24 (mẫu chatbot)."""
    oi_usdt = None
    oi_data = _http_get(BASE_FUTURES, "/fapi/v1/openInterest", {"symbol": symbol_clean})
    if oi_data and price:
        try:
            oi_usdt = float(oi_data["openInterest"]) * price
        except (KeyError, TypeError, ValueError):
            pass
    hist = _http_get(
        BASE_FUTURES,
        "/futures/data/openInterestHist",
        {"symbol": symbol_clean, "period": "1h", "limit": 24},
    )
    oi_delta = None
    if isinstance(hist, list) and len(hist) >= 2:
        try:
            oi_now = float(hist[-1]["sumOpenInterest"])
            oi_old = float(hist[0]["sumOpenInterest"])
            if oi_old > 0:
                oi_delta = (oi_now - oi_old) / oi_old * 100
        except (KeyError, TypeError, ValueError):
            pass
    return oi_usdt, oi_delta


def fetch_ls_ratio(symbol_clean: str, period: str = "5m") -> Tuple[Optional[float], Optional[float]]:
    acc = _http_get(
        BASE_FUTURES,
        "/futures/data/globalLongShortAccountRatio",
        {"symbol": symbol_clean, "period": period, "limit": 1},
    )
    pos = _http_get(
        BASE_FUTURES,
        "/futures/data/topLongShortPositionRatio",
        {"symbol": symbol_clean, "period": period, "limit": 1},
    )
    lsr_acc = float(acc[0]["longShortRatio"]) if isinstance(acc, list) and acc else None
    lsr_pos = float(pos[0]["longShortRatio"]) if isinstance(pos, list) and pos else None
    return lsr_acc, lsr_pos


def build_symbol_data(
    symbol_clean: str,
    pair_display: str,
    ticker_info: Optional[dict] = None,
    use_closed_candle: bool = False,
) -> List[Any]:
    """
    Thu thập chỉ số một mã qua Binance REST (symbol_data_fetch / feedback khách).
    Trả về list cột A→BF.
    """
    fut_status = validate_futures_symbol(symbol_clean)
    spot_status = get_spot_status(symbol_clean)

    if ticker_info and ticker_info.get("last"):
        price = float(ticker_info["last"])
        pct24 = float(ticker_info.get("percentage", 0))
        vol24 = float(ticker_info.get("quoteVolume", 0))
    else:
        ticker = fetch_ticker_24h(symbol_clean)
        price = float(ticker["lastPrice"])
        pct24 = float(ticker["priceChangePercent"])
        vol24 = float(ticker.get("quoteVolume", 0))

    k1h, k4h, k1d, k1w = _fetch_klines_bundle(symbol_clean)

    o1 = parse_ohlcv(k1h)
    o4 = parse_ohlcv(k4h)
    o1d = parse_ohlcv(k1d)
    o1w = parse_ohlcv(k1w)

    def slice_closed(ohlc: dict) -> dict:
        if not use_closed_candle or len(ohlc["close"]) < 2:
            return ohlc
        return {k: v[:-1] for k, v in ohlc.items()}

    o1_ind = slice_closed(o1)
    closes_1h = o1_ind["close"]
    highs_1h = o1_ind["high"]
    lows_1h = o1_ind["low"]

    bb1_u, bb1_l = bb_upper_lower(closes_1h)
    bb4_u, bb4_l = bb_upper_lower(o4["close"])
    bb1d_u, bb1d_l = bb_upper_lower(o1d["close"])
    bb1w_u, bb1w_l = bb_upper_lower(o1w["close"])

    # Vol 1h/4h mẫu chatbot: volume(nến cuối) × lastPrice; MA20 = mean(volume 20 nến) × price
    idx_last = -2 if use_closed_candle and len(o1["base_vol"]) >= 2 else -1
    vol_1h = float(o1["base_vol"][idx_last]) * price
    vol_4h = float(o4["base_vol"][idx_last]) * price if o4["base_vol"] else 0.0
    vol_window = o1["base_vol"][max(0, len(o1["base_vol"]) - 20) :]
    if use_closed_candle and len(vol_window) > 1:
        vol_window = vol_window[:-1]
    vol_ma20 = _mean(vol_window) * price if vol_window else None
    vol_ratio = (vol_1h / vol_ma20) if vol_ma20 and vol_ma20 > 0 else None

    # Max/min 40 ngày
    d40 = o1d["high"][-40:]
    l40 = o1d["low"][-40:]
    max40 = max(d40) if d40 else None
    min40 = min(l40) if l40 else None

    max_up_4h, max_dn_4h = max_body_pct_4h(k4h, lookback=min(360, len(k4h)))

    # J-K: biên độ 1h max tăng/giảm trong 7 ngày (168 nến)
    ohlcv_1h_7d = k1h[-168:] if len(k1h) >= 168 else k1h
    amp_up_week, amp_dn_week = _amplitude_range_from_klines(ohlcv_1h_7d)

    # R-S: biên độ 30d từ 30 nến 1d cuối
    ohlcv_1d_30 = k1d[-30:] if len(k1d) >= 30 else k1d
    amp_up_30d, amp_dn_30d = _amplitude_range_from_klines(ohlcv_1d_30)

    # AD-AE: biên độ giá ngày lớn nhất trong 365 ngày
    max_daily_vol, max_daily_date = _max_daily_volatility_from_klines(k1d, lookback_days=365)

    # AF-AG: BB width 1d (3 ngày trước / hiện tại)
    bw_3d, bw_now = _bb_width_3d_and_now(o1d["close"])

    # RSI mẫu chatbot (calc_rsi SMA rolling) — U: 1d, AH: 4h
    rsi_1d = rsi_sma_last(o1d["close"])
    rsi_4h = rsi_sma_last(o4["close"])

    ma7 = sma_last(closes_1h, 7)
    ma25 = sma_last(closes_1h, 25)
    ma99 = sma_last(closes_1h, 99)
    macd_v, macd_s, macd_h = compute_macd(closes_1h)
    stoch_rsi_k, stoch_rsi_d = compute_stoch_rsi(closes_1h)
    stoch_k, stoch_d = compute_stochastic(highs_1h, lows_1h, closes_1h)

    (oi_usdt, oi_delta), (lsr_acc_sheet, lsr_pos_sheet) = _fetch_metrics_bundle(symbol_clean, price)

    dist_bb_up = ((bb1_u - price) / price * 100) if bb1_u and price else None
    dist_bb_dn = ((price - bb1_l) / price * 100) if bb1_l and price else None

    score, suggest, reasons = compute_score(
        price, ma7, ma25, ma99, macd_v, macd_s, macd_h,
        stoch_rsi_k, stoch_rsi_d, lsr_acc_sheet, lsr_pos_sheet, oi_delta,
    )

    recent_h = max(o1["high"][-24:]) if len(o1["high"]) >= 24 else max(o1["high"])
    recent_l = min(o1["low"][-24:]) if len(o1["low"]) >= 24 else min(o1["low"])
    open_1h = o1["open"][idx_last]

    row = [
        pair_display,
        round(pct24, 3),
        round(price, 8),
        bb1_u, bb1_l, bb4_u, bb4_l, bb1d_u, bb1d_l,
        amp_up_week if amp_up_week is not None else "",
        amp_dn_week if amp_dn_week is not None else "",
        max40, min40,
        max_up_4h, max_dn_4h,
        bb1w_u, bb1w_l,
        amp_up_30d if amp_up_30d is not None else "",
        amp_dn_30d if amp_dn_30d is not None else "",
        vol24,
        rsi_1d,
        "",
        round(bb1w_l / min40, 4) if bb1w_l and min40 else "",
        f"{dist_bb_up:.2f}%" if dist_bb_up is not None else "",
        f"{dist_bb_dn:.2f}%" if dist_bb_dn is not None else "",
        round(vol_1h, 2),
        round(vol_4h, 2),
        fut_status,
        spot_status,
        max_daily_vol,
        max_daily_date,
        f"{round(bw_3d * 100, 2)}%" if bw_3d is not None else "",
        f"{round(bw_now * 100, 2)}%" if bw_now is not None else "",
        round(rsi_4h, 2) if rsi_4h is not None else "",
        round(vol_1h, 2),
        round(vol_ma20, 2) if vol_ma20 else "",
        "",  # AK delist
        ma7, ma25, ma99,
        macd_v, macd_s, macd_h,
        stoch_rsi_k, stoch_rsi_d,
        oi_usdt, oi_delta,
        lsr_acc_sheet, lsr_pos_sheet,
        round(vol_ratio, 2) if vol_ratio else "",
        score, suggest, reasons,
        open_1h, recent_h, recent_l,
        stoch_k, stoch_d,
    ]
    return row


