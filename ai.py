import asyncio, httpx, logging, random, os, feedparser
from datetime import datetime
from typing import Optional
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)
YEAR = datetime.now().year
MONTH = datetime.now().strftime("%B %Y")

# ── API Keys (from environment) ───────────────────────────────────────────────
GEMINI_KEY   = os.environ.get("GEMINI_API_KEY","")
MISTRAL_KEY  = os.environ.get("MISTRAL_API_KEY","")
DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY","")

# ── Daily usage limits per user per API ──────────────────────────────────────
LIMITS = {"gemini": 10, "mistral": 10, "deepseek": 8}

# ══════════════════════════════════════════════════════════════════════════════
# PREMIUM APIs (Gemini, Mistral, DeepSeek) — tried first if key + limit ok
# ══════════════════════════════════════════════════════════════════════════════

async def _gemini(system: str, user: str) -> Optional[str]:
    if not GEMINI_KEY: return None
    try:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
        payload = {"contents":[{"parts":[{"text":f"{system}\n\n{user}"}]}],
                   "generationConfig":{"temperature":0.7,"maxOutputTokens":800}}
        async with httpx.AsyncClient(timeout=25) as c:
            r = await c.post(url, json=payload)
            if r.status_code == 200:
                txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                if txt and len(txt) > 15: return txt.strip()
    except Exception as e: log.debug(f"Gemini: {e}")
    return None

async def _mistral(system: str, user: str) -> Optional[str]:
    if not MISTRAL_KEY: return None
    try:
        async with httpx.AsyncClient(timeout=25) as c:
            r = await c.post("https://api.mistral.ai/v1/chat/completions",
                json={"model":"mistral-small-latest","messages":[
                    {"role":"system","content":system},
                    {"role":"user","content":user}]},
                headers={"Authorization":f"Bearer {MISTRAL_KEY}","Content-Type":"application/json"})
            if r.status_code == 200:
                txt = r.json()["choices"][0]["message"]["content"]
                if txt and len(txt) > 15: return txt.strip()
    except Exception as e: log.debug(f"Mistral: {e}")
    return None

async def _deepseek(system: str, user: str) -> Optional[str]:
    if not DEEPSEEK_KEY: return None
    try:
        async with httpx.AsyncClient(timeout=25) as c:
            r = await c.post("https://api.deepseek.com/chat/completions",
                json={"model":"deepseek-chat","messages":[
                    {"role":"system","content":system},
                    {"role":"user","content":user}]},
                headers={"Authorization":f"Bearer {DEEPSEEK_KEY}","Content-Type":"application/json"})
            if r.status_code == 200:
                txt = r.json()["choices"][0]["message"]["content"]
                if txt and len(txt) > 15: return txt.strip()
    except Exception as e: log.debug(f"DeepSeek: {e}")
    return None

# ── Free fallback AIs ─────────────────────────────────────────────────────────
async def _pollinations(system: str, user: str) -> Optional[str]:
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post("https://text.pollinations.ai/openai",
                json={"model":"openai","messages":[
                    {"role":"system","content":system},
                    {"role":"user","content":user}
                ],"seed":random.randint(1,9999),"private":True},
                headers={"Content-Type":"application/json"})
            if r.status_code == 200:
                txt = r.json().get("choices",[{}])[0].get("message",{}).get("content","")
                if txt and len(txt) > 15: return txt.strip()
    except Exception as e: log.debug(f"Poll: {e}")
    return None

async def _g4f(prompt: str) -> Optional[str]:
    def _sync():
        try:
            import g4f
            r = g4f.ChatCompletion.create(model=g4f.models.gpt_4,
                messages=[{"role":"user","content":prompt}])
            return r if isinstance(r,str) else str(r)
        except:
            import g4f
            r = g4f.ChatCompletion.create(model=g4f.models.default,
                messages=[{"role":"user","content":prompt}])
            return r if isinstance(r,str) else str(r)
    try:
        loop = asyncio.get_event_loop()
        r = await asyncio.wait_for(loop.run_in_executor(None,_sync),timeout=25)
        if r and len(r) > 15: return r.strip()
    except Exception as e: log.debug(f"G4F: {e}")
    return None

async def _ddg(query: str) -> Optional[str]:
    try:
        from duckduckgo_search import DDGS
        loop = asyncio.get_event_loop()
        def _sync():
            with DDGS() as d: return d.chat(query, model="claude-3-haiku")
        r = await asyncio.wait_for(loop.run_in_executor(None,_sync), timeout=20)
        if r and isinstance(r,str) and len(r) > 15: return r.strip()
    except Exception as e: log.debug(f"DDG: {e}")
    return None

