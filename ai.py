import asyncio, httpx, logging, random
from datetime import datetime
from typing import Optional

log=logging.getLogger(__name__)
YEAR=datetime.now().year

# ── G4F ──────────────────────────────────────────────────────────────────────
def _g4f_sync(prompt:str)->str:
    try:
        import g4f
        r=g4f.ChatCompletion.create(model=g4f.models.gpt_4,messages=[{"role":"user","content":prompt}])
        return r if isinstance(r,str) else str(r)
    except:
        try:
            import g4f
            r=g4f.ChatCompletion.create(model=g4f.models.default,messages=[{"role":"user","content":prompt}])
            return r if isinstance(r,str) else str(r)
        except Exception as e: raise Exception(f"G4F: {e}")

async def _g4f(prompt:str)->Optional[str]:
    try:
        loop=asyncio.get_event_loop()
        r=await asyncio.wait_for(loop.run_in_executor(None,_g4f_sync,prompt),timeout=25)
        if r and len(r)>10: return r.strip()
    except Exception as e: log.warning(f"G4F: {e}")
    return None

async def _poll(system:str,user:str)->Optional[str]:
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r=await c.post("https://text.pollinations.ai/openai",
                json={"model":"openai","messages":[{"role":"system","content":system},{"role":"user","content":user}],"seed":random.randint(1,9999),"private":True},
                headers={"Content-Type":"application/json"})
            if r.status_code==200:
                txt=r.json().get("choices",[{}])[0].get("message",{}).get("content","")
                if txt and len(txt)>10: return txt.strip()
    except Exception as e: log.warning(f"Poll: {e}")
    return None

async def _poll_txt(prompt:str)->Optional[str]:
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r=await c.get(f"https://text.pollinations.ai/{prompt[:600].replace(chr(10),' ')}",headers={"Accept":"text/plain"})
            if r.status_code==200 and len(r.text)>10: return r.text.strip()
    except: pass
    return None

