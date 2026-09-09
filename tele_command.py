"""
tele_command.py - Telegram Bot nhận lệnh điều khiển từ xa

Chạy song song với hd_order.py trong thread riêng (daemon thread).
Nhận lệnh từ Telegram → Ghi trạng thái vào Google Sheet B2
→ Bot chính (hd_order.py) đọc B2 và xử lý ở chu kỳ tiếp theo.

Hai chế độ:
  - 1 folder 1 sheet: /stop, /pause... → ghi vào sheet của folder đó.
  - Nhiều sheet (1 bot chung nhóm): bật tele_multi_sheet, cấu hình mã sheet (A, B, C...).
    Chỉ 1 folder chạy listener (run_tele_command = true); các folder còn lại run_tele_command = false.
    Trong nhóm gõ /stop A, /stop B để chỉ định sheet.

Ví dụ config.ini (folder trung tâm lệnh - chạy listener):
  [global]
  run_tele_command = true
  tele_multi_sheet = true
  tele_slugs = A, B, C
  tele_sheet_A_id = <spreadsheet_id_của_sheet_A>
  tele_sheet_A_tab = Chờ và khớp
  tele_sheet_B_id = <spreadsheet_id_của_sheet_B>
  tele_sheet_B_tab = Chờ và khớp
  tele_sheet_C_id = <spreadsheet_id_của_sheet_C>
  tele_sheet_C_tab = Chờ và khớp

Folder chỉ chạy bot (không nhận lệnh): run_tele_command = false (hoặc bỏ dòng, mặc định true).
"""

import asyncio
import threading
import logging
import time
import configparser
import os
import ccxt

import cst
import gg_sheet_factory

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from datetime import datetime

logger = logging.getLogger(__name__)

# ── Whitelist chat_id được phép gửi lệnh ─────────────────────────────────
ALLOWED_CHAT_IDS = {str(cst.chat_id)}

# ── Multi-sheet: 1 bot, 1 nhóm, nhiều sheet (nhiều folder) ───────────────
# Chỉ 1 folder chạy Telegram listener; config.ini có tele_multi_sheet = true và danh sách sheet.
MULTI_SHEET = False
SHEET_CONFIG = {}  # slug.upper() -> {"spreadsheet_id", "tab"}


def _load_multi_sheet_config():
    global MULTI_SHEET, SHEET_CONFIG
    try:
        config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.ini")
        if not os.path.exists(config_path):
            return
        cfg = configparser.ConfigParser()
        cfg.read(config_path, encoding="utf-8")
        if not cfg.has_section("global"):
            return
        MULTI_SHEET = cfg.getboolean("global", "tele_multi_sheet", fallback=False)
        if not MULTI_SHEET:
            return
        slugs_str = cfg.get("global", "tele_slugs", fallback="").strip()
        if not slugs_str:
            MULTI_SHEET = False
            return
        slugs = [s.strip().upper() for s in slugs_str.split(",") if s.strip()]
        for slug in slugs:
            sid = cfg.get("global", f"tele_sheet_{slug}_id", fallback=None)
            tab = cfg.get("global", f"tele_sheet_{slug}_tab", fallback=None)
            if sid and tab:
                SHEET_CONFIG[slug.upper()] = {"spreadsheet_id": sid.strip(), "tab": tab.strip()}
        if SHEET_CONFIG:
            logger.info(f"[TELE CMD] Multi-sheet: slugs={list(SHEET_CONFIG.keys())}")
        else:
            MULTI_SHEET = False
    except Exception as e:
        logger.warning(f"[TELE CMD] Load multi-sheet config: {e}")
        MULTI_SHEET = False
        SHEET_CONFIG = {}


_load_multi_sheet_config()

# ── Tên bot (key_name) để hiển thị khi 1 nhóm nhiều bot ──────────────────
BOT_LABEL = getattr(cst, "key_name", None) or "Bot"


def _reply_prefix() -> str:
    return f"🤖 <b>[{BOT_LABEL}]</b>\n\n"


# ══════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════

