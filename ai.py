import asyncio, httpx, logging, random
from datetime import datetime
from typing import Optional

log = logging.getLogger(__name__)
YEAR = datetime.now().year  # 2026

# ── Multiple Free AI Endpoints (fallback chain) ───────────────────────────────
AI_ENDPOINTS = [
    # 1. Pollinations (most reliable)
    {"url":"https://text.pollinations.ai/openai","type":"openai"},
    # 2. Pollinations text (simple)  
    {"url":"https://text.pollinations.ai/","type":"text"},
]

async def _try_pollinations_openai(system: str, user: str) -> Optional[str]:
    try:
        async with httpx.AsyncClient(timeout=25) as c:
            r = await c.post("https://text.pollinations.ai/openai",
                json={"model":"openai","messages":[
                    {"role":"system","content":system},
                    {"role":"user","content":user}
                ],"seed":random.randint(1,9999),"private":True},
                headers={"Content-Type":"application/json"})
            if r.status_code==200:
                d=r.json()
                txt=d.get("choices",[{}])[0].get("message",{}).get("content","")
                if txt and len(txt)>15: return txt.strip()
    except Exception as e:
        log.warning(f"Pollinations OpenAI: {e}")
    return None

async def _try_pollinations_text(prompt: str) -> Optional[str]:
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            encoded = prompt[:800].replace('\n',' ')
            r = await c.get(f"https://text.pollinations.ai/{encoded}",
                headers={"Accept":"text/plain"})
            if r.status_code==200 and len(r.text)>15:
                return r.text.strip()
    except Exception as e:
        log.warning(f"Pollinations text: {e}")
    return None

async def _try_openai_free(system: str, user: str) -> Optional[str]:
    """Try free OpenAI-compatible endpoints"""
    endpoints = [
        "https://api.openai.com/v1/chat/completions",  # skip if no key
    ]
    # Try free proxy
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post("https://api.g4f.in.net/api/chat",
                json={"model":"gpt-4o-mini","messages":[
                    {"role":"system","content":system},
                    {"role":"user","content":user}
                ]},
                headers={"Content-Type":"application/json"})
            if r.status_code==200:
                d=r.json()
                txt=d.get("choices",[{}])[0].get("message",{}).get("content","")
                if txt and len(txt)>15: return txt.strip()
    except Exception as e:
        log.warning(f"G4F proxy: {e}")
    return None

async def _wiki_search(query: str) -> Optional[str]:
    """Wikipedia — Hindi first, then English"""
    for lang in ["hi","en"]:
        try:
            url=f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{query.replace(' ','_')}"
            async with httpx.AsyncClient(timeout=8) as c:
                r=await c.get(url)
                if r.status_code==200:
                    d=r.json()
                    ext=d.get("extract","")
                    if ext and len(ext)>80:
                        return f"*{d.get('title','')}*\n\n{ext[:500]}..."
        except: continue
    return None

# ── Main AI function ──────────────────────────────────────────────────────────
async def ask_ai(question: str, user_data: dict=None, mode: str="study") -> str:
    ud=user_data or {}
    cls=ud.get("class_type",""); subj=ud.get("course",""); goal=ud.get("goal","")

    if mode=="ai":
        system=(
            f"Tum ek expert Study AI Tutor ho Indian students ke liye. Aaj ka year {YEAR} hai. "
            "SIRF padhai, exam, school, college, career ke sawaal ka jawab do. "
            "Off-topic pe refuse karo: 'Main sirf study help kar sakta hoon.' "
            "Hindi/Hinglish mein jawab do. Step-by-step, examples ke saath. "
            "Markdown aur emojis use karo. Clear aur helpful raho."
        )
    else:
        system=(
            f"Tum ek expert Indian teacher ho. {YEAR} mein padha rahe ho. "
            f"Class: {cls}, Subject: {subj}, Goal: {goal}. "
            "Hindi mein clearly padhao. Real life Indian examples do. "
            "Step-by-step samjhao. Markdown aur emojis use karo. "
            "Chote paragraphs mein likho. Formulas, tricks batao."
        )

    # Try multiple AIs in sequence
    result = await _try_pollinations_openai(system, question)
    if result: return result

    result = await _try_openai_free(system, question)
    if result: return result

    result = await _try_pollinations_text(f"{system}\n\nSawal: {question}")
    if result: return result

    # Wikipedia fallback
    result = await _wiki_search(question)
    if result:
        return f"📚 *Wikipedia se jawab:*\n\n{result}\n\n_AI abhi busy hai, Wikipedia se answer mila_"

    return (
        "⚠️ *AI abhi busy hai!*\n\n"
        "Thodi der baad try karo ya 📱 Study App mein jawab dhundho.\n"
        "Wahan Wikipedia + Quiz + Notes sab hai!"
    )

