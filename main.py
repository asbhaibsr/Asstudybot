import logging, os, asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler)
from db import db
from ai import ask_ai
from utils import is_admin, broadcast_msg, get_news_updates

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

TOKEN      = os.environ.get("BOT_TOKEN", "YOUR_BOT_TOKEN")
OWNER_ID   = int(os.environ.get("OWNER_ID", "123456789"))
UPI_ID     = os.environ.get("UPI_ID", "arsadsaifi8272@ibl")
MINI_APP   = os.environ.get("MINI_APP_URL", "https://YOUR_USERNAME.github.io/studyapp")

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
    for k,v in items.items():
        row.append(InlineKeyboardButton(v, callback_data=f"{prefix}{k}"))
        if len(row)==cols: btns.append(row); row=[]
    if row: btns.append(row)
    return InlineKeyboardMarkup(btns)

def main_kb(premium):
    badge = "💎" if premium else "🆓"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 Study Mini App Kholein", web_app=WebAppInfo(url=MINI_APP))],
        [InlineKeyboardButton("🤖 AI Se Poochho", callback_data="ai"),
         InlineKeyboardButton("❓ Sawal Poochho", callback_data="question")],
        [InlineKeyboardButton("📢 Latest Updates", callback_data="updates"),
         InlineKeyboardButton("📰 Hindi News", callback_data="news")],
        [InlineKeyboardButton(f"{badge} Premium (₹199/mo)", callback_data="premium"),
         InlineKeyboardButton("👤 Profile", callback_data="profile")],
        [InlineKeyboardButton("📊 Progress", callback_data="progress"),
         InlineKeyboardButton("ℹ️ Help", callback_data="help")],
    ])

# ── Start ─────────────────────────────────────────────────────────────────────
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if await db.is_blocked(u.id):
        await update.message.reply_text("❌ Aapko block kar diya gaya hai."); return ConversationHandler.END
    await db.add_user(u.id, u.first_name, u.username)
    ud = await db.get_user(u.id)
    if ud and ud.get("class_type"):
        return await menu(update, ctx)
    await update.message.reply_text(
        f"🙏 *Namaste {u.first_name}!*\n\n"
        "🤖 Main aapka *Study + Sarkari Updates Bot* hoon!\n\n"
        "✅ Free features:\n"
        "• Sabhi subjects padhai\n• Sarkari job/form alerts\n"
        "• Yojana/Result notifications\n• Hindi news\n• AI help\n\n"
        "Pehle apni class batao 👇",
        parse_mode="Markdown", reply_markup=kb(CLASSES,"cl_"))
    return SELECT_CLASS