def _write_b2(value: str, slug: str = None) -> tuple:
    """
    Ghi B2 = value. Trả (success: bool, error_msg: str | None).
    - Nếu MULTI_SHEET và slug: ghi vào sheet tương ứng slug.
    - Nếu không MULTI_SHEET: ghi vào sheet của cst (folder hiện tại).
    """
    if MULTI_SHEET:
        if not slug or not slug.strip():
            return False, "Thiếu mã sheet. Ví dụ: /stop A (hoặc B, C...). Gõ /help xem mã."
        key = slug.strip().upper()
        if key not in SHEET_CONFIG:
            return False, f"Mã sheet không hợp lệ. Có: {', '.join(SHEET_CONFIG.keys())}"
        sheet = SHEET_CONFIG[key]
        try:
            gg_sheet_factory.update_single_value_to_sheet(
                sheet["spreadsheet_id"], sheet["tab"], "B2", value
            )
            logger.info(f"[TELE CMD] Đã ghi B2 = '{value}' cho sheet [{key}]")
            return True, None
        except Exception as e:
            logger.error(f"[TELE CMD] Lỗi ghi B2 sheet [{key}]: {e}", exc_info=True)
            return False, str(e)
    try:
        gg_sheet_factory.update_single_value(cst.tab_dat_lenh, "B2", value)
        logger.info(f"[TELE CMD] Đã ghi B2 = '{value}'")
        return True, None
    except Exception as e:
        logger.error(f"[TELE CMD] Lỗi ghi B2='{value}': {e}", exc_info=True)
        return False, str(e)


def _get_slug_from_args(context: ContextTypes.DEFAULT_TYPE) -> str:
    """Lấy mã sheet từ tham số lệnh, ví dụ /stop A → 'A'."""
    if not context.args or len(context.args) < 1:
        return ""
    return (context.args[0] or "").strip()


def _get_status_text(slug: str = None) -> str:
    """Lấy thông tin trạng thái (B2 + Binance). slug chỉ dùng khi MULTI_SHEET để báo sheet nào."""
    try:
        b2_result = gg_sheet_factory.get_dat_lenh("B2:B2")
        b2_value = b2_result[0][0] if (b2_result and b2_result[0]) else "N/A"

        exchange = ccxt.binance({
            'enableRateLimit': True,
            'apiKey': cst.key_binance,
            'secret': cst.secret_binance,
            'options': {'defaultType': 'future'}
        })
        exchange.setSandboxMode(False)

        balance = exchange.fetch_balance()
        positions = balance['info'].get('positions', [])
        active_positions = [
            (p['symbol'], p['positionAmt'])
            for p in positions
            if float(p.get('positionAmt', 0)) != 0
        ]
        open_orders = exchange.fetch_open_orders()

        title = f"📊 <b>TRẠNG THÁI BOT [{BOT_LABEL}]</b>"
        if slug:
            title += f" — Sheet <code>{slug}</code>"
        lines = [title, "", f"<b>B2 (Trạng thái):</b> <code>{b2_value}</code>", f"<b>Vị thế đang mở:</b> {len(active_positions)}"]
        for sym, amt in active_positions[:15]:
            lines.append(f"  • {sym}: {amt}")
        if len(active_positions) > 15:
            lines.append(f"  ... và {len(active_positions) - 15} vị thế khác")
        lines.append(f"<b>Lệnh chờ (open orders):</b> {len(open_orders)}")
        lines.append(f"<b>Thời gian:</b> {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}")
        return "\n".join(lines)

    except Exception as e:
        logger.error(f"[TELE CMD] Lỗi _get_status_text: {e}", exc_info=True)
        return f"❌ Lỗi lấy trạng thái: {e}"


def _is_authorized(update: Update) -> bool:
    """Kiểm tra chat_id có trong whitelist không."""
    chat_id = str(update.effective_chat.id)
    if chat_id not in ALLOWED_CHAT_IDS:
        logger.warning(f"[TELE CMD] Lệnh từ chat_id KHÔNG được phép: {chat_id}")
        return False
    return True


