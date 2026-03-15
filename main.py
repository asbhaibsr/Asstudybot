import logging, os, asyncio, threading
from flask import Flask, send_from_directory, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler)
from db import db
from ai import ask_ai, get_updates_text, get_news_text

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════
# ⚠️  SIRF YE VALUES BADLO — BAAKI SAB READY HAI  ⚠️
# ══════════════════════════════════════════════════════════════
TOKEN    = os.environ.get("BOT_TOKEN",  "YOUR_BOT_TOKEN_HERE")
OWNER_ID = int(os.environ.get("OWNER_ID", "123456789"))
UPI_ID   = os.environ.get("UPI_ID",    "arsadsaifi8272@ibl")
PORT     = int(os.environ.get("PORT",   "8080"))

# Tumhara Koyeb URL — pehle se set hai!
KOYEB_URL = os.environ.get(
    "KOYEB_URL",
    "https://chilly-ardath-arsadsaifi784-74d0cd5c.koyeb.app"
)
MINI_APP = f"{KOYEB_URL}/app"
# ══════════════════════════════════════════════════════════════

flask_app = Flask(__name__, static_folder="static")

@flask_app.route("/")
def home():
    return jsonify({"status": "ok", "bot": "IndiaStudyAI_Bot", "app": "/app"})

@flask_app.route("/health")
def health():
    return jsonify({"status": "ok"}), 200

@flask_app.route("/app")
@flask_app.route("/app/")
def mini_app():
    return send_from_directory("static", "index.html")

@flask_app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory("static", filename)

def run_flask():
    log.info(f"Flask on :{PORT} | App: {MINI_APP}")
    flask_app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)

SELECT_CLASS, SELECT_COURSE, SELECT_GOAL, MENU, CHATTING, WAIT_SS = range(6)

CLASSES = {
    "c1_5":"📚 Class 1-5","c6_8":"📖 Class 6-8","c9_10":"🎓 Class 9-10",
    "c11_12":"🏫 Class 11-12","college":"🎓 College","adult":"👨‍💼 Adult"
}
COURSES = {
    "math":"➕ Maths","science":"🔬 Science","hindi":"🇮🇳 Hindi",
    "english":"🔤 English","sst":"🌍 SST/History","computer":"💻 Computer","gk":"🧠 GK"
}
GOALS = {
    "exam":"📝 Exam Prep","skill":"💡 Skill Seekhna","homework":"📋 Homework Help",
    "job":"💼 Sarkari Naukri","hobby":"🎨 Hobby"
}

def kb(items, prefix, cols=2):
    btns, row = [], []
    for k, v in items.items():
        row.append(InlineKeyboardButton(v, callback_data=f"{prefix}{k}"))
        if len(row) == cols: btns.append(row); row = []
    if row: btns.append(row)
    return InlineKeyboardMarkup(btns)

def main_kb(premium):
    badge = "💎" if premium else "🆓"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 Study Mini App Kholein", web_app=WebAppInfo(url=MINI_APP))],
        [InlineKeyboardButton("🤖 AI Tutor", callback_data="ai"),
         InlineKeyboardButton("❓ Study Sawal", callback_data="question")],
        [InlineKeyboardButton("📢 Sarkari Updates", callback_data="updates"),
         InlineKeyboardButton("📰 Hindi News", callback_data="news")],
        [InlineKeyboardButton(f"{badge} Premium – ₹199/mo", callback_data="premium"),
         InlineKeyboardButton("👤 Profile", callback_data="profile")],
        [InlineKeyboardButton("📊 Progress", callback_data="progress"),
         InlineKeyboardButton("ℹ️ Help", callback_data="help")],
    ])

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if await db.is_blocked(u.id):
        await update.message.reply_text("❌ Aapko block kar diya gaya hai.")
        return ConversationHandler.END
    await db.add_user(u.id, u.first_name, u.username)
    ud = await db.get_user(u.id)
    if ud and ud.get("class_type"):
        return await _send_menu(update, ctx)
    await update.message.reply_text(
        f"🙏 *Namaste {u.first_name}!*\n\n"
        "🤖 Main hoon *@IndiaStudyAI\\_Bot*!\n\n"
        "✅ *FREE mein milega:*\n"
        "• 📚 Sabhi subjects – Wikipedia + AI se\n"
        "• 🤖 AI Tutor – 10 sawaal/din\n"
        "• 🎯 Daily Quiz – Live API se\n"
        "• 📢 Sarkari Jobs/Forms/Results\n"
        "• 📰 Hindi News\n"
        "• ⏱️ Pomodoro Timer\n"
        "• 🃏 Flashcards\n\n"
        "Pehle apni *class* batao 👇",
        parse_mode="Markdown", reply_markup=kb(CLASSES, "cl_"))
    return SELECT_CLASS

