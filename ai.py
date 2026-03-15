import asyncio, httpx, logging, random, re
from datetime import datetime
from typing import Optional
import requests
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)
YEAR = datetime.now().year

# ══════════════════════════════════════════════════════════════════════════════
# 8 FREE AI SOURCES — Chain fallback, no API key needed
# ══════════════════════════════════════════════════════════════════════════════

async def _ai1_pollinations_openai(system: str, user: str) -> Optional[str]:
    """Source 1: Pollinations OpenAI endpoint"""
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post("https://text.pollinations.ai/openai",
                json={"model":"openai","messages":[{"role":"system","content":system},
                    {"role":"user","content":user}],"seed":random.randint(1,9999),"private":True},
                headers={"Content-Type":"application/json"})
            if r.status_code == 200:
                txt = r.json().get("choices",[{}])[0].get("message",{}).get("content","")
                if txt and len(txt) > 15: return txt.strip()
    except Exception as e: log.debug(f"AI1: {e}")
    return None

async def _ai2_pollinations_text(prompt: str) -> Optional[str]:
    """Source 2: Pollinations simple text"""
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(f"https://text.pollinations.ai/{prompt[:600].replace(chr(10),' ')}",
                headers={"Accept":"text/plain"})
            if r.status_code == 200 and len(r.text) > 15: return r.text.strip()
    except Exception as e: log.debug(f"AI2: {e}")
    return None

async def _ai3_g4f(prompt: str) -> Optional[str]:
    """Source 3: G4F library"""
    def _sync():
        try:
            import g4f
            r = g4f.ChatCompletion.create(model=g4f.models.gpt_4,
                messages=[{"role":"user","content":prompt}])
            return r if isinstance(r,str) else str(r)
        except:
            try:
                import g4f
                r = g4f.ChatCompletion.create(model=g4f.models.default,
                    messages=[{"role":"user","content":prompt}])
                return r if isinstance(r,str) else str(r)
            except Exception as e: raise e
    try:
        loop = asyncio.get_event_loop()
        r = await asyncio.wait_for(loop.run_in_executor(None, _sync), timeout=25)
        if r and len(r) > 15: return r.strip()
    except Exception as e: log.debug(f"AI3: {e}")
    return None

async def _ai4_huggingface(prompt: str) -> Optional[str]:
    """Source 4: HuggingFace free inference"""
    models = [
        "mistralai/Mistral-7B-Instruct-v0.2",
        "HuggingFaceH4/zephyr-7b-beta",
        "microsoft/DialoGPT-large"
    ]
    for model in models:
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.post(f"https://api-inference.huggingface.co/models/{model}",
                    json={"inputs": prompt[:500], "parameters":{"max_new_tokens":300}},
                    headers={"Content-Type":"application/json"})
                if r.status_code == 200:
                    d = r.json()
                    if isinstance(d, list) and d:
                        txt = d[0].get("generated_text","")
                        if txt and len(txt) > 15:
                            return txt.replace(prompt[:100],"").strip()
        except Exception as e: log.debug(f"AI4 {model}: {e}")
    return None

async def _ai5_openrouter_free(system: str, user: str) -> Optional[str]:
    """Source 5: OpenRouter free models"""
    try:
        async with httpx.AsyncClient(timeout=18) as c:
            r = await c.post("https://openrouter.ai/api/v1/chat/completions",
                json={"model":"google/gemma-2-9b-it:free",
                    "messages":[{"role":"system","content":system},{"role":"user","content":user}]},
                headers={"Content-Type":"application/json","HTTP-Referer":"https://indiastudyai.app"})
            if r.status_code == 200:
                txt = r.json().get("choices",[{}])[0].get("message",{}).get("content","")
                if txt and len(txt) > 15: return txt.strip()
    except Exception as e: log.debug(f"AI5: {e}")
    return None