# ══════════════════════════════════════════════════════════════════════════
# COMMAND HANDLERS
# ══════════════════════════════════════════════════════════════════════════

async def cmd_stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return
    slug = _get_slug_from_args(context)
    if MULTI_SHEET and not slug:
        await update.message.reply_text(
            _reply_prefix() + "⚠️ Thiếu mã sheet. Ví dụ: <code>/stop A</code> hoặc <code>/stop B</code>. Có: " + ", ".join(SHEET_CONFIG.keys()),
            parse_mode='HTML'
        )
        return
    logger.info(f"[TELE CMD] /stop slug={slug or '(mặc định)'} từ chat_id={update.effective_chat.id}")
    loop = asyncio.get_running_loop()
    success, err = await loop.run_in_executor(None, lambda: _write_b2("STOP", slug))
    if success:
        target = f" (sheet <b>{slug}</b>)" if slug else ""
        await update.message.reply_text(
            _reply_prefix() + f"🛑 <b>ĐÃ GHI B2 = STOP</b>{target}\n\n"
            "Bot sẽ đóng tất cả vị thế và hủy lệnh chờ ở chu kỳ tiếp theo (~60s).\n\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}",
            parse_mode='HTML'
        )
    else:
        await update.message.reply_text(_reply_prefix() + f"❌ {err or 'Lỗi ghi Sheet.'}", parse_mode='HTML')


