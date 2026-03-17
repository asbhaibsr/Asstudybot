import os
import logging
import asyncio
import threading
from datetime import datetime, timedelta
from flask import Flask, send_from_directory, jsonify, request
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    MessageHandler, filters, ContextTypes, ConversationHandler
)
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from ai import (
    ask_ai, generate_pdf, image_to_text, fetch_updates,
    generate_mindmap_image, generate_question_paper,
    generate_study_plan, build_vocabulary
)
from db import db

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
log = logging.getLogger(__name__)

# Environment variables
TOKEN = os.environ.get("BOT_TOKEN", "")
OWNER_ID = int(os.environ.get("OWNER_ID", "0"))
PORT = int(os.environ.get("PORT", 8080))
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")
MINI_APP_URL = os.environ.get("MINI_APP_URL", f"https://your-app.koyeb.app")

# States for conversation
(
    SELECT_CLASS, SELECT_SUBJECT, SELECT_GOAL,
    AI_TUTOR, QUICK_QUESTION,
    WAIT_EXAM_NAME, WAIT_EXAM_DATE,
    WAIT_REMINDER_TEXT, WAIT_REMINDER_TIME,
    WAIT_NOTE_TITLE, WAIT_NOTE_CONTENT,
    WAIT_STUDY_PLAN, WAIT_CAREER_INFO,
    WAIT_MINDMAP_TOPIC, WAIT_VOCAB_TOPIC,
    WAIT_QUESTION_PAPER, WAIT_FEEDBACK
) = range(17)

# ==================== FLASK APP FOR MINI APP ====================

flask_app = Flask(__name__, static_folder="app")

@flask_app.route('/')
def home():
    return jsonify({
        "status": "ok",
        "bot": "IndiaStudyAI 2026",
        "message": "Bot is running!"
    })

@flask_app.route('/health')
def health():
    return jsonify({"status": "healthy"}), 200

@flask_app.route('/app')
@flask_app.route('/app/')
def serve_app():
    return send_from_directory('app', 'index.html')

@flask_app.route('/app/<path:path>')
def serve_app_files(path):
    return send_from_directory('app', path)

@flask_app.route('/webhook', methods=['POST'])
def webhook():
    """Webhook for Telegram updates"""
    update = Update.de_json(request.get_json(force=True), app.bot)
    asyncio.run_coroutine_threadsafe(app.process_update(update), app.loop)
    return jsonify({"status": "ok"}), 200

def run_flask():
    """Run Flask in a separate thread"""
    flask_app.run(host='0.0.0.0', port=PORT, debug=False, use_reloader=False)

# ==================== HELPER FUNCTIONS ====================

def get_main_keyboard(user_id: int, premium: bool = False):
    """Get main menu keyboard"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📱 Open Mini App", web_app=WebAppInfo(url=f"{MINI_APP_URL}/app"))],
        [InlineKeyboardButton("🤖 AI Study Tutor", callback_data="ai_tutor"),
         InlineKeyboardButton("❓ Quick Question", callback_data="quick_q")],
        [InlineKeyboardButton("📢 Sarkari Updates", callback_data="updates"),
         InlineKeyboardButton("📰 Hindi News", callback_data="news")],
        [InlineKeyboardButton("📝 Question Paper", callback_data="qpaper"),
         InlineKeyboardButton("🗺️ Mind Map", callback_data="mindmap")],
        [InlineKeyboardButton("📊 Study Planner", callback_data="planner"),
         InlineKeyboardButton("📖 Vocabulary", callback_data="vocab")],
        [InlineKeyboardButton("📷 Image to Text", callback_data="ocr"),
         InlineKeyboardButton("📄 My Notes", callback_data="notes")],
        [InlineKeyboardButton("👥 Refer & Earn", callback_data="refer"),
         InlineKeyboardButton("💎 Premium", callback_data="premium")],
        [InlineKeyboardButton("👤 Profile", callback_data="profile"),
         InlineKeyboardButton("⚙️ Settings", callback_data="settings")],
        [InlineKeyboardButton("📤 Share Bot", url=f"https://t.me/share/url?url=https://t.me/IndiaStudyAI_Bot&text=India's Best Study Bot!")]
    ])

def get_back_button():
    """Get back button"""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔙 Back to Menu", callback_data="menu")]
    ])

# ==================== START COMMAND ====================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start command handler"""
    user = update.effective_user
    
    # Check for referral
    ref_by = None
    if context.args and context.args[0].startswith("ref"):
        try:
            ref_by = int(context.args[0][3:])
        except:
            pass
    
    # Add user to database
    await db.add_user(
        user_id=user.id,
        name=user.first_name,
        username=user.username,
        ref_by=ref_by
    )
    
    # Check if user has profile
    db_user = await db.get_user(user.id)
    
    if db_user and db_user.get("class_type"):
        # User already has profile, show menu
        premium = await db.is_premium(user.id)
        await update.message.reply_text(
            f"👋 Welcome back, {user.first_name}!\n\nWhat would you like to study today?",
            reply_markup=get_main_keyboard(user.id, premium)
        )
        return ConversationHandler.END
    else:
        # New user - start profile setup
        await update.message.reply_text(
            f"👋 Namaste {user.first_name}!\n\n"
            f"🎓 Let's setup your profile first.\n\n"
            f"Select your class:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📚 Class 1-5", callback_data="class_1_5"),
                 InlineKeyboardButton("📖 Class 6-8", callback_data="class_6_8")],
                [InlineKeyboardButton("🎓 Class 9-10", callback_data="class_9_10"),
                 InlineKeyboardButton("🏫 Class 11-12", callback_data="class_11_12")],
                [InlineKeyboardButton("🎓 College", callback_data="class_college"),
                 InlineKeyboardButton("👨‍💼 Job Prep", callback_data="class_job")]
            ])
        )
        return SELECT_CLASS