async def _ai6_groq_free(prompt: str) -> Optional[str]:
    """Source 6: Groq free tier (no key needed for basic)"""
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post("https://api.groq.com/openai/v1/chat/completions",
                json={"model":"llama-3.1-8b-instant",
                    "messages":[{"role":"user","content":prompt[:800]}],"max_tokens":500},
                headers={"Content-Type":"application/json","Authorization":"Bearer gsk_free"})
            if r.status_code == 200:
                txt = r.json().get("choices",[{}])[0].get("message",{}).get("content","")
                if txt and len(txt) > 15: return txt.strip()
    except Exception as e: log.debug(f"AI6: {e}")
    return None

async def _ai7_llmfoundry(system: str, user: str) -> Optional[str]:
    """Source 7: LLM Foundry / alternative free endpoint"""
    endpoints = [
        "https://llm.api.cloud.yandex.net/foundationModels/v1/completion",
        "https://api.together.xyz/inference",
    ]
    for ep in endpoints:
        try:
            async with httpx.AsyncClient(timeout=15) as c:
                r = await c.post(ep,
                    json={"model":"mistralai/Mixtral-8x7B-Instruct-v0.1",
                        "messages":[{"role":"system","content":system},{"role":"user","content":user}],
                        "max_tokens":400},
                    headers={"Content-Type":"application/json"})
                if r.status_code == 200:
                    txt = r.json().get("output",{}).get("text","") or \
                          r.json().get("choices",[{}])[0].get("message",{}).get("content","")
                    if txt and len(txt) > 15: return txt.strip()
        except Exception as e: log.debug(f"AI7 {ep}: {e}")
    return None

async def _ai8_wikidata(query: str) -> Optional[str]:
    """Source 8: Wikidata structured knowledge"""
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            # SPARQL query for India-related facts
            sparql = f"""SELECT ?item ?itemLabel ?desc WHERE {{
                ?item wdt:P17 wd:Q668.
                ?item rdfs:label "{query}"@en.
                OPTIONAL {{?item schema:description ?desc FILTER(LANG(?desc)="en")}}
                SERVICE wikibase:label {{bd:serviceParam wikibase:language "hi,en".}}
            }} LIMIT 3"""
            r = await c.get("https://query.wikidata.org/sparql",
                params={"query":sparql,"format":"json"},
                headers={"User-Agent":"IndiaStudyBot/1.0"})
            if r.status_code == 200:
                d = r.json()
                results = d.get("results",{}).get("bindings",[])
                if results:
                    lines = [f"• {res.get('itemLabel',{}).get('value','')} — {res.get('desc',{}).get('value','')}"
                             for res in results[:3] if res.get('itemLabel',{}).get('value')]
                    if lines: return "\n".join(lines)
    except Exception as e: log.debug(f"AI8 Wikidata: {e}")
    return None

# ══════════════════════════════════════════════════════════════════════════════
# FREE CONTENT SOURCES (Wikipedia ke alawa)
# ══════════════════════════════════════════════════════════════════════════════

async def fetch_openlibrary(query: str) -> Optional[str]:
    """Open Library — free books/notes"""
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(f"https://openlibrary.org/search.json?q={query}&fields=title,author_name,subject,first_sentence&limit=3")
            if r.status_code == 200:
                docs = r.json().get("docs",[])
                if docs:
                    lines = []
                    for d in docs[:3]:
                        title = d.get("title","")
                        author = d.get("author_name",[""])[0]
                        subj = d.get("subject",[""])[:3]
                        lines.append(f"📚 *{title}* — {author}\n   Topics: {', '.join(subj)}")
                    return "\n\n".join(lines)
    except Exception as e: log.debug(f"OpenLibrary: {e}")
    return None

async def fetch_arxiv(query: str) -> Optional[str]:
    """arXiv — free science papers summary"""
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.get(f"http://export.arxiv.org/api/query?search_query=all:{query}&max_results=3")
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "lxml-xml")
                entries = soup.find_all("entry")[:3]
                if entries:
                    lines = []
                    for e in entries:
                        title = e.find("title")
                        summary = e.find("summary")
                        if title:
                            lines.append(f"🔬 *{title.text.strip()}*\n{(summary.text.strip()[:200]+'...') if summary else ''}")
                    return "\n\n".join(lines)
    except Exception as e: log.debug(f"arXiv: {e}")
    return None

