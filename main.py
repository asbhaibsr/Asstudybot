import logging,os,threading,random
from datetime import datetime,date
from flask import Flask,send_from_directory,jsonify
from telegram import Update,InlineKeyboardButton,InlineKeyboardMarkup,WebAppInfo
from telegram.ext import (Application,CommandHandler,CallbackQueryHandler,
    MessageHandler,filters,ContextTypes,ConversationHandler)
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from db import db
from ai import ask_ai,get_updates_text,get_news_text,get_morning_message,get_daily_quote,get_daily_fact

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s',level=logging.INFO)
log=logging.getLogger(__name__)

TOKEN   =os.environ.get("BOT_TOKEN","YOUR_BOT_TOKEN")
OWNER_ID=int(os.environ.get("OWNER_ID","123456789"))
UPI_ID  =os.environ.get("UPI_ID","arsadsaifi8272@ibl")
PORT    =int(os.environ.get("PORT","8080"))
KOYEB_URL=os.environ.get("KOYEB_URL","https://chilly-ardath-arsadsaifi784-74d0cd5c.koyeb.app")
MINI_APP=f"{KOYEB_URL}/app"
BOT_LINK="https://t.me/IndiaStudyAI_Bot"

flask_app=Flask(__name__,static_folder="app")
@flask_app.route("/")
def home(): return jsonify({"status":"ok","app":"/app"})
@flask_app.route("/health")
def health(): return jsonify({"status":"ok"}),200

@flask_app.route("/app")
@flask_app.route("/app/")
def mini_app(): return send_from_directory("app","index.html")
def run_flask(): flask_app.run(host="0.0.0.0",port=PORT,debug=False,use_reloader=False)

SELECT_CLASS,SELECT_COURSE,SELECT_GOAL,MENU,CHATTING,WAIT_SS,SET_EXAM=range(7)
CLASSES={"c1_5":"📚 Class 1-5","c6_8":"📖 Class 6-8","c9_10":"🎓 Class 9-10","c11_12":"🏫 Class 11-12","college":"🎓 College","adult":"👨‍💼 Adult Learner"}
COURSES={"math":"➕ Maths","science":"🔬 Science","hindi":"🇮🇳 Hindi","english":"🔤 English","sst":"🌍 SST/History","computer":"💻 Computer","gk":"🧠 GK"}
GOALS={"exam":"📝 Exam Prep","skill":"💡 Skill Seekhna","homework":"📋 Homework Help","job":"💼 Sarkari Naukri","hobby":"🎨 Hobby"}

def kb(items,prefix,cols=2):
    btns,row=[],[]
    for k,v in items.items():
        row.append(InlineKeyboardButton(v,callback_data=f"{prefix}{k}"))
        if len(row)==cols: btns.append(row);row=[]
    if row: btns.append(row)
    return InlineKeyboardMarkup(btns)

def main_kb(premium,points=0,streak=0):
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
        [InlineKeyboardButton(f"{badge} Premium ₹199/mo",callback_data="premium"),
         InlineKeyboardButton("👤 Profile",callback_data="profile")],
        [InlineKeyboardButton("⚙️ Settings",callback_data="settings"),
         InlineKeyboardButton("ℹ️ Help",callback_data="help")],
    ])

