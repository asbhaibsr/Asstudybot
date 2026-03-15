import os
from ai import get_news_updates  # re-export

OWNER_ID = int(os.environ.get("OWNER_ID","123456789"))

async def is_admin(uid: int) -> bool:
    return uid == OWNER_ID

async def broadcast_msg(bot, users, message, status_msg=None):
    sent = fail = 0
    for i, u in enumerate(users):
        try:
            await bot.send_message(u["user_id"],
                f"📢 *Bot se Suchna:*\n\n{message}", parse_mode="Markdown")
            sent += 1
        except:
            fail += 1
        if status_msg and (i+1) % 25 == 0:
            try: await status_msg.edit_text(f"📢 Bhej raha hoon... {i+1}/{len(users)}")
            except: pass
    return sent, fail