async def fetch_dbpedia(query: str) -> Optional[str]:
    """DBpedia — structured Wikipedia data"""
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(f"https://dbpedia.org/sparql",
                params={"query":f"SELECT ?abstract WHERE {{ <http://dbpedia.org/resource/{query.replace(' ','_')}> dbo:abstract ?abstract . FILTER(LANG(?abstract)='en') }} LIMIT 1",
                    "format":"json"})
            if r.status_code == 200:
                bindings = r.json().get("results",{}).get("bindings",[])
                if bindings:
                    text = bindings[0].get("abstract",{}).get("value","")
                    if text and len(text) > 80: return text[:500]+"..."
    except Exception as e: log.debug(f"DBpedia: {e}")
    return None

async def fetch_ncert_content(subject: str, topic: str) -> Optional[str]:
    """NCERT-style content via AI"""
    prompt = f"NCERT {subject} textbook ke style mein {topic} explain karo. Hindi mein. Simple language. Examples do."
    return await _ai1_pollinations_openai("Expert NCERT teacher. Hindi mein padhao.", prompt)

async def fetch_wikisource(query: str) -> Optional[str]:
    """Wikisource — free texts"""
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(f"https://en.wikisource.org/w/api.php?action=opensearch&search={query}&limit=3&format=json")
            if r.status_code == 200:
                d = r.json()
                if d[1]:
                    lines = [f"• [{d[1][i]}]({d[3][i]})" for i in range(min(3,len(d[1])))]
                    return "📖 Wikisource se:\n" + "\n".join(lines)
    except Exception as e: log.debug(f"Wikisource: {e}")
    return None

# ══════════════════════════════════════════════════════════════════════════════
# MAIN AI FUNCTION — 8 sources chain
# ══════════════════════════════════════════════════════════════════════════════

async def ask_ai(question: str, user_data: dict = None, mode: str = "study", lang: str = "hi") -> str:
    ud = user_data or {}
    cls = ud.get("class_type",""); subj = ud.get("course",""); goal = ud.get("goal","")

    lang_inst = {"hi":"Pure Hindi mein jawab do.","en":"Answer in English only.",
                 "mix":"Hinglish (Hindi+English mix) mein.","hi-en":"Hindi aur English dono mein."}
    li = lang_inst.get(lang, "Hindi mein.")

    if mode == "ai":
        system = (f"Expert Study AI Tutor for Indian students. Year:{YEAR}. {li} "
                  "SIRF padhai/exam/career topics. Off-topic refuse karo. "
                  "Step-by-step, examples, markdown+emojis.")
    else:
        system = (f"Expert Indian teacher. {YEAR}. Class:{cls}, Subject:{subj}, Goal:{goal}. {li} "
                  "Clearly padhao. Real examples. Step-by-step. Markdown+emojis.")

    full = f"{system}\n\nSawal: {question}"

    # Try all 8 AI sources
    sources = [
        lambda: _ai1_pollinations_openai(system, question),
        lambda: _ai3_g4f(full),
        lambda: _ai5_openrouter_free(system, question),
        lambda: _ai2_pollinations_text(full),
        lambda: _ai4_huggingface(full),
        lambda: _ai7_llmfoundry(system, question),
        lambda: _ai6_groq_free(full),
    ]
    for src in sources:
        try:
            r = await src()
            if r and len(r) > 20: return r
        except: pass

    # Content fallbacks
    for fetch_fn in [
        lambda: fetch_dbpedia(question),
        lambda: fetch_openlibrary(question),
        lambda: fetch_wikisource(question),
    ]:
        try:
            r = await fetch_fn()
            if r: return f"📚 *Study Content:*\n\n{r}\n\n_AI busy hai, database se answer mila_"
        except: pass

    return ("⚠️ Sabhi AI sources busy hain abhi.\n\n"
            "📱 Thodi der baad dobara try karo ya:\n"
            "• /menu se Study App kholein\n"
            "• NCERT.nic.in check karein")

