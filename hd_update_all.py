#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Cập nhật sheet 100 mã (50 tăng + 50 giảm) — tab production.

Logic số liệu: binance_symbol_row (Binance REST).
Số dư: REST /fapi/v2/account (không dùng CCXT). Cột AK: delist (n8n + Support).

Chạy: python hd_update_all.py
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any, List

import cst
import symbol_filter
import gg_sheet_factory
import requests

from binance_futures_direct import futures_signed_request
from binance_symbol_row import (
    build_symbol_data,
    fetch_all_tickers_24h,
    preload_exchange_caches,
)

file_name = os.path.basename(os.path.abspath(__file__))
os.system(f"title {file_name} - {cst.key_name}")

logs_dir = cst.account_dir('logs')  # [MULTI-ACC] tách theo tài khoản
logs_dir.mkdir(exist_ok=True)
log_timestamp = datetime.now().strftime("%d_%m_%Y_%H_%M_%S")
log_filename = logs_dir / f"hd_update_all_{log_timestamp}.txt"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    encoding="utf-8",
)
logger = logging.getLogger(__name__)
file_handler = logging.FileHandler(log_filename, encoding="utf-8")
file_handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))
logger.addHandler(file_handler)

is_test_mode = False

# Tiêu đề cột A→BF (khớp sheet production)
HEADER_ROW = [
    "Mã",
    "% 24h",
    "Giá trị hiện thời",
    "BB1h trên",
    "BB1h dưới",
    "BB4h trên",
    "BB4h dưới",
    "BB1 ngày trên",
    "BB1 ngày dưới",
    "Biên độ 1h max tăng tuần",
    "Biên độ 1h max giảm tuần",
    "Max 40 ngày",
    "Min 40 ngày",
    "Max tăng 4h/60 ngày",
    "Max giảm 4h/60 ngày",
    "Giá Cao Nhất",
    "Giá Thấp Nhất",
    "Biên độ 30d tăng",
    "Biên độ 30d giảm",
    "Volume 24h",
    "RSI 14",
    "",
    "Min/Min40",
    "% đến BB1h trên",
    "% đến BB1h dưới",
    "Vol 1h",
    "Vol 4h",
    "Futures (trạng thái)",
    "Spot (trạng thái)",
    "Biên độ giá ngày lớn nhất (%)",
    "Ngày biên độ lớn nhất",
    "BB width 1d (3 ngày trước)",
    "BB width 1d (hiện tại)",
    "RSI 14 (4h)",
    "Vol 1h (hiện tại)",
    "Vol 1h MA20",
    "Cảnh báo delist sắp tới",
    "MA7 (1h)",
    "MA25 (1h)",
    "MA99 (1h)",
    "MACD (1h)",
    "MACD Signal (1h)",
    "MACD Hist (1h)",
    "Stoch RSI %K (1h)",
    "Stoch RSI %D (1h)",
    "Open Interest (USDT)",
    "OI Δ 24h (%)",
    "L/S Ratio (account)",
    "L/S Ratio (top traders)",
    "Vol 1h / MA20",
    "Score LONG/SHORT",
    "Gợi ý",
    "Lý do score",
    "Open 1h",
    "High 1h gần đây",
    "Low 1h gần đây",
    "Stoch %K (1h)",
    "Stoch %D (1h)",
]
SHEET_NUM_COLUMNS = len(HEADER_ROW)
AK_COL_IDX = HEADER_ROW.index("Cảnh báo delist sắp tới")

SHEET_LEADER_SYMBOLS = ("BTCDOM/USDT:USDT", "BTC/USDT:USDT")


def _fetch_account_balances() -> tuple:
    """
    Số dư margin / ví / PnL qua REST (timeout 15s).
    Tránh CCXT fetch_balance() — hay treo sau khi xử lý xong ~100 mã.
    """
    print("💰 Đang lấy số dư tài khoản (REST /fapi/v2/account)...", flush=True)
    try:
        acc = futures_signed_request("GET", "/fapi/v2/account", timeout=15)
        if not isinstance(acc, dict):
            raise RuntimeError("API account không trả JSON object")
        margin = round(float(acc.get("totalMarginBalance") or 0), 4)
        wallet = round(float(acc.get("totalWalletBalance") or 0), 4)
        pnl_raw = acc.get("totalCrossUnPnl")
        if pnl_raw is None:
            pnl_raw = acc.get("totalUnrealizedProfit", 0)
        pnl = round(float(pnl_raw or 0), 4)
        print(f"   └─ margin={margin} | ví={wallet} | pnl={pnl}", flush=True)
        return margin, wallet, pnl
    except Exception as e:
        logger.warning(f"fetch account REST: {e}", exc_info=True)
        print(f"⚠️ Không lấy được số dư (bỏ qua): {e}", flush=True)
        return "", "", ""


