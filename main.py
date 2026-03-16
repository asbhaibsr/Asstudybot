import logging, os, threading, random, asyncio
from datetime import datetime, date, timedelta
from flask import Flask, send_from_directory, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes, ConversationHandler)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from db import db
from ai import (ask_ai, ask_ai_simple, fetch_updates, fetch_news,
    get_morning_message, generate_pdf, image_to_text,
    generate_question_paper, generate_mind_map, career_counsel,
    generate_study_plan, get_current_affairs, build_vocabulary,
    summarize_topic)

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)
log = logging.getLogger(__name__)

TOKEN     = os.environ.get("BOT_TOKEN","YOUR_BOT_TOKEN")
OWNER_ID  = int(os.environ.get("OWNER_ID","123456789"))
UPI_ID    = os.environ.get("UPI_ID","arsadsaifi8272@ibl")
PORT      = int(os.environ.get("PORT","8080"))
KOYEB_URL = os.environ.get("KOYEB_URL","https://your-app.koyeb.app")
MINI_APP  = f"{KOYEB_URL}/app"
BOT_LINK  = "https://t.me/IndiaStudyAI_Bot"

# ── Flask (serve mini app) ────────────────────────────────────────────────────
flask_app = Flask(__name__, static_folder="app")

@flask_app.route("/")
def home(): return jsonify({"status":"ok","bot":"IndiaStudyAI"})

@flask_app.route("/health")
def health(): return jsonify({"status":"ok"}), 200

@flask_app.route("/app")
@flask_app.route("/app/")
def mini_app(): return send_from_directory("app","index.html")

@flask_app.route("/app/<path:fname>")
def mini_app_files(fname): return send_from_directory("app", fname)

def run_flask():
    flask_app.run(host="0.0.0.0", port=PORT, debug=False, use_reloader=False)

# ── States ─────────────────────────────────────────────────────────────────────
(SELECT_CLASS, SELECT_COURSE, SELECT_GOAL, MENU,
 AI_TUTOR_CLASS, AI_TUTOR_SUBJECT, AI_TUTOR_CHAT,
 CHATTING, WAIT_SS, SET_EXAM, SET_REMINDER, SAVE_NOTE) = range(12)

# ── Data Maps ─────────────────────────────────────────────────────────────────
CLASSES = {
    "c1_5":"📚 Class 1-5","c6_8":"📖 Class 6-8","c9_10":"🎓 Class 9-10",
    "c11_12":"🏫 Class 11-12","college":"🎓 College","adult":"👨‍💼 Adult/Job",
}
COURSES = {
    "math":"➕ Maths","science":"🔬 Science","hindi":"🇮🇳 Hindi",
    "english":"🔤 English","sst":"🌍 History/SST","physics":"⚛️ Physics",
    "chemistry":"🧪 Chemistry","biology":"🧬 Biology",
    "computer":"💻 Computer","gk":"🧠 GK/Current Affairs",
}
GOALS = {
    "exam":"📝 Board/Exam Prep","skill":"💡 Skill Building",
    "homework":"📋 Homework Help","job":"💼 Sarkari Naukri",
    "competitive":"🏆 JEE/NEET/UPSC","hobby":"🎨 Hobby/Interest",
}

# ── Helper: build keyboard ────────────────────────────────────────────────────
def kb(items: dict, prefix: str, cols: int = 2) -> InlineKeyboardMarkup:
    btns, row = [], []
    for k,v in items.items():
        row.append(InlineKeyboardButton(v, callback_data=f"{prefix}{k}"))
        if len(row) == cols: btns.append(row); row = []
    if row: btns.append(row)
    return InlineKeyboardMarkup(btns)

def _setEl(ctx_data, k, v): ctx_data[k] = v

async def _del(msg):
    try: await msg.delete()
    except: pass

# ── MAIN MENU keyboard ────────────────────────────────────────────────────────
def main_kb(premium: bool) -> InlineKeyboardMarkup:
    badge = "💎 Premium" if premium else "🆓 Free"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 Study Mini App", web_app=WebAppInfo(url=MINI_APP))],
        [InlineKeyboardButton("🤖 AI Study Tutor",   callback_data="ai_tutor"),
         InlineKeyboardButton("❓ Quick Sawal",       callback_data="question")],
        [InlineKeyboardButton("📢 Sarkari Updates",  callback_data="updates"),
         InlineKeyboardButton("📰 Hindi News",        callback_data="news")],
        [InlineKeyboardButton("📰 Current Affairs",  callback_data="current_affairs"),
         InlineKeyboardButton("🎯 Daily Challenge",   callback_data="daily_challenge")],
        [InlineKeyboardButton("🏆 Leaderboard",       callback_data="leaderboard"),
         InlineKeyboardButton("📝 Question Paper",    callback_data="qpaper_menu")],
        [InlineKeyboardButton("📊 Study Planner",     callback_data="study_planner"),
         InlineKeyboardButton("🎓 Career Guide",      callback_data="career_guide")],
        [InlineKeyboardButton("🗺️ Mind Map",          callback_data="mind_map_menu"),
         InlineKeyboardButton("📖 Vocabulary",        callback_data="vocab_menu")],
        [InlineKeyboardButton("📷 Image→Text",        callback_data="ocr_mode"),
         InlineKeyboardButton("📄 Resume Banao",      callback_data="resume_builder")],
        [InlineKeyboardButton("📝 Meri Notes",        callback_data="my_notes"),
         InlineKeyboardButton("⏰ Reminder",           callback_data="set_reminder")],
        [InlineKeyboardButton("💬 Chat History",      callback_data="chat_history"),
         InlineKeyboardButton("👥 Refer & Earn",       callback_data="refer")],
        [InlineKeyboardButton(f"{badge} ₹199/mo",     callback_data="premium"),
         InlineKeyboardButton("👤 Profile",            callback_data="profile")],
        [InlineKeyboardButton("🌐 Language",          callback_data="lang_menu"),
         InlineKeyboardButton("⚙️ Settings",           callback_data="settings")],
    ])

# ══════════════════════════════════════════════════════════════════════════════
# /start
# ══════════════════════════════════════════════════════════════════════════════
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    u = update.effective_user
    if await db.is_blocked(u.id):
        await update.message.reply_text("❌ Block ho gaye."); return ConversationHandler.END

    ref_by = None
    if ctx.args and ctx.args[0].startswith("REF"):
        try: ref_by = int(ctx.args[0][3:])
        except: pass

    await db.add_user(u.id, u.first_name, u.username, ref_by=ref_by)

    if ref_by and ref_by != u.id:
        try:
            await ctx.bot.send_message(ref_by,
                f"🎉 *{u.first_name}* ne tera refer link use kiya!\n+100 pts! 🏆",
                parse_mode="Markdown")
        except: pass

    ud = await db.get_user(u.id)
    if ud and ud.get("class_type"):
        return await _send_menu(update, ctx)

    await update.message.reply_text(
        f"🙏 *Namaste {u.first_name}!*\n\n"
        f"🤖 *@IndiaStudyAI\\_Bot* — India ka #1 Free Study Saathi!\n\n"
        f"🎁 *50 Points joining bonus!*\n\n"
        f"✅ *Features:*\n"
        f"• 🤖 AI Tutor (Gemini·Mistral·DeepSeek·Groq+5 Free)\n"
        f"• 📢 Live Sarkari Updates (Scraping+RSS)\n"
        f"• 📰 Hindi News (RSS+Google News)\n"
        f"• 📷 Image→Text (Gemini Vision)\n"
        f"• 📄 Resume·PDF·Question Paper Builder\n"
        f"• 📝 Notes save → PDF download\n"
        f"• 🗺️ Mind Map Generator\n"
        f"• 🎓 Career Counsellor AI\n"
        f"• 📊 Smart Study Planner\n"
        f"• ⏰ Custom Reminders + Streak\n\n"
        f"Pehle *apni class* batao 👇",
        parse_mode="Markdown",
        reply_markup=kb(CLASSES, "cl_"))
    return SELECT_CLASS

