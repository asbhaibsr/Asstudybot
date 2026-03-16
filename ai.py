import asyncio, httpx, logging, random, os, feedparser, base64
from datetime import datetime
from typing import Optional
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)
YEAR  = datetime.now().year
MONTH = datetime.now().strftime("%B %Y")

# ══════════════════════════════════════════════════════════════════════════════
# API KEYS  (set in environment)
# ══════════════════════════════════════════════════════════════════════════════
GEMINI_KEY   = os.environ.get("GEMINI_API_KEY",   "")
MISTRAL_KEY  = os.environ.get("MISTRAL_API_KEY",  "")
DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
GROQ_KEY     = os.environ.get("GROQ_API_KEY",     "")   # free tier
TOGETHER_KEY = os.environ.get("TOGETHER_API_KEY", "")   # free tier
COHERE_KEY   = os.environ.get("COHERE_API_KEY",   "")   # free tier

# ── Daily per-user limits for paid/limited APIs ───────────────────────────────
LIMITS = {
    "gemini":   15,   # Gemini 1.5 Flash free: 1500 req/day global
    "mistral":  10,
    "deepseek": 10,
    "groq":     30,   # Groq free: generous limit
    "together": 10,
    "cohere":   10,
}

# ══════════════════════════════════════════════════════════════════════════════
# PREMIUM APIs
# ══════════════════════════════════════════════════════════════════════════════
async def _gemini(system: str, user: str, image_b64: str = None) -> Optional[str]:
    if not GEMINI_KEY: return None
    try:
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"gemini-1.5-flash:generateContent?key={GEMINI_KEY}")
        parts = []
        if image_b64:
            parts.append({"inline_data": {"mime_type": "image/jpeg", "data": image_b64}})
        parts.append({"text": f"{system}\n\n{user}"})
        payload = {
            "contents": [{"parts": parts}],
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 1200}
        }
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(url, json=payload)
            if r.status_code == 200:
                txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                if txt and len(txt) > 15: return txt.strip()
    except Exception as e: log.debug(f"Gemini: {e}")
    return None

async def _mistral(system: str, user: str) -> Optional[str]:
    if not MISTRAL_KEY: return None
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(
                "https://api.mistral.ai/v1/chat/completions",
                json={"model": "mistral-small-latest",
                      "messages": [{"role":"system","content":system},
                                   {"role":"user","content":user}]},
                headers={"Authorization": f"Bearer {MISTRAL_KEY}",
                         "Content-Type": "application/json"})
            if r.status_code == 200:
                txt = r.json()["choices"][0]["message"]["content"]
                if txt and len(txt) > 15: return txt.strip()
    except Exception as e: log.debug(f"Mistral: {e}")
    return None

async def _deepseek(system: str, user: str) -> Optional[str]:
    if not DEEPSEEK_KEY: return None
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(
                "https://api.deepseek.com/chat/completions",
                json={"model": "deepseek-chat",
                      "messages": [{"role":"system","content":system},
                                   {"role":"user","content":user}]},
                headers={"Authorization": f"Bearer {DEEPSEEK_KEY}",
                         "Content-Type": "application/json"})
            if r.status_code == 200:
                txt = r.json()["choices"][0]["message"]["content"]
                if txt and len(txt) > 15: return txt.strip()
    except Exception as e: log.debug(f"DeepSeek: {e}")
    return None

# ══════════════════════════════════════════════════════════════════════════════
# FREE APIs  (unlimited / very generous)
# ══════════════════════════════════════════════════════════════════════════════
async def _groq(system: str, user: str) -> Optional[str]:
    """Groq free tier — very fast (llama3)"""
    if not GROQ_KEY: return None
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(
                "https://api.groq.com/openai/v1/chat/completions",
                json={"model": "llama3-8b-8192",
                      "messages": [{"role":"system","content":system},
                                   {"role":"user","content":user}],
                      "max_tokens": 1000},
                headers={"Authorization": f"Bearer {GROQ_KEY}",
                         "Content-Type": "application/json"})
            if r.status_code == 200:
                txt = r.json()["choices"][0]["message"]["content"]
                if txt and len(txt) > 15: return txt.strip()
    except Exception as e: log.debug(f"Groq: {e}")
    return None

