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

# Font Setup (Hindi Support)
FONT_URLS = {
    "hindi": "https://github.com/google/fonts/raw/main/ofl/notosansdevanagari/NotoSansDevanagari%5Bwdth%2Cwght%5D.ttf",
    "fallback": "https://github.com/google/fonts/raw/main/ofl/notosans/NotoSans%5Bwdth%2Cwght%5D.ttf"
}
FONT_PATHS = {
    "hindi": "/tmp/NotoSansDevanagari.ttf",
    "fallback": "/tmp/NotoSans.ttf"
}

async def download_fonts():
    """Download Hindi fonts for PDF generation"""
    async with httpx.AsyncClient() as client:
        for name, url in FONT_URLS.items():
            if not os.path.exists(FONT_PATHS[name]):
                try:
                    r = await client.get(url)
                    with open(FONT_PATHS[name], "wb") as f:
                        f.write(r.content)
                    pdfmetrics.registerFont(TTFont(name.capitalize() + 'Font', FONT_PATHS[name]))
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
        
        # Add all available providers
        if GEMINI_KEY:
            self.providers.append(self._gemini)
        if GROQ_KEY:
            self.providers.append(self._groq)
        if MISTRAL_KEY:
            self.providers.append(self._mistral)
        if DEEPSEEK_KEY:
            self.providers.append(self._deepseek)
        if CLAUDE_KEY:
            self.providers.append(self._claude)
        if OPENROUTER_KEY:
            self.providers.append(self._openrouter)
        
        # Free providers (no key needed)
        self.providers.extend([
            self._pollinations,
            self._huggingface,
            self._g4f
        ])
    
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
                    "maxOutputTokens": 2048
                }
            }
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(url, json=payload)
                if r.status_code == 200:
                    data = r.json()
                    return data["candidates"][0]["content"]["parts"][0]["text"]
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
                "model": "llama3-70b-8192",
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user}
                ],
                "temperature": 0.7,
                "max_tokens": 2048
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
        try:
            url = "https://api.mistral.ai/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {MISTRAL_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "mistral-large-latest",
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user}
                ]
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
        try:
            url = "https://api.deepseek.com/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {DEEPSEEK_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "deepseek-chat",
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user}
                ]
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
        try:
            url = "https://api.anthropic.com/v1/messages"
            headers = {
                "x-api-key": CLAUDE_KEY,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "claude-3-haiku-20240307",
                "max_tokens": 2048,
                "system": system,
                "messages": [{"role": "user", "content": user}]
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
        try:
            url = "https://openrouter.ai/api/v1/chat/completions"
            headers = {
                "Authorization": f"Bearer {OPENROUTER_KEY}",
                "Content-Type": "application/json"
            }
            payload = {
                "model": "mistralai/mixtral-8x7b-instruct",
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user}
                ]
            }
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(url, json=payload, headers=headers)
                if r.status_code == 200:
                    return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            log.debug(f"OpenRouter error: {e}")
        return None
    
    async def _pollinations(self, system: str, user: str) -> Optional[str]:
        """Pollinations AI (Free)"""
        try:
            url = "https://text.pollinations.ai/openai"
            payload = {
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user}
                ],
                "private": True
            }
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(url, json=payload)
                if r.status_code == 200:
                    return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            log.debug(f"Pollinations error: {e}")
        return None
    
    async def _huggingface(self, system: str, user: str) -> Optional[str]:
        """HuggingFace Inference API"""
        try:
            url = "https://api-inference.huggingface.co/models/mistralai/Mistral-7B-Instruct-v0.3"
            prompt = f"{system}\n\nUser: {user}\nAssistant:"
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.post(url, json={"inputs": prompt, "parameters": {"max_new_tokens": 500}})
                if r.status_code == 200:
                    data = r.json()
                    if isinstance(data, list) and data:
                        return data[0].get("generated_text", "")
        except Exception as e:
            log.debug(f"HuggingFace error: {e}")
        return None
    
    async def _g4f(self, system: str, user: str) -> Optional[str]:
        """G4F (Free) - Run in executor"""
        def _sync():
            try:
                import g4f
                response = g4f.ChatCompletion.create(
                    model=g4f.models.gpt_4,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user}
                    ]
                )
                return response if isinstance(response, str) else str(response)
            except:
                return None
        
        try:
            loop = asyncio.get_event_loop()
            return await asyncio.wait_for(
                loop.run_in_executor(None, _sync),
                timeout=self.timeout
            )
        except Exception as e:
            log.debug(f"G4F error: {e}")
            return None
    
    async def race(self, system: str, user: str) -> Tuple[str, str]:
        """
        Run all providers in parallel, return fastest response
        Returns: (answer, provider_name)
        """
        tasks = []
        for provider in self.providers:
            tasks.append(provider(system, user))
        
        # Run all tasks concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Find first valid response
        for i, result in enumerate(results):
            if isinstance(result, str) and result and len(result) > 20:
                provider_name = self.providers[i].__name__.replace('_', '')
                return result.strip(), provider_name
        
        return None, None

