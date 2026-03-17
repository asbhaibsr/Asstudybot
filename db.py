from motor.motor_asyncio import AsyncIOMotorClient
import os
import datetime
from bson import ObjectId
from typing import Optional, List, Dict
import logging

log = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.client = None
        self.db = None
        self.users = None
        self.questions = None
        self.notes = None
        self.reminders = None
        self.referrals = None
        self.feedback = None
    
    async def connect(self):
        """Connect to MongoDB"""
        mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
        self.client = AsyncIOMotorClient(mongo_url)
        self.db = self.client["IndiaStudyAI"]
        self.users = self.db["users"]
        self.questions = self.db["questions"]
        self.notes = self.db["notes"]
        self.reminders = self.db["reminders"]
        self.referrals = self.db["referrals"]
        self.feedback = self.db["feedback"]
        
        # Create indexes
        await self.users.create_index("user_id", unique=True)
        await self.questions.create_index([("user_id", 1), ("timestamp", -1)])
        await self.notes.create_index([("user_id", 1), ("timestamp", -1)])
        await self.reminders.create_index("remind_at")
        log.info("✅ Database connected")
    
    # ==================== USER MANAGEMENT ====================
    
    async def add_user(self, user_id: int, name: str, username: str = None, ref_by: int = None):
        """Add new user to database"""
        user = await self.users.find_one({"user_id": user_id})
        
        if not user:
            # New user
            user_data = {
                "user_id": user_id,
                "name": name,
                "username": username,
                "joined": datetime.datetime.now(),
                "last_active": datetime.datetime.now(),
                "points": 50,  # Joining bonus
                "streak": 0,
                "max_streak": 0,
                "total_questions": 0,
                "language": "hi",
                "premium": False,
                "premium_expiry": None,
                "class_type": None,
                "course": None,
                "goal": None,
                "exam_name": None,
                "exam_date": None,
                "notify_morning": True,
                "notify_exam": True,
                "ref_count": 0,
                "ref_earned": 0,
                "badges": ["🌱 Newbie"],
                "blocked": False
            }
            await self.users.insert_one(user_data)
            
            # Handle referral
            if ref_by and ref_by != user_id:
                await self.add_referral(ref_by, user_id)
    
    async def get_user(self, user_id: int) -> Optional[Dict]:
        """Get user by ID"""
        return await self.users.find_one({"user_id": user_id})
    
    async def update_profile(self, user_id: int, class_type: str, course: str, goal: str):
        """Update user profile"""
        await self.users.update_one(
            {"user_id": user_id},
            {"$set": {
                "class_type": class_type,
                "course": course,
                "goal": goal,
                "last_active": datetime.datetime.now()
            }}
        )
    
    async def update_language(self, user_id: int, language: str):
        """Update user language preference"""
        await self.users.update_one(
            {"user_id": user_id},
            {"$set": {"language": language}}
        )
    
    async def update_settings(self, user_id: int, **kwargs):
        """Update user settings"""
        await self.users.update_one(
            {"user_id": user_id},
            {"$set": kwargs}
        )
    
    async def is_blocked(self, user_id: int) -> bool:
        """Check if user is blocked"""
        user = await self.get_user(user_id)
        return user.get("blocked", False) if user else False
    
    async def block_user(self, user_id: int):
        """Block a user"""
        await self.users.update_one(
            {"user_id": user_id},
            {"$set": {"blocked": True}}
        )
    
    async def unblock_user(self, user_id: int):
        """Unblock a user"""
        await self.users.update_one(
            {"user_id": user_id},
            {"$set": {"blocked": False}}
        )
    
    # ==================== PREMIUM MANAGEMENT ====================
    
    async def is_premium(self, user_id: int) -> bool:
        """Check if user has premium"""
        user = await self.get_user(user_id)
        if not user or not user.get("premium"):
            return False
        
        # Check expiry
        if user.get("premium_expiry"):
            if user["premium_expiry"] < datetime.datetime.now():
                await self.remove_premium(user_id)
                return False
        
        return True
    
    async def set_premium(self, user_id: int, days: int = 30):
        """Set premium for user"""
        expiry = datetime.datetime.now() + datetime.timedelta(days=days)
        await self.users.update_one(
            {"user_id": user_id},
            {"$set": {
                "premium": True,
                "premium_expiry": expiry
            }}
        )
    
    async def remove_premium(self, user_id: int):
        """Remove premium from user"""
        await self.users.update_one(
            {"user_id": user_id},
            {"$set": {"premium": False, "premium_expiry": None}}
        )
    
    # ==================== POINTS & STREAK ====================
    
    async def add_points(self, user_id: int, points: int):
        """Add points to user"""
        await self.users.update_one(
            {"user_id": user_id},
            {"$inc": {"points": points}}
        )
    
    async def update_streak(self, user_id: int):
        """Update daily streak"""
        user = await self.get_user(user_id)
        if not user:
            return
        
        last_active = user.get("last_active")
        today = datetime.datetime.now().date()
        
        if last_active and last_active.date() == today - datetime.timedelta(days=1):
            # Consecutive day
            new_streak = user.get("streak", 0) + 1
            update = {
                "$set": {"streak": new_streak},
                "$inc": {"points": 10}  # Bonus for streak
            }
            
            if new_streak > user.get("max_streak", 0):
                update["$set"]["max_streak"] = new_streak
            
            await self.users.update_one({"user_id": user_id}, update)
            
        elif not last_active or last_active.date() < today:
            # New streak
            await self.users.update_one(
                {"user_id": user_id},
                {"$set": {"streak": 1}, "$inc": {"points": 5}}
            )
    
    async def check_and_award(self, user_id: int):
        """Check and award achievements"""
        user = await self.get_user(user_id)
        if not user:
            return
        
        points = user.get("points", 0)
        badges = user.get("badges", [])
        new_badges = []
        
        if points >= 100 and "💪 Bronze" not in badges:
            new_badges.append("💪 Bronze")
        if points >= 500 and "🥈 Silver" not in badges:
            new_badges.append("🥈 Silver")
        if points >= 1000 and "🥇 Gold" not in badges:
            new_badges.append("🥇 Gold")
        if points >= 5000 and "👑 Platinum" not in badges:
            new_badges.append("👑 Platinum")
        
        if new_badges:
            await self.users.update_one(
                {"user_id": user_id},
                {"$push": {"badges": {"$each": new_badges}}}
            )
    
    # ==================== USAGE TRACKING ====================
    
    async def inc_usage(self, user_id: int, type: str):
        """Increment usage count"""
        today = datetime.datetime.now().date().isoformat()
        field = f"usage.{type}.{today}"
        
        await self.users.update_one(
            {"user_id": user_id},
            {"$inc": {field: 1, "total_questions": 1}}
        )
    
    async def get_usage(self, user_id: int, type: str) -> int:
        """Get today's usage count"""
        user = await self.get_user(user_id)
        if not user:
            return 0
        
        today = datetime.datetime.now().date().isoformat()
        return user.get("usage", {}).get(type, {}).get(today, 0)
    
    async def inc_api_usage(self, user_id: int, api: str):
        """Increment API usage"""
        today = datetime.datetime.now().date().isoformat()
        field = f"api_usage.{api}.{today}"
        
        await self.users.update_one(
            {"user_id": user_id},
            {"$inc": {field: 1}}
        )
    
    async def get_api_usage(self, user_id: int) -> Dict:
        """Get today's API usage"""
        user = await self.get_user(user_id)
        if not user:
            return {}
        
        today = datetime.datetime.now().date().isoformat()
        return user.get("api_usage", {}).get(today, {})
    
    # ==================== QUESTIONS HISTORY ====================
    
    async def save_q(self, user_id: int, question: str, answer: str, api_used: str):
        """Save question-answer pair"""
        doc = {
            "user_id": user_id,
            "question": question[:200],
            "answer": answer[:1000],
            "api_used": api_used,
            "timestamp": datetime.datetime.now()
        }
        await self.questions.insert_one(doc)
        
        # Update last active
        await self.users.update_one(
            {"user_id": user_id},
            {"$set": {"last_active": datetime.datetime.now()}}
        )
        
        # Update streak
        await self.update_streak(user_id)
    
    async def get_chat_history(self, user_id: int, limit: int = 20) -> List:
        """Get user's chat history"""
        cursor = self.questions.find(
            {"user_id": user_id}
        ).sort("timestamp", -1).limit(limit)
        return await cursor.to_list(length=limit)
    
    async def delete_chat_item(self, user_id: int, item_id: str):
        """Delete a specific chat item"""
        try:
            await self.questions.delete_one({
                "_id": ObjectId(item_id),
                "user_id": user_id
            })
        except:
            pass
    
    async def delete_chat_history(self, user_id: int):
        """Delete all chat history for user"""
        await self.questions.delete_many({"user_id": user_id})
    
    # ==================== NOTES ====================
    
    async def save_note(self, user_id: int, title: str, content: str, source: str = "manual"):
        """Save a note"""
        doc = {
            "user_id": user_id,
            "title": title[:100],
            "content": content[:2000],
            "source": source,
            "timestamp": datetime.datetime.now()
        }
        result = await self.notes.insert_one(doc)
        return str(result.inserted_id)
    
    async def get_user_notes(self, user_id: int) -> List:
        """Get all notes for user"""
        cursor = self.notes.find(
            {"user_id": user_id}
        ).sort("timestamp", -1).limit(50)
        return await cursor.to_list(length=50)
    
    async def get_note(self, user_id: int, note_id: str) -> Optional[Dict]:
        """Get a specific note"""
        try:
            return await self.notes.find_one({
                "_id": ObjectId(note_id),
                "user_id": user_id
            })
        except:
            return None
    
    async def delete_note(self, user_id: int, note_id: str):
        """Delete a note"""
        try:
            await self.notes.delete_one({
                "_id": ObjectId(note_id),
                "user_id": user_id
            })
        except:
            pass
    
    async def delete_all_notes(self, user_id: int):
        """Delete all notes for user"""
        await self.notes.delete_many({"user_id": user_id})
    
    # ==================== REMINDERS ====================
    
    async def add_reminder(self, user_id: int, text: str, remind_at: datetime.datetime):
        """Add a reminder"""
        doc = {
            "user_id": user_id,
            "text": text[:100],
            "remind_at": remind_at,
            "created": datetime.datetime.now(),
            "sent": False
        }
        await self.reminders.insert_one(doc)
    
    async def get_user_reminders(self, user_id: int) -> List:
        """Get all reminders for user"""
        cursor = self.reminders.find({
            "user_id": user_id,
            "sent": False
        }).sort("remind_at", 1)
        return await cursor.to_list(length=20)
    
    async def get_due_reminders(self) -> List:
        """Get all due reminders"""
        cursor = self.reminders.find({
            "remind_at": {"$lte": datetime.datetime.now()},
            "sent": False
        })
        return await cursor.to_list(length=100)
    
    async def mark_reminder_sent(self, reminder_id: str):
        """Mark reminder as sent"""
        try:
            await self.reminders.update_one(
                {"_id": ObjectId(reminder_id)},
                {"$set": {"sent": True}}
            )
        except:
            pass
    
    # ==================== REFERRALS ====================
    
    async def add_referral(self, referrer_id: int, referred_id: int):
        """Add a referral"""
        # Check if already referred
        existing = await self.referrals.find_one({
            "referrer_id": referrer_id,
            "referred_id": referred_id
        })
        if existing:
            return
        
        # Add referral record
        doc = {
            "referrer_id": referrer_id,
            "referred_id": referred_id,
            "timestamp": datetime.datetime.now(),
            "rewarded": False
        }
        await self.referrals.insert_one(doc)
        
        # Update referrer count
        await self.users.update_one(
            {"user_id": referrer_id},
            {"$inc": {"ref_count": 1, "points": 100}}
        )
        
        # Check for premium reward (20 referrals = 1 week premium)
        referrer = await self.get_user(referrer_id)
        if referrer and referrer.get("ref_count", 0) >= 20:
            # Award 1 week premium
            await self.set_premium(referrer_id, 7)
            # Reset count after reward
            await self.users.update_one(
                {"user_id": referrer_id},
                {"$set": {"ref_count": 0}}
            )
    
    async def get_referral_count(self, user_id: int) -> int:
        """Get user's referral count"""
        user = await self.get_user(user_id)
        return user.get("ref_count", 0) if user else 0
    
    # ==================== FEEDBACK ====================
    
    async def save_feedback(self, user_id: int, rating: int, comment: str):
        """Save user feedback"""
        doc = {
            "user_id": user_id,
            "rating": rating,
            "comment": comment[:500],
            "timestamp": datetime.datetime.now()
        }
        await self.feedback.insert_one(doc)
    
    # ==================== EXAMS ====================
    
    async def set_exam(self, user_id: int, exam_name: str, exam_date: str):
        """Set user's exam date"""
        try:
            date_obj = datetime.datetime.strptime(exam_date, "%Y-%m-%d")
            await self.users.update_one(
                {"user_id": user_id},
                {"$set": {
                    "exam_name": exam_name,
                    "exam_date": date_obj
                }}
            )
        except Exception as e:
            log.error(f"Set exam error: {e}")
    
    async def get_exam_reminders(self) -> List:
        """Get users with exams approaching"""
        today = datetime.datetime.now()
        reminders = []
        
        cursor = self.users.find({
            "exam_date": {"$gte": today},
            "notify_exam": True
        })
        
        async for user in cursor:
            days_left = (user["exam_date"] - today).days
            if days_left in [1, 7, 30]:  # Remind on these days
                reminders.append({
                    "user_id": user["user_id"],
                    "exam_name": user.get("exam_name", "Exam"),
                    "days_left": days_left
                })
        
        return reminders
    
    # ==================== STUDY PLAN ====================
    
    async def save_study_plan(self, user_id: int, plan: str, exam_date: str, subjects: str):
        """Save study plan"""
        await self.users.update_one(
            {"user_id": user_id},
            {"$set": {
                "study_plan": {
                    "plan": plan,
                    "exam_date": exam_date,
                    "subjects": subjects,
                    "created": datetime.datetime.now()
                }
            }}
        )
    
    async def get_study_plan(self, user_id: int) -> Optional[Dict]:
        """Get user's study plan"""
        user = await self.get_user(user_id)
        return user.get("study_plan") if user else None
    
    # ==================== CACHE ====================
    
    async def set_cache(self, key: str, value: str, hours: int = 24):
        """Set cache value"""
        expiry = datetime.datetime.now() + datetime.timedelta(hours=hours)
        doc = {
            "key": key,
            "value": value,
            "expiry": expiry
        }
        await self.db.cache.update_one(
            {"key": key},
            {"$set": doc},
            upsert=True
        )
    
    async def get_cache(self, key: str) -> Optional[str]:
        """Get cache value"""
        doc = await self.db.cache.find_one({"key": key})
        if doc and doc.get("expiry") > datetime.datetime.now():
            return doc.get("value")
        return None
    
    async def del_cache(self, key: str):
        """Delete cache"""
        await self.db.cache.delete_one({"key": key})
    
    async def del_cache_prefix(self, prefix: str):
        """Delete all cache with prefix"""
        await self.db.cache.delete_many({"key": {"$regex": f"^{prefix}"}})
    
    # ==================== LEADERBOARD ====================
    
    async def get_leaderboard(self, limit: int = 10) -> List:
        """Get top users by points"""
        cursor = self.users.find(
            {"blocked": False}
        ).sort("points", -1).limit(limit)
        return await cursor.to_list(length=limit)
    
    async def get_rank(self, user_id: int) -> int:
        """Get user's rank"""
        user = await self.get_user(user_id)
        if not user:
            return 0
        
        points = user.get("points", 0)
        count = await self.users.count_documents({
            "blocked": False,
            "points": {"$gt": points}
        })
        return count + 1
    
    # ==================== DAILY CHALLENGE ====================
    
    async def challenge_done_today(self, user_id: int) -> bool:
        """Check if user did daily challenge today"""
        user = await self.get_user(user_id)
        if not user:
            return False
        
        last_challenge = user.get("last_challenge")
        if last_challenge:
            return last_challenge.date() == datetime.datetime.now().date()
        return False
    
    async def mark_challenge_done(self, user_id: int):
        """Mark daily challenge as done"""
        await self.users.update_one(
            {"user_id": user_id},
            {"$set": {"last_challenge": datetime.datetime.now()}}
        )
    
    # ==================== STATS ====================
    
    async def stats(self) -> Dict:
        """Get bot statistics"""
        total = await self.users.count_documents({})
        today_start = datetime.datetime.combine(
            datetime.datetime.now().date(),
            datetime.time.min
        )
        
        active_today = await self.users.count_documents({
            "last_active": {"$gte": today_start}
        })
        
        new_today = await self.users.count_documents({
            "joined": {"$gte": today_start}
        })
        
        premium = await self.users.count_documents({"premium": True})
        blocked = await self.users.count_documents({"blocked": True})
        
        questions = await self.questions.count_documents({})
        notes_total = await self.notes.count_documents({})
        
        return {
            "total": total,
            "active_today": active_today,
            "new_today": new_today,
            "premium": premium,
            "blocked": blocked,
            "questions": questions,
            "notes_total": notes_total
        }
    
    # ==================== MORNING NOTIFICATIONS ====================
    
    async def morning_notify_users(self) -> List:
        """Get users who want morning notifications"""
        cursor = self.users.find({
            "notify_morning": True,
            "blocked": False
        })
        return await cursor.to_list(length=1000)

# Global database instance
db = Database()