async def _together(system: str, user: str) -> Optional[str]:
    """Together AI free tier"""
    if not TOGETHER_KEY: return None
    try:
        async with httpx.AsyncClient(timeout=18) as c:
            r = await c.post(
                "https://api.together.xyz/v1/chat/completions",
                json={"model": "mistralai/Mixtral-8x7B-Instruct-v0.1",
                      "messages": [{"role":"system","content":system},
                                   {"role":"user","content":user}],
                      "max_tokens": 1000},
                headers={"Authorization": f"Bearer {TOGETHER_KEY}",
                         "Content-Type": "application/json"})
            if r.status_code == 200:
                txt = r.json()["choices"][0]["message"]["content"]
                if txt and len(txt) > 15: return txt.strip()
    except Exception as e: log.debug(f"Together: {e}")
    return None

async def _cohere(system: str, user: str) -> Optional[str]:
    """Cohere free tier"""
    if not COHERE_KEY: return None
    try:
        async with httpx.AsyncClient(timeout=18) as c:
            r = await c.post(
                "https://api.cohere.ai/v1/chat",
                json={"model": "command-r",
                      "message": f"{system}\n\n{user}",
                      "max_tokens": 1000},
                headers={"Authorization": f"Bearer {COHERE_KEY}",
                         "Content-Type": "application/json"})
            if r.status_code == 200:
                txt = r.json().get("text","")
                if txt and len(txt) > 15: return txt.strip()
    except Exception as e: log.debug(f"Cohere: {e}")
    return None

async def _pollinations(system: str, user: str) -> Optional[str]:
    """Pollinations.ai — completely free"""
    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(
                "https://text.pollinations.ai/openai",
                json={"model": "openai",
                      "messages": [{"role":"system","content":system},
                                   {"role":"user","content":user}],
                      "seed": random.randint(1,9999), "private": True},
                headers={"Content-Type": "application/json"})
            if r.status_code == 200:
                txt = r.json().get("choices",[{}])[0].get("message",{}).get("content","")
                if txt and len(txt) > 15: return txt.strip()
    except Exception as e: log.debug(f"Pollinations: {e}")
    return None

async def _pollinations_txt(prompt: str) -> Optional[str]:
    """Pollinations GET fallback"""
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(
                f"https://text.pollinations.ai/{prompt[:600].replace(chr(10),' ')}",
                headers={"Accept": "text/plain"})
            if r.status_code == 200 and len(r.text) > 15:
                return r.text.strip()
    except: pass
    return None

async def _g4f(prompt: str) -> Optional[str]:
    """g4f free library"""
    def _sync():
        try:
            import g4f
            r = g4f.ChatCompletion.create(
                model=g4f.models.gpt_4,
                messages=[{"role":"user","content":prompt}])
            return r if isinstance(r,str) else str(r)
        except:
            try:
                import g4f
                r = g4f.ChatCompletion.create(
                    model=g4f.models.default,
                    messages=[{"role":"user","content":prompt}])
                return r if isinstance(r,str) else str(r)
            except: return None
    try:
        loop = asyncio.get_event_loop()
        r = await asyncio.wait_for(loop.run_in_executor(None, _sync), timeout=20)
        if r and len(r) > 15: return r.strip()
    except Exception as e: log.debug(f"G4F: {e}")
    return None

async def _ddg(query: str) -> Optional[str]:
    """DuckDuckGo AI chat"""
    try:
        from duckduckgo_search import DDGS
        loop = asyncio.get_event_loop()
        def _sync():
            with DDGS() as d: return d.chat(query, model="claude-3-haiku")
        r = await asyncio.wait_for(loop.run_in_executor(None, _sync), timeout=18)
        if r and isinstance(r,str) and len(r) > 15: return r.strip()
    except Exception as e: log.debug(f"DDG: {e}")
    return None

