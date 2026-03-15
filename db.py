import os
from datetime import datetime, date, timedelta
from motor.motor_asyncio import AsyncIOMotorClient

MONGO_URI = os.environ.get("MONGO_URI","mongodb+srv://USER:PASS@cluster.mongodb.net/studybot")

class DB:
    def __init__(self):
        self.client=self.users=self.usage=self.questions=self.settings=None

    async def connect(self):
        self.client=AsyncIOMotorClient(MONGO_URI,serverSelectionTimeoutMS=8000)
        d=self.client["studybot"]
        self.users=d["users"]; self.usage=d["usage"]
        self.questions=d["questions"]; self.settings=d["settings"]
        await self.users.create_index("user_id",unique=True)
        await self.usage.create_index([("user_id",1),("date",1)])
        print("✅ MongoDB connected!")

    async def add_user(self,uid,name,username=None,ref_by=None):
        existing=await self.users.find_one({"user_id":uid})
        if not existing:
            await self.users.insert_one({
                "user_id":uid,"name":name,"username":username,
                "class_type":None,"course":None,"goal":None,
                "is_blocked":False,"is_premium":False,"premium_expiry":None,
                "total_q":0,"streak":0,"max_streak":0,
                "last_active":date.today().isoformat(),
                "points":50,"badges":["🌱 Newcomer"],
                "ref_by":ref_by,"ref_count":0,
                "notify_morning":True,"notify_exam":True,
                "exam_date":None,"exam_name":None,
                "joined":datetime.now().isoformat(),
            })
            if ref_by:
                await self.users.update_one({"user_id":ref_by},{"$inc":{"ref_count":1,"points":100}})
                await self._check_ref_reward(ref_by)
        else:
            await self._update_streak(uid)

    async def _update_streak(self,uid):
        user=await self.users.find_one({"user_id":uid})
        if not user: return
        last=user.get("last_active",""); today=date.today().isoformat()
        yesterday=(date.today()-timedelta(days=1)).isoformat()
        if last==today: return
        new_s=user.get("streak",0)+1 if last==yesterday else 1
        max_s=max(new_s,user.get("max_streak",0))
        await self.users.update_one({"user_id":uid},{"$set":{"last_active":today,"streak":new_s,"max_streak":max_s}})
        await self._check_streak_badges(uid,new_s)

    async def _check_streak_badges(self,uid,streak):
        bmap={3:"🔥 3-Day Streak",7:"⭐ Week Warrior",14:"💪 Fortnight Hero",30:"🏆 Monthly Master",100:"👑 Legend"}
        if streak in bmap:
            await self.users.update_one({"user_id":uid},{"$addToSet":{"badges":bmap[streak]},"$inc":{"points":streak*10}})
            return bmap[streak]
        return None

    async def _check_ref_reward(self,uid):
        user=await self.users.find_one({"user_id":uid})
        if not user: return False
        if user.get("ref_count",0)%5==0:
            await self.set_premium(uid,7); return True
        return False

    async def get_user(self,uid):
        return await self.users.find_one({"user_id":uid})

    async def update_profile(self,uid,cls,course,goal):
        await self.users.update_one({"user_id":uid},{"$set":{"class_type":cls,"course":course,"goal":goal}})

    async def update_settings(self,uid,**kwargs):
        await self.users.update_one({"user_id":uid},{"$set":kwargs})

    async def is_blocked(self,uid):
        u=await self.users.find_one({"user_id":uid},{"is_blocked":1})
        return bool(u and u.get("is_blocked"))

    async def block_user(self,uid):
        await self.users.update_one({"user_id":uid},{"$set":{"is_blocked":True}})

    async def unblock_user(self,uid):
        await self.users.update_one({"user_id":uid},{"$set":{"is_blocked":False}})

    async def all_users(self):
        return await self.users.find({"is_blocked":False},{"user_id":1}).to_list(None)

    async def morning_notify_users(self):
        return await self.users.find({"is_blocked":False,"notify_morning":True},{"user_id":1,"name":1,"streak":1}).to_list(None)

    async def stats(self):
        return {
            "total":await self.users.count_documents({}),
            "premium":await self.users.count_documents({"is_premium":True}),
            "blocked":await self.users.count_documents({"is_blocked":True}),
            "questions":await self.questions.count_documents({}),
            "active_today":await self.users.count_documents({"last_active":date.today().isoformat()}),
        }

    async def is_premium(self,uid):
        u=await self.users.find_one({"user_id":uid},{"is_premium":1,"premium_expiry":1})
        if not u or not u.get("is_premium"): return False
        exp=u.get("premium_expiry")
        if exp and date.fromisoformat(exp)<date.today():
            await self.remove_premium(uid); return False
        return True

    async def set_premium(self,uid,days=30):
        u=await self.users.find_one({"user_id":uid},{"premium_expiry":1,"is_premium":1})
        if u and u.get("is_premium") and u.get("premium_expiry"):
            try: cur=date.fromisoformat(u["premium_expiry"]); exp=(max(cur,date.today())+timedelta(days=days)).isoformat()
            except: exp=(date.today()+timedelta(days=days)).isoformat()
        else: exp=(date.today()+timedelta(days=days)).isoformat()
        await self.users.update_one({"user_id":uid},{"$set":{"is_premium":True,"premium_expiry":exp}})

    async def remove_premium(self,uid):
        await self.users.update_one({"user_id":uid},{"$set":{"is_premium":False,"premium_expiry":None}})

    async def get_usage(self,uid,kind):
        today=date.today().isoformat()
        doc=await self.usage.find_one({"user_id":uid,"date":today})
        return (doc or {}).get(kind,0)

    async def inc_usage(self,uid,kind):
        today=date.today().isoformat()
        await self.usage.update_one({"user_id":uid,"date":today},{"$inc":{kind:1}},upsert=True)
        if kind=="q":
            await self.users.update_one({"user_id":uid},{"$inc":{"total_q":1,"points":2}})

    async def save_q(self,uid,question,answer):
        await self.questions.insert_one({"user_id":uid,"question":question,"answer":answer,"ts":datetime.now().isoformat()})

    async def add_points(self,uid,pts):
        await self.users.update_one({"user_id":uid},{"$inc":{"points":pts}})

    async def get_leaderboard(self,limit=10):
        cursor=self.users.find({"is_blocked":False},{"user_id":1,"name":1,"points":1,"streak":1,"badges":1}).sort("points",-1).limit(limit)
        return await cursor.to_list(None)

    async def get_rank(self,uid):
        user=await self.users.find_one({"user_id":uid},{"points":1})
        if not user: return 0
        rank=await self.users.count_documents({"points":{"$gt":user.get("points",0)},"is_blocked":False})
        return rank+1

    async def set_exam(self,uid,name,exam_date):
        await self.users.update_one({"user_id":uid},{"$set":{"exam_name":name,"exam_date":exam_date}})

    async def get_exam_reminders(self):
        results=[]
        for days_ahead in [30,7,1]:
            target=(date.today()+timedelta(days=days_ahead)).isoformat()
            cursor=self.users.find({"exam_date":target,"is_blocked":False,"notify_exam":True},{"user_id":1,"exam_name":1})
            users=await cursor.to_list(None)
            for u in users: u["days_left"]=days_ahead; results.append(u)
        return results

db=DB()
