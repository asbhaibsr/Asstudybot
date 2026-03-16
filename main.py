import logging,os,threading,random,asyncio
from datetime import datetime,date,timedelta
from flask import Flask,send_from_directory,jsonify
from telegram import Update,InlineKeyboardButton,InlineKeyboardMarkup,WebAppInfo
from telegram.ext import (Application,CommandHandler,CallbackQueryHandler,
    MessageHandler,filters,ContextTypes,ConversationHandler)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from db import db
from ai import ask_ai,ask_ai_simple,fetch_updates,fetch_news,get_morning_message,generate_pdf,image_to_text

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s',level=logging.INFO)
log=logging.getLogger(__name__)

TOKEN    =os.environ.get("BOT_TOKEN","YOUR_BOT_TOKEN")
OWNER_ID =int(os.environ.get("OWNER_ID","123456789"))
UPI_ID   =os.environ.get("UPI_ID","arsadsaifi8272@ibl")
PORT     =int(os.environ.get("PORT","8080"))
KOYEB_URL=os.environ.get("KOYEB_URL","https://chilly-ardath-arsadsaifi784-74d0cd5c.koyeb.app")
MINI_APP =f"{KOYEB_URL}/app"
BOT_LINK ="https://t.me/IndiaStudyAI_Bot"

flask_app=Flask(__name__,static_folder="app")
@flask_app.route("/")
def home(): return jsonify({"status":"ok"})
@flask_app.route("/health")
def health(): return jsonify({"status":"ok"}),200
@flask_app.route("/app")
@flask_app.route("/app/")
def mini_app(): return send_from_directory("app","index.html")
def run_flask(): flask_app.run(host="0.0.0.0",port=PORT,debug=False,use_reloader=False)

# States
(SELECT_CLASS,SELECT_COURSE,SELECT_GOAL,MENU,
 AI_TUTOR_CLASS,AI_TUTOR_SUBJECT,AI_TUTOR_CHAT,
 CHATTING,WAIT_SS,SET_EXAM,SET_REMINDER,SAVE_NOTE)=range(12)

CLASSES={"c1_5":"📚 Class 1-5","c6_8":"📖 Class 6-8","c9_10":"🎓 Class 9-10",
         "c11_12":"🏫 Class 11-12","college":"🎓 College","adult":"👨‍💼 Adult"}
COURSES={"math":"➕ Maths","science":"🔬 Science","hindi":"🇮🇳 Hindi",
         "english":"🔤 English","sst":"🌍 SST","computer":"💻 Computer","gk":"🧠 GK"}
GOALS={"exam":"📝 Exam Prep","skill":"💡 Skill","homework":"📋 Homework","job":"💼 Sarkari Naukri","hobby":"🎨 Hobby"}

def kb(items,prefix,cols=2):
    btns,row=[],[]
    for k,v in items.items():
        row.append(InlineKeyboardButton(v,callback_data=f"{prefix}{k}"))
        if len(row)==cols: btns.append(row);row=[]
    if row: btns.append(row)
    return InlineKeyboardMarkup(btns)

async def _del(msg):
    """Delete message safely"""
    try: await msg.delete()
    except: pass

async def _del_by_id(bot, chat_id, msg_id):
    try: await bot.delete_message(chat_id, msg_id)
    except: pass

def main_kb(premium):
    badge="💎" if premium else "🆓"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 Study Mini App",web_app=WebAppInfo(url=MINI_APP))],
        [InlineKeyboardButton("🤖 AI Study Tutor",callback_data="ai_tutor"),
         InlineKeyboardButton("❓ Quick Sawal",callback_data="question")],
        [InlineKeyboardButton("📢 Sarkari Updates",callback_data="updates"),
         InlineKeyboardButton("📰 Hindi News",callback_data="news")],
        [InlineKeyboardButton("🎯 Daily Challenge",callback_data="daily_challenge"),
         InlineKeyboardButton("🏆 Leaderboard",callback_data="leaderboard")],
        [InlineKeyboardButton("📷 Image → Text",callback_data="ocr_mode"),
         InlineKeyboardButton("📄 Resume Banao",callback_data="resume_builder")],
        [InlineKeyboardButton("📝 Meri Notes",callback_data="my_notes"),
         InlineKeyboardButton("⏰ Reminder",callback_data="set_reminder")],
        [InlineKeyboardButton("💬 Chat History",callback_data="chat_history"),
         InlineKeyboardButton("👥 Refer & Earn",callback_data="refer")],
        [InlineKeyboardButton(f"{badge} Premium ₹199/mo",callback_data="premium"),
         InlineKeyboardButton("👤 Profile",callback_data="profile")],
        [InlineKeyboardButton("🌐 Language",callback_data="lang_menu"),
         InlineKeyboardButton("⚙️ Settings",callback_data="settings")],
    ])