async def sel_class(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    ctx.user_data["class_type"] = q.data[3:]
    await q.edit_message_text("✅ Class set!\nAb *subject* batao 👇",
        parse_mode="Markdown", reply_markup=kb(COURSES, "co_"))
    return SELECT_COURSE

async def sel_course(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    ctx.user_data["course"] = q.data[3:]
    await q.edit_message_text("✅ Subject set!\nAb *goal* batao 👇",
        parse_mode="Markdown", reply_markup=kb(GOALS, "go_", 1))
    return SELECT_GOAL

async def sel_goal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await db.update_profile(q.from_user.id,
        ctx.user_data.get("class_type"), ctx.user_data.get("course"), q.data[3:])
    await q.edit_message_text("🎉 *Profile ready!* Menu se shuru karo 👇", parse_mode="Markdown")
    ctx.user_data["mode"] = "question"
    return await _send_menu(q, ctx)

async def menu_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["mode"] = "question"
    return await _send_menu(update, ctx)

async def _send_menu(src, ctx):
    uid = src.effective_user.id if hasattr(src,'effective_user') else src.from_user.id
    prem = await db.is_premium(uid)
    txt = (f"🏠 *Main Menu*  {'💎 Premium' if prem else '🆓 Free'}\n\n"
           f"📱 *Study App* → {MINI_APP}\n"
           "🤖 *AI Tutor* — Study sawaal poochho\n"
           "📢 *Updates* — Sarkari jobs/forms/results\n"
           "📰 *News* — Aaj ki Hindi khabar")
    mk = main_kb(prem)
    if hasattr(src,'message') and src.message:
        await src.message.reply_text(txt, parse_mode="Markdown", reply_markup=mk)
    elif hasattr(src,'edit_message_text'):
        await src.edit_message_text(txt, parse_mode="Markdown", reply_markup=mk)
    else:
        await ctx.bot.send_message(uid, txt, parse_mode="Markdown", reply_markup=mk)
    return MENU

async def ai_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    uid = q.from_user.id
    prem = await db.is_premium(uid); used = await db.get_usage(uid, "ai")
    if not prem and used >= 10:
        return await _limit_msg(q, "AI Tutor", 10)
    rem = "∞" if prem else str(10 - used)
    await q.edit_message_text(
        f"🤖 *AI Tutor Mode*\nAaj ke bache: *{rem}* sawaal\n\n"
        "Sirf study topics — Math, Science, GK, Career!\n_/menu — wapas_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="back_menu")]]))
    ctx.user_data["mode"] = "ai"
    return CHATTING

async def question_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    uid = q.from_user.id
    prem = await db.is_premium(uid); used = await db.get_usage(uid, "q")
    if not prem and used >= 10:
        return await _limit_msg(q, "Sawal", 10)
    rem = "∞" if prem else str(10 - used)
    await q.edit_message_text(
        f"❓ *Study Sawal Mode*\nAaj ke bache: *{rem}*\n\nSawal type karo!\n_/menu — wapas_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="back_menu")]]))
    ctx.user_data["mode"] = "question"
    return CHATTING

async def _limit_msg(q, what, lim):
    await q.edit_message_text(
        f"⚠️ *{what} limit khatam!*\nFree mein {lim}/din.\n\n💎 *₹199/month — unlimited!*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💎 Premium Lo", callback_data="premium")],
            [InlineKeyboardButton("🔙 Menu", callback_data="back_menu")]]))
    return MENU

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if await db.is_blocked(uid): return
    txt = update.message.text
    if txt.startswith("/"): return
    mode = ctx.user_data.get("mode", "question")
    if mode == "screenshot":
        return await handle_screenshot(update, ctx)
    prem = await db.is_premium(uid)
    ud   = await db.get_user(uid)
    kind = "ai" if mode == "ai" else "q"
    used = await db.get_usage(uid, kind)
    if not prem and used >= 10:
        await update.message.reply_text("⚠️ Limit khatam! /menu pe jao premium lo.")
        return
    wait = await update.message.reply_text(
        "🤖 Soch raha hoon..." if mode=="ai" else "🔍 Jawab dhundh raha hoon...")
    resp = await ask_ai(txt, ud, mode)
    await db.inc_usage(uid, kind)
    await db.save_q(uid, txt, resp)
    await wait.delete()
    await update.message.reply_text(resp, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👍 Helpful", callback_data="fb_good"),
             InlineKeyboardButton("👎 Aur better chahiye", callback_data="fb_bad")],
            [InlineKeyboardButton("🔙 Menu", callback_data="back_menu")]]))
    return CHATTING