# ==================== PROFILE SETUP ====================

async def select_class(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle class selection"""
    query = update.callback_query
    await query.answer()
    
    class_map = {
        "class_1_5": "Class 1-5",
        "class_6_8": "Class 6-8",
        "class_9_10": "Class 9-10",
        "class_11_12": "Class 11-12",
        "class_college": "College",
        "class_job": "Job Preparation"
    }
    
    context.user_data["class_type"] = class_map.get(query.data, "Class 9-10")
    
    await query.edit_message_text(
        f"✅ Class selected: {context.user_data['class_type']}\n\n"
        f"Now select your main subject:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("➕ Maths", callback_data="subj_math"),
             InlineKeyboardButton("🔬 Science", callback_data="subj_science")],
            [InlineKeyboardButton("🇮🇳 Hindi", callback_data="subj_hindi"),
             InlineKeyboardButton("🇬🇧 English", callback_data="subj_english")],
            [InlineKeyboardButton("⚛️ Physics", callback_data="subj_physics"),
             InlineKeyboardButton("🧪 Chemistry", callback_data="subj_chemistry")],
            [InlineKeyboardButton("🧬 Biology", callback_data="subj_bio"),
             InlineKeyboardButton("🌍 History", callback_data="subj_history")],
            [InlineKeyboardButton("💻 Computer", callback_data="subj_computer"),
             InlineKeyboardButton("🧠 GK", callback_data="subj_gk")]
        ])
    )
    return SELECT_SUBJECT

async def select_subject(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle subject selection"""
    query = update.callback_query
    await query.answer()
    
    subject_map = {
        "subj_math": "Mathematics",
        "subj_science": "Science",
        "subj_hindi": "Hindi",
        "subj_english": "English",
        "subj_physics": "Physics",
        "subj_chemistry": "Chemistry",
        "subj_bio": "Biology",
        "subj_history": "History",
        "subj_computer": "Computer Science",
        "subj_gk": "General Knowledge"
    }
    
    context.user_data["subject"] = subject_map.get(query.data, "Mathematics")
    
    await query.edit_message_text(
        f"✅ Subject selected: {context.user_data['subject']}\n\n"
        f"Finally, select your goal:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 Exam Preparation", callback_data="goal_exam"),
             InlineKeyboardButton("💡 Skill Building", callback_data="goal_skill")],
            [InlineKeyboardButton("📋 Homework Help", callback_data="goal_homework"),
             InlineKeyboardButton("🏆 Competitive Exams", callback_data="goal_competitive")],
            [InlineKeyboardButton("🎨 Just Learning", callback_data="goal_hobby")]
        ])
    )
    return SELECT_GOAL

