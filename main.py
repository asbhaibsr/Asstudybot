import logging,os,threading,random
from datetime import datetime,date,timedelta
from flask import Flask,send_from_directory,jsonify
from telegram import Update,InlineKeyboardButton,InlineKeyboardMarkup,WebAppInfo
from telegram.ext import (Application,CommandHandler,CallbackQueryHandler,
    MessageHandler,filters,ContextTypes,ConversationHandler)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from db import db
from ai import ask_ai,get_updates_text,get_news_text,get_morning_message

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
def home(): return jsonify({"status":"ok","app":"/app"})
@flask_app.route("/health")
def health(): return jsonify({"status":"ok"}),200
@flask_app.route("/app")
@flask_app.route("/app/")
def mini_app(): return send_from_directory("app","index.html")
def run_flask(): flask_app.run(host="0.0.0.0",port=PORT,debug=False,use_reloader=False)

SELECT_CLASS,SELECT_COURSE,SELECT_GOAL,MENU,CHATTING,WAIT_SS,SET_EXAM,SET_REMINDER,SAVE_NOTE=range(9)
CLASSES={"c1_5":"📚 Class 1-5","c6_8":"📖 Class 6-8","c9_10":"🎓 Class 9-10","c11_12":"🏫 Class 11-12","college":"🎓 College","adult":"👨‍💼 Adult"}
COURSES={"math":"➕ Maths","science":"🔬 Science","hindi":"🇮🇳 Hindi","english":"🔤 English","sst":"🌍 SST/History","computer":"💻 Computer","gk":"🧠 GK"}
GOALS={"exam":"📝 Exam Prep","skill":"💡 Skill Seekhna","homework":"📋 Homework","job":"💼 Sarkari Naukri","hobby":"🎨 Hobby"}

# Text translations
T={
    "hi":{"welcome":"Namaste","study":"📚 Sabhi Subjects","ai":"🤖 AI Tutor","updates":"📢 Sarkari Updates","news":"📰 Hindi News","ask":"Sawaal type karo","thinking":"🤔 Soch raha hoon...","searching":"🔍 Jawab dhundh raha hoon...","limit":"⚠️ Limit khatam! /menu se premium lo."},
    "en":{"welcome":"Welcome","study":"📚 All Subjects","ai":"🤖 AI Tutor","updates":"📢 Govt Updates","news":"📰 News","ask":"Type your question","thinking":"🤔 Thinking...","searching":"🔍 Searching for answer...","limit":"⚠️ Limit reached! Get premium from /menu."}
}

def t(uid_or_lang, key):
    lang = uid_or_lang if isinstance(uid_or_lang,str) else "hi"
    return T.get(lang,T["hi"]).get(key,"")

def kb(items,prefix,cols=2):
    btns,row=[],[]
    for k,v in items.items():
        row.append(InlineKeyboardButton(v,callback_data=f"{prefix}{k}"))
        if len(row)==cols: btns.append(row);row=[]
    if row: btns.append(row)
    return InlineKeyboardMarkup(btns)

def main_kb(premium,lang="hi"):
    badge="💎" if premium else "🆓"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 Study App Kholein",web_app=WebAppInfo(url=MINI_APP))],
        [InlineKeyboardButton("🤖 AI Tutor",callback_data="ai"),
         InlineKeyboardButton("❓ Sawal Poochho",callback_data="question")],
        [InlineKeyboardButton("📢 Sarkari Updates",callback_data="updates"),
         InlineKeyboardButton("📰 Hindi News",callback_data="news")],
        [InlineKeyboardButton("🏆 Leaderboard",callback_data="leaderboard"),
         InlineKeyboardButton("👥 Refer & Earn",callback_data="refer")],
        [InlineKeyboardButton("🎯 Daily Challenge",callback_data="daily_challenge"),
         InlineKeyboardButton("📅 Exam Countdown",callback_data="set_exam")],
        [InlineKeyboardButton("📝 Meri Notes",callback_data="my_notes"),
         InlineKeyboardButton("⏰ Reminder Set Karo",callback_data="set_reminder")],
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
        try: await ctx.bot.send_message(ref_by,f"🎉 *{u.first_name}* ne refer link use kiya! +100 pts! 🏆",parse_mode="Markdown")
        except: pass
    ud=await db.get_user(u.id)
    if ud and ud.get("class_type"): return await _send_menu(update,ctx)
    await update.message.reply_text(
        f"🙏 *Namaste {u.first_name}!*\n\n"
        "🤖 *@IndiaStudyAI\\_Bot* — India ka #1 Free Study Bot!\n\n"
        "🎁 *Joining Bonus: 50 Points!*\n\n"
        "✅ *FREE mein milega:*\n"
        "• 📚 Sabhi Subjects — 8 Free AI Sources\n"
        "• 🤖 AI Tutor — 10 sawaal/din\n"
        "• 📢 Real Sarkari Updates (Scraped Live!)\n"
        "• 📰 Live Hindi News (RSS Feeds)\n"
        "• 🎯 Daily Challenge + Leaderboard\n"
        "• 📝 Notes Save/Download\n"
        "• ⏰ Custom Reminders\n"
        "• 👥 Refer → Free Premium!\n\n"
        "Pehle *class* batao 👇",
        parse_mode="Markdown",reply_markup=kb(CLASSES,"cl_"))
    return SELECT_CLASS

