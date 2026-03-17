import asyncio
import httpx
import logging
import random
import os
import base64
import json
import re
from datetime import datetime
from typing import Optional, Dict, List, Tuple
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.pagesizes import A4, letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch
import io
from PIL import Image, ImageDraw, ImageFont

log = logging.getLogger(__name__)

# API Keys
GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
MISTRAL_KEY = os.environ.get("MISTRAL_API_KEY", "")
DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
CLAUDE_KEY = os.environ.get("CLAUDE_API_KEY", "")
OPENROUTER_KEY = os.environ.get("OPENROUTER_API_KEY", "")

# Font Setup (Hindi Support) - Using smaller, reliable fonts
FONT_URLS = {
    "hindi": "https://github.com/notofonts/noto-fonts/raw/main/hinted/ttf/NotoSansDevanagari/NotoSansDevanagari-Regular.ttf",
    "fallback": "https://github.com/notofonts/noto-fonts/raw/main/hinted/ttf/NotoSans/NotoSans-Regular.ttf"
}
FONT_PATHS = {
    "hindi": "/tmp/NotoSansDevanagari-Regular.ttf",
    "fallback": "/tmp/NotoSans-Regular.ttf"
}

async def download_fonts():
    """Download Hindi fonts for PDF generation"""
    async with httpx.AsyncClient(timeout=30) as client:
        for name, url in FONT_URLS.items():
            if not os.path.exists(FONT_PATHS[name]):
                try:
                    log.info(f"Downloading font: {name}")
                    r = await client.get(url)
                    with open(FONT_PATHS[name], "wb") as f:
                        f.write(r.content)
                    pdfmetrics.registerFont(TTFont(name.capitalize() + 'Font', FONT_PATHS[name]))
                    log.info(f"✅ Font registered: {name}")
                except Exception as e:
                    log.error(f"Font download failed for {name}: {e}")
                    return False
    return True

# ==================== AI RACE MODE ====================
# Multiple AI providers running in parallel - fastest wins

