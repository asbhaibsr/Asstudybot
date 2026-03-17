from motor.motor_asyncio import AsyncIOMotorClient
import os
import datetime
from bson import ObjectId
from typing import Optional, List, Dict, Any
import logging
import asyncio

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
        self.cache = None
        self._connected = False
    
    async def connect(self):
        """Connect to MongoDB with proper error handling"""
        mongo_url = os.environ.get("MONGO_URL", "")
        
        # Check if MongoDB URL is provided
        if not mongo_url:
            log.warning("⚠️ MONGO_URL not set - running without database")
            self._connected = False
            return False
        
        # Don't use localhost in production
        if "localhost" in mongo_url or "127.0.0.1" in mongo_url:
            log.error("❌ Cannot use localhost MongoDB in cloud! Please use MongoDB Atlas")
            log.info("Get free MongoDB Atlas: https://www.mongodb.com/cloud/atlas")
            self._connected = False
            return False
        
        # Try to connect with timeout
        try:
            log.info("🔄 Connecting to MongoDB...")
            self.client = AsyncIOMotorClient(
                mongo_url,
                serverSelectionTimeoutMS=5000,
                connectTimeoutMS=5000
            )
            
            # Ping database to verify connection
            await self.client.admin.command('ping')
            
            self.db = self.client["IndiaStudyAI"]
            self.users = self.db["users"]
            self.questions = self.db["questions"]
            self.notes = self.db["notes"]
            self.reminders = self.db["reminders"]
            self.referrals = self.db["referrals"]
            self.feedback = self.db["feedback"]
            self.cache = self.db["cache"]
            
            # Create indexes (don't fail if they exist)
            try:
                await self.users.create_index("user_id", unique=True)
                await self.questions.create_index([("user_id", 1), ("timestamp", -1)])
                await self.notes.create_index([("user_id", 1), ("timestamp", -1)])
                await self.reminders.create_index("remind_at")
                await self.cache.create_index("key", unique=True)
            except Exception as e:
                log.debug(f"Index creation (might already exist): {e}")
            
            self._connected = True
            log.info("✅ Database connected successfully")
            return True
            
        except Exception as e:
            log.error(f"❌ Database connection failed: {e}")
            log.info("⚠️ Continuing without database - some features will be limited")
            self._connected = False
            return False
    
    def is_connected(self) -> bool:
        """Check if database is connected"""
        return self._connected
    
    # ==================== USER MANAGEMENT (with fallback) ====================
    
    async def add_user(self, user_id: int, name: str, username: str = None, ref_by: int = None):
        """Add new user to database with fallback"""
        if not self._connected:
            log.debug(f"DB not connected - skipping add_user for {user_id}")
            return True
        
        try:
            user = await self.users.find_one({"user_id": user_id})
            
            if not user:
                # New user
                user_data = {
                    "user_id": user_id,
                    "name": name,
                    "username": username,
                    "joined": datetime.datetime.now(),
                    "last_active": datetime.datetime.now(),
                    "points": 50,
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
                    "blocked": False,
                    "usage": {},
                    "api_usage": {}
                }
                await self.users.insert_one(user_data)
                log.info(f"✅ New user added: {user_id} - {name}")
                
                # Handle referral
                if ref_by and ref_by != user_id:
                    await self.add_referral(ref_by, user_id)
            return True
        except Exception as e:
            log.error(f"Error adding user: {e}")
            return False
    
    async def get_user(self, user_id: int) -> Optional[Dict]:
        """Get user by ID with fallback"""
        if not self._connected:
            # Return minimal user data
            return {
                "user_id": user_id,
                "name": "User",
                "language": "hi",
                "points": 0,
                "premium": False,
                "class_type": None,
                "course": None,
                "goal": None
            }
        
        try:
            return await self.users.find_one({"user_id": user_id})
        except Exception as e:
            log.error(f"Error getting user: {e}")
            return {
                "user_id": user_id,
                "name": "User",
                "language": "hi",
                "points": 0,
                "premium": False
            }
    
    async def update_profile(self, user_id: int, class_type: str, course: str, goal: str):
        """Update user profile"""
        if not self._connected:
            return True
        
        try:
            await self.users.update_one(
                {"user_id": user_id},
                {"$set": {
                    "class_type": class_type,
                    "course": course,
                    "goal": goal,
                    "last_active": datetime.datetime.now()
                }}
            )
            return True
        except Exception as e:
            log.error(f"Error updating profile: {e}")
            return False
    
    async def update_language(self, user_id: int, language: str):
        """Update user language preference"""
        if not self._connected:
            return True
        
        try:
            await self.users.update_one(
                {"user_id": user_id},
                {"$set": {"language": language}}
            )
            return True
        except Exception as e:
            log.error(f"Error updating language: {e}")
            return False
    
    async def update_settings(self, user_id: int, **kwargs):
        """Update user settings"""
        if not self._connected:
            return True
        
        try:
            await self.users.update_one(
                {"user_id": user_id},
                {"$set": kwargs}
            )
            return True
        except Exception as e:
            log.error(f"Error updating settings: {e}")
            return False
    
    async def is_blocked(self, user_id: int) -> bool:
        """Check if user is blocked"""
        if not self._connected:
            return False
        
        try:
            user = await self.get_user(user_id)
            return user.get("blocked", False) if user else False
        except:
            return False
    
    async def block_user(self, user_id: int):
        """Block a user"""
        if not self._connected:
            return True
        
        try:
            await self.users.update_one(
                {"user_id": user_id},
                {"$set": {"blocked": True}}
            )
            return True
        except Exception as e:
            log.error(f"Error blocking user: {e}")
            return False
    
    async def unblock_user(self, user_id: int):
        """Unblock a user"""
        if not self._connected:
            return True
        
        try:
            await self.users.update_one(
                {"user_id": user_id},
                {"$set": {"blocked": False}}
            )
            return True
        except Exception as e:
            log.error(f"Error unblocking user: {e}")
            return False
    
    # ==================== PREMIUM MANAGEMENT ====================
    
    async def is_premium(self, user_id: int) -> bool:
        """Check if user has premium"""
        if not self._connected:
            return False
        
        try:
            user = await self.get_user(user_id)
            if not user or not user.get("premium"):
                return False
            
            # Check expiry
            if user.get("premium_expiry"):
                if user["premium_expiry"] < datetime.datetime.now():
                    await self.remove_premium(user_id)
                    return False
            
            return True
        except:
            return False
    
    async def set_premium(self, user_id: int, days: int = 30):
        """Set premium for user"""
        if not self._connected:
            return False
        
        try:
            expiry = datetime.datetime.now() + datetime.timedelta(days=days)
            await self.users.update_one(
                {"user_id": user_id},
                {"$set": {
                    "premium": True,
                    "premium_expiry": expiry
                }}
            )
            return True
        except Exception as e:
            log.error(f"Error setting premium: {e}")
            return False
    
    async def remove_premium(self, user_id: int):
        """Remove premium from user"""
        if not self._connected:
            return True
        
        try:
            await self.users.update_one(
                {"user_id": user_id},
                {"$set": {"premium": False, "premium_expiry": None}}
            )
            return True
        except Exception as e:
            log.error(f"Error removing premium: {e}")
            return False
    
    # ==================== POINTS & STREAK ====================
    
    async def add_points(self, user_id: int, points: int):
        """Add points to user"""
        if not self._connected:
            return True
        
        try:
            await self.users.update_one(
                {"user_id": user_id},
                {"$inc": {"points": points}}
            )
            return True
        except Exception as e:
            log.error(f"Error adding points: {e}")
            return False
    
    async def update_streak(self, user_id: int):
        """Update daily streak"""
        if not self._connected:
            return True
        
        try:
            user = await self.get_user(user_id)
            if not user:
                return False
            
            last_active = user.get("last_active")
            today = datetime.datetime.now().date()
            
            if last_active and last_active.date() == today - datetime.timedelta(days=1):
                # Consecutive day
                new_streak = user.get("streak", 0) + 1
                update = {
                    "$set": {"streak": new_streak, "last_active": datetime.datetime.now()},
                    "$inc": {"points": 10}
                }
                
                if new_streak > user.get("max_streak", 0):
                    update["$set"]["max_streak"] = new_streak
                
                await self.users.update_one({"user_id": user_id}, update)
                
            elif not last_active or last_active.date() < today:
                # New streak
                await self.users.update_one(
                    {"user_id": user_id},
                    {"$set": {"streak": 1, "last_active": datetime.datetime.now()},
                     "$inc": {"points": 5}}
                )
            return True
        except Exception as e:
            log.error(f"Error updating streak: {e}")
            return False
    
    async def check_and_award(self, user_id: int):
        """Check and award achievements"""
        if not self._connected:
            return True
        
        try:
            user = await self.get_user(user_id)
            if not user:
                return False
            
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
            return True
        except Exception as e:
            log.error(f"Error checking awards: {e}")
            return False
    
    # ==================== USAGE TRACKING ====================
    
    async def inc_usage(self, user_id: int, type: str):
        """Increment usage count"""
        if not self._connected:
            return True
        
        try:
            today = datetime.datetime.now().date().isoformat()
            field = f"usage.{type}.{today}"
            
            await self.users.update_one(
                {"user_id": user_id},
                {"$inc": {field: 1, "total_questions": 1}}
            )
            return True
        except Exception as e:
            log.error(f"Error incrementing usage: {e}")
            return False
    
    async def get_usage(self, user_id: int, type: str) -> int:
        """Get today's usage count"""
        if not self._connected:
            return 0
        
        try:
            user = await self.get_user(user_id)
            if not user:
                return 0
            
            today = datetime.datetime.now().date().isoformat()
            return user.get("usage", {}).get(type, {}).get(today, 0)
        except:
            return 0
    
    async def inc_api_usage(self, user_id: int, api: str):
        """Increment API usage"""
        if not self._connected:
            return True
        
        try:
            today = datetime.datetime.now().date().isoformat()
            field = f"api_usage.{today}.{api}"
            
            await self.users.update_one(
                {"user_id": user_id},
                {"$inc": {field: 1}}
            )
            return True
        except Exception as e:
            log.error(f"Error incrementing API usage: {e}")
            return False
    
    async def get_api_usage(self, user_id: int) -> Dict:
        """Get today's API usage"""
        if not self._connected:
            return {}
        
        try:
            user = await self.get_user(user_id)
            if not user:
                return {}
            
            today = datetime.datetime.now().date().isoformat()
            return user.get("api_usage", {}).get(today, {})
        except:
            return {}
    
    # ==================== QUESTIONS HISTORY ====================
    
    async def save_q(self, user_id: int, question: str, answer: str, api_used: str):
        """Save question-answer pair"""
        if not self._connected:
            return True
        
        try:
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
            return True
        except Exception as e:
            log.error(f"Error saving question: {e}")
            return False
    
    async def get_chat_history(self, user_id: int, limit: int = 20) -> List:
        """Get user's chat history"""
        if not self._connected:
            return []
        
        try:
            cursor = self.questions.find(
                {"user_id": user_id}
            ).sort("timestamp", -1).limit(limit)
            return await cursor.to_list(length=limit)
        except Exception as e:
            log.error(f"Error getting chat history: {e}")
            return []
    
    async def delete_chat_item(self, user_id: int, item_id: str):
        """Delete a specific chat item"""
        if not self._connected:
            return True
        
        try:
            await self.questions.delete_one({
                "_id": ObjectId(item_id),
                "user_id": user_id
            })
            return True
        except Exception as e:
            log.error(f"Error deleting chat item: {e}")
            return False
    
    async def delete_chat_history(self, user_id: int):
        """Delete all chat history for user"""
        if not self._connected:
            return True
        
        try:
            await self.questions.delete_many({"user_id": user_id})
            return True
        except Exception as e:
            log.error(f"Error deleting chat history: {e}")
            return False
    
    # ==================== NOTES ====================
    
    async def save_note(self, user_id: int, title: str, content: str, source: str = "manual") -> str:
        """Save a note"""
        if not self._connected:
            return ""
        
        try:
            doc = {
                "user_id": user_id,
                "title": title[:100],
                "content": content[:2000],
                "source": source,
                "timestamp": datetime.datetime.now()
            }
            result = await self.notes.insert_one(doc)
            return str(result.inserted_id)
        except Exception as e:
            log.error(f"Error saving note: {e}")
            return ""
    
    async def get_user_notes(self, user_id: int) -> List:
        """Get all notes for user"""
        if not self._connected:
            return []
        
        try:
            cursor = self.notes.find(
                {"user_id": user_id}
            ).sort("timestamp", -1).limit(50)
            return await cursor.to_list(length=50)
        except Exception as e:
            log.error(f"Error getting user notes: {e}")
            return []
    
    async def get_note(self, user_id: int, note_id: str) -> Optional[Dict]:
        """Get a specific note"""
        if not self._connected:
            return None
        
        try:
            return await self.notes.find_one({
                "_id": ObjectId(note_id),
                "user_id": user_id
            })
        except Exception as e:
            log.error(f"Error getting note: {e}")
            return None
    
    async def delete_note(self, user_id: int, note_id: str):
        """Delete a note"""
        if not self._connected:
            return True
        
        try:
            await self.notes.delete_one({
                "_id": ObjectId(note_id),
                "user_id": user_id
            })
            return True
        except Exception as e:
            log.error(f"Error deleting note: {e}")
            return False
    
    async def delete_all_notes(self, user_id: int):
        """Delete all notes for user"""
        if not self._connected:
            return True
        
        try:
            await self.notes.delete_many({"user_id": user_id})
            return True
        except Exception as e:
            log.error(f"Error deleting all notes: {e}")
            return False
    
    # ==================== REMINDERS ====================
    
    async def add_reminder(self, user_id: int, text: str, remind_at: datetime.datetime):
        """Add a reminder"""
        if not self._connected:
            return True
        
        try:
            doc = {
                "user_id": user_id,
                "text": text[:100],
                "remind_at": remind_at,
                "created": datetime.datetime.now(),
                "sent": False
            }
            await self.reminders.insert_one(doc)
            return True
        except Exception as e:
            log.error(f"Error adding reminder: {e}")
            return False
    
    async def get_user_reminders(self, user_id: int) -> List:
        """Get all reminders for user"""
        if not self._connected:
            return []
        
        try:
            cursor = self.reminders.find({
                "user_id": user_id,
                "sent": False
            }).sort("remind_at", 1)
            return await cursor.to_list(length=20)
        except Exception as e:
            log.error(f"Error getting user reminders: {e}")
            return []
    
    async def get_due_reminders(self) -> List:
        """Get all due reminders"""
        if not self._connected:
            return []
        
        try:
            cursor = self.reminders.find({
                "remind_at": {"$lte": datetime.datetime.now()},
                "sent": False
            })
            return await cursor.to_list(length=100)
        except Exception as e:
            log.error(f"Error getting due reminders: {e}")
            return []
    
    async def mark_reminder_sent(self, reminder_id: str):
        """Mark reminder as sent"""
        if not self._connected:
            return True
        
        try:
            await self.reminders.update_one(
                {"_id": ObjectId(reminder_id)},
                {"$set": {"sent": True}}
            )
            return True
        except Exception as e:
            log.error(f"Error marking reminder sent: {e}")
            return False
    
    # ==================== REFERRALS ====================
    
    async def add_referral(self, referrer_id: int, referred_id: int):
        """Add a referral"""
        if not self._connected:
            return False
        
        try:
            # Check if already referred
            existing = await self.referrals.find_one({
                "referrer_id": referrer_id,
                "referred_id": referred_id
            })
            if existing:
                return False
            
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
            
            # Give points to referred user
            await self.add_points(referred_id, 100)
            
            return True
        except Exception as e:
            log.error(f"Error adding referral: {e}")
            return False
    
    async def get_referral_count(self, user_id: int) -> int:
        """Get user's referral count"""
        if not self._connected:
            return 0
        
        try:
            user = await self.get_user(user_id)
            return user.get("ref_count", 0) if user else 0
        except:
            return 0
    
    # ==================== FEEDBACK ====================
    
    async def save_feedback(self, user_id: int, rating: int, comment: str):
        """Save user feedback"""
        if not self._connected:
            return True
        
        try:
            doc = {
                "user_id": user_id,
                "rating": rating,
                "comment": comment[:500],
                "timestamp": datetime.datetime.now()
            }
            await self.feedback.insert_one(doc)
            return True
        except Exception as e:
            log.error(f"Error saving feedback: {e}")
            return False
    
    # ==================== EXAMS ====================
    
    async def set_exam(self, user_id: int, exam_name: str, exam_date: str):
        """Set user's exam date"""
        if not self._connected:
            return True
        
        try:
            date_obj = datetime.datetime.strptime(exam_date, "%Y-%m-%d")
            await self.users.update_one(
                {"user_id": user_id},
                {"$set": {
                    "exam_name": exam_name,
                    "exam_date": date_obj
                }}
            )
            return True
        except Exception as e:
            log.error(f"Error setting exam: {e}")
            return False
    
    async def get_exam_reminders(self) -> List:
        """Get users with exams approaching"""
        if not self._connected:
            return []
        
        try:
            today = datetime.datetime.now()
            reminders = []
            
            cursor = self.users.find({
                "exam_date": {"$gte": today},
                "notify_exam": True
            })
            
            async for user in cursor:
                days_left = (user["exam_date"] - today).days
                if days_left in [1, 7, 30]:
                    reminders.append({
                        "user_id": user["user_id"],
                        "exam_name": user.get("exam_name", "Exam"),
                        "days_left": days_left
                    })
            
            return reminders
        except Exception as e:
            log.error(f"Error getting exam reminders: {e}")
            return []
    
    # ==================== STUDY PLAN ====================
    
    async def save_study_plan(self, user_id: int, plan: str, exam_date: str, subjects: str):
        """Save study plan"""
        if not self._connected:
            return True
        
        try:
            await self.users.update_one(
                {"user_id": user_id},
                {"$set": {
                    "study_plan": {
                        "plan": plan[:2000],
                        "exam_date": exam_date,
                        "subjects": subjects[:100],
                        "created": datetime.datetime.now()
                    }
                }}
            )
            return True
        except Exception as e:
            log.error(f"Error saving study plan: {e}")
            return False
    
    async def get_study_plan(self, user_id: int) -> Optional[Dict]:
        """Get user's study plan"""
        if not self._connected:
            return None
        
        try:
            user = await self.get_user(user_id)
            return user.get("study_plan") if user else None
        except:
            return None
    
    # ==================== CACHE ====================
    
    async def set_cache(self, key: str, value: str, hours: int = 24):
        """Set cache value"""
        if not self._connected:
            return True
        
        try:
            expiry = datetime.datetime.now() + datetime.timedelta(hours=hours)
            doc = {
                "key": key,
                "value": value,
                "expiry": expiry
            }
            await self.cache.update_one(
                {"key": key},
                {"$set": doc},
                upsert=True
            )
            return True
        except Exception as e:
            log.error(f"Error setting cache: {e}")
            return False
    
    async def get_cache(self, key: str) -> Optional[str]:
        """Get cache value"""
        if not self._connected:
            return None
        
        try:
            doc = await self.cache.find_one({"key": key})
            if doc and doc.get("expiry") > datetime.datetime.now():
                return doc.get("value")
            return None
        except Exception as e:
            log.error(f"Error getting cache: {e}")
            return None
    
    async def del_cache(self, key: str):
        """Delete cache"""
        if not self._connected:
            return True
        
        try:
            await self.cache.delete_one({"key": key})
            return True
        except Exception as e:
            log.error(f"Error deleting cache: {e}")
            return False
    
    async def del_cache_prefix(self, prefix: str):
        """Delete all cache with prefix"""
        if not self._connected:
            return True
        
        try:
            await self.cache.delete_many({"key": {"$regex": f"^{prefix}"}})
            return True
        except Exception as e:
            log.error(f"Error deleting cache prefix: {e}")
            return False
    
    # ==================== LEADERBOARD ====================
    
    async def get_leaderboard(self, limit: int = 10) -> List:
        """Get top users by points"""
        if not self._connected:
            return []
        
        try:
            cursor = self.users.find(
                {"blocked": False}
            ).sort("points", -1).limit(limit)
            return await cursor.to_list(length=limit)
        except Exception as e:
            log.error(f"Error getting leaderboard: {e}")
            return []
    
    async def get_rank(self, user_id: int) -> int:
        """Get user's rank"""
        if not self._connected:
            return 0
        
        try:
            user = await self.get_user(user_id)
            if not user:
                return 0
            
            points = user.get("points", 0)
            count = await self.users.count_documents({
                "blocked": False,
                "points": {"$gt": points}
            })
            return count + 1
        except:
            return 0
    
    # ==================== DAILY CHALLENGE ====================
    
    async def challenge_done_today(self, user_id: int) -> bool:
        """Check if user did daily challenge today"""
        if not self._connected:
            return False
        
        try:
            user = await self.get_user(user_id)
            if not user:
                return False
            
            last_challenge = user.get("last_challenge")
            if last_challenge:
                return last_challenge.date() == datetime.datetime.now().date()
            return False
        except:
            return False
    
    async def mark_challenge_done(self, user_id: int):
        """Mark daily challenge as done"""
        if not self._connected:
            return True
        
        try:
            await self.users.update_one(
                {"user_id": user_id},
                {"$set": {"last_challenge": datetime.datetime.now()}}
            )
            return True
        except Exception as e:
            log.error(f"Error marking challenge done: {e}")
            return False
    
    # ==================== STATS ====================
    
    async def stats(self) -> Dict:
        """Get bot statistics"""
        if not self._connected:
            return {
                "total": 0,
                "active_today": 0,
                "new_today": 0,
                "premium": 0,
                "blocked": 0,
                "questions": 0,
                "notes_total": 0
            }
        
        try:
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
        except Exception as e:
            log.error(f"Error getting stats: {e}")
            return {
                "total": 0,
                "active_today": 0,
                "new_today": 0,
                "premium": 0,
                "blocked": 0,
                "questions": 0,
                "notes_total": 0
            }
    
    # ==================== MORNING NOTIFICATIONS ====================
    
    async def morning_notify_users(self) -> List:
        """Get users who want morning notifications"""
        if not self._connected:
            return []
        
        try:
            cursor = self.users.find({
                "notify_morning": True,
                "blocked": False
            })
            return await cursor.to_list(length=1000)
        except Exception as e:
            log.error(f"Error getting morning notify users: {e}")
            return []
    
    # ==================== ALL USERS ====================
    
    async def all_users(self) -> List:
        """Get all users (for admin)"""
        if not self._connected:
            return []
        
        try:
            cursor = self.users.find({})
            return await cursor.to_list(length=10000)
        except Exception as e:
            log.error(f"Error getting all users: {e}")
            return []

# Create global database instance
db = Database()

# Export the db instance
__all__ = ['db']