# ── Profile setup flow ─────────────────────────────────────────────────────────
async def sel_class(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    ctx.user_data["class_type"] = q.data[3:]
    await q.edit_message_text("✅ Class set!\n\nAb *subject* batao 👇",
        parse_mode="Markdown", reply_markup=kb(COURSES,"co_"))
    return SELECT_COURSE

async def sel_course(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    ctx.user_data["course"] = q.data[3:]
    await q.edit_message_text("✅ Subject set!\n\nAb *lakshya* batao 👇",
        parse_mode="Markdown", reply_markup=kb(GOALS,"go_",1))
    return SELECT_GOAL

async def sel_goal(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await db.update_profile(q.from_user.id,
        ctx.user_data.get("class_type"),
        ctx.user_data.get("course"),
        q.data[3:])
    await q.edit_message_text("🎉 *Profile ready! Chalo padhte hain!*", parse_mode="Markdown")
    ctx.user_data["mode"] = "question"
    return await _send_menu(q, ctx)

async def update_profile(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await _del(q.message)
    await ctx.bot.send_message(q.from_user.id,
        "✏️ *Profile Update*\n\nClass dobara select karo:",
        parse_mode="Markdown", reply_markup=kb(CLASSES,"cl_"))
    return SELECT_CLASS

async def menu_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    ctx.user_data["mode"] = "question"
    return await _send_menu(update, ctx)

async def _send_menu(src, ctx):
    uid  = src.effective_user.id if hasattr(src,'effective_user') else src.from_user.id
    prem = await db.is_premium(uid)
    ud   = await db.get_user(uid)
    pts  = ud.get("points",0) if ud else 0
    strk = ud.get("streak",0) if ud else 0
    strk_txt = f"🔥 *{strk} din streak!*" if strk > 1 else "🌱 Aaj se streak!"
    lang = (ud or {}).get("language","hi")

    # API status bar
    from ai import GEMINI_KEY, MISTRAL_KEY, DEEPSEEK_KEY, GROQ_KEY
    api_icons = []
    if GEMINI_KEY:   api_icons.append("G✅")
    if MISTRAL_KEY:  api_icons.append("M✅")
    if DEEPSEEK_KEY: api_icons.append("D✅")
    if GROQ_KEY:     api_icons.append("Groq✅")
    if not api_icons: api_icons = ["Free AI"]

    txt = (f"🏠 *Main Menu* {'💎' if prem else '🆓'}\n\n"
           f"⭐ *{pts} pts* | {strk_txt}\n"
           f"🤖 AI: {' · '.join(api_icons)}")

    if hasattr(src,'message') and src.message:
        await src.message.reply_text(txt, parse_mode="Markdown", reply_markup=main_kb(prem))
    elif hasattr(src,'edit_message_text'):
        try: await src.edit_message_text(txt, parse_mode="Markdown", reply_markup=main_kb(prem))
        except: await ctx.bot.send_message(uid, txt, parse_mode="Markdown", reply_markup=main_kb(prem))
    else:
        await ctx.bot.send_message(uid, txt, parse_mode="Markdown", reply_markup=main_kb(prem))
    return MENU

# ══════════════════════════════════════════════════════════════════════════════
# AI STUDY TUTOR (3-step: Class → Subject → Chat)
# ══════════════════════════════════════════════════════════════════════════════
async def ai_tutor_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await _del(q.message)
    await ctx.bot.send_message(q.from_user.id,
        "🤖 *AI Study Tutor*\n\nKis class ke liye padhna hai? 👇",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📚 Class 1-5",  callback_data="ait_c1_5"),
             InlineKeyboardButton("📖 Class 6-8",  callback_data="ait_c6_8")],
            [InlineKeyboardButton("🎓 Class 9-10", callback_data="ait_c9_10"),
             InlineKeyboardButton("🏫 Class 11-12",callback_data="ait_c11_12")],
            [InlineKeyboardButton("🎓 College",    callback_data="ait_college"),
             InlineKeyboardButton("👨‍💼 Adult/Job",  callback_data="ait_adult")],
            [InlineKeyboardButton("🔙 Menu",       callback_data="back_menu")]]))
    return AI_TUTOR_CLASS

async def ait_class_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    ctx.user_data["ait_class"] = q.data.replace("ait_","")
    await _del(q.message)
    # Save to user profile too
    await ctx.bot.send_message(q.from_user.id,
        f"✅ *{CLASSES.get(ctx.user_data['ait_class'],'')}*\n\nAb *subject* choose karo 👇",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Maths",      callback_data="ais_math"),
             InlineKeyboardButton("🔬 Science",    callback_data="ais_science")],
            [InlineKeyboardButton("🇮🇳 Hindi",     callback_data="ais_hindi"),
             InlineKeyboardButton("🔤 English",    callback_data="ais_english")],
            [InlineKeyboardButton("⚛️ Physics",    callback_data="ais_physics"),
             InlineKeyboardButton("🧪 Chemistry",  callback_data="ais_chemistry")],
            [InlineKeyboardButton("🧬 Biology",    callback_data="ais_biology"),
             InlineKeyboardButton("🌍 History/SST",callback_data="ais_sst")],
            [InlineKeyboardButton("💻 Computer",   callback_data="ais_computer"),
             InlineKeyboardButton("🧠 GK/Current", callback_data="ais_gk")],
            [InlineKeyboardButton("📚 All Subjects",callback_data="ais_all"),
             InlineKeyboardButton("🔙 Wapas",      callback_data="ai_tutor")]]))
    return AI_TUTOR_SUBJECT

async def ait_subject_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    subj = q.data.replace("ais_","")
    ctx.user_data["ait_subject"] = subj
    uid   = q.from_user.id
    prem  = await db.is_premium(uid)
    used  = await db.get_usage(uid,"ai")
    limit = 999 if prem else 15

    await _del(q.message)
    if not prem and used >= limit:
        await ctx.bot.send_message(uid,
            "⚠️ *AI limit khatam!*\nFree: 15 sawaal/din\n\n💎 Premium lo — Unlimited!",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💎 Premium Lo",callback_data="premium")],
                [InlineKeyboardButton("🔙 Menu",      callback_data="back_menu")]]))
        return MENU

    api_usage = await db.get_api_usage(uid)
    cls       = ctx.user_data.get("ait_class","c9_10")
    ud        = await db.get_user(uid)
    lang      = (ud or {}).get("language","hi")

    from ai import GEMINI_KEY, MISTRAL_KEY, DEEPSEEK_KEY, GROQ_KEY, LIMITS
    api_status = []
    if GEMINI_KEY:
        left = LIMITS["gemini"] - api_usage.get("gemini",0)
        api_status.append(f"Gemini({left})")
    if MISTRAL_KEY:
        left = LIMITS["mistral"] - api_usage.get("mistral",0)
        api_status.append(f"Mistral({left})")
    if DEEPSEEK_KEY:
        left = LIMITS["deepseek"] - api_usage.get("deepseek",0)
        api_status.append(f"DeepSeek({left})")
    if GROQ_KEY:
        left = LIMITS["groq"] - api_usage.get("groq",0)
        api_status.append(f"Groq({left})")
    if not api_status:
        api_status = ["Free AI (∞)"]

    rem = "∞" if prem else str(limit - used)
    subj_name = {"math":"Maths","science":"Science","hindi":"Hindi","english":"English",
                 "physics":"Physics","chemistry":"Chemistry","biology":"Biology",
                 "sst":"History/SST","computer":"Computer","gk":"GK","all":"All Subjects"}.get(subj, subj)

    # Send initial AI message
    msg = await ctx.bot.send_message(uid,
        f"🤖 *AI Tutor Ready!*\n"
        f"📚 {CLASSES.get(cls,cls)} | 📖 {subj_name}\n"
        f"🔧 AI: {' | '.join(api_status)}\n"
        f"💬 Sawaal bache aaj: *{rem}*\n\n"
        f"Padhai ka sawaal type karo! 🎓\n"
        f"_/menu — wapas jaao_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🌐 Hindi",    callback_data="set_lang_hi"),
             InlineKeyboardButton("🌐 English",  callback_data="set_lang_en"),
             InlineKeyboardButton("🌐 Hinglish", callback_data="set_lang_mix")],
            [InlineKeyboardButton("📝 Notes Mode ON",callback_data="ait_notes_mode")],
            [InlineKeyboardButton("🔙 Subject",  callback_data=f"ait_{cls}"),
             InlineKeyboardButton("🔙 Menu",     callback_data="back_menu")]]))

    ctx.user_data["mode"]         = "ai_tutor"
    ctx.user_data["mode_class"]   = cls
    ctx.user_data["mode_subject"] = subj
    ctx.user_data["tutor_msg_id"] = msg.message_id
    ctx.user_data["ait_history"]  = []
    return AI_TUTOR_CHAT