async def _poll_txt(prompt: str) -> Optional[str]:
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(
                f"https://text.pollinations.ai/{prompt[:600].replace(chr(10),' ')}",
                headers={"Accept":"text/plain"})
            if r.status_code == 200 and len(r.text) > 15: return r.text.strip()
    except: pass
    return None

# ══════════════════════════════════════════════════════════════════════════════
# MAIN AI — tries premium APIs first, then free fallbacks
# ══════════════════════════════════════════════════════════════════════════════
async def ask_ai(question: str, user_data: dict = None, mode: str = "study",
                 api_usage: dict = None) -> tuple[str, str]:
    """Returns (answer, api_used)"""
    ud = user_data or {}
    cls = ud.get("class_type",""); subj = ud.get("course",""); goal = ud.get("goal","")
    lang = ud.get("language","hi")
    usage = api_usage or {}

    if lang == "en":
        if mode == "ai":
            system = f"Expert Study AI Tutor for Indian students. Year:{YEAR}. Answer ONLY study/exam/career questions. Refuse off-topic politely. Step-by-step with examples. Markdown."
        else:
            system = f"Expert Indian teacher. {YEAR}. Class:{cls}, Subject:{subj}. Teach clearly with real examples. Step-by-step. Markdown."
    else:
        if mode == "ai":
            system = f"Expert Study AI Tutor Indian students ke liye. {YEAR}. SIRF padhai/exam/career. Off-topic refuse karo. Hindi/Hinglish. Step-by-step. Markdown."
        else:
            system = f"Expert Indian teacher. {YEAR}. Class:{cls}, Subject:{subj}. Hindi mein clearly padhao. Examples. Step-by-step. Markdown."

    full = f"{system}\n\nSawal: {question}"

    # 1. Premium APIs (if key available and limit not exceeded)
    if GEMINI_KEY and usage.get("gemini",0) < LIMITS["gemini"]:
        r = await _gemini(system, question)
        if r: return r, "gemini"

    if MISTRAL_KEY and usage.get("mistral",0) < LIMITS["mistral"]:
        r = await _mistral(system, question)
        if r: return r, "mistral"

    if DEEPSEEK_KEY and usage.get("deepseek",0) < LIMITS["deepseek"]:
        r = await _deepseek(system, question)
        if r: return r, "deepseek"

    # 2. Free fallbacks (unlimited)
    for fn, name in [
        (lambda: _pollinations(system, question), "pollinations"),
        (lambda: _g4f(full), "g4f"),
        (lambda: _ddg(question), "duckduckgo"),
        (lambda: _poll_txt(full), "pollinations_txt"),
    ]:
        try:
            r = await fn()
            if r and len(r) > 20: return r, name
        except: continue

    return ("⚠️ Sabhi AI sources busy hain! Thodi der baad try karo.","none")

async def ask_ai_simple(question: str, user_data: dict = None, mode: str = "study") -> str:
    """Simple wrapper — returns just the text"""
    result, _ = await ask_ai(question, user_data, mode)
    return result

# ══════════════════════════════════════════════════════════════════════════════
# OCR — Image to Text
# ══════════════════════════════════════════════════════════════════════════════
async def image_to_text(image_path: str) -> str:
    """Extract text from image using pytesseract"""
    try:
        import pytesseract
        from PIL import Image
        loop = asyncio.get_event_loop()
        def _ocr():
            img = Image.open(image_path)
            # Try Hindi + English
            text = pytesseract.image_to_string(img, lang='hin+eng')
            if not text.strip():
                text = pytesseract.image_to_string(img, lang='eng')
            return text.strip()
        text = await loop.run_in_executor(None, _ocr)
        return text if text else "❌ Image mein text nahi mila ya clearly nahi dikh raha."
    except Exception as e:
        log.warning(f"OCR: {e}")
        return "❌ Image processing mein dikkat aayi. Clear image bhejo."