def _col_letter(idx: int) -> str:
    if idx < 0:
        return "?"
    n = idx + 1
    letters = []
    while n:
        n, r = divmod(n - 1, 26)
        letters.append(chr(ord("A") + r))
    return "".join(reversed(letters))


def log_symbol_column_audit_to_main_log(symbol: str, row: list) -> None:
    """Ghi A→BF mã động đầu tiên vào log chính (đối chiếu)."""
    if not symbol or not row:
        return
    try:
        logger.info("=" * 70)
        logger.info(f"COLUMN AUDIT (mã động đầu tiên, bỏ BTC/BTCDOM): {symbol}")
        for i, col_name in enumerate(HEADER_ROW):
            value = row[i] if i < len(row) else ""
            if isinstance(value, float):
                rendered = f"{value:,.8f}".rstrip("0").rstrip(".") if math.isfinite(value) else str(value)
            else:
                rendered = str(value) if value != "" else "(trống)"
            logger.info(f"{_col_letter(i):<3} | {col_name:<35} | {rendered}")
        logger.info("=" * 70)
    except Exception as e:
        logger.error(f"Lỗi ghi column audit cho {symbol}: {e}", exc_info=True)


# ── Delist (cột AK) ─────────────────────────────────────────────────────────

# Binance CMS đã đổi sang POST (GET trả 400 từ ~2025). Thử 2 endpoint:
_BINANCE_CMS_URLS = [
    "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query",
    "https://www.binance.com/bapi/apex/v1/public/apex/cms/article/list/query",
]
_BINANCE_DELIST_CATALOG_ID = 161
_CMS_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Content-Type": "application/json",
    "lang": "en",
    "Accept-Language": "en",
    "clienttype": "web",
    "Referer": "https://www.binance.com/en/support/announcement/list/161",
}
_DELIST_API_URL = "https://n8n.deepview.win/webhook/delist-current-month"


def _venue_from_delist_title(title: str) -> str:
    t = title.lower()
    if "binance futures" in t or "futures will delist" in t or "usdt-m" in t or "usdⓈ-m" in t:
        return "FUT"
    if "margin" in t and "futures" not in t and "futures will" not in t:
        return "MG"
    return "SPOT"


def _extract_dates_from_text(text: str) -> list:
    return re.findall(r"\d{4}-\d{2}-\d{2}", text or "")


def _pick_delist_date_for_article(dates, today_d):
    if not dates:
        return None
    parsed = []
    for d in dates:
        try:
            dt = datetime.strptime(d, "%Y-%m-%d").date()
            parsed.append((dt, d))
        except ValueError:
            continue
    if not parsed:
        return None
    future = [(dt, s) for dt, s in parsed if dt >= today_d]
    if future:
        future.sort(key=lambda x: x[0])
        return future[0][1]
    parsed.sort(key=lambda x: x[0])
    last_dt, last_s = parsed[-1]
    if (today_d - last_dt).days <= 120:
        return last_s
    return None