async def select_goal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle goal selection and finish profile"""
    query = update.callback_query
    await query.answer()
    
    goal_map = {
        "goal_exam": "Exam Preparation",
        "goal_skill": "Skill Building",
        "goal_homework": "Homework Help",
        "goal_competitive": "Competitive Exams",
        "goal_hobby": "Just Learning"
    }
    
    goal = goal_map.get(query.data, "Exam Preparation")
    
    # Save profile to database
    await db.update_profile(
        user_id=query.from_user.id,
        class_type=context.user_data["class_type"],
        course=context.user_data["subject"],
        goal=goal
    )
    
    # Give joining bonus
    await db.add_points(query.from_user.id, 50)
    
    await query.edit_message_text(
        f"🎉 Profile Complete!\n\n"
        f"📚 Class: {context.user_data['class_type']}\n"
        f"📖 Subject: {context.user_data['subject']}\n"
        f"🎯 Goal: {goal}\n\n"
        f"✨ You got 50 bonus points!\n\n"
        f"What would you like to do now?",
        reply_markup=get_main_keyboard(query.from_user.id)
    )
    return ConversationHandler.END

# ==================== AI TUTOR ====================

async def ai_tutor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start AI tutor mode"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    premium = await db.is_premium(user_id)
    usage = await db.get_usage(user_id, "ai")
    limit = 999 if premium else 15
    
    if not premium and usage >= limit:
        await query.edit_message_text(
            "⚠️ You've reached your daily limit (15 questions).\n\n"
            "💎 Get Premium for unlimited questions!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💎 Get Premium", callback_data="premium")],
                [InlineKeyboardButton("🔙 Menu", callback_data="menu")]
            ])
        )
        return ConversationHandler.END
    
    await query.edit_message_text(
        "🤖 AI Study Tutor Activated!\n\n"
        f"💬 Questions left today: {'∞' if premium else limit - usage}\n\n"
        "Ask me anything about your studies. I'll explain like a story so you never forget!\n\n"
        "_Type your question below or send an image_",
        reply_markup=get_back_button()
    )
    context.user_data["mode"] = "ai_tutor"
    return AI_TUTOR

# ==================== QUICK QUESTION ====================

async def quick_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start quick question mode"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    premium = await db.is_premium(user_id)
    usage = await db.get_usage(user_id, "q")
    limit = 999 if premium else 20
    
    if not premium and usage >= limit:
        await query.edit_message_text(
            "⚠️ Daily limit reached (20 questions).\n\n"
            "💎 Get Premium for unlimited!",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("💎 Premium", callback_data="premium")],
                [InlineKeyboardButton("🔙 Menu", callback_data="menu")]
            ])
        )
        return ConversationHandler.END
    
    await query.edit_message_text(
        "❓ Quick Question Mode\n\n"
        f"Questions left: {'∞' if premium else limit - usage}\n\n"
        "Type your question and I'll give a quick answer!",
        reply_markup=get_back_button()
    )
    context.user_data["mode"] = "quick"
    return QUICK_QUESTION

# ==================== HANDLE TEXT MESSAGES ====================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all text messages"""
    user_id = update.effective_user.id
    text = update.message.text
    
    # Check if user is blocked
    if await db.is_blocked(user_id):
        await update.message.reply_text("❌ You are blocked from using this bot.")
        return ConversationHandler.END
    
    mode = context.user_data.get("mode", "quick")
    
    # Handle different modes
    if mode == "ai_tutor" or mode == "quick":
        # Get answer from AI
        wait_msg = await update.message.reply_text("🤔 Thinking...")
        
        # Get user data for context
        user_data = await db.get_user(user_id)
        
        # Get answer
        answer, provider = await ask_ai(text, user_data, mode)
        
        # Track usage
        await db.inc_usage(user_id, "ai" if mode == "ai_tutor" else "q")
        
        # Save to history
        await db.save_q(user_id, text, answer, provider)
        
        await wait_msg.delete()
        
        # Create reply keyboard
        keyboard = [
            [InlineKeyboardButton("📝 Save as Note", callback_data="save_note"),
             InlineKeyboardButton("📄 Download PDF", callback_data="download_pdf")],
            [InlineKeyboardButton("📤 Share WhatsApp", url=f"https://wa.me/?text={answer[:300].replace(' ', '%20')}..."),
             InlineKeyboardButton("🔙 Menu", callback_data="menu")]
        ]
        
        await update.message.reply_text(
            answer,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        # Store last answer for saving
        context.user_data["last_answer"] = answer
        context.user_data["last_question"] = text
        
    elif mode == "wait_feedback":
        # Save feedback
        await db.save_feedback(user_id, 5, text)  # Rating 5 for text feedback
        await update.message.reply_text(
            "✅ Thank you for your feedback!",
            reply_markup=get_main_keyboard(user_id, await db.is_premium(user_id))
        )
        context.user_data["mode"] = None
        return ConversationHandler.END
    
    return mode

# ==================== HANDLE PHOTOS ====================

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photo messages for OCR"""
    user_id = update.effective_user.id
    
    if await db.is_blocked(user_id):
        await update.message.reply_text("❌ You are blocked.")
        return
    
    wait_msg = await update.message.reply_text("📷 Processing image...")
    
    try:
        # Download photo
        photo = update.message.photo[-1]
        file = await context.bot.get_file(photo.file_id)
        path = f"/tmp/{user_id}_{datetime.now().timestamp()}.jpg"
        await file.download_to_drive(path)
        
        # Extract text
        text = await image_to_text(path)
        
        # Clean up
        try:
            os.remove(path)
        except:
            pass
        
        await wait_msg.delete()
        
        keyboard = [
            [InlineKeyboardButton("📝 Save as Note", callback_data="save_note"),
             InlineKeyboardButton("🔙 Menu", callback_data="menu")]
        ]
        
        await update.message.reply_text(
            f"📷 Extracted Text:\n\n{text}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        
        context.user_data["last_answer"] = text
        
    except Exception as e:
        log.error(f"Photo handling error: {e}")
        await wait_msg.delete()
        await update.message.reply_text(
            "❌ Failed to process image. Please try again.",
            reply_markup=get_back_button()
        )

# ==================== UPDATES & NEWS ====================

async def show_updates(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show sarkari updates"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text("📢 Fetching latest updates...")
    
    updates = await fetch_updates("all")
    
    keyboard = [
        [InlineKeyboardButton("💼 Jobs", callback_data="upd_jobs"),
         InlineKeyboardButton("📋 Forms", callback_data="upd_forms")],
        [InlineKeyboardButton("📊 Results", callback_data="upd_results"),
         InlineKeyboardButton("🪪 Admit Cards", callback_data="upd_admit")],
        [InlineKeyboardButton("🔄 Refresh", callback_data="updates"),
         InlineKeyboardButton("🔙 Menu", callback_data="menu")]
    ]
    
    await query.edit_message_text(
        f"📢 *Latest Sarkari Updates*\n\n{updates}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def show_news(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show Hindi news"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text("📰 Fetching latest news...")
    
    # Try to get from cache
    news = await db.get_cache("news_india")
    if not news:
        news = await ask_ai_simple("Latest India news headlines for today. 8 items with brief description.", mode="quick")
        await db.set_cache("news_india", news, 6)  # Cache for 6 hours
    
    keyboard = [
        [InlineKeyboardButton("🏛️ Politics", callback_data="news_pol"),
         InlineKeyboardButton("🏏 Sports", callback_data="news_sports")],
        [InlineKeyboardButton("💼 Business", callback_data="news_biz"),
         InInlineKeyboardButton("📚 Education", callback_data="news_edu")],
        [InlineKeyboardButton("🔄 Refresh", callback_data="news"),
         InlineKeyboardButton("🔙 Menu", callback_data="menu")]
    ]
    
    await query.edit_message_text(
        f"📰 *Today's News*\n\n{news}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ==================== NOTES ====================

async def my_notes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user's notes"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    notes = await db.get_user_notes(user_id)
    
    if not notes:
        await query.edit_message_text(
            "📝 You don't have any notes yet.\n\n"
            "Save notes from AI answers by clicking 'Save as Note' button.",
            reply_markup=get_back_button()
        )
        return
    
    # Create note list
    text = "📝 *Your Notes*\n\n"
    keyboard = []
    
    for i, note in enumerate(notes[:10], 1):
        title = note.get("title", f"Note {i}")[:30]
        text += f"{i}. {title}\n"
        keyboard.append([InlineKeyboardButton(
            f"📖 {title}", 
            callback_data=f"view_note_{note['_id']}"
        )])
    
    keyboard.append([InlineKeyboardButton("🔙 Menu", callback_data="menu")])
    
    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def view_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """View a specific note"""
    query = update.callback_query
    await query.answer()
    
    note_id = query.data.replace("view_note_", "")
    user_id = query.from_user.id
    
    note = await db.get_note(user_id, note_id)
    if not note:
        await query.edit_message_text("❌ Note not found.", reply_markup=get_back_button())
        return
    
    content = note.get("content", "")[:500]
    
    keyboard = [
        [InlineKeyboardButton("📄 Download PDF", callback_data=f"note_pdf_{note_id}"),
         InlineKeyboardButton("🗑️ Delete", callback_data=f"del_note_{note_id}")],
        [InlineKeyboardButton("🔙 Back", callback_data="notes")]
    ]
    
    await query.edit_message_text(
        f"📝 *{note.get('title', 'Note')}*\n\n{content}",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def delete_note(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Delete a note"""
    query = update.callback_query
    await query.answer()
    
    note_id = query.data.replace("del_note_", "")
    user_id = query.from_user.id
    
    await db.delete_note(user_id, note_id)
    await query.answer("✅ Note deleted!", show_alert=True)
    
    # Go back to notes list
    await my_notes(update, context)

# ==================== REFERRAL SYSTEM ====================

async def refer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show referral info"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    ref_count = await db.get_referral_count(user_id)
    
    ref_link = f"https://t.me/IndiaStudyAI_Bot?start=ref{user_id}"
    
    text = (
        f"👥 *Refer & Earn*\n\n"
        f"Your Referral Link:\n`{ref_link}`\n\n"
        f"📊 Total Referrals: *{ref_count}*\n\n"
        f"🎁 *Rewards:*\n"
        f"• Each referral = 100 points\n"
        f"• 20 referrals = 1 Week FREE Premium\n\n"
        f"Share your link with friends!"
    )
    
    keyboard = [
        [InlineKeyboardButton("📤 Share Link", url=f"https://t.me/share/url?url={ref_link}&text=Join India's best study bot!")],
        [InlineKeyboardButton("📋 Copy Link", callback_data="copy_link")],
        [InlineKeyboardButton("🔙 Menu", callback_data="menu")]
    ]
    
    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ==================== PROFILE ====================

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show user profile"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user = await db.get_user(user_id)
    
    if not user:
        await query.edit_message_text("❌ User not found.", reply_markup=get_back_button())
        return
    
    premium = await db.is_premium(user_id)
    rank = await db.get_rank(user_id)
    
    text = (
        f"👤 *Your Profile*\n\n"
        f"📚 Class: {user.get('class_type', 'Not set')}\n"
        f"📖 Subject: {user.get('course', 'Not set')}\n"
        f"🎯 Goal: {user.get('goal', 'Not set')}\n\n"
        f"⭐ Points: *{user.get('points', 0)}*\n"
        f"🏆 Rank: *#{rank}*\n"
        f"🔥 Streak: *{user.get('streak', 0)} days*\n"
        f"📊 Max Streak: *{user.get('max_streak', 0)}*\n"
        f"❓ Total Questions: *{user.get('total_questions', 0)}*\n"
        f"👥 Referrals: *{user.get('ref_count', 0)}*\n\n"
        f"💎 Premium: {'✅ Active' if premium else '❌ Not Active'}\n"
        f"🏅 Badges: {' '.join(user.get('badges', []))}"
    )
    
    keyboard = [
        [InlineKeyboardButton("📝 My Notes", callback_data="notes"),
         InlineKeyboardButton("📊 Stats", callback_data="stats")],
        [InlineKeyboardButton("🔙 Menu", callback_data="menu")]
    ]
    
    await query.edit_message_text(
        text,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# ==================== SETTINGS ====================

async def settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show settings menu"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user = await db.get_user(user_id)
    
    lang = user.get("language", "hi")
    lang_text = "🇮🇳 Hindi" if lang == "hi" else "🇬🇧 English" if lang == "en" else "🔀 Hinglish"
    
    morning = user.get("notify_morning", True)
    exam_notify = user.get("notify_exam", True)
    
    keyboard = [
        [InlineKeyboardButton(f"🌐 Language: {lang_text}", callback_data="change_lang")],
        [InlineKeyboardButton(f"🌅 Morning: {'✅ ON' if morning else '❌ OFF'}", callback_data="toggle_morning")],
        [InlineKeyboardButton(f"📅 Exam: {'✅ ON' if exam_notify else '❌ OFF'}", callback_data="toggle_exam")],
        [InlineKeyboardButton("📝 Edit Profile", callback_data="edit_profile")],
        [InlineKeyboardButton("❓ Help", callback_data="help"),
         InlineKeyboardButton("💬 Feedback", callback_data="feedback")],
        [InlineKeyboardButton("🔙 Menu", callback_data="menu")]
    ]
    
    await query.edit_message_text(
        "⚙️ *Settings*\n\nCustomize your experience:",
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def change_lang(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Change language"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    user = await db.get_user(user_id)
    current = user.get("language", "hi")
    
    next_lang = "en" if current == "hi" else "mix" if current == "en" else "hi"
    lang_names = {"hi": "🇮🇳 Hindi", "en": "🇬🇧 English", "mix": "🔀 Hinglish"}
    
    await db.update_language(user_id, next_lang)
    await query.answer(f"Language set to {lang_names[next_lang]}", show_alert=True)
    
    # Refresh settings
    await settings(update, context)

# ==================== PREMIUM ====================

async def premium_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show premium info"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    premium = await db.is_premium(user_id)
    
    if premium:
        user = await db.get_user(user_id)
        expiry = user.get("premium_expiry", "").strftime("%d %b %Y") if user.get("premium_expiry") else "N/A"
        
        await query.edit_message_text(
            f"💎 *Premium Active*\n\n"
            f"Expiry: {expiry}\n\n"
            f"✨ You have access to all premium features!",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Menu", callback_data="menu")]
            ])
        )
    else:
        await query.edit_message_text(
            "💎 *Premium Features*\n\n"
            "✅ Unlimited AI questions\n"
            "✅ Unlimited notes & PDFs\n"
            "✅ Chat history (30 days)\n"
            "✅ Priority support\n"
            "✅ Advanced study tools\n\n"
            "💰 Price: ₹199/month\n"
            "🎁 FREE: 20 referrals = 1 week premium\n\n"
            "UPI ID: `arsadsaifi8272@ibl`\n\n"
            "Send screenshot after payment.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("✅ I've Paid", callback_data="paid")],
                [InlineKeyboardButton("🎁 Get FREE via Refer", callback_data="refer")],
                [InlineKeyboardButton("🔙 Menu", callback_data="menu")]
            ])
        )