# ══════════════════════════════════════════════════════════════════════════════
# PDF Generator
# ══════════════════════════════════════════════════════════════════════════════
async def generate_pdf(title: str, content: str, filename: str = "notes.pdf") -> str:
    """Generate PDF from text content"""
    try:
        from fpdf import FPDF
        import re

        loop = asyncio.get_event_loop()
        def _make_pdf():
            pdf = FPDF()
            pdf.add_page()
            pdf.set_auto_page_break(auto=True, margin=15)
            # Title
            pdf.set_font("Helvetica","B",16)
            pdf.cell(0,12,title[:60],align='C',new_x="LMARGIN",new_y="NEXT")
            pdf.set_font("Helvetica","",9)
            pdf.cell(0,6,f"IndiaStudyAI | {datetime.now().strftime('%d %B %Y')}",
                     align='C',new_x="LMARGIN",new_y="NEXT")
            pdf.ln(4)
            # Content — clean markdown
            clean = re.sub(r'\*\*(.*?)\*\*',r'\1',content)
            clean = re.sub(r'\*(.*?)\*',r'\1',clean)
            clean = re.sub(r'#{1,3}\s','',clean)
            clean = re.sub(r'`([^`]+)`',r'\1',clean)
            # Remove non-latin characters for basic FPDF
            clean = clean.encode('ascii','replace').decode('ascii')
            pdf.set_font("Helvetica","",11)
            for line in clean.split('\n'):
                if line.strip():
                    if line.startswith('•') or line.startswith('-'):
                        pdf.set_x(15)
                        pdf.multi_cell(0,6,f"  {line.strip()}")
                    else:
                        pdf.multi_cell(0,6,line.strip())
                else:
                    pdf.ln(3)
            path = f"/tmp/{filename}"
            pdf.output(path)
            return path

        path = await loop.run_in_executor(None, _make_pdf)
        return path
    except Exception as e:
        log.error(f"PDF: {e}")
        return ""

# ══════════════════════════════════════════════════════════════════════════════
# NEWS & UPDATES — Real scraping + RSS + Google News + Cache support
# ══════════════════════════════════════════════════════════════════════════════
RSS_SARKARI = [
    "https://www.sarkariresult.com/feed/",
    "https://www.indgovtjobs.in/feeds/posts/default",
    "https://www.freejobalert.com/feed/",
]
RSS_NEWS = {
    "india": ["https://feeds.feedburner.com/ndtvnews-top-stories",
              "https://timesofindia.indiatimes.com/rssfeedstopstories.cms"],
    "pol":   ["https://feeds.feedburner.com/ndtvnews-india-news"],
    "sport": ["https://feeds.feedburner.com/ndtvsports-latest"],
    "biz":   ["https://feeds.feedburner.com/ndtvprofit-latest",
              "https://economictimes.indiatimes.com/rssfeedsdefault.cms"],
    "edu":   ["https://timesofindia.indiatimes.com/rssfeeds/913168846.cms"],
}
GOOGLE_NEWS = {
    "all":     f"sarkari+naukri+result+yojana+India+{YEAR}",
    "jobs":    f"government+jobs+recruitment+India+{YEAR}",
    "forms":   f"sarkari+form+apply+online+India+{YEAR}",
    "results": f"board+exam+result+{YEAR}+CBSE+India",
    "yojana":  f"government+yojana+scheme+India+{YEAR}",
    "admit":   f"admit+card+hall+ticket+India+{YEAR}",
    "scholar": f"scholarship+India+students+{YEAR}",
    "india":   f"India+breaking+news+today+{YEAR}",
    "pol":     f"India+politics+BJP+Congress+{YEAR}",
    "sport":   f"India+cricket+IPL+sports+{YEAR}",
    "biz":     f"India+economy+business+{YEAR}",
    "edu":     f"India+education+CBSE+JEE+NEET+{YEAR}",
}

def _parse_feed(url: str, max_items: int = 8) -> Optional[str]:
    try:
        feed = feedparser.parse(url)
        if not feed.entries: return None
        lines = []
        for e in feed.entries[:max_items]:
            title = e.get("title","")[:80]
            link  = e.get("link","")
            pub   = e.get("published","")[:16] if e.get("published") else ""
            if title:
                lines.append(f"• *{title}*\n  📅 {pub}\n  🔗 {link}\n")
        return "\n".join(lines) if lines else None
    except: return None

async def _scrape_sarkari() -> Optional[str]:
    try:
        async with httpx.AsyncClient(timeout=10,
            headers={"User-Agent":"Mozilla/5.0"}) as c:
            r = await c.get("https://www.sarkariresult.com/latestjob/")
            if r.status_code == 200:
                soup = BeautifulSoup(r.text,"lxml")
                links = []
                for a in soup.find_all("a",href=True)[:20]:
                    txt = a.get_text(strip=True)[:70]
                    href = a.get("href","")
                    if txt and len(txt) > 10 and ("notification" in href.lower()
                        or "recruitment" in txt.lower() or "result" in txt.lower()):
                        full = href if href.startswith("http") else f"https://www.sarkariresult.com{href}"
                        links.append(f"• *{txt}*\n  🔗 {full}\n")
                if links:
                    return f"📋 *SarkariResult.com — Live {YEAR}*\n\n" + "\n".join(links[:7])
    except: pass
    return None

async def _fetch_rss_parallel(urls: list) -> Optional[str]:
    loop = asyncio.get_event_loop()
    tasks = [loop.run_in_executor(None, _parse_feed, url) for url in urls]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    for r in results:
        if isinstance(r, str) and len(r) > 50: return r
    return None