class AIRacer:
    def __init__(self):
        self.providers = []
        self.timeout = 15  # seconds
        
        # Add all available providers with keys
        if GEMINI_KEY:
            self.providers.append(("gemini", self._gemini))
        if GROQ_KEY:
            self.providers.append(("groq", self._groq))
        if MISTRAL_KEY:
            self.providers.append(("mistral", self._mistral))
        if DEEPSEEK_KEY:
            self.providers.append(("deepseek", self._deepseek))
        if CLAUDE_KEY:
            self.providers.append(("claude", self._claude))
        if OPENROUTER_KEY:
            self.providers.append(("openrouter", self._openrouter))
        
        # Free providers (no key needed)
        self.providers.append(("pollinations", self._pollinations))
        # g4f commented out because it requires additional libraries
        # self.providers.append(("g4f", self._g4f))
        
        log.info(f"🚀 AI Racer initialized with {len(self.providers)} providers")
    
    async def _gemini(self, system: str, user: str) -> Optional[str]:
        """Google Gemini AI"""
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
            payload = {
                "contents": [{
                    "parts": [{"text": f"{system}\n\n{user}"}]
                }],
                "generationConfig": {
                    "temperature": 0.7,
                    "maxOutputTokens": 1500
                }
            }
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(url, json=payload)
                if r.status_code == 200:
                    data = r.json()
                    return data["candidates"][0]["content"]["parts"][0]["text"]
                else:
                    log.debug(f"Gemini error status: {r.status_code}")
        except Exception as e:
            log.debug(f"Gemini error: {e}")
        return None
    
    async def _groq(self, system: str, user: str) -> Optional[str]:
        """Groq (Llama 3) - Very Fast"""
        try:
            url = "https://api.groq.com/openai/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {GROQ_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "llama3-8b-8192",
                "messages": [
                    {"role": "system", "content": system[:1500]},
                    {"role": "user", "content": user[:2000]}
                ],
                "temperature": 0.7,
                "max_tokens": 1000
            }
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(url, json=payload, headers=headers)
                if r.status_code == 200:
                    return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            log.debug(f"Groq error: {e}")
        return None
    
    async def _mistral(self, system: str, user: str) -> Optional[str]:
        """Mistral AI"""
        if not MISTRAL_KEY:
            return None
        try:
            url = "https://api.mistral.ai/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {MISTRAL_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "mistral-small-latest",
                "messages": [
                    {"role": "system", "content": system[:1500]},
                    {"role": "user", "content": user[:2000]}
                ],
                "max_tokens": 1000
            }
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(url, json=payload, headers=headers)
                if r.status_code == 200:
                    return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            log.debug(f"Mistral error: {e}")
        return None
    
    async def _deepseek(self, system: str, user: str) -> Optional[str]:
        """DeepSeek AI"""
        if not DEEPSEEK_KEY:
            return None
        try:
            url = "https://api.deepseek.com/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {DEEPSEEK_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": system[:1500]},
                    {"role": "user", "content": user[:2000]}
                ],
                "max_tokens": 1000
            }
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(url, json=payload, headers=headers)
                if r.status_code == 200:
                    return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            log.debug(f"DeepSeek error: {e}")
        return None
    
    async def _claude(self, system: str, user: str) -> Optional[str]:
        """Claude AI (Anthropic)"""
        if not CLAUDE_KEY:
            return None
        try:
            url = "https://api.anthropic.com/v1/messages"
            headers = {
                "x-api-key": CLAUDE_KEY,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "claude-3-haiku-20240307",
                "max_tokens": 1000,
                "system": system[:1500],
                "messages": [{"role": "user", "content": user[:2000]}]
            }
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(url, json=payload, headers=headers)
                if r.status_code == 200:
                    return r.json()["content"][0]["text"]
        except Exception as e:
            log.debug(f"Claude error: {e}")
        return None
    
    async def _openrouter(self, system: str, user: str) -> Optional[str]:
        """OpenRouter (Multiple models)"""
        if not OPENROUTER_KEY:
            return None
        try:
            url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {OPENROUTER_KEY}",
                "Content-Type": "application/json",
                "HTTP-Referer": "https://t.me/IndiaStudyAI_Bot",
                "X-Title": "IndiaStudyAI"
            }
            payload = {
                "model": "mistralai/mixtral-8x7b-instruct",
                "messages": [
                    {"role": "system", "content": system[:1500]},
                    {"role": "user", "content": user[:2000]}
                ],
                "max_tokens": 1000
            }
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(url, json=payload, headers=headers)
                if r.status_code == 200:
                    return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            log.debug(f"OpenRouter error: {e}")
        return None
    
    async def _pollinations(self, system: str, user: str) -> Optional[str]:
        """Pollinations AI (Free) - Fast and reliable"""
        try:
            # Using GET method for faster response
            prompt = f"{system}\n\n{user}"[:1000]
            url = f"https://text.pollinations.ai/{prompt.replace(' ', '%20')}"
            async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
                r = await client.get(url)
                if r.status_code == 200 and len(r.text) > 20:
                    return r.text.strip()
        except Exception as e:
            log.debug(f"Pollinations error: {e}")
            
        # Fallback to POST method
        try:
            url = "https://text.pollinations.ai/openai"
            payload = {
                "messages": [
                    {"role": "system", "content": system[:1000]},
                    {"role": "user", "content": user[:1500]}
                ],
                "private": True,
                "seed": random.randint(1, 9999)
            }
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(url, json=payload)
                if r.status_code == 200:
                    data = r.json()
                    return data["choices"][0]["message"]["content"]
        except Exception as e:
            log.debug(f"Pollinations POST error: {e}")
        return None
    
    async def race(self, system: str, user: str) -> Tuple[Optional[str], str]:
        """
        Run all providers in parallel, return fastest response
        Returns: (answer, provider_name)
        """
        if not self.providers:
            log.error("No AI providers available")
            return None, "none"
        
        tasks = []
        provider_names = []
        
        for name, provider_func in self.providers:
            tasks.append(provider_func(system, user))
            provider_names.append(name)
        
        # Run all tasks concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Find first valid response
        for i, result in enumerate(results):
            if isinstance(result, str) and result and len(result) > 15:
                # Clean the response - remove any you.com links
                result = re.sub(r'https?://(?:www\.)?you\.com[^\s]*', '', result)
                result = re.sub(r'you\.com/pricing', '', result, flags=re.IGNORECASE)
                return result.strip(), provider_names[i]
        
        return None, "none"

# Create global racer instance
ai_racer = AIRacer()

