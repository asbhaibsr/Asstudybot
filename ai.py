import asyncio, httpx, logging, random
from typing import Optional

log = logging.getLogger(__name__)

# ── G4F — Free AI, No API Key ─────────────────────────────────────────────────
async def ask_ai(question: str, user_data: dict = None, mode: str = "study") -> str:
    ud = user_data or {}
    cls  = ud.get("class_type", "")
    subj = ud.get("course", "")
    goal = ud.get("goal", "")

    if mode == "ai":
        system = (
            "Tum ek strict Study AI Tutor ho Indian students ke liye. "
            "SIRF padhai, exam, school/college, career se related sawaal ka jawab do. "
            "Agar koi off-topic pooche (movies, entertainment, personal life, dating etc.) "
            "to politely refuse karo: 'Main sirf study topics mein help kar sakta hoon.' "
            "Hindi/Hinglish mein jawab do. Clear, step-by-step, examples ke saath. "
            "Emojis aur markdown use karo."
        )
    else:
        system = (
            f"Tum ek expert Indian teacher ho. Class: {cls}, Subject: {subj}, Goal: {goal}. "
            "Hindi mein clear aur simple tarike se padhao. "
            "Real Indian examples do. Step-by-step samjhao. Markdown use karo."
        )

    prompt = f"{system}\n\nStudent ka sawaal: {question}"

    # Try G4F first
    try:
        result = await _g4f_query(prompt)
        if result and len(result) > 20:
            return result
    except Exception as e:
        log.warning(f"G4F failed: {e}")

    # Fallback: Wikipedia search + format
    try:
        wiki = await _wiki_search(question)
        if wiki:
            return f"📚 *Wikipedia se:*\n\n{wiki}\n\n_(AI temporarily unavailable, Wikipedia se answer diya)_"
    except Exception as e:
        log.warning(f"Wiki fallback failed: {e}")

    return "⚠️ Abhi answer nahi de pa raha. Thodi der baad try karo!"

async def _g4f_query(prompt: str) -> str:
    """G4F async query — tries multiple free providers"""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _g4f_sync, prompt)

def _g4f_sync(prompt: str) -> str:
    try:
        import g4f
        from g4f.client import Client
        client = Client()
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            timeout=30,
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        log.warning(f"G4F client error: {e}")
        # Try legacy method
        try:
            import g4f
            resp = g4f.ChatCompletion.create(
                model=g4f.models.default,
                messages=[{"role": "user", "content": prompt}],
                timeout=30,
            )
            if isinstance(resp, str):
                return resp
            return str(resp)
        except Exception as e2:
            raise Exception(f"G4F both methods failed: {e2}")

# ── Wikipedia fallback ────────────────────────────────────────────────────────
async def _wiki_search(query: str) -> Optional[str]:
    """Search Wikipedia (free, no key needed)"""
    try:
        # Hindi Wikipedia first
        url = "https://hi.wikipedia.org/api/rest_v1/page/summary/" + query.replace(" ", "_")
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(url)
            if r.status_code == 200:
                d = r.json()
                extract = d.get("extract", "")
                title = d.get("title", "")
                if extract and len(extract) > 50:
                    return f"*{title}*\n\n{extract[:600]}..."

        # English Wikipedia
        url2 = f"https://en.wikipedia.org/api/rest_v1/page/summary/{query.replace(' ','_')}"
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(url2)
            if r.status_code == 200:
                d = r.json()
                extract = d.get("extract", "")
                title = d.get("title", "")
                if extract and len(extract) > 50:
                    return f"*{title}*\n\n{extract[:600]}..."
    except:
        pass
    return None

# ── News — NewsAPI.org free tier (1000 req/month) ────────────────────────────
# Fallback: GNews, then RSS feeds
NEWS_SOURCES = {
    "india":   "India latest news",
    "pol":     "India politics BJP Congress",
    "sport":   "India cricket IPL sports",
    "biz":     "India economy business market",
    "edu":     "India education CBSE board exam school",
}