# ══════════════════════════════════════════════════════════════════════════════
# QUICK QUESTION
# ══════════════════════════════════════════════════════════════════════════════
async def question_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    uid   = q.from_user.id
    prem  = await db.is_premium(uid)
    used  = await db.get_usage(uid,"q")
    limit = 999 if prem else 15
    await _del(q.message)
    if not prem and used >= limit:
        await ctx.bot.send_message(uid,
            "⚠️ *Limit khatam!*\nFree: 15/din\n\n💎 Premium lo!",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💎 Premium",callback_data="premium")],
                [InlineKeyboardButton("🔙 Menu",   callback_data="back_menu")]]))
        return MENU
    rem = "∞" if prem else str(limit-used)
    await ctx.bot.send_message(uid,
        f"❓ *Quick Sawaal Mode*\nBache: *{rem}*\n\n"
        f"Koi bhi sawaal type karo!\n_/menu — wapas_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    ctx.user_data["mode"] = "question"
    return CHATTING

# ══════════════════════════════════════════════════════════════════════════════
# HANDLE ALL TEXT MESSAGES
# ══════════════════════════════════════════════════════════════════════════════
async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if await db.is_blocked(uid): return
    txt = update.message.text
    if txt.startswith("/"): return
    mode = ctx.user_data.get("mode","question")

    # ── Special input modes ──────────────────────────────────────────────────
    if mode == "screenshot":
        return await handle_screenshot(update, ctx)

    if mode == "set_exam_name":
        ctx.user_data["exam_name"] = txt
        await update.message.reply_text("📅 Exam *date* daalo (YYYY-MM-DD):", parse_mode="Markdown")
        ctx.user_data["mode"] = "set_exam_date"; return CHATTING

    if mode == "set_exam_date":
        try:
            date.fromisoformat(txt.strip())
            await db.set_exam(uid, ctx.user_data.get("exam_name","Exam"), txt.strip())
            days = max(0,(date.fromisoformat(txt.strip())-date.today()).days)
            await update.message.reply_text(
                f"✅ *Exam set!*\n📝 {ctx.user_data.get('exam_name')}\n"
                f"📅 {txt.strip()}\n⏳ *{days} din baaki!*",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
            ctx.user_data["mode"] = "question"; return MENU
        except:
            await update.message.reply_text("❌ Format: YYYY-MM-DD\nExample: 2026-03-20"); return CHATTING

    if mode == "set_reminder_text":
        ctx.user_data["reminder_text"] = txt
        await update.message.reply_text(
            "⏰ Kab bhejun reminder?\n\n"
            "`30m` = 30 minutes\n`2h` = 2 hours\n`1d` = 1 day\n`9am` = subah 9 baje",
            parse_mode="Markdown")
        ctx.user_data["mode"] = "set_reminder_time"; return CHATTING

    if mode == "set_reminder_time":
        rd = _parse_reminder_time(txt.strip())
        if not rd:
            await update.message.reply_text("❌ Format: `30m`, `2h`, `1d`, `9am`", parse_mode="Markdown")
            return CHATTING
        await db.add_reminder(uid, ctx.user_data.get("reminder_text","!"), rd)
        await update.message.reply_text(
            f"✅ *Reminder set!*\n📝 {ctx.user_data.get('reminder_text')}\n"
            f"⏰ {rd.strftime('%d %b %Y, %I:%M %p')}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
        ctx.user_data["mode"] = "question"; return MENU

    if mode == "save_note_title":
        ctx.user_data["note_title"] = txt
        await update.message.reply_text("📝 Note ka *content* type karo:", parse_mode="Markdown")
        ctx.user_data["mode"] = "save_note_content"; return CHATTING

    if mode == "save_note_content":
        title   = ctx.user_data.get("note_title","Note")
        nid     = await db.save_note(uid, title, txt)
        wa_text = f"📝 {title}\n\n{txt[:400]}\n\n— @IndiaStudyAI_Bot"
        wa      = f"https://wa.me/?text={wa_text.replace(' ','+')}"
        await update.message.reply_text(
            f"✅ *Note save ho gaya!*\n📝 {title}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📤 WhatsApp Share",url=wa)],
                [InlineKeyboardButton("📋 Notes dekhein", callback_data="my_notes")],
                [InlineKeyboardButton("🔙 Menu",          callback_data="back_menu")]]))
        ctx.user_data["mode"] = "question"; return MENU

    if mode == "resume_info":
        ctx.user_data["resume_data"] = txt
        wait = await update.message.reply_text("📄 AI Resume bana raha hai... ⏳")
        ud   = await db.get_user(uid)
        lang = (ud or {}).get("language","hi")
        prompt = (
            f"Ek professional ATS-friendly resume banao:\n{txt}\n\n"
            f"Format: Name, Contact Info, Career Objective, Education, Skills, "
            f"Work Experience, Projects, Languages Known, Hobbies.\n"
            f"{'English mein.' if lang=='en' else 'English mein banao.'} "
            f"Clean, bold headings, proper spacing."
        )
        resume_txt, api = await ask_ai(prompt, mode="resume")
        pdf_path = await generate_pdf("My Resume", resume_txt, "resume.pdf")
        await _del(wait)
        if pdf_path and os.path.exists(pdf_path):
            with open(pdf_path,"rb") as f:
                await update.message.reply_document(f,
                    filename="Resume_IndiaStudyAI.pdf",
                    caption=(f"📄 *Aapka Professional Resume ready hai!*\n\n"
                             f"✅ ATS-Friendly format\n✅ Edit karo MS Word mein\n"
                             f"✅ PDF download ready 🎯"),
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
        else:
            await update.message.reply_text(
                f"📄 *Aapka Resume:*\n\n{resume_txt}",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
        ctx.user_data["mode"] = "question"; return MENU

    if mode == "study_planner_input":
        parts = txt.split("\n")
        subjects   = parts[0] if len(parts)>0 else txt
        exam_date  = parts[1].strip() if len(parts)>1 else ""
        hours_day  = int(parts[2].strip()) if len(parts)>2 else 4
        wait       = await update.message.reply_text("📊 AI study plan bana raha hai... ⏳")
        ud         = await db.get_user(uid)
        lang       = (ud or {}).get("language","hi")
        plan       = await generate_study_plan(subjects, exam_date, hours_day, lang)
        pdf_path   = await generate_pdf(f"Study Plan — {subjects[:30]}", plan, "study_plan.pdf")
        await _del(wait)
        if exam_date:
            await db.save_study_plan(uid, plan, exam_date, subjects)
        if pdf_path and os.path.exists(pdf_path):
            with open(pdf_path,"rb") as f:
                await update.message.reply_document(f, filename="StudyPlan_IndiaStudyAI.pdf",
                    caption="📊 *Tumhara Study Plan ready hai!*", parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
        else:
            await update.message.reply_text(plan, parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
        ctx.user_data["mode"] = "question"; return MENU

    if mode == "career_input":
        wait = await update.message.reply_text("🎓 Career analysis chal rahi hai... ⏳")
        ud   = await db.get_user(uid)
        lang = (ud or {}).get("language","hi")
        parts = txt.split("\n")
        skills   = parts[0] if len(parts)>0 else txt
        interests= parts[1] if len(parts)>1 else ""
        edu      = parts[2] if len(parts)>2 else ""
        result   = await career_counsel(skills, interests, edu, lang)
        await _del(wait)
        await update.message.reply_text(result, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📝 Note Save",callback_data="save_last_ans")],
                [InlineKeyboardButton("🔙 Menu",     callback_data="back_menu")]]))
        ctx.user_data["last_answer"]   = result
        ctx.user_data["last_question"] = "Career Guidance"
        ctx.user_data["mode"]          = "question"; return MENU

    if mode == "mind_map_input":
        wait   = await update.message.reply_text("🗺️ Mind map ban raha hai... ⏳")
        ud     = await db.get_user(uid)
        lang   = (ud or {}).get("language","hi")
        mmap   = await generate_mind_map(txt, lang)
        await _del(wait)
        # Format mind map as text
        lines  = [f"🗺️ *Mind Map: {mmap.get('center',txt)}*\n"]
        for b in mmap.get("branches",[]):
            lines.append(f"\n*{b.get('label','')}*")
            for s in b.get("sub",[]):
                lines.append(f"  • {s}")
        result = "\n".join(lines)
        await update.message.reply_text(result, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📄 PDF Download",callback_data="ans_to_pdf")],
                [InlineKeyboardButton("📝 Save Note",   callback_data="save_last_ans")],
                [InlineKeyboardButton("🔙 Menu",        callback_data="back_menu")]]))
        ctx.user_data["last_answer"]   = result
        ctx.user_data["last_question"] = f"Mind Map: {txt}"
        ctx.user_data["mode"]          = "question"; return MENU

    if mode == "vocab_input":
        wait = await update.message.reply_text("📖 Vocabulary bana raha hoon... ⏳")
        ud   = await db.get_user(uid)
        lang = (ud or {}).get("language","hi")
        result = await build_vocabulary(txt, lang)
        await _del(wait)
        await update.message.reply_text(result, parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📝 Save",callback_data="save_last_ans")],
                [InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
        ctx.user_data["last_answer"]   = result
        ctx.user_data["last_question"] = f"Vocabulary: {txt}"
        ctx.user_data["mode"]          = "question"; return MENU

    if mode == "qpaper_topic":
        wait = await update.message.reply_text("📝 Question paper ban raha hai... ⏳")
        subj = ctx.user_data.get("qpaper_subj","Science")
        cls  = ctx.user_data.get("qpaper_cls","Class 9-10")
        diff = ctx.user_data.get("qpaper_diff","Medium")
        ud   = await db.get_user(uid)
        lang = (ud or {}).get("language","hi")
        paper  = await generate_question_paper(txt or subj, cls, diff, lang)
        pdf_path = await generate_pdf(f"Question Paper — {txt or subj}", paper,"qpaper.pdf")
        await _del(wait)
        if pdf_path and os.path.exists(pdf_path):
            with open(pdf_path,"rb") as f:
                await update.message.reply_document(f, filename="QuestionPaper_IndiaStudyAI.pdf",
                    caption=f"📝 *{txt or subj} — Question Paper + Answer Key*",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
        else:
            await update.message.reply_text(paper, parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
        ctx.user_data["mode"] = "question"; return MENU

    # ── AI Question or AI Tutor ───────────────────────────────────────────────
    prem       = await db.is_premium(uid)
    ud         = await db.get_user(uid)
    api_usage  = await db.get_api_usage(uid)
    kind       = "ai" if mode == "ai_tutor" else "q"
    used       = await db.get_usage(uid, kind)
    limit      = 999 if prem else 15

    if not prem and used >= limit:
        await update.message.reply_text(
            "⚠️ *Daily limit khatam!*\n\n💎 Premium lo — Unlimited sawaal!",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💎 Premium",callback_data="premium")],
                [InlineKeyboardButton("🔙 Menu",   callback_data="back_menu")]]))
        return

    user_msg_id = update.message.message_id
    wait        = await update.message.reply_text("🤔 Soch raha hoon...")

    # Prepare context
    ai_ud = dict(ud) if ud else {}
    if mode == "ai_tutor":
        ai_ud["class_type"] = ctx.user_data.get("mode_class","")
        ai_ud["course"]     = ctx.user_data.get("mode_subject","")

    resp, api_used = await ask_ai(txt, ai_ud, mode if mode=="ai_tutor" else "study", api_usage)

    # Track usage
    await db.inc_usage(uid, kind)
    if api_used in ("gemini","mistral","deepseek","groq","together","cohere"):
        await db.inc_api_usage(uid, api_used)
    await db.save_q(uid, txt, resp, api_used)
    await db.check_and_award(uid)

    await _del(wait)
    # Delete user message for cleaner UX
    try: await ctx.bot.delete_message(uid, user_msg_id)
    except: pass

    wa   = f"https://wa.me/?text={('📚 IndiaStudyAI:'+chr(10)+resp[:400]).replace(' ','+')}"
    sent = await update.message.reply_text(
        resp, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Helpful +pts",  callback_data="fb_good"),
             InlineKeyboardButton("🔄 Dobara",         callback_data=f"retry_{kind}")],
            [InlineKeyboardButton("📤 WhatsApp",       url=wa),
             InlineKeyboardButton("📝 Note Save",      callback_data="save_last_ans")],
            [InlineKeyboardButton("📄 PDF Download",   callback_data="ans_to_pdf"),
             InlineKeyboardButton("🔙 Menu",           callback_data="back_menu")]]))

    ctx.user_data["last_answer"]      = resp[:1000]
    ctx.user_data["last_question"]    = txt[:100]
    ctx.user_data["last_ans_msg_id"]  = sent.message_id

    # Save to AI history if in tutor mode
    if mode == "ai_tutor":
        hist = ctx.user_data.get("ait_history",[])
        hist.append({"role":"user","content":txt})
        hist.append({"role":"assistant","content":resp})
        ctx.user_data["ait_history"] = hist[-12:]

    # Auto-save if notes mode is ON
    if ctx.user_data.get("save_to_notes"):
        await db.save_note(uid, txt[:50], resp, "AI Tutor")

    return AI_TUTOR_CHAT if mode=="ai_tutor" else CHATTING

# ══════════════════════════════════════════════════════════════════════════════
# HANDLE PHOTOS (Image → Text via Gemini Vision)
# ══════════════════════════════════════════════════════════════════════════════
async def handle_photo(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if await db.is_blocked(uid): return
    mode = ctx.user_data.get("mode","question")
    if mode == "screenshot": return await handle_screenshot(update, ctx)

    wait = await update.message.reply_text("📷 Image process ho rahi hai... ⏳")
    try:
        photo = update.message.photo[-1]
        file  = await ctx.bot.get_file(photo.file_id)
        path  = f"/tmp/img_{uid}.jpg"
        await file.download_to_drive(path)
        text  = await image_to_text(path)
        try: os.remove(path)
        except: pass

        await _del(wait)
        wa = f"https://wa.me/?text={('📷 Image Text:'+chr(10)+text[:400]).replace(' ','+')}"
        await update.message.reply_text(
            f"📷 *Image se result:*\n\n{text[:2000]}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📝 Note Save",    callback_data="save_last_ans")],
                [InlineKeyboardButton("📄 PDF Download", callback_data="ans_to_pdf")],
                [InlineKeyboardButton("📤 WhatsApp",     url=wa)],
                [InlineKeyboardButton("🔙 Menu",         callback_data="back_menu")]]))
        ctx.user_data["last_answer"]   = text[:1000]
        ctx.user_data["last_question"] = "Image Text Extraction"
    except Exception as e:
        log.error(f"Photo: {e}")
        await _del(wait)
        await update.message.reply_text(
            "❌ Image process nahi ho paayi.\nClear image bhejo ya sawaal type karo!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))

# ══════════════════════════════════════════════════════════════════════════════
# NEW FEATURES — Callbacks
# ══════════════════════════════════════════════════════════════════════════════

# ── Current Affairs ────────────────────────────────────────────────────────────
async def current_affairs_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    uid = q.from_user.id
    await _del(q.message)
    wait = await ctx.bot.send_message(uid,"⏳ Current affairs la raha hoon...")
    ud   = await db.get_user(uid)
    lang = (ud or {}).get("language","hi")
    cached = await db.get_cache(f"curr_affairs_{lang}")
    if cached: txt = cached
    else:
        txt = await get_current_affairs(lang)
        await db.set_cache(f"curr_affairs_{lang}", txt, 6)
    await _del(wait)
    await ctx.bot.send_message(uid,
        f"📰 *Current Affairs — {datetime.now().strftime('%B %Y')}*\n\n{txt}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📄 PDF Download", callback_data="ca_pdf")],
            [InlineKeyboardButton("🔄 Refresh",      callback_data="ca_refresh")],
            [InlineKeyboardButton("🔙 Menu",         callback_data="back_menu")]]))
    ctx.user_data["last_answer"]   = txt
    ctx.user_data["last_question"] = "Current Affairs"
    return MENU