async def ask_ai(question: str, user_data: dict = None, mode: str = "study") -> Tuple[str, str]:
    """
    Main AI function with race mode
    Returns: (answer, provider_name)
    """
    lang = user_data.get("language", "hi") if user_data else "hi"
    
    # Get class and subject if available
    class_type = user_data.get("class_type", "") if user_data else ""
    subject = user_data.get("course", "") if user_data else ""
    
    # System prompts based on mode and language - optimized for speed
    if mode == "study":
        if lang == "hi":
            system = (f"आप एक भारतीय शिक्षा AI हैं। उत्तर हिंदी में दें। "
                     f"कक्षा: {class_type}, विषय: {subject}. "
                     f"सरल भाषा में समझाएं। उदाहरण दें। बाहरी लिंक न दें।")
        elif lang == "en":
            system = (f"You are an Indian education AI. Answer in English. "
                     f"Class: {class_type}, Subject: {subject}. "
                     f"Explain simply with examples. No external links.")
        else:  # mix / hinglish
            system = (f"Indian study AI. Answer in Hinglish (Hindi+English mix). "
                     f"Class: {class_type}, Subject: {subject}. "
                     f"Simple explanation with examples. No external links.")
    
    elif mode == "quick":
        if lang == "hi":
            system = "संक्षिप्त उत्तर हिंदी में दें। बाहरी लिंक न दें।"
        elif lang == "en":
            system = "Give concise answer in English. No external links."
        else:
            system = "Give quick answer in Hinglish. No external links."
    
    elif mode == "mindmap":
        if lang == "hi":
            system = "माइंड मैप टेक्स्ट बनाएं। केंद्र में विषय, 5-6 शाखाएं।"
        else:
            system = "Create text mind map. Center topic, 5-6 branches with sub-points."
    
    else:
        system = "Answer the question helpfully. No external links."
    
    # Add instruction to avoid you.com
    system += " DO NOT mention you.com or any pricing links."
    
    # Race all AIs
    answer, provider = await ai_racer.race(system, question)
    
    if answer:
        # Final cleanup of any remaining you.com links
        answer = re.sub(r'https?://(?:www\.)?you\.com[^\s]*', '', answer)
        answer = re.sub(r'you\.com/pricing', '', answer, flags=re.IGNORECASE)
        return answer, provider
    else:
        return "⚠️ सभी AI सेवाएं व्यस्त हैं। कृपया थोड़ी देर बाद प्रयास करें।", "none"

async def ask_ai_simple(question: str, user_data: dict = None, mode: str = "study") -> str:
    """Simple version that returns only answer"""
    answer, _ = await ask_ai(question, user_data, mode)
    return answer

# ==================== PDF GENERATION ====================

async def generate_pdf(title: str, content: str, filename: str = "notes.pdf") -> str:
    """Generate PDF with Hindi font support"""
    try:
        # Download fonts first
        await download_fonts()
        
        path = f"/tmp/{filename}"
        doc = SimpleDocTemplate(path, pagesize=A4)
        styles = getSampleStyleSheet()
        
        # Create custom styles with Hindi font
        try:
            # Try to register Hindi font
            pdfmetrics.registerFont(TTFont('HindiFont', FONT_PATHS["hindi"]))
            font_name = 'HindiFont'
        except:
            try:
                # Fallback to regular font
                pdfmetrics.registerFont(TTFont('FallbackFont', FONT_PATHS["fallback"]))
                font_name = 'FallbackFont'
            except:
                font_name = 'Helvetica'
        
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Title'],
            fontName=font_name,
            fontSize=18,
            textColor=colors.HexColor('#7c3aed'),
            alignment=1,  # Center
            spaceAfter=12
        )
        
        normal_style = ParagraphStyle(
            'CustomNormal',
            parent=styles['Normal'],
            fontName=font_name,
            fontSize=11,
            leading=16,
            spaceAfter=6
        )
        
        heading_style = ParagraphStyle(
            'CustomHeading',
            parent=styles['Heading2'],
            fontName=font_name,
            fontSize=14,
            textColor=colors.HexColor('#4a1d96'),
            spaceBefore=10,
            spaceAfter=6
        )
        
        story = []
        
        # Title
        story.append(Paragraph(f"<b>{title}</b>", title_style))
        story.append(Spacer(1, 8))
        
        # Date
        date_style = ParagraphStyle(
            'DateStyle',
            parent=normal_style,
            fontSize=9,
            textColor=colors.grey,
            alignment=1
        )
        story.append(Paragraph(f"📅 {datetime.now().strftime('%d %B %Y')}", date_style))
        story.append(Spacer(1, 16))
        
        # Process content - remove markdown stars but keep structure
        lines = content.split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                story.append(Spacer(1, 4))
                continue
            
            # Remove markdown formatting
            clean_line = re.sub(r'\*\*(.*?)\*\*', r'\1', line)  # Bold
            clean_line = re.sub(r'\*(.*?)\*', r'\1', clean_line)  # Italic
            clean_line = re.sub(r'`(.*?)`', r'\1', clean_line)  # Code
            clean_line = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', clean_line)  # Links
            
            # Check if it's a heading
            if line.startswith('# '):
                story.append(Paragraph(clean_line[2:], heading_style))
            elif line.startswith('## ') or line.startswith('### '):
                story.append(Paragraph(clean_line[3:], heading_style))
            elif line.startswith('- ') or line.startswith('• ') or line.startswith('* '):
                # Bullet points
                story.append(Paragraph(f"• {clean_line[2:]}", normal_style))
            elif re.match(r'^\d+\.', line):
                # Numbered list
                story.append(Paragraph(clean_line, normal_style))
            else:
                # Normal text
                try:
                    story.append(Paragraph(clean_line, normal_style))
                except:
                    # If still failing, use ascii only
                    safe_line = clean_line.encode('ascii', 'ignore').decode()
                    story.append(Paragraph(safe_line, normal_style))
        
        # Footer
        story.append(Spacer(1, 24))
        footer_style = ParagraphStyle(
            'Footer',
            parent=normal_style,
            fontSize=8,
            textColor=colors.grey,
            alignment=1
        )
        story.append(Paragraph("Generated by IndiaStudyAI Bot", footer_style))
        
        # Build PDF
        doc.build(story)
        return path
        
    except Exception as e:
        log.error(f"PDF generation failed: {e}")
        # Fallback to text file
        try:
            text_path = f"/tmp/{filename.replace('.pdf', '.txt')}"
            with open(text_path, 'w', encoding='utf-8') as f:
                f.write(f"{title}\n")
                f.write("="*50 + "\n\n")
                # Remove markdown
                clean = re.sub(r'[*#`\[\]()]', '', content)
                f.write(clean)
            return text_path
        except:
            return ""