async def _huggingface(system: str, user: str) -> Optional[str]:
    """HuggingFace Inference API — free"""
    try:
        prompt = f"{system}\n\nUser: {user}\nAssistant:"
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.post(
                "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.3",
                json={"inputs": prompt, "parameters": {"max_new_tokens": 600, "return_full_text": False}},
                headers={"Content-Type": "application/json"})
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list) and data:
                    txt = data[0].get("generated_text","")
                    if txt and len(txt) > 15: return txt.strip()
    except Exception as e: log.debug(f"HuggingFace: {e}")
    return None

# ══════════════════════════════════════════════════════════════════════════════
# RACE CONDITION — Sabhi AIs simultaneously, jo pehle aaye wo answer de
# ══════════════════════════════════════════════════════════════════════════════
async def _race_free(system: str, user: str) -> Optional[str]:
    """Run multiple free AIs in parallel — fastest wins"""
    full_prompt = f"{system}\n\n{user}"
    tasks = {
        "_pollinations": _pollinations(system, user),
        "_g4f":          _g4f(full_prompt),
        "_ddg":          _ddg(user),
        "_huggingface":  _huggingface(system, user),
        "_poll_txt":     _pollinations_txt(full_prompt),
    }
    # asyncio.gather with concurrent execution
    results = await asyncio.gather(*tasks.values(), return_exceptions=True)
    for r in results:
        if isinstance(r, str) and len(r) > 20:
            return r
    return None

# ══════════════════════════════════════════════════════════════════════════════
# MAIN AI ENGINE
# ══════════════════════════════════════════════════════════════════════════════
async def ask_ai(question: str, user_data: dict = None, mode: str = "study",
                 api_usage: dict = None) -> tuple[str, str]:
    """Returns (answer, api_used)
    Priority: Gemini → Mistral → DeepSeek → Groq → Together → Cohere → Free race
    """
    ud       = user_data or {}
    cls      = ud.get("class_type","")
    subj     = ud.get("course","")
    lang     = ud.get("language","hi")
    usage    = api_usage or {}

    # ── Build system prompt ──────────────────────────────────────────────────
    if lang == "en":
        if mode == "ai":
            system = (f"You are an expert AI Study Tutor for Indian students. Year:{YEAR}. "
                      f"Answer ONLY study/exam/career questions. Refuse off-topic politely. "
                      f"Step-by-step with real Indian examples. Markdown.")
        elif mode == "news":
            system = f"Indian news/sarkari updates expert. Latest {YEAR} real info. Bullets. Bold titles."
        elif mode == "resume":
            system = "Professional resume writer. Clean ATS-friendly format. English."
        else:
            system = (f"Expert Indian teacher. {YEAR}. Class:{cls}, Subject:{subj}. "
                      f"Teach clearly with real examples. Step-by-step. Markdown. English.")
    else:
        if mode == "ai":
            system = (f"Aap expert Study AI Tutor hain Indian students ke liye. {YEAR}. "
                      f"SIRF padhai/exam/career ke sawaal. Off-topic refuse karo. "
                      f"Hindi/Hinglish. Step-by-step. Markdown.")
        elif mode == "news":
            system = f"Indian news/sarkari expert. Latest {YEAR}. Hindi bullets. Bold headlines."
        elif mode == "resume":
            system = "Professional resume writer. Hindi/English mix. ATS-friendly format."
        else:
            system = (f"Aap expert Indian teacher hain. {YEAR}. Class:{cls}, Subject:{subj}. "
                      f"Hindi mein clearly padhao. Real examples. Step-by-step. Markdown.")

    # ── Try premium APIs (key available + limit not hit) ────────────────────
    if GEMINI_KEY and usage.get("gemini",0) < LIMITS["gemini"]:
        r = await _gemini(system, question)
        if r: return r, "gemini"

    if MISTRAL_KEY and usage.get("mistral",0) < LIMITS["mistral"]:
        r = await _mistral(system, question)
        if r: return r, "mistral"

    if DEEPSEEK_KEY and usage.get("deepseek",0) < LIMITS["deepseek"]:
        r = await _deepseek(system, question)
        if r: return r, "deepseek"

    if GROQ_KEY and usage.get("groq",0) < LIMITS["groq"]:
        r = await _groq(system, question)
        if r: return r, "groq"

    if TOGETHER_KEY and usage.get("together",0) < LIMITS["together"]:
        r = await _together(system, question)
        if r: return r, "together"

    if COHERE_KEY and usage.get("cohere",0) < LIMITS["cohere"]:
        r = await _cohere(system, question)
        if r: return r, "cohere"

    # ── Free race (all parallel) ─────────────────────────────────────────────
    r = await _race_free(system, question)
    if r: return r, "free"

    return ("⚠️ Abhi thodi der baad try karo. Sabhi AI sources busy hain.", "none")