# ==================== FEEDBACK ====================

async def feedback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Ask for feedback"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "💬 We'd love to hear your feedback!\n\n"
        "Please type your feedback below:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 Cancel", callback_data="menu")]
        ])
    )
    context.user_data["mode"] = "wait_feedback"
    return WAIT_FEEDBACK

# ==================== CALLBACK HANDLER ====================

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all callbacks"""
    query = update.callback_query
    data = query.data
    
    # Handle menu navigation
    if data == "menu":
        await query.answer()
        premium = await db.is_premium(query.from_user.id)
        await query.edit_message_text(
            "🏠 *Main Menu*\n\nWhat would you like to do?",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard(query.from_user.id, premium)
        )
        return ConversationHandler.END
    
    elif data == "ai_tutor":
        return await ai_tutor(update, context)
    
    elif data == "quick_q":
        return await quick_question(update, context)
    
    elif data == "updates":
        await show_updates(update, context)
    
    elif data == "news":
        await show_news(update, context)
    
    elif data == "notes":
        await my_notes(update, context)
    
    elif data.startswith("view_note_"):
        await view_note(update, context)
    
    elif data.startswith("del_note_"):
        await delete_note(update, context)
    
    elif data == "refer":
        await refer(update, context)
    
    elif data == "profile":
        await profile(update, context)
    
    elif data == "settings":
        await settings(update, context)
    
    elif data == "change_lang":
        await change_lang(update, context)
    
    elif data == "premium":
        await premium_info(update, context)
    
    elif data == "feedback":
        return await feedback(update, context)
    
    elif data == "save_note":
        # Save last answer as note
        user_id = query.from_user.id
        last_answer = context.user_data.get("last_answer", "")
        last_question = context.user_data.get("last_question", "AI Answer")
        
        if last_answer:
            await db.save_note(user_id, last_question[:50], last_answer, "AI")
            await query.answer("✅ Note saved!", show_alert=True)
        else:
            await query.answer("❌ No answer to save", show_alert=True)
    
    elif data == "download_pdf":
        # Download last answer as PDF
        user_id = query.from_user.id
        last_answer = context.user_data.get("last_answer", "")
        last_question = context.user_data.get("last_question", "Notes")
        
        if not last_answer:
            await query.answer("❌ No content to download", show_alert=True)
            return
        
        await query.answer("📄 Generating PDF...")
        
        pdf_path = await generate_pdf(last_question, last_answer)
        
        if pdf_path and os.path.exists(pdf_path):
            with open(pdf_path, 'rb') as f:
                await context.bot.send_document(
                    chat_id=user_id,
                    document=f,
                    filename=f"{last_question[:30]}.pdf",
                    caption="📄 Your PDF is ready!"
                )
    
    elif data == "copy_link":
        ref_link = f"https://t.me/IndiaStudyAI_Bot?start=ref{query.from_user.id}"
        await query.answer(f"Link copied: {ref_link}", show_alert=True)
    
    elif data == "paid":
        await query.edit_message_text(
            "📸 Please send a screenshot of your payment.\n\n"
            "We'll activate premium within 24 hours.",
            reply_markup=get_back_button()
        )
        context.user_data["mode"] = "wait_payment"
    
    elif data.startswith("upd_"):
        # Handle update categories
        cat = data.replace("upd_", "")
        await query.answer(f"Loading {cat}...")
        updates = await fetch_updates(cat)
        await query.edit_message_text(
            f"📢 *{cat.upper()} Updates*\n\n{updates}",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔄 Refresh", callback_data="updates"),
                 InlineKeyboardButton("🔙 Menu", callback_data="menu")]
            ])
        )
    
    elif data == "mindmap":
        await query.edit_message_text(
            "🗺️ *Mind Map Generator*\n\n"
            "Enter a topic to generate a mind map:",
            reply_markup=get_back_button()
        )
        context.user_data["mode"] = "wait_mindmap"
        return WAIT_MINDMAP_TOPIC
    
    elif data == "qpaper":
        await query.edit_message_text(
            "📝 *Question Paper Generator*\n\n"
            "Enter subject name (e.g., Mathematics, Science, Physics):",
            reply_markup=get_back_button()
        )
        context.user_data["mode"] = "wait_qpaper"
        return WAIT_QUESTION_PAPER
    
    elif data == "vocab":
        await query.edit_message_text(
            "📖 *Vocabulary Builder*\n\n"
            "Enter a topic (e.g., Environment, Technology, Business):",
            reply_markup=get_back_button()
        )
        context.user_data["mode"] = "wait_vocab"
        return WAIT_VOCAB_TOPIC
    
    elif data == "planner":
        await query.edit_message_text(
            "📊 *Study Planner*\n\n"
            "Enter your subjects (comma separated) and exam date:\n"
            "Format: `Subjects | YYYY-MM-DD | Hours per day`\n\n"
            "Example: `Math, Physics, Chemistry | 2026-04-10 | 5`",
            reply_markup=get_back_button()
        )
        context.user_data["mode"] = "wait_planner"
        return WAIT_STUDY_PLAN

# ==================== SPECIAL MODE HANDLERS ====================

async def handle_mindmap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle mind map generation"""
    topic = update.message.text
    user_id = update.effective_user.id
    
    wait_msg = await update.message.reply_text("🗺️ Generating mind map...")
    
    try:
        # Generate mind map image
        image_path = await generate_mindmap_image(topic)
        
        if image_path and os.path.exists(image_path):
            with open(image_path, 'rb') as f:
                await context.bot.send_photo(
                    chat_id=user_id,
                    photo=f,
                    caption=f"🗺️ Mind Map: {topic}",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Menu", callback_data="menu")]
                    ])
                )
        else:
            # Fallback to text mind map
            mindmap_text = await ask_ai_simple(f"Create a text mind map for {topic}")
            await update.message.reply_text(
                mindmap_text,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Menu", callback_data="menu")]
                ])
            )
        
        await wait_msg.delete()
        
    except Exception as e:
        log.error(f"Mind map error: {e}")
        await wait_msg.delete()
        await update.message.reply_text(
            "❌ Failed to generate mind map. Please try again.",
            reply_markup=get_back_button()
        )
    
    context.user_data["mode"] = None
    return ConversationHandler.END