# Create global racer instance
ai_racer = AIRacer()

async def ask_ai(question: str, user_data: dict = None, mode: str = "study") -> Tuple[str, str]:
    """
    Main AI function with race mode
    Returns: (answer, provider_name)
    """
    lang = user_data.get("language", "hi") if user_data else "hi"
    
    # System prompts based on mode and language
    system_prompts = {
        "study": {
            "hi": "आप एक उन्नत भारतीय शिक्षा AI हैं। सभी उत्तर हिंदी में दें। कहानी के रूप में समझाएं ताकि छात्र कभी न भूलें। उदाहरण दें। कभी भी बाहरी लिंक न दें।",
            "en": "You are an advanced Indian education AI. Answer in English. Explain like a story so students never forget. Give examples. Never give external links.",
            "mix": "You are an advanced Indian education AI. Answer in Hinglish (Hindi+English mix). Explain like a story. Give examples. No external links."
        },
        "quick": {
            "hi": "आप एक त्वरित सहायक हैं। संक्षिप्त और सटीक उत्तर हिंदी में दें।",
            "en": "You are a quick assistant. Give concise and accurate answers in English.",
            "mix": "You are a quick assistant. Give concise answers in Hinglish."
        },
        "mindmap": {
            "hi": "आपको एक माइंड मैप टेक्स्ट बनाना है। मुख्य विषय को केंद्र में रखें और 5-6 शाखाएं बनाएं। प्रत्येक शाखा में 3-4 उप-बिंदु हों।",
            "en": "Create a mind map text. Put main topic in center with 5-6 branches. Each branch has 3-4 sub-points.",
            "mix": "Mind map banao. Center mein main topic, 5-6 branches, har branch mein 3-4 sub-points."
        }
    }
    
    system = system_prompts.get(mode, system_prompts["study"]).get(lang, system_prompts["study"]["hi"])
    
    # Add class/subject context if available
    if user_data:
        if user_data.get("class_type"):
            system += f"\nClass: {user_data['class_type']}"
        if user_data.get("course"):
            system += f"\nSubject: {user_data['course']}"
    
    # Race all AIs
    answer, provider = await ai_racer.race(system, question)
    
    if answer:
        # Remove any you.com links if present
        answer = re.sub(r'https?://(?:www\.)?you\.com[^\s]*', '', answer)
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
            title_style = ParagraphStyle(
                'CustomTitle',
                parent=styles['Title'],
                fontName='HindiFont',
                fontSize=18,
                textColor=colors.HexColor('#7c3aed'),
                alignment=1,  # Center
                spaceAfter=12
            )
            
            normal_style = ParagraphStyle(
                'CustomNormal',
                parent=styles['Normal'],
                fontName='HindiFont',
                fontSize=12,
                leading=16,
                spaceAfter=8
            )
            
            heading_style = ParagraphStyle(
                'CustomHeading',
                parent=styles['Heading2'],
                fontName='HindiFont',
                fontSize=14,
                textColor=colors.HexColor('#4a1d96'),
                spaceAfter=10
            )
        except:
            # Fallback to default fonts
            title_style = styles['Title']
            normal_style = styles['Normal']
            heading_style = styles['Heading2']
        
        story = []
        
        # Title
        story.append(Paragraph(f"<b>{title}</b>", title_style))
        story.append(Spacer(1, 12))
        
        # Date
        date_style = ParagraphStyle(
            'DateStyle',
            parent=normal_style,
            fontSize=10,
            textColor=colors.grey,
            alignment=1
        )
        story.append(Paragraph(f"📅 {datetime.now().strftime('%d %B %Y')}", date_style))
        story.append(Spacer(1, 20))
        
        # Process content (remove markdown stars)
        lines = content.split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                story.append(Spacer(1, 6))
                continue
            
            # Remove markdown formatting
            clean_line = re.sub(r'\*\*(.*?)\*\*', r'\1', line)  # Bold
            clean_line = re.sub(r'\*(.*?)\*', r'\1', clean_line)  # Italic
            clean_line = re.sub(r'`(.*?)`', r'\1', clean_line)  # Code
            
            # Check if it's a heading
            if line.startswith('# '):
                story.append(Paragraph(clean_line[2:], heading_style))
            elif line.startswith('## '):
                story.append(Paragraph(clean_line[3:], heading_style))
            elif line.startswith('### '):
                story.append(Paragraph(clean_line[4:], heading_style))
            elif line.startswith('- ') or line.startswith('• '):
                # Bullet points
                story.append(Paragraph(f"• {clean_line[2:]}", normal_style))
            else:
                # Normal text
                story.append(Paragraph(clean_line, normal_style))
        
        # Footer
        story.append(Spacer(1, 30))
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
                f.write(content)
            return text_path
        except:
            return ""