async def ask_ai_simple(question: str, user_data: dict = None, mode: str = "study") -> str:
    result, _ = await ask_ai(question, user_data, mode)
    return result

# ══════════════════════════════════════════════════════════════════════════════
# IMAGE → TEXT  (Gemini Vision first, then pytesseract fallback)
# ══════════════════════════════════════════════════════════════════════════════
async def image_to_text(image_path: str) -> str:
    """Extract text + explain image using Gemini Vision"""
    # 1. Try Gemini Vision (best for Hindi+English)
    if GEMINI_KEY:
        try:
            with open(image_path, "rb") as f:
                img_b64 = base64.b64encode(f.read()).decode()
            result = await _gemini(
                "Extract ALL text from this image exactly as written. "
                "If handwritten, transcribe it. If it's a question/problem, also solve it. "
                "Return the extracted text first, then explanation.",
                "Please extract text and explain this image.",
                image_b64=img_b64
            )
            if result: return result
        except Exception as e:
            log.warning(f"Gemini Vision: {e}")

    # 2. Try pytesseract fallback
    try:
        import pytesseract
        from PIL import Image
        loop = asyncio.get_event_loop()
        def _ocr():
            img = Image.open(image_path)
            text = pytesseract.image_to_string(img, lang='hin+eng')
            if not text.strip():
                text = pytesseract.image_to_string(img, lang='eng')
            return text.strip()
        text = await loop.run_in_executor(None, _ocr)
        return text if text else "❌ Image mein text nahi mila."
    except Exception as e:
        log.warning(f"OCR fallback: {e}")

    return "❌ Image process nahi ho paayi. Clear image bhejo ya Gemini API key set karo."

# ══════════════════════════════════════════════════════════════════════════════
# PDF GENERATOR  (ReportLab — Hindi+English Unicode support)
# ══════════════════════════════════════════════════════════════════════════════
async def generate_pdf(title: str, content: str, filename: str = "notes.pdf") -> str:
    """Generate clean PDF with Unicode support"""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, HRFlowable
        from reportlab.lib.enums import TA_CENTER, TA_LEFT
        import re

        path = f"/tmp/{filename}"
        loop = asyncio.get_event_loop()

        def _make():
            doc = SimpleDocTemplate(path, pagesize=A4,
                                    rightMargin=2*cm, leftMargin=2*cm,
                                    topMargin=2*cm, bottomMargin=2*cm)
            styles = getSampleStyleSheet()
            story  = []

            # Title style
            title_style = ParagraphStyle('Title2', parent=styles['Title'],
                fontSize=18, textColor=colors.HexColor('#7c3aed'),
                spaceAfter=6, alignment=TA_CENTER)
            sub_style = ParagraphStyle('Sub', parent=styles['Normal'],
                fontSize=9, textColor=colors.grey,
                spaceAfter=12, alignment=TA_CENTER)
            h3_style = ParagraphStyle('H3', parent=styles['Heading3'],
                fontSize=13, textColor=colors.HexColor('#5b21b6'), spaceBefore=10)
            body_style = ParagraphStyle('Body', parent=styles['Normal'],
                fontSize=11, leading=16, spaceAfter=6)
            bullet_style = ParagraphStyle('Bullet', parent=styles['Normal'],
                fontSize=11, leading=16, leftIndent=14,
                bulletIndent=4, spaceAfter=4)

            story.append(Paragraph(title[:80], title_style))
            story.append(Paragraph(
                f"IndiaStudyAI | {datetime.now().strftime('%d %B %Y')}", sub_style))
            story.append(HRFlowable(width="100%", color=colors.HexColor('#7c3aed'),
                                    thickness=1.5, spaceAfter=12))

            # Clean markdown
            clean = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', content)
            clean = re.sub(r'\*(.*?)\*',   r'<i>\1</i>', clean)
            clean = re.sub(r'`([^`]+)`',   r'<font name="Courier">\1</font>', clean)

            for line in clean.split('\n'):
                line = line.strip()
                if not line: story.append(Spacer(1, 6)); continue
                if line.startswith('### ') or line.startswith('## ') or line.startswith('# '):
                    h = re.sub(r'^#+\s*','', line)
                    story.append(Paragraph(h, h3_style))
                elif line.startswith('• ') or line.startswith('- ') or line.startswith('* '):
                    story.append(Paragraph(f"• {line[2:]}", bullet_style))
                elif re.match(r'^\d+\.\s', line):
                    story.append(Paragraph(line, bullet_style))
                else:
                    try:
                        story.append(Paragraph(line, body_style))
                    except:
                        safe = line.encode('ascii','replace').decode()
                        story.append(Paragraph(safe, body_style))

            story.append(Spacer(1, 20))
            story.append(HRFlowable(width="100%", color=colors.lightgrey, thickness=0.5))
            story.append(Paragraph("Generated by @IndiaStudyAI_Bot", sub_style))
            doc.build(story)
            return path

        return await loop.run_in_executor(None, _make)

    except Exception as e:
        log.error(f"ReportLab PDF: {e}")
        # Fallback: plain text file
        try:
            import re
            clean = re.sub(r'[*#`]','', content)
            path  = f"/tmp/{filename.replace('.pdf','.txt')}"
            with open(path,'w',encoding='utf-8') as f:
                f.write(f"{title}\nIndiaStudyAI | {datetime.now().strftime('%d %B %Y')}\n")
                f.write("="*50+"\n\n")
                f.write(clean)
            return path
        except: return ""