async def ca_refresh_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    uid = q.from_user.id
    ud  = await db.get_user(uid)
    lang = (ud or {}).get("language","hi")
    await db.del_cache(f"curr_affairs_{lang}")
    return await current_affairs_cb(update, ctx)

async def ca_pdf_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer("📄 PDF ban raha hai...")
    uid = q.from_user.id
    txt = ctx.user_data.get("last_answer","")
    if not txt: return MENU
    path = await generate_pdf("Current Affairs", txt, "current_affairs.pdf")
    if path and os.path.exists(path):
        with open(path,"rb") as f:
            await ctx.bot.send_document(uid, f, filename="CurrentAffairs_IndiaStudyAI.pdf",
                caption="📰 *Current Affairs PDF*", parse_mode="Markdown")
    return MENU

# ── Question Paper ─────────────────────────────────────────────────────────────
async def qpaper_menu_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await _del(q.message)
    await ctx.bot.send_message(q.from_user.id,
        "📝 *Question Paper Generator*\n\nKis class ke liye? 👇",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Class 9-10",callback_data="qp_cls_910"),
             InlineKeyboardButton("Class 11-12",callback_data="qp_cls_1112")],
            [InlineKeyboardButton("College",    callback_data="qp_cls_col"),
             InlineKeyboardButton("Competitive",callback_data="qp_cls_comp")],
            [InlineKeyboardButton("🔙 Menu",    callback_data="back_menu")]]))
    return MENU

async def qp_cls_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    cls_map = {"qp_cls_910":"Class 9-10","qp_cls_1112":"Class 11-12",
               "qp_cls_col":"College","qp_cls_comp":"Competitive Exam"}
    ctx.user_data["qpaper_cls"] = cls_map.get(q.data,"Class 9-10")
    await q.edit_message_text(
        f"✅ {ctx.user_data['qpaper_cls']}\n\n*Difficulty?* 👇",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("Easy",  callback_data="qp_diff_easy"),
             InlineKeyboardButton("Medium",callback_data="qp_diff_med")],
            [InlineKeyboardButton("Hard",  callback_data="qp_diff_hard"),
             InlineKeyboardButton("Mixed", callback_data="qp_diff_mix")],
            [InlineKeyboardButton("🔙",    callback_data="qpaper_menu")]]))
    return MENU

async def qp_diff_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    diff_map = {"qp_diff_easy":"Easy","qp_diff_med":"Medium",
                "qp_diff_hard":"Hard","qp_diff_mix":"Mixed"}
    ctx.user_data["qpaper_diff"] = diff_map.get(q.data,"Medium")
    await q.edit_message_text(
        f"✅ {ctx.user_data['qpaper_diff']} difficulty\n\n"
        f"*Subject/Topic type karo:*\n_(e.g. Mathematics, Photosynthesis, Indian History)_",
        parse_mode="Markdown")
    ctx.user_data["mode"] = "qpaper_topic"
    return CHATTING

# ── Study Planner ──────────────────────────────────────────────────────────────
async def study_planner_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    uid = q.from_user.id
    await _del(q.message)
    # Check if existing plan
    plan = await db.get_study_plan(uid)
    if plan:
        await ctx.bot.send_message(uid,
            f"📊 *Tumhara Study Plan exist karta hai!*\n\n"
            f"📅 Exam: {plan.get('exam_date','?')}\n"
            f"📚 Subjects: {plan.get('subjects','?')[:50]}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("👁️ Dekho",        callback_data="sp_view")],
                [InlineKeyboardButton("📄 PDF Download", callback_data="sp_pdf")],
                [InlineKeyboardButton("🔄 Naya Banao",   callback_data="sp_new")],
                [InlineKeyboardButton("🔙 Menu",         callback_data="back_menu")]]))
    else:
        return await _sp_new(q, ctx)
    return MENU

async def _sp_new(q, ctx):
    uid = q.from_user.id if hasattr(q,'from_user') else q.effective_user.id
    await ctx.bot.send_message(uid,
        "📊 *Smart Study Planner*\n\n"
        "Niche format mein type karo:\n\n"
        "*Subjects* (line 1)\n"
        "*Exam Date* YYYY-MM-DD (line 2)\n"
        "*Hours/day* (line 3)\n\n"
        "_Example:_\n```\nMath, Physics, Chemistry\n2026-04-10\n5\n```",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    ctx.user_data["mode"] = "study_planner_input"
    return CHATTING

async def sp_view_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    uid  = q.from_user.id
    plan = await db.get_study_plan(uid)
    if not plan: return await study_planner_cb(update, ctx)
    await q.edit_message_text(plan.get("plan","")[:3500], parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📄 PDF",   callback_data="sp_pdf")],
            [InlineKeyboardButton("🔙 Menu",  callback_data="back_menu")]]))
    return MENU

async def sp_pdf_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer("📄 PDF ban raha hai...")
    uid  = q.from_user.id
    plan = await db.get_study_plan(uid)
    if not plan: return MENU
    path = await generate_pdf("Study Plan", plan.get("plan",""), "study_plan.pdf")
    if path and os.path.exists(path):
        with open(path,"rb") as f:
            await ctx.bot.send_document(uid, f, filename="StudyPlan_IndiaStudyAI.pdf",
                caption="📊 *Tumhara Study Plan PDF*", parse_mode="Markdown")
    return MENU

# ── Career Guide ───────────────────────────────────────────────────────────────
async def career_guide_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await _del(q.message)
    await ctx.bot.send_message(q.from_user.id,
        "🎓 *Career Counsellor AI*\n\n"
        "Apni details niche format mein type karo:\n\n"
        "*Skills* (line 1)\n*Interests* (line 2)\n*Education* (line 3)\n\n"
        "_Example:_\n```\nPython, Math, Drawing\nTechnology, Science\nClass 12 PCM\n```",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    ctx.user_data["mode"] = "career_input"
    return CHATTING

# ── Mind Map ───────────────────────────────────────────────────────────────────
async def mind_map_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await _del(q.message)
    await ctx.bot.send_message(q.from_user.id,
        "🗺️ *Mind Map Generator*\n\nKis topic ka mind map chahiye?\n"
        "_Example: Photosynthesis, Mughal Empire, Python Programming_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    ctx.user_data["mode"] = "mind_map_input"
    return CHATTING

# ── Vocabulary ─────────────────────────────────────────────────────────────────
async def vocab_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await _del(q.message)
    await ctx.bot.send_message(q.from_user.id,
        "📖 *Vocabulary Builder*\n\nKis topic ke words chahiye?\n"
        "_Example: Environment, Computer Science, Business_",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    ctx.user_data["mode"] = "vocab_input"
    return CHATTING

# ── OCR Mode ───────────────────────────────────────────────────────────────────
async def ocr_mode_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await _del(q.message)
    await ctx.bot.send_message(q.from_user.id,
        "📷 *Image → Text Mode*\n\n"
        "Koi bhi image bhejo:\n"
        "• 📝 Handwritten notes\n"
        "• 📄 Printed text / question\n"
        "• 🖼️ Question paper\n"
        "• 📸 Board / whiteboard photo\n\n"
        "Gemini Vision se text nikalta hoon + explain karta hoon! 🤖",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    ctx.user_data["mode"] = "ocr"
    return CHATTING

# ── Resume Builder ─────────────────────────────────────────────────────────────
async def resume_builder_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await _del(q.message)
    await ctx.bot.send_message(q.from_user.id,
        "📄 *AI Resume Builder*\n\n"
        "Apni details type karo:\n\n"
        "_Example:_\n"
        "Naam: Rahul Kumar\n"
        "Phone: 9876543210\n"
        "Email: rahul@gmail.com\n"
        "Education: B.Sc Computer, Delhi Univ 2023\n"
        "Skills: Python, MS Office, English\n"
        "Experience: Data entry 1 year\n"
        "Projects: School management system\n"
        "Languages: Hindi, English\n\n"
        "_Jitni detail doge, utna achha professional resume banega!_ ✨",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    ctx.user_data["mode"] = "resume_info"
    return CHATTING

# ── PDF from last answer ───────────────────────────────────────────────────────
async def ans_to_pdf_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer("📄 PDF ban raha hai...")
    uid      = q.from_user.id
    content  = ctx.user_data.get("last_answer","")
    question = ctx.user_data.get("last_question","Notes")
    if not content:
        await q.answer("Koi content nahi mila!", show_alert=True); return MENU
    path = await generate_pdf(question[:50], content)
    if path and os.path.exists(path):
        with open(path,"rb") as f:
            await ctx.bot.send_document(uid, f, filename="IndiaStudyAI_Notes.pdf",
                caption="📄 *PDF ready!*", parse_mode="Markdown")
    else:
        await q.answer("PDF nahi ban paya!", show_alert=True)
    return MENU

# ── Save last answer as note ───────────────────────────────────────────────────
async def save_last_ans_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q       = update.callback_query; await q.answer()
    uid     = q.from_user.id
    content = ctx.user_data.get("last_answer","")
    title   = ctx.user_data.get("last_question","AI Answer")[:50]
    if content:
        await db.save_note(uid, title, content, "AI Answer")
        await q.answer("✅ Note save ho gaya!", show_alert=True)
    else:
        await q.answer("Koi content nahi mila!", show_alert=True)
    return MENU

# ── Chat History ───────────────────────────────────────────────────────────────
async def chat_history_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query; await q.answer()
    uid  = q.from_user.id
    prem = await db.is_premium(uid)
    await _del(q.message)
    if not prem:
        await ctx.bot.send_message(uid,
            "💎 *Chat History — Premium Feature*\n\n"
            "Apni pichli conversations 2 mahine tak access karo!\n\n"
            "Premium lo aur unlock karo! 🔓",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💎 Premium Lo",callback_data="premium")],
                [InlineKeyboardButton("🔙 Menu",      callback_data="back_menu")]]))
        return MENU
    history = await db.get_chat_history(uid, 15)
    if not history:
        await ctx.bot.send_message(uid,
            "💬 *Chat History*\n\nAbhi koi history nahi hai.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
        return MENU
    lines = ["💬 *Aapki Recent Conversations*\n"]
    btns  = []
    for i,h in enumerate(history[:10]):
        q_txt = h.get("question","")[:35]
        ts    = h.get("ts","")[:10]
        api   = h.get("api_used","")
        lines.append(f"{i+1}. _{q_txt}_\n   📅{ts} | 🤖{api}")
        btns.append([
            InlineKeyboardButton(f"📖 {q_txt[:22]}",callback_data=f"vh_{str(h['_id'])}"),
            InlineKeyboardButton("🗑️",              callback_data=f"vhd_{str(h['_id'])}")])
    btns.append([InlineKeyboardButton("🗑️ Sab Delete",callback_data="ch_clear_all")])
    btns.append([InlineKeyboardButton("🔙 Menu",callback_data="back_menu")])
    await ctx.bot.send_message(uid,"\n".join(lines),parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(btns))
    return MENU

async def view_hist_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query; await q.answer()
    uid = q.from_user.id
    hid = q.data.replace("vh_","")
    # get from db
    from bson import ObjectId
    try:
        doc = await db.questions.find_one({"_id":ObjectId(hid),"user_id":uid})
    except: doc = None
    if not doc: await q.answer("Nahi mila!",show_alert=True); return MENU
    await q.message.reply_text(
        f"❓ *{doc.get('question','')}*\n\n{doc.get('answer','')}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🗑️ Delete",  callback_data=f"vhd_{hid}")],
            [InlineKeyboardButton("🔙 History", callback_data="chat_history")]]))
    return MENU

