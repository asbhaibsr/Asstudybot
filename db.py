import os
from datetime import datetime, date, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
from typing import Optional  # यह import जोड़ना था

MONGO_URI = os.environ.get("MONGO_URI","mongodb+srv://USER:PASS@cluster.mongodb.net/studybot")

class DB:
    def __init__(self):
        self.client = self.users = self.usage = self.questions = None
        self.notes = self.reminders = self.cache = None

    async def connect(self):
        self.client    = AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=8000)
        d              = self.client["studybot"]
        self.users     = d["users"]
        self.usage     = d["usage"]
        self.questions = d["questions"]
        self.notes     = d["notes"]
        self.reminders = d["reminders"]
        self.cache     = d["cache"]
        await self.users.create_index("user_id", unique=True)
        await self.usage.create_index([("user_id",1),("date",1)])
        await self.cache.create_index("key", unique=True)
        await self.cache.create_index("expires_at", expireAfterSeconds=0)
        await self.notes.create_index("expires_at", expireAfterSeconds=0)
        await self.questions.create_index("expires_at", expireAfterSeconds=0)
        print("✅ MongoDB connected!")

    # ── Cache System (applies to ALL fetched content) ──────────────────────
    async def get_cache(self, key: str) -> Optional[str]:
        doc = await self.cache.find_one({"key": key})
        if doc:
            return doc.get("value")
        return None

    async def set_cache(self, key: str, value: str, ttl_hours: int = 24):
        """Cache for TTL hours — default 24h (1 day)"""
        expires = datetime.now() + timedelta(hours=ttl_hours)
        await self.cache.update_one(
            {"key": key},
            {"$set": {"key": key, "value": value, "expires_at": expires}},
            upsert=True)

    async def cleanup_old_cache(self):
        """MongoDB TTL index handles this automatically"""
        pass

    # ── Users ──────────────────────────────────────────────────────────────
    async def add_user(self, uid, name, username=None, ref_by=None):
        existing = await self.users.find_one({"user_id": uid})
        if not existing:
            await self.users.insert_one({
                "user_id":uid,"name":name,"username":username,
                "class_type":None,"course":None,"goal":None,
                "language":"hi","is_blocked":False,
                "is_premium":False,"premium_expiry":None,
                "total_q":0,"streak":0,"max_streak":0,
                "last_active":date.today().isoformat(),
                "points":50,"badges":["🌱 Newcomer"],
                "ref_by":ref_by,"ref_count":0,
                "notify_morning":True,"notify_exam":True,
                "exam_date":None,"exam_name":None,
                "api_usage":{},
                "joined":datetime.now().isoformat(),
            })
            if ref_by:
                await self.users.update_one({"user_id":ref_by},
                    {"$inc":{"ref_count":1,"points":100}})
                await self._check_ref_reward(ref_by)
        else:
            await self._update_streak(uid)

    async def _update_streak(self, uid):
        user = await self.users.find_one({"user_id": uid})
        if not user: return
        last = user.get("last_active",""); today = date.today().isoformat()
        yesterday = (date.today()-timedelta(days=1)).isoformat()
        if last == today: return
        new_s = user.get("streak",0)+1 if last==yesterday else 1
        max_s = max(new_s, user.get("max_streak",0))
        await self.users.update_one({"user_id":uid},
            {"$set":{"last_active":today,"streak":new_s,"max_streak":max_s}})
        await self._check_streak_badges(uid, new_s)

    async def _check_streak_badges(self, uid, streak):
        bmap = {3:"🔥 3-Day",7:"⭐ Week Warrior",14:"💪 Fortnight",30:"🏆 Monthly",100:"👑 Legend"}
        if streak in bmap:
            await self.users.update_one({"user_id":uid},
                {"$addToSet":{"badges":bmap[streak]},"$inc":{"points":streak*10}})

    async def _check_ref_reward(self, uid):
        user = await self.users.find_one({"user_id":uid})
        if not user: return
        if user.get("ref_count",0) % 5 == 0:
            await self.set_premium(uid, 7)

    async def get_user(self, uid):
        return await self.users.find_one({"user_id":uid})

    async def update_profile(self, uid, cls, course, goal):
        await self.users.update_one({"user_id":uid},
            {"$set":{"class_type":cls,"course":course,"goal":goal}})

    async def update_language(self, uid, lang):
        await self.users.update_one({"user_id":uid},{"$set":{"language":lang}})

    async def update_settings(self, uid, **kwargs):
        await self.users.update_one({"user_id":uid},{"$set":kwargs})

    async def is_blocked(self, uid):
        u = await self.users.find_one({"user_id":uid},{"is_blocked":1})
        return bool(u and u.get("is_blocked"))

    async def block_user(self, uid):
        await self.users.update_one({"user_id":uid},{"$set":{"is_blocked":True}})

    async def unblock_user(self, uid):
        await self.users.update_one({"user_id":uid},{"$set":{"is_blocked":False}})

    async def all_users(self):
        return await self.users.find({"is_blocked":False},{"user_id":1}).to_list(None)

    async def morning_notify_users(self):
        return await self.users.find(
            {"is_blocked":False,"notify_morning":True},
            {"user_id":1,"name":1,"streak":1}).to_list(None)

    async def stats(self):
        return {
            "total":       await self.users.count_documents({}),
            "premium":     await self.users.count_documents({"is_premium":True}),
            "blocked":     await self.users.count_documents({"is_blocked":True}),
            "questions":   await self.questions.count_documents({}),
            "active_today":await self.users.count_documents({"last_active":date.today().isoformat()}),
            "notes_total": await self.notes.count_documents({}),
        }

    # ── API Usage Tracking per user per day ───────────────────────────────
    async def get_api_usage(self, uid) -> dict:
        today = date.today().isoformat()
        doc = await self.usage.find_one({"user_id":uid,"date":today})
        return (doc or {}).get("api_usage", {})

    async def inc_api_usage(self, uid, api_name: str):
        today = date.today().isoformat()
        await self.usage.update_one(
            {"user_id":uid,"date":today},
            {"$inc":{f"api_usage.{api_name}":1}},
            upsert=True)

    # ── Premium ────────────────────────────────────────────────────────────
    async def is_premium(self, uid):
        u = await self.users.find_one({"user_id":uid},{"is_premium":1,"premium_expiry":1})
        if not u or not u.get("is_premium"): return False
        exp = u.get("premium_expiry")
        if exp and date.fromisoformat(exp) < date.today():
            await self.remove_premium(uid); return False
        return True

    async def set_premium(self, uid, days=30):
        u = await self.users.find_one({"user_id":uid},{"premium_expiry":1,"is_premium":1})
        if u and u.get("is_premium") and u.get("premium_expiry"):
            try:
                cur = date.fromisoformat(u["premium_expiry"])
                exp = (max(cur,date.today())+timedelta(days=days)).isoformat()
            except: exp = (date.today()+timedelta(days=days)).isoformat()
        else: exp = (date.today()+timedelta(days=days)).isoformat()
        await self.users.update_one({"user_id":uid},
            {"$set":{"is_premium":True,"premium_expiry":exp}})

    async def remove_premium(self, uid):
        await self.users.update_one({"user_id":uid},
            {"$set":{"is_premium":False,"premium_expiry":None}})

    # ── General Usage ─────────────────────────────────────────────────────
    async def get_usage(self, uid, kind):
        today = date.today().isoformat()
        doc = await self.usage.find_one({"user_id":uid,"date":today})
        return (doc or {}).get(kind, 0)

    async def inc_usage(self, uid, kind):
        today = date.today().isoformat()
        await self.usage.update_one(
            {"user_id":uid,"date":today},{"$inc":{kind:1}},upsert=True)
        if kind == "q":
            await self.users.update_one({"user_id":uid},
                {"$inc":{"total_q":1,"points":2}})

    async def save_q(self, uid, question, answer, api_used=""):
        """Save with 2-month auto-expiry"""
        expires = datetime.now() + timedelta(days=60)
        await self.questions.insert_one({
            "user_id":uid,"question":question,"answer":answer,
            "api_used":api_used,"ts":datetime.now().isoformat(),
            "expires_at":expires})

    # ── Chat History (Premium only, 2 month auto-delete) ─────────────────
    async def get_chat_history(self, uid, limit=20):
        cursor = self.questions.find(
            {"user_id":uid},
            {"question":1,"answer":1,"ts":1,"api_used":1}
        ).sort("ts",-1).limit(limit)
        return await cursor.to_list(None)

    # ── Points & Leaderboard ──────────────────────────────────────────────
    async def add_points(self, uid, pts):
        await self.users.update_one({"user_id":uid},{"$inc":{"points":pts}})

    async def get_leaderboard(self, limit=10):
        cursor = self.users.find(
            {"is_blocked":False},
            {"user_id":1,"name":1,"points":1,"streak":1,"badges":1}
        ).sort("points",-1).limit(limit)
        return await cursor.to_list(None)

    async def get_rank(self, uid):
        user = await self.users.find_one({"user_id":uid},{"points":1})
        if not user: return 0
        rank = await self.users.count_documents(
            {"points":{"$gt":user.get("points",0)},"is_blocked":False})
        return rank + 1

    # ── Notes (auto-delete after 2 months) ────────────────────────────────
    async def save_note(self, uid, title, content, subject="General"):
        expires = datetime.now() + timedelta(days=60)
        result = await self.notes.insert_one({
            "user_id":uid,"title":title,"content":content,
            "subject":subject,"ts":datetime.now().isoformat(),
            "expires_at":expires})
        return str(result.inserted_id)

    async def get_user_notes(self, uid, limit=15):
        cursor = self.notes.find(
            {"user_id":uid},{"title":1,"subject":1,"ts":1}
        ).sort("ts",-1).limit(limit)
        return await cursor.to_list(None)

    async def get_note(self, uid, note_id):
        from bson import ObjectId
        try: return await self.notes.find_one({"_id":ObjectId(note_id),"user_id":uid})
        except: return None

    async def delete_note(self, uid, note_id):
        from bson import ObjectId
        try: await self.notes.delete_one({"_id":ObjectId(note_id),"user_id":uid})
        except: pass

    # ── Reminders ─────────────────────────────────────────────────────────
    async def add_reminder(self, uid, text, remind_at):
        await self.reminders.insert_one({
            "user_id":uid,"text":text,
            "remind_at":remind_at.isoformat(),"sent":False,
            "expires_at": remind_at + timedelta(days=1),
            "created":datetime.now().isoformat()})

    async def get_due_reminders(self):
        now = datetime.now().isoformat()
        cursor = self.reminders.find({"remind_at":{"$lte":now},"sent":False})
        return await cursor.to_list(None)

    async def mark_reminder_sent(self, rid):
        from bson import ObjectId
        try: await self.reminders.update_one({"_id":ObjectId(rid)},{"$set":{"sent":True}})
        except: pass

    async def get_user_reminders(self, uid):
        now = datetime.now().isoformat()
        cursor = self.reminders.find(
            {"user_id":uid,"sent":False,"remind_at":{"$gte":now}},
            {"text":1,"remind_at":1}
        ).sort("remind_at",1).limit(5)
        return await cursor.to_list(None)

    # ── Exam ──────────────────────────────────────────────────────────────
    async def set_exam(self, uid, name, exam_date):
        await self.users.update_one({"user_id":uid},
            {"$set":{"exam_name":name,"exam_date":exam_date}})

    async def get_exam_reminders(self):
        results = []
        for days_ahead in [30,7,1]:
            target = (date.today()+timedelta(days=days_ahead)).isoformat()
            cursor = self.users.find(
                {"exam_date":target,"is_blocked":False,"notify_exam":True},
                {"user_id":1,"exam_name":1})
            users = await cursor.to_list(None)
            for u in users: u["days_left"] = days_ahead; results.append(u)
        return results

# Fix Optional import
from typing import Optional
db = DB()
