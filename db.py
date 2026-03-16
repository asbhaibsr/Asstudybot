import os
from datetime import datetime, date, timedelta
from motor.motor_asyncio import AsyncIOMotorClient
from typing import Optional

MONGO_URI = os.environ.get("MONGO_URI",
    "mongodb+srv://USER:PASS@cluster.mongodb.net/studybot")

class DB:
    def __init__(self):
        self.client = None
        # collections
        self.users = self.usage = self.questions = None
        self.notes = self.reminders = self.cache   = None
        self.study_plans = self.achievements        = None
        self.vocab_history = self.daily_quiz        = None

    async def connect(self):
        self.client       = AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=8000)
        d                 = self.client["studybot"]
        self.users        = d["users"]
        self.usage        = d["usage"]
        self.questions    = d["questions"]
        self.notes        = d["notes"]
        self.reminders    = d["reminders"]
        self.cache        = d["cache"]
        self.study_plans  = d["study_plans"]
        self.achievements = d["achievements"]
        self.vocab_history= d["vocab_history"]
        self.daily_quiz   = d["daily_quiz"]

        # Indexes
        await self.users.create_index("user_id", unique=True)
        await self.usage.create_index([("user_id",1),("date",1)])
        await self.cache.create_index("key", unique=True)
        await self.cache.create_index("expires_at", expireAfterSeconds=0)
        await self.notes.create_index("expires_at", expireAfterSeconds=0)
        await self.questions.create_index("expires_at", expireAfterSeconds=0)
        await self.reminders.create_index("expires_at", expireAfterSeconds=0)
        print("✅ MongoDB connected!")

    # ══════════════════════════════════════════════════════════════════════
    # CACHE
    # ══════════════════════════════════════════════════════════════════════
    async def get_cache(self, key: str) -> Optional[str]:
        try:
            doc = await self.cache.find_one({"key": key})
            return doc.get("value") if doc else None
        except: return None

    async def set_cache(self, key: str, value: str, ttl_hours: int = 24):
        expires = datetime.now() + timedelta(hours=ttl_hours)
        try:
            await self.cache.update_one(
                {"key": key},
                {"$set": {"key": key, "value": value, "expires_at": expires}},
                upsert=True)
        except: pass

    async def del_cache(self, key: str):
        try: await self.cache.delete_one({"key": key})
        except: pass

    async def del_cache_prefix(self, prefix: str):
        """Delete all cache keys starting with prefix"""
        try:
            await self.cache.delete_many({"key": {"$regex": f"^{prefix}"}})
        except: pass

    # ══════════════════════════════════════════════════════════════════════
    # USERS
    # ══════════════════════════════════════════════════════════════════════
    async def add_user(self, uid: int, name: str, username=None, ref_by=None):
        existing = await self.users.find_one({"user_id": uid})
        if not existing:
            await self.users.insert_one({
                "user_id":       uid,
                "name":          name,
                "username":      username,
                "class_type":    None,
                "course":        None,
                "goal":          None,
                "language":      "hi",
                "is_blocked":    False,
                "is_premium":    False,
                "premium_expiry": None,
                "total_q":       0,
                "streak":        0,
                "max_streak":    0,
                "last_active":   date.today().isoformat(),
                "points":        50,
                "badges":        ["🌱 Newcomer"],
                "ref_by":        ref_by,
                "ref_count":     0,
                "notify_morning":True,
                "notify_exam":   True,
                "exam_date":     None,
                "exam_name":     None,
                "api_usage":     {},
                "daily_challenge_done": None,  # date string
                "joined":        datetime.now().isoformat(),
            })
            # Reward referrer
            if ref_by and ref_by != uid:
                await self.users.update_one({"user_id": ref_by},
                    {"$inc": {"ref_count":1, "points":100}})
                await self._check_ref_reward(ref_by)
        else:
            await self._update_streak(uid)

    async def _update_streak(self, uid: int):
        user = await self.users.find_one({"user_id": uid})
        if not user: return
        last      = user.get("last_active","")
        today_s   = date.today().isoformat()
        yesterday = (date.today()-timedelta(days=1)).isoformat()
        if last == today_s: return
        new_s = user.get("streak",0)+1 if last==yesterday else 1
        max_s = max(new_s, user.get("max_streak",0))
        await self.users.update_one({"user_id":uid},
            {"$set": {"last_active":today_s,"streak":new_s,"max_streak":max_s}})
        await self._check_streak_badges(uid, new_s)

    async def _check_streak_badges(self, uid: int, streak: int):
        bmap = {3:"🔥 3-Day",7:"⭐ Week Warrior",14:"💪 Fortnight",
                30:"🏆 Monthly",100:"👑 Legend",365:"🌟 Year Master"}
        if streak in bmap:
            await self.users.update_one({"user_id":uid},
                {"$addToSet":{"badges":bmap[streak]}, "$inc":{"points":streak*10}})

    async def _check_ref_reward(self, uid: int):
        user = await self.users.find_one({"user_id":uid})
        if not user: return
        if user.get("ref_count",0) % 5 == 0:
            await self.set_premium(uid, 7)
            return True
        return False

    async def get_user(self, uid: int) -> Optional[dict]:
        return await self.users.find_one({"user_id": uid})

    async def update_profile(self, uid: int, cls: str, course: str, goal: str):
        await self.users.update_one({"user_id":uid},
            {"$set":{"class_type":cls,"course":course,"goal":goal}})

    async def update_language(self, uid: int, lang: str):
        await self.users.update_one({"user_id":uid},{"$set":{"language":lang}})

    async def update_settings(self, uid: int, **kwargs):
        await self.users.update_one({"user_id":uid},{"$set":kwargs})

    async def is_blocked(self, uid: int) -> bool:
        u = await self.users.find_one({"user_id":uid},{"is_blocked":1})
        return bool(u and u.get("is_blocked"))

    async def block_user(self, uid: int):
        await self.users.update_one({"user_id":uid},{"$set":{"is_blocked":True}})

    async def unblock_user(self, uid: int):
        await self.users.update_one({"user_id":uid},{"$set":{"is_blocked":False}})

    async def all_users(self):
        return await self.users.find({"is_blocked":False},{"user_id":1}).to_list(None)

    async def morning_notify_users(self):
        return await self.users.find(
            {"is_blocked":False,"notify_morning":True},
            {"user_id":1,"name":1,"streak":1}).to_list(None)

    async def stats(self) -> dict:
        return {
            "total":        await self.users.count_documents({}),
            "premium":      await self.users.count_documents({"is_premium":True}),
            "blocked":      await self.users.count_documents({"is_blocked":True}),
            "questions":    await self.questions.count_documents({}),
            "active_today": await self.users.count_documents(
                {"last_active":date.today().isoformat()}),
            "notes_total":  await self.notes.count_documents({}),
            "new_today":    await self.users.count_documents(
                {"joined":{"$gte":datetime.now().replace(hour=0,minute=0,second=0).isoformat()}}),
        }

    # ══════════════════════════════════════════════════════════════════════
    # API USAGE TRACKING (per user per day)
    # ══════════════════════════════════════════════════════════════════════
    async def get_api_usage(self, uid: int) -> dict:
        today = date.today().isoformat()
        doc   = await self.usage.find_one({"user_id":uid,"date":today})
        return (doc or {}).get("api_usage",{})

    async def inc_api_usage(self, uid: int, api_name: str):
        today = date.today().isoformat()
        await self.usage.update_one(
            {"user_id":uid,"date":today},
            {"$inc":{f"api_usage.{api_name}":1}},
            upsert=True)

    # ══════════════════════════════════════════════════════════════════════
    # PREMIUM
    # ══════════════════════════════════════════════════════════════════════
    async def is_premium(self, uid: int) -> bool:
        u = await self.users.find_one({"user_id":uid},{"is_premium":1,"premium_expiry":1})
        if not u or not u.get("is_premium"): return False
        exp = u.get("premium_expiry")
        if exp and date.fromisoformat(exp) < date.today():
            await self.remove_premium(uid); return False
        return True

    async def set_premium(self, uid: int, days: int = 30):
        u = await self.users.find_one({"user_id":uid},{"premium_expiry":1,"is_premium":1})
        if u and u.get("is_premium") and u.get("premium_expiry"):
            try:
                cur = date.fromisoformat(u["premium_expiry"])
                exp = (max(cur,date.today())+timedelta(days=days)).isoformat()
            except: exp = (date.today()+timedelta(days=days)).isoformat()
        else:
            exp = (date.today()+timedelta(days=days)).isoformat()
        await self.users.update_one({"user_id":uid},
            {"$set":{"is_premium":True,"premium_expiry":exp}})

    async def remove_premium(self, uid: int):
        await self.users.update_one({"user_id":uid},
            {"$set":{"is_premium":False,"premium_expiry":None}})

    # ══════════════════════════════════════════════════════════════════════
    # GENERAL USAGE COUNTERS
    # ══════════════════════════════════════════════════════════════════════
    async def get_usage(self, uid: int, kind: str) -> int:
        today = date.today().isoformat()
        doc   = await self.usage.find_one({"user_id":uid,"date":today})
        return (doc or {}).get(kind, 0)

    async def inc_usage(self, uid: int, kind: str):
        today = date.today().isoformat()
        await self.usage.update_one(
            {"user_id":uid,"date":today},
            {"$inc":{kind:1}}, upsert=True)
        if kind == "q":
            await self.users.update_one({"user_id":uid},
                {"$inc":{"total_q":1,"points":2}})

    async def save_q(self, uid: int, question: str, answer: str, api_used: str = ""):
        expires = datetime.now() + timedelta(days=60)
        await self.questions.insert_one({
            "user_id":  uid, "question": question, "answer": answer,
            "api_used": api_used, "ts": datetime.now().isoformat(),
            "expires_at": expires})

    # ══════════════════════════════════════════════════════════════════════
    # CHAT HISTORY
    # ══════════════════════════════════════════════════════════════════════
    async def get_chat_history(self, uid: int, limit: int = 20):
        cursor = self.questions.find(
            {"user_id":uid},
            {"question":1,"answer":1,"ts":1,"api_used":1,"_id":1}
        ).sort("ts",-1).limit(limit)
        return await cursor.to_list(None)

    async def delete_chat_item(self, uid: int, item_id: str):
        from bson import ObjectId
        try: await self.questions.delete_one({"_id":ObjectId(item_id),"user_id":uid})
        except: pass

    async def clear_chat_history(self, uid: int):
        await self.questions.delete_many({"user_id":uid})

    # ══════════════════════════════════════════════════════════════════════
    # POINTS & LEADERBOARD
    # ══════════════════════════════════════════════════════════════════════
    async def add_points(self, uid: int, pts: int):
        await self.users.update_one({"user_id":uid},{"$inc":{"points":pts}})

    async def get_leaderboard(self, limit: int = 10):
        cursor = self.users.find(
            {"is_blocked":False},
            {"user_id":1,"name":1,"points":1,"streak":1,"badges":1,"ref_count":1}
        ).sort("points",-1).limit(limit)
        return await cursor.to_list(None)

    async def get_rank(self, uid: int) -> int:
        user = await self.users.find_one({"user_id":uid},{"points":1})
        if not user: return 0
        rank = await self.users.count_documents(
            {"points":{"$gt":user.get("points",0)},"is_blocked":False})
        return rank + 1

    # ══════════════════════════════════════════════════════════════════════
    # NOTES  (auto-delete 2 months)
    # ══════════════════════════════════════════════════════════════════════
    async def save_note(self, uid: int, title: str, content: str,
                        subject: str = "General") -> str:
        expires = datetime.now() + timedelta(days=60)
        result  = await self.notes.insert_one({
            "user_id": uid, "title": title, "content": content,
            "subject": subject, "ts": datetime.now().isoformat(),
            "expires_at": expires})
        return str(result.inserted_id)

    async def get_user_notes(self, uid: int, limit: int = 20):
        cursor = self.notes.find(
            {"user_id":uid},{"title":1,"subject":1,"ts":1}
        ).sort("ts",-1).limit(limit)
        return await cursor.to_list(None)

    async def get_note(self, uid: int, note_id: str) -> Optional[dict]:
        from bson import ObjectId
        try: return await self.notes.find_one({"_id":ObjectId(note_id),"user_id":uid})
        except: return None

    async def delete_note(self, uid: int, note_id: str):
        from bson import ObjectId
        try: await self.notes.delete_one({"_id":ObjectId(note_id),"user_id":uid})
        except: pass

    async def delete_all_notes(self, uid: int):
        await self.notes.delete_many({"user_id":uid})

    # ══════════════════════════════════════════════════════════════════════
    # REMINDERS
    # ══════════════════════════════════════════════════════════════════════
    async def add_reminder(self, uid: int, text: str, remind_at: datetime):
        await self.reminders.insert_one({
            "user_id":  uid, "text": text,
            "remind_at":remind_at.isoformat(), "sent": False,
            "expires_at": remind_at + timedelta(days=1),
            "created":  datetime.now().isoformat()})

    async def get_due_reminders(self):
        now    = datetime.now().isoformat()
        cursor = self.reminders.find({"remind_at":{"$lte":now},"sent":False})
        return await cursor.to_list(None)

    async def mark_reminder_sent(self, rid: str):
        from bson import ObjectId
        try: await self.reminders.update_one({"_id":ObjectId(rid)},{"$set":{"sent":True}})
        except: pass

    async def get_user_reminders(self, uid: int):
        now    = datetime.now().isoformat()
        cursor = self.reminders.find(
            {"user_id":uid,"sent":False,"remind_at":{"$gte":now}},
            {"text":1,"remind_at":1,"_id":1}
        ).sort("remind_at",1).limit(5)
        return await cursor.to_list(None)

    async def delete_reminder(self, uid: int, rid: str):
        from bson import ObjectId
        try: await self.reminders.delete_one({"_id":ObjectId(rid),"user_id":uid})
        except: pass

    # ══════════════════════════════════════════════════════════════════════
    # EXAM TRACKING
    # ══════════════════════════════════════════════════════════════════════
    async def set_exam(self, uid: int, name: str, exam_date: str):
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
            for u in users:
                u["days_left"] = days_ahead
                results.append(u)
        return results

    # ══════════════════════════════════════════════════════════════════════
    # STUDY PLAN
    # ══════════════════════════════════════════════════════════════════════
    async def save_study_plan(self, uid: int, plan: str, exam_date: str, subjects: str):
        expires = datetime.now() + timedelta(days=120)
        await self.study_plans.update_one(
            {"user_id": uid},
            {"$set": {"user_id":uid,"plan":plan,"exam_date":exam_date,
                      "subjects":subjects,"ts":datetime.now().isoformat(),
                      "expires_at":expires}},
            upsert=True)

    async def get_study_plan(self, uid: int) -> Optional[dict]:
        return await self.study_plans.find_one({"user_id":uid})

    # ══════════════════════════════════════════════════════════════════════
    # DAILY CHALLENGE — prevent repeat on same day
    # ══════════════════════════════════════════════════════════════════════
    async def challenge_done_today(self, uid: int) -> bool:
        u = await self.users.find_one({"user_id":uid},{"daily_challenge_done":1})
        return (u or {}).get("daily_challenge_done") == date.today().isoformat()

    async def mark_challenge_done(self, uid: int):
        await self.users.update_one({"user_id":uid},
            {"$set":{"daily_challenge_done":date.today().isoformat()}})

    # ══════════════════════════════════════════════════════════════════════
    # ACHIEVEMENTS
    # ══════════════════════════════════════════════════════════════════════
    async def check_and_award(self, uid: int):
        """Auto-award badges based on stats"""
        u = await self.users.find_one({"user_id":uid})
        if not u: return
        new_badges = []
        pts    = u.get("points",0)
        total_q= u.get("total_q",0)
        refs   = u.get("ref_count",0)
        pts_map  = {500:"⭐ 500 Club",1000:"💎 1K Elite",5000:"👑 5K Master"}
        q_map    = {10:"📝 10 Q",50:"📚 50 Q",100:"🎓 100 Q"}
        ref_map  = {1:"👥 First Ref",5:"🤝 5 Refs",10:"🌟 10 Refs"}
        for threshold,badge in pts_map.items():
            if pts >= threshold: new_badges.append(badge)
        for threshold,badge in q_map.items():
            if total_q >= threshold: new_badges.append(badge)
        for threshold,badge in ref_map.items():
            if refs >= threshold: new_badges.append(badge)
        if new_badges:
            await self.users.update_one({"user_id":uid},
                {"$addToSet":{"badges":{"$each":new_badges}}})

db = DB()