async def del_hist_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query; await q.answer()
    hid = q.data.replace("vhd_","")
    await db.delete_chat_item(q.from_user.id, hid)
    await q.answer("🗑️ Delete ho gaya!",show_alert=True)
    return await chat_history_cb(update, ctx)

async def clear_hist_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await db.clear_chat_history(q.from_user.id)
    await q.answer("✅ Sab delete ho gaya!",show_alert=True)
    return await back_menu(update, ctx)

# ── Updates ────────────────────────────────────────────────────────────────────
async def show_updates(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await _del(q.message)
    uid  = q.from_user.id
    wait = await ctx.bot.send_message(uid,"⏳ Live data la raha hoon...")
    cached = await db.get_cache("updates_all")
    txt    = cached if cached else await fetch_updates("all")
    if not cached: await db.set_cache("updates_all", txt, 24)
    await _del(wait)
    await ctx.bot.send_message(uid,
        f"📢 *Sarkari Updates — Live {datetime.now().strftime('%B %Y')}*\n\n{txt}",
        parse_mode="Markdown", disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💼 Jobs",    callback_data="upd_jobs"),
             InlineKeyboardButton("📋 Forms",   callback_data="upd_forms")],
            [InlineKeyboardButton("📊 Results", callback_data="upd_results"),
             InlineKeyboardButton("🏛️ Yojana",  callback_data="upd_yojana")],
            [InlineKeyboardButton("🪪 Admit",   callback_data="upd_admit"),
             InlineKeyboardButton("🎓 Scholar", callback_data="upd_scholar")],
            [InlineKeyboardButton("🔄 Naya Data",callback_data="upd_refresh"),
             InlineKeyboardButton("🔙 Menu",    callback_data="back_menu")]]))
    return MENU

async def show_upd_cat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query; await q.answer()
    cat = q.data.replace("upd_","")
    if cat == "refresh":
        await db.del_cache_prefix("updates_")
        return await show_updates(update, ctx)
    labels = {"jobs":"💼 Jobs","forms":"📋 Forms","results":"📊 Results",
              "yojana":"🏛️ Yojana","admit":"🪪 Admit Card","scholar":"🎓 Scholarship"}
    lbl  = labels.get(cat,"Updates")
    await _del(q.message)
    uid  = q.from_user.id
    wait = await ctx.bot.send_message(uid,f"⏳ {lbl} la raha hoon...")
    ck   = f"updates_{cat}"
    txt  = await db.get_cache(ck)
    if not txt:
        txt = await fetch_updates(cat)
        await db.set_cache(ck, txt, 24)
    await _del(wait)
    await ctx.bot.send_message(uid,
        f"*{lbl} — Live*\n\n{txt}",
        parse_mode="Markdown", disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh",  callback_data=f"upd_refresh")],
            [InlineKeyboardButton("🔙 Updates",  callback_data="updates"),
             InlineKeyboardButton("🔙 Menu",     callback_data="back_menu")]]))
    return MENU

# ── News ──────────────────────────────────────────────────────────────────────
async def show_news(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query; await q.answer()
    await _del(q.message)
    uid  = q.from_user.id
    wait = await ctx.bot.send_message(uid,"📰 RSS feeds se news la raha hoon...")
    cached = await db.get_cache("news_india")
    txt    = cached if cached else await fetch_news("india")
    if not cached: await db.set_cache("news_india", txt, 6)
    await _del(wait)
    await ctx.bot.send_message(uid,
        f"📰 *Aaj Ki Khabar — Live*\n\n{txt}",
        parse_mode="Markdown", disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏛️ Rajniti", callback_data="nws_pol"),
             InlineKeyboardButton("🏏 Sports",  callback_data="nws_sport")],
            [InlineKeyboardButton("💼 Business",callback_data="nws_biz"),
             InlineKeyboardButton("📚 Education",callback_data="nws_edu")],
            [InlineKeyboardButton("🔄 Refresh", callback_data="nws_refresh"),
             InlineKeyboardButton("🔙 Menu",    callback_data="back_menu")]]))
    return MENU

async def show_news_cat(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query; await q.answer()
    cat = q.data.replace("nws_","")
    if cat == "refresh":
        await db.del_cache_prefix("news_")
        return await show_news(update, ctx)
    labels = {"pol":"🏛️ Rajniti","sport":"🏏 Sports","biz":"💼 Business","edu":"📚 Education"}
    lbl  = labels.get(cat,"News")
    await _del(q.message)
    uid  = q.from_user.id
    wait = await ctx.bot.send_message(uid,f"⏳ {lbl} la raha hoon...")
    ck   = f"news_{cat}"
    txt  = await db.get_cache(ck)
    if not txt:
        txt = await fetch_news(cat)
        await db.set_cache(ck, txt, 6)
    await _del(wait)
    await ctx.bot.send_message(uid,
        f"*{lbl} — Live*\n\n{txt}",
        parse_mode="Markdown", disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh", callback_data="nws_refresh"),
             InlineKeyboardButton("🔙 News",    callback_data="news"),
             InlineKeyboardButton("🔙 Menu",    callback_data="back_menu")]]))
    return MENU

# ── Leaderboard ────────────────────────────────────────────────────────────────
async def leaderboard_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q       = update.callback_query; await q.answer()
    uid     = q.from_user.id
    leaders = await db.get_leaderboard(10)
    rank    = await db.get_rank(uid)
    medals  = ["🥇","🥈","🥉","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
    lines   = [f"*🏆 Top 10 — IndiaStudyAI {datetime.now().year}*\n"]
    for i,u in enumerate(leaders):
        name  = u.get("name","User")[:12]
        pts   = u.get("points",0)
        streak= u.get("streak",0)
        refs  = u.get("ref_count",0)
        you   = " ← You!" if u["user_id"]==uid else ""
        lines.append(f"{medals[i]} *{name}* — {pts}pts 🔥{streak} 👥{refs}{you}")
    lines.append(f"\n📊 *Tumhara rank: #{rank}*")
    await _del(q.message)
    await ctx.bot.send_message(uid, "\n".join(lines), parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👥 Refer karo",callback_data="refer")],
            [InlineKeyboardButton("🔙 Menu",       callback_data="back_menu")]]))
    return MENU

# ── Refer ──────────────────────────────────────────────────────────────────────
async def refer_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q  = update.callback_query; await q.answer()
    uid= q.from_user.id
    ud = await db.get_user(uid)
    ref_count= ud.get("ref_count",0) if ud else 0
    pts      = ud.get("points",0) if ud else 0
    next_r   = 5-(ref_count%5) if ref_count%5 != 0 else 5
    ref_link = f"{BOT_LINK}?start=REF{uid}"
    share    = f"Yaar ye study bot bahut badhiya hai! Free mein padhai karo 📚 {ref_link}"
    await _del(q.message)
    await ctx.bot.send_message(uid,
        f"👥 *Refer & Earn*\n\n"
        f"🔗 *Tera link:*\n`{ref_link}`\n\n"
        f"📊 Refer: *{ref_count}* | Points: *{pts}*\n"
        f"Agle reward ke liye: *{next_r}* refer\n\n"
        f"🎁 *Rewards:*\n"
        f"• Har refer = 100 pts dono ko\n"
        f"• 5 refer = 7 din FREE Premium!\n"
        f"• 10 refer = 30 din Premium!\n"
        f"• 20 refer = Lifetime Access 👑",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 WhatsApp Share",
                url=f"https://wa.me/?text={share.replace(' ','+')}"),
             InlineKeyboardButton("📋 Copy Link",
                callback_data="copy_ref")],
            [InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    return MENU

# ── Daily Challenge ────────────────────────────────────────────────────────────
async def daily_challenge_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query; await q.answer()
    uid = q.from_user.id
    await _del(q.message)
    done = await db.challenge_done_today(uid)
    if done:
        await ctx.bot.send_message(uid,
            "✅ *Aaj ka challenge ho gaya!*\n\nKal subah naya challenge milega! 🌅",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
        return MENU
    challenges = [
        {"q":"India ka sabse bada state (area mein)?","opts":["Maharashtra","Rajasthan","MP","UP"],"a":1,"cat":"GK"},
        {"q":"Newton ki 2nd law?","opts":["F=mv","F=ma","F=mg","F=m/a"],"a":1,"cat":"Physics"},
        {"q":"Photosynthesis mein kaunsi gas absorb hoti hai?","opts":["O2","N2","CO2","H2"],"a":2,"cat":"Science"},
        {"q":"India mein kitne states hain? (2026)","opts":["25","26","28","30"],"a":2,"cat":"GK"},
        {"q":"x²-5x+6=0 ke roots?","opts":["2,3","1,6","2,4","3,4"],"a":0,"cat":"Math"},
        {"q":"Samvidhan kab lagu hua?","opts":["15 Aug 47","26 Jan 50","26 Nov 49","2 Oct 48"],"a":1,"cat":"History"},
        {"q":"DNA ka full form?","opts":["Deoxyribose Nucleic Acid","Deoxy Nitric Acid","Di Nitro Acid","None"],"a":0,"cat":"Biology"},
        {"q":"CPU ka full form?","opts":["Central Process Unit","Central Processing Unit","Computer Process Unit","None"],"a":1,"cat":"Computer"},
        {"q":"India ki capital?","opts":["Mumbai","Kolkata","New Delhi","Chennai"],"a":2,"cat":"GK"},
        {"q":"H2O mein hydrogen atoms?","opts":["1","2","3","4"],"a":1,"cat":"Chemistry"},
    ]
    ch = random.choice(challenges)
    ctx.user_data["challenge"] = ch
    opts = "\n".join([f"{chr(65+i)}. {o}" for i,o in enumerate(ch["opts"])])
    await ctx.bot.send_message(uid,
        f"🎯 *Daily Challenge!*\n🏷️ *{ch['cat']}*\n\n❓ *{ch['q']}*\n\n{opts}\n\n✅ Sahi = +20 pts!",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"A. {ch['opts'][0][:20]}",callback_data="ch_0"),
             InlineKeyboardButton(f"B. {ch['opts'][1][:20]}",callback_data="ch_1")],
            [InlineKeyboardButton(f"C. {ch['opts'][2][:20]}",callback_data="ch_2"),
             InlineKeyboardButton(f"D. {ch['opts'][3][:20]}",callback_data="ch_3")]]))
    return MENU