async def handle_qpaper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle question paper generation"""
    subject = update.message.text
    user_id = update.effective_user.id
    
    wait_msg = await update.message.reply_text("📝 Generating question paper...")
    
    # Get user's class
    user = await db.get_user(user_id)
    class_name = user.get("class_type", "Class 10") if user else "Class 10"
    
    # Generate paper
    paper = await generate_question_paper(subject, class_name, "Medium")
    
    await wait_msg.delete()
    
    # Create PDF
    pdf_path = await generate_pdf(f"Question Paper - {subject}", paper)
    
    if pdf_path and os.path.exists(pdf_path):
        with open(pdf_path, 'rb') as f:
            await context.bot.send_document(
                chat_id=user_id,
                document=f,
                filename=f"{subject}_Question_Paper.pdf",
                caption=f"📝 Question Paper: {subject}",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Menu", callback_data="menu")]
                ])
            )
    else:
        await update.message.reply_text(
            paper,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Menu", callback_data="menu")]
            ])
        )
    
    context.user_data["mode"] = None
    return ConversationHandler.END

async def handle_vocab(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle vocabulary generation"""
    topic = update.message.text
    user_id = update.effective_user.id
    
    wait_msg = await update.message.reply_text("📖 Building vocabulary...")
    
    # Get user's language
    user = await db.get_user(user_id)
    lang = user.get("language", "hi") if user else "hi"
    
    # Generate vocabulary
    vocab = await build_vocabulary(topic, lang)
    
    await wait_msg.delete()
    
    await update.message.reply_text(
        vocab,
        parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 Save as Note", callback_data="save_note"),
             InlineKeyboardButton("🔙 Menu", callback_data="menu")]
        ])
    )
    
    context.user_data["last_answer"] = vocab
    context.user_data["mode"] = None
    return ConversationHandler.END