async def show_updates(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await q.edit_message_text("⏳ Sarkari updates la raha hoon...")
    txt = await get_updates_text("all")
    await q.edit_message_text(f"📢 *Latest Sarkari Updates*\n\n{txt}",
        parse_mode="Markdown", disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💼 Jobs", callback_data="upd_jobs"),
             InlineKeyboardButton("📋 Forms", callback_data="upd_forms")],
            [InlineKeyboardButton("📊 Results", callback_data="upd_results"),
             InlineKeyboardButton("🏛️ Yojana", callback_data="upd_yojana")],
            [InlineKeyboardButton("🪪 Admit Card", callback_data="upd_admit"),
             InlineKeyboardButton("🎓 Scholarship", callback_data="upd_scholar")],
            [InlineKeyboardButton("🔄 Refresh", callback_data="updates"),
             InlineKeyboardButton("🔙 Menu", callback_data="back_menu")]]))
    return MENU

async def show_upd_cat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    cat = q.data.replace("upd_", "")
    labels = {"jobs":"💼 Jobs","forms":"📋 Forms","results":"📊 Results",
              "yojana":"🏛️ Yojana","admit":"🪪 Admit Card","scholar":"🎓 Scholarship"}
    lbl = labels.get(cat, "Updates")
    await q.edit_message_text(f"⏳ {lbl} la raha hoon...")
    txt = await get_updates_text(cat)
    await q.edit_message_text(f"*{lbl}*\n\n{txt}", parse_mode="Markdown",
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh", callback_data=q.data)],
            [InlineKeyboardButton("🔙 Wapas", callback_data="updates")]]))
    return MENU

async def show_news(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await q.edit_message_text("📰 News la raha hoon...")
    txt = await get_news_text("india")
    await q.edit_message_text(f"📰 *Aaj Ki Khabar*\n\n{txt}",
        parse_mode="Markdown", disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏛️ Rajniti", callback_data="nws_pol"),
             InlineKeyboardButton("🏏 Sports", callback_data="nws_sport")],
            [InlineKeyboardButton("💼 Business", callback_data="nws_biz"),
             InlineKeyboardButton("📚 Education", callback_data="nws_edu")],
            [InlineKeyboardButton("🔄 Refresh", callback_data="news"),
             InlineKeyboardButton("🔙 Menu", callback_data="back_menu")]]))
    return MENU

async def show_news_cat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    cat = q.data.replace("nws_", "")
    labels = {"pol":"🏛️ Rajniti","sport":"🏏 Sports","biz":"💼 Business","edu":"📚 Education"}
    lbl = labels.get(cat, "News")
    await q.edit_message_text(f"⏳ {lbl} la raha hoon...")
    txt = await get_news_text(cat)
    await q.edit_message_text(f"*{lbl}*\n\n{txt}", parse_mode="Markdown",
        disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh", callback_data=q.data)],
            [InlineKeyboardButton("🔙 News", callback_data="news")]]))
    return MENU

async def premium_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await q.edit_message_text(
        "💎 *Premium Plan – ₹199/month*\n\n"
        "✅ Unlimited AI Tutor\n✅ Unlimited sawaal\n"
        "✅ Unlimited quiz & flashcards\n✅ Priority support\n\n"
        f"━━━━━━━━━━\n💳 UPI: `{UPI_ID}`\n💰 ₹199\n━━━━━━━━━━\n\n"
        "1️⃣ UPI pe ₹199 bhejo\n2️⃣ Screenshot lo\n3️⃣ Neeche button dabao",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Pay kar diya – Screenshot Bhejo", callback_data="prem_paid")],
            [InlineKeyboardButton("🔙 Menu", callback_data="back_menu")]]))
    return MENU

