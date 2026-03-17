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
import requests

from ai import (
    ask_ai, generate_pdf, image_to_text, fetch_updates,
    generate_mindmap_text, generate_question_paper,
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

# Check if token exists
if not TOKEN:
    log.error("❌ BOT_TOKEN environment variable not set!")
    exit(1)

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
        "message": "Bot is running!",
        "db_connected": db.is_connected() if hasattr(db, 'is_connected') else False
    })

@flask_app.route('/health')
def health():
    return jsonify({
        "status": "healthy",
        "db_connected": db.is_connected() if hasattr(db, 'is_connected') else False
    }), 200

@flask_app.route('/app')
@flask_app.route('/app/')
def serve_app():
    return send_from_directory('app', 'index.html')

@flask_app.route('/app/<path:path>')
def serve_app_files(path):
    return send_from_directory('app', path)

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
    
    log.info(f"📨 /start from {user.id} - {user.first_name}")
    
    # Check for referral
    ref_by = None
    if context.args and context.args[0].startswith("ref"):
        try:
            ref_by = int(context.args[0][3:])
            log.info(f"Referral from: {ref_by}")
        except:
            pass
    
    # Add user to database
    try:
        await db.add_user(
            user_id=user.id,
            name=user.first_name,
            username=user.username,
            ref_by=ref_by
        )
    except Exception as e:
        log.error(f"Error adding user: {e}")
    
    # Check if user has profile
    db_user = await db.get_user(user.id)
    
    if db_user and db_user.get("class_type"):
        # User already has profile, show menu
        premium = await db.is_premium(user.id) if hasattr(db, 'is_premium') else False
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
    try:
        await db.update_profile(
            user_id=query.from_user.id,
            class_type=context.user_data["class_type"],
            course=context.user_data["subject"],
            goal=goal
        )
        
        # Give joining bonus
        await db.add_points(query.from_user.id, 50)
    except Exception as e:
        log.error(f"Error saving profile: {e}")
    
    await query.edit_message_text(
        f"🎉 Profile Complete!\n\n"
        f"📚 Class: {context.user_data['class_type']}\n"
        f"📖 Subject: {context.user_data['subject']}\n"
        f"🎯 Goal: {goal}\n\n"
        f"✨ You got 50 bonus points!\n\n"
        f"What would you like to do now?",
        reply_markup=get_main_keyboard(query.from_user.id, False)
    )
    return ConversationHandler.END

# ==================== AI TUTOR ====================