# ==================== MIND MAP GENERATOR (Image) ====================

async def generate_mindmap_image(topic: str, lang: str = "hi") -> Optional[str]:
    """Generate a visual mind map image"""
    try:
        # First get mind map content from AI
        system = "Create a mind map. Return ONLY a JSON object with this format: {'center':'topic','branches':[{'name':'branch1','points':['point1','point2','point3']}]}. Give 5-6 branches."
        user = f"Create mind map for: {topic}"
        
        # Use AI to generate structure
        answer, _ = await ask_ai(user, {"language": "en"}, "mindmap")
        
        # Try to parse JSON
        try:
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', answer, re.DOTALL)
            if json_match:
                mindmap = json.loads(json_match.group())
            else:
                mindmap = {"center": topic, "branches": []}
        except:
            # Fallback structure
            mindmap = {"center": topic, "branches": []}
        
        # Create image
        img = Image.new('RGB', (1200, 800), color='white')
        draw = ImageDraw.Draw(img)
        
        # Try to load fonts
        try:
            # Download a font if needed
            font_path = "/tmp/DejaVuSans.ttf"
            if not os.path.exists(font_path):
                font_url = "https://github.com/dejavu-fonts/dejavu-fonts/raw/master/ttf/DejaVuSans.ttf"
                async with httpx.AsyncClient() as client:
                    r = await client.get(font_url)
                    with open(font_path, 'wb') as f:
                        f.write(r.content)
            
            title_font = ImageFont.truetype(font_path, 24)
            branch_font = ImageFont.truetype(font_path, 18)
            point_font = ImageFont.truetype(font_path, 14)
        except:
            title_font = ImageFont.load_default()
            branch_font = ImageFont.load_default()
            point_font = ImageFont.load_default()
        
        # Draw center topic
        center_x, center_y = 600, 200
        draw.ellipse((center_x-60, center_y-30, center_x+60, center_y+30), fill='#7c3aed', outline='black')
        draw.text((center_x, center_y), mindmap['center'][:20], fill='white', font=title_font, anchor='mm')
        
        # Draw branches
        branch_positions = []
        colors = ['#ef4444', '#f59e0b', '#10b981', '#3b82f6', '#8b5cf6', '#ec4899']
        
        for i, branch in enumerate(mindmap.get('branches', [])[:6]):
            angle = (i * 60) * 3.14159 / 180  # 60 degrees apart
            branch_x = center_x + int(250 * cos(angle))
            branch_y = center_y + int(150 * sin(angle))
            
            # Draw line from center to branch
            draw.line((center_x, center_y, branch_x, branch_y), fill='gray', width=2)
            
            # Draw branch circle
            draw.ellipse((branch_x-40, branch_y-20, branch_x+40, branch_y+20), 
                        fill=colors[i % len(colors)], outline='black')
            draw.text((branch_x, branch_y), branch.get('name', f'Branch {i+1}')[:15], 
                     fill='white', font=branch_font, anchor='mm')
            
            # Draw sub-points
            for j, point in enumerate(branch.get('points', [])[:3]):
                point_y = branch_y + 40 + (j * 25)
                draw.ellipse((branch_x-5, point_y-5, branch_x+5, point_y+5), 
                            fill=colors[i % len(colors)], outline='black')
                draw.text((branch_x + 20, point_y), point[:30], 
                         fill='black', font=point_font, anchor='lm')
            
            branch_positions.append((branch_x, branch_y))
        
        # Save image
        image_path = f"/tmp/mindmap_{int(datetime.now().timestamp())}.png"
        img.save(image_path)
        return image_path
        
    except Exception as e:
        log.error(f"Mind map generation failed: {e}")
        return None