UPD_QUERIES = {
    "all":     "sarkari naukri recruitment result form India 2025",
    "jobs":    "government job recruitment vacancy India 2025",
    "forms":   "online form apply government India 2025",
    "results": "board exam result 2025 CBSE Bihar UP",
    "yojana":  "government scheme yojana 2025 India benefit",
    "admit":   "admit card hall ticket download 2025",
    "scholar": "scholarship 2025 India students apply",
}

async def get_news_text(category: str = "india") -> str:
    query = NEWS_SOURCES.get(category, "India news")
    # Try GNews free API (100/day free — no key needed for basic)
    try:
        result = await _gnews_fetch(query)
        if result: return result
    except: pass
    # Fallback to G4F
    return await _ai_news(query)

async def get_updates_text(category: str = "all") -> str:
    query = UPD_QUERIES.get(category, UPD_QUERIES["all"])
    try:
        result = await _gnews_fetch(query)
        if result: return result
    except: pass
    return await _ai_news(f"India sarkari: {query}")

async def _gnews_fetch(query: str) -> Optional[str]:
    """GNews.io — free tier, no key for basic search"""
    try:
        # Try without key first (limited)
        url = "https://gnews.io/api/v4/search"
        params = {"q": query, "lang": "hi", "country": "in", "max": 7}
        import os
        key = os.environ.get("GNEWS_API_KEY", "")
        if key:
            params["apikey"] = key
        else:
            # Use NewsData.io free (no key needed for basic)
            return await _newsdata_fetch(query)

        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(url, params=params)
            if r.status_code == 200:
                d = r.json()
                articles = d.get("articles", [])
                if articles:
                    return _format_articles(articles)
    except: pass
    return None

async def _newsdata_fetch(query: str) -> Optional[str]:
    """NewsData.io free tier"""
    try:
        import os
        key = os.environ.get("NEWSDATA_API_KEY", "")
        if not key:
            return None
        url = "https://newsdata.io/api/1/news"
        params = {"apikey": key, "q": query, "language": "hi,en",
                  "country": "in", "size": 7}
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(url, params=params)
            if r.status_code == 200:
                d = r.json()
                articles = d.get("results", [])
                if articles:
                    lines = []
                    for a in articles[:7]:
                        t = (a.get("title") or "")[:75]
                        src = a.get("source_id", "")
                        pub = (a.get("pubDate") or "")[:10]
                        url_ = a.get("link", "")
                        lines.append(f"• *{t}*\n  📰 {src} | 📅 {pub}\n  🔗 {url_}\n")
                    return "\n".join(lines)
    except: pass
    return None

def _format_articles(articles: list) -> str:
    lines = []
    for a in articles[:7]:
        t   = (a.get("title") or "")[:75]
        src = (a.get("source", {}) or {}).get("name", "")
        pub = (a.get("publishedAt") or "")[:10]
        url = a.get("url", "")
        lines.append(f"• *{t}*\n  📰 {src} | 📅 {pub}\n  🔗 {url}\n")
    return "\n".join(lines) if lines else ""

async def _ai_news(topic: str) -> str:
    """Use G4F to generate news summary when APIs unavailable"""
    prompt = (
        f"India ke baare mein latest real news aur updates batao: '{topic}'. "
        "2024-2025 ki real information. Hindi mein 6-7 bullet points. "
        "Har point mein: headline bold, 1-2 line detail, date agar pata ho. "
        "Sarkari info mein: scheme/post name, benefit, official site. "
        "Markdown use karo."
    )
    try:
        result = await _g4f_query(prompt)
        if result and len(result) > 50:
            return result
    except: pass
    # Last resort static fallback
    return (
        "⚠️ *Live news abhi unavailable*\n\n"
        "Inhe check karo:\n"
        "• 🔗 [sarkariresult.com](https://sarkariresult.com)\n"
        "• 🔗 [rojgarresult.com](https://rojgarresult.com)\n"
        "• 🔗 [india.gov.in](https://india.gov.in)\n"
        "• 🔗 [ndtv.in](https://ndtv.in) — Hindi news\n"
        "• 🔗 [aajtak.in](https://aajtak.in) — Latest khabar"
    )