async def sel_class(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    ctx.user_data["class_type"]=q.data[3:]
    await q.edit_message_text("✅ Class set!\n\nAb subject batao 👇",
        parse_mode="Markdown", reply_markup=kb(COURSES,"co_"))
    return SELECT_COURSE

async def sel_course(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    ctx.user_data["course"]=q.data[3:]
    await q.edit_message_text("✅ Subject set!\n\nAb goal batao — kyun aaye ho? 👇",
        parse_mode="Markdown", reply_markup=kb(GOALS,"go_",1))
    return SELECT_GOAL

async def sel_goal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    await db.update_profile(q.from_user.id, ctx.user_data.get("class_type"),
        ctx.user_data.get("course"), q.data[3:])
    await q.edit_message_text("🎉 *Profile ban gayi!* Main menu se kuch bhi karo 👇",parse_mode="Markdown")
    ctx.user_data["mode"]="question"
    return await _send_menu(q, ctx)

async def menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["mode"]="question"
    return await _send_menu(update, ctx)

async def _send_menu(src, ctx):
    uid = src.effective_user.id if hasattr(src,'effective_user') else src.from_user.id
    prem = await db.is_premium(uid)
    txt = (f"🏠 *Main Menu* {'💎 Premium' if prem else '🆓 Free'}\n\n"
           "Kya karna chahte ho?\n\n"
           "📱 *Study App* – Sabhi subjects\n"
           "🤖 *AI* – Kuch bhi poochho\n"
           "📢 *Updates* – Sarkari forms/jobs/results\n"
           "📰 *News* – Hindi samachar")
    mk = main_kb(prem)
    if hasattr(src,'message') and src.message:
        await src.message.reply_text(txt, parse_mode="Markdown", reply_markup=mk)
    elif hasattr(src,'edit_message_text'):
        await src.edit_message_text(txt, parse_mode="Markdown", reply_markup=mk)
    else:
        await ctx.bot.send_message(uid, txt, parse_mode="Markdown", reply_markup=mk)
    return MENU

# ── AI / Question handlers ────────────────────────────────────────────────────
async def ai_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    uid=q.from_user.id; prem=await db.is_premium(uid); used=await db.get_usage(uid,"ai")
    if not prem and used>=5:
        return await _limit_msg(q,"AI",5)
    rem="∞" if prem else str(5-used)
    await q.edit_message_text(
        f"🤖 *AI Mode ON!*\nAaj ke AI messages: *{rem}* bache\n\n"
        "Kuch bhi poochho – padhai, career, sarkari kaam!\n_/menu – wapas_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    ctx.user_data["mode"]="ai"; return CHATTING

async def question_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    uid=q.from_user.id; prem=await db.is_premium(uid); used=await db.get_usage(uid,"q")
    if not prem and used>=10:
        return await _limit_msg(q,"Sawal",10)
    rem="∞" if prem else str(10-used)
    await q.edit_message_text(
        f"❓ *Sawal Mode*\nAaj ke sawal: *{rem}* bache\n\nApna sawal type karo!\n_/menu – wapas_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    ctx.user_data["mode"]="question"; return CHATTING

async def _limit_msg(q, what, lim):
    await q.edit_message_text(
        f"⚠️ *{what} limit khatam!*\nFree mein {lim}/din.\n\n"
        "💎 *Premium lo ₹199/month – unlimited!*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💎 Premium Lo",callback_data="premium")],
            [InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    return MENU

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id
    if await db.is_blocked(uid): return
    txt=update.message.text
    if txt.startswith("/"): return
    mode=ctx.user_data.get("mode","question")
    if mode=="screenshot":
        return await handle_screenshot(update, ctx)
    prem=await db.is_premium(uid); ud=await db.get_user(uid)
    if mode=="ai":
        used=await db.get_usage(uid,"ai")
        if not prem and used>=5:
            await update.message.reply_text("⚠️ AI limit khatam! /menu pe jao premium lo."); return
        await update.message.reply_text("🤖 Soch raha hoon...")
        resp=await ask_ai(txt, ud, "ai")
        await db.inc_usage(uid,"ai")
    else:
        used=await db.get_usage(uid,"q")
        if not prem and used>=10:
            await update.message.reply_text("⚠️ Sawal limit khatam! /menu pe jao."); return
        await update.message.reply_text("🔍 Jawab dhundh raha hoon...")
        resp=await ask_ai(txt, ud, "study")
        await db.inc_usage(uid,"q")
    await db.save_q(uid, txt, resp)
    await update.message.reply_text(resp, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👍 Help mila",callback_data="fb_good"),
             InlineKeyboardButton("👎 Aur better chahiye",callback_data="fb_bad")],
            [InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    return CHATTING

# ── Updates (Jobs/Forms/Results/Yojana) ──────────────────────────────────────
async def show_updates(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    await q.edit_message_text("⏳ Latest updates la raha hoon...", parse_mode="Markdown")
    updates = await get_news_updates("sarkari naukri form result yojana 2025")
    if not updates:
        updates = "⚠️ Abhi updates nahi mili. Thodi der mein dobara try karo."
    await q.edit_message_text(
        f"📢 *Latest Sarkari Updates*\n\n{updates}",
        parse_mode="Markdown", disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh",callback_data="updates"),
             InlineKeyboardButton("💼 Jobs",callback_data="upd_jobs")],
            [InlineKeyboardButton("📋 Forms",callback_data="upd_forms"),
             InlineKeyboardButton("📊 Results",callback_data="upd_results")],
            [InlineKeyboardButton("🏛️ Yojana",callback_data="upd_yojana"),
             InlineKeyboardButton("🪪 Admit Card",callback_data="upd_admit")],
            [InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    return MENU

async def show_category_updates(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    cat=q.data.replace("upd_","")
    queries={"jobs":"sarkari naukri recruitment 2025","forms":"online form apply 2025 government",
             "results":"board exam result 2025","yojana":"government yojana scheme 2025 India",
             "admit":"admit card hall ticket 2025"}
    labels={"jobs":"💼 Sarkari Naukri","forms":"📋 Online Forms","results":"📊 Exam Results",
            "yojana":"🏛️ Sarkari Yojana","admit":"🪪 Admit Cards"}
    await q.edit_message_text(f"⏳ {labels.get(cat,'Updates')} la raha hoon...")
    updates=await get_news_updates(queries.get(cat,"sarkari 2025"))
    await q.edit_message_text(
        f"*{labels.get(cat,'Updates')}*\n\n{updates}",
        parse_mode="Markdown", disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh",callback_data=q.data)],
            [InlineKeyboardButton("🔙 Wapas Updates",callback_data="updates")]]))
    return MENU

async def show_news(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    await q.edit_message_text("📰 Hindi news la raha hoon...")
    news=await get_news_updates("aaj ki taza khabar hindi samachar India")
    await q.edit_message_text(
        f"📰 *Aaj Ki Taza Khabar*\n\n{news}",
        parse_mode="Markdown", disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh",callback_data="news"),
             InlineKeyboardButton("🏛️ Rajniti",callback_data="news_pol")],
            [InlineKeyboardButton("🏏 Sports",callback_data="news_sport"),
             InlineKeyboardButton("💼 Business",callback_data="news_biz")],
            [InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    return MENU

async def show_news_cat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    cat=q.data.replace("news_","")
    qmap={"pol":"India rajniti news aaj","sport":"cricket India sports news","biz":"India business economy news"}
    lmap={"pol":"🏛️ Rajniti","sport":"🏏 Sports","biz":"💼 Business"}
    await q.edit_message_text(f"⏳ {lmap.get(cat,'News')} la raha hoon...")
    news=await get_news_updates(qmap.get(cat,"India news"))
    await q.edit_message_text(
        f"*{lmap.get(cat,'News')}*\n\n{news}",
        parse_mode="Markdown", disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh",callback_data=q.data)],
            [InlineKeyboardButton("🔙 Wapas News",callback_data="news")]]))
    return MENU

# ── Premium ───────────────────────────────────────────────────────────────────
async def premium_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    await q.edit_message_text(
        "💎 *Premium Plan – ₹199/month*\n\n"
        "✅ Unlimited sawal\n✅ Unlimited AI\n✅ Unlimited news/updates\n"
        "✅ Sabhi subjects\n✅ Priority support\n\n"
        "━━━━━━━━━━━━━━━\n"
        f"💳 UPI ID: `{UPI_ID}`\n"
        "💰 Amount: ₹199\n"
        "━━━━━━━━━━━━━━━\n\n"
        "1️⃣ ₹199 UPI pe bhejo\n"
        "2️⃣ Screenshot lo\n"
        "3️⃣ Neeche button dabao\n\n"
        "⚡ 1-2 ghante mein activate!",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Maine Pay Kar Diya – Screenshot Bhejo",callback_data="prem_paid")],
            [InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    return MENU

async def prem_paid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    await q.edit_message_text(
        "📸 *Screenshot Bhejo Is Chat Mein!*\n\n"
        "Owner verify karega aur 1-2 ghante mein activate karega.\n"
        "Activate hone pe notification aayegi! 🔔",
        parse_mode="Markdown")
    ctx.user_data["mode"]="screenshot"; return WAIT_SS

async def handle_screenshot(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id; u=update.effective_user
    caption=(f"💳 *New Premium Request!*\n👤 {u.first_name}\n🆔 `{uid}`\n"
             f"@{u.username or 'N/A'}\n\n`/addpremium {uid}` – approve\n`/removepremium {uid}` – reject")
    try:
        if update.message.photo:
            await ctx.bot.forward_message(OWNER_ID, update.message.chat_id, update.message.message_id)
        await ctx.bot.send_message(OWNER_ID, caption, parse_mode="Markdown")
    except: pass
    await update.message.reply_text("✅ Request bhej di! 1-2 ghante mein activate hoga. 🔔")
    ctx.user_data["mode"]="question"; return MENU

# ── Profile / Progress ────────────────────────────────────────────────────────
async def profile(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    uid=q.from_user.id; ud=await db.get_user(uid); prem=await db.is_premium(uid)
    cl=CLASSES.get(ud.get("class_type",""),"N/A") if ud else "N/A"
    co=COURSES.get(ud.get("course",""),"N/A") if ud else "N/A"
    go=GOALS.get(ud.get("goal",""),"N/A") if ud else "N/A"
    qa=await db.get_usage(uid,"q"); aa=await db.get_usage(uid,"ai")
    tq=ud.get("total_q",0) if ud else 0
    await q.edit_message_text(
        f"👤 *Meri Profile*\n\n📚 Class: {cl}\n📖 Subject: {co}\n🎯 Goal: {go}\n"
        f"💎 Plan: {'Premium ✨' if prem else 'Free'}\n\n"
        f"📊 *Aaj:*\n❓ Sawal: {qa}/{'∞' if prem else '10'}\n"
        f"🤖 AI: {aa}/{'∞' if prem else '5'}\n📈 Total Sawal: {tq}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✏️ Profile Update",callback_data="update_profile")],
            [InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    return MENU

async def progress(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    uid=q.from_user.id; ud=await db.get_user(uid)
    t=ud.get("total_q",0) if ud else 0
    lv=("🌱 Beginner" if t<50 else "⭐ Intermediate" if t<150 else "🔥 Advanced" if t<300 else "🏆 Expert")
    nx=(50 if t<50 else 150 if t<150 else 300 if t<300 else "MAX")
    await q.edit_message_text(
        f"📊 *Meri Progress*\n\n🏅 Level: {lv}\n❓ Total Sawal: {t}\n"
        f"🎯 Next Level: {nx} sawal\n\n*Levels:*\n🌱 0+ | ⭐ 50+ | 🔥 150+ | 🏆 300+",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    return MENU

async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    await q.edit_message_text(
        "ℹ️ *Help & Commands*\n\n"
        "/start – Shuru karo\n/menu – Main menu\n\n"
        "*Free Plan:*\n• 10 sawal/din\n• 5 AI/din\n• News & Updates unlimited\n• Study App\n\n"
        "*Premium ₹199/mo:*\n• Sab unlimited\n\n"
        "📢 Updates: Sarkari jobs, forms, results, yojana sab aata hai!\n"
        "📰 News: Hindi samachar bhi!",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    return MENU

async def back_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    ctx.user_data["mode"]="question"
    return await _send_menu(q, ctx)

async def update_profile(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer()
    await q.edit_message_text("Class dobara select karo:", reply_markup=kb(CLASSES,"cl_"))
    return SELECT_CLASS

# ── Admin Commands ────────────────────────────────────────────────────────────
async def cmd_addpremium(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!=OWNER_ID: return
    if not ctx.args: await update.message.reply_text("Usage: /addpremium <user_id>"); return
    uid=int(ctx.args[0]); days=int(ctx.args[1]) if len(ctx.args)>1 else 30
    await db.set_premium(uid, days)
    try: await ctx.bot.send_message(uid,"🎉 *Premium Activate Ho Gaya!* 1 mahine ke liye.\nUnlimited padhai karo!",parse_mode="Markdown")
    except: pass
    await update.message.reply_text(f"✅ Premium added for {uid} ({days} days)")

async def cmd_removepremium(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!=OWNER_ID: return
    if not ctx.args: await update.message.reply_text("Usage: /removepremium <user_id>"); return
    uid=int(ctx.args[0]); await db.remove_premium(uid)
    try: await ctx.bot.send_message(uid,"ℹ️ Aapka premium plan khatam ho gaya. Renew karne ke liye /menu karo.")
    except: pass
    await update.message.reply_text(f"✅ Premium removed for {uid}")

async def cmd_block(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!=OWNER_ID: return
    if not ctx.args: await update.message.reply_text("Usage: /block <user_id>"); return
    uid=int(ctx.args[0]); await db.block_user(uid)
    try: await ctx.bot.send_message(uid,"❌ Aapko block kar diya gaya hai.")
    except: pass
    await update.message.reply_text(f"✅ Blocked {uid}")

async def cmd_unblock(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!=OWNER_ID: return
    if not ctx.args: await update.message.reply_text("Usage: /unblock <user_id>"); return
    uid=int(ctx.args[0]); await db.unblock_user(uid)
    try: await ctx.bot.send_message(uid,"✅ Aapka block hat gaya! /start karo.")
    except: pass
    await update.message.reply_text(f"✅ Unblocked {uid}")

async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!=OWNER_ID: return
    s=await db.stats()
    await update.message.reply_text(
        f"📊 *Bot Stats*\n\n👥 Total: {s['total']}\n💎 Premium: {s['premium']}\n"
        f"🚫 Blocked: {s['blocked']}\n❓ Total Qs: {s['questions']}\n\n"
        "*Admin Commands:*\n/addpremium <id> [days]\n/removepremium <id>\n"
        "/block <id>\n/unblock <id>\n/broadcast <msg>\n/stats",
        parse_mode="Markdown")

async def cmd_broadcast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!=OWNER_ID: return
    if not ctx.args: await update.message.reply_text("Usage: /broadcast <message>"); return
    msg=" ".join(ctx.args)
    users=await db.all_users()
    sm=await update.message.reply_text(f"📢 Bhej raha hoon... 0/{len(users)}")
    sent,fail=await broadcast_msg(ctx.bot, users, msg, sm)
    await sm.edit_text(f"✅ Done!\n✅ Bheja: {sent}\n❌ Failed: {fail}")

async def post_init(app):
    await db.connect()

def main():
    app=Application.builder().token(TOKEN).post_init(post_init).build()
    ch=ConversationHandler(
        entry_points=[CommandHandler("start",start)],
        states={
            SELECT_CLASS:[CallbackQueryHandler(sel_class,pattern="^cl_")],
            SELECT_COURSE:[CallbackQueryHandler(sel_course,pattern="^co_")],
            SELECT_GOAL:[CallbackQueryHandler(sel_goal,pattern="^go_")],
            MENU:[
                CallbackQueryHandler(ai_handler,pattern="^ai$"),
                CallbackQueryHandler(question_handler,pattern="^question$"),
                CallbackQueryHandler(show_updates,pattern="^updates$"),
                CallbackQueryHandler(show_category_updates,pattern="^upd_"),
                CallbackQueryHandler(show_news,pattern="^news$"),
                CallbackQueryHandler(show_news_cat,pattern="^news_"),
                CallbackQueryHandler(premium_info,pattern="^premium$"),
                CallbackQueryHandler(prem_paid,pattern="^prem_paid$"),
                CallbackQueryHandler(profile,pattern="^profile$"),
                CallbackQueryHandler(progress,pattern="^progress$"),
                CallbackQueryHandler(help_cmd,pattern="^help$"),
                CallbackQueryHandler(back_menu,pattern="^back_menu$"),
                CallbackQueryHandler(update_profile,pattern="^update_profile$"),
                CallbackQueryHandler(lambda u,c: MENU,pattern="^fb_"),
                MessageHandler(filters.TEXT&~filters.COMMAND,handle_text),
            ],
            CHATTING:[
                MessageHandler(filters.TEXT&~filters.COMMAND,handle_text),
                MessageHandler(filters.PHOTO,handle_screenshot),
                CallbackQueryHandler(back_menu,pattern="^back_menu$"),
                CallbackQueryHandler(lambda u,c: MENU,pattern="^fb_"),
            ],
            WAIT_SS:[
                MessageHandler(filters.PHOTO,handle_screenshot),
                MessageHandler(filters.TEXT&~filters.COMMAND,handle_screenshot),
                CallbackQueryHandler(back_menu,pattern="^back_menu$"),
            ],
        },
        fallbacks=[CommandHandler("menu",menu),CommandHandler("start",start)],
        per_message=False,
    )
    app.add_handler(ch)
    for cmd,fn in [("menu",menu),("addpremium",cmd_addpremium),("removepremium",cmd_removepremium),
                   ("block",cmd_block),("unblock",cmd_unblock),("stats",cmd_stats),("broadcast",cmd_broadcast)]:
        app.add_handler(CommandHandler(cmd,fn))
    print("🚀 Bot chalu hai!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__=="__main__":
    main()