# ==================== MIND MAP GENERATOR (Text-based) ====================

async def generate_mindmap_text(topic: str, lang: str = "hi") -> str:
    """Generate a text-based mind map (no images to save space)"""
    system = "Create a text mind map. Format with indentation and symbols."
    user = f"Create mind map for: {topic}"
    
    answer, _ = await ask_ai(system, {"language": lang}, "mindmap")
    
    if answer and len(answer) > 20:
        return answer
    else:
        # Fallback simple mind map
        lines = [
            f"🗺️ *Mind Map: {topic}*\n",
            "└── 📌 Main Topic",
            "    ├── 📖 Branch 1",
            "    │   ├── Point 1",
            "    │   ├── Point 2",
            "    │   └── Point 3",
            "    ├── 📚 Branch 2",
            "    │   ├── Point 1",
            "    │   ├── Point 2",
            "    │   └── Point 3",
            "    └── 📝 Branch 3",
            "        ├── Point 1",
            "        ├── Point 2",
            "        └── Point 3"
        ]
        return "\n".join(lines)

# ==================== IMAGE TO TEXT ====================

async def image_to_text(image_path: str) -> str:
    """Extract text from image using Gemini Vision"""
    if not GEMINI_KEY:
        return "Gemini API Key missing! Please set GEMINI_API_KEY environment variable."
    
    try:
        # Read and encode image
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode()
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
        
        payload = {
            "contents": [{
                "parts": [
                    {"text": "Extract all text from this image. If it's a question, also solve it. If handwritten, transcribe it. Return text in same language as image."},
                    {"inline_data": {"mime_type": "image/jpeg", "data": image_data}}
                ]
            }]
        }
        
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(url, json=payload)
            if r.status_code == 200:
                data = r.json()
                return data["candidates"][0]["content"]["parts"][0]["text"]
            else:
                return f"❌ API Error: {r.status_code}"
                
    except Exception as e:
        log.error(f"Image to text error: {e}")
        return f"❌ Error: {str(e)}"

# ==================== NEWS & UPDATES ====================