# ══════════════════════════════════════════════════════════════════════════════
# QUESTION PAPER GENERATOR
# ══════════════════════════════════════════════════════════════════════════════
async def generate_question_paper(subject: str, cls: str, difficulty: str,
                                   lang: str = "hi") -> str:
    li = "in English" if lang == "en" else "Hindi mein"
    prompt = (
        f"Create a complete {difficulty} difficulty question paper {li}.\n"
        f"Subject: {subject}, Class: {cls}, Year: {YEAR}\n\n"
        f"Format:\n"
        f"Section A: 10 MCQ (1 mark each)\n"
        f"Section B: 5 Short Answer (2 marks each)\n"
        f"Section C: 3 Long Answer (5 marks each)\n"
        f"Total: 35 marks, Time: 2 hours\n\n"
        f"Also provide complete Answer Key at the end.\n"
        f"Use markdown formatting."
    )
    return await ask_ai_simple(prompt, mode="study")

# ══════════════════════════════════════════════════════════════════════════════
# MIND MAP GENERATOR
# ══════════════════════════════════════════════════════════════════════════════
async def generate_mind_map(topic: str, lang: str = "hi") -> dict:
    li = "in English" if lang == "en" else "Hindi mein"
    prompt = (
        f"Create a mind map for '{topic}' {li}.\n"
        f"Return ONLY valid JSON in this format:\n"
        f'{{"center":"{topic}","branches":[{{"label":"Branch1","sub":["sub1","sub2","sub3"]}},{{"label":"Branch2","sub":["sub1","sub2"]}}]}}\n'
        f"Give 5-6 main branches, 3-4 sub-items each. No explanation, only JSON."
    )
    result = await ask_ai_simple(prompt, mode="study")
    try:
        import json, re
        # extract JSON from response
        match = re.search(r'\{.*\}', result, re.DOTALL)
        if match:
            return json.loads(match.group())
    except: pass
    return {"center": topic, "branches": [{"label": topic, "sub": ["Details available"]}]}