async def prem_paid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await q.edit_message_text(
        "📸 *Screenshot Bhejo Is Chat Mein!*\n\nOwner verify karega, 1-2 ghante mein active hoga! 🔔",
        parse_mode="Markdown")
    ctx.user_data["mode"] = "screenshot"
    return WAIT_SS

async def handle_screenshot(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id; u = update.effective_user
    cap = (f"💳 *Premium Request!*\n👤 {u.first_name}\n🆔 `{uid}`\n"
           f"@{u.username or 'N/A'}\n\n`/addpremium {uid}` – approve karo")
    try:
        if update.message.photo:
            await ctx.bot.forward_message(OWNER_ID, update.message.chat_id, update.message.message_id)
        await ctx.bot.send_message(OWNER_ID, cap, parse_mode="Markdown")
    except Exception as e: log.error(f"Forward error: {e}")
    await update.message.reply_text("✅ Request bhej di! 1-2 ghante mein active hoga. 🔔")
    ctx.user_data["mode"] = "question"
    return MENU

async def profile_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    uid = q.from_user.id; ud = await db.get_user(uid); prem = await db.is_premium(uid)
    cl = CLASSES.get(ud.get("class_type",""),"N/A") if ud else "N/A"
    co = COURSES.get(ud.get("course",""),"N/A") if ud else "N/A"
    go = GOALS.get(ud.get("goal",""),"N/A") if ud else "N/A"
    qa = await db.get_usage(uid,"q"); aa = await db.get_usage(uid,"ai")
    tq = ud.get("total_q",0) if ud else 0
    await q.edit_message_text(
        f"👤 *Meri Profile*\n\n📚 {cl}\n📖 {co}\n🎯 {go}\n"
        f"💎 {'Premium ✨' if prem else 'Free'}\n\n"
        f"📊 *Aaj:*\n❓ Sawaal: {qa}/{'∞' if prem else '10'}\n"
        f"🤖 AI: {aa}/{'∞' if prem else '10'}\n📈 Total: {tq}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✏️ Update Profile", callback_data="update_profile")],
            [InlineKeyboardButton("🔙 Menu", callback_data="back_menu")]]))
    return MENU

async def progress_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    uid = q.from_user.id; ud = await db.get_user(uid)
    t = ud.get("total_q",0) if ud else 0
    lv = ("🌱 Beginner" if t<50 else "⭐ Intermediate" if t<150 else "🔥 Advanced" if t<300 else "🏆 Expert")
    nx = 50 if t<50 else 150 if t<150 else 300 if t<300 else "MAX"
    await q.edit_message_text(
        f"📊 *Progress*\n\n🏅 {lv}\n❓ Total: {t}\n🎯 Next: {nx}\n\n"
        "🌱 0+ | ⭐ 50+ | 🔥 150+ | 🏆 300+",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="back_menu")]]))
    return MENU

async def help_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await q.edit_message_text(
        f"ℹ️ *@IndiaStudyAI\\_Bot Help*\n\n"
        "/start /menu /profile /premium\n\n"
        "*Free:* 10 sawaal/din, 10 AI/din, news unlimited\n"
        f"*Premium ₹199:* Sab unlimited\n\n"
        f"🌐 Web App: {MINI_APP}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu", callback_data="back_menu")]]))
    return MENU

async def back_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    ctx.user_data["mode"] = "question"
    return await _send_menu(q, ctx)

