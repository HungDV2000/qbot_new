import asyncio
import concurrent.futures
from telegram import Bot
from telegram.constants import ParseMode
import cst
import time


async def send_telegram_message(chat_id, text, is_html, show_web_preview):
    """
    Mỗi lần gửi tạo Bot mới + async with — tránh 'Event loop is closed'
    khi gọi send_tele nhiều lần trong cùng một scan (asyncio.run đóng loop cũ).
    """
    try:
        async with Bot(token=cst.bot_token) as bot:
            if is_html:
                await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    parse_mode=ParseMode.HTML,
                    disable_web_page_preview=not show_web_preview,
                )
            else:
                await bot.send_message(chat_id=chat_id, text=text)
        print("Message sent successfully")
    except Exception as e:
        print(f"Error sending message: {e}")


def send(chat_id, text, is_html, show_web_preview):
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(send_telegram_message(chat_id, text, is_html, show_web_preview))
    else:
        # Đã có event loop (vd. tele_command) → chạy asyncio.run trong thread riêng
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            pool.submit(
                asyncio.run,
                send_telegram_message(chat_id, text, is_html, show_web_preview),
            ).result()
    




def format_telegram_message(msg, is_html):
    """
    Thêm prefix_channel vào đầu message nếu có
    """
    if cst.prefix_channel and cst.prefix_channel.strip():
        prefix = cst.prefix_channel.strip()
        # Nếu message đã có HTML tags hoặc emoji, thêm prefix vào đầu với HTML format
        if is_html and (msg.startswith('<b>') or msg.startswith('✅') or msg.startswith('🛑') or msg.startswith('🚨') or msg.startswith('⚠️')):
            return f"<b>[{prefix}]</b>\n\n{msg}"
        elif is_html:
            return f"<b>[{prefix}]</b>\n\n{msg}"
        else:
            return f"[{prefix}]\n\n{msg}"
    return msg

# ══════════════════════════════════════════════════════════════════════════════
# CHỐNG TIN TRÙNG — có THỜI HẠN (trước đây nhớ vĩnh viễn)
#
# Bản cũ dùng `sent_messages_all = set()` và KHÔNG bao giờ xoá:
#   1) Rò rỉ bộ nhớ — bot chạy 24/7, mỗi tin gửi đi nằm lại trong RAM mãi
#      (~4 MB/tháng mỗi tiến trình; nhân 9 bot × N tài khoản là đáng kể).
#   2) send_tele_with_limit_per_hour bị sai nghĩa: tin trùng nội dung chỉ gửi
#      được ĐÚNG 1 LẦN mãi mãi, thay vì "giới hạn mỗi giờ" như tên gọi.
#
# Nay: nhớ kèm thời điểm, TỰ QUÊN sau _RECENT_TTL giây → hết rò rỉ, đúng nghĩa.
# ══════════════════════════════════════════════════════════════════════════════
_RECENT_TTL = 3600          # nhớ tin trong 1 giờ
_MAX_TRACKED = 5000         # trần an toàn, tránh phình khi tin đến dồn dập

_recent_messages = {}       # {nội_dung_tin: thời_điểm_gửi}
sent_messages = {}          # {user_id: {'count', 'last_sent_time'}} — rate limit theo giờ


def _prune_recent(now=None):
    """Xoá tin đã quá hạn (và cắt bớt nếu quá đông) — giữ bộ nhớ ổn định."""
    now = now or time.time()
    for m in [m for m, ts in _recent_messages.items() if now - ts > _RECENT_TTL]:
        _recent_messages.pop(m, None)
    if len(_recent_messages) > _MAX_TRACKED:              # cũ nhất bị loại trước
        for m, _ in sorted(_recent_messages.items(), key=lambda kv: kv[1])[
                :len(_recent_messages) - _MAX_TRACKED]:
            _recent_messages.pop(m, None)
    for uid in [u for u, i in sent_messages.items()
                if now - i.get('last_sent_time', 0) > _RECENT_TTL * 2]:
        sent_messages.pop(uid, None)


def send_tele(msg, chat_id, is_html, show_web_preview):
    """Gửi tin ngay, KHÔNG chặn trùng."""
    print(f"msg======================={msg}")
    # Cố ý KHÔNG ghi vào _recent_messages: hàm này không dùng tới danh sách đó,
    # mà ghi vào sẽ khiến send_tele_with_limit_per_hour nuốt oan tin trùng nội dung.
    formatted_msg = format_telegram_message(msg, is_html)
    send(str(chat_id), formatted_msg, is_html, show_web_preview)


def send_tele_with_limit_per_hour(msg, chat_id, is_html, show_web_preview, count_mess_per_hour):
    """
    Gửi tin có giới hạn: cùng nội dung chỉ gửi lại sau 1 giờ, và mỗi nhóm tin
    (theo dòng đầu) tối đa `count_mess_per_hour` lần trong 1 giờ.
    """
    print(f"msg======================={msg}")
    now = time.time()
    _prune_recent(now)

    last = _recent_messages.get(msg)
    if last is not None and now - last < _RECENT_TTL:
        print(f"--> Same mess (đã gửi {int(now - last)}s trước, chờ hết 1 giờ)")
        return

    user_id = msg.split('\n', 1)[0]
    current_time = int(now)

    if user_id not in sent_messages:
        sent_messages[user_id] = {'count': 1, 'last_sent_time': current_time}
    else:
        info = sent_messages[user_id]
        if info['count'] >= count_mess_per_hour and current_time - info['last_sent_time'] < 3600:
            print(f"--> Vượt giới hạn {count_mess_per_hour} tin/giờ cho '{user_id}'")
            return
        info['count'] = 1 if current_time - info['last_sent_time'] >= 3600 else info['count'] + 1
        info['last_sent_time'] = current_time

    _recent_messages[msg] = now
    formatted_msg = format_telegram_message(msg, is_html)
    send(str(chat_id), formatted_msg, is_html, show_web_preview)
