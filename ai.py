import httpx, logging, asyncio
from typing import Optional

log = logging.getLogger(__name__)

# ── FREE AI — Pollinations.ai (No API key, No install needed) ─────────────────
# 100% free, no rate limit for basic use, works on Koyeb

POLLINATIONS_URL = "https://text.pollinations.ai/openai"

async def ask_ai(question: str, user_data: dict = None, mode: str = "study") -> str:
    ud = user_data or {}
    cls  = ud.get("class_type", "")
    subj = ud.get("course", "")
    goal = ud.get("goal", "")

    if mode == "ai":
        system = (
            "Tum ek strict Study AI Tutor ho Indian students ke liye. "
            "SIRF padhai, exam, school/college, career se related sawaal ka jawab do. "
            "Agar koi off-topic pooche to politely refuse karo: "
            "'Main sirf study topics mein help kar sakta hoon.' "
            "Hindi/Hinglish mein jawab do. Clear, step-by-step, examples ke saath. "
            "Emojis aur markdown use karo."
        )
    else:
        system = (
            f"Tum ek expert Indian teacher ho. "
            f"Class: {cls}, Subject: {subj}, Goal: {goal}. "
            "Hindi mein clear aur simple tarike se padhao. "
            "Real Indian examples do. Step-by-step samjhao. "
            "Markdown aur emojis use karo."
        )

    # Try Pollinations.ai first (most reliable, no key needed)
    try:
        result = await _pollinations_query(system, question)
        if result and len(result) > 20:
            return result
    except Exception as e:
        log.warning(f"Pollinations failed: {e}")

    # Fallback: Wikipedia
    try:
        wiki = await _wiki_search(question)
        if wiki:
            return f"📚 *Wikipedia se:*\n\n{wiki}\n\n_AI temporarily unavailable_"
    except Exception as e:
        log.warning(f"Wiki fallback failed: {e}")

    return "⚠️ Abhi jawab nahi de pa raha. Thodi der baad try karo!"


async def _pollinations_query(system: str, question: str) -> str:
    """Pollinations.ai — completely free, no API key needed"""
    payload = {
        "model": "openai",
        "messages": [
            {"role": "system", "content": system},
            {"role": "user",   "content": question}
        ],
        "seed": 42,
        "private": True
    }
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(POLLINATIONS_URL, json=payload,
                         headers={"Content-Type": "application/json"})
        if r.status_code == 200:
            d = r.json()
            return d["choices"][0]["message"]["content"].strip()
        raise Exception(f"Status {r.status_code}: {r.text[:200]}")


async def _wiki_search(query: str) -> Optional[str]:
    """Wikipedia API — free, no key"""
    urls = [
        f"https://hi.wikipedia.org/api/rest_v1/page/summary/{query.replace(' ','_')}",
        f"https://en.wikipedia.org/api/rest_v1/page/summary/{query.replace(' ','_')}",
    ]
    async with httpx.AsyncClient(timeout=10) as c:
        for url in urls:
            try:
                r = await c.get(url)
                if r.status_code == 200:
                    d = r.json()
                    extract = d.get("extract", "")
                    title   = d.get("title", "")
                    if extract and len(extract) > 80:
                        return f"*{title}*\n\n{extract[:600]}..."
            except:
                continue
    return None


# ── News & Sarkari Updates ────────────────────────────────────────────────────
UPD_PROMPTS = {
    "all":     "India 2025 mein latest sarkari naukri, recruitment, form, result, yojana ki real updates do.",
    "jobs":    "India 2025 mein latest government sarkari naukri aur recruitment vacancy ki list do.",
    "forms":   "India 2025 mein abhi kaunse government online forms apply ho rahe hain — list do.",
    "results": "India 2025 mein latest board exam aur sarkari exam results ki list do.",
    "yojana":  "India 2025 mein latest government yojana aur schemes ki list do — benefit aur apply kaise.",
    "admit":   "India 2025 mein latest admit card aur hall ticket download karne wale exams ki list do.",
    "scholar": "India 2025 mein students ke liye latest scholarship schemes ki list do.",
}

NEWS_PROMPTS = {
    "india":  "Aaj ki India ki top 7 latest news Hindi mein do — real events 2025.",
    "pol":    "India ki latest politics news 2025 — BJP, Congress, elections.",
    "sport":  "India ki latest sports news 2025 — cricket, IPL, Olympics.",
    "biz":    "India ki latest business aur economy news 2025.",
    "edu":    "India ki latest education news 2025 — CBSE, board exams, colleges.",
    "tech":   "India ki latest technology aur startup news 2025.",
}

async def get_updates_text(category: str = "all") -> str:
    prompt = UPD_PROMPTS.get(category, UPD_PROMPTS["all"])
    full = (
        f"{prompt}\n\n"
        "Hindi mein 7 bullet points mein do. "
        "Har point mein: bold title, 1-2 line detail, official website agar ho. "
        "Markdown use karo. Real 2025 info do."
    )
    try:
        result = await _pollinations_query("Tum ek India sarkari updates expert ho.", full)
        if result and len(result) > 50:
            return result
    except Exception as e:
        log.warning(f"Updates error: {e}")
    return _fallback_links()

async def get_news_text(category: str = "india") -> str:
    prompt = NEWS_PROMPTS.get(category, NEWS_PROMPTS["india"])
    full = (
        f"{prompt}\n\n"
        "Hindi mein 7 news items do. "
        "Har item: *bold headline*, 1-2 line detail, date. "
        "Markdown use karo."
    )
    try:
        # Try RSS feed first
        rss = await _fetch_rss(category)
        if rss:
            return rss
        # Fallback to AI
        result = await _pollinations_query("Tum ek Hindi news reporter ho.", full)
        if result and len(result) > 50:
            return result
    except Exception as e:
        log.warning(f"News error: {e}")
    return _fallback_links()

async def _fetch_rss(category: str) -> Optional[str]:
    """Free RSS feeds — no API key needed"""
    RSS = {
        "india": "https://feeds.feedburner.com/ndtvnews-top-stories",
        "sport": "https://feeds.feedburner.com/ndtvsports-latest",
        "tech":  "https://feeds.feedburner.com/gadgets360-latest",
    }
    url = RSS.get(category)
    if not url:
        return None
    try:
        proxy = f"https://api.allorigins.win/get?url={httpx.URL(url)}"
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(proxy)
            if r.status_code != 200:
                return None
            import xml.etree.ElementTree as ET
            content = r.json().get("contents", "")
            root = ET.fromstring(content)
            items = root.findall(".//item")[:7]
            if not items:
                return None
            lines = []
            for item in items:
                title = item.findtext("title", "").strip()
                link  = item.findtext("link", "").strip()
                pub   = item.findtext("pubDate", "")[:16]
                lines.append(f"• *{title}*\n  📅 {pub}\n  🔗 {link}\n")
            return "\n".join(lines)
    except:
        return None

def _fallback_links() -> str:
    return (
        "⚠️ *Live updates abhi unavailable*\n\n"
        "Inhe check karo:\n"
        "• 🔗 [sarkariresult.com](https://sarkariresult.com)\n"
        "• 🔗 [rojgarresult.com](https://rojgarresult.com)\n"
        "• 🔗 [india.gov.in](https://india.gov.in)\n"
        "• 🔗 [ndtv.in](https://ndtv.in)\n"
        "• 🔗 [aajtak.in](https://aajtak.in)"
    )