# ==================== IMAGE TO TEXT ====================

async def image_to_text(image_path: str) -> str:
    """Extract text from image using Gemini Vision"""
    if not GEMINI_KEY:
        return "Gemini API Key missing!"
    
    try:
        with open(image_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode()
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
        
        payload = {
            "contents": [{
                "parts": [
                    {"text": "Extract all text from this image. If it's a question, also solve it. If handwritten, transcribe it. Return text in same language."},
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
        # Try RSS first
        rss_urls = {
            "all": "https://news.google.com/rss/search?q=sarkari+result+india&hl=hi&gl=IN",
            "jobs": "https://news.google.com/rss/search?q=sarkari+naukri&hl=hi&gl=IN",
            "admit": "https://news.google.com/rss/search?q=admit+card&hl=hi&gl=IN",
            "result": "https://news.google.com/rss/search?q=exam+result&hl=hi&gl=IN"
        }
        
        url = rss_urls.get(category, rss_urls["all"])
        
        async with httpx.AsyncClient() as client:
            r = await client.get(url)
            if r.status_code == 200:
                # Simple RSS parsing
                import xml.etree.ElementTree as ET
                root = ET.fromstring(r.text)
                items = []
                
                for item in root.findall('.//item')[:8]:
                    title = item.find('title').text if item.find('title') is not None else ''
                    link = item.find('link').text if item.find('link') is not None else ''
                    pubDate = item.find('pubDate').text if item.find('pubDate') is not None else ''
                    
                    items.append(f"📌 *{title}*\n📅 {pubDate[:16]}\n🔗 [Read More]({link})\n")
                
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
Section A: 10 MCQ (1 mark each)
Section B: 5 Short Answer (2 marks each)  
Section C: 3 Long Answer (5 marks each)

Also provide answer key at the end.

Use proper formatting with sections marked."""
    
    return await ask_ai_simple(prompt, mode="study")

# ==================== STUDY PLANNER ====================

async def generate_study_plan(subjects: str, exam_date: str, hours_per_day: int) -> str:
    """Generate personalized study plan"""
    try:
        from datetime import datetime
        exam = datetime.strptime(exam_date, "%Y-%m-%d")
        today = datetime.now()
        days_left = (exam - today).days
        
        prompt = f"""Create a {days_left}-day study plan for:
Subjects: {subjects}
Hours per day: {hours_per_day}

Include:
- Daily schedule
- Topic distribution
- Revision days
- Mock test days
- Important topics focus

Make it practical and achievable."""
        
        return await ask_ai_simple(prompt, mode="study")
        
    except Exception as e:
        return f"Error: {str(e)}"

# ==================== VOCABULARY BUILDER ====================

async def build_vocabulary(topic: str, lang: str = "hi") -> str:
    """Generate vocabulary list"""
    prompt = f"""Create a vocabulary list for '{topic}'.

Include 10 important words/phrases with:
- Word
- Meaning (in {lang})
- Example sentence
- Synonym/Antonym

Format in a clean table."""
    
    return await ask_ai_simple(prompt, mode="study")

# ==================== HELPER FUNCTIONS ====================

def cos(angle):
    """Helper for mind map"""
    from math import cos
    return cos(angle)

def sin(angle):
    """Helper for mind map"""
    from math import sin
    return sin(angle)