# ══════════════════════════════════════════════════════════════════════════════
# CAREER COUNSELLOR
# ══════════════════════════════════════════════════════════════════════════════
async def career_counsel(skills: str, interests: str, education: str,
                          lang: str = "hi") -> str:
    li = "in English" if lang == "en" else "Hindi mein"
    prompt = (
        f"Career counsellor {li} for Indian student.\n"
        f"Skills: {skills}\nInterests: {interests}\nEducation: {education}\n\n"
        f"Give:\n"
        f"1. Top 5 career options with job roles\n"
        f"2. Best exams to appear (JEE/NEET/UPSC/SSC etc)\n"
        f"3. Recommended colleges/courses\n"
        f"4. Expected salary range 2026\n"
        f"5. Step-by-step roadmap\n"
        f"Year: {YEAR}. Use markdown."
    )
    return await ask_ai_simple(prompt, mode="study")

# ══════════════════════════════════════════════════════════════════════════════
# SMART STUDY PLANNER
# ══════════════════════════════════════════════════════════════════════════════
async def generate_study_plan(subjects: str, exam_date: str, hours_per_day: int,
                               lang: str = "hi") -> str:
    li = "in English" if lang == "en" else "Hindi mein"
    try:
        from datetime import date
        days_left = max(1,(date.fromisoformat(exam_date)-date.today()).days)
    except: days_left = 30
    prompt = (
        f"Create a {days_left}-day study plan {li}.\n"
        f"Subjects: {subjects}\nExam Date: {exam_date}\n"
        f"Available hours/day: {hours_per_day}\n\n"
        f"Format:\n"
        f"- Week-wise schedule\n"
        f"- Daily topic distribution\n"
        f"- Revision days\n"
        f"- Mock test days\n"
        f"- Important topics to focus\n"
        f"Use markdown tables where needed."
    )
    return await ask_ai_simple(prompt, mode="study")

# ══════════════════════════════════════════════════════════════════════════════
# BOOK / TOPIC SUMMARY
# ══════════════════════════════════════════════════════════════════════════════
async def summarize_topic(topic: str, lang: str = "hi") -> str:
    li = "in English" if lang == "en" else "Hindi mein"
    prompt = (
        f"'{topic}' ka complete 5-minute summary {li}.\n\n"
        f"Include:\n"
        f"1. One-line definition\n"
        f"2. Key concepts (5-7 points)\n"
        f"3. Important dates/formulas/names\n"
        f"4. Real-world examples\n"
        f"5. Exam tips\n"
        f"6. Common mistakes to avoid\n\n"
        f"Use markdown. Year {YEAR}."
    )
    return await ask_ai_simple(prompt, mode="study")

# ══════════════════════════════════════════════════════════════════════════════
# CURRENT AFFAIRS (Daily)
# ══════════════════════════════════════════════════════════════════════════════
async def get_current_affairs(lang: str = "hi") -> str:
    li = "in English" if lang == "en" else "Hindi mein"
    prompt = (
        f"India current affairs {MONTH} {li}.\n"
        f"10 most important news items for competitive exam students.\n"
        f"Format each: **Headline** → Brief explanation → Exam relevance\n"
        f"Topics: Politics, Economy, Sports, Science, Awards, International.\n"
        f"Use markdown."
    )
    return await ask_ai_simple(prompt, mode="news")

# ══════════════════════════════════════════════════════════════════════════════
# VOCABULARY BUILDER
# ══════════════════════════════════════════════════════════════════════════════
async def build_vocabulary(word_or_topic: str, lang: str = "hi") -> str:
    li = "in English with Hindi translation" if lang == "hi" else "in English"
    prompt = (
        f"Vocabulary builder {li} for '{word_or_topic}'.\n"
        f"Give 10 important words/phrases related to this topic.\n"
        f"For each word: meaning, example sentence, synonyms, antonyms.\n"
        f"Use markdown."
    )
    return await ask_ai_simple(prompt, mode="study")

