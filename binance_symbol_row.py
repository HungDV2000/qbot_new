# -*- coding: utf-8 -*-
"""
Giá hiện tại từ Binance Futures REST (không cần key) — hd_update_cho_va_khop
dùng để ghi cột Q ("giá hiện tại") tab "Chờ và khớp".

Bản cũ còn dựng cả dòng 58 cột cho tab "100 mã" (Bollinger, RSI, OI...) — đã
bỏ cùng tab đó.
"""
from __future__ import annotations

import json
import logging
import re
import time
import urllib.parse
import urllib.request
from typing import Any, Optional, Tuple

logger = logging.getLogger(__name__)

BASE_FUTURES = "https://fapi.binance.com"


def _http_get(base: str, path: str, params: Optional[dict] = None, timeout: int = 12) -> Any:
    import urllib.error
    qs = urllib.parse.urlencode(params or {})
    url = f"{base}{path}" + (f"?{qs}" if qs else "")
    req = urllib.request.Request(url, headers={"User-Agent": "qbot/1.0"})
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


def fetch_ticker_24h(symbol_clean: str) -> dict:
    data = _http_get(BASE_FUTURES, "/fapi/v1/ticker/24hr", {"symbol": symbol_clean})
    if not isinstance(data, dict):
        raise RuntimeError("ticker/24hr không hợp lệ")
    return data


def fetch_all_tickers_24h() -> dict:
    """
    GET /fapi/v1/ticker/24hr (toàn sàn, 1 lượt gọi).
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
        key = f"{sym[:-4]}/USDT:USDT"
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
    Giá hiện tại của 1 mã: lấy từ bảng ticker toàn sàn, round(..., 8).
    Không có trong bảng thì hỏi riêng mã đó. Lỗi → ô trống.
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