# ══════════════════════════════════════════════════════════════════════════════
# SARKARI UPDATES — Real scraping (no API key)
# ══════════════════════════════════════════════════════════════════════════════

def _scrape_sync(url: str, selectors: list) -> list:
    """Synchronous scraping"""
    try:
        headers = {"User-Agent":"Mozilla/5.0 (Android 13; Mobile; rv:109.0) Gecko/111.0 Firefox/111.0"}
        r = requests.get(url, headers=headers, timeout=8)
        soup = BeautifulSoup(r.text, "lxml")
        items = []
        for sel in selectors:
            found = soup.select(sel)
            for el in found[:8]:
                text = el.get_text(strip=True)[:100]
                href = el.get("href","")
                if text and len(text) > 10:
                    items.append({"title":text,"url":href if href.startswith("http") else ""})
        return items[:8]
    except Exception as e:
        log.debug(f"Scrape {url}: {e}")
        return []

async def scrape_sarkari_jobs() -> list:
    """Scrape from multiple sarkari job sites"""
    loop = asyncio.get_event_loop()
    all_items = []

    # Source 1: SarkariResult RSS
    try:
        async with httpx.AsyncClient(timeout=8, headers={"User-Agent":"Mozilla/5.0"}) as c:
            r = await c.get("https://www.sarkariresult.com/feed/")
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "lxml-xml")
                for item in soup.find_all("item")[:6]:
                    title = item.find("title")
                    link = item.find("link")
                    pub = item.find("pubDate")
                    if title:
                        all_items.append({
                            "title": title.text[:80],
                            "url": link.text if link else "",
                            "date": pub.text[:16] if pub else "",
                            "source": "SarkariResult"
                        })
    except Exception as e: log.debug(f"SR RSS: {e}")

    # Source 2: Rojgar Result RSS
    try:
        async with httpx.AsyncClient(timeout=8, headers={"User-Agent":"Mozilla/5.0"}) as c:
            r = await c.get("https://www.rojgarresult.com/feed/")
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "lxml-xml")
                for item in soup.find_all("item")[:4]:
                    title = item.find("title")
                    link = item.find("link")
                    if title:
                        all_items.append({
                            "title": title.text[:80],
                            "url": link.text if link else "",
                            "source": "RojgarResult"
                        })
    except Exception as e: log.debug(f"RR RSS: {e}")

    # Source 3: Google News RSS for sarkari jobs
    try:
        query = f"sarkari naukri recruitment 2026"
        async with httpx.AsyncClient(timeout=8, headers={"User-Agent":"Mozilla/5.0"}) as c:
            r = await c.get(f"https://news.google.com/rss/search?q={query}&hl=hi&gl=IN&ceid=IN:hi")
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "lxml-xml")
                for item in soup.find_all("item")[:5]:
                    title = item.find("title")
                    link = item.find("link")
                    pub = item.find("pubDate")
                    if title:
                        all_items.append({
                            "title": title.text[:80],
                            "url": link.text if link else "",
                            "date": pub.text[:16] if pub else "",
                            "source": "Google News"
                        })
    except Exception as e: log.debug(f"GNews: {e}")

    return all_items[:10]

async def scrape_by_category(category: str) -> list:
    """Category-specific scraping"""
    cat_queries = {
        "jobs": "sarkari naukri recruitment vacancy 2026",
        "forms": "government form apply online 2026 last date",
        "results": "board exam result 2026 CBSE UP Bihar",
        "yojana": "government scheme yojana 2026 India",
        "admit": "admit card hall ticket 2026",
        "scholar": "scholarship 2026 India students",
    }
    query = cat_queries.get(category, cat_queries["jobs"])
    items = []

    # Google News RSS
    try:
        async with httpx.AsyncClient(timeout=8, headers={"User-Agent":"Mozilla/5.0"}) as c:
            r = await c.get(f"https://news.google.com/rss/search?q={query}&hl=hi&gl=IN&ceid=IN:hi")
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "lxml-xml")
                for item in soup.find_all("item")[:7]:
                    title = item.find("title")
                    link = item.find("link")
                    pub = item.find("pubDate")
                    if title:
                        items.append({
                            "title": title.text[:80],
                            "url": link.text if link else "",
                            "date": pub.text[:16] if pub else "",
                        })
    except Exception as e: log.debug(f"Cat scrape: {e}")
    return items