async def cmd_pause(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return
    slug = _get_slug_from_args(context)
    if MULTI_SHEET and not slug:
        await update.message.reply_text(
            _reply_prefix() + "⚠️ Thiếu mã sheet. Ví dụ: <code>/pause A</code>. Có: " + ", ".join(SHEET_CONFIG.keys()),
            parse_mode='HTML'
        )
        return
    loop = asyncio.get_running_loop()
    success, err = await loop.run_in_executor(None, lambda: _write_b2("CHỜ", slug))
    if success:
        target = f" (sheet <b>{slug}</b>)" if slug else ""
        await update.message.reply_text(
            _reply_prefix() + f"💤 <b>ĐÃ GHI B2 = CHỜ</b>{target}\n\n"
            "Bot sẽ ngừng scan lệnh mới ở chu kỳ tiếp theo (~60s).\n"
            "Vị thế và lệnh hiện tại được giữ nguyên.\n\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}",
            parse_mode='HTML'
        )
    else:
        await update.message.reply_text(_reply_prefix() + f"❌ {err or 'Lỗi ghi Sheet.'}", parse_mode='HTML')


async def cmd_long(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return
    slug = _get_slug_from_args(context)
    if MULTI_SHEET and not slug:
        await update.message.reply_text(
            _reply_prefix() + "⚠️ Thiếu mã sheet. Ví dụ: <code>/long A</code>. Có: " + ", ".join(SHEET_CONFIG.keys()),
            parse_mode='HTML'
        )
        return
    loop = asyncio.get_running_loop()
    success, err = await loop.run_in_executor(None, lambda: _write_b2("LONG", slug))
    if success:
        target = f" (sheet <b>{slug}</b>)" if slug else ""
        await update.message.reply_text(
            _reply_prefix() + f"📈 <b>ĐÃ GHI B2 = LONG</b>{target}\n\n"
            "Bot sẽ scan và đặt lệnh LONG ở chu kỳ tiếp theo.\n\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}",
            parse_mode='HTML'
        )
    else:
        await update.message.reply_text(_reply_prefix() + f"❌ {err or 'Lỗi ghi Sheet.'}", parse_mode='HTML')


async def cmd_short(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return
    slug = _get_slug_from_args(context)
    if MULTI_SHEET and not slug:
        await update.message.reply_text(
            _reply_prefix() + "⚠️ Thiếu mã sheet. Ví dụ: <code>/short A</code>. Có: " + ", ".join(SHEET_CONFIG.keys()),
            parse_mode='HTML'
        )
        return
    loop = asyncio.get_running_loop()
    success, err = await loop.run_in_executor(None, lambda: _write_b2("SHORT", slug))
    if success:
        target = f" (sheet <b>{slug}</b>)" if slug else ""
        await update.message.reply_text(
            _reply_prefix() + f"📉 <b>ĐÃ GHI B2 = SHORT</b>{target}\n\n"
            "Bot sẽ scan và đặt lệnh SHORT ở chu kỳ tiếp theo.\n\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}",
            parse_mode='HTML'
        )
    else:
        await update.message.reply_text(_reply_prefix() + f"❌ {err or 'Lỗi ghi Sheet.'}", parse_mode='HTML')


async def cmd_xoa_cho(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return
    slug = _get_slug_from_args(context)
    if MULTI_SHEET and not slug:
        await update.message.reply_text(
            _reply_prefix() + "⚠️ Thiếu mã sheet. Ví dụ: <code>/xoa_cho A</code>. Có: " + ", ".join(SHEET_CONFIG.keys()),
            parse_mode='HTML'
        )
        return
    loop = asyncio.get_running_loop()
    success, err = await loop.run_in_executor(None, lambda: _write_b2("XÓA CHỜ", slug))
    if success:
        target = f" (sheet <b>{slug}</b>)" if slug else ""
        await update.message.reply_text(
            _reply_prefix() + f"🗑️ <b>ĐÃ GHI B2 = XÓA CHỜ</b>{target}\n\n"
            "Bot sẽ hủy tất cả lệnh chờ (pending), giữ nguyên vị thế.\n\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}",
            parse_mode='HTML'
        )
    else:
        await update.message.reply_text(_reply_prefix() + f"❌ {err or 'Lỗi ghi Sheet.'}", parse_mode='HTML')


async def cmd_xoa_vi_the(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return
    slug = _get_slug_from_args(context)
    if MULTI_SHEET and not slug:
        await update.message.reply_text(
            _reply_prefix() + "⚠️ Thiếu mã sheet. Ví dụ: <code>/xoa_vi_the A</code>. Có: " + ", ".join(SHEET_CONFIG.keys()),
            parse_mode='HTML'
        )
        return
    loop = asyncio.get_running_loop()
    success, err = await loop.run_in_executor(None, lambda: _write_b2("XÓA VỊ THẾ", slug))
    if success:
        target = f" (sheet <b>{slug}</b>)" if slug else ""
        await update.message.reply_text(
            _reply_prefix() + f"🗑️ <b>ĐÃ GHI B2 = XÓA VỊ THẾ</b>{target}\n\n"
            "Bot sẽ đóng tất cả vị thế, giữ nguyên lệnh chờ.\n\n"
            f"⏰ {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}",
            parse_mode='HTML'
        )
    else:
        await update.message.reply_text(_reply_prefix() + f"❌ {err or 'Lỗi ghi Sheet.'}", parse_mode='HTML')


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return
    slug = _get_slug_from_args(context)
    await update.message.reply_text(_reply_prefix() + "⏳ Đang lấy thông tin, vui lòng chờ...", parse_mode='HTML')
    try:
        loop = asyncio.get_running_loop()
        status_text = await loop.run_in_executor(None, lambda: _get_status_text(slug))
        await update.message.reply_text(status_text, parse_mode='HTML')
    except Exception as e:
        await update.message.reply_text(_reply_prefix() + f"❌ Lỗi lấy trạng thái: {e}", parse_mode='HTML')


async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not _is_authorized(update):
        return
    help_text = (
        _reply_prefix() +
        "📋 <b>LỆNH ĐIỀU KHIỂN</b>\n\n"
        "/stop [mã]     - Đóng vị thế + hủy lệnh chờ\n"
        "/pause [mã]    - Dừng scan (B2=CHỜ)\n"
        "/long [mã]     - Bật scan LONG\n"
        "/short [mã]    - Bật scan SHORT\n"
        "/xoa_cho [mã]  - Hủy lệnh chờ, giữ vị thế\n"
        "/xoa_vi_the [mã] - Đóng vị thế, giữ lệnh chờ\n"
        "/status [mã]   - Xem trạng thái\n"
        "/help          - Xem danh sách lệnh\n\n"
    )
    if MULTI_SHEET and SHEET_CONFIG:
        help_text += (
            "📌 <b>Nhiều sheet (1 bot, 1 nhóm):</b> Bắt buộc chỉ định <b>mã sheet</b>.\n"
            f"Mã có: <code>{', '.join(SHEET_CONFIG.keys())}</code>\n"
            "Ví dụ: <code>/stop A</code>, <code>/pause B</code>\n\n"
        )
    help_text += "⚠️ <i>Lệnh ghi vào Google Sheet, bot xử lý sau ~60s.</i>"
    await update.message.reply_text(help_text, parse_mode='HTML')


# ══════════════════════════════════════════════════════════════════════════
# RUNNER
# ══════════════════════════════════════════════════════════════════════════

def _run_bot():
    """
    Hàm chạy trong thread riêng.
    Tạo event loop mới, khởi động Application và polling.
    """
    logger.info("[TELE CMD] Thread bắt đầu, đang khởi tạo Application...")
    try:
        # Khởi tạo Google Sheets API cho thread này
        gg_sheet_factory.init_sheet_api()

        # Tạo event loop riêng cho thread (bắt buộc vì asyncio không share loop giữa threads)
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        application = Application.builder().token(cst.bot_token).build()

        application.add_handler(CommandHandler("stop",       cmd_stop))
        application.add_handler(CommandHandler("pause",      cmd_pause))
        application.add_handler(CommandHandler("long",       cmd_long))
        application.add_handler(CommandHandler("short",      cmd_short))
        application.add_handler(CommandHandler("xoa_cho",    cmd_xoa_cho))
        application.add_handler(CommandHandler("xoa_vi_the", cmd_xoa_vi_the))
        application.add_handler(CommandHandler("status",     cmd_status))
        application.add_handler(CommandHandler("help",       cmd_help))

        logger.info(f"[TELE CMD] Đang lắng nghe lệnh - Authorized: {ALLOWED_CHAT_IDS}")
        print(f"✅ [TELE CMD] Telegram command bot đang lắng nghe lệnh...", flush=True)

        # Gửi thông báo khởi động (không bắt buộc, có thể tắt nếu spam)
        async def _notify_start():
            try:
                extra = ""
                if MULTI_SHEET and SHEET_CONFIG:
                    extra = f"\nChế độ nhiều sheet. Mã: {', '.join(SHEET_CONFIG.keys())}. Gõ /stop A, /pause B..."
                await application.bot.send_message(
                    chat_id=cst.chat_id,
                    text=(
                        f"🤖 <b>Bot lệnh [{BOT_LABEL}] đã sẵn sàng</b>\n\n"
                        f"Gõ /help để xem danh sách lệnh.{extra}\n"
                        f"⏰ {datetime.now().strftime('%H:%M:%S %d/%m/%Y')}"
                    ),
                    parse_mode='HTML'
                )
            except Exception as e:
                logger.warning(f"[TELE CMD] Không gửi được tin khởi động: {e}")

        loop.run_until_complete(_notify_start())

        # Bắt đầu polling (blocking - chiếm thread này)
        application.run_polling(allowed_updates=Update.ALL_TYPES)

    except Exception as e:
        logger.error(f"[TELE CMD] Lỗi nghiêm trọng trong thread: {e}", exc_info=True)
        print(f"❌ [TELE CMD] Lỗi thread: {e}", flush=True)


def start_tele_command_thread() -> threading.Thread:
    """
    Khởi động Telegram command bot trong daemon thread.
    Gọi hàm này một lần duy nhất khi khởi động hd_order.py.

    Returns:
        Thread đã được khởi động
    """
    thread = threading.Thread(
        target=_run_bot,
        name="TeleCommandBot",
        daemon=True  # Tự dừng khi main thread kết thúc
    )
    thread.start()
    logger.info(f"[TELE CMD] Thread '{thread.name}' đã khởi động (daemon=True)")
    return thread