async def handle_planner(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle study plan generation"""
    text = update.message.text
    user_id = update.effective_user.id
    
    try:
        # Parse input
        parts = text.split('|')
        if len(parts) >= 2:
            subjects = parts[0].strip()
            exam_date = parts[1].strip()
            hours = int(parts[2].strip()) if len(parts) >= 3 else 4
        else:
            subjects = text
            exam_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
            hours = 4
        
        wait_msg = await update.message.reply_text("📊 Creating study plan...")
        
        # Generate plan
        plan = await generate_study_plan(subjects, exam_date, hours)
        
        await wait_msg.delete()
        
        # Save plan
        await db.save_study_plan(user_id, plan, exam_date, subjects)
        
        # Create PDF
        pdf_path = await generate_pdf("Study Plan", plan)
        
        if pdf_path and os.path.exists(pdf_path):
            with open(pdf_path, 'rb') as f:
                await context.bot.send_document(
                    chat_id=user_id,
                    document=f,
                    filename="Study_Plan.pdf",
                    caption="📊 Your Personalized Study Plan",
                    reply_markup=InlineKeyboardMarkup([
                        [InlineKeyboardButton("🔙 Menu", callback_data="menu")]
                    ])
                )
        else:
            await update.message.reply_text(
                plan,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 Menu", callback_data="menu")]
                ])
            )
        
    except Exception as e:
        log.error(f"Planner error: {e}")
        await update.message.reply_text(
            "❌ Failed to create plan. Please check format.",
            reply_markup=get_back_button()
        )
    
    context.user_data["mode"] = None
    return ConversationHandler.END

# ==================== SCHEDULED JOBS ====================

async def send_morning_messages(app):
    """Send morning messages to users"""
    users = await db.morning_notify_users()
    sent = 0
    
    for user in users:
        try:
            user_id = user["user_id"]
            name = user.get("name", "Student")
            streak = user.get("streak", 0)
            
            # Get quote of the day
            quote = await ask_ai_simple("Give a short motivational quote in Hindi for students", mode="quick")
            
            message = (
                f"🌅 *Good Morning, {name}!*\n\n"
                f"{quote}\n\n"
                f"🔥 Current Streak: *{streak} days*\n\n"
                f"Today's Goals:\n"
                f"• Study at least 2 hours\n"
                f"• Complete daily challenge\n"
                f"• Review yesterday's topics\n\n"
                f"✨ Make today count!"
            )
            
            await app.bot.send_message(
                chat_id=user_id,
                text=message,
                parse_mode="Markdown",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🎯 Daily Challenge", callback_data="challenge"),
                     InlineKeyboardButton("📚 Start Studying", callback_data="ai_tutor")]
                ])
            )
            sent += 1
            
        except Exception as e:
            log.error(f"Morning message error for {user_id}: {e}")
    
    log.info(f"Morning messages sent: {sent}")

async def check_reminders(app):
    """Check and send due reminders"""
    reminders = await db.get_due_reminders()
    
    for reminder in reminders:
        try:
            await app.bot.send_message(
                chat_id=reminder["user_id"],
                text=f"⏰ *Reminder*\n\n{reminder['text']}",
                parse_mode="Markdown"
            )
            await db.mark_reminder_sent(str(reminder["_id"]))
            
        except Exception as e:
            log.error(f"Reminder error: {e}")

async def check_exam_reminders(app):
    """Check and send exam reminders"""
    reminders = await db.get_exam_reminders()
    
    for rem in reminders:
        try:
            days = rem["days_left"]
            if days == 1:
                msg = f"⚠️ *TOMORROW* is your {rem['exam_name']} exam! Best of luck! 🍀"
            elif days == 7:
                msg = f"📅 *7 days left* for {rem['exam_name']} exam. Start revision! 📚"
            elif days == 30:
                msg = f"📅 *30 days left* for {rem['exam_name']} exam. Make a study plan!"
            else:
                msg = f"📅 {rem['days_left']} days left for {rem['exam_name']} exam."
            
            await app.bot.send_message(
                chat_id=rem["user_id"],
                text=msg,
                parse_mode="Markdown"
            )
            
        except Exception as e:
            log.error(f"Exam reminder error: {e}")

# ==================== ADMIN COMMANDS ====================

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: Show bot statistics"""
    if update.effective_user.id != OWNER_ID:
        return
    
    stats = await db.stats()
    
    text = (
        f"📊 *Bot Statistics*\n\n"
        f"👥 Total Users: *{stats['total']}*\n"
        f"✅ Active Today: *{stats['active_today']}*\n"
        f"🆕 New Today: *{stats['new_today']}*\n"
        f"💎 Premium Users: *{stats['premium']}*\n"
        f"🚫 Blocked: *{stats['blocked']}*\n"
        f"❓ Total Questions: *{stats['questions']}*\n"
        f"📝 Total Notes: *{stats['notes_total']}*"
    )
    
    await update.message.reply_text(text, parse_mode="Markdown")

async def admin_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: Broadcast message to all users"""
    if update.effective_user.id != OWNER_ID:
        return
    
    if not context.args:
        await update.message.reply_text("Usage: /broadcast <message>")
        return
    
    message = " ".join(context.args)
    
    # Get all users
    users = await db.users.find({}).to_list(length=None)
    
    sent = 0
    failed = 0
    
    status_msg = await update.message.reply_text(f"📢 Broadcasting... 0/{len(users)}")
    
    for i, user in enumerate(users):
        try:
            await context.bot.send_message(
                chat_id=user["user_id"],
                text=f"📢 *Broadcast Message*\n\n{message}",
                parse_mode="Markdown"
            )
            sent += 1
        except:
            failed += 1
        
        if (i + 1) % 10 == 0:
            await status_msg.edit_text(f"📢 Broadcasting... {i+1}/{len(users)}")
    
    await status_msg.edit_text(
        f"✅ Broadcast complete!\n"
        f"Sent: {sent}\n"
        f"Failed: {failed}"
    )

async def admin_add_premium(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: Add premium to user"""
    if update.effective_user.id != OWNER_ID:
        return
    
    try:
        user_id = int(context.args[0])
        days = int(context.args[1]) if len(context.args) > 1 else 30
        
        await db.set_premium(user_id, days)
        
        await update.message.reply_text(f"✅ Premium added to {user_id} for {days} days")
        
        # Notify user
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"🎉 *Premium Activated!*\n\nYour premium is active for {days} days. Enjoy unlimited access!",
                parse_mode="Markdown"
            )
        except:
            pass
            
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {e}")