async def _wiki(q:str)->Optional[str]:
    for lang in ["hi","en"]:
        try:
            async with httpx.AsyncClient(timeout=8) as c:
                r=await c.get(f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{q.replace(' ','_')}")
                if r.status_code==200:
                    d=r.json(); ext=d.get("extract","")
                    if ext and len(ext)>80: return f"*{d.get('title','')}*\n\n{ext[:500]}..."
        except: continue
    return None

async def _ddg_search(query:str)->Optional[str]:
    """DuckDuckGo free search"""
    try:
        from duckduckgo_search import DDGS
        loop=asyncio.get_event_loop()
        def _search():
            with DDGS() as d:
                results=list(d.text(query+" site:ndtv.com OR site:thehindu.com OR site:sarkariresult.com",max_results=5))
                return results
        results=await asyncio.wait_for(loop.run_in_executor(None,_search),timeout=10)
        if results:
            lines=[f"• *{r['title']}*\n  {r['body'][:120]}...\n  🔗 {r['href']}" for r in results[:5]]
            return "\n\n".join(lines)
    except Exception as e: log.warning(f"DDG: {e}")
    return None

# ── Daily Content APIs ────────────────────────────────────────────────────────
async def get_daily_quote()->str:
    """Free quote API"""
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r=await c.get("https://api.quotable.io/random?tags=inspirational,education")
            if r.status_code==200:
                d=r.json()
                return f'💬 *"{d["content"]}"*\n— _{d["author"]}_'
    except: pass
    # Fallback quotes
    quotes=[
        ('सपने वो नहीं जो आप सोते समय देखते हैं, सपने वो हैं जो आपको सोने नहीं देते।','APJ Abdul Kalam'),
        ('शिक्षा सबसे शक्तिशाली हथियार है जिसे आप दुनिया बदलने के लिए उपयोग कर सकते हैं।','Nelson Mandela'),
        ('कल की असफलता आज की सफलता की नींव है।','Anonymous'),
        ('पढ़ो, लिखो, आगे बढ़ो — यही जीवन का मंत्र है।','BR Ambedkar'),
        ('जो व्यक्ति सीखना बंद कर देता है वह बूढ़ा हो जाता है।','Henry Ford'),
    ]
    q=random.choice(quotes)
    return f'💬 *"{q[0]}"*\n— _{q[1]}_'

async def get_daily_fact()->str:
    """Daily interesting fact"""
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r=await c.get("http://numbersapi.com/random/trivia")
            if r.status_code==200 and len(r.text)>20:
                return f"🔢 *Number Fact:* {r.text}"
    except: pass
    facts=[
        "🌍 India mein 22 officially recognized languages hain!",
        "🔬 Human body mein 37 trillion cells hote hain!",
        "⚡ Bijli ki speed 299,792 km/second hai!",
        "🧠 Insaan ka brain 20% oxygen use karta hai!",
        "📚 India world ka sabse bada youth population wala desh hai!",
        "🚀 ISRO ne 104 satellites ek saath launch kiye the — world record!",
        "🌊 Pacific Ocean duniya ka sabse bada ocean hai!",
        "🦁 India mein duniya ke 70% tigers hain!",
    ]
    return random.choice(facts)

async def get_morning_message(name:str,streak:int)->str:
    today=datetime.now().strftime("%d %B %Y")
    quote=await get_daily_quote()
    fact=await get_daily_fact()
    streak_msg=f"🔥 Streak: *{streak} din!* Khatam mat karna!" if streak>1 else "🌱 Aaj se streak shuru karo!"
    return (
        f"🌅 *Good Morning, {name}!*\n"
        f"📅 {today}\n\n"
        f"{quote}\n\n"
        f"{fact}\n\n"
        f"{streak_msg}\n\n"
        f"📚 Aaj bhi padhai karo — greatness awaits! 🚀"
    )

# ── Main AI ───────────────────────────────────────────────────────────────────
async def ask_ai(question:str,user_data:dict=None,mode:str="study")->str:
    ud=user_data or {}
    cls=ud.get("class_type",""); subj=ud.get("course",""); goal=ud.get("goal","")
    if mode=="ai":
        system=(f"Expert Study AI Tutor for Indian students. Year:{YEAR}. "
                "SIRF padhai/exam/career topics answer karo. "
                "Off-topic pe: 'Main sirf study mein help kar sakta hoon.' "
                "Hindi/Hinglish mein. Step-by-step. Markdown+emojis.")
    else:
        system=(f"Expert Indian teacher. {YEAR}. Class:{cls}, Subject:{subj}, Goal:{goal}. "
                "Hindi mein clearly padhao. Real examples. Step-by-step. Markdown+emojis.")
    full=f"{system}\n\nSawal: {question}"
    r=await _g4f(full)
    if r: return r
    r=await _poll(system,question)
    if r: return r
    r=await _poll_txt(full)
    if r: return r
    wiki=await _wiki(question)
    if wiki: return f"📚 *Wikipedia se:*\n\n{wiki}\n\n_AI busy hai, Wikipedia se jawab mila_"
    return "⚠️ AI abhi busy hai. Thodi der baad try karo!"

# ── News & Updates ────────────────────────────────────────────────────────────
UPD_Q={
    "all":f"India March {YEAR} latest sarkari updates naukri form result yojana. Hindi 6 bullets. Bold titles. Real {YEAR} info.",
    "jobs":f"India sarkari naukri recruitment March {YEAR} latest vacancies. Hindi bullets.",
    "forms":f"India online government form apply March {YEAR} last dates. Hindi bullets.",
    "results":f"India board exam results March {YEAR} CBSE UP Bihar. Hindi bullets.",
    "yojana":f"India PM Modi government yojana schemes March {YEAR} benefits. Hindi bullets.",
    "admit":f"India admit card hall ticket March {YEAR}. Hindi bullets.",
    "scholar":f"India scholarship {YEAR} students apply. Hindi bullets.",
}
NEWS_Q={
    "india":f"India latest breaking news March 15 {YEAR}. Hindi 6 bullets.",
    "pol":f"India politics BJP Congress March {YEAR}. Hindi bullets.",
    "sport":f"India cricket IPL sports March {YEAR}. Hindi bullets.",
    "biz":f"India economy business March {YEAR}. Hindi bullets.",
    "edu":f"India education CBSE JEE NEET March {YEAR}. Hindi bullets.",
}
RSS_FEEDS={
    "india":["https://feeds.feedburner.com/ndtvnews-top-stories","https://timesofindia.indiatimes.com/rssfeedstopstories.cms"],
    "sport":["https://feeds.feedburner.com/ndtvsports-latest"],
    "biz":["https://feeds.feedburner.com/ndtvprofit-latest"],
    "pol":["https://feeds.feedburner.com/ndtvnews-india-news"],
    "edu":["https://feeds.feedburner.com/ndtvnews-top-stories"],
}
def _parse_rss(xml:str)->Optional[str]:
    import re
    items=re.findall(r'<item>(.*?)</item>',xml,re.DOTALL)
    if not items: return None
    lines=[]
    for item in items[:7]:
        t=re.search(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>',item,re.DOTALL)
        l=re.search(r'<link>(.*?)</link>',item)
        p=re.search(r'<pubDate>(.*?)</pubDate>',item)
        if t:
            lines.append(f"• *{t.group(1).strip()[:75]}*\n  📅 {p.group(1).strip()[:16] if p else ''}\n  🔗 {l.group(1).strip() if l else ''}\n")
    return "\n".join(lines) if lines else None

async def _fetch_rss(urls:list)->Optional[str]:
    for url in urls:
        try:
            async with httpx.AsyncClient(timeout=8,headers={"User-Agent":"Mozilla/5.0"},follow_redirects=True) as c:
                r=await c.get(url)
                if r.status_code==200:
                    result=_parse_rss(r.text)
                    if result: return result
        except: continue
    return None

async def _ai_news(prompt:str)->str:
    r=await _g4f(prompt)
    if r: return r
    r=await _poll(f"Indian news assistant. Latest {YEAR} real info. Hindi bullets.",prompt)
    if r: return r
    r=await _ddg_search(prompt[:100])
    if r: return r
    r=await _poll_txt(prompt)
    if r: return r
    return ("⚠️ *Live updates unavailable*\n\n📌 Check karo:\n"
            "• [sarkariresult.com](https://sarkariresult.com)\n"
            "• [rojgarresult.com](https://rojgarresult.com)\n"
            "• [ndtv.in](https://ndtv.in)\n• [aajtak.in](https://aajtak.in)")

async def get_updates_text(category:str="all")->str:
    prompt=UPD_Q.get(category,UPD_Q["all"])
    r=await _fetch_rss(["https://www.sarkariresult.com/feed/","https://feeds.feedburner.com/ndtvnews-top-stories"])
    if r: return r
    r=await _ddg_search(f"sarkari naukri result form {YEAR} India latest")
    if r: return r
    return await _ai_news(prompt)

async def get_news_text(category:str="india")->str:
    prompt=NEWS_PROMPTS=NEWS_Q.get(category,NEWS_Q["india"])
    r=await _fetch_rss(RSS_FEEDS.get(category,RSS_FEEDS["india"]))
    if r: return r
    r=await _ddg_search(f"India {category} news today {YEAR}")
    if r: return r
    return await _ai_news(prompt)