def _format_items(items: list) -> str:
    if not items:
        return ""
    lines = []
    for item in items[:8]:
        title = item.get("title","")
        url = item.get("url","")
        date = item.get("date","")
        src = item.get("source","")
        line = f"• *{title}*"
        if date: line += f"\n  📅 {date[:16]}"
        if src: line += f" | 📰 {src}"
        if url: line += f"\n  🔗 {url}"
        lines.append(line)
    return "\n\n".join(lines)

async def get_updates_text(category: str = "all") -> str:
    """Get sarkari updates — real scraping + AI fallback"""
    # Real scraping
    if category == "all":
        items = await scrape_sarkari_jobs()
    else:
        items = await scrape_by_category(category)

    if items:
        formatted = _format_items(items)
        if formatted:
            return formatted

    # AI fallback
    cat_prompts = {
        "all": f"India March {YEAR} ke latest sarkari updates: naukri, form, result, yojana. Real {YEAR} info. 6-7 bullets.",
        "jobs": f"India sarkari naukri recruitment March {YEAR}. Latest vacancies.",
        "forms": f"India online form apply March {YEAR}. Last dates.",
        "results": f"India board exam results March {YEAR}.",
        "yojana": f"India government schemes March {YEAR}.",
        "admit": f"India admit card March {YEAR}.",
        "scholar": f"India scholarship {YEAR}.",
    }
    prompt = cat_prompts.get(category, cat_prompts["all"])
    return await _ai_news_multi(prompt, "sarkari")

# ══════════════════════════════════════════════════════════════════════════════
# NEWS — Multiple RSS + AI fallback
# ══════════════════════════════════════════════════════════════════════════════

NEWS_RSS = {
    "india": [
        "https://feeds.feedburner.com/ndtvnews-top-stories",
        "https://timesofindia.indiatimes.com/rssfeedstopstories.cms",
        "https://news.google.com/rss/search?q=India+news+today&hl=hi&gl=IN&ceid=IN:hi",
    ],
    "pol": [
        "https://feeds.feedburner.com/ndtvnews-india-news",
        "https://news.google.com/rss/search?q=India+politics+2026&hl=hi&gl=IN&ceid=IN:hi",
    ],
    "sport": [
        "https://feeds.feedburner.com/ndtvsports-latest",
        "https://news.google.com/rss/search?q=India+cricket+IPL+2026&hl=en&gl=IN&ceid=IN:en",
    ],
    "biz": [
        "https://feeds.feedburner.com/ndtvprofit-latest",
        "https://news.google.com/rss/search?q=India+economy+business+2026&hl=hi&gl=IN&ceid=IN:hi",
    ],
    "edu": [
        "https://news.google.com/rss/search?q=India+education+CBSE+JEE+NEET+2026&hl=hi&gl=IN&ceid=IN:hi",
    ],
}

def _parse_rss_items(xml: str) -> list:
    try:
        soup = BeautifulSoup(xml, "lxml-xml")
        items = []
        for item in soup.find_all("item")[:7]:
            title = item.find("title")
            link = item.find("link")
            pub = item.find("pubDate")
            if title:
                items.append({
                    "title": title.text.strip()[:80],
                    "url": link.text.strip() if link else "",
                    "date": pub.text.strip()[:16] if pub else "",
                })
        return items
    except: return []

async def _fetch_rss_best(urls: list) -> list:
    for url in urls:
        try:
            async with httpx.AsyncClient(timeout=8,
                headers={"User-Agent":"Mozilla/5.0"}, follow_redirects=True) as c:
                r = await c.get(url)
                if r.status_code == 200:
                    items = _parse_rss_items(r.text)
                    if items: return items
        except: continue
    return []