async def challenge_answer_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q       = update.callback_query; await q.answer()
    uid     = q.from_user.id
    chosen  = int(q.data[3:])
    ch      = ctx.user_data.get("challenge")
    if not ch: return await back_menu(update, ctx)
    await db.mark_challenge_done(uid)
    await _del(q.message)
    if chosen == ch["a"]:
        await db.add_points(uid, 20)
        await ctx.bot.send_message(uid,
            f"✅ *Bilkul Sahi!* +20 pts! 🎉\n\n"
            f"✔️ Answer: *{ch['opts'][ch['a']]}*",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    else:
        await ctx.bot.send_message(uid,
            f"❌ *Galat!*\n\n✔️ Sahi answer: *{ch['opts'][ch['a']]}*\n\nKal dobara try karo! 💪",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    return MENU

# ── Notes ──────────────────────────────────────────────────────────────────────
async def my_notes_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q     = update.callback_query; await q.answer()
    uid   = q.from_user.id
    notes = await db.get_user_notes(uid)
    await _del(q.message)
    if not notes:
        await ctx.bot.send_message(uid,
            "📝 *Meri Notes*\n\nKoi note nahi hai!\nAI se jawab milne pe 'Note Save' dabao.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📝 Naya Note",callback_data="write_note")],
                [InlineKeyboardButton("🔙 Menu",     callback_data="back_menu")]]))
        return MENU
    lines = ["📝 *Meri Notes*\n"]
    btns  = []
    for note in notes:
        title = note.get("title","Note")[:30]
        ts    = note.get("ts","")[:10]
        subj  = note.get("subject","")
        lines.append(f"• *{title}* ({subj}) — {ts}")
        btns.append([
            InlineKeyboardButton(f"📖 {title[:22]}",callback_data=f"view_note_{str(note['_id'])}"),
            InlineKeyboardButton("🗑️",              callback_data=f"del_note_{str(note['_id'])}")])
    btns.append([InlineKeyboardButton("📝 Naya Note",callback_data="write_note"),
                 InlineKeyboardButton("🗑️ Sab Delete",callback_data="del_all_notes")])
    btns.append([InlineKeyboardButton("🔙 Menu",callback_data="back_menu")])
    await ctx.bot.send_message(uid, "\n".join(lines), parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(btns))
    return MENU

async def write_note_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await _del(q.message)
    await ctx.bot.send_message(q.from_user.id,
        "📝 Note ka *title* type karo:", parse_mode="Markdown")
    ctx.user_data["mode"] = "save_note_title"
    return CHATTING

async def view_note_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query; await q.answer()
    uid = q.from_user.id
    nid = q.data.replace("view_note_","")
    note = await db.get_note(uid, nid)
    if not note: await q.answer("Nahi mila!",show_alert=True); return MENU
    title   = note.get("title","Note")
    content = note.get("content","")[:800]
    wa      = f"https://wa.me/?text={('📝 '+title+chr(10)+content[:400]+chr(10)+'— @IndiaStudyAI_Bot').replace(' ','+')}"
    await _del(q.message)
    await ctx.bot.send_message(uid,
        f"📝 *{title}*\n\n{content}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 WhatsApp",     url=wa),
             InlineKeyboardButton("📄 PDF Download", callback_data=f"note_pdf_{nid}")],
            [InlineKeyboardButton("🗑️ Delete",       callback_data=f"del_note_{nid}"),
             InlineKeyboardButton("🔙 Notes",        callback_data="my_notes")]]))
    ctx.user_data["last_answer"]   = content
    ctx.user_data["last_question"] = title
    return MENU

async def del_note_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query; await q.answer()
    uid = q.from_user.id
    nid = q.data.replace("del_note_","")
    await db.delete_note(uid, nid)
    await q.answer("🗑️ Note delete ho gaya!",show_alert=True)
    return await my_notes_cb(update, ctx)

async def del_all_notes_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await db.delete_all_notes(q.from_user.id)
    await q.answer("✅ Sab notes delete!",show_alert=True)
    return await back_menu(update, ctx)

async def note_pdf_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query; await q.answer("📄 PDF ban raha hai...")
    uid = q.from_user.id
    nid = q.data.replace("note_pdf_","")
    note = await db.get_note(uid, nid)
    if not note: return MENU
    path = await generate_pdf(note.get("title","Note"), note.get("content",""))
    if path and os.path.exists(path):
        with open(path,"rb") as f:
            await ctx.bot.send_document(uid, f, filename="IndiaStudyAI_Note.pdf",
                caption="📄 *PDF ready!*", parse_mode="Markdown")
    return MENU

# ── Reminders ──────────────────────────────────────────────────────────────────
async def set_reminder_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query; await q.answer()
    uid = q.from_user.id
    await _del(q.message)
    reminders = await db.get_user_reminders(uid)
    rem_lines = ""
    if reminders:
        rem_lines = "\n\n*Active Reminders:*\n"
        for r in reminders:
            rem_lines += f"• {r['text'][:25]} — {r['remind_at'][:16]}\n"
    await ctx.bot.send_message(uid,
        f"⏰ *Reminder Set Karo*\n\nKya reminder chahiye?{rem_lines}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    ctx.user_data["mode"] = "set_reminder_text"
    return CHATTING

# ── Language ───────────────────────────────────────────────────────────────────
async def lang_menu_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await _del(q.message)
    ud = await db.get_user(q.from_user.id)
    current = (ud or {}).get("language","hi")
    marks = {"hi":"✅ ","en":"","mix":""}
    marks[current] = "✅ "
    await ctx.bot.send_message(q.from_user.id,
        "🌐 *Language Choose Karo*\n\n"
        "AI is language mein jawab dega.\nMini App mein bhi change hogi.",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"{marks.get('hi','')}🇮🇳 Hindi",    callback_data="set_lang_hi"),
             InlineKeyboardButton(f"{marks.get('en','')}🇬🇧 English",  callback_data="set_lang_en")],
            [InlineKeyboardButton(f"{marks.get('mix','')}🔀 Hinglish", callback_data="set_lang_mix")],
            [InlineKeyboardButton("🔙 Menu",                           callback_data="back_menu")]]))
    return MENU

async def set_lang_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query; await q.answer()
    lang = q.data.replace("set_lang_","")
    await db.update_language(q.from_user.id, lang)
    names = {"hi":"Hindi 🇮🇳","en":"English 🇬🇧","mix":"Hinglish 🔀"}
    await q.answer(f"✅ {names.get(lang,lang)} set ho gaya!", show_alert=True)
    return await back_menu(update, ctx)

# ── Settings ───────────────────────────────────────────────────────────────────
async def settings_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query; await q.answer()
    uid = q.from_user.id
    ud  = await db.get_user(uid)
    await _del(q.message)
    morning = ud.get("notify_morning",True) if ud else True
    exam_n  = ud.get("notify_exam",True) if ud else True
    await ctx.bot.send_message(uid,
        "⚙️ *Settings*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"🌅 Morning: {'✅ ON' if morning else '❌ OFF'}",
                callback_data="toggle_morning")],
            [InlineKeyboardButton(f"📅 Exam Reminder: {'✅ ON' if exam_n else '❌ OFF'}",
                callback_data="toggle_exam_n")],
            [InlineKeyboardButton("🌐 Language",       callback_data="lang_menu")],
            [InlineKeyboardButton("✏️ Profile Update", callback_data="update_profile")],
            [InlineKeyboardButton("📅 Set Exam Date",  callback_data="set_exam")],
            [InlineKeyboardButton("🔙 Menu",           callback_data="back_menu")]]))
    return MENU

async def toggle_morning_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q  = update.callback_query; await q.answer()
    ud = await db.get_user(q.from_user.id)
    nv = not ud.get("notify_morning",True) if ud else False
    await db.update_settings(q.from_user.id, notify_morning=nv)
    await q.answer(f"Morning notification {'ON ✅' if nv else 'OFF ❌'}", show_alert=True)
    return await settings_cb(update, ctx)

async def toggle_exam_n_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q  = update.callback_query; await q.answer()
    ud = await db.get_user(q.from_user.id)
    nv = not ud.get("notify_exam",True) if ud else False
    await db.update_settings(q.from_user.id, notify_exam=nv)
    await q.answer(f"Exam reminder {'ON ✅' if nv else 'OFF ❌'}", show_alert=True)
    return await settings_cb(update, ctx)

