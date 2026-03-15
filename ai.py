import os, httpx, asyncio

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "YOUR_GEMINI_KEY")
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
NEWS_KEY   = os.environ.get("GNEWS_API_KEY", "")  # gnews.io free key
NEWS_URL   = "https://gnews.io/api/v4/search"

# ── AI ────────────────────────────────────────────────────────────────────────
async def ask_ai(question: str, user_data: dict = None, mode: str = "study") -> str:
    ud = user_data or {}
    cls  = ud.get("class_type","")
    subj = ud.get("course","")
    goal = ud.get("goal","")

    if mode == "ai":
        sys = ("Tum ek helpful AI assistant ho Indian students ke liye. "
               "Hindi aur English mix mein jawab do (Hinglish). "
               "Friendly, clear aur short raho. Emojis use karo. "
               "Koi bhi sawal – padhai, career, sarkari naukri, general – sab ka jawab do.")
    else:
        sys = (f"Tum ek expert Indian teacher ho. Class: {cls}, Subject: {subj}, Goal: {goal}. "
               "Hindi mein padhao. Simple bhasha, real examples, step-by-step. "
               "Emojis aur markdown use karo. "
               "Maths mein steps dikhao. Science mein examples do. "
               "Grammar questions mein rules + examples dono do.")

    body = {
        "contents":[{"parts":[{"text":f"{sys}\n\nSawal: {question}"}]}],
        "generationConfig":{"temperature":0.7,"maxOutputTokens":700}
    }
    try:
        async with httpx.AsyncClient(timeout=25) as c:
            r = await c.post(GEMINI_URL, json=body)
            d = r.json()
            if "candidates" in d:
                return d["candidates"][0]["content"]["parts"][0]["text"].strip()
            return "😕 Abhi jawab nahi de pa raha. Thodi der baad try karo."
    except Exception as e:
        return f"⚠️ AI busy hai. Thodi der mein dobara try karo!\n_{e}_"

# ── News & Sarkari Updates ────────────────────────────────────────────────────
async def get_news_updates(query: str) -> str:
    """Fetch news using GNews free API (100 req/day free)"""
    if not NEWS_KEY:
        return await _fallback_news(query)
    try:
        params = {"q":query,"lang":"hi","country":"in","max":8,"apikey":NEWS_KEY}
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(NEWS_URL, params=params)
            d = r.json()
            articles = d.get("articles",[])
            if not articles:
                params["lang"]="en"
                r = await c.get(NEWS_URL, params=params)
                d = r.json(); articles=d.get("articles",[])
            if not articles:
                return await _fallback_news(query)
            lines = []
            for a in articles[:7]:
                title = a.get("title","")[:80]
                url   = a.get("url","")
                src   = a.get("source",{}).get("name","")
                pub   = a.get("publishedAt","")[:10]
                lines.append(f"• *{title}*\n  📰 {src} | 📅 {pub}\n  🔗 {url}\n")
            return "\n".join(lines)
    except Exception as e:
        return await _fallback_news(query)

async def _fallback_news(query: str) -> str:
    """Use Gemini to generate latest info when no news API key"""
    prompt = (f"Latest India news aur updates ke baare mein batao: '{query}'. "
              "Real aur recent information do (2024-2025). "
              "Hindi mein 6-8 bullet points mein. "
              "Sarkari updates ho to: scheme name, benefit, apply kaise – short mein. "
              "Job/form ho to: post name, last date, website. "
              "News ho to: kya hua, kab, kahan. "
              "Markdown use karo.")
    try:
        body={
            "contents":[{"parts":[{"text":prompt}]}],
            "generationConfig":{"temperature":0.3,"maxOutputTokens":800}
        }
        async with httpx.AsyncClient(timeout=25) as c:
            r=await c.post(GEMINI_URL,json=body)
            d=r.json()
            if "candidates" in d:
                return d["candidates"][0]["content"]["parts"][0]["text"].strip()
    except: pass
    return "⚠️ Updates abhi nahi mil rahi. Thodi der baad try karo.\n\n🌐 Sarkari sites:\n• sarkariresult.com\n• rojgarresult.com\n• india.gov.in"