async def get_news_text(category: str = "india") -> str:
    feeds = NEWS_RSS.get(category, NEWS_RSS["india"])
    items = await _fetch_rss_best(feeds)
    if items:
        return _format_items(items)

    # AI fallback
    news_prompts = {
        "india": f"India latest news March {YEAR}.",
        "pol": f"India politics news March {YEAR}.",
        "sport": f"India cricket sports news March {YEAR}.",
        "biz": f"India economy business March {YEAR}.",
        "edu": f"India education CBSE JEE NEET news {YEAR}.",
    }
    return await _ai_news_multi(news_prompts.get(category, news_prompts["india"]), "news")

async def _ai_news_multi(prompt: str, kind: str) -> str:
    """Try multiple AIs for news"""
    sys = (f"Indian {kind} expert. Latest real {YEAR} info. Hindi mein 6-7 bullet points. "
           "Bold title, short detail. Real data only.")
    full = f"{sys}\n\n{prompt}\n\nFormat: • **Title** — detail. Markdown."

    for src in [
        lambda: _ai1_pollinations_openai(sys, prompt),
        lambda: _ai3_g4f(full),
        lambda: _ai2_pollinations_text(full),
        lambda: _ai5_openrouter_free(sys, prompt),
    ]:
        try:
            r = await src()
            if r and len(r) > 30: return r
        except: pass

    return ("⚠️ *Live updates unavailable*\n\n📌 Check karo:\n"
            "• [sarkariresult.com](https://sarkariresult.com)\n"
            "• [rojgarresult.com](https://rojgarresult.com)\n"
            "• [ndtv.in](https://ndtv.in)\n• [aajtak.in](https://aajtak.in)")

# ══════════════════════════════════════════════════════════════════════════════
# DAILY CONTENT
# ══════════════════════════════════════════════════════════════════════════════

async def get_daily_quote() -> str:
    try:
        async with httpx.AsyncClient(timeout=6) as c:
            r = await c.get("https://api.quotable.io/random?tags=inspirational,education,wisdom")
            if r.status_code == 200:
                d = r.json()
                return f'💬 *"{d["content"]}"*\n— _{d["author"]}_'
    except: pass
    quotes = [
        ("सपने वो नहीं जो आप सोते हैं, सपने वो हैं जो आपको सोने नहीं देते।","APJ Abdul Kalam"),
        ("शिक्षा सबसे शक्तिशाली हथियार है।","Nelson Mandela"),
        ("पढ़ो, लिखो, आगे बढ़ो।","BR Ambedkar"),
        ("असफलता सफलता की पहली सीढ़ी है।","Anonymous"),
        ("जो आज पढ़ेगा, वो कल राज करेगा।","Hindi Proverb"),
    ]
    q = random.choice(quotes)
    return f'💬 *"{q[0]}"*\n— _{q[1]}_'

async def get_daily_fact() -> str:
    try:
        async with httpx.AsyncClient(timeout=6) as c:
            r = await c.get("http://numbersapi.com/random/trivia")
            if r.status_code == 200 and len(r.text) > 20:
                return f"🔢 *Fact:* {r.text}"
    except: pass
    facts = [
        "🇮🇳 India mein 22 officially recognized languages hain!",
        "🔬 Human body mein 37 trillion cells hote hain!",
        "🚀 ISRO ne 104 satellites ek saath launch kiye — World Record!",
        "🧠 Insaan ka brain 20% oxygen use karta hai!",
        "🌊 India mein 7500+ km ki coastline hai!",
        "📚 India world ka 2nd largest English speaking country hai!",
    ]
    return random.choice(facts)

async def get_morning_message(name: str, streak: int) -> str:
    today = datetime.now().strftime("%d %B %Y")
    quote = await get_daily_quote()
    fact = await get_daily_fact()
    streak_msg = f"🔥 *{streak} din ki streak!* Khatam mat karna!" if streak > 1 else "🌱 Aaj se streak shuru karo!"
    return (f"🌅 *Good Morning, {name}!*\n📅 {today}\n\n"
            f"{quote}\n\n{fact}\n\n{streak_msg}\n\n"
            f"📚 Aaj bhi padhai karo — greatness awaits! 🚀")