# ── Exam Countdown ─────────────────────────────────────────────────────────────
async def set_exam_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query; await q.answer()
    uid = q.from_user.id
    ud  = await db.get_user(uid)
    await _del(q.message)
    if ud and ud.get("exam_date"):
        try:
            days = max(0,(date.fromisoformat(ud["exam_date"])-date.today()).days)
            await ctx.bot.send_message(uid,
                f"📅 *Tumhara Exam*\n\n"
                f"📝 {ud.get('exam_name','Exam')}\n"
                f"📅 {ud['exam_date']}\n"
                f"⏳ *{days} din baaki!*\n"
                f"{'🟢 Bahut time!' if days>60 else '🟡 Revision time!' if days>14 else '🔴 Last days!'}",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✏️ Change Exam",callback_data="change_exam")],
                    [InlineKeyboardButton("📊 Study Planner",callback_data="study_planner")],
                    [InlineKeyboardButton("🔙 Menu",        callback_data="back_menu")]]))
            return MENU
        except: pass
    await ctx.bot.send_message(uid,"📅 Exam ka *naam* type karo:", parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    ctx.user_data["mode"] = "set_exam_name"
    return CHATTING

async def change_exam_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await _del(q.message)
    await ctx.bot.send_message(q.from_user.id,"✏️ Naya *exam naam* type karo:", parse_mode="Markdown")
    ctx.user_data["mode"] = "set_exam_name"
    return CHATTING

# ── Premium ────────────────────────────────────────────────────────────────────
async def premium_info(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query; await q.answer()
    uid = q.from_user.id
    prem = await db.is_premium(uid)
    await _del(q.message)
    if prem:
        ud  = await db.get_user(uid)
        exp = ud.get("premium_expiry","?") if ud else "?"
        await ctx.bot.send_message(uid,
            f"💎 *Premium Active!*\n\n✅ Expiry: {exp}\n✅ Unlimited AI\n✅ Unlimited Notes\n✅ Chat History",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
        return MENU
    await ctx.bot.send_message(uid,
        f"💎 *Premium — ₹199/month*\n\n"
        f"✅ Unlimited AI (Gemini·Mistral·DeepSeek·Groq)\n"
        f"✅ Chat History (2 mahine)\n"
        f"✅ Unlimited sawaal\n"
        f"✅ Unlimited Notes + PDF\n"
        f"✅ Question Paper generator\n"
        f"✅ Resume Builder\n"
        f"✅ Career Counselling\n"
        f"✅ Study Planner\n\n"
        f"━━━━━━━━━━\n💳 UPI: `{UPI_ID}`\n💰 Amount: ₹199\n━━━━━━━━━━\n\n"
        f"1️⃣ ₹199 bhejo\n2️⃣ Screenshot lo\n3️⃣ Button dabao ✅\n\n"
        f"💡 *FREE Option:* 5 refer = 7 din premium!\n"
        f"💡 *10 refer = 30 din!*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Pay kar diya — Screenshot do", callback_data="prem_paid")],
            [InlineKeyboardButton("👥 Refer karke FREE lo",          callback_data="refer")],
            [InlineKeyboardButton("🔙 Menu",                        callback_data="back_menu")]]))
    return MENU

async def prem_paid(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    await _del(q.message)
    await ctx.bot.send_message(q.from_user.id,
        "📸 *Payment Screenshot Bhejo!*\n\n1-2 ghante mein activate hoga! 🔔",
        parse_mode="Markdown")
    ctx.user_data["mode"] = "screenshot"
    return WAIT_SS

async def handle_screenshot(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    u   = update.effective_user
    cap = (f"💳 *New Premium Request!*\n"
           f"👤 {u.first_name}\n🆔 `{uid}`\n@{u.username or 'N/A'}\n\n"
           f"`/addpremium {uid} 30`")
    try:
        if update.message.photo:
            await ctx.bot.forward_message(OWNER_ID, update.message.chat_id, update.message.message_id)
        await ctx.bot.send_message(OWNER_ID, cap, parse_mode="Markdown")
    except Exception as e: log.error(f"Fwd screenshot: {e}")
    await update.message.reply_text(
        "✅ *Request bhej di!*\n\n1-2 ghante mein activate hoga.\n"
        "Confirmation message milega! 🎉",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    ctx.user_data["mode"] = "question"
    return MENU

# ── Profile ────────────────────────────────────────────────────────────────────
async def profile_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query; await q.answer()
    uid = q.from_user.id
    ud  = await db.get_user(uid)
    prem = await db.is_premium(uid)
    cls  = CLASSES.get(ud.get("class_type",""),"N/A") if ud else "N/A"
    co   = COURSES.get(ud.get("course",""),"N/A") if ud else "N/A"
    pts  = ud.get("points",0) if ud else 0
    strk = ud.get("streak",0) if ud else 0
    maxs = ud.get("max_streak",0) if ud else 0
    tq   = ud.get("total_q",0) if ud else 0
    refs = ud.get("ref_count",0) if ud else 0
    badges = ud.get("badges",[]) if ud else []
    rank = await db.get_rank(uid)
    exp  = ud.get("premium_expiry","") if ud else ""
    await _del(q.message)
    await ctx.bot.send_message(uid,
        f"👤 *Meri Profile*\n\n"
        f"📚 {cls} | 📖 {co}\n"
        f"{'💎 Premium ✨' if prem else '🆓 Free'}"
        f"{' ('+exp+')' if prem and exp else ''}\n\n"
        f"⭐ *Points:* {pts} | *Rank:* #{rank}\n"
        f"🔥 *Streak:* {strk} din | *Best:* {maxs}\n"
        f"👥 *Referrals:* {refs}\n"
        f"📈 *Total Sawaal:* {tq}\n"
        f"🏅 *Badges:* {' '.join(badges[:4]) if badges else '—'}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✏️ Profile Update",  callback_data="update_profile")],
            [InlineKeyboardButton("📝 Meri Notes",      callback_data="my_notes"),
             InlineKeyboardButton("💬 History",         callback_data="chat_history")],
            [InlineKeyboardButton("📊 Study Planner",   callback_data="study_planner")],
            [InlineKeyboardButton("🔙 Menu",            callback_data="back_menu")]]))
    return MENU

async def ait_notes_mode_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q   = update.callback_query; await q.answer()
    cur = ctx.user_data.get("save_to_notes",False)
    ctx.user_data["save_to_notes"] = not cur
    await q.answer(f"Notes Mode {'ON 📝' if not cur else 'OFF'}", show_alert=True)
    return AI_TUTOR_CHAT

async def feedback_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    if q.data == "fb_good":
        await q.answer("✅ Shukriya! +1 pt!")
        await db.add_points(q.from_user.id, 1)
    else:
        await q.answer("📝 Feedback noted!")
    return MENU

async def retry_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q    = update.callback_query; await q.answer()
    kind = q.data.replace("retry_","")
    ctx.user_data["mode"] = "ai_tutor" if kind=="ai" else "question"
    await _del(q.message)
    await ctx.bot.send_message(q.from_user.id,"🔄 Dobara sawaal type karo!",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    return AI_TUTOR_CHAT if kind=="ai" else CHATTING

async def back_menu(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query; await q.answer()
    ctx.user_data["mode"]          = "question"
    ctx.user_data["save_to_notes"] = False
    return await _send_menu(q, ctx)

# ══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def _parse_reminder_time(txt: str):
    now = datetime.now()
    try:
        t = txt.lower().strip()
        if t.endswith('m'):  return now + timedelta(minutes=int(t[:-1]))
        if t.endswith('h'):  return now + timedelta(hours=int(t[:-1]))
        if t.endswith('d'):  return now + timedelta(days=int(t[:-1]))
        if 'am' in t or 'pm' in t:
            fmt = "%I%p" if len(t) <= 4 else "%I:%M%p"
            tr  = datetime.strptime(t.upper().replace(' ',''), fmt)
            result = now.replace(hour=tr.hour, minute=tr.minute, second=0, microsecond=0)
            if result < now: result += timedelta(days=1)
            return result
    except: pass
    return None

# ══════════════════════════════════════════════════════════════════════════════
# SCHEDULED JOBS
# ══════════════════════════════════════════════════════════════════════════════
async def send_morning_messages(bot):
    users = await db.morning_notify_users()
    sent  = 0
    for u in users:
        try:
            ud  = await db.get_user(u["user_id"])
            msg = await get_morning_message(
                ud.get("name","Student") if ud else "Student",
                ud.get("streak",0) if ud else 0)
            await bot.send_message(u["user_id"], msg, parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🎯 Daily Challenge",callback_data="daily_challenge"),
                     InlineKeyboardButton("📱 Study App",web_app=WebAppInfo(url=MINI_APP))],
                    [InlineKeyboardButton("📢 Updates",    callback_data="updates"),
                     InlineKeyboardButton("📰 CA",        callback_data="current_affairs")]]))
            sent += 1
        except: pass
    log.info(f"✅ Morning messages: {sent}")

async def send_exam_reminders(bot):
    for r in await db.get_exam_reminders():
        try:
            d = r["days_left"]; n = r.get("exam_name","Exam")
            msgs = {1:f"⚠️ *KAL HAI!* {n} — Last revision! Best of luck! 🍀",
                    7:f"📅 *{n} — 7 din baaki!* Regular revision karo! 📚",
                    30:f"📅 *{n} — 30 din baaki!* Preparation shuru karo! 💪"}
            await bot.send_message(r["user_id"], msgs.get(d,f"📅 {n} — {d} din!"),
                parse_mode="Markdown")
        except: pass

async def send_due_reminders(bot):
    for r in await db.get_due_reminders():
        try:
            await bot.send_message(r["user_id"],
                f"⏰ *Reminder!*\n\n{r['text']}", parse_mode="Markdown")
            await db.mark_reminder_sent(str(r["_id"]))
        except: pass