async def sel_class(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    ctx.user_data["class_type"]=q.data[3:]
    await q.edit_message_text("✅ Class set!\nAb *subject* batao 👇",parse_mode="Markdown",reply_markup=kb(COURSES,"co_"))
    return SELECT_COURSE

async def sel_course(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    ctx.user_data["course"]=q.data[3:]
    await q.edit_message_text("✅ Subject!\nAb *lakshya* batao 👇",parse_mode="Markdown",reply_markup=kb(GOALS,"go_",1))
    return SELECT_GOAL

async def sel_goal(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    await db.update_profile(q.from_user.id,ctx.user_data.get("class_type"),ctx.user_data.get("course"),q.data[3:])
    await q.edit_message_text("🎉 *Profile ready!*",parse_mode="Markdown")
    ctx.user_data["mode"]="question"
    return await _send_menu(q,ctx)

async def menu_cmd(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    ctx.user_data["mode"]="question"; return await _send_menu(update,ctx)

async def _send_menu(src,ctx):
    uid=src.effective_user.id if hasattr(src,'effective_user') else src.from_user.id
    prem=await db.is_premium(uid); ud=await db.get_user(uid)
    pts=ud.get("points",0) if ud else 0
    streak=ud.get("streak",0) if ud else 0
    lang=ud.get("language","hi") if ud else "hi"
    streak_txt=f"🔥 {streak} din streak!" if streak>1 else "🌱 Streak shuru karo!"
    txt=(f"🏠 *Main Menu* {'💎 Premium' if prem else '🆓 Free'}\n\n"
         f"⭐ Points: *{pts}* | {streak_txt}\n\n"
         "📱 Study App — 8 AI sources + Live news\n"
         "📢 Updates — Real scraping se live data\n"
         "📝 Notes — Save & WhatsApp share\n"
         "⏰ Reminders — Custom alerts set karo")
    mk=main_kb(prem,lang)
    if hasattr(src,'message') and src.message:
        await src.message.reply_text(txt,parse_mode="Markdown",reply_markup=mk)
    elif hasattr(src,'edit_message_text'):
        await src.edit_message_text(txt,parse_mode="Markdown",reply_markup=mk)
    else:
        await ctx.bot.send_message(uid,txt,parse_mode="Markdown",reply_markup=mk)
    return MENU

# ── Language Menu ──────────────────────────────────────────────────────────────
async def lang_menu_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    await q.edit_message_text(
        "🌐 *Language / Bhasha Chunein*\n\nApni pasandida bhasha chunein:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🇮🇳 Hindi",callback_data="set_lang_hi"),
             InlineKeyboardButton("🇬🇧 English",callback_data="set_lang_en")],
            [InlineKeyboardButton("🔀 Hinglish (Mix)",callback_data="set_lang_mix")],
            [InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    return MENU

async def set_lang_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    lang=q.data.replace("set_lang_","")
    await db.update_language(q.from_user.id,lang)
    names={"hi":"Hindi 🇮🇳","en":"English 🇬🇧","mix":"Hinglish 🔀"}
    await q.answer(f"✅ Language set: {names.get(lang,lang)}",show_alert=True)
    return await back_menu(update,ctx)

# ── AI / Question ──────────────────────────────────────────────────────────────
async def ai_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    uid=q.from_user.id; prem=await db.is_premium(uid); used=await db.get_usage(uid,"ai")
    if not prem and used>=10: return await _limit_msg(q,"AI Tutor",10)
    rem="∞" if prem else str(10-used)
    await q.edit_message_text(
        f"🤖 *AI Tutor*\nAaj bache: *{rem}* sawaal\n\n"
        "8 free AI sources use kar raha hoon!\n"
        "Math, Science, GK, Career — sab poochho!\n_Sirf padhai topics_\n/menu — wapas",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    ctx.user_data["mode"]="ai"; return CHATTING

async def question_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    uid=q.from_user.id; prem=await db.is_premium(uid); used=await db.get_usage(uid,"q")
    if not prem and used>=10: return await _limit_msg(q,"Sawaal",10)
    rem="∞" if prem else str(10-used)
    await q.edit_message_text(
        f"❓ *Sawaal Mode*\nAaj bache: *{rem}*\n\nSawal type karo!\n/menu — wapas",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    ctx.user_data["mode"]="question"; return CHATTING

async def _limit_msg(q,what,lim):
    await q.edit_message_text(
        f"⚠️ *{what} limit khatam!*\nFree mein {lim}/din.\n\n💎 *Premium = Unlimited!*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💎 Premium Lo",callback_data="premium")],
            [InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    return MENU

async def handle_text(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id
    if await db.is_blocked(uid): return
    txt=update.message.text
    if txt.startswith("/"): return
    mode=ctx.user_data.get("mode","question")

    # Mode handlers
    if mode=="screenshot": return await handle_screenshot(update,ctx)
    if mode=="set_exam_name":
        ctx.user_data["exam_name"]=txt
        await update.message.reply_text("📅 Ab *exam date* daalo (YYYY-MM-DD):",parse_mode="Markdown")
        ctx.user_data["mode"]="set_exam_date"; return CHATTING
    if mode=="set_exam_date":
        try:
            date.fromisoformat(txt.strip())
            await db.set_exam(uid,ctx.user_data.get("exam_name","Exam"),txt.strip())
            days=max(0,(date.fromisoformat(txt.strip())-date.today()).days)
            await update.message.reply_text(
                f"✅ *Exam set!*\n📅 {ctx.user_data.get('exam_name')} — {txt.strip()}\n⏳ *{days} din baaki!*\n\nReminder milega 30, 7, 1 din pehle! 🔔",
                parse_mode="Markdown",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
            ctx.user_data["mode"]="question"; return MENU
        except:
            await update.message.reply_text("❌ Format: YYYY-MM-DD (jaise 2026-05-15)"); return CHATTING
    if mode=="set_reminder_text":
        ctx.user_data["reminder_text"]=txt
        await update.message.reply_text(
            "⏰ Reminder kab bhejun?\n\nExamples:\n`30m` — 30 minute baad\n`2h` — 2 ghante baad\n`1d` — kal\n`9am` — aaj 9 baje",
            parse_mode="Markdown")
        ctx.user_data["mode"]="set_reminder_time"; return CHATTING
    if mode=="set_reminder_time":
        remind_dt = _parse_reminder_time(txt.strip())
        if not remind_dt:
            await update.message.reply_text("❌ Format samajh nahi aaya. Try: `30m`, `2h`, `1d`, `9am`",parse_mode="Markdown")
            return CHATTING
        await db.add_reminder(uid,ctx.user_data.get("reminder_text","Reminder!"),remind_dt)
        await update.message.reply_text(
            f"✅ *Reminder set!*\n📝 {ctx.user_data.get('reminder_text')}\n⏰ {remind_dt.strftime('%d %b %Y, %I:%M %p')}",
            parse_mode="Markdown",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
        ctx.user_data["mode"]="question"; return MENU
    if mode=="save_note_title":
        ctx.user_data["note_title"]=txt
        await update.message.reply_text("📝 Ab note ka *content* type karo:",parse_mode="Markdown")
        ctx.user_data["mode"]="save_note_content"; return CHATTING
    if mode=="save_note_content":
        title=ctx.user_data.get("note_title","Note")
        subj=ctx.user_data.get("note_subject","General")
        note_id=await db.save_note(uid,title,txt,subj)
        share_text=f"📝 *{title}*\n\n{txt[:500]}\n\n— @IndiaStudyAI_Bot"
        wa_url=f"https://wa.me/?text={share_text.replace(' ','+')[:500]}"
        await update.message.reply_text(
            f"✅ *Note save ho gaya!*\n📝 Title: {title}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📤 WhatsApp Share",url=wa_url)],
                [InlineKeyboardButton("📋 Meri Notes",callback_data="my_notes")],
                [InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
        ctx.user_data["mode"]="question"; return MENU

    # Normal AI/Question mode
    prem=await db.is_premium(uid); ud=await db.get_user(uid)
    kind="ai" if mode=="ai" else "q"
    used=await db.get_usage(uid,kind)
    if not prem and used>=10:
        await update.message.reply_text("⚠️ Limit khatam! /menu pe jao."); return
    lang=ud.get("language","hi") if ud else "hi"
    wait=await update.message.reply_text(
        "🤖 8 AI sources try kar raha hoon..." if mode=="ai" else "🔍 Jawab dhundh raha hoon...")
    resp=await ask_ai(txt,ud,mode)
    await db.inc_usage(uid,kind); await db.save_q(uid,txt,resp)
    try: await wait.delete()
    except: pass
    # WhatsApp share option for answers
    share_url=f"https://wa.me/?text={('📚 IndiaStudyAI Answer:\n\n'+resp[:400]).replace(' ','+')}"
    await update.message.reply_text(resp,parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Helpful",callback_data="fb_good"),
             InlineKeyboardButton("❌ Better Chahiye",callback_data="fb_bad")],
            [InlineKeyboardButton("📤 WhatsApp Share",url=share_url),
             InlineKeyboardButton("📝 Note Save Karo",callback_data=f"save_ans_{uid}")],
            [InlineKeyboardButton("🔄 Dobara",callback_data=f"retry_{kind}"),
             InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    ctx.user_data["last_answer"]=resp[:500]
    ctx.user_data["last_question"]=txt[:100]
    return CHATTING

def _parse_reminder_time(txt:str) -> datetime:
    """Parse reminder time from user input"""
    from datetime import datetime,timedelta
    now=datetime.now()
    try:
        if txt.endswith('m'): return now+timedelta(minutes=int(txt[:-1]))
        if txt.endswith('h'): return now+timedelta(hours=int(txt[:-1]))
        if txt.endswith('d'): return now+timedelta(days=int(txt[:-1]))
        if 'am' in txt.lower() or 'pm' in txt.lower():
            t=datetime.strptime(txt.upper().replace(' ',''),"%I%p" if len(txt)<=3 else "%I:%M%p")
            return now.replace(hour=t.hour,minute=t.minute,second=0,microsecond=0)
    except: pass
    return None

# ── Notes System ───────────────────────────────────────────────────────────────
async def my_notes_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    uid=q.from_user.id; notes=await db.get_user_notes(uid)
    if not notes:
        await q.edit_message_text(
            "📝 *Meri Notes*\n\nAbhi koi note save nahi hai!\n\nBot se koi bhi jawab mile to 'Note Save Karo' button dabao.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📝 Naya Note Likho",callback_data="write_note")],
                [InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
        return MENU
    lines=["📝 *Meri Notes*\n"]
    btns=[]
    for i,note in enumerate(notes):
        title=note.get("title","Note")[:30]
        ts=note.get("ts","")[:10]
        subj=note.get("subject","")
        lines.append(f"{i+1}. *{title}* — {subj} ({ts})")
        note_id=str(note.get("_id",""))
        btns.append([InlineKeyboardButton(f"📖 {title[:20]}",callback_data=f"view_note_{note_id}")])
    btns.append([InlineKeyboardButton("📝 Naya Note",callback_data="write_note")])
    btns.append([InlineKeyboardButton("🔙 Menu",callback_data="back_menu")])
    await q.edit_message_text("\n".join(lines),parse_mode="Markdown",reply_markup=InlineKeyboardMarkup(btns))
    return MENU

async def write_note_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    await q.edit_message_text("📝 *Naya Note*\n\nNote ka *title* type karo:",parse_mode="Markdown")
    ctx.user_data["mode"]="save_note_title"
    ctx.user_data["note_subject"]="General"
    return CHATTING

async def save_ans_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    uid=q.from_user.id
    title=ctx.user_data.get("last_question","AI Answer")[:50]
    content=ctx.user_data.get("last_answer","")
    if content:
        await db.save_note(uid,title,content,"AI Answer")
        await q.answer("✅ Note save ho gaya!",show_alert=True)
    return MENU

async def view_note_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    uid=q.from_user.id
    note_id=q.data.replace("view_note_","")
    note=await db.get_note(uid,note_id)
    if not note:
        await q.answer("Note nahi mila!",show_alert=True); return MENU
    title=note.get("title","Note"); content=note.get("content","")[:600]
    share_text=f"📝 {title}\n\n{content}\n\n— @IndiaStudyAI_Bot"
    wa_url=f"https://wa.me/?text={share_text.replace(' ','+')[:500]}"
    await q.edit_message_text(
        f"📝 *{title}*\n\n{content}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 WhatsApp Share",url=wa_url)],
            [InlineKeyboardButton("🗑️ Delete",callback_data=f"del_note_{note_id}")],
            [InlineKeyboardButton("🔙 Notes",callback_data="my_notes")]]))
    return MENU

async def del_note_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    uid=q.from_user.id; note_id=q.data.replace("del_note_","")
    await db.delete_note(uid,note_id)
    await q.answer("🗑️ Delete ho gaya!",show_alert=True)
    return await my_notes_cb(update,ctx)

# ── Reminders ─────────────────────────────────────────────────────────────────
async def set_reminder_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    uid=q.from_user.id
    reminders=await db.get_user_reminders(uid)
    rem_txt=""
    if reminders:
        rem_txt="\n\n*Active Reminders:*\n"+"\n".join([f"• {r['text'][:30]} — {r['remind_at'][:16]}" for r in reminders[:3]])
    await q.edit_message_text(
        f"⏰ *Reminder Set Karo*\n\nKya reminder dun? (text type karo){rem_txt}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    ctx.user_data["mode"]="set_reminder_text"; return CHATTING

# ── Updates/News ───────────────────────────────────────────────────────────────
async def show_updates(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    await q.edit_message_text("⏳ Live scraping se updates la raha hoon...")
    txt=await get_updates_text("all")
    await q.edit_message_text(f"📢 *Sarkari Updates — Live*\n\n{txt}",
        parse_mode="Markdown",disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💼 Jobs",callback_data="upd_jobs"),InlineKeyboardButton("📋 Forms",callback_data="upd_forms")],
            [InlineKeyboardButton("📊 Results",callback_data="upd_results"),InlineKeyboardButton("🏛️ Yojana",callback_data="upd_yojana")],
            [InlineKeyboardButton("🪪 Admit Card",callback_data="upd_admit"),InlineKeyboardButton("🎓 Scholarship",callback_data="upd_scholar")],
            [InlineKeyboardButton("🔄 Refresh",callback_data="updates"),InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    return MENU

async def show_upd_cat(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    cat=q.data.replace("upd_","")
    labels={"jobs":"💼 Jobs","forms":"📋 Forms","results":"📊 Results","yojana":"🏛️ Yojana","admit":"🪪 Admit Card","scholar":"🎓 Scholarship"}
    lbl=labels.get(cat,"Updates")
    await q.edit_message_text(f"⏳ {lbl} scraping kar raha hoon...")
    txt=await get_updates_text(cat)
    await q.edit_message_text(f"*{lbl} — Live Data*\n\n{txt}",parse_mode="Markdown",disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh",callback_data=q.data)],
            [InlineKeyboardButton("🔙 Updates",callback_data="updates")]]))
    return MENU

async def show_news(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    await q.edit_message_text("📰 RSS feeds se news la raha hoon...")
    txt=await get_news_text("india")
    await q.edit_message_text(f"📰 *Aaj Ki Khabar — Live RSS*\n\n{txt}",
        parse_mode="Markdown",disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏛️ Rajniti",callback_data="nws_pol"),InlineKeyboardButton("🏏 Sports",callback_data="nws_sport")],
            [InlineKeyboardButton("💼 Business",callback_data="nws_biz"),InlineKeyboardButton("📚 Education",callback_data="nws_edu")],
            [InlineKeyboardButton("🔄 Refresh",callback_data="news"),InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    return MENU

async def show_news_cat(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    cat=q.data.replace("nws_","")
    labels={"pol":"🏛️ Rajniti","sport":"🏏 Sports","biz":"💼 Business","edu":"📚 Education"}
    lbl=labels.get(cat,"News")
    await q.edit_message_text(f"⏳ {lbl} RSS se la raha hoon...")
    txt=await get_news_text(cat)
    await q.edit_message_text(f"*{lbl} — Live*\n\n{txt}",parse_mode="Markdown",disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh",callback_data=q.data)],
            [InlineKeyboardButton("🔙 News",callback_data="news")]]))
    return MENU

# ── Leaderboard ────────────────────────────────────────────────────────────────
async def leaderboard_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    uid=q.from_user.id; leaders=await db.get_leaderboard(10); rank=await db.get_rank(uid)
    medals=["🥇","🥈","🥉","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
    lines=["*🏆 Top 10 — IndiaStudyAI*\n"]
    for i,u in enumerate(leaders):
        name=u.get("name","User")[:12]; pts=u.get("points",0); streak=u.get("streak",0)
        marker=" ← You!" if u["user_id"]==uid else ""
        lines.append(f"{medals[i]} *{name}* — {pts} pts 🔥{streak}{marker}")
    lines.append(f"\n📊 *Tumhara rank: #{rank}*\n💡 Sawaal poochho, quiz khelo — points badhao!")
    await q.edit_message_text("\n".join(lines),parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👥 Dost ko Challenge",callback_data="refer")],
            [InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    return MENU

# ── Refer ──────────────────────────────────────────────────────────────────────
async def refer_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    uid=q.from_user.id; ud=await db.get_user(uid)
    ref_count=ud.get("ref_count",0) if ud else 0; pts=ud.get("points",0) if ud else 0
    next_reward=5-(ref_count%5); ref_link=f"{BOT_LINK}?start=REF{uid}"
    share_msg=f"Yaar ye bot bahut achha hai! Free mein padhai karo aur sarkari updates lo! 📚 {ref_link}"
    await q.edit_message_text(
        f"👥 *Refer & Earn*\n\n🔗 Link:\n`{ref_link}`\n\n"
        f"📊 Refer kiye: *{ref_count}* | Points: *{pts}*\n"
        f"Agle reward ke liye: *{next_reward}* aur refer karo\n\n"
        f"🎁 5 refer = 7 din FREE Premium! 🎉\n\n"
        f"📤 Share: '{share_msg[:100]}...'",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 WhatsApp Share",url=f"https://wa.me/?text={share_msg.replace(' ','+')}")]
            ,[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    return MENU

# ── Daily Challenge ────────────────────────────────────────────────────────────
async def daily_challenge_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    uid=q.from_user.id; used=await db.get_usage(uid,"challenge")
    if used>=1:
        await q.edit_message_text("✅ *Aaj ka challenge done!*\n\nKal dobara aana! 🔥",
            parse_mode="Markdown",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
        return MENU
    challenges=[
        {"q":"India ka sabse bada state (area)?","opts":["Maharashtra","Rajasthan","MP","UP"],"a":1,"cat":"GK"},
        {"q":"Newton ki 2nd law?","opts":["F=mv","F=ma","F=mg","F=m/a"],"a":1,"cat":"Physics"},
        {"q":"Photosynthesis mein kaunsi gas absorb?","opts":["O2","N2","CO2","H2"],"a":2,"cat":"Science"},
        {"q":"India mein kitne states?","opts":["25","26","28","30"],"a":2,"cat":"GK"},
        {"q":"x² - 5x + 6 = 0 ke roots?","opts":["2,3","1,6","2,4","3,4"],"a":0,"cat":"Math"},
        {"q":"Samvidhan kab lagu hua?","opts":["15 Aug 1947","26 Jan 1950","26 Nov 1949","2 Oct 1948"],"a":1,"cat":"History"},
        {"q":"1 GB = ?","opts":["1000 MB","1024 MB","512 MB","2048 MB"],"a":1,"cat":"Computer"},
        {"q":"Sandhi ke kitne prakar?","opts":["2","3","4","5"],"a":1,"cat":"Hindi"},
    ]
    ch=random.choice(challenges); ctx.user_data["challenge"]=ch
    opts_text="\n".join([f"{chr(65+i)}. {o}" for i,o in enumerate(ch["opts"])])
    kb_opts=[[InlineKeyboardButton(f"{chr(65+i)}. {ch['opts'][i]}",callback_data=f"ch_{i}") for i in range(2)],
             [InlineKeyboardButton(f"{chr(65+i)}. {ch['opts'][i]}",callback_data=f"ch_{i}") for i in range(2,4)]]
    await q.edit_message_text(
        f"🎯 *Daily Challenge!*\n🏷️ {ch['cat']}\n\n❓ *{ch['q']}*\n\n{opts_text}\n\n✅ Sahi = +20 pts!",
        parse_mode="Markdown",reply_markup=InlineKeyboardMarkup(kb_opts))
    return MENU

async def challenge_answer_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    uid=q.from_user.id; chosen=int(q.data[3:]); ch=ctx.user_data.get("challenge")
    if not ch: return await back_menu(update,ctx)
    await db.inc_usage(uid,"challenge")
    if chosen==ch["a"]:
        await db.add_points(uid,20)
        await q.edit_message_text(f"✅ *Sahi!* +20 pts! 🎉\n\nAnswer: *{ch['opts'][ch['a']]}*\n\nKal phir aana! 🔥",
            parse_mode="Markdown",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    else:
        await q.edit_message_text(f"❌ *Galat!*\nSahi answer: *{ch['opts'][ch['a']]}*\n\nKal dobara try karo! 💪",
            parse_mode="Markdown",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    return MENU

# ── Exam Countdown ─────────────────────────────────────────────────────────────
async def set_exam_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    uid=q.from_user.id; ud=await db.get_user(uid)
    exam_date=ud.get("exam_date") if ud else None
    if exam_date:
        try:
            days=max(0,(date.fromisoformat(exam_date)-date.today()).days)
            await q.edit_message_text(
                f"📅 *Tumhara Exam*\n\n📝 {ud.get('exam_name')}\n📅 {exam_date}\n⏳ *{days} din baaki!*\n\n{'🔥 Jaldi karo!' if days<30 else '💪 Preparation achhi karo!'}",
                parse_mode="Markdown",reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✏️ Change",callback_data="change_exam")],
                    [InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
            return MENU
        except: pass
    await q.edit_message_text("📅 *Exam Countdown*\n\nExam ka *naam* type karo:",parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    ctx.user_data["mode"]="set_exam_name"; return CHATTING

async def change_exam_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    await q.edit_message_text("✏️ Naya *exam naam* type karo:",parse_mode="Markdown")
    ctx.user_data["mode"]="set_exam_name"; return CHATTING

# ── Settings ───────────────────────────────────────────────────────────────────
async def settings_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    uid=q.from_user.id; ud=await db.get_user(uid)
    morning=ud.get("notify_morning",True) if ud else True
    exam_n=ud.get("notify_exam",True) if ud else True
    lang=ud.get("language","hi") if ud else "hi"
    lang_names={"hi":"Hindi 🇮🇳","en":"English 🇬🇧","mix":"Hinglish 🔀"}
    await q.edit_message_text(
        f"⚙️ *Settings*\n\n🌐 Language: {lang_names.get(lang,'Hindi')}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"🌅 Morning: {'✅' if morning else '❌'}",callback_data="toggle_morning")],
            [InlineKeyboardButton(f"📅 Exam Reminder: {'✅' if exam_n else '❌'}",callback_data="toggle_exam_n")],
            [InlineKeyboardButton("🌐 Language Change",callback_data="lang_menu")],
            [InlineKeyboardButton("✏️ Profile Update",callback_data="update_profile")],
            [InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    return MENU

async def toggle_morning_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    ud=await db.get_user(q.from_user.id)
    new_val=not ud.get("notify_morning",True) if ud else False
    await db.update_settings(q.from_user.id,notify_morning=new_val)
    await q.answer(f"Morning {'ON ✅' if new_val else 'OFF ❌'}",show_alert=True)
    return await settings_cb(update,ctx)

async def toggle_exam_n_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    ud=await db.get_user(q.from_user.id)
    new_val=not ud.get("notify_exam",True) if ud else False
    await db.update_settings(q.from_user.id,notify_exam=new_val)
    await q.answer(f"Exam reminder {'ON ✅' if new_val else 'OFF ❌'}",show_alert=True)
    return await settings_cb(update,ctx)

# ── Premium ────────────────────────────────────────────────────────────────────
async def premium_info(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    await q.edit_message_text(
        "💎 *Premium — ₹199/month*\n\n"
        "✅ Unlimited AI (8 sources)\n✅ Unlimited sawaal\n"
        "✅ Unlimited notes\n✅ Priority support\n\n"
        f"━━━━━━━━━━\n💳 UPI: `{UPI_ID}`\n💰 ₹199\n━━━━━━━━━━\n\n"
        "1️⃣ ₹199 bhejo\n2️⃣ Screenshot lo\n3️⃣ Button dabao\n\n"
        "💡 *FREE:* 5 refer karo = 7 din premium!",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Pay kar diya",callback_data="prem_paid")],
            [InlineKeyboardButton("👥 Refer karke FREE lo",callback_data="refer")],
            [InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    return MENU

async def prem_paid(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    await q.edit_message_text("📸 *Screenshot Bhejo!*\n\n1-2 ghante mein activate hoga! 🔔",parse_mode="Markdown")
    ctx.user_data["mode"]="screenshot"; return WAIT_SS

async def handle_screenshot(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id; u=update.effective_user
    cap=(f"💳 *Premium!*\n👤 {u.first_name}\n🆔 `{uid}`\n"
         f"@{u.username or 'N/A'}\n\n`/addpremium {uid}`")
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
    tq=ud.get("total_q",0) if ud else 0; pts=ud.get("points",0) if ud else 0
    streak=ud.get("streak",0) if ud else 0; max_s=ud.get("max_streak",0) if ud else 0
    badges=ud.get("badges",[]) if ud else []; rank=await db.get_rank(uid)
    ref_count=ud.get("ref_count",0) if ud else 0
    notes_count=len(await db.get_user_notes(uid))
    await q.edit_message_text(
        f"👤 *Meri Profile*\n\n"
        f"📚 {cl} | 📖 {co}\n💎 {'Premium ✨' if prem else 'Free'}\n\n"
        f"⭐ Points: *{pts}* | Rank: *#{rank}*\n"
        f"🔥 Streak: *{streak}* | Best: *{max_s}*\n"
        f"👥 Referrals: *{ref_count}*\n"
        f"📝 Notes: *{notes_count}*\n"
        f"🏅 Badges: {' '.join(badges[:3]) if badges else 'None'}\n\n"
        f"📊 Total Sawaal: *{tq}*",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✏️ Profile Update",callback_data="update_profile"),
             InlineKeyboardButton("📝 Meri Notes",callback_data="my_notes")],
            [InlineKeyboardButton("🏆 Leaderboard",callback_data="leaderboard")],
            [InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    return MENU

async def help_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    await q.edit_message_text(
        "ℹ️ *@IndiaStudyAI\\_Bot*\n\n"
        "/start /menu /profile\n\n"
        "*Free:* 10 sawaal/din, 10 AI/din\n"
        "*Premium ₹199:* Unlimited\n\n"
        "*AI Sources:* 8 free sources\n"
        "*News:* Live RSS feeds\n"
        "*Updates:* Real-time scraping\n"
        "*Notes:* Save + WhatsApp share\n"
        "*Reminders:* Custom alerts\n\n"
        f"🌐 App: {MINI_APP}",
        parse_mode="Markdown",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    return MENU

async def back_menu(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    ctx.user_data["mode"]="question"; return await _send_menu(q,ctx)

async def update_profile(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    await q.edit_message_text("Class dobara select karo:",reply_markup=kb(CLASSES,"cl_"))
    return SELECT_CLASS

async def feedback_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query
    if q.data=="fb_good":
        await q.answer("✅ Shukriya! +1 pt!",show_alert=False)
        await db.add_points(q.from_user.id,1)
    else:
        await q.answer("📝 Feedback noted!",show_alert=False)
    return MENU

async def retry_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    kind=q.data.replace("retry_",""); ctx.user_data["mode"]="ai" if kind=="ai" else "question"
    await q.edit_message_text("🔄 Type karo!",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    return CHATTING

# ── Scheduled Jobs ─────────────────────────────────────────────────────────────
async def send_morning_messages(bot):
    log.info("🌅 Morning messages...")
    users=await db.morning_notify_users(); sent=0
    for u in users:
        try:
            ud=await db.get_user(u["user_id"])
            name=ud.get("name","Student") if ud else "Student"
            streak=ud.get("streak",0) if ud else 0
            msg=await get_morning_message(name,streak)
            await bot.send_message(u["user_id"],msg,parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🎯 Daily Challenge",callback_data="daily_challenge"),
                     InlineKeyboardButton("📱 Study App",web_app=WebAppInfo(url=MINI_APP))],
                    [InlineKeyboardButton("📢 Live Updates",callback_data="updates")]]))
            sent+=1
        except: pass
    log.info(f"✅ Sent: {sent}")

async def send_exam_reminders(bot):
    reminders=await db.get_exam_reminders()
    for r in reminders:
        try:
            days=r["days_left"]; name=r.get("exam_name","Exam")
            if days==1: msg=f"⚠️ *Kal hai {name}!* 🔥 Best of luck! 🍀"
            elif days==7: msg=f"📅 *{name} — 7 din baaki!* Revision shuru karo! 📚"
            else: msg=f"📅 *{name} — {days} din baaki!* 💪"
            await bot.send_message(r["user_id"],msg,parse_mode="Markdown")
        except: pass

async def send_due_reminders(bot):
    """Check and send due custom reminders"""
    reminders=await db.get_due_reminders()
    for r in reminders:
        try:
            await bot.send_message(r["user_id"],
                f"⏰ *Reminder!*\n\n{r['text']}",parse_mode="Markdown")
            await db.mark_reminder_sent(str(r["_id"]))
        except: pass

# ── Admin Commands ─────────────────────────────────────────────────────────────
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
    try: await ctx.bot.send_message(uid,"✅ Unblock! /start karo.")
    except: pass
    await update.message.reply_text(f"✅ Unblocked {uid}")

async def cmd_stats(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!=OWNER_ID: return
    s=await db.stats()
    await update.message.reply_text(
        f"📊 *Stats*\n\n👥 {s['total']} | 💎 {s['premium']}\n"
        f"🚫 {s['blocked']} | ❓ {s['questions']}\n"
        f"✅ Active: {s['active_today']} | 📝 Notes: {s['notes']}\n\n"
        f"🌐 {MINI_APP}\n\n"
        "/addpremium <id> [d] | /removepremium | /block | /unblock | /broadcast",
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
    scheduler=AsyncIOScheduler(timezone="Asia/Kolkata")
    scheduler.add_job(send_morning_messages,"cron",hour=7,minute=0,args=[app.bot])
    scheduler.add_job(send_exam_reminders,"cron",hour=8,minute=0,args=[app.bot])
    scheduler.add_job(send_due_reminders,"interval",minutes=5,args=[app.bot])
    scheduler.start()
    log.info(f"✅ Bot ready! App: {MINI_APP}")

def main():
    t=threading.Thread(target=run_flask,daemon=True); t.start()
    app=Application.builder().token(TOKEN).post_init(post_init).build()
    ch=ConversationHandler(
        entry_points=[CommandHandler("start",start)],
        states={
            SELECT_CLASS:[CallbackQueryHandler(sel_class,pattern="^cl_")],
            SELECT_COURSE:[CallbackQueryHandler(sel_course,pattern="^co_")],
            SELECT_GOAL:[CallbackQueryHandler(sel_goal,pattern="^go_")],
            MENU:[
                CallbackQueryHandler(ai_cb,pattern="^ai$"),
                CallbackQueryHandler(question_cb,pattern="^question$"),
                CallbackQueryHandler(show_updates,pattern="^updates$"),
                CallbackQueryHandler(show_upd_cat,pattern="^upd_"),
                CallbackQueryHandler(show_news,pattern="^news$"),
                CallbackQueryHandler(show_news_cat,pattern="^nws_"),
                CallbackQueryHandler(premium_info,pattern="^premium$"),
                CallbackQueryHandler(prem_paid,pattern="^prem_paid$"),
                CallbackQueryHandler(profile_cb,pattern="^profile$"),
                CallbackQueryHandler(help_cb,pattern="^help$"),
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
                CallbackQueryHandler(save_ans_cb,pattern="^save_ans_"),
                CallbackQueryHandler(view_note_cb,pattern="^view_note_"),
                CallbackQueryHandler(del_note_cb,pattern="^del_note_"),
                CallbackQueryHandler(set_reminder_cb,pattern="^set_reminder$"),
                CallbackQueryHandler(feedback_cb,pattern="^fb_"),
                CallbackQueryHandler(retry_cb,pattern="^retry_"),
                MessageHandler(filters.TEXT&~filters.COMMAND,handle_text),
                MessageHandler(filters.PHOTO,handle_screenshot),
            ],
            CHATTING:[
                MessageHandler(filters.TEXT&~filters.COMMAND,handle_text),
                MessageHandler(filters.PHOTO,handle_screenshot),
                CallbackQueryHandler(back_menu,pattern="^back_menu$"),
                CallbackQueryHandler(feedback_cb,pattern="^fb_"),
                CallbackQueryHandler(retry_cb,pattern="^retry_"),
                CallbackQueryHandler(save_ans_cb,pattern="^save_ans_"),
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
    log.info("🚀 Bot chalu!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__=="__main__":
    main()