async def update_profile(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await q.edit_message_text("Class dobara select karo:", reply_markup=kb(CLASSES, "cl_"))
    return SELECT_CLASS

async def cmd_addpremium(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not ctx.args: await update.message.reply_text("Usage: /addpremium <id> [days]"); return
    uid = int(ctx.args[0]); days = int(ctx.args[1]) if len(ctx.args)>1 else 30
    await db.set_premium(uid, days)
    try: await ctx.bot.send_message(uid, "🎉 *Premium active!* Unlimited padhai karo!", parse_mode="Markdown")
    except: pass
    await update.message.reply_text(f"✅ Premium: {uid} ({days} days)")

async def cmd_removepremium(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not ctx.args: await update.message.reply_text("Usage: /removepremium <id>"); return
    uid = int(ctx.args[0]); await db.remove_premium(uid)
    try: await ctx.bot.send_message(uid, "ℹ️ Premium khatam. Renew karo /menu se.")
    except: pass
    await update.message.reply_text(f"✅ Removed: {uid}")

async def cmd_block(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not ctx.args: return
    uid = int(ctx.args[0]); await db.block_user(uid)
    try: await ctx.bot.send_message(uid, "❌ Block ho gaye.")
    except: pass
    await update.message.reply_text(f"✅ Blocked {uid}")

async def cmd_unblock(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not ctx.args: return
    uid = int(ctx.args[0]); await db.unblock_user(uid)
    try: await ctx.bot.send_message(uid, "✅ Unblock! /start karo.")
    except: pass
    await update.message.reply_text(f"✅ Unblocked {uid}")

async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    s = await db.stats()
    await update.message.reply_text(
        f"📊 *Bot Stats*\n\n👥 Users: {s['total']}\n💎 Premium: {s['premium']}\n"
        f"🚫 Blocked: {s['blocked']}\n❓ Questions: {s['questions']}\n\n"
        f"🌐 Mini App: {MINI_APP}\n\n"
        "📋 *Admin Commands:*\n/addpremium <id> [days]\n/removepremium <id>\n"
        "/block <id> | /unblock <id>\n/broadcast <msg>",
        parse_mode="Markdown")

async def cmd_broadcast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not ctx.args: await update.message.reply_text("Usage: /broadcast <msg>"); return
    msg = " ".join(ctx.args); users = await db.all_users()
    sm = await update.message.reply_text(f"📢 Bhej raha hoon... 0/{len(users)}")
    sent = fail = 0
    for i, u in enumerate(users):
        try:
            await ctx.bot.send_message(u["user_id"], f"📢 *Suchna:*\n\n{msg}", parse_mode="Markdown")
            sent += 1
        except: fail += 1
        if (i+1) % 25 == 0:
            try: await sm.edit_text(f"📢 {i+1}/{len(users)}...")
            except: pass
    await sm.edit_text(f"✅ Done!\n✅ Bheja: {sent}\n❌ Failed: {fail}")

async def post_init(app):
    await db.connect()
    log.info(f"✅ Bot ready! Mini App: {MINI_APP}")

def main():
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()
    app = Application.builder().token(TOKEN).post_init(post_init).build()
    ch = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECT_CLASS:  [CallbackQueryHandler(sel_class,  pattern="^cl_")],
            SELECT_COURSE: [CallbackQueryHandler(sel_course, pattern="^co_")],
            SELECT_GOAL:   [CallbackQueryHandler(sel_goal,   pattern="^go_")],
            MENU: [
                CallbackQueryHandler(ai_cb,          pattern="^ai$"),
                CallbackQueryHandler(question_cb,    pattern="^question$"),
                CallbackQueryHandler(show_updates,   pattern="^updates$"),
                CallbackQueryHandler(show_upd_cat,   pattern="^upd_"),
                CallbackQueryHandler(show_news,      pattern="^news$"),
                CallbackQueryHandler(show_news_cat,  pattern="^nws_"),
                CallbackQueryHandler(premium_info,   pattern="^premium$"),
                CallbackQueryHandler(prem_paid,      pattern="^prem_paid$"),
                CallbackQueryHandler(profile_cb,     pattern="^profile$"),
                CallbackQueryHandler(progress_cb,    pattern="^progress$"),
                CallbackQueryHandler(help_cb,        pattern="^help$"),
                CallbackQueryHandler(back_menu,      pattern="^back_menu$"),
                CallbackQueryHandler(update_profile, pattern="^update_profile$"),
                CallbackQueryHandler(lambda u,c: MENU, pattern="^fb_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text),
            ],
            CHATTING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text),
                MessageHandler(filters.PHOTO, handle_screenshot),
                CallbackQueryHandler(back_menu, pattern="^back_menu$"),
                CallbackQueryHandler(lambda u,c: MENU, pattern="^fb_"),
            ],
            WAIT_SS: [
                MessageHandler(filters.PHOTO, handle_screenshot),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_screenshot),
                CallbackQueryHandler(back_menu, pattern="^back_menu$"),
            ],
        },
        fallbacks=[CommandHandler("menu", menu_cmd), CommandHandler("start", start)],
        per_message=False,
    )
    app.add_handler(ch)
    for cmd, fn in [
        ("menu", menu_cmd), ("addpremium", cmd_addpremium),
        ("removepremium", cmd_removepremium), ("block", cmd_block),
        ("unblock", cmd_unblock), ("stats", cmd_stats), ("broadcast", cmd_broadcast)
    ]:
        app.add_handler(CommandHandler(cmd, fn))
    log.info("🚀 Bot polling shuru!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