# ══════════════════════════════════════════════════════════════════════════════
# NEWS & UPDATES — Real scraping + RSS + Google News
# ══════════════════════════════════════════════════════════════════════════════
RSS_SARKARI = [
    "https://www.sarkariresult.com/feed/",
    "https://www.indgovtjobs.in/feeds/posts/default",
    "https://www.freejobalert.com/feed/",
    "https://www.sarkarinaukriblog.com/feeds/posts/default",
]
RSS_NEWS = {
    "india": [
        "https://feeds.feedburner.com/ndtvnews-top-stories",
        "https://timesofindia.indiatimes.com/rssfeedstopstories.cms",
        "https://www.thehindu.com/feeder/default.rss",
    ],
    "pol":   ["https://feeds.feedburner.com/ndtvnews-india-news"],
    "sport": [
        "https://feeds.feedburner.com/ndtvsports-latest",
        "https://timesofindia.indiatimes.com/rssfeeds/4719148.cms",
    ],
    "biz": [
        "https://feeds.feedburner.com/ndtvprofit-latest",
        "https://economictimes.indiatimes.com/rssfeedsdefault.cms",
    ],
    "edu": [
        "https://timesofindia.indiatimes.com/rssfeeds/913168846.cms",
        "https://www.hindustantimes.com/feeds/rss/education/rssfeed.xml",
    ],
}

GOOGLE_QUERIES = {
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
            desc  = ""
            if hasattr(e,"summary"):
                desc = BeautifulSoup(e.summary,"lxml").get_text()[:120] if e.summary else ""
            if title:
                lines.append(f"*{title}*\n  📅 {pub}\n  📖 {desc[:100]+'...' if desc else ''}\n  🔗 [Official Site]({link})\n")
        return "\n".join(lines) if lines else None
    except Exception as e:
        log.debug(f"Feed {url}: {e}")
        return None

async def _fetch_rss_parallel(urls: list) -> Optional[str]:
    loop = asyncio.get_event_loop()
    tasks = [loop.run_in_executor(None, _parse_feed, url) for url in urls]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    combined = []
    for r in results:
        if isinstance(r, str) and len(r) > 50:
            combined.append(r)
    return "\n".join(combined[:3]) if combined else None

async def _scrape_sarkari() -> Optional[str]:
    try:
        async with httpx.AsyncClient(timeout=10,
            headers={"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"}) as c:
            r = await c.get("https://www.sarkariresult.com/latestjob/")
            if r.status_code == 200:
                soup = BeautifulSoup(r.text,"lxml")
                links = []
                for a in soup.find_all("a",href=True)[:25]:
                    txt  = a.get_text(strip=True)[:70]
                    href = a.get("href","")
                    if txt and len(txt) > 10 and any(kw in (href+txt).lower()
                        for kw in ["notification","recruitment","result","admit","form","vacancy"]):
                        full = href if href.startswith("http") else f"https://www.sarkariresult.com{href}"
                        links.append(f"*{txt}*\n  🔗 [Official Site]({full})\n")
                if links:
                    return f"📋 *SarkariResult.com — Live {YEAR}*\n\n" + "\n".join(links[:8])
    except Exception as e:
        log.debug(f"Scrape: {e}")
    return None

async def _google_news_rss(query: str) -> Optional[str]:
    url = f"https://news.google.com/rss/search?q={query}&hl=hi&gl=IN&ceid=IN:hi"
    loop = asyncio.get_event_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(None, _parse_feed, url, 8), timeout=10)
    except: return None

async def fetch_updates(category: str = "all") -> str:
    # 1. Live scraping
    if category in ("all","jobs"):
        r = await _scrape_sarkari()
        if r: return r
    # 2. Google News RSS
    gn = await _google_news_rss(GOOGLE_QUERIES.get(category, GOOGLE_QUERIES["all"]))
    if gn: return f"📢 *{category.upper()} — {MONTH}*\n\n{gn}"
    # 3. Direct RSS feeds
    rss = await _fetch_rss_parallel(RSS_SARKARI)
    if rss: return f"📢 *Sarkari Updates — {MONTH}*\n\n{rss}"
    # 4. AI fallback (always works)
    prompts = {
        "all":    f"India {MONTH} latest 8 sarkari updates. Naukri, form, result, yojana. Hindi bullets. Bold title, detail, official website name.",
        "jobs":   f"India govt jobs recruitment {MONTH}. 8 vacancies. Post, dept, last date, site.",
        "forms":  f"India online govt forms active {MONTH}. 8 items. Last date, apply link.",
        "results":f"India board/exam results {MONTH}. CBSE UP Bihar. 8 items.",
        "yojana": f"India PM Modi yojana {MONTH}. 8 schemes. Benefit, kaise apply.",
        "admit":  f"India admit cards {MONTH}. 8 upcoming. Exam, date, download site.",
        "scholar":f"India scholarships {MONTH}. 8 active. Amount, apply date, site.",
    }
    ai = await ask_ai_simple(prompts.get(category, prompts["all"]), mode="news")
    return ai

