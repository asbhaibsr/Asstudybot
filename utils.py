import os
from typing import Optional

OWNER_ID = int(os.environ.get("OWNER_ID","123456789"))

async def is_admin(uid: int) -> bool:
    return uid == OWNER_ID

def format_number(n: int) -> str:
    """1234567 → 12,34,567 (Indian format)"""
    s = str(n)
    if len(s) <= 3: return s
    result = s[-3:]
    s = s[:-3]
    while len(s) > 2:
        result = s[-2:] + "," + result
        s = s[:-2]
    if s: result = s + "," + result
    return result

def truncate(text: str, max_len: int = 100, suffix: str = "...") -> str:
    if len(text) <= max_len: return text
    return text[:max_len-len(suffix)] + suffix

def safe_md(text: str) -> str:
    """Escape special Markdown characters"""
    chars = ['_','*','[',']','(',')','>','#','+','-','=','|','{','}','.','!']
    for c in chars:
        text = text.replace(c, f"\\{c}")
    return text