# ── Start ─────────────────────────────────────────────────────────────────────
async def start(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    u=update.effective_user
    if await db.is_blocked(u.id):
        await update.message.reply_text("❌ Aapko block kar diya gaya hai."); return ConversationHandler.END
    ref_by=None
    if ctx.args and ctx.args[0].startswith("REF"):
        try: ref_by=int(ctx.args[0][3:])
        except: pass
    await db.add_user(u.id,u.first_name,u.username,ref_by=ref_by)
    if ref_by and ref_by!=u.id:
        try: await ctx.bot.send_message(ref_by,f"🎉 *{u.first_name}* ne aapka refer link use kiya!\n+100 points mile! 🏆",parse_mode="Markdown")
        except: pass
    ud=await db.get_user(u.id)
    if ud and ud.get("class_type"): return await _send_menu(update,ctx)
    await update.message.reply_text(
        f"🙏 *Namaste {u.first_name}!*\n\n"
        "🤖 Main hoon *@IndiaStudyAI\\_Bot*\n"
        "India ka #1 Free Study + Sarkari Bot!\n\n"
        "🎁 *Joining Bonus: 50 Points!*\n\n"
        "✅ *FREE mein milega:*\n"
        "• 📚 Sabhi Subjects — Wikipedia+AI\n"
        "• 🤖 AI Tutor — 10 sawaal/din\n"
        "• 🎯 Daily Quiz + Challenge\n"
        "• 📢 Sarkari Jobs/Forms/Results\n"
        "• 📰 Hindi News — Latest 2026\n"
        "• 🔥 Streak + Badges System\n"
        "• 🏆 Leaderboard\n"
        "• 👥 Refer karke Premium Free!\n\n"
        "Pehle apni *class* batao 👇",
        parse_mode="Markdown",reply_markup=kb(CLASSES,"cl_"))
    return SELECT_CLASS

async def sel_class(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    ctx.user_data["class_type"]=q.data[3:]
    await q.edit_message_text("✅ Class set!\n\nAb *subject* batao 👇",parse_mode="Markdown",reply_markup=kb(COURSES,"co_"))
    return SELECT_COURSE

async def sel_course(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    ctx.user_data["course"]=q.data[3:]
    await q.edit_message_text("✅ Subject set!\n\nAb *lakshya* batao 👇",parse_mode="Markdown",reply_markup=kb(GOALS,"go_",1))
    return SELECT_GOAL

async def sel_goal(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    await db.update_profile(q.from_user.id,ctx.user_data.get("class_type"),ctx.user_data.get("course"),q.data[3:])
    await q.edit_message_text("🎉 *Profile ready!*\n\nAb sab features use karo 👇",parse_mode="Markdown")
    ctx.user_data["mode"]="question"
    return await _send_menu(q,ctx)

async def menu_cmd(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    ctx.user_data["mode"]="question"; return await _send_menu(update,ctx)

async def _send_menu(src,ctx):
    uid=src.effective_user.id if hasattr(src,'effective_user') else src.from_user.id
    prem=await db.is_premium(uid); ud=await db.get_user(uid)
    pts=ud.get("points",0) if ud else 0; streak=ud.get("streak",0) if ud else 0
    streak_txt=f"🔥 {streak} din streak!" if streak>1 else "🌱 Streak shuru karo!"
    txt=(f"🏠 *Main Menu* {'💎 Premium' if prem else '🆓 Free'}\n\n"
         f"⭐ Points: *{pts}* | {streak_txt}\n\n"
         "📱 Study App — Sabhi subjects\n"
         "🤖 AI Tutor — Kuch bhi poochho\n"
         "📢 Updates — Sarkari jobs/forms\n"
         "🏆 Leaderboard — Top ban jao\n"
         "👥 Refer — Dosto ko bhejo, premium pao")
    mk=main_kb(prem,pts,streak)
    if hasattr(src,'message') and src.message:
        await src.message.reply_text(txt,parse_mode="Markdown",reply_markup=mk)
    elif hasattr(src,'edit_message_text'):
        await src.edit_message_text(txt,parse_mode="Markdown",reply_markup=mk)
    else:
        await ctx.bot.send_message(uid,txt,parse_mode="Markdown",reply_markup=mk)
    return MENU

# ── AI/Question ───────────────────────────────────────────────────────────────
async def ai_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    uid=q.from_user.id; prem=await db.is_premium(uid); used=await db.get_usage(uid,"ai")
    if not prem and used>=10: return await _limit_msg(q,"AI Tutor",10)
    rem="∞" if prem else str(10-used)
    await q.edit_message_text(f"🤖 *AI Tutor*\nAaj bache: *{rem}* sawaal\n\nMath, Science, GK, Career — sab poochho!\n_Sirf padhai topics — off-topic refuse hoga_\n/menu — wapas",
        parse_mode="Markdown",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    ctx.user_data["mode"]="ai"; return CHATTING

async def question_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    uid=q.from_user.id; prem=await db.is_premium(uid); used=await db.get_usage(uid,"q")
    if not prem and used>=10: return await _limit_msg(q,"Sawaal",10)
    rem="∞" if prem else str(10-used)
    await q.edit_message_text(f"❓ *Sawaal Mode*\nAaj bache: *{rem}*\n\nApna sawaal type karo!\n/menu — wapas",
        parse_mode="Markdown",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    ctx.user_data["mode"]="question"; return CHATTING

async def _limit_msg(q,what,lim):
    await q.edit_message_text(f"⚠️ *{what} limit khatam!*\nFree mein {lim}/din.\n\n💎 *Premium lo ₹199/month — unlimited!*",
        parse_mode="Markdown",reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("💎 Premium Lo",callback_data="premium")],
            [InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    return MENU

async def handle_text(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id
    if await db.is_blocked(uid): return
    txt=update.message.text
    if txt.startswith("/"): return
    mode=ctx.user_data.get("mode","question")
    if mode=="screenshot": return await handle_screenshot(update,ctx)
    if mode=="set_exam_name":
        ctx.user_data["exam_name"]=txt
        await update.message.reply_text("📅 Ab exam ki *date* daalo (format: YYYY-MM-DD, jaise 2026-05-15):",parse_mode="Markdown")
        ctx.user_data["mode"]="set_exam_date"; return CHATTING
    if mode=="set_exam_date":
        try:
            exam_date=txt.strip()
            date.fromisoformat(exam_date)
            await db.set_exam(uid,ctx.user_data.get("exam_name","Exam"),exam_date)
            days=max(0,(date.fromisoformat(exam_date)-date.today()).days)
            await update.message.reply_text(f"✅ *Exam set ho gaya!*\n\n📅 {ctx.user_data.get('exam_name')} — {exam_date}\n⏳ *{days} din baaki hain!*\n\nReminder milega 30, 7, aur 1 din pehle! 🔔",
                parse_mode="Markdown",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
            ctx.user_data["mode"]="question"; return MENU
        except:
            await update.message.reply_text("❌ Format galat hai! YYYY-MM-DD mein daalo, jaise: 2026-05-15"); return CHATTING
    prem=await db.is_premium(uid); ud=await db.get_user(uid)
    kind="ai" if mode=="ai" else "q"; used=await db.get_usage(uid,kind)
    if not prem and used>=10:
        await update.message.reply_text("⚠️ Limit khatam! /menu se premium lo."); return
    wait=await update.message.reply_text("🤖 Soch raha hoon..." if mode=="ai" else "🔍 Jawab dhundh raha hoon...")
    resp=await ask_ai(txt,ud,mode)
    await db.inc_usage(uid,kind); await db.save_q(uid,txt,resp)
    try: await wait.delete()
    except: pass
    await update.message.reply_text(resp,parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Helpful",callback_data="fb_good"),
             InlineKeyboardButton("❌ Aur Better",callback_data="fb_bad")],
            [InlineKeyboardButton("🔄 Dobara Poochho",callback_data=f"retry_{kind}"),
             InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    return CHATTING

# ── Leaderboard ───────────────────────────────────────────────────────────────
async def leaderboard_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    uid=q.from_user.id
    leaders=await db.get_leaderboard(10); rank=await db.get_rank(uid)
    medals=["🥇","🥈","🥉","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
    lines=[f"*🏆 Top 10 — IndiaStudyAI*\n"]
    for i,u in enumerate(leaders):
        name=u.get("name","User")[:12]; pts=u.get("points",0); streak=u.get("streak",0)
        marker=" ← Tum!" if u["user_id"]==uid else ""
        lines.append(f"{medals[i]} *{name}* — {pts} pts 🔥{streak}{marker}")
    lines.append(f"\n📊 *Tumhara rank: #{rank}*")
    lines.append(f"\n💡 Zyada sawaal poochho, quiz khelo — points badhao!")
    await q.edit_message_text("\n".join(lines),parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("👥 Dost ko Challenge",callback_data="refer")],
            [InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    return MENU

# ── Refer & Earn ──────────────────────────────────────────────────────────────
async def refer_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    uid=q.from_user.id; ud=await db.get_user(uid)
    ref_count=ud.get("ref_count",0) if ud else 0; pts=ud.get("points",0) if ud else 0
    next_reward=5-(ref_count%5); ref_link=f"{BOT_LINK}?start=REF{uid}"
    await q.edit_message_text(
        f"👥 *Refer & Earn*\n\n"
        f"🔗 Tumhara refer link:\n`{ref_link}`\n\n"
        f"📊 *Stats:*\n"
        f"• Abhi tak refer kiye: *{ref_count}*\n"
        f"• Total points: *{pts}*\n"
        f"• Agle reward ke liye: *{next_reward} aur* refer karo\n\n"
        f"🎁 *Rewards:*\n"
        f"• Har refer = +100 points\n"
        f"• 5 refer = 7 din FREE Premium! 🎉\n"
        f"• 10 refer = 15 din FREE Premium!\n\n"
        f"📤 *Share karo:*\n"
        f"'Yaar ye bot bahut achha hai! Free mein padhai karo: {ref_link}'",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📤 WhatsApp pe Share",url=f"https://wa.me/?text=Yaar+ye+bot+bahut+achha+hai!+Free+mein+padhai+karo+aur+sarkari+updates+lo!+%F0%9F%93%9A{ref_link}")],
            [InlineKeyboardButton("📋 Link Copy Karo",callback_data="copy_ref")],
            [InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    return MENU

async def copy_ref_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; uid=q.from_user.id
    ref_link=f"{BOT_LINK}?start=REF{uid}"
    await q.answer(f"Link: {ref_link}",show_alert=True)
    return MENU

# ── Daily Challenge ───────────────────────────────────────────────────────────
async def daily_challenge_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    uid=q.from_user.id; used=await db.get_usage(uid,"challenge")
    if used>=1:
        await q.edit_message_text("✅ *Aaj ka challenge already complete!*\n\nKal dobara aana! 🔥\nHar din challenge karo — streak badhao!",
            parse_mode="Markdown",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
        return MENU
    challenges=[
        {"q":"India ka sabse bada state (area mein) kaunsa hai?","opts":["Maharashtra","Rajasthan","Madhya Pradesh","Uttar Pradesh"],"a":1,"cat":"GK"},
        {"q":"Newton ki 2nd law kya hai?","opts":["F=mv","F=ma","F=mg","F=m/a"],"a":1,"cat":"Physics"},
        {"q":"'Sandhi' ka matlab kya hai Hindi grammar mein?","opts":["Tod","Jod","Badlav","Antim"],"a":1,"cat":"Hindi"},
        {"q":"Computer mein 1 GB = ?","opts":["1000 MB","1024 MB","512 MB","2048 MB"],"a":1,"cat":"Computer"},
        {"q":"Photosynthesis mein kaunsi gas absorb hoti hai?","opts":["O2","N2","CO2","H2"],"a":2,"cat":"Science"},
        {"q":"India mein kitne states hain?","opts":["25","26","28","29"],"a":2,"cat":"GK"},
        {"q":"x² - 5x + 6 = 0 ke roots kya hain?","opts":["2,3","1,6","2,4","3,4"],"a":0,"cat":"Math"},
        {"q":"World War II kab khatam hua?","opts":["1943","1944","1945","1946"],"a":2,"cat":"History"},
    ]
    ch=random.choice(challenges)
    ctx.user_data["challenge"]=ch
    opts_text="\n".join([f"{chr(65+i)}. {o}" for i,o in enumerate(ch["opts"])])
    kb_opts=[[InlineKeyboardButton(f"{chr(65+i)}. {o}",callback_data=f"ch_{i}") for i in range(2)],
             [InlineKeyboardButton(f"{chr(65+i)}. {o}",callback_data=f"ch_{i}") for i in range(2,4)]]
    await q.edit_message_text(
        f"🎯 *Aaj Ka Daily Challenge!*\n🏷️ Category: {ch['cat']}\n\n"
        f"❓ *{ch['q']}*\n\n{opts_text}\n\n"
        f"✅ Sahi jawab = +20 points!\n⏰ Sirf 1 baar!",
        parse_mode="Markdown",reply_markup=InlineKeyboardMarkup(kb_opts))
    return MENU

async def challenge_answer_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    uid=q.from_user.id; chosen=int(q.data[3:]); ch=ctx.user_data.get("challenge")
    if not ch: return await back_menu(update,ctx)
    await db.inc_usage(uid,"challenge")
    if chosen==ch["a"]:
        await db.add_points(uid,20)
        await q.edit_message_text(
            f"✅ *Bilkul Sahi!* +20 points! 🎉\n\n"
            f"*{ch['q']}*\nAnswer: *{ch['opts'][ch['a']]}*\n\n"
            f"Kal phir aana next challenge ke liye! 🔥",
            parse_mode="Markdown",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    else:
        await q.edit_message_text(
            f"❌ *Galat!*\n\n*{ch['q']}*\nSahi answer: *{ch['opts'][ch['a']]}*\n\n"
            f"Koi baat nahi — kal dobara try karo! 💪",
            parse_mode="Markdown",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    return MENU

# ── Exam Countdown ────────────────────────────────────────────────────────────
async def set_exam_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    uid=q.from_user.id; ud=await db.get_user(uid)
    exam_name=ud.get("exam_name") if ud else None
    exam_date=ud.get("exam_date") if ud else None
    if exam_date:
        try:
            days=max(0,(date.fromisoformat(exam_date)-date.today()).days)
            await q.edit_message_text(
                f"📅 *Tumhara Exam*\n\n"
                f"📝 Exam: *{exam_name}*\n📅 Date: *{exam_date}*\n"
                f"⏳ Baaki hain: *{days} din*\n\n"
                f"{'🔥 Jaldi karo! Time kam hai!' if days<30 else '💪 Achhi preparation karo!'}",
                parse_mode="Markdown",reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("✏️ Change Karo",callback_data="change_exam")],
                    [InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
            return MENU
        except: pass
    await q.edit_message_text(
        "📅 *Exam Countdown Set Karo*\n\nReminder milega 30, 7, aur 1 din pehle!\n\nPehle *exam ka naam* type karo:",
        parse_mode="Markdown",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    ctx.user_data["mode"]="set_exam_name"; return CHATTING

async def change_exam_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    await q.edit_message_text("✏️ Naya *exam naam* type karo:",parse_mode="Markdown")
    ctx.user_data["mode"]="set_exam_name"; return CHATTING

# ── Settings ──────────────────────────────────────────────────────────────────
async def settings_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    uid=q.from_user.id; ud=await db.get_user(uid)
    morning=ud.get("notify_morning",True) if ud else True
    exam_n=ud.get("notify_exam",True) if ud else True
    await q.edit_message_text(
        "⚙️ *Settings*\n\nApni preferences set karo:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton(f"🌅 Morning Notify: {'✅ ON' if morning else '❌ OFF'}",callback_data="toggle_morning")],
            [InlineKeyboardButton(f"📅 Exam Reminder: {'✅ ON' if exam_n else '❌ OFF'}",callback_data="toggle_exam_n")],
            [InlineKeyboardButton("✏️ Profile Update",callback_data="update_profile")],
            [InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    return MENU

async def toggle_morning_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    uid=q.from_user.id; ud=await db.get_user(uid)
    new_val=not ud.get("notify_morning",True) if ud else False
    await db.update_settings(uid,notify_morning=new_val)
    await q.answer(f"Morning notification {'ON ✅' if new_val else 'OFF ❌'}",show_alert=True)
    return await settings_cb(update,ctx)

async def toggle_exam_n_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    uid=q.from_user.id; ud=await db.get_user(uid)
    new_val=not ud.get("notify_exam",True) if ud else False
    await db.update_settings(uid,notify_exam=new_val)
    await q.answer(f"Exam reminder {'ON ✅' if new_val else 'OFF ❌'}",show_alert=True)
    return await settings_cb(update,ctx)

# ── Updates/News ──────────────────────────────────────────────────────────────
async def show_updates(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    await q.edit_message_text("⏳ Latest 2026 sarkari updates la raha hoon...")
    txt=await get_updates_text("all")
    await q.edit_message_text(f"📢 *Sarkari Updates — 2026*\n\n{txt}",parse_mode="Markdown",disable_web_page_preview=True,
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
    await q.edit_message_text(f"⏳ {lbl} la raha hoon...")
    txt=await get_updates_text(cat)
    await q.edit_message_text(f"*{lbl} — 2026*\n\n{txt}",parse_mode="Markdown",disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Refresh",callback_data=q.data)],[InlineKeyboardButton("🔙 Updates",callback_data="updates")]]))
    return MENU

async def show_news(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    await q.edit_message_text("📰 Taaza khabar la raha hoon...")
    txt=await get_news_text("india")
    await q.edit_message_text(f"📰 *Aaj Ki Khabar — 2026*\n\n{txt}",parse_mode="Markdown",disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🏛️ Rajniti",callback_data="nws_pol"),InlineKeyboardButton("🏏 Sports",callback_data="nws_sport")],
            [InlineKeyboardButton("💼 Business",callback_data="nws_biz"),InlineKeyboardButton("📚 Education",callback_data="nws_edu")],
            [InlineKeyboardButton("🔄 Refresh",callback_data="news"),InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    return MENU

async def show_news_cat(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    cat=q.data.replace("nws_","")
    labels={"pol":"🏛️ Rajniti","sport":"🏏 Sports","biz":"💼 Business","edu":"📚 Education"}
    lbl=labels.get(cat,"News"); await q.edit_message_text(f"⏳ {lbl} la raha hoon...")
    txt=await get_news_text(cat)
    await q.edit_message_text(f"*{lbl} — 2026*\n\n{txt}",parse_mode="Markdown",disable_web_page_preview=True,
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Refresh",callback_data=q.data)],[InlineKeyboardButton("🔙 News",callback_data="news")]]))
    return MENU

# ── Premium ───────────────────────────────────────────────────────────────────
async def premium_info(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    await q.edit_message_text(
        "💎 *Premium Plan — ₹199/month*\n\n"
        "✅ Unlimited AI Tutor\n✅ Unlimited sawaal\n✅ Unlimited quiz\n"
        "✅ Priority support\n✅ Unlimited news\n\n"
        f"━━━━━━━━━━\n💳 UPI: `{UPI_ID}`\n💰 ₹199\n━━━━━━━━━━\n\n"
        "1️⃣ UPI pe ₹199 bhejo\n2️⃣ Screenshot lo\n3️⃣ Button dabao\n\n"
        "💡 *Ya FREE mein lo:* 5 doston ko refer karo!",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Pay kar diya — Screenshot Bhejo",callback_data="prem_paid")],
            [InlineKeyboardButton("👥 Refer karke FREE lo",callback_data="refer")],
            [InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    return MENU

async def prem_paid(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    await q.edit_message_text("📸 *Screenshot Bhejo Is Chat Mein!*\n\nOwner verify karega, 1-2 ghante mein activate hoga! 🔔",parse_mode="Markdown")
    ctx.user_data["mode"]="screenshot"; return WAIT_SS

async def handle_screenshot(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    uid=update.effective_user.id; u=update.effective_user
    cap=(f"💳 *Premium Request!*\n👤 {u.first_name}\n🆔 `{uid}`\n@{u.username or 'N/A'}\n\n`/addpremium {uid}` — approve karo")
    try:
        if update.message.photo:
            await ctx.bot.forward_message(OWNER_ID,update.message.chat_id,update.message.message_id)
        await ctx.bot.send_message(OWNER_ID,cap,parse_mode="Markdown")
    except Exception as e: log.error(f"Forward: {e}")
    await update.message.reply_text("✅ Request bhej di! 1-2 ghante mein activate hoga. 🔔")
    ctx.user_data["mode"]="question"; return MENU

# ── Profile/Progress ──────────────────────────────────────────────────────────
async def profile_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    uid=q.from_user.id; ud=await db.get_user(uid); prem=await db.is_premium(uid)
    cl=CLASSES.get(ud.get("class_type",""),"N/A") if ud else "N/A"
    co=COURSES.get(ud.get("course",""),"N/A") if ud else "N/A"
    go=GOALS.get(ud.get("goal",""),"N/A") if ud else "N/A"
    qa=await db.get_usage(uid,"q"); aa=await db.get_usage(uid,"ai")
    tq=ud.get("total_q",0) if ud else 0; pts=ud.get("points",0) if ud else 0
    streak=ud.get("streak",0) if ud else 0; max_s=ud.get("max_streak",0) if ud else 0
    badges=ud.get("badges",[]) if ud else []; rank=await db.get_rank(uid)
    ref_count=ud.get("ref_count",0) if ud else 0
    badges_txt=" ".join(badges[:3]) if badges else "Koi badge nahi abhi"
    await q.edit_message_text(
        f"👤 *Meri Profile*\n\n"
        f"📚 {cl} | 📖 {co}\n🎯 {go}\n"
        f"💎 {'Premium ✨' if prem else 'Free'}\n\n"
        f"⭐ Points: *{pts}* | Rank: *#{rank}*\n"
        f"🔥 Streak: *{streak}* din | Best: *{max_s}*\n"
        f"👥 Referrals: *{ref_count}*\n"
        f"🏅 Badges: {badges_txt}\n\n"
        f"📊 *Aaj:*\n❓ Sawaal: {qa}/{'∞' if prem else '10'}\n"
        f"🤖 AI: {aa}/{'∞' if prem else '10'}\n📈 Total: {tq}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✏️ Profile Update",callback_data="update_profile")],
            [InlineKeyboardButton("🏆 Leaderboard",callback_data="leaderboard")],
            [InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    return MENU

async def help_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    await q.edit_message_text(
        f"ℹ️ *@IndiaStudyAI\\_Bot Help*\n\n"
        "/start — Shuru karo\n/menu — Main menu\n\n"
        "*Free:* 10 sawaal/din, 10 AI/din\n*Premium ₹199:* Sab unlimited\n\n"
        "*Points kamao:*\n• Sawaal poochho: +2 pts\n• Daily challenge: +20 pts\n• Refer karo: +100 pts\n• Streak badges: +bonus\n\n"
        f"🌐 App: {MINI_APP}",
        parse_mode="Markdown",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    return MENU

async def back_menu(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    ctx.user_data["mode"]="question"; return await _send_menu(q,ctx)

async def update_profile(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    await q.edit_message_text("✏️ Class dobara select karo:",reply_markup=kb(CLASSES,"cl_"))
    return SELECT_CLASS

async def feedback_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query
    if q.data=="fb_good":
        await q.answer("✅ Shukriya! +1 point! 😊",show_alert=False)
        await db.add_points(q.from_user.id,1)
    else:
        await q.answer("📝 Feedback note kar liya! Improve karenge.",show_alert=False)
    return MENU

async def retry_cb(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    q=update.callback_query;await q.answer()
    kind=q.data.replace("retry_",""); ctx.user_data["mode"]="ai" if kind=="ai" else "question"
    await q.edit_message_text("🔄 Type karo apna sawaal!",reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Menu",callback_data="back_menu")]]))
    return CHATTING

# ── Scheduled Jobs ────────────────────────────────────────────────────────────
async def send_morning_messages(bot):
    """7 AM daily — morning motivation"""
    log.info("📢 Sending morning messages...")
    users=await db.morning_notify_users()
    sent=0
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
                    [InlineKeyboardButton("📢 Updates",callback_data="updates")]]))
            sent+=1
        except: pass
    log.info(f"✅ Morning messages sent: {sent}")

async def send_exam_reminders(bot):
    """Daily exam reminders"""
    reminders=await db.get_exam_reminders()
    for r in reminders:
        try:
            days=r["days_left"]; name=r.get("exam_name","Exam")
            if days==1: msg=f"⚠️ *Kal hai {name}!*\n\nAaj raat revision karo! 🔥\nBest of luck! 🍀"
            elif days==7: msg=f"📅 *{name} mein sirf 7 din baaki!*\n\nRevision shuru karo! 📚"
            else: msg=f"📅 *{name} mein {days} din baaki hain!*\n\nAchhi preparation karo! 💪"
            await bot.send_message(r["user_id"],msg,parse_mode="Markdown")
        except: pass

# ── Admin Commands ────────────────────────────────────────────────────────────
async def cmd_addpremium(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!=OWNER_ID: return
    if not ctx.args: await update.message.reply_text("Usage: /addpremium <id> [days]"); return
    uid=int(ctx.args[0]); days=int(ctx.args[1]) if len(ctx.args)>1 else 30
    await db.set_premium(uid,days)
    try: await ctx.bot.send_message(uid,"🎉 *Premium active!* Unlimited padhai karo!",parse_mode="Markdown")
    except: pass
    await update.message.reply_text(f"✅ Premium: {uid} ({days} days)")

async def cmd_removepremium(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!=OWNER_ID: return
    if not ctx.args: await update.message.reply_text("Usage: /removepremium <id>"); return
    uid=int(ctx.args[0]); await db.remove_premium(uid)
    try: await ctx.bot.send_message(uid,"ℹ️ Premium khatam. /menu se renew karo.")
    except: pass
    await update.message.reply_text(f"✅ Removed: {uid}")

async def cmd_block(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!=OWNER_ID: return
    if not ctx.args: return
    uid=int(ctx.args[0]); await db.block_user(uid)
    try: await ctx.bot.send_message(uid,"❌ Block ho gaye.")
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
        f"📊 *Bot Stats*\n\n👥 Total: {s['total']}\n💎 Premium: {s['premium']}\n"
        f"🚫 Blocked: {s['blocked']}\n❓ Questions: {s['questions']}\n"
        f"✅ Active Today: {s['active_today']}\n\n🌐 App: {MINI_APP}\n\n"
        "📋 *Commands:*\n/addpremium <id> [days]\n/removepremium <id>\n/block /unblock <id>\n/broadcast <msg>",
        parse_mode="Markdown")

async def cmd_broadcast(update:Update,ctx:ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id!=OWNER_ID: return
    if not ctx.args: await update.message.reply_text("Usage: /broadcast <msg>"); return
    msg=" ".join(ctx.args); users=await db.all_users()
    sm=await update.message.reply_text(f"📢 Bhej raha hoon... 0/{len(users)}")
    sent=fail=0
    for i,u in enumerate(users):
        try: await ctx.bot.send_message(u["user_id"],f"📢 *Bot Suchna:*\n\n{msg}",parse_mode="Markdown"); sent+=1
        except: fail+=1
        if (i+1)%25==0:
            try: await sm.edit_text(f"📢 {i+1}/{len(users)}...")
            except: pass
    await sm.edit_text(f"✅ Done!\n✅ {sent}\n❌ {fail}")

async def post_init(app):
    await db.connect()
    # Setup scheduler
    scheduler=AsyncIOScheduler(timezone="Asia/Kolkata")
    scheduler.add_job(send_morning_messages,"cron",hour=7,minute=0,args=[app.bot])
    scheduler.add_job(send_exam_reminders,"cron",hour=8,minute=0,args=[app.bot])
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
                CallbackQueryHandler(copy_ref_cb,pattern="^copy_ref$"),
                CallbackQueryHandler(daily_challenge_cb,pattern="^daily_challenge$"),
                CallbackQueryHandler(challenge_answer_cb,pattern="^ch_"),
                CallbackQueryHandler(set_exam_cb,pattern="^set_exam$"),
                CallbackQueryHandler(change_exam_cb,pattern="^change_exam$"),
                CallbackQueryHandler(settings_cb,pattern="^settings$"),
                CallbackQueryHandler(toggle_morning_cb,pattern="^toggle_morning$"),
                CallbackQueryHandler(toggle_exam_n_cb,pattern="^toggle_exam_n$"),
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
        },
        fallbacks=[CommandHandler("menu",menu_cmd),CommandHandler("start",start)],
        per_message=False,
    )
    app.add_handler(ch)
    for cmd,fn in [("menu",menu_cmd),("addpremium",cmd_addpremium),("removepremium",cmd_removepremium),
                   ("block",cmd_block),("unblock",cmd_unblock),("stats",cmd_stats),("broadcast",cmd_broadcast)]:
        app.add_handler(CommandHandler(cmd,fn))
    log.info("🚀 Bot chalu!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__=="__main__":
    main()