# ── Start ──────────────────────────────────────────────────────────────────────
async def start(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    u=update.effective_user
    if await db.is_blocked(u.id):
        await update.message.reply_text("❌ Block ho gaye."); return ConversationHandler.END
    ref_by=None
    if ctx.args and ctx.args[0].startswith("REF"):
        try: ref_by=int(ctx.args[0][3:])
        except: pass
    await db.add_user(u.id,u.first_name,u.username,ref_by=ref_by)
    if ref_by and ref_by!=u.id:
        try: await ctx.bot.send_message(ref_by,f"🎉 *{u.first_name}* ne refer link use kiya!\n+100 pts! 🏆",parse_mode="Markdown")
        except: pass
    ud=await db.get_user(u.id)
    if ud and ud.get("class_type"): return await _send_menu(update,ctx)
    msg=await update.message.reply_text(
        f"🙏 *Namaste {u.first_name}!*\n\n"
        "🤖 *@IndiaStudyAI\\_Bot* — India ka Smart Study Saathi!\n\n"
        "🎁 *50 Points joining bonus!*\n\n"
        "✅ *Features:*\n"
        "• 🤖 AI Tutor (Gemini + Mistral + DeepSeek)\n"
        "• 📢 Live Sarkari Updates (Real scraping)\n"
        "• 📰 Live Hindi News (RSS feeds)\n"
        "• 📷 Image se text nikalo (OCR)\n"
        "• 📄 Resume banao (AI se)\n"
        "• 📝 Notes save + PDF download\n"
        "• ⏰ Custom reminders\n"
        "• 🔥 Streak + Badges + Leaderboard\n\n"
        "Pehle *class* batao 👇",
        parse_mode="Markdown",reply_markup=kb(CLASSES,"cl_"))
    ctx.user_data["msgs_to_del"]=[msg.message_id]
    return SELECT_CLASS

async def sel_class(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    ctx.user_data["class_type"]=q.data[3:]
    await q.edit_message_text("✅ Class set!\n\nAb *subject* batao 👇",
        parse_mode="Markdown",reply_markup=kb(COURSES,"co_"))
    return SELECT_COURSE

async def sel_course(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    ctx.user_data["course"]=q.data[3:]
    await q.edit_message_text("✅ Subject!\n\nAb *lakshya* batao 👇",
        parse_mode="Markdown",reply_markup=kb(GOALS,"go_",1))
    return SELECT_GOAL

async def sel_goal(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    await db.update_profile(q.from_user.id,
        ctx.user_data.get("class_type"),ctx.user_data.get("course"),q.data[3:])
    await q.edit_message_text("🎉 *Profile ready!*",parse_mode="Markdown")
    ctx.user_data["mode"]="question"
    return await _send_menu(q,ctx)

async def menu_cmd(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    ctx.user_data["mode"]="question"
    return await _send_menu(update,ctx)

async def _send_menu(src,ctx):
    uid=src.effective_user.id if hasattr(src,'effective_user') else src.from_user.id
    prem=await db.is_premium(uid); ud=await db.get_user(uid)
    pts=ud.get("points",0) if ud else 0
    streak=ud.get("streak",0) if ud else 0
    streak_txt=f"🔥 {streak} din streak!" if streak>1 else "🌱 Aaj se streak shuru karo!"
    txt=(f"🏠 *Main Menu* {'💎' if prem else '🆓'}\n\n"
         f"⭐ *{pts} pts* | {streak_txt}")
    mk=main_kb(prem)
    if hasattr(src,'message') and src.message:
        sent=await src.message.reply_text(txt,parse_mode="Markdown",reply_markup=mk)
    elif hasattr(src,'edit_message_text'):
        await src.edit_message_text(txt,parse_mode="Markdown",reply_markup=mk)
        return MENU
    else:
        sent=await ctx.bot.send_message(uid,txt,parse_mode="Markdown",reply_markup=mk)
    # Store message ID for later deletion
    ctx.user_data["last_menu_id"]=sent.message_id if 'sent' in dir() else None
    return MENU

# ── AI STUDY TUTOR — Nested buttons ───────────────────────────────────────────
async def ai_tutor_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    uid=q.from_user.id; ud=await db.get_user(uid)
    # Delete previous message
    try: await q.message.delete()
    except: pass
    await ctx.bot.send_message(uid,
        "🤖 *AI Study Tutor*\n\nKaunsi class ke liye padhna hai? 👇",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📚 Class 1-5",callback_data="ait_c1_5"),
             InlineKeyboardButton("📖 Class 6-8",callback_data="ait_c6_8")],
            [InlineKeyboardButton("🎓 Class 9-10",callback_data="ait_c9_10"),
             InlineKeyboardButton("🏫 Class 11-12",callback_data="ait_c11_12")],
            [InlineKeyboardButton("🎓 College",callback_data="ait_college"),
             InlineKeyboardButton("👨‍💼 Adult/Job",callback_data="ait_adult")],
            [InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    return AI_TUTOR_CLASS

async def ait_class_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    ctx.user_data["ait_class"]=q.data.replace("ait_","")
    try: await q.message.delete()
    except: pass
    uid=q.from_user.id
    await ctx.bot.send_message(uid,
        f"✅ *{CLASSES.get(ctx.user_data['ait_class'],'')}* select hua!\n\nKaunsa subject? 👇",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Maths",callback_data="ais_math"),
             InlineKeyboardButton("🔬 Science",callback_data="ais_science")],
            [InlineKeyboardButton("🇮🇳 Hindi",callback_data="ais_hindi"),
             InlineKeyboardButton("🔤 English",callback_data="ais_english")],
            [InlineKeyboardButton("⚛️ Physics",callback_data="ais_physics"),
             InlineKeyboardButton("🧪 Chemistry",callback_data="ais_chemistry")],
            [InlineKeyboardButton("🧬 Biology",callback_data="ais_bio"),
             InlineKeyboardButton("🌍 History/SST",callback_data="ais_history")],
            [InlineKeyboardButton("💻 Computer",callback_data="ais_computer"),
             InlineKeyboardButton("🧠 GK",callback_data="ais_gk")],
            [InlineKeyboardButton("🔙 Wapas",callback_data="ai_tutor")]]))
    return AI_TUTOR_SUBJECT

async def ait_subject_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    ctx.user_data["ait_subject"]=q.data.replace("ais_","")
    uid=q.from_user.id; prem=await db.is_premium(uid)
    used_ai=await db.get_usage(uid,"ai")
    api_usage=await db.get_api_usage(uid)
    try: await q.message.delete()
    except: pass

    if not prem and used_ai>=10:
        await ctx.bot.send_message(uid,
            "⚠️ *AI limit khatam!*\nFree mein 10/din.\n\n💎 Premium lo!",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💎 Premium Lo",callback_data="premium")],
                [InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
        return MENU

    sub=ctx.user_data["ait_subject"]; cls=ctx.user_data.get("ait_class","c9_10")
    rem="∞" if prem else str(10-used_ai)

    # Show API status
    apis=[]
    from ai import GEMINI_KEY,MISTRAL_KEY,DEEPSEEK_KEY,LIMITS
    if GEMINI_KEY: apis.append(f"Gemini({LIMITS['gemini']-api_usage.get('gemini',0)} left)")
    if MISTRAL_KEY: apis.append(f"Mistral({LIMITS['mistral']-api_usage.get('mistral',0)} left)")
    if DEEPSEEK_KEY: apis.append(f"DeepSeek({LIMITS['deepseek']-api_usage.get('deepseek',0)} left)")
    if not apis: apis=["Free AI (unlimited)"]
    api_txt=" | ".join(apis)

    await ctx.bot.send_message(uid,
        f"🤖 *AI Tutor Ready!*\n"
        f"📚 {CLASSES.get(cls,cls)} | 📖 {sub.capitalize()}\n"
        f"AI: {api_txt}\n"
        f"Sawaal bache aaj: *{rem}*\n\n"
        f"Padhai ka sawaal type karo!\n"
        f"_Basic se advanced — sab samjhaunga_ 🎓\n\n"
        f"/menu — wapas",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 Notes le raha hoon",callback_data="ait_notes_mode")],
            [InlineKeyboardButton("🔙 Subject Change",callback_data=f"ait_{cls}")],
            [InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    ctx.user_data["mode"]="ai_tutor"
    ctx.user_data["mode_class"]=cls
    ctx.user_data["mode_subject"]=sub
    return AI_TUTOR_CHAT

# ── Quick Question ─────────────────────────────────────────────────────────────
async def question_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    uid=q.from_user.id; prem=await db.is_premium(uid); used=await db.get_usage(uid,"q")
    if not prem and used>=10: return await _limit_msg(q,"Sawaal",10)
    rem="∞" if prem else str(10-used)
    try: await q.message.delete()
    except: pass
    await ctx.bot.send_message(uid,
        f"❓ *Quick Sawaal Mode*\nAaj bache: *{rem}*\n\nSawal type karo!\n/menu — wapas",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    ctx.user_data["mode"]="question"; return CHATTING

async def _limit_msg(q,what,lim):
    try: await q.message.delete()
    except: pass
    uid=q.from_user.id
    await q._bot.send_message(uid,
        f"⚠️ *{what} limit khatam!*\nFree mein {lim}/din.\n\n💎 *Premium = Unlimited!*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💎 Premium Lo",callback_data="premium")],
            [InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    return MENU

# ── Handle all text messages ───────────────────────────────────────────────────
async def handle_text(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id
    if await db.is_blocked(uid): return
    txt=update.message.text
    if txt.startswith("/"): return
    mode=ctx.user_data.get("mode","question")

    # Screenshot mode
    if mode=="screenshot": return await handle_screenshot(update,ctx)

    # Exam setting modes
    if mode=="set_exam_name":
        ctx.user_data["exam_name"]=txt
        await update.message.reply_text("📅 Ab *exam date* daalo (YYYY-MM-DD):",parse_mode="Markdown")
        ctx.user_data["mode"]="set_exam_date"; return CHATTING
    if mode=="set_exam_date":
        try:
            date.fromisoformat(txt.strip())
            await db.set_exam(uid,ctx.user_data.get("exam_name","Exam"),txt.strip())
            days=max(0,(date.fromisoformat(txt.strip())-date.today()).days)
            sent=await update.message.reply_text(
                f"✅ *Exam set!*\n📅 {ctx.user_data.get('exam_name')} — {txt.strip()}\n⏳ *{days} din baaki!*",
                parse_mode="Markdown",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
            ctx.user_data["mode"]="question"; return MENU
        except:
            await update.message.reply_text("❌ Format: YYYY-MM-DD"); return CHATTING

    # Reminder modes
    if mode=="set_reminder_text":
        ctx.user_data["reminder_text"]=txt
        await update.message.reply_text(
            "⏰ Kab bhejun?\n`30m` `2h` `1d` `9am`",parse_mode="Markdown")
        ctx.user_data["mode"]="set_reminder_time"; return CHATTING
    if mode=="set_reminder_time":
        rd=_parse_reminder_time(txt.strip())
        if not rd:
            await update.message.reply_text("❌ Format: `30m`, `2h`, `1d`, `9am`",parse_mode="Markdown")
            return CHATTING
        await db.add_reminder(uid,ctx.user_data.get("reminder_text","!"),rd)
        await update.message.reply_text(
            f"✅ *Reminder set!*\n📝 {ctx.user_data.get('reminder_text')}\n⏰ {rd.strftime('%d %b, %I:%M %p')}",
            parse_mode="Markdown",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
        ctx.user_data["mode"]="question"; return MENU

    # Note saving
    if mode=="save_note_title":
        ctx.user_data["note_title"]=txt
        await update.message.reply_text("📝 Note ka *content* type karo:",parse_mode="Markdown")
        ctx.user_data["mode"]="save_note_content"; return CHATTING
    if mode=="save_note_content":
        title=ctx.user_data.get("note_title","Note")
        nid=await db.save_note(uid,title,txt)
        wa=f"https://wa.me/?text={('📝 '+title+chr(10)+chr(10)+txt[:400]+chr(10)+'— @IndiaStudyAI_Bot').replace(' ','+')}"
        await update.message.reply_text(f"✅ *Note save!*\n📝 {title}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📤 WhatsApp Share",url=wa)],
                [InlineKeyboardButton("📋 Notes dekhein",callback_data="my_notes")],
                [InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
        ctx.user_data["mode"]="question"; return MENU

    # Resume builder
    if mode=="resume_info":
        ctx.user_data["resume_data"]=txt
        wait=await update.message.reply_text("📄 Resume ban raha hai...")
        prompt=(f"Ek professional resume banao is information se:\n{txt}\n\n"
                "Format: Name, Contact, Objective, Education, Skills, Experience, Projects, Languages.\n"
                "Professional aur clean format. English mein.")
        resume_txt,api=await ask_ai(prompt,mode="resume")
        # Generate PDF
        pdf_path=await generate_pdf(f"Resume",resume_txt,"resume.pdf")
        try: await wait.delete()
        except: pass
        if pdf_path:
            with open(pdf_path,"rb") as f:
                await update.message.reply_document(f,filename="Resume_IndiaStudyAI.pdf",
                    caption="📄 *Aapka Resume ready hai!*\n\nEdit karke use karo! 🎯",
                    parse_mode="Markdown",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
        else:
            await update.message.reply_text(resume_txt,parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
        ctx.user_data["mode"]="question"; return MENU

    # AI Tutor or normal Q
    prem=await db.is_premium(uid); ud=await db.get_user(uid)
    api_usage=await db.get_api_usage(uid)

    if mode=="ai_tutor":
        kind="ai"
    else:
        kind="q"

    used=await db.get_usage(uid,kind)
    if not prem and used>=10:
        await update.message.reply_text("⚠️ Limit khatam! /menu pe jao."); return

    # Delete user's message after processing (cleaner UI)
    user_msg_id=update.message.message_id

    wait=await update.message.reply_text("🤔 Soch raha hoon...")

    # Prepare user_data for AI
    ai_ud=ud.copy() if ud else {}
    if mode=="ai_tutor":
        ai_ud["class_type"]=ctx.user_data.get("mode_class","")
        ai_ud["course"]=ctx.user_data.get("mode_subject","")

    resp,api_used=await ask_ai(txt,ai_ud,mode,api_usage)
    await db.inc_usage(uid,kind)
    if api_used in ("gemini","mistral","deepseek"):
        await db.inc_api_usage(uid,api_used)
    await db.save_q(uid,txt,resp,api_used)

    try: await wait.delete()
    except: pass
    # Delete user message for cleaner chat
    try: await ctx.bot.delete_message(uid,user_msg_id)
    except: pass

    wa=f"https://wa.me/?text={('📚 IndiaStudyAI Answer:'+chr(10)+chr(10)+resp[:400]).replace(' ','+')}"
    sent=await update.message.reply_text(resp,parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Helpful +1",callback_data="fb_good"),
             InlineKeyboardButton("❌ Dobara",callback_data=f"retry_{kind}")],
            [InlineKeyboardButton("📤 WhatsApp Share",url=wa),
             InlineKeyboardButton("📝 Note Save",callback_data="save_last_ans")],
            [InlineKeyboardButton("📄 PDF Download",callback_data="ans_to_pdf"),
             InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    ctx.user_data["last_answer"]=resp[:800]
    ctx.user_data["last_question"]=txt[:100]
    ctx.user_data["last_ans_msg_id"]=sent.message_id
    return AI_TUTOR_CHAT if mode=="ai_tutor" else CHATTING

# ── Handle Photos (OCR) ────────────────────────────────────────────────────────
async def handle_photo(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id
    if await db.is_blocked(uid): return
    mode=ctx.user_data.get("mode","question")
    if mode=="screenshot": return await handle_screenshot(update,ctx)

    wait=await update.message.reply_text("📷 Image process ho rahi hai...")
    try:
        photo=update.message.photo[-1]
        file=await ctx.bot.get_file(photo.file_id)
        path=f"/tmp/img_{uid}.jpg"
        await file.download_to_drive(path)

        # OCR
        text=await image_to_text(path)
        try: await wait.delete()
        except: pass

        if len(text) > 20:
            # Ask AI about the extracted text
            ud=await db.get_user(uid)
            api_usage=await db.get_api_usage(uid)
            prompt=f"Is image se ye text mila:\n\n{text}\n\nIs content ke baare mein explain karo aur help karo."
            resp,api_used=await ask_ai(prompt,ud,"ai",api_usage)
            await db.inc_api_usage(uid,api_used) if api_used in ("gemini","mistral","deepseek") else None

            await update.message.reply_text(
                f"📷 *Image se text nikala:*\n```\n{text[:500]}\n```\n\n"
                f"🤖 *AI ka jawab:*\n\n{resp}",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("📝 Note Save",callback_data="save_last_ans")],
                    [InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
            ctx.user_data["last_answer"]=resp
            ctx.user_data["last_question"]=f"Image text: {text[:100]}"
        else:
            await update.message.reply_text(
                "📷 Image se clearly text nahi nikal paya.\n\nClear image bhejo ya sawaal type karo!",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    except Exception as e:
        log.error(f"Photo: {e}")
        try: await wait.delete()
        except: pass
        await update.message.reply_text("❌ Image process nahi ho paayi. Dobara try karo.")

# ── OCR Mode ───────────────────────────────────────────────────────────────────
async def ocr_mode_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    try: await q.message.delete()
    except: pass
    await ctx.bot.send_message(q.from_user.id,
        "📷 *Image → Text Mode*\n\n"
        "Koi bhi image bhejo:\n"
        "• 📝 Handwritten notes\n"
        "• 📄 Printed text\n"
        "• 🖼️ Question paper\n"
        "• 📸 Board/whiteboard photo\n\n"
        "Main text nikal kar AI se explain karunga! 🤖",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    ctx.user_data["mode"]="ocr"; return CHATTING

# ── Resume Builder ─────────────────────────────────────────────────────────────
async def resume_builder_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    try: await q.message.delete()
    except: pass
    await ctx.bot.send_message(q.from_user.id,
        "📄 *AI Resume Builder*\n\n"
        "Apni details type karo:\n\n"
        "*Example:*\n"
        "Naam: Rahul Kumar\n"
        "Phone: 9876543210\n"
        "Email: rahul@gmail.com\n"
        "Education: B.Sc Computer, Delhi University 2023\n"
        "Skills: Python, MS Office, English\n"
        "Experience: Data entry 1 year\n"
        "Languages: Hindi, English\n\n"
        "_Jitni detail doge, utna achha resume banega!_ 📝",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    ctx.user_data["mode"]="resume_info"; return CHATTING

# ── PDF from answer ────────────────────────────────────────────────────────────
async def ans_to_pdf_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer("📄 PDF ban raha hai...")
    uid=q.from_user.id
    content=ctx.user_data.get("last_answer","")
    question=ctx.user_data.get("last_question","Notes")
    if not content:
        await q.answer("Koi answer nahi mila!",show_alert=True); return MENU
    path=await generate_pdf(question[:50],content)
    if path:
        try:
            with open(path,"rb") as f:
                await ctx.bot.send_document(uid,f,filename="IndiaStudyAI_Notes.pdf",
                    caption="📄 *PDF ready!*",parse_mode="Markdown")
        except Exception as e: log.error(f"PDF send: {e}")
    else:
        await q.answer("PDF nahi ban paya!",show_alert=True)
    return MENU

# ── Save last answer as note ───────────────────────────────────────────────────
async def save_last_ans_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    uid=q.from_user.id
    content=ctx.user_data.get("last_answer","")
    title=ctx.user_data.get("last_question","AI Answer")[:50]
    if content:
        await db.save_note(uid,title,content,"AI Answer")
        await q.answer("✅ Note save ho gaya!",show_alert=True)
    else:
        await q.answer("Koi answer nahi mila!",show_alert=True)
    return MENU

# ── Chat History (Premium only) ────────────────────────────────────────────────
async def chat_history_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    uid=q.from_user.id; prem=await db.is_premium(uid)
    if not prem:
        try: await q.message.delete()
        except: pass
        await ctx.bot.send_message(uid,
            "💎 *Chat History — Premium Feature*\n\n"
            "Apni pichli sabhi conversations dekho!\n"
            "2 mahine tak save rahti hain.\n\n"
            "Premium lo aur unlock karo! 🔓",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💎 Premium Lo",callback_data="premium")],
                [InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
        return MENU
    history=await db.get_chat_history(uid,15)
    if not history:
        await q.edit_message_text("💬 *Chat History*\n\nAbhi koi history nahi hai.",
            parse_mode="Markdown",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
        return MENU
    lines=["💬 *Aapki Recent Conversations*\n"]
    btns=[]
    for i,h in enumerate(history[:10]):
        q_text=h.get("question","")[:35]
        ts=h.get("ts","")[:10]
        api=h.get("api_used","")
        lines.append(f"{i+1}. _{q_text}..._\n   📅{ts} | 🤖{api}")
        btns.append([InlineKeyboardButton(f"📖 {q_text[:25]}",callback_data=f"view_hist_{str(h['_id'])}")])
    btns.append([InlineKeyboardButton("🔙 Menu",callback_data="back_menu")])
    try: await q.message.delete()
    except: pass
    await ctx.bot.send_message(uid,"\n".join(lines),parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(btns))
    return MENU

# ── Updates ────────────────────────────────────────────────────────────────────
async def show_updates(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    try: await q.message.delete()
    except: pass
    uid=q.from_user.id
    wait=await ctx.bot.send_message(uid,"⏳ Live scraping ho rahi hai...")
    # Cache check
    cached=await db.get_cache("updates_all")
    if cached:
        txt=cached+"\\n\\n_📦 Cached (1 din purana)_"
    else:
        txt=await fetch_updates("all")
        await db.set_cache("updates_all",txt,24)
    try: await wait.delete()
    except: pass
    await ctx.bot.send_message(uid,f"📢 *Sarkari Updates — Live*\n\n{txt}",
        parse_mode="Markdown",disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💼 Jobs",callback_data="upd_jobs"),
             InlineKeyboardButton("📋 Forms",callback_data="upd_forms")],
            [InlineKeyboardButton("📊 Results",callback_data="upd_results"),
             InlineKeyboardButton("🏛️ Yojana",callback_data="upd_yojana")],
            [InlineKeyboardButton("🪪 Admit Card",callback_data="upd_admit"),
             InlineKeyboardButton("🎓 Scholarship",callback_data="upd_scholar")],
            [InlineKeyboardButton("🔄 Refresh (Naya)",callback_data="upd_refresh"),
             InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    return MENU

async def show_upd_cat(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    cat=q.data.replace("upd_","")
    if cat=="refresh":
        await db.cache.delete_one({"key":"updates_all"})
        return await show_updates(update,ctx)
    labels={"jobs":"💼 Jobs","forms":"📋 Forms","results":"📊 Results",
            "yojana":"🏛️ Yojana","admit":"🪪 Admit Card","scholar":"🎓 Scholarship"}
    lbl=labels.get(cat,"Updates")
    try: await q.message.delete()
    except: pass
    uid=q.from_user.id
    wait=await ctx.bot.send_message(uid,f"⏳ {lbl} la raha hoon...")
    cache_key=f"updates_{cat}"
    cached=await db.get_cache(cache_key)
    if cached: txt=cached
    else:
        txt=await fetch_updates(cat)
        await db.set_cache(cache_key,txt,24)
    try: await wait.delete()
    except: pass
    await ctx.bot.send_message(uid,f"*{lbl} — Live*\n\n{txt}",
        parse_mode="Markdown",disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh",callback_data=f"upd_refresh_{cat}")],
            [InlineKeyboardButton("🔙 Updates",callback_data="updates")]]))
    return MENU

async def show_news(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    try: await q.message.delete()
    except: pass
    uid=q.from_user.id
    wait=await ctx.bot.send_message(uid,"📰 RSS feeds se news la raha hoon...")
    cached=await db.get_cache("news_india")
    if cached: txt=cached
    else:
        txt=await fetch_news("india")
        await db.set_cache("news_india",txt,6)
    try: await wait.delete()
    except: pass
    await ctx.bot.send_message(uid,f"📰 *Aaj Ki Khabar — Live*\n\n{txt}",
        parse_mode="Markdown",disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏛️ Rajniti",callback_data="nws_pol"),
             InlineKeyboardButton("🏏 Sports",callback_data="nws_sport")],
            [InlineKeyboardButton("💼 Business",callback_data="nws_biz"),
             InlineKeyboardButton("📚 Education",callback_data="nws_edu")],
            [InlineKeyboardButton("🔄 Refresh",callback_data="nws_refresh"),
             InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    return MENU

async def show_news_cat(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    cat=q.data.replace("nws_","")
    if cat=="refresh":
        await db.cache.delete_one({"key":"news_india"})
        return await show_news(update,ctx)
    labels={"pol":"🏛️ Rajniti","sport":"🏏 Sports","biz":"💼 Business","edu":"📚 Education"}
    lbl=labels.get(cat,"News")
    try: await q.message.delete()
    except: pass
    uid=q.from_user.id
    wait=await ctx.bot.send_message(uid,f"⏳ {lbl} la raha hoon...")
    cache_key=f"news_{cat}"
    cached=await db.get_cache(cache_key)
    if cached: txt=cached
    else:
        txt=await fetch_news(cat)
        await db.set_cache(cache_key,txt,6)
    try: await wait.delete()
    except: pass
    await ctx.bot.send_message(uid,f"*{lbl} — Live*\n\n{txt}",
        parse_mode="Markdown",disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh",callback_data=f"nws_refresh_{cat}")],
            [InlineKeyboardButton("🔙 News",callback_data="news")]]))
    return MENU

# ── Leaderboard ────────────────────────────────────────────────────────────────
async def leaderboard_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    uid=q.from_user.id
    leaders=await db.get_leaderboard(10); rank=await db.get_rank(uid)
    medals=["🥇","🥈","🥉","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
    lines=["*🏆 Top 10 — IndiaStudyAI*\n"]
    for i,u in enumerate(leaders):
        name=u.get("name","User")[:12]; pts=u.get("points",0); streak=u.get("streak",0)
        marker=" ← You!" if u["user_id"]==uid else ""
        lines.append(f"{medals[i]} *{name}* — {pts} pts 🔥{streak}{marker}")
    lines.append(f"\n📊 *Tumhara rank: #{rank}*")
    try: await q.message.delete()
    except: pass
    await ctx.bot.send_message(uid,"\n".join(lines),parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👥 Refer karo",callback_data="refer")],
            [InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    return MENU

# ── Refer ──────────────────────────────────────────────────────────────────────
async def refer_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    uid=q.from_user.id; ud=await db.get_user(uid)
    ref_count=ud.get("ref_count",0) if ud else 0
    pts=ud.get("points",0) if ud else 0
    next_r=5-(ref_count%5)
    ref_link=f"{BOT_LINK}?start=REF{uid}"
    share=f"Yaar ye bot bahut achha hai! Free mein padhai karo! 📚 {ref_link}"
    try: await q.message.delete()
    except: pass
    await ctx.bot.send_message(uid,
        f"👥 *Refer & Earn*\n\n"
        f"🔗 Tera link:\n`{ref_link}`\n\n"
        f"📊 Refer kiye: *{ref_count}* | Points: *{pts}*\n"
        f"Agle reward ke liye: *{next_r}* refer\n\n"
        f"🎁 5 refer = 7 din FREE Premium!",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 WhatsApp Share",url=f"https://wa.me/?text={share.replace(' ','+')}")]
            ,[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    return MENU

# ── Daily Challenge ────────────────────────────────────────────────────────────
async def daily_challenge_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    uid=q.from_user.id; used=await db.get_usage(uid,"challenge")
    try: await q.message.delete()
    except: pass
    if used>=1:
        await ctx.bot.send_message(uid,"✅ *Aaj ka challenge done!*\n\nKal dobara aana! 🔥",
            parse_mode="Markdown",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
        return MENU
    challenges=[
        {"q":"India ka sabse bada state (area)?","opts":["Maharashtra","Rajasthan","MP","UP"],"a":1,"cat":"GK"},
        {"q":"Newton ki 2nd law?","opts":["F=mv","F=ma","F=mg","F=m/a"],"a":1,"cat":"Physics"},
        {"q":"Photosynthesis mein kaunsi gas absorb?","opts":["O2","N2","CO2","H2"],"a":2,"cat":"Science"},
        {"q":"India mein kitne states?","opts":["25","26","28","30"],"a":2,"cat":"GK"},
        {"q":"x² - 5x + 6 ke roots?","opts":["2,3","1,6","2,4","3,4"],"a":0,"cat":"Math"},
        {"q":"Samvidhan kab lagu hua?","opts":["15 Aug 47","26 Jan 50","26 Nov 49","2 Oct 48"],"a":1,"cat":"History"},
    ]
    ch=random.choice(challenges); ctx.user_data["challenge"]=ch
    opts="\n".join([f"{chr(65+i)}. {o}" for i,o in enumerate(ch["opts"])])
    await ctx.bot.send_message(uid,
        f"🎯 *Daily Challenge!*\n🏷️ {ch['cat']}\n\n❓ *{ch['q']}*\n\n{opts}\n\n✅ Sahi = +20 pts!",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"A. {ch['opts'][0]}",callback_data="ch_0"),
             InlineKeyboardButton(f"B. {ch['opts'][1]}",callback_data="ch_1")],
            [InlineKeyboardButton(f"C. {ch['opts'][2]}",callback_data="ch_2"),
             InlineKeyboardButton(f"D. {ch['opts'][3]}",callback_data="ch_3")]]))
    return MENU

async def challenge_answer_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    uid=q.from_user.id; chosen=int(q.data[3:]); ch=ctx.user_data.get("challenge")
    if not ch: return await back_menu(update,ctx)
    await db.inc_usage(uid,"challenge")
    try: await q.message.delete()
    except: pass
    if chosen==ch["a"]:
        await db.add_points(uid,20)
        await ctx.bot.send_message(uid,
            f"✅ *Bilkul Sahi!* +20 pts! 🎉\n\nAnswer: *{ch['opts'][ch['a']]}*",
            parse_mode="Markdown",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    else:
        await ctx.bot.send_message(uid,
            f"❌ *Galat!*\nSahi: *{ch['opts'][ch['a']]}*\n\nKal dobara! 💪",
            parse_mode="Markdown",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    return MENU

# ── Notes ──────────────────────────────────────────────────────────────────────
async def my_notes_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    uid=q.from_user.id; notes=await db.get_user_notes(uid)
    try: await q.message.delete()
    except: pass
    if not notes:
        await ctx.bot.send_message(uid,
            "📝 *Meri Notes*\n\nKoi note nahi hai abhi!\n\nAI se jawab milne pe 'Note Save' dabao.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📝 Naya Note",callback_data="write_note")],
                [InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
        return MENU
    lines=["📝 *Meri Notes*\n"]; btns=[]
    for i,note in enumerate(notes):
        title=note.get("title","Note")[:30]; ts=note.get("ts","")[:10]
        lines.append(f"{i+1}. *{title}* ({ts})")
        btns.append([InlineKeyboardButton(f"📖 {title[:22]}",callback_data=f"view_note_{str(note['_id'])}")])
    btns.append([InlineKeyboardButton("📝 Naya Note",callback_data="write_note"),
                 InlineKeyboardButton("🔙 Menu",callback_data="back_menu")])
    await ctx.bot.send_message(uid,"\n".join(lines),parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(btns))
    return MENU

async def write_note_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    try: await q.message.delete()
    except: pass
    await ctx.bot.send_message(q.from_user.id,
        "📝 Note ka *title* type karo:",parse_mode="Markdown")
    ctx.user_data["mode"]="save_note_title"; return CHATTING

async def view_note_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    uid=q.from_user.id; nid=q.data.replace("view_note_","")
    note=await db.get_note(uid,nid)
    if not note: await q.answer("Nahi mila!",show_alert=True); return MENU
    title=note.get("title","Note"); content=note.get("content","")[:600]
    wa=f"https://wa.me/?text={('📝 '+title+chr(10)+content[:400]+chr(10)+'— @IndiaStudyAI_Bot').replace(' ','+')}"
    try: await q.message.delete()
    except: pass
    await ctx.bot.send_message(uid,f"📝 *{title}*\n\n{content}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 WhatsApp",url=wa),
             InlineKeyboardButton("📄 PDF",callback_data=f"note_pdf_{nid}")],
            [InlineKeyboardButton("🗑️ Delete",callback_data=f"del_note_{nid}"),
             InlineKeyboardButton("🔙 Notes",callback_data="my_notes")]]))
    return MENU

async def del_note_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    uid=q.from_user.id; nid=q.data.replace("del_note_","")
    await db.delete_note(uid,nid)
    await q.answer("🗑️ Delete ho gaya!",show_alert=True)
    return await my_notes_cb(update,ctx)

async def note_pdf_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer("📄 PDF ban raha hai...")
    uid=q.from_user.id; nid=q.data.replace("note_pdf_","")
    note=await db.get_note(uid,nid)
    if not note: return MENU
    path=await generate_pdf(note.get("title","Notes"),note.get("content",""))
    if path:
        with open(path,"rb") as f:
            await ctx.bot.send_document(uid,f,filename="IndiaStudyAI_Note.pdf",
                caption="📄 *PDF ready!*",parse_mode="Markdown")
    return MENU

# ── Reminders ──────────────────────────────────────────────────────────────────
async def set_reminder_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    try: await q.message.delete()
    except: pass
    uid=q.from_user.id; reminders=await db.get_user_reminders(uid)
    rem_txt=""
    if reminders:
        rem_txt="\n\n*Active Reminders:*\n"+"\n".join([f"• {r['text'][:25]} — {r['remind_at'][:16]}" for r in reminders])
    await ctx.bot.send_message(uid,
        f"⏰ *Reminder Set Karo*\n\nKya reminder dun?{rem_txt}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    ctx.user_data["mode"]="set_reminder_text"; return CHATTING

# ── Exam Countdown ─────────────────────────────────────────────────────────────
async def set_exam_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    uid=q.from_user.id; ud=await db.get_user(uid)
    exam_date=ud.get("exam_date") if ud else None
    try: await q.message.delete()
    except: pass
    if exam_date:
        try:
            days=max(0,(date.fromisoformat(exam_date)-date.today()).days)
            await ctx.bot.send_message(uid,
                f"📅 *Tumhara Exam*\n\n📝 {ud.get('exam_name')}\n📅 {exam_date}\n⏳ *{days} din baaki!*",
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✏️ Change",callback_data="change_exam")],
                    [InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
            return MENU
        except: pass
    await ctx.bot.send_message(uid,"📅 Exam ka *naam* type karo:",parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    ctx.user_data["mode"]="set_exam_name"; return CHATTING

async def change_exam_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    try: await q.message.delete()
    except: pass
    await ctx.bot.send_message(q.from_user.id,"✏️ Naya *exam naam* type karo:",parse_mode="Markdown")
    ctx.user_data["mode"]="set_exam_name"; return CHATTING

# ── Language ───────────────────────────────────────────────────────────────────
async def lang_menu_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    try: await q.message.delete()
    except: pass
    await ctx.bot.send_message(q.from_user.id,
        "🌐 *Language Choose Karo*",parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🇮🇳 Hindi",callback_data="set_lang_hi"),
             InlineKeyboardButton("🇬🇧 English",callback_data="set_lang_en")],
            [InlineKeyboardButton("🔀 Hinglish",callback_data="set_lang_mix")],
            [InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    return MENU

async def set_lang_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    lang=q.data.replace("set_lang_","")
    await db.update_language(q.from_user.id,lang)
    names={"hi":"Hindi 🇮🇳","en":"English 🇬🇧","mix":"Hinglish 🔀"}
    await q.answer(f"✅ {names.get(lang,lang)}",show_alert=True)
    return await back_menu(update,ctx)

# ── Settings ───────────────────────────────────────────────────────────────────
async def settings_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    uid=q.from_user.id; ud=await db.get_user(uid)
    morning=ud.get("notify_morning",True) if ud else True
    exam_n=ud.get("notify_exam",True) if ud else True
    try: await q.message.delete()
    except: pass
    await ctx.bot.send_message(uid,"⚙️ *Settings*",parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"🌅 Morning: {'✅' if morning else '❌'}",callback_data="toggle_morning")],
            [InlineKeyboardButton(f"📅 Exam: {'✅' if exam_n else '❌'}",callback_data="toggle_exam_n")],
            [InlineKeyboardButton("🌐 Language",callback_data="lang_menu")],
            [InlineKeyboardButton("✏️ Profile Update",callback_data="update_profile")],
            [InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    return MENU

async def toggle_morning_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    ud=await db.get_user(q.from_user.id)
    nv=not ud.get("notify_morning",True) if ud else False
    await db.update_settings(q.from_user.id,notify_morning=nv)
    await q.answer(f"Morning {'ON ✅' if nv else 'OFF ❌'}",show_alert=True)
    return await settings_cb(update,ctx)

async def toggle_exam_n_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    ud=await db.get_user(q.from_user.id)
    nv=not ud.get("notify_exam",True) if ud else False
    await db.update_settings(q.from_user.id,notify_exam=nv)
    await q.answer(f"Exam reminder {'ON ✅' if nv else 'OFF ❌'}",show_alert=True)
    return await settings_cb(update,ctx)

# ── Premium ────────────────────────────────────────────────────────────────────
async def premium_info(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    try: await q.message.delete()
    except: pass
    await ctx.bot.send_message(q.from_user.id,
        "💎 *Premium — ₹199/month*\n\n"
        "✅ Unlimited AI (Gemini+Mistral+DeepSeek)\n"
        "✅ Chat History (2 mahine)\n"
        "✅ Unlimited sawaal\n"
        "✅ Unlimited notes + PDF\n"
        "✅ Resume builder\n\n"
        f"━━━━━━━━━━\n💳 UPI: `{UPI_ID}`\n💰 ₹199\n━━━━━━━━━━\n\n"
        "1️⃣ ₹199 bhejo  2️⃣ Screenshot lo  3️⃣ Button dabao\n\n"
        "💡 *FREE:* 5 refer karo = 7 din premium!",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Pay kar diya",callback_data="prem_paid")],
            [InlineKeyboardButton("👥 Refer karke FREE lo",callback_data="refer")],
            [InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    return MENU

async def prem_paid(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    try: await q.message.delete()
    except: pass
    await ctx.bot.send_message(q.from_user.id,
        "📸 *Screenshot Bhejo!*\n\n1-2 ghante mein activate hoga! 🔔",
        parse_mode="Markdown")
    ctx.user_data["mode"]="screenshot"; return WAIT_SS

async def handle_screenshot(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id; u=update.effective_user
    cap=f"💳 *Premium!*\n👤 {u.first_name}\n🆔 `{uid}`\n@{u.username or 'N/A'}\n\n`/addpremium {uid}`"
    try:
        if update.message.photo:
            await ctx.bot.forward_message(OWNER_ID,update.message.chat_id,update.message.message_id)
        await ctx.bot.send_message(OWNER_ID,cap,parse_mode="Markdown")
    except Exception as e: log.error(f"Fwd: {e}")
    await update.message.reply_text("✅ Request bhej di! 1-2 ghante mein active hoga.")
    ctx.user_data["mode"]="question"; return MENU

# ── Profile ────────────────────────────────────────────────────────────────────
async def profile_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    uid=q.from_user.id; ud=await db.get_user(uid); prem=await db.is_premium(uid)
    cl=CLASSES.get(ud.get("class_type",""),"N/A") if ud else "N/A"
    co=COURSES.get(ud.get("course",""),"N/A") if ud else "N/A"
    pts=ud.get("points",0) if ud else 0; streak=ud.get("streak",0) if ud else 0
    max_s=ud.get("max_streak",0) if ud else 0; tq=ud.get("total_q",0) if ud else 0
    badges=ud.get("badges",[]) if ud else []; rank=await db.get_rank(uid)
    ref_count=ud.get("ref_count",0) if ud else 0
    try: await q.message.delete()
    except: pass
    await ctx.bot.send_message(uid,
        f"👤 *Meri Profile*\n\n"
        f"📚 {cl} | 📖 {co}\n"
        f"💎 {'Premium ✨' if prem else 'Free'}\n\n"
        f"⭐ Points: *{pts}* | Rank: *#{rank}*\n"
        f"🔥 Streak: *{streak}* | Best: *{max_s}*\n"
        f"👥 Referrals: *{ref_count}*\n"
        f"🏅 {' '.join(badges[:3]) if badges else '—'}\n"
        f"📈 Total Sawaal: *{tq}*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✏️ Profile Update",callback_data="update_profile")],
            [InlineKeyboardButton("📝 Meri Notes",callback_data="my_notes"),
             InlineKeyboardButton("💬 History",callback_data="chat_history")],
            [InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    return MENU

async def back_menu(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    ctx.user_data["mode"]="question"
    return await _send_menu(q,ctx)

async def update_profile(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    try: await q.message.delete()
    except: pass
    await ctx.bot.send_message(q.from_user.id,
        "✏️ Class dobara select karo:",reply_markup=kb(CLASSES,"cl_"))
    return SELECT_CLASS

async def feedback_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query
    if q.data=="fb_good":
        await q.answer("✅ Shukriya! +1 pt!"); await db.add_points(q.from_user.id,1)
    else:
        await q.answer("📝 Feedback noted!")
    return MENU

async def retry_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    kind=q.data.replace("retry_",""); ctx.user_data["mode"]="ai_tutor" if kind=="ai" else "question"
    try: await q.message.delete()
    except: pass
    await ctx.bot.send_message(q.from_user.id,"🔄 Dobara type karo!",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    return AI_TUTOR_CHAT if kind=="ai" else CHATTING

async def ait_notes_mode_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer("📝 Notes mode ON!")
    ctx.user_data["save_to_notes"]=True; return AI_TUTOR_CHAT

def _parse_reminder_time(txt:str):
    from datetime import datetime,timedelta
    now=datetime.now()
    try:
        if txt.endswith('m'): return now+timedelta(minutes=int(txt[:-1]))
        if txt.endswith('h'): return now+timedelta(hours=int(txt[:-1]))
        if txt.endswith('d'): return now+timedelta(days=int(txt[:-1]))
        if 'am' in txt.lower() or 'pm' in txt.lower():
            t=datetime.strptime(txt.upper().replace(' ',''),
                "%I%p" if len(txt.strip())<=3 else "%I:%M%p")
            return now.replace(hour=t.hour,minute=t.minute,second=0,microsecond=0)
    except: pass
    return None

# ── Scheduled Jobs ─────────────────────────────────────────────────────────────
async def send_morning_messages(bot):
    users=await db.morning_notify_users(); sent=0
    for u in users:
        try:
            ud=await db.get_user(u["user_id"])
            msg=await get_morning_message(ud.get("name","Student") if ud else "Student",
                                          ud.get("streak",0) if ud else 0)
            await bot.send_message(u["user_id"],msg,parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🎯 Daily Challenge",callback_data="daily_challenge"),
                     InlineKeyboardButton("📱 Study App",web_app=WebAppInfo(url=MINI_APP))],
                    [InlineKeyboardButton("📢 Updates",callback_data="updates")]]))
            sent+=1
        except: pass
    log.info(f"✅ Morning: {sent}")

async def send_exam_reminders(bot):
    for r in await db.get_exam_reminders():
        try:
            d=r["days_left"]; n=r.get("exam_name","Exam")
            msgs={1:f"⚠️ *Kal hai {n}!* Best of luck! 🍀",
                  7:f"📅 *{n} — 7 din baaki!* Revision! 📚",
                  30:f"📅 *{n} — 30 din baaki!* Preparation! 💪"}
            await bot.send_message(r["user_id"],msgs.get(d,f"📅 {n} — {d} din!"),parse_mode="Markdown")
        except: pass

async def send_due_reminders(bot):
    for r in await db.get_due_reminders():
        try:
            await bot.send_message(r["user_id"],f"⏰ *Reminder!*\n\n{r['text']}",parse_mode="Markdown")
            await db.mark_reminder_sent(str(r["_id"]))
        except: pass

# ── Admin ──────────────────────────────────────────────────────────────────────
async def cmd_addpremium(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!=OWNER_ID: return
    if not ctx.args: await update.message.reply_text("Usage: /addpremium <id> [days]"); return
    uid=int(ctx.args[0]); days=int(ctx.args[1]) if len(ctx.args)>1 else 30
    await db.set_premium(uid,days)
    try: await ctx.bot.send_message(uid,"🎉 *Premium active!*",parse_mode="Markdown")
    except: pass
    await update.message.reply_text(f"✅ Premium: {uid} ({days} days)")

async def cmd_removepremium(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!=OWNER_ID: return
    if not ctx.args: return
    uid=int(ctx.args[0]); await db.remove_premium(uid)
    await update.message.reply_text(f"✅ Removed: {uid}")

async def cmd_block(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!=OWNER_ID: return
    if not ctx.args: return
    uid=int(ctx.args[0]); await db.block_user(uid)
    try: await ctx.bot.send_message(uid,"❌ Block.")
    except: pass
    await update.message.reply_text(f"✅ Blocked {uid}")

async def cmd_unblock(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!=OWNER_ID: return
    if not ctx.args: return
    uid=int(ctx.args[0]); await db.unblock_user(uid)
    await update.message.reply_text(f"✅ Unblocked {uid}")

async def cmd_stats(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!=OWNER_ID: return
    s=await db.stats()
    await update.message.reply_text(
        f"📊 *Stats*\n👥 {s['total']} | 💎 {s['premium']}\n"
        f"✅ Today: {s['active_today']} | 📝 Notes: {s['notes_total']}\n"
        f"❓ Q: {s['questions']} | 🚫 {s['blocked']}\n\n"
        f"APIs: Gemini={'✅' if os.environ.get('GEMINI_API_KEY') else '❌'} | "
        f"Mistral={'✅' if os.environ.get('MISTRAL_API_KEY') else '❌'} | "
        f"DeepSeek={'✅' if os.environ.get('DEEPSEEK_API_KEY') else '❌'}\n\n"
        f"🌐 {MINI_APP}",
        parse_mode="Markdown")

async def cmd_broadcast(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!=OWNER_ID: return
    if not ctx.args: return
    msg=" ".join(ctx.args); users=await db.all_users()
    sm=await update.message.reply_text(f"📢 0/{len(users)}")
    sent=fail=0
    for i,u in enumerate(users):
        try: await ctx.bot.send_message(u["user_id"],f"📢 *Suchna:*\n\n{msg}",parse_mode="Markdown"); sent+=1
        except: fail+=1
        if (i+1)%25==0:
            try: await sm.edit_text(f"📢 {i+1}/{len(users)}")
            except: pass
    await sm.edit_text(f"✅ {sent} | ❌ {fail}")

async def post_init(app):
    await db.connect()
    sched=AsyncIOScheduler(timezone="Asia/Kolkata")
    sched.add_job(send_morning_messages,"cron",hour=7,minute=0,args=[app.bot])
    sched.add_job(send_exam_reminders,"cron",hour=8,minute=0,args=[app.bot])
    sched.add_job(send_due_reminders,"interval",minutes=5,args=[app.bot])
    sched.start()
    log.info(f"✅ Ready! {MINI_APP}")

def main():
    threading.Thread(target=run_flask,daemon=True).start()
    app=Application.builder().token(TOKEN).post_init(post_init).build()
    ch=ConversationHandler(
        entry_points=[CommandHandler("start",start)],
        states={
            SELECT_CLASS:[CallbackQueryHandler(sel_class,pattern="^cl_")],
            SELECT_COURSE:[CallbackQueryHandler(sel_course,pattern="^co_")],
            SELECT_GOAL:[CallbackQueryHandler(sel_goal,pattern="^go_")],
            AI_TUTOR_CLASS:[
                CallbackQueryHandler(ait_class_cb,pattern="^ait_"),
                CallbackQueryHandler(back_menu,pattern="^back_menu$"),
            ],
            AI_TUTOR_SUBJECT:[
                CallbackQueryHandler(ait_subject_cb,pattern="^ais_"),
                CallbackQueryHandler(ai_tutor_cb,pattern="^ai_tutor$"),
                CallbackQueryHandler(back_menu,pattern="^back_menu$"),
            ],
            AI_TUTOR_CHAT:[
                MessageHandler(filters.TEXT&~filters.COMMAND,handle_text),
                MessageHandler(filters.PHOTO,handle_photo),
                CallbackQueryHandler(ait_notes_mode_cb,pattern="^ait_notes_mode$"),
                CallbackQueryHandler(save_last_ans_cb,pattern="^save_last_ans$"),
                CallbackQueryHandler(ans_to_pdf_cb,pattern="^ans_to_pdf$"),
                CallbackQueryHandler(feedback_cb,pattern="^fb_"),
                CallbackQueryHandler(retry_cb,pattern="^retry_"),
                CallbackQueryHandler(back_menu,pattern="^back_menu$"),
            ],
            MENU:[
                CallbackQueryHandler(ai_tutor_cb,pattern="^ai_tutor$"),
                CallbackQueryHandler(question_cb,pattern="^question$"),
                CallbackQueryHandler(show_updates,pattern="^updates$"),
                CallbackQueryHandler(show_upd_cat,pattern="^upd_"),
                CallbackQueryHandler(show_news,pattern="^news$"),
                CallbackQueryHandler(show_news_cat,pattern="^nws_"),
                CallbackQueryHandler(premium_info,pattern="^premium$"),
                CallbackQueryHandler(prem_paid,pattern="^prem_paid$"),
                CallbackQueryHandler(profile_cb,pattern="^profile$"),
                CallbackQueryHandler(back_menu,pattern="^back_menu$"),
                CallbackQueryHandler(update_profile,pattern="^update_profile$"),
                CallbackQueryHandler(leaderboard_cb,pattern="^leaderboard$"),
                CallbackQueryHandler(refer_cb,pattern="^refer$"),
                CallbackQueryHandler(daily_challenge_cb,pattern="^daily_challenge$"),
                CallbackQueryHandler(challenge_answer_cb,pattern="^ch_"),
                CallbackQueryHandler(set_exam_cb,pattern="^set_exam$"),
                CallbackQueryHandler(change_exam_cb,pattern="^change_exam$"),
                CallbackQueryHandler(settings_cb,pattern="^settings$"),
                CallbackQueryHandler(toggle_morning_cb,pattern="^toggle_morning$"),
                CallbackQueryHandler(toggle_exam_n_cb,pattern="^toggle_exam_n$"),
                CallbackQueryHandler(lang_menu_cb,pattern="^lang_menu$"),
                CallbackQueryHandler(set_lang_cb,pattern="^set_lang_"),
                CallbackQueryHandler(my_notes_cb,pattern="^my_notes$"),
                CallbackQueryHandler(write_note_cb,pattern="^write_note$"),
                CallbackQueryHandler(save_last_ans_cb,pattern="^save_last_ans$"),
                CallbackQueryHandler(view_note_cb,pattern="^view_note_"),
                CallbackQueryHandler(del_note_cb,pattern="^del_note_"),
                CallbackQueryHandler(note_pdf_cb,pattern="^note_pdf_"),
                CallbackQueryHandler(set_reminder_cb,pattern="^set_reminder$"),
                CallbackQueryHandler(ocr_mode_cb,pattern="^ocr_mode$"),
                CallbackQueryHandler(resume_builder_cb,pattern="^resume_builder$"),
                CallbackQueryHandler(ans_to_pdf_cb,pattern="^ans_to_pdf$"),
                CallbackQueryHandler(chat_history_cb,pattern="^chat_history$"),
                CallbackQueryHandler(feedback_cb,pattern="^fb_"),
                CallbackQueryHandler(retry_cb,pattern="^retry_"),
                MessageHandler(filters.TEXT&~filters.COMMAND,handle_text),
                MessageHandler(filters.PHOTO,handle_photo),
            ],
            CHATTING:[
                MessageHandler(filters.TEXT&~filters.COMMAND,handle_text),
                MessageHandler(filters.PHOTO,handle_photo),
                CallbackQueryHandler(back_menu,pattern="^back_menu$"),
                CallbackQueryHandler(save_last_ans_cb,pattern="^save_last_ans$"),
                CallbackQueryHandler(ans_to_pdf_cb,pattern="^ans_to_pdf$"),
                CallbackQueryHandler(feedback_cb,pattern="^fb_"),
                CallbackQueryHandler(retry_cb,pattern="^retry_"),
            ],
            WAIT_SS:[
                MessageHandler(filters.PHOTO,handle_screenshot),
                MessageHandler(filters.TEXT&~filters.COMMAND,handle_screenshot),
                CallbackQueryHandler(back_menu,pattern="^back_menu$"),
            ],
            SET_EXAM:[
                MessageHandler(filters.TEXT&~filters.COMMAND,handle_text),
                CallbackQueryHandler(back_menu,pattern="^back_menu$"),
            ],
            SET_REMINDER:[
                MessageHandler(filters.TEXT&~filters.COMMAND,handle_text),
                CallbackQueryHandler(back_menu,pattern="^back_menu$"),
            ],
            SAVE_NOTE:[
                MessageHandler(filters.TEXT&~filters.COMMAND,handle_text),
                CallbackQueryHandler(back_menu,pattern="^back_menu$"),
            ],
        },
        fallbacks=[CommandHandler("menu",menu_cmd),CommandHandler("start",start)],
        per_message=False,
    )
    app.add_handler(ch)
    for cmd,fn in [("menu",menu_cmd),("addpremium",cmd_addpremium),
        ("removepremium",cmd_removepremium),("block",cmd_block),
        ("unblock",cmd_unblock),("stats",cmd_stats),("broadcast",cmd_broadcast)]:
        app.add_handler(CommandHandler(cmd,fn))
    log.info("🚀 Chalu!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__=="__main__":
    main()