async def fetch_news(category: str = "india") -> str:
    # 1. Direct RSS
    feeds = RSS_NEWS.get(category, RSS_NEWS["india"])
    rss   = await _fetch_rss_parallel(feeds)
    if rss:
        labels = {"india":"🇮🇳 India","pol":"🏛️ Rajniti","sport":"🏏 Sports",
                  "biz":"💼 Business","edu":"📚 Education"}
        return f"{labels.get(category,'📰')} *{MONTH}*\n\n{rss}"
    # 2. Google News
    gn = await _google_news_rss(GOOGLE_QUERIES.get(category, GOOGLE_QUERIES["india"]))
    if gn: return f"📰 *{category} — {MONTH}*\n\n{gn}"
    # 3. AI fallback
    prompts = {
        "india": f"India latest news {MONTH}. 8 items. Hindi bullets. Bold headline, 2-line summary.",
        "pol":   f"India politics BJP Congress {MONTH}. 8 items Hindi.",
        "sport": f"India cricket IPL sports {MONTH}. 8 items Hindi.",
        "biz":   f"India economy business {MONTH}. 8 items Hindi.",
        "edu":   f"India education CBSE JEE NEET {MONTH}. 8 items Hindi.",
    }
    return await ask_ai_simple(prompts.get(category, prompts["india"]), mode="news")

# ══════════════════════════════════════════════════════════════════════════════
# DAILY CONTENT
# ══════════════════════════════════════════════════════════════════════════════
async def get_daily_quote() -> str:
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get("https://api.quotable.io/random?tags=education,success,wisdom")
            if r.status_code == 200:
                d = r.json()
                return f'💬 *"{d["content"]}"*\n— _{d["author"]}_'
    except: pass
    quotes = [
        ("सपने वो नहीं जो सोते समय देखें, सपने वो हैं जो सोने न दें।","APJ Abdul Kalam"),
        ("शिक्षा सबसे शक्तिशाली हथियार है जिससे दुनिया बदली जा सकती है।","Nelson Mandela"),
        ("पढ़ो, लिखो, आगे बढ़ो।","BR Ambedkar"),
        ("हर expert कभी beginner था।","Anonymous"),
        ("मेहनत इतनी खामोशी से करो कि सफलता शोर मचा दे।","Anonymous"),
        ("कल की चिंता मत करो, आज का काम आज करो।","Chanakya"),
    ]
    q = random.choice(quotes)
    return f'💬 *"{q[0]}"*\n— _{q[1]}_'

async def get_daily_fact() -> str:
    facts = [
        "🇮🇳 India mein 22 officially recognized languages hain!",
        "🔬 Human body mein 37 trillion cells hote hain!",
        "🚀 ISRO ne 104 satellites ek saath launch kiye — world record!",
        "🏏 India ne 1983 aur 2011 mein Cricket World Cup jeeta!",
        "💡 India ne zero aur chess duniya ko diya!",
        "📱 India mein 75 crore+ smartphone users hain!",
        "🌊 India mein 7,500 km ki coastline hai!",
        "📚 World mein sabse zyada engineers India mein train hote hain!",
        "🎓 IIT aur IIM world ke top institutions mein gine jaate hain!",
        "⚡ India ka power grid world ka 3rd largest hai!",
    ]
    return random.choice(facts)

async def get_morning_message(name: str, streak: int) -> str:
    today = datetime.now().strftime("%d %B %Y, %A")
    quote = await get_daily_quote()
    fact  = await get_daily_fact()
    s_txt = f"🔥 *{streak} din streak! Todna mat!*" if streak > 1 else "🌱 *Aaj se streak shuru karo!*"
    return (
        f"🌅 *Good Morning, {name}!*\n📅 {today}\n\n"
        f"{quote}\n\n{fact}\n\n{s_txt}\n\n"
        f"📚 Aaj bhi padhai karo — Greatness awaits! 💪"
    )