# ══════════════════════════════════════════════════════════════════════════════
# ADMIN COMMANDS
# ══════════════════════════════════════════════════════════════════════════════
async def cmd_addpremium(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not ctx.args: await update.message.reply_text("Usage: /addpremium <id> [days]"); return
    uid  = int(ctx.args[0])
    days = int(ctx.args[1]) if len(ctx.args)>1 else 30
    await db.set_premium(uid, days)
    try: await ctx.bot.send_message(uid,
        f"🎉 *Premium active ho gaya!*\n✨ {days} din ke liye!\nSab features unlock hain. 💎",
        parse_mode="Markdown")
    except: pass
    await update.message.reply_text(f"✅ Premium set: {uid} ({days} days)")

async def cmd_removepremium(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not ctx.args: return
    await db.remove_premium(int(ctx.args[0]))
    await update.message.reply_text(f"✅ Premium removed: {ctx.args[0]}")

async def cmd_block(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not ctx.args: return
    uid = int(ctx.args[0])
    await db.block_user(uid)
    try: await ctx.bot.send_message(uid,"❌ Aapko block kar diya gaya.")
    except: pass
    await update.message.reply_text(f"✅ Blocked: {uid}")

async def cmd_unblock(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not ctx.args: return
    await db.unblock_user(int(ctx.args[0]))
    await update.message.reply_text(f"✅ Unblocked: {ctx.args[0]}")

async def cmd_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    s = await db.stats()
    from ai import GEMINI_KEY, MISTRAL_KEY, DEEPSEEK_KEY, GROQ_KEY, TOGETHER_KEY, COHERE_KEY
    api_status = (
        f"Gemini={'✅' if GEMINI_KEY else '❌'} | "
        f"Mistral={'✅' if MISTRAL_KEY else '❌'} | "
        f"DeepSeek={'✅' if DEEPSEEK_KEY else '❌'}\n"
        f"Groq={'✅' if GROQ_KEY else '❌'} | "
        f"Together={'✅' if TOGETHER_KEY else '❌'} | "
        f"Cohere={'✅' if COHERE_KEY else '❌'}"
    )
    await update.message.reply_text(
        f"📊 *IndiaStudyAI Stats*\n\n"
        f"👥 Total: {s['total']}\n"
        f"✅ Aaj active: {s['active_today']}\n"
        f"🆕 Aaj naye: {s['new_today']}\n"
        f"💎 Premium: {s['premium']}\n"
        f"🚫 Blocked: {s['blocked']}\n"
        f"❓ Questions: {s['questions']}\n"
        f"📝 Notes: {s['notes_total']}\n\n"
        f"🤖 APIs:\n{api_status}\n\n"
        f"🌐 {MINI_APP}",
        parse_mode="Markdown")

async def cmd_broadcast(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != OWNER_ID: return
    if not ctx.args: await update.message.reply_text("Usage: /broadcast <message>"); return
    msg   = " ".join(ctx.args)
    users = await db.all_users()
    sm    = await update.message.reply_text(f"📢 0/{len(users)} bhej raha hoon...")
    sent = fail = 0
    for i,u in enumerate(users):
        try:
            await ctx.bot.send_message(u["user_id"],
                f"📢 *IndiaStudyAI — Suchna:*\n\n{msg}", parse_mode="Markdown")
            sent += 1
        except: fail += 1
        if (i+1)%25==0:
            try: await sm.edit_text(f"📢 {i+1}/{len(users)} bhej diya...")
            except: pass
    await sm.edit_text(f"✅ Bheja: {sent} | ❌ Fail: {fail}")

# ══════════════════════════════════════════════════════════════════════════════
# BOT STARTUP
# ══════════════════════════════════════════════════════════════════════════════
async def post_init(app):
    await db.connect()
    sched = AsyncIOScheduler(timezone="Asia/Kolkata")
    sched.add_job(send_morning_messages,"cron",  hour=7,  minute=0,  args=[app.bot])
    sched.add_job(send_exam_reminders,  "cron",  hour=8,  minute=0,  args=[app.bot])
    sched.add_job(send_due_reminders,   "interval",minutes=5,        args=[app.bot])
    sched.start()
    log.info(f"✅ Bot ready! Mini App: {MINI_APP}")

def main():
    threading.Thread(target=run_flask, daemon=True).start()
    app = Application.builder().token(TOKEN).post_init(post_init).build()

    # ── Conversation Handler ─────────────────────────────────────────────────
    ch = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECT_CLASS: [CallbackQueryHandler(sel_class, pattern="^cl_")],
            SELECT_COURSE:[CallbackQueryHandler(sel_course,pattern="^co_")],
            SELECT_GOAL:  [CallbackQueryHandler(sel_goal,  pattern="^go_")],

            AI_TUTOR_CLASS: [
                CallbackQueryHandler(ait_class_cb, pattern="^ait_"),
                CallbackQueryHandler(back_menu,    pattern="^back_menu$"),
            ],
            AI_TUTOR_SUBJECT: [
                CallbackQueryHandler(ait_subject_cb,pattern="^ais_"),
                CallbackQueryHandler(ai_tutor_cb,   pattern="^ai_tutor$"),
                CallbackQueryHandler(back_menu,     pattern="^back_menu$"),
            ],
            AI_TUTOR_CHAT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text),
                MessageHandler(filters.PHOTO,                   handle_photo),
                CallbackQueryHandler(ait_notes_mode_cb,pattern="^ait_notes_mode$"),
                CallbackQueryHandler(save_last_ans_cb, pattern="^save_last_ans$"),
                CallbackQueryHandler(ans_to_pdf_cb,    pattern="^ans_to_pdf$"),
                CallbackQueryHandler(feedback_cb,      pattern="^fb_"),
                CallbackQueryHandler(retry_cb,         pattern="^retry_"),
                CallbackQueryHandler(set_lang_cb,      pattern="^set_lang_"),
                CallbackQueryHandler(back_menu,        pattern="^back_menu$"),
            ],

            MENU: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text),
                MessageHandler(filters.PHOTO,                   handle_photo),
                CallbackQueryHandler(ai_tutor_cb,       pattern="^ai_tutor$"),
                CallbackQueryHandler(question_cb,       pattern="^question$"),
                CallbackQueryHandler(show_updates,      pattern="^updates$"),
                CallbackQueryHandler(show_upd_cat,      pattern="^upd_"),
                CallbackQueryHandler(show_news,         pattern="^news$"),
                CallbackQueryHandler(show_news_cat,     pattern="^nws_"),
                CallbackQueryHandler(current_affairs_cb,pattern="^current_affairs$"),
                CallbackQueryHandler(ca_refresh_cb,     pattern="^ca_refresh$"),
                CallbackQueryHandler(ca_pdf_cb,         pattern="^ca_pdf$"),
                CallbackQueryHandler(qpaper_menu_cb,    pattern="^qpaper_menu$"),
                CallbackQueryHandler(qp_cls_cb,         pattern="^qp_cls_"),
                CallbackQueryHandler(qp_diff_cb,        pattern="^qp_diff_"),
                CallbackQueryHandler(study_planner_cb,  pattern="^study_planner$"),
                CallbackQueryHandler(sp_view_cb,        pattern="^sp_view$"),
                CallbackQueryHandler(sp_pdf_cb,         pattern="^sp_pdf$"),
                CallbackQueryHandler(lambda u,c: _sp_new(u.callback_query, c),
                                                        pattern="^sp_new$"),
                CallbackQueryHandler(career_guide_cb,   pattern="^career_guide$"),
                CallbackQueryHandler(mind_map_cb,       pattern="^mind_map_menu$"),
                CallbackQueryHandler(vocab_cb,          pattern="^vocab_menu$"),
                CallbackQueryHandler(ocr_mode_cb,       pattern="^ocr_mode$"),
                CallbackQueryHandler(resume_builder_cb, pattern="^resume_builder$"),
                CallbackQueryHandler(premium_info,      pattern="^premium$"),
                CallbackQueryHandler(prem_paid,         pattern="^prem_paid$"),
                CallbackQueryHandler(profile_cb,        pattern="^profile$"),
                CallbackQueryHandler(update_profile,    pattern="^update_profile$"),
                CallbackQueryHandler(leaderboard_cb,    pattern="^leaderboard$"),
                CallbackQueryHandler(refer_cb,          pattern="^refer$"),
                CallbackQueryHandler(daily_challenge_cb,pattern="^daily_challenge$"),
                CallbackQueryHandler(challenge_answer_cb,pattern="^ch_"),
                CallbackQueryHandler(set_exam_cb,       pattern="^set_exam$"),
                CallbackQueryHandler(change_exam_cb,    pattern="^change_exam$"),
                CallbackQueryHandler(settings_cb,       pattern="^settings$"),
                CallbackQueryHandler(toggle_morning_cb, pattern="^toggle_morning$"),
                CallbackQueryHandler(toggle_exam_n_cb,  pattern="^toggle_exam_n$"),
                CallbackQueryHandler(lang_menu_cb,      pattern="^lang_menu$"),
                CallbackQueryHandler(set_lang_cb,       pattern="^set_lang_"),
                CallbackQueryHandler(my_notes_cb,       pattern="^my_notes$"),
                CallbackQueryHandler(write_note_cb,     pattern="^write_note$"),
                CallbackQueryHandler(view_note_cb,      pattern="^view_note_"),
                CallbackQueryHandler(del_note_cb,       pattern="^del_note_"),
                CallbackQueryHandler(del_all_notes_cb,  pattern="^del_all_notes$"),
                CallbackQueryHandler(note_pdf_cb,       pattern="^note_pdf_"),
                CallbackQueryHandler(save_last_ans_cb,  pattern="^save_last_ans$"),
                CallbackQueryHandler(ans_to_pdf_cb,     pattern="^ans_to_pdf$"),
                CallbackQueryHandler(chat_history_cb,   pattern="^chat_history$"),
                CallbackQueryHandler(view_hist_cb,      pattern="^vh_"),
                CallbackQueryHandler(del_hist_cb,       pattern="^vhd_"),
                CallbackQueryHandler(clear_hist_cb,     pattern="^ch_clear_all$"),
                CallbackQueryHandler(set_reminder_cb,   pattern="^set_reminder$"),
                CallbackQueryHandler(ait_notes_mode_cb, pattern="^ait_notes_mode$"),
                CallbackQueryHandler(feedback_cb,       pattern="^fb_"),
                CallbackQueryHandler(retry_cb,          pattern="^retry_"),
                CallbackQueryHandler(back_menu,         pattern="^back_menu$"),
            ],

            CHATTING: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text),
                MessageHandler(filters.PHOTO,                   handle_photo),
                CallbackQueryHandler(save_last_ans_cb, pattern="^save_last_ans$"),
                CallbackQueryHandler(ans_to_pdf_cb,    pattern="^ans_to_pdf$"),
                CallbackQueryHandler(feedback_cb,      pattern="^fb_"),
                CallbackQueryHandler(retry_cb,         pattern="^retry_"),
                CallbackQueryHandler(back_menu,        pattern="^back_menu$"),
            ],

            WAIT_SS: [
                MessageHandler(filters.PHOTO,                   handle_screenshot),
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_screenshot),
                CallbackQueryHandler(back_menu,        pattern="^back_menu$"),
            ],

            SET_EXAM: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text),
                CallbackQueryHandler(back_menu,        pattern="^back_menu$"),
            ],
        },
        fallbacks=[
            CommandHandler("menu",  menu_cmd),
            CommandHandler("start", start),
        ],
        per_message=False,
        allow_reentry=True,
    )
    app.add_handler(ch)

    # Extra commands
    for cmd, fn in [
        ("menu",          menu_cmd),
        ("addpremium",    cmd_addpremium),
        ("removepremium", cmd_removepremium),
        ("block",         cmd_block),
        ("unblock",       cmd_unblock),
        ("stats",         cmd_stats),
        ("broadcast",     cmd_broadcast),
    ]:
        app.add_handler(CommandHandler(cmd, fn))

    log.info("🚀 IndiaStudyAI Bot chalu kar raha hoon...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