async def _google_news_rss(query: str) -> Optional[str]:
    url = f"https://news.google.com/rss/search?q={query}&hl=hi&gl=IN&ceid=IN:hi"
    loop = asyncio.get_event_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(None, _parse_feed, url, 8), timeout=10)
    except: return None

async def fetch_updates(category: str = "all") -> str:
    """Fetch sarkari updates — scrape → RSS → Google News → AI"""
    if category in ("all","jobs"):
        r = await _scrape_sarkari()
        if r: return r
    gn = await _google_news_rss(GOOGLE_NEWS.get(category, GOOGLE_NEWS["all"]))
    if gn: return f"📢 *{category.upper()} — {MONTH}*\n\n{gn}"
    rss = await _fetch_rss_parallel(RSS_SARKARI[:3])
    if rss: return f"📢 *Sarkari Updates — {MONTH}*\n\n{rss}"
    prompts = {
        "all":f"India {MONTH} latest sarkari: naukri form result yojana. 7 bullets. Bold title detail website.",
        "jobs":f"India govt jobs recruitment {MONTH}. 7 vacancies. Post name, last date, website.",
        "forms":f"India online govt forms {MONTH}. 7 active. Last date, apply link.",
        "results":f"India board results {MONTH}. CBSE UP Bihar. 7 items.",
        "yojana":f"India PM Modi yojana {MONTH}. 7 schemes. Benefit, apply kaise.",
        "admit":f"India admit cards {MONTH}. 7 upcoming. Exam, date, download.",
        "scholar":f"India scholarships {MONTH}. 7 active. Name, amount, apply.",
    }
    return await ask_ai_simple(prompts.get(category,prompts["all"]),mode="news")

async def fetch_news(category: str = "india") -> str:
    """Fetch news — RSS → Google News → AI"""
    feeds = RSS_NEWS.get(category, RSS_NEWS["india"])
    rss = await _fetch_rss_parallel(feeds[:3])
    if rss:
        labels = {"india":"🇮🇳 India","pol":"🏛️ Rajniti","sport":"🏏 Sports","biz":"💼 Business","edu":"📚 Education"}
        return f"{labels.get(category,'📰')} *{MONTH}*\n\n{rss}"
    gn = await _google_news_rss(GOOGLE_NEWS.get(category, GOOGLE_NEWS["india"]))
    if gn: return f"📰 *{category} — {MONTH}*\n\n{gn}"
    prompts = {
        "india":f"India latest news {MONTH}. 7 bullets Hindi.",
        "pol":f"India politics {MONTH}. 7 items.",
        "sport":f"India cricket IPL {MONTH}. 7 items.",
        "biz":f"India economy {MONTH}. 7 items.",
        "edu":f"India education CBSE JEE {MONTH}. 7 items.",
    }
    return await ask_ai_simple(prompts.get(category,prompts["india"]),mode="news")

# ── Daily content ─────────────────────────────────────────────────────────────
async def get_daily_quote() -> str:
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get("https://api.quotable.io/random?tags=education,success")
            if r.status_code == 200:
                d = r.json()
                return f'💬 *"{d["content"]}"*\n— _{d["author"]}_'
    except: pass
    quotes=[("सपने वो नहीं जो सोते समय देखें, सपने वो हैं जो सोने न दें।","APJ Abdul Kalam"),
            ("शिक्षा सबसे शक्तिशाली हथियार है।","Nelson Mandela"),
            ("पढ़ो, लिखो, आगे बढ़ो।","BR Ambedkar"),
            ("हर expert कभी beginner था।","Anonymous"),]
    q=random.choice(quotes)
    return f'💬 *"{q[0]}"*\n— _{q[1]}_'

async def get_daily_fact() -> str:
    facts=["🇮🇳 India mein 22 officially recognized languages hain!",
           "🔬 Human body mein 37 trillion cells hote hain!",
           "🚀 ISRO ne 104 satellites ek saath launch kiye — world record!",
           "🏏 India ne 1983 aur 2011 mein Cricket World Cup jeeta!",
           "💡 India ne zero aur chess duniya ko diya!",
           "📱 India mein 75 crore+ smartphone users hain!",]
    return random.choice(facts)

async def get_morning_message(name: str, streak: int) -> str:
    today = datetime.now().strftime("%d %B %Y, %A")
    quote = await get_daily_quote()
    fact  = await get_daily_fact()
    s_txt = f"🔥 *{streak} din streak!* Todna mat!" if streak > 1 else "🌱 Aaj se streak shuru karo!"
    return (f"🌅 *Good Morning, {name}!*\n📅 {today}\n\n{quote}\n\n{fact}\n\n{s_txt}\n\n"
            "📚 Aaj bhi padhai karo — greatness awaits! 💪")