# ==================== MAIN FUNCTION ====================

def main():
    """Start the bot"""
    global app
    
    # Start Flask in separate thread
    threading.Thread(target=run_flask, daemon=True).start()
    
    # Create application
    app = Application.builder().token(TOKEN).build()
    
    # Add conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            SELECT_CLASS: [CallbackQueryHandler(select_class)],
            SELECT_SUBJECT: [CallbackQueryHandler(select_subject)],
            SELECT_GOAL: [CallbackQueryHandler(select_goal)],
            AI_TUTOR: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)],
            QUICK_QUESTION: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)],
            WAIT_MINDMAP_TOPIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_mindmap)],
            WAIT_QUESTION_PAPER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_qpaper)],
            WAIT_VOCAB_TOPIC: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_vocab)],
            WAIT_STUDY_PLAN: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_planner)],
            WAIT_FEEDBACK: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)],
        },
        fallbacks=[CommandHandler("cancel", lambda u,c: ConversationHandler.END)],
        allow_reentry=True
    )
    
    app.add_handler(conv_handler)
    
    # Add other handlers
    app.add_handler(CallbackQueryHandler(callback_handler))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    
    # Admin commands
    app.add_handler(CommandHandler("stats", admin_stats))
    app.add_handler(CommandHandler("broadcast", admin_broadcast))
    app.add_handler(CommandHandler("addpremium", admin_add_premium))
    
    # Setup scheduler
    scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")
    scheduler.add_job(send_morning_messages, "cron", hour=7, minute=0, args=[app])
    scheduler.add_job(check_reminders, "interval", minutes=5, args=[app])
    scheduler.add_job(check_exam_reminders, "cron", hour=9, minute=0, args=[app])
    scheduler.start()
    
    # Connect to database on startup
    async def post_init(application):
        await db.connect()
        log.info("✅ Bot started!")
    
    app.post_init = post_init
    
    # Start bot
    if WEBHOOK_URL:
        # Use webhook
        app.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=TOKEN,
            webhook_url=f"{WEBHOOK_URL}/{TOKEN}"
        )
    else:
        # Use polling
        app.run_polling()

if __name__ == "__main__":
    main()
