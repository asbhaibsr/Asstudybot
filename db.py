import os
from datetime import datetime, date, timedelta
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://USER:PASS@cluster.mongodb.net/studybot")

class DB:
    def __init__(self):
        self.client = None
        self.col = None  # users
        self.usage_col = None
        self.q_col = None
        self.settings_col = None

    async def connect(self):
        self.client = AsyncIOMotorClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        d = self.client["studybot"]
        self.col         = d["users"]
        self.usage_col   = d["usage"]
        self.q_col       = d["questions"]
        self.settings_col= d["settings"]
        # Indexes
        await self.col.create_index("user_id", unique=True)
        await self.usage_col.create_index([("user_id",1),("date",1)])
        print("✅ MongoDB connected!")

    # ── Users ───────────────────────────────────────────────────────────────
    async def add_user(self, uid, name, username=None):
        await self.col.update_one({"user_id":uid},
            {"$setOnInsert":{
                "user_id":uid,"name":name,"username":username,
                "class_type":None,"course":None,"goal":None,
                "is_blocked":False,"is_premium":False,"premium_expiry":None,
                "total_q":0,"streak":0,"joined":datetime.now().isoformat()
            }}, upsert=True)

    async def get_user(self, uid):
        return await self.col.find_one({"user_id":uid})

    async def update_profile(self, uid, cls, course, goal):
        await self.col.update_one({"user_id":uid},
            {"$set":{"class_type":cls,"course":course,"goal":goal}})

    async def is_blocked(self, uid):
        u=await self.col.find_one({"user_id":uid},{"is_blocked":1})
        return u.get("is_blocked",False) if u else False

    async def block_user(self, uid):
        await self.col.update_one({"user_id":uid},{"$set":{"is_blocked":True}})

    async def unblock_user(self, uid):
        await self.col.update_one({"user_id":uid},{"$set":{"is_blocked":False}})

    async def all_users(self):
        return await self.col.find({"is_blocked":False},{"user_id":1}).to_list(None)

    async def stats(self):
        return {
            "total":   await self.col.count_documents({}),
            "premium": await self.col.count_documents({"is_premium":True}),
            "blocked": await self.col.count_documents({"is_blocked":True}),
            "questions":await self.q_col.count_documents({}),
        }

    # ── Premium ─────────────────────────────────────────────────────────────
    async def is_premium(self, uid):
        u=await self.col.find_one({"user_id":uid},{"is_premium":1,"premium_expiry":1})
        if not u or not u.get("is_premium"): return False
        exp=u.get("premium_expiry")
        if exp and date.fromisoformat(exp)<date.today():
            await self.remove_premium(uid); return False
        return True

    async def set_premium(self, uid, days=30):
        exp=(date.today()+timedelta(days=days)).isoformat()
        await self.col.update_one({"user_id":uid},
            {"$set":{"is_premium":True,"premium_expiry":exp}})

    async def remove_premium(self, uid):
        await self.col.update_one({"user_id":uid},
            {"$set":{"is_premium":False,"premium_expiry":None}})

    # ── Usage tracking ───────────────────────────────────────────────────────
    async def get_usage(self, uid, kind):
        today=date.today().isoformat()
        doc=await self.usage_col.find_one({"user_id":uid,"date":today})
        return (doc or {}).get(kind,0)

    async def inc_usage(self, uid, kind):
        today=date.today().isoformat()
        await self.usage_col.update_one(
            {"user_id":uid,"date":today},{"$inc":{kind:1}},upsert=True)
        if kind=="q":
            await self.col.update_one({"user_id":uid},{"$inc":{"total_q":1}})

    # ── Questions ────────────────────────────────────────────────────────────
    async def save_q(self, uid, question, answer):
        await self.q_col.insert_one({
            "user_id":uid,"question":question,"answer":answer,
            "ts":datetime.now().isoformat()
        })

db = DB()