# ── News & Updates — Multiple Sources ────────────────────────────────────────
RSS_FEEDS = {
    "india":  ["https://feeds.feedburner.com/ndtvnews-top-stories",
               "https://timesofindia.indiatimes.com/rssfeedstopstories.cms"],
    "sport":  ["https://feeds.feedburner.com/ndtvsports-latest"],
    "biz":    ["https://feeds.feedburner.com/ndtvprofit-latest"],
    "pol":    ["https://feeds.feedburner.com/ndtvnews-india-news"],
    "edu":    ["https://feeds.feedburner.com/ndtvnews-top-stories"],
}

UPD_PROMPTS = {
    "all":    f"India mein March {YEAR} ke latest sarkari updates: naukri, form, result, yojana. Real info.",
    "jobs":   f"India government sarkari naukri recruitment March {YEAR}. Latest vacancies.",
    "forms":  f"India online government form apply March {YEAR}. Last dates.",
    "results":f"India board exam results March {YEAR}. CBSE UP Bihar latest.",
    "yojana": f"India government yojana scheme March {YEAR}. Benefits aur apply process.",
    "admit":  f"India admit card hall ticket March {YEAR}. Download links.",
    "scholar":f"India scholarship {YEAR} students. Apply kaise karen.",
}

NEWS_PROMPTS = {
    "india": f"India aaj ki taaza khabar March 15 {YEAR}. Latest breaking news.",
    "pol":   f"India politics BJP Congress news March {YEAR}.",
    "sport": f"India cricket IPL sports news March {YEAR}.",
    "biz":   f"India economy business market news March {YEAR}.",
    "edu":   f"India education school college news March {YEAR}.",
}

def _parse_rss(xml: str, max_items: int=7) -> Optional[str]:
    import re
    items=re.findall(r'<item>(.*?)</item>', xml, re.DOTALL)
    if not items: return None
    lines=[]
    for item in items[:max_items]:
        t=re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>',item,re.DOTALL)
        l=re.search(r'<link>(.*?)</link>',item)
        p=re.search(r'<pubDate>(.*?)</pubDate>',item)
        if t:
            title=t.group(1).strip()[:75]
            link=l.group(1).strip() if l else ""
            pub=p.group(1).strip()[:16] if p else ""
            lines.append(f"• *{title}*\n  📅 {pub}\n  🔗 {link}\n")
    return "\n".join(lines) if lines else None

async def _fetch_rss(urls: list) -> Optional[str]:
    for url in urls:
        try:
            async with httpx.AsyncClient(timeout=8,
                headers={"User-Agent":"Mozilla/5.0"}, follow_redirects=True) as c:
                r=await c.get(url)
                if r.status_code==200:
                    result=_parse_rss(r.text)
                    if result: return result
        except: continue
    return None

async def _ai_news(prompt: str) -> str:
    full_prompt=(
        f"Aaj {datetime.now().strftime('%d %B %Y')} ki real latest news/updates batao: {prompt}\n"
        "Hindi mein 6-7 bullet points. Bilkul latest 2026 info. "
        "Har point: headline bold, 1-2 line detail. Markdown use karo."
    )
    system=f"Tum ek helpful Indian news assistant ho. {YEAR} mein ho."

    result=await _try_pollinations_openai(system, full_prompt)
    if result: return result

    result=await _try_openai_free(system, full_prompt)
    if result: return result

    result=await _try_pollinations_text(full_prompt)
    if result: return result

    return (
        f"⚠️ *Live updates abhi unavailable*\n\n"
        "📌 Ye sites check karo:\n"
        "• [sarkariresult.com](https://sarkariresult.com)\n"
        "• [rojgarresult.com](https://rojgarresult.com)\n"
        "• [ndtv.in](https://ndtv.in)\n"
        "• [aajtak.in](https://aajtak.in)\n"
        "• [india.gov.in](https://india.gov.in)"
    )

async def get_updates_text(category: str="all") -> str:
    prompt=UPD_PROMPTS.get(category, UPD_PROMPTS["all"])
    # Sarkari sites se RSS try karo
    feeds=["https://www.sarkariresult.com/feed/",
           "https://feeds.feedburner.com/ndtvnews-top-stories"]
    result=await _fetch_rss(feeds)
    if result: return result
    return await _ai_news(prompt)

async def get_news_text(category: str="india") -> str:
    prompt=NEWS_PROMPTS.get(category, NEWS_PROMPTS["india"])
    feeds=RSS_FEEDS.get(category, RSS_FEEDS["india"])
    result=await _fetch_rss(feeds)
    if result: return result
    return await _ai_news(prompt)