async def fetch_updates(category: str = "all") -> str:
    """Fetch live sarkari updates"""
    try:
        # Try Google News RSS first
        search_queries = {
            "all": "sarkari+result+india+2026",
            "jobs": "sarkari+naukri+2026",
            "results": "board+exam+result+2026",
            "admit": "admit+card+2026",
            "forms": "online+form+2026"
        }
        
        query = search_queries.get(category, search_queries["all"])
        url = f"https://news.google.com/rss/search?q={query}&hl=hi&gl=IN"
        
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(url)
            if r.status_code == 200:
                # Simple parsing
                import xml.etree.ElementTree as ET
                root = ET.fromstring(r.text)
                items = []
                
                for item in root.findall('.//item')[:6]:
                    title = item.find('title')
                    link = item.find('link')
                    pubDate = item.find('pubDate')
                    
                    if title is not None and title.text:
                        title_text = title.text
                        link_text = link.text if link is not None else ""
                        date_text = pubDate.text[:16] if pubDate is not None and pubDate.text else ""
                        
                        items.append(f"📌 *{title_text}*")
                        if date_text:
                            items.append(f"📅 {date_text}")
                        if link_text:
                            items.append(f"🔗 [Read more]({link_text})")
                        items.append("")
                
                if items:
                    return "\n".join(items)
        
        # Fallback to AI
        return await ask_ai_simple(f"Latest {category} sarkari updates 2026. 5 items with dates.", mode="quick")
        
    except Exception as e:
        log.error(f"Updates error: {e}")
        return "❌ Updates fetch failed. Please try again."

# ==================== QUESTION PAPER ====================

async def generate_question_paper(subject: str, class_name: str, difficulty: str) -> str:
    """Generate question paper using AI"""
    prompt = f"""Create a {difficulty} difficulty question paper for {subject} - {class_name}.

Format:
Section A: 5 MCQ (1 mark each)
Section B: 3 Short Answer (2 marks each)  
Section C: 2 Long Answer (5 marks each)

Total: 21 marks, Time: 1 hour

Also provide answer key at the end.

Use proper formatting with sections marked."""
    
    return await ask_ai_simple(prompt, mode="quick")

# ==================== STUDY PLANNER ====================

async def generate_study_plan(subjects: str, exam_date: str, hours_per_day: int) -> str:
    """Generate personalized study plan"""
    try:
        from datetime import datetime
        exam = datetime.strptime(exam_date, "%Y-%m-%d")
        today = datetime.now()
        days_left = (exam - today).days
        if days_left < 0:
            days_left = 30  # default if past date
    except:
        days_left = 30
    
    prompt = f"""Create a {days_left}-day study plan for:
Subjects: {subjects}
Hours per day: {hours_per_day}

Include:
- Weekly schedule
- Topic distribution
- Revision days
- Mock test days

Make it practical and achievable. Use bullet points."""
    
    return await ask_ai_simple(prompt, mode="quick")

# ==================== VOCABULARY BUILDER ====================

async def build_vocabulary(topic: str, lang: str = "hi") -> str:
    """Generate vocabulary list"""
    prompt = f"""Create a vocabulary list for '{topic}'.

Include 8 important words/phrases with:
- Word
- Meaning (in {'Hindi' if lang == 'hi' else 'English'})
- Example sentence

Format in a simple list."""
    
    return await ask_ai_simple(prompt, mode="quick")

# ==================== CAREER COUNSELOR ====================

async def career_counsel(skills: str, interests: str, education: str, lang: str = "hi") -> str:
    """Generate career advice"""
    prompt = f"""Career advice for:
Skills: {skills}
Interests: {interests}
Education: {education}

Suggest:
1. Top 3 career options
2. Required exams
3. Next steps

Answer in {'Hindi' if lang == 'hi' else 'English' if lang == 'en' else 'Hinglish'}."""
    
    return await ask_ai_simple(prompt, mode="quick")

# ==================== CURRENT AFFAIRS ====================

async def get_current_affairs(lang: str = "hi") -> str:
    """Get current affairs"""
    month = datetime.now().strftime("%B %Y")
    prompt = f"India current affairs {month}. 8 important news items for students. Brief points."
    
    return await ask_ai_simple(prompt, mode="quick")

# ==================== TOPIC SUMMARY ====================

async def summarize_topic(topic: str, lang: str = "hi") -> str:
    """Summarize a topic"""
    prompt = f"Summarize '{topic}' in 5 points. Include key facts and examples."
    
    return await ask_ai_simple(prompt, mode="quick")

# ==================== HELPER FUNCTIONS ====================

def clean_markdown(text: str) -> str:
    """Remove markdown formatting for plain text"""
    if not text:
        return text
    # Remove bold/italic markers
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    text = re.sub(r'__(.*?)__', r'\1', text)
    text = re.sub(r'_(.*?)_', r'\1', text)
    # Remove code blocks
    text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    text = re.sub(r'`(.*?)`', r'\1', text)
    # Remove links
    text = re.sub(r'\[([^\]]+)\]\([^\)]+\)', r'\1', text)
    return text

def truncate_text(text: str, max_length: int = 1000) -> str:
    """Truncate text to max length"""
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."