def _symbol_tokens_from_delist_title(title: str) -> set:
    t = (title or "").upper()
    bases: set = set()
    for m in re.finditer(r"(?<![A-Z0-9])([A-Z0-9]{2,32})USDT(?![A-Z0-9])", t):
        b = m.group(1)
        if b in ("USD", "USDC"):
            continue
        bases.add(b)
    for m in re.finditer(r"(?<![A-Z0-9])([A-Z0-9]{2,20})USD(?![A-Z0-9])", t):
        b = m.group(1)
        if b in ("USD", "USDT", "BUSD", "TUSD", "USDC", "USDD"):
            continue
        bases.add(b)
    m = re.search(
        r"(?:BINANCE )?WILL DELIST\s+(.+?)(?:\s+ON\s+\d{4}-\d{2}-\d{2}|\s+ON\s+\(|\(|\Z)",
        t,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        chunk = m.group(1)
        chunk = re.sub(r"\s+", " ", chunk)
        for noise in [
            "MULTIPLE", "CONTRACTS", "PERPETUAL", "MARGIN", "LOAN", "SUPPORT", "REBRAND",
            "AIRDROP", "PLAN", "USDT", "U.S.", "DOLLAR",
        ]:
            chunk = re.sub(rf"\b{noise}\b", " ", chunk, flags=re.I)
        for part in re.split(r"[,;]|\s+AND\s+|\s+FROM\s+", chunk):
            part = re.sub(r"[\(\)\[\]—\-]", " ", part).strip()
            if not part:
                continue
            tok = re.sub(r"[^A-Z0-9]", "", part) if part else ""
            if 2 <= len(tok) <= 20 and tok.isalnum() and not tok.isdigit():
                bases.add(tok)
    noise2 = {
        "BINANCE", "FUTURES", "SPOT", "WILL", "NOTIFY", "NOTICE", "MARGIN", "REMOVAL",
        "TRADING", "USDT", "USDC", "BUSD", "LOAN", "PAIR", "PAIRS", "DELIST", "SUPPORT", "ON",
    }
    return {b for b in bases if b not in noise2}


def _build_upcoming_delist_by_pair() -> dict:
    today_d = datetime.now().date()
    by_pair_venue: dict = {}

    # Thử POST lần lượt qua các endpoint (Binance hay đổi)
    articles = []
    _cms_body = {"type": 1, "pageNo": 1, "pageSize": 200, "catalogId": _BINANCE_DELIST_CATALOG_ID}
    for _cms_url in _BINANCE_CMS_URLS:
        try:
            r = requests.post(
                _cms_url,
                json=_cms_body,
                headers=_CMS_HEADERS,
                timeout=45,
            )
            if r.status_code in (403, 400):
                logger.info(f"binance delist: {_cms_url} trả {r.status_code}, thử endpoint tiếp")
                continue
            r.raise_for_status()
            data = r.json()
            if data.get("code") not in (None, "000000", 0, "0"):
                logger.warning(f"binance delist: API code={data.get('code')} msg={data.get('message')}")
                continue
            arts = (data.get("data") or {}).get("catalogs")
            if not arts:
                logger.warning(f"binance delist: không có catalogs từ {_cms_url}")
                continue
            articles = arts[0].get("articles") or []
            logger.info(f"binance delist: đọc được {len(articles)} bài catalog 161 (từ {_cms_url})")
            break  # Thành công → dừng
        except Exception as e:
            logger.warning(f"binance delist: lỗi {_cms_url}: {e}")
            continue

    if not articles:
        logger.warning("binance delist: không tải được bài viết từ bất kỳ endpoint nào")
        return {}

    articles_matched = 0
    for art in articles:
        title = (art.get("title") or "").strip()
        if not title:
            continue
        if re.search(r"Delist|Delisting|REMOVAL|Remove\s+(?:of|Spot|Margin)", title, re.I) is None:
            continue
        if re.search(r"multiple|several|various", title, re.I) and not re.search(
            r"(?<![A-Z0-9])([A-Z0-9]{2,32})USDT(?![A-Z0-9])", title, re.I
        ):
            continue
        dates = _extract_dates_from_text(title)
        d_use = _pick_delist_date_for_article(dates, today_d)
        if not d_use:
            continue
        venue = _venue_from_delist_title(title)
        syms = _symbol_tokens_from_delist_title(title)
        if not syms:
            continue
        articles_matched += 1
        for b in syms:
            pkey = f"{b.upper()}/USDT"
            by_pair_venue.setdefault(pkey, {})
            by_pair_venue[pkey].setdefault(venue, set()).add(d_use)

    logger.info(f"binance delist: {articles_matched} bài có mã + ngày → {len(by_pair_venue)} cặp")
    flat: dict = {}
    for pkey, venues in by_pair_venue.items():
        parts: list = []
        for v in ("FUT", "MG", "SPOT"):
            if v not in venues:
                continue
            d_sorted = sorted(venues[v])[:3]
            parts.append(f"{v} {', '.join(d_sorted)}")
        if parts:
            s = " | ".join(parts)
            flat[pkey] = s[:320] if len(s) > 320 else s
    return flat


def _delist_warn_lookup(dmap, pair):
    if not dmap or not pair:
        return ""
    if pair in dmap:
        return dmap[pair]
    pu = pair.upper()
    if pu in dmap:
        return dmap[pu]
    for k in dmap.keys():
        if str(k).upper() == pu:
            return dmap[k]
    return ""


def _normalize_pair_for_sheet(symbol: str) -> str:
    return str(symbol or "").replace(":USDT", "").upper()


def _dedupe_symbols_by_normalized_pair(symbols, tickers):
    chosen: dict = {}
    for s in symbols:
        key = _normalize_pair_for_sheet(s)
        if not key:
            continue
        prev = chosen.get(key)
        if prev is None:
            chosen[key] = s
            continue
        if (":USDT" in s) and (":USDT" not in prev):
            chosen[key] = s
            continue
        try:
            prev_vol = float(tickers.get(prev, {}).get("quoteVolume") or 0)
            cur_vol = float(tickers.get(s, {}).get("quoteVolume") or 0)
            if cur_vol > prev_vol:
                chosen[key] = s
        except Exception:
            pass
    return list(chosen.values())


def _parse_delist_datetime_utc(raw: str):
    txt = str(raw or "").strip()
    if not txt:
        return None
    for fmt in ("%Y-%m-%d %H:%M UTC", "%Y-%m-%d %H:%M:%S UTC"):
        try:
            return datetime.strptime(txt, fmt)
        except ValueError:
            continue
    return None


def _load_future_delist_by_pair_from_api() -> dict:
    try:
        r = requests.get(_DELIST_API_URL, timeout=30)
        r.raise_for_status()
        # n8n webhook có thể trả 200 nhưng body rỗng → r.json() crash
        if not r.text or not r.text.strip():
            logger.warning("Delist API trả body rỗng (200 nhưng không có dữ liệu)")
            return {}
        payload = r.json()
    except Exception as e:
        logger.warning(f"Không tải được delist API: {e}")
        return {}

    if not isinstance(payload, dict):
        logger.warning("Delist API trả dữ liệu không phải object")
        return {}
    if payload.get("success") is False:
        logger.warning(f"Delist API báo lỗi: {payload}")
        return {}

    items = payload.get("data")
    if not isinstance(items, list):
        logger.warning("Delist API thiếu trường data dạng list")
        return {}

    now_utc = datetime.utcnow()
    best: dict = {}

    for it in items:
        if not isinstance(it, dict):
            continue
        pair_key = str(it.get("symbol") or "").strip().upper()
        dt_txt = str(it.get("delist_datetime") or "").strip()
        if not pair_key or not dt_txt:
            continue
        dt_utc = _parse_delist_datetime_utc(dt_txt)
        if dt_utc is None or dt_utc <= now_utc:
            continue
        prev = best.get(pair_key)
        if prev is None or dt_utc < prev[0]:
            best[pair_key] = (dt_utc, pair_key)

    out = {k: v[1] for k, v in best.items()}
    logger.info(f"Delist API: {len(out)} cặp có mốc delist trong tương lai")
    return out


def _merge_delist_warn_api_and_cms(api_map: dict, cms_map: dict) -> dict:
    keys = set(api_map or {}) | set(cms_map or {})
    merged: dict = {}
    for k in keys:
        parts = []
        if api_map and k in api_map and api_map[k]:
            parts.append(api_map[k])
        if cms_map and k in cms_map and cms_map[k]:
            parts.append(f"Support: {cms_map[k]}")
        if parts:
            s = " | ".join(parts)
            merged[k] = s[:400] if len(s) > 400 else s
    return merged


# ══════════════════════════════════════════════════════════════════════════════
# HAI CHẾ ĐỘ CHẠY — khai bằng `update_all_mode` trong [global]
#
#   balance_only (MẶC ĐỊNH) : chỉ lấy SỐ DƯ, ghi vào J1:M2 tab ĐẶT LỆNH.
#                             1 lượt gọi Binance + 1 lượt ghi Google. ~1 giây.
#                             KHÔNG đụng tới tab "100 mã" → xoá tab đó cũng
#                             không sao.
#
#   full                    : hành vi CŨ — dựng cả bảng 100 mã (58 cột: Bollinger,
#                             Stoch, khối lượng, cảnh báo delist...).
#                             8 lượt gọi Binance MỖI MÃ, mất 1–3 phút, tốn RAM.
#                             ⚠️ Chỉ bật khi tab "100 mã" VẪN CÒN trên sheet.
#
# `symbol_mode` / `symbol_list` CHỈ có tác dụng ở chế độ full.
# ══════════════════════════════════════════════════════════════════════════════
UPDATE_ALL_MODE = (cst.config.get('global', 'update_all_mode',
                                  fallback='balance_only') or 'balance_only').strip().lower()
if UPDATE_ALL_MODE not in ('balance_only', 'full'):
    raise SystemExit(
        f"❌ update_all_mode = '{UPDATE_ALL_MODE}' không hợp lệ. "
        f"Chỉ nhận: balance_only hoặc full."
    )

# Vùng ghi số dư trên tab ĐẶT LỆNH: J1:M2 (2 dòng × 4 cột)
BALANCE_ANCHOR_COL = (cst.config.get('global', 'balance_cell',
                                     fallback='J') or 'J').strip().upper()
BALANCE_HEADER = ["Số dư ví", "Ký quỹ", "Lãi/lỗ mở", "Cập nhật lúc"]


def _ghi_so_du(total_margin, total_wallet, total_pnl):
    """
    Ghi số dư + thời điểm cập nhật vào J1:M2 của tab ĐẶT LỆNH.

        J            K         L          M
    1   Số dư ví     Ký quỹ    Lãi/lỗ mở  Cập nhật lúc
    2   12345.67     2000.00   -50.25     05/09/2026 14:30:00

    Vùng J1:M2 đã kiểm chứng là TRỐNG: dòng 1-2 của tab ĐẶT LỆNH hiện chỉ dùng
    B2 (trạng thái) và D1:E2 (cấu hình vốn); hd_track_30_prices ghi cột I:Z
    nhưng chỉ ở dòng 4-53 và 55-104.
    """
    ts = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    khoi = [BALANCE_HEADER, [total_wallet, total_margin, total_pnl, ts]]
    # array_index = -1 → ghi từ dòng 1
    gg_sheet_factory.update_multi(
        gg_sheet_factory.tab_dat_lenh, -1, khoi, BALANCE_ANCHOR_COL)
    print(f"   └─ ví={total_wallet} ký quỹ={total_margin} pnl={total_pnl} lúc {ts}",
          flush=True)


def do_it():
    start_time = time.time()

    if UPDATE_ALL_MODE == 'balance_only':
        print(f"\n{'='*80}", flush=True)
        print(f"💰 CẬP NHẬT SỐ DƯ → {gg_sheet_factory.tab_dat_lenh} "
              f"{BALANCE_ANCHOR_COL}1:M2 - {datetime.now():%Y-%m-%d %H:%M:%S}", flush=True)
        print(f"{'='*80}\n", flush=True)
        logger.info("BẮT ĐẦU CẬP NHẬT SỐ DƯ (chế độ balance_only)")
        total_margin, total_wallet, total_pnl = _fetch_account_balances()
        _ghi_so_du(total_margin, total_wallet, total_pnl)
        print(f"✅ Xong sau {time.time() - start_time:.1f}s", flush=True)
        logger.info(f"Cập nhật số dư xong sau {time.time() - start_time:.1f}s")
        return

    print(f"\n{'='*80}", flush=True)
    print(f"🚀 BẮT ĐẦU CẬP NHẬT SHEET 100 MÃ - {datetime.now():%Y-%m-%d %H:%M:%S}", flush=True)
    print(f"{'='*80}\n", flush=True)
    logger.info("BẮT ĐẦU CẬP NHẬT DỮ LIỆU SHEET 100 MÃ")

    total_margin, total_wallet, total_pnl = _fetch_account_balances()

    tickers = fetch_all_tickers_24h()
    print(f"✅ Đã lấy {len(tickers)} tickers (REST)", flush=True)

    all_futures_usdt = [
        s for s in tickers
        if "/USDT" in s and "-" not in s and tickers[s].get("percentage") is not None
    ]
    print(f"📊 Futures USDT: {len(all_futures_usdt)}", flush=True)

    try:
        white_list = set(gg_sheet_factory.get_white_list())
        print(f"📝 Whitelist: {len(white_list)} mã", flush=True)
    except Exception as e:
        logger.warning(f"Whitelist: {e}")
        white_list = set()

    # ── CHẾ ĐỘ CHỌN MÃ (xem symbol_filter.py) ────────────────────────────────
    che_do_list = (cst.symbol_mode == symbol_filter.MODE_LIST)

    if che_do_list:
        # Chỉ lấy đúng các mã khai trong symbol_list.
        # Mã dẫn đầu (BTCDOM, BTC) đã hiển thị riêng ở đầu sheet nên bỏ khỏi
        # danh sách để không xuất hiện hai lần.
        dung, thieu, trung_dan_dau = symbol_filter.loc_theo_danh_sach(
            cst.symbol_list, set(all_futures_usdt), bo_qua=SHEET_LEADER_SYMBOLS)

        print(f"🎯 symbol_mode=list — khai {len(cst.symbol_list)} mã, "
              f"dùng được {len(dung)}", flush=True)
        for m in trung_dan_dau:
            print(f"   ℹ️  {m} đã có ở dòng dẫn đầu — bỏ khỏi danh sách (khỏi trùng)",
                  flush=True)
        for m in thieu:
            print(f"   ⚠️  {m} KHÔNG có trên Binance Futures USDT — bỏ qua", flush=True)
            logger.warning(f"symbol_list: {m} không có trên sàn")

        if not dung:
            # KHÔNG âm thầm quay về 100 mã: chạy nhầm 100 mã nguy hiểm hơn là dừng.
            raise SystemExit(
                "❌ symbol_mode = list nhưng KHÔNG mã nào trong symbol_list dùng được.\n"
                f"   Đang khai: {', '.join(cst.symbol_list) or '(trống)'}\n"
                "   Kiểm tra lại chính tả, hoặc đổi symbol_mode = all."
            )

        # Ở chế độ này người dùng đã CHỌN TAY từng mã → không lọc theo volume,
        # nhưng vẫn cảnh báo nếu mã quá ít thanh khoản.
        for m in dung:
            vol = tickers[m].get("quoteVolume") or 0
            if vol < 100_000:
                print(f"   ⚠️  {m} thanh khoản thấp (24h: {vol:,.0f} USDT)", flush=True)
        futures_symbols = [s for s in dung if (tickers[s].get("last") or 0) > 0]

    else:
        if white_list:
            futures_symbols = [s for s in all_futures_usdt if s in white_list]
            if not futures_symbols:
                print("⚠️  Whitelist tab 'list' không khớp mã nào → dùng lại TOÀN BỘ mã.",
                      flush=True)
                logger.warning("Whitelist không khớp mã nào — quay về toàn bộ")
                futures_symbols = all_futures_usdt
        else:
            futures_symbols = all_futures_usdt

        futures_symbols = [
            s for s in futures_symbols
            if (tickers[s].get("quoteVolume") or 0) >= 100_000
            and (tickers[s].get("last") or 0) > 0
        ]
    futures_symbols = _dedupe_symbols_by_normalized_pair(futures_symbols, tickers)
    print(f"✅ Sau lọc: {len(futures_symbols)} mã", flush=True)

    preload_exchange_caches()

    print("📣 Tải cảnh báo delist...", flush=True)
    delist_warn_by_pair = _merge_delist_warn_api_and_cms(
        _load_future_delist_by_pair_from_api(),
        _build_upcoming_delist_by_pair(),
    )
    print(f"   └─ AK: {len(delist_warn_by_pair)} cặp", flush=True)

    def get_row_result(symbol: str) -> List[Any]:
        pair = symbol.replace(":USDT", "")
        symbol_clean = pair.replace("/", "")
        ti = tickers.get(symbol) or {}
        price = float(ti.get("last") or 0)
        pct = float(ti.get("percentage") or 0)

        if price <= 0:
            empty = [""] * SHEET_NUM_COLUMNS
            empty[0] = pair
            empty[1] = pct
            empty[AK_COL_IDX] = _delist_warn_lookup(delist_warn_by_pair, pair)
            return empty

        t0 = time.perf_counter()
        print(f"🔄 [REST] {symbol} - %24h: {pct:.2f}%, giá: {price}", flush=True)
        try:
            row = list(build_symbol_data(symbol_clean, pair, ticker_info=ti))
            if len(row) < SHEET_NUM_COLUMNS:
                row.extend([""] * (SHEET_NUM_COLUMNS - len(row)))
            elif len(row) > SHEET_NUM_COLUMNS:
                row = row[:SHEET_NUM_COLUMNS]
            row[AK_COL_IDX] = _delist_warn_lookup(delist_warn_by_pair, pair)
            print(f"   └─ xong {time.perf_counter() - t0:.1f}s", flush=True)
            time.sleep(0.05)
            return row
        except Exception as e:
            print(f"⚠️ {pair} lỗi: {e}", flush=True)
            logger.warning(f"[{symbol}] build_symbol_data: {e}", exc_info=True)
            empty = [""] * SHEET_NUM_COLUMNS
            empty[0] = pair
            empty[1] = pct
            empty[AK_COL_IDX] = _delist_warn_lookup(delist_warn_by_pair, pair)
            return empty

    tab_rows: List[List[Any]] = []
    title1 = f"Top {cst.top_count} có % giảm giá nhiều nhất trong 24h"
    title2 = f"Top {cst.top_count} có % tăng giá nhiều nhất trong 24h"
    empty_row = [""] * SHEET_NUM_COLUMNS

    for fixed_sym in SHEET_LEADER_SYMBOLS:
        if fixed_sym in tickers:
            tab_rows.append(get_row_result(fixed_sym))
        else:
            tab_rows.append(empty_row)

    excluded = set(SHEET_LEADER_SYMBOLS)

    if che_do_list:
        # BỐ CỤC PHẲNG: không chia tăng/giảm, không dòng tiêu đề.
        # Giữ ĐÚNG THỨ TỰ người dùng khai trong symbol_list.
        list_all = list(futures_symbols)
        print(f"📋 Bố cục phẳng — {len(list_all)} mã theo đúng thứ tự đã khai",
              flush=True)
    else:
        giam_symbols = [s for s in futures_symbols if tickers[s]["percentage"] < 0 and s not in excluded]
        tang_symbols = [s for s in futures_symbols if tickers[s]["percentage"] > 0 and s not in excluded]
        list_giam = sorted(giam_symbols, key=lambda x: tickers[x]["percentage"])[: cst.top_count]
        list_tang = sorted(tang_symbols, key=lambda x: tickers[x]["percentage"], reverse=True)[: cst.top_count]

        list_all = [title1, *list_giam, title2, *list_tang]
    with open(cst.account_dir("data") / "list_all.json", "w", encoding="utf-8") as f:  # [MULTI-ACC]
        json.dump(list_all, f)

    def _fetch_symbols_parallel(symbols: list, label: str) -> list:
        """Fetch nhiều symbol song song, giữ đúng thứ tự."""
        if not symbols:
            return []
        # max_workers=3: cân bằng tốc độ và rate limit (3 account × 3 workers × 8 req/mã = 72 burst)
        results: dict = {}
        with ThreadPoolExecutor(max_workers=3) as pool:
            future_map = {pool.submit(get_row_result, sym): (i, sym) for i, sym in enumerate(symbols)}
            done_count = 0
            for fut in as_completed(future_map):
                i, sym = future_map[fut]
                done_count += 1
                try:
                    results[i] = fut.result()
                    print(f"{label} [{done_count}/{len(symbols)}] ✅ {sym}", flush=True)
                except Exception as e:
                    logger.warning(f"{label} {sym} lỗi trong parallel fetch: {e}", exc_info=True)
                    results[i] = empty_row
        return [results[i] for i in range(len(symbols))]

    first_dynamic_symbol = None
    first_dynamic_row = None

    if che_do_list:
        # ══ BỐ CỤC PHẲNG (symbol_mode = list) ═══════════════════════════════
        # Không dòng tiêu đề, không chia tăng/giảm, không chèn dòng trống cho
        # đủ top_count. Các mã xếp ĐÚNG THỨ TỰ đã khai trong symbol_list.
        flat_data = _fetch_symbols_parallel(list_all, "🎯")
        if flat_data:
            first_dynamic_symbol, first_dynamic_row = list_all[0], flat_data[0]
        tab_rows.extend(flat_data)
        giam_data, tang_data = [], flat_data     # cho dòng tổng kết bên dưới
        print(f"✅ Đã xử lý xong {len(flat_data)} mã (bố cục phẳng)", flush=True)

    else:
        # ══ BỐ CỤC HAI KHỐI như cũ (symbol_mode = all) ══════════════════════
        tab_rows.append([title1] + [""] * (SHEET_NUM_COLUMNS - 1))

        _list_giam = list_giam[:1] if is_test_mode else list_giam
        giam_data = _fetch_symbols_parallel(_list_giam, "📉")
        if giam_data:
            first_dynamic_symbol, first_dynamic_row = _list_giam[0], giam_data[0]
        tab_rows.extend(giam_data)
        for _ in range(max(0, cst.top_count - len(giam_data))):
            tab_rows.append(empty_row)

        # Refresh tickers trước khi xử lý danh sách tăng (giảm ~50% độ cũ của giá)
        try:
            tickers = fetch_all_tickers_24h()
            print(f"🔄 Đã refresh tickers ({len(tickers)} symbols) trước danh sách tăng", flush=True)
        except Exception as e:
            logger.warning(f"Không refresh được tickers giữa chừng: {e}")

        tab_rows.append([title2] + [""] * (SHEET_NUM_COLUMNS - 1))
        _list_tang = [] if is_test_mode else list_tang
        tang_data = _fetch_symbols_parallel(_list_tang, "📈")
        if tang_data and first_dynamic_symbol is None:
            first_dynamic_symbol, first_dynamic_row = _list_tang[0], tang_data[0]
        tab_rows.extend(tang_data)
        for _ in range(max(0, cst.top_count - len(tang_data))):
            tab_rows.append(empty_row)

    if not che_do_list:
        print(
            f"✅ Đã xử lý xong {len(giam_data)} giảm + {len(tang_data)} tăng "
            f"(tổng {len(tab_rows)} dòng nội dung)",
            flush=True,
        )

    sheet_data = (
        [HEADER_ROW]
        + [["Số dư margin/ví/pnl", total_margin, total_wallet, total_pnl]]
        + tab_rows
    )

    # ⚠️ XOÁ DỮ LIỆU CŨ TRƯỚC KHI GHI
    #
    # Google Sheets values.update CHỈ ghi đè đúng số dòng gửi lên — dòng thừa
    # bên dưới GIỮ NGUYÊN nội dung cũ → các mã của lần chạy trước vẫn nằm lại,
    # nhìn sheet tưởng bot vẫn đang theo dõi chúng.
    # Xoá ở CẢ HAI chế độ:
    #   • list : chỉ ghi vài dòng → không xoá thì 90+ mã cũ nằm lại bên dưới
    #   • all  : nếu đổi top_count (vd 50→20) thì phần dôi ra cũng nằm lại
    # Tốn thêm 1 lượt gọi Google mỗi vòng (~0.5 lượt/phút/tài khoản) — không đáng kể.
    print("🧹 Xoá dữ liệu cũ trên tab trước khi ghi danh sách mới...", flush=True)
    gg_sheet_factory.clear_multi(
        gg_sheet_factory.tab_list_all_ma, -1, "A", end_row=1000, end_column="ZZ")

    print(f"💾 Đang ghi {len(sheet_data)} dòng → Google Sheet (có thể mất 1–3 phút)...", flush=True)
    t_write = time.perf_counter()
    gg_sheet_factory.update_multi(gg_sheet_factory.tab_list_all_ma, -1, sheet_data, "A")
    print(f"   └─ ghi sheet xong {time.perf_counter() - t_write:.1f}s", flush=True)

    print("🕐 Cập nhật timestamp A1...", flush=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    gg_sheet_factory.update_single_value(gg_sheet_factory.tab_list_all_ma, "A1", ts)

    elapsed = time.time() - start_time
    print(f"✅ Hoàn tất {elapsed:.1f}s | {len(giam_data)} giảm + {len(tang_data)} tăng | A1={ts}", flush=True)
    logger.info(f"Hoàn tất — {elapsed:.1f}s")
    if first_dynamic_symbol and first_dynamic_row:
        print(f"📝 Ghi column audit vào log: {first_dynamic_symbol}...", flush=True)
        log_symbol_column_audit_to_main_log(first_dynamic_symbol, first_dynamic_row)


gg_sheet_factory.init_sheet_api()

print("\n" + "=" * 80, flush=True)
print("  HD_UPDATE_ALL — Sheet 100 mã (binance_symbol_row + delist AK)", flush=True)
print(f"  Log: {log_filename}", flush=True)
print(f"  Delay: {cst.delay_update_all}s | Top: {cst.top_count}", flush=True)
print("=" * 80 + "\n", flush=True)

while True:
    try:
        do_it()
    except Exception as e:
        print(f"❌ Tổng lỗi: {e}", flush=True)
        logger.error(f"Tổng lỗi: {e}", exc_info=True)
    if is_test_mode:
        break
    print(f"\n⏳ Chờ {cst.delay_update_all}s...\n", flush=True)
    time.sleep(cst.delay_update_all)