async def ai_tutor(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start AI tutor mode"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    premium = await db.is_premium(user_id) if hasattr(db, 'is_premium') else False
    
    await query.edit_message_text(
        "🤖 *AI Study Tutor Activated!*\n\n"
        "Ask me anything about your studies. I'll explain like a story so you never forget!\n\n"
        "_Type your question below or send an image_",
        parse_mode="Markdown",
        reply_markup=get_back_button()
    )
    context.user_data["mode"] = "ai_tutor"
    return AI_TUTOR

# ==================== QUICK QUESTION ====================

async def quick_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Start quick question mode"""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "❓ *Quick Question Mode*\n\n"
        "Type your question and I'll give a quick answer!",
        parse_mode="Markdown",
        reply_markup=get_back_button()
    )
    context.user_data["mode"] = "quick"
    return QUICK_QUESTION

# ==================== HANDLE TEXT MESSAGES ====================

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle all text messages"""
    user_id = update.effective_user.id
    text = update.message.text
    
    log.info(f"📝 Message from {user_id}: {text[:50]}...")
    
    # Send typing indicator
    await context.bot.send_chat_action(chat_id=user_id, action="typing")
    
    mode = context.user_data.get("mode", "quick")
    
    # Handle feedback mode
    if mode == "wait_feedback":
        try:
            await db.save_feedback(user_id, 5, text)
        except:
            pass
        await update.message.reply_text(
            "✅ Thank you for your feedback!",
            reply_markup=get_main_keyboard(user_id, False)
        )
        context.user_data["mode"] = None
        return ConversationHandler.END
    
    # Get answer from AI
    wait_msg = await update.message.reply_text("🤔 Thinking...")
    
    try:
        # Get user data for context
        user_data = await db.get_user(user_id)
        
        # Get answer
        answer, provider = await ask_ai(text, user_data, mode)
        
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
        
        # Try to save to database (don't fail if it doesn't work)
        try:
            await db.save_q(user_id, text, answer, provider)
            await db.inc_usage(user_id, "ai" if mode == "ai_tutor" else "q")
        except Exception as e:
            log.debug(f"Could not save to DB: {e}")
        
    except Exception as e:
        log.error(f"AI Error: {e}")
        await wait_msg.delete()
        await update.message.reply_text(
            "❌ Sorry, I encountered an error. Please try again.",
            reply_markup=get_back_button()
        )
    
    return mode

# ==================== HANDLE PHOTOS ====================

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle photo messages for OCR"""
    user_id = update.effective_user.id
    
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
    
    # Get news from AI
    news = await ask_ai_simple("Latest India news headlines for today. 8 items with brief description.", mode="quick")
    
    keyboard = [
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
    notes = await db.get_user_notes(user_id) if hasattr(db, 'get_user_notes') else []
    
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
    
    note = await db.get_note(user_id, note_id) if hasattr(db, 'get_note') else None
    if not note:
        await query.edit_message_text("❌ Note not found.", reply_markup=get_back_button())
        return
    
    content = note.get("content", "")[:500]
    
    keyboard = [
        [InlineKeyboardButton("🗑️ Delete", callback_data=f"del_note_{note_id}")],
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
    
    if hasattr(db, 'delete_note'):
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
    ref_count = await db.get_referral_count(user_id) if hasattr(db, 'get_referral_count') else 0
    
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
    
    premium = await db.is_premium(user_id) if hasattr(db, 'is_premium') else False
    
    text = (
        f"👤 *Your Profile*\n\n"
        f"📚 Class: {user.get('class_type', 'Not set')}\n"
        f"📖 Subject: {user.get('course', 'Not set')}\n"
        f"🎯 Goal: {user.get('goal', 'Not set')}\n\n"
        f"⭐ Points: *{user.get('points', 0)}*\n"
        f"🔥 Streak: *{user.get('streak', 0)} days*\n"
        f"❓ Total Questions: *{user.get('total_questions', 0)}*\n"
        f"👥 Referrals: *{user.get('ref_count', 0)}*\n\n"
        f"💎 Premium: {'✅ Active' if premium else '❌ Not Active'}"
    )
    
    keyboard = [
        [InlineKeyboardButton("📝 My Notes", callback_data="notes")],
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
    
    lang = user.get("language", "hi") if user else "hi"
    lang_text = "🇮🇳 Hindi" if lang == "hi" else "🇬🇧 English" if lang == "en" else "🔀 Hinglish"
    
    keyboard = [
        [InlineKeyboardButton(f"🌐 Language: {lang_text}", callback_data="change_lang")],
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
    current = user.get("language", "hi") if user else "hi"
    
    next_lang = "en" if current == "hi" else "mix" if current == "en" else "hi"
    lang_names = {"hi": "🇮🇳 Hindi", "en": "🇬🇧 English", "mix": "🔀 Hinglish"}
    
    if hasattr(db, 'update_language'):
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
    premium = await db.is_premium(user_id) if hasattr(db, 'is_premium') else False
    
    if premium:
        user = await db.get_user(user_id)
        expiry = user.get("premium_expiry", "")
        if expiry:
            try:
                expiry = expiry.strftime("%d %b %Y")
            except:
                expiry = "Active"
        else:
            expiry = "Active"
        
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
            "✅ Chat history\n"
            "✅ Advanced study tools\n\n"
            "💰 Price: ₹199/month\n"
            "🎁 FREE: 20 referrals = 1 week premium\n\n"
            "UPI ID: `arsadsaifi8272@ibl`\n\n"
            "Send screenshot after payment.",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
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
    await query.answer()
    
    data = query.data
    user_id = query.from_user.id
    
    # Handle menu navigation
    if data == "menu":
        premium = await db.is_premium(user_id) if hasattr(db, 'is_premium') else False
        await query.edit_message_text(
            "🏠 *Main Menu*\n\nWhat would you like to do?",
            parse_mode="Markdown",
            reply_markup=get_main_keyboard(user_id, premium)
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
        last_answer = context.user_data.get("last_answer", "")
        last_question = context.user_data.get("last_question", "AI Answer")
        
        if last_answer and hasattr(db, 'save_note'):
            await db.save_note(user_id, last_question[:50], last_answer, "AI")
            await query.answer("✅ Note saved!", show_alert=True)
        else:
            await query.answer("❌ No answer to save", show_alert=True)
    
    elif data == "download_pdf":
        # Download last answer as PDF
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
        ref_link = f"https://t.me/IndiaStudyAI_Bot?start=ref{user_id}"
        await query.answer(f"Link copied: {ref_link}", show_alert=True)
    
    elif data == "mindmap":
        await query.edit_message_text(
            "🗺️ *Mind Map Generator*\n\n"
            "Enter a topic to generate a mind map:",
            parse_mode="Markdown",
            reply_markup=get_back_button()
        )
        context.user_data["mode"] = "wait_mindmap"
        return WAIT_MINDMAP_TOPIC
    
    elif data == "qpaper":
        await query.edit_message_text(
            "📝 *Question Paper Generator*\n\n"
            "Enter subject name (e.g., Mathematics, Science, Physics):",
            parse_mode="Markdown",
            reply_markup=get_back_button()
        )
        context.user_data["mode"] = "wait_qpaper"
        return WAIT_QUESTION_PAPER
    
    elif data == "vocab":
        await query.edit_message_text(
            "📖 *Vocabulary Builder*\n\n"
            "Enter a topic (e.g., Environment, Technology, Business):",
            parse_mode="Markdown",
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
            parse_mode="Markdown",
            reply_markup=get_back_button()
        )
        context.user_data["mode"] = "wait_planner"
        return WAIT_STUDY_PLAN
    
    elif data == "ocr":
        await query.edit_message_text(
            "📷 *Image to Text*\n\n"
            "Send me any image and I'll extract text from it!",
            parse_mode="Markdown",
            reply_markup=get_back_button()
        )
    
    elif data == "help":
        await query.edit_message_text(
            "❓ *Help*\n\n"
            "• 🤖 AI Tutor: Ask any study question\n"
            "• 📢 Updates: Latest sarkari news\n"
            "• 📝 Notes: Save your study notes\n"
            "• 📷 OCR: Extract text from images\n"
            "• 🗺️ Mind Map: Create visual maps\n\n"
            "More features coming soon!",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 Menu", callback_data="menu")]
            ])
        )
    
    elif data == "edit_profile":
        # Reset profile
        await query.edit_message_text(
            "📝 *Edit Profile*\n\n"
            "Select your class:",
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📚 Class 1-5", callback_data="class_1_5"),
                 InlineKeyboardButton("📖 Class 6-8", callback_data="class_6_8")],
                [InlineKeyboardButton("🎓 Class 9-10", callback_data="class_9_10"),
                 InlineKeyboardButton("🏫 Class 11-12", callback_data="class_11_12")],
                [InlineKeyboardButton("🎓 College", callback_data="class_college"),
                 InlineKeyboardButton("👨‍💼 Job Prep", callback_data="class_job")],
                [InlineKeyboardButton("🔙 Cancel", callback_data="menu")]
            ])
        )
        return SELECT_CLASS

# ==================== SPECIAL MODE HANDLERS ====================

async def handle_mindmap(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle mind map generation"""
    topic = update.message.text
    user_id = update.effective_user.id
    
    wait_msg = await update.message.reply_text("🗺️ Generating mind map...")
    
    try:
        # Generate text mind map
        mindmap_text = await generate_mindmap_text(topic)
        
        await wait_msg.delete()
        
        await update.message.reply_text(
            mindmap_text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📝 Save as Note", callback_data="save_note"),
                 InlineKeyboardButton("🔙 Menu", callback_data="menu")]
            ])
        )
        
        context.user_data["last_answer"] = mindmap_text
        context.user_data["last_question"] = f"Mind Map: {topic}"
        
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
    
    try:
        # Get user's class
        user = await db.get_user(user_id)
        class_name = user.get("class_type", "Class 10") if user else "Class 10"
        
        # Generate paper
        paper = await generate_question_paper(subject, class_name, "Medium")
        
        await wait_msg.delete()
        
        await update.message.reply_text(
            paper,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📝 Save as Note", callback_data="save_note"),
                 InlineKeyboardButton("🔙 Menu", callback_data="menu")]
            ])
        )
        
        context.user_data["last_answer"] = paper
        context.user_data["last_question"] = f"Question Paper: {subject}"
        
    except Exception as e:
        log.error(f"Question paper error: {e}")
        await wait_msg.delete()
        await update.message.reply_text(
            "❌ Failed to generate question paper. Please try again.",
            reply_markup=get_back_button()
        )
    
    context.user_data["mode"] = None
    return ConversationHandler.END

