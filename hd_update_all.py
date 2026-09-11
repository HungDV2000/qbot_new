#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
hd_update_all — ghi SỐ DƯ tài khoản vào tab ĐẶT LỆNH, vùng J1:M2.

        J            K         L          M
    1   Số dư ví     Ký quỹ    Lãi/lỗ mở  Cập nhật lúc
    2   12345.67     2000.00   -50.25     05/09/2026 14:30:00

Mỗi vòng: 1 lượt gọi Binance (REST /fapi/v2/account) + 1 lượt ghi Google.
Nhịp: `delay_update_all` (giây). Cột bắt đầu: `balance_cell` (mặc định J).

Bản cũ còn chế độ `full` dựng bảng "100 mã" 58 cột — đã bỏ cùng tab đó.

Chạy: python hd_update_all.py
"""
import logging
import os
import time
from datetime import datetime

import cst
import config_watcher
import gg_sheet_factory
from binance_futures_direct import futures_signed_request

file_name = os.path.basename(os.path.abspath(__file__))
os.system(f"title {file_name} - {cst.key_name}")

logs_dir = cst.account_dir('logs')  # [MULTI-ACC] tách theo tài khoản
logs_dir.mkdir(exist_ok=True)
log_filename = logs_dir / f"hd_update_all_{datetime.now().strftime('%d_%m_%Y_%H_%M_%S')}.txt"

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

# Máy cũ có thể còn dòng `update_all_mode = full` trong config.ini
_che_do_cu = (cst.config.get('global', 'update_all_mode', fallback='') or '').strip().lower()
if _che_do_cu and _che_do_cu != 'balance_only':
    print(f"⚠️  update_all_mode = {_che_do_cu}: chế độ này đã bỏ cùng tab \"100 mã\" "
          f"— bot chỉ ghi số dư. Xoá dòng đó khỏi config.ini cho gọn.", flush=True)

BALANCE_ANCHOR_COL = (cst.config.get('global', 'balance_cell',
                                     fallback='J') or 'J').strip().upper()
BALANCE_HEADER = ["Số dư ví", "Ký quỹ", "Lãi/lỗ mở", "Cập nhật lúc"]


def _fetch_account_balances() -> tuple:
    """Số dư margin / ví / PnL qua REST (timeout 15s). Lỗi → 3 ô trống."""
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


def _ghi_so_du(total_margin, total_wallet, total_pnl):
    """Ghi tiêu đề + số dư + thời điểm cập nhật vào J1:M2 của tab ĐẶT LỆNH."""
    ts = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    khoi = [BALANCE_HEADER, [total_wallet, total_margin, total_pnl, ts]]
    # array_index = -1 → ghi từ dòng 1
    gg_sheet_factory.update_multi(
        gg_sheet_factory.tab_dat_lenh, -1, khoi, BALANCE_ANCHOR_COL)
    print(f"   └─ ví={total_wallet} ký quỹ={total_margin} pnl={total_pnl} lúc {ts}",
          flush=True)


def do_it():
    bat_dau = time.time()
    print(f"\n{'='*80}", flush=True)
    print(f"💰 CẬP NHẬT SỐ DƯ → {gg_sheet_factory.tab_dat_lenh} "
          f"{BALANCE_ANCHOR_COL}1:M2 - {datetime.now():%Y-%m-%d %H:%M:%S}", flush=True)
    print(f"{'='*80}\n", flush=True)
    total_margin, total_wallet, total_pnl = _fetch_account_balances()
    _ghi_so_du(total_margin, total_wallet, total_pnl)
    print(f"✅ Xong sau {time.time() - bat_dau:.1f}s", flush=True)
    logger.info(f"Cập nhật số dư xong sau {time.time() - bat_dau:.1f}s")


gg_sheet_factory.init_sheet_api()

print("\n" + "=" * 80, flush=True)
print("  HD_UPDATE_ALL — số dư → tab ĐẶT LỆNH J1:M2", flush=True)
print(f"  Log: {log_filename}", flush=True)
print(f"  Nhịp: {cst.delay_update_all}s", flush=True)
print("=" * 80 + "\n", flush=True)

while True:
    try:
        do_it()
    except Exception as e:
        print(f"❌ Tổng lỗi: {e}", flush=True)
        logger.error(f"Tổng lỗi: {e}", exc_info=True)
    print(f"\n⏳ Chờ {cst.delay_update_all}s...\n", flush=True)
    config_watcher.ngu(cst.delay_update_all)