async def handle_vocab(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle vocabulary generation"""
    topic = update.message.text
    user_id = update.effective_user.id
    
    wait_msg = await update.message.reply_text("📖 Building vocabulary...")
    
    try:
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
        context.user_data["last_question"] = f"Vocabulary: {topic}"
        
    except Exception as e:
        log.error(f"Vocabulary error: {e}")
        await wait_msg.delete()
        await update.message.reply_text(
            "❌ Failed to build vocabulary. Please try again.",
            reply_markup=get_back_button()
        )
    
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
        
        await update.message.reply_text(
            plan,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📝 Save as Note", callback_data="save_note"),
                 InlineKeyboardButton("🔙 Menu", callback_data="menu")]
            ])
        )
        
        context.user_data["last_answer"] = plan
        context.user_data["last_question"] = f"Study Plan: {subjects}"
        
    except Exception as e:
        log.error(f"Planner error: {e}")
        await update.message.reply_text(
            "❌ Failed to create plan. Please check format.",
            reply_markup=get_back_button()
        )
    
    context.user_data["mode"] = None
    return ConversationHandler.END

# ==================== SCHEDULED JOBS ====================

async def check_reminders(app):
    """Check and send due reminders"""
    if not hasattr(db, 'get_due_reminders'):
        return
    
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

# ==================== ADMIN COMMANDS ====================

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin: Show bot statistics"""
    if update.effective_user.id != OWNER_ID:
        await update.message.reply_text("❌ Unauthorized")
        return
    
    stats = await db.stats() if hasattr(db, 'stats') else {"total": 0, "active_today": 0}
    
    text = (
        f"📊 *Bot Statistics*\n\n"
        f"👥 Total Users: *{stats.get('total', 0)}*\n"
        f"✅ Active Today: *{stats.get('active_today', 0)}*\n"
        f"💎 Premium: *{stats.get('premium', 0)}*\n"
        f"📝 Notes: *{stats.get('notes_total', 0)}*"
    )
    
    await update.message.reply_text(text, parse_mode="Markdown")

# ==================== MAIN FUNCTION ====================

async def post_init(application):
    """Initialize after bot starts"""
    # Connect to database
    await db.connect()
    
    # Log bot info
    bot_info = await application.bot.get_me()
    log.info(f"✅ Bot started: @{bot_info.username}")
    log.info(f"✅ Database connected: {db.is_connected() if hasattr(db, 'is_connected') else False}")
    log.info(f"✅ Mini App URL: {MINI_APP_URL}/app")

def main():
    """Start the bot"""
    log.info("🚀 Starting IndiaStudyAI Bot...")
    
    # Start Flask in separate thread
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    log.info(f"✅ Flask server started on port {PORT}")
    
    # CRITICAL FIX: Stop any existing bot instances
    try:
        log.info("🔄 Cleaning up previous bot instances...")
        requests.post(
            f"https://api.telegram.org/bot{TOKEN}/deleteWebhook",
            json={"drop_pending_updates": True}
        )
        log.info("✅ Webhook deleted, pending updates dropped")
    except Exception as e:
        log.warning(f"Could not delete webhook: {e}")
    
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
    
    # Setup scheduler
    scheduler = AsyncIOScheduler(timezone="Asia/Kolkata")
    scheduler.add_job(check_reminders, "interval", minutes=5, args=[app])
    scheduler.start()
    
    # Set post-init
    app.post_init = post_init
    
    # Start bot with proper settings to avoid conflict
    log.info("📡 Starting bot in polling mode...")
    app.run_polling(
        drop_pending_updates=True,  # CRITICAL: This fixes the conflict error
        allowed_updates=Update.ALL_TYPES
    )

if __name__ == "__main__":
    main()
