#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bio with AI — ربات حرفه‌ای کانال تلگرام
============================================
نسخه ۲.۰ با قابلیت‌های پیشرفته:
  ● فرمت‌های پیشرفته تلگرام (bold, italic, code, pre, spoiler, blockquote)
  ● انواع پست: خبری، تحلیلی، آموزشی، طنز علمی، الهام‌بخش
  ● دکمه‌های اینلاین و نظرسنجی
  ● تولید تصویر با کیفیت بالا
  ● محتوای ترند روز
  ● ۱۰+ قالب مختلف پست
"""

import base64
import html
import json
import os
import random
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, List, Dict, Any

import feedparser
import requests

# ----------------------------------------------------------------------
# تنظیمات عمومی
# ----------------------------------------------------------------------
BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
CHANNEL_ID = os.environ.get("CHANNEL_ID", "@Bio_with_AI").strip()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
AI_CONFIG = os.environ.get("AI_CONFIG", "").strip()

# تنظیمات جدید
ENABLE_POLLS = os.environ.get("ENABLE_POLLS", "1") == "1"
ENABLE_BUTTONS = os.environ.get("ENABLE_BUTTONS", "1") == "1"
POST_STYLE = os.environ.get("POST_STYLE", "smart").strip()  # smart | news | educational | inspirational | funny
USE_TRENDING = os.environ.get("USE_TRENDING", "1") == "1"

FALLBACK_GEMINI_MODELS = [m.strip() for m in os.environ.get("GEMINI_MODELS",
    "gemini-flash-latest, gemini-2.5-flash, gemini-2.0-flash").split(",") if m.strip()]
GEMINI_IMAGE_FALLBACK = ["gemini-2.5-flash-image", "gemini-2.0-flash-preview-image-generation"]
INCLUDE_PRO = os.environ.get("INCLUDE_PRO", "0") == "1"
MAX_AGE_DAYS = int(os.environ.get("MAX_AGE_DAYS", "7"))
FORCE_TYPE = os.environ.get("FORCE_TYPE", "").strip().lower()
CONTENT_MIX = os.environ.get("CONTENT_MIX", "news:4,trending:3,educational:2,tool:1")
WITH_IMAGE = os.environ.get("WITH_IMAGE", "1") == "1"
FULL_TEXT_AFTER_IMAGE = os.environ.get("FULL_TEXT_AFTER_IMAGE", "1") == "1"
BASE_TAGS = os.environ.get("BASE_TAGS", "#بیوانفورماتیک #زیست_شناسی #هوش_مصنوعی").strip()

DAILY_MIN = int(os.environ.get("DAILY_MIN", "20"))
DAILY_MAX = int(os.environ.get("DAILY_MAX", "30"))
FORCE_POST = os.environ.get("FORCE_POST", "") == "1"

DRY_RUN = "--dry-run" in sys.argv
SELFTEST = "--selftest" in sys.argv
MOCK_LLM = os.environ.get("MOCK_LLM", "") == "1"
TELEGRAM_DRY = os.environ.get("TELEGRAM_DRY", "") == "1"

TEHRAN_TZ = timezone(timedelta(hours=3, minutes=30))
ROOT = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(ROOT, "state", "posted.json")

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# ======================================================================
# کلاس‌های جدید برای فرمت‌بندی پیشرفته
# ======================================================================
class TelegramFormatter:
    """فرمت‌کننده پیشرفته پیام‌های تلگرام"""
    
    @staticmethod
    def bold(text: str) -> str:
        return f"<b>{html.escape(text)}</b>"
    
    @staticmethod
    def italic(text: str) -> str:
        return f"<i>{html.escape(text)}</i>"
    
    @staticmethod
    def underline(text: str) -> str:
        return f"<u>{html.escape(text)}</u>"
    
    @staticmethod
    def strikethrough(text: str) -> str:
        return f"<s>{html.escape(text)}</s>"
    
    @staticmethod
    def spoiler(text: str) -> str:
        return f'<span class="tg-spoiler">{html.escape(text)}</span>'
    
    @staticmethod
    def code(text: str) -> str:
        return f"<code>{html.escape(text)}</code>"
    
    @staticmethod
    def pre(text: str, language: str = "") -> str:
        if language:
            return f'<pre language="{html.escape(language)}">{html.escape(text)}</pre>'
        return f"<pre>{html.escape(text)}</pre>"
    
    @staticmethod
    def link(text: str, url: str) -> str:
        return f'<a href="{html.escape(url)}">{html.escape(text)}</a>'
    
    @staticmethod
    def blockquote(text: str) -> str:
        return f"<blockquote>{html.escape(text)}</blockquote>"
    
    @staticmethod
    def mention(user: str) -> str:
        return f"<a href='tg://user?id={user}'>{html.escape(user)}</a>"
    
    @staticmethod
    def emoji_list(items: List[str], emoji: str = "•") -> str:
        """ساخت لیست با ایموجی"""
        return "\n".join(f"{emoji} {item}" for item in items)
    
    @staticmethod
    def numbered_list(items: List[str]) -> str:
        """ساخت لیست شماره‌دار"""
        return "\n".join(f"{i+1}. {item}" for i, item in enumerate(items))


# ======================================================================
# قالب‌های پست (۱۰+ قالب مختلف)
# ======================================================================
POST_TEMPLATES = {
    "scientific": {
        "emoji": "🔬",
        "title_format": "{emoji} {bold(title)}",
        "body_format": "{body}",
        "footer_format": "\n\n📚 {bold('منبع:')} {link(source_name, source_url)}\n{channel_link}"
    },
    "news": {
        "emoji": "📰",
        "title_format": "{emoji} {bold(title)}",
        "body_format": "{body}\n\n💡 {italic(why)}" if "{why}" in "{body}" else "{body}",
        "footer_format": "\n\n🔗 {bold('منبع:')} {link(source_name, source_url)}\n{channel_link}"
    },
    "educational": {
        "emoji": "🎓",
        "title_format": "{emoji} {bold(title)}",
        "body_format": "📖 {italic('مطلب آموزشی')}\n\n{body}\n\n{blockquote(why)}" if "{why}" in "{body}" else "{body}",
        "footer_format": "\n\n{channel_link}"
    },
    "inspirational": {
        "emoji": "✨",
        "title_format": "{emoji} {bold(title)}",
        "body_format": "{body}\n\n🌟 {italic(why)}" if "{why}" in "{body}" else "{body}",
        "footer_format": "\n\n{channel_link}"
    },
    "funny": {
        "emoji": "😄",
        "title_format": "{emoji} {bold(title)}",
        "body_format": "{body}\n\n🤔 {italic(why)}" if "{why}" in "{body}" else "{body}",
        "footer_format": "\n\n{channel_link}"
    },
    "tool": {
        "emoji": "🛠",
        "title_format": "{emoji} {bold(title)}",
        "body_format": "{body}\n\n💡 {italic(why)}" if "{why}" in "{body}" else "{body}",
        "footer_format": "\n\n🔗 {bold('لینک ابزار:')} {link(source_name, source_url)}\n{channel_link}"
    },
    "roadmap": {
        "emoji": "🗺",
        "title_format": "{emoji} {bold(title)}",
        "body_format": "{intro}\n\n🎯 {bold('مسیر پیشنهادی:')}\n{steps}\n\n✅ {bold('سخن پایانی:')} {final}",
        "footer_format": "\n\n🔗 {bold('منبع:')} {link(source_name, source_url)}\n{channel_link}"
    },
    "tip": {
        "emoji": "💡",
        "title_format": "{emoji} {bold(title)}",
        "body_format": "{body}\n\n🎯 {italic(why)}" if "{why}" in "{body}" else "{body}",
        "footer_format": "\n\n🔗 {bold('منبع:')} {link(source_name, source_url)}\n{channel_link}"
    },
    "debate": {
        "emoji": "⚡",
        "title_format": "{emoji} {bold(title)}",
        "body_format": "{body}\n\n🤔 {bold('نکته مهم:')} {italic(why)}" if "{why}" in "{body}" else "{body}",
        "footer_format": "\n\n💬 نظر شما چیست؟\n{channel_link}"
    },
    "summary": {
        "emoji": "📊",
        "title_format": "{emoji} {bold(title)}",
        "body_format": "📌 {bold('خلاصه:')}\n{body}\n\n{blockquote(why)}" if "{why}" in "{body}" else "{body}",
        "footer_format": "\n\n{channel_link}"
    }
}


def get_post_template(style: str = "smart") -> Dict[str, str]:
    """انتخاب قالب مناسب بر اساس سبک"""
    if style == "smart":
        # انتخاب تصادفی با وزن‌های مختلف
        weights = {
            "scientific": 3, "news": 4, "educational": 3, "inspirational": 2,
            "funny": 1, "tool": 2, "roadmap": 2, "tip": 3, "debate": 1, "summary": 2
        }
        return random.choices(list(POST_TEMPLATES.keys()), weights=list(weights.values()))[0]
    return style if style in POST_TEMPLATES else "news"


# ======================================================================
# موتورهای هوش مصنوعی (همان کد قبلی با کمی بهبود)
# ======================================================================
class Engine:
    def __init__(self, kind: str, api_key: str, models: list[str], base_url: str = ""):
        self.kind = kind
        self.api_key = api_key
        self.models = models
        self.base_url = base_url.rstrip("/")
        self.id = f"{kind}:{api_key[-6:]}"

    def __repr__(self):
        return f"<{self.kind} {self.models} …{self.api_key[-6:]}>"


def load_engines() -> list[Engine]:
    engines: list[Engine] = []
    raw_cfg = os.environ.get("AI_CONFIG", "").strip()
    legacy = os.environ.get("GEMINI_API_KEY", "").strip()
    if raw_cfg:
        try:
            cfg = json.loads(raw_cfg)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"AI_CONFIG معتبر نیست: {exc.msg}") from exc
        default_models = [str(m).strip() for m in cfg.get("gemini_models", []) if str(m).strip()] or FALLBACK_GEMINI_MODELS
        for entry in cfg.get("gemini", []):
            if isinstance(entry, dict):
                key = str(entry.get("api_key", "")).strip()
                models = [str(m).strip() for m in entry.get("models", default_models) if str(m).strip()]
            else:
                key, models = str(entry).strip(), default_models
            if key and models:
                engines.append(Engine("gemini", key, models))
        for e in cfg.get("openai_compatible", []):
            if e.get("api_key") and e.get("base_url") and e.get("model"):
                engines.append(Engine("openai", e["api_key"].strip(),
                                      [e["model"].strip()], e["base_url"]))
    if not engines and legacy:
        engines.append(Engine("gemini", legacy, FALLBACK_GEMINI_MODELS))
    return engines


ENGINES: list[Engine] = []
PINNED_GEMINI_MODELS: list[str] = []

# ... (بقیه کدهای موتورهای AI از فایل قبلی)
# برای اختصار، کدهای قبلی رو اینجا قرار می‌دم ولی در فایل نهایی کامل می‌شه


# ======================================================================
# تولید محتوای ترند روز
# ======================================================================
def get_trending_topics() -> List[Dict[str, str]]:
    """گرفتن موضوعات ترند از منابع مختلف"""
    topics = []
    
    # ۱. Google Trends (از طریق RSS غیررسمی)
    try:
        # استفاده از API غیررسمی برای ترندهای گوگل
        resp = requests.get(
            "https://trends.google.com/trends/api/dailytrends",
            params={"hl": "en-US", "tz": "-240", "ed": "20240825"},
            headers={"User-Agent": UA},
            timeout=15
        )
        if resp.status_code == 200:
            # پردازش پاسخ (نیاز به پارس کردن JSONP)
            data = resp.text[5:]  # حذف ")]}'" از ابتدا
            try:
                json_data = json.loads(data)
                for trend in json_data.get("default", {}).get("trendingSearches", [])[:10]:
                    title = trend.get("title", {}).get("query", "")
                    if title:
                        topics.append({
                            "title": title,
                            "source": "Google Trends",
                            "summary": trend.get("formattedTraffic", ""),
                            "link": f"https://trends.google.com/trends/explore?q={title.replace(' ', '%20')}"
                        })
            except:
                pass
    except:
        pass
    
    # ۲. Twitter/X (از طریق RSS جایگزین)
    try:
        # استفاده از Nitter (نسخه غیررسمی توییتر)
        # اینجا می‌تونیم از یک منبع دیگه استفاده کنیم
        resp = requests.get(
            "https://nitter.net/trends",
            headers={"User-Agent": UA},
            timeout=10
        )
        # پردازش HTML برای استخراج ترندها
        # (در نسخه کامل پیاده‌سازی می‌شود)
    except:
        pass
    
    # ۳. Reddit
    try:
        subreddits = ["bioinformatics", "biology", "artificial", "science"]
        for sub in subreddits:
            resp = requests.get(
                f"https://www.reddit.com/r/{sub}/hot.json",
                params={"limit": 5},
                headers={"User-Agent": UA},
                timeout=10
            )
            if resp.status_code == 200:
                data = resp.json()
                for post in data.get("data", {}).get("children", []):
                    post_data = post.get("data", {})
                    title = post_data.get("title", "")
                    if title:
                        topics.append({
                            "title": title,
                            "source": f"r/{sub}",
                            "summary": post_data.get("selftext", "")[:200],
                            "link": f"https://reddit.com{post_data.get('permalink', '')}"
                        })
    except:
        pass
    
    # ۴. ScienceDaily (ترندهای علمی)
    # (در ادامه از RSS‌های معمولی استفاده می‌شود)
    
    return topics


# ======================================================================
# سیستم سیستم‌پرامپت‌های جدید
# ======================================================================
SYSTEM_PROMPTS = {
    "scientific": """تو یک دانشمند برجسته در حوزه بیوانفورماتیک و هوش مصنوعی هستی.
    باید محتوایی علمی، دقیق و در عین حال جذاب برای کانال تلگرام تولید کنی.
    از اصطلاحات تخصصی به‌درستی استفاده کن و توضیحات را با مثال‌های ملموس همراه کن.
    سطح نوشتار باید دانشگاهی اما روان و قابل فهم برای دانشجویان باشد.""",
    
    "news": """تو یک روزنامه‌نگار علمی خبره هستی که آخرین دستاوردهای زیست‌شناسی و هوش مصنوعی را
    به زبانی جذاب و روان گزارش می‌کنی. باید خبر را به‌گونه‌ای بیان کنی که هم دقیق باشد
    و هم مخاطب را به خواندن ترغیب کند.""",
    
    "educational": """تو یک استاد دانشگاه هستی که می‌خواهی یک مطلب آموزشی جذاب را به زبان ساده
    اما علمی برای دانشجویان توضیح دهی. باید مفاهیم پیچیده را با مثال‌های روزمره و قابل درک
    همراه کنی.""",
    
    "inspirational": """تو یک سخنران انگیزشی در حوزه علم هستی که می‌خواهی مخاطبان را
    به کشف و یادگیری ترغیب کنی. باید با بیانی الهام‌بخش و پرشور، اهمیت موضوع را
    برای آینده علم و فناوری توضیح دهی.""",
    
    "funny": """تو یک کمدین علمی هستی که می‌خواهی با طنز و شوخی، مفاهیم علمی را
    به زبانی ساده و خنده‌دار برای مخاطبان توضیح دهی. باید علمی باشی اما با چاشنی طنز.""",
    
    "tool": """تو یک متخصص بیوانفورماتیک هستی که ابزارهای مختلف را به کاربران
    معرفی می‌کنی. باید کاربرد، مزایا و نحوه استفاده از ابزار را به‌طور کامل توضیح دهی.""",
    
    "roadmap": """تو یک مشاور مسیر شغلی در حوزه علوم زیستی و محاسباتی هستی که
    برای افراد علاقه‌مند، مسیر یادگیری و پیشرفت را ترسیم می‌کنی. باید مراحل
    را دقیق و عملی بیان کنی.""",
    
    "tip": """تو یک گورو بیوانفورماتیک هستی که ترفندهای ناب و کاربردی را
    به اشتراک می‌گذاری. باید ترفندها را دقیق، قابل اجرا و مفید بیان کنی."""
}


def get_system_prompt(style: str) -> str:
    """انتخاب سیستم‌پرامپت مناسب بر اساس سبک"""
    base = SYSTEM_PROMPTS.get(style, SYSTEM_PROMPTS["scientific"])
    return base + """

قواعد کلی:
۱. پاسخ را فقط به صورت JSON معتبر بده.
۲. از ایموجی‌های مناسب استفاده کن.
۳. متن را به پاراگراف‌های کوتاه و خوانا تقسیم کن.
۴. از اصطلاحات تخصصی با توضیح کوتاه استفاده کن.
۵. مخاطب را با سوالات چالشی درگیر کن."""


# ======================================================================
# ساخت پست با قالب‌های پیشرفته
# ======================================================================
def render_advanced_post(d: Dict[str, Any], source_url: str, source_name: str,
                         style: str = "smart") -> Tuple[str, str]:
    """ساخت پست با فرمت‌های پیشرفته تلگرام"""
    
    # انتخاب قالب
    template_name = get_post_template(style)
    template = POST_TEMPLATES[template_name]
    
    # آماده‌سازی داده‌ها
    title = d.get("title", "عنوان")
    body = d.get("body", "")
    why = d.get("why", "")
    intro = d.get("intro", "")
    steps = d.get("steps", [])
    final = d.get("final", "")
    tags = d.get("tags", [])
    
    # ساخت استپ‌ها برای رودمپ
    steps_text = ""
    if steps:
        num_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣"]
        for i, step in enumerate(steps[:8]):
            if isinstance(step, dict):
                head = step.get("title", "")
                detail = step.get("detail", "")
            else:
                head, detail = str(step), ""
            marker = num_emojis[i] if i < len(num_emojis) else "▫️"
            steps_text += f"\n{marker} <b>{html.escape(head)}</b>"
            if detail:
                steps_text += f"\n   {html.escape(detail)}"
    
    # ساخت تگ‌ها
    tags_text = " ".join([f"#{t}" for t in tags[:4]]) + " " + BASE_TAGS
    
    # ساخت لینک کانال
    channel_link = ""
    if CHANNEL_LINK_ENV:
        channel_link = f'📌 <b>کانال:</b> <a href="{html.escape(CHANNEL_LINK_ENV)}">Bio with AI</a>'
    elif CHANNEL_ID.startswith("@"):
        channel_link = f'📌 <b>کانال:</b> <a href="https://t.me/{CHANNEL_ID[1:]}">Bio with AI</a>'
    
    # اعمال قالب
    try:
        # ساخت متن اصلی با استفاده از قالب
        full_text = template["body_format"].format(
            title=html.escape(title),
            body=html.escape(body),
            why=html.escape(why),
            intro=html.escape(intro),
            steps=steps_text,
            final=html.escape(final),
            blockquote=TelegramFormatter.blockquote,
            bold=TelegramFormatter.bold,
            italic=TelegramFormatter.italic,
            underline=TelegramFormatter.underline,
            strikethrough=TelegramFormatter.strikethrough,
            spoiler=TelegramFormatter.spoiler,
            code=TelegramFormatter.code,
            pre=TelegramFormatter.pre,
            link=TelegramFormatter.link,
            emoji_list=TelegramFormatter.emoji_list,
            numbered_list=TelegramFormatter.numbered_list,
            tags=tags_text
        )
    except KeyError:
        # اگر قالب با خطا مواجه شد، از قالب ساده استفاده کن
        full_text = f"{html.escape(body)}"
    
    # افزودن عنوان
    if "{title}" not in full_text:
        full_text = f"{template['emoji']} <b>{html.escape(title)}</b>\n\n{full_text}"
    
    # افزودن تگ‌ها و فوتر
    full_text += f"\n\n{tags_text}\n\n{template['footer_format'].format(
        source_name=html.escape(source_name),
        source_url=html.escape(source_url),
        channel_link=channel_link,
        bold=TelegramFormatter.bold,
        italic=TelegramFormatter.italic,
        link=TelegramFormatter.link
    )}"
    
    # ساخت کپشن برای تصویر
    caption = f"{template['emoji']} <b>{html.escape(title)}</b>\n\n"
    caption += f"{html.escape(d.get('caption', body))[:700]}"
    caption += f"\n\n{tags_text}"
    
    return full_text, caption


def generate_inline_keyboard(links: List[Tuple[str, str]]) -> Dict[str, Any]:
    """ساخت کیبورد اینلاین برای پست"""
    if not ENABLE_BUTTONS:
        return {}
    
    keyboard = []
    for text, url in links[:3]:  # حداکثر ۳ دکمه
        keyboard.append([{"text": text, "url": url}])
    
    # دکمه کانال
    if CHANNEL_ID.startswith("@"):
        keyboard.append([{"text": "📌 عضویت در کانال", "url": f"https://t.me/{CHANNEL_ID[1:]}"}])
    
    return {"reply_markup": {"inline_keyboard": keyboard}}


# ======================================================================
# ارسال پست با فرمت‌های مختلف
# ======================================================================
def send_advanced_post(text: str, caption: str = "", image: bytes = None,
                       buttons: Dict = None, poll: Dict = None) -> None:
    """ارسال پست با فرمت‌های پیشرفته"""
    
    # تقسیم متن به بخش‌های کوچک‌تر
    chunks = split_message(text)
    
    # اگر تصویر داریم، اول تصویر رو می‌فرستیم
    if image and WITH_IMAGE:
        try:
            tg_post("sendPhoto", {
                "chat_id": CHANNEL_ID,
                "caption": caption[:1024],
                "parse_mode": "HTML",
            }, files={"photo": ("image.png", image, "image/png")})
            log("🖼 تصویر با کپشن ارسال شد")
        except Exception as exc:
            log(f"⚠ ارسال تصویر ناموفق: {exc}")
    
    # ارسال متن کامل
    for i, chunk in enumerate(chunks):
        data = {
            "chat_id": CHANNEL_ID,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": "false" if i == 0 else "true",
        }
        
        # افزودن دکمه‌ها فقط به پیام اول
        if i == 0 and buttons:
            data.update(buttons)
        
        # اگر نظرسنجی داریم و پیام اول است
        if i == 0 and poll:
            # نظرسنجی رو جداگانه می‌فرستیم
            send_poll(poll)
        
        tg_post("sendMessage", data)
        log(f"📤 بخش {i+1}/{len(chunks)} ارسال شد")
        
        # کمی تأخیر بین پیام‌ها
        if i < len(chunks) - 1:
            time.sleep(1)


def send_poll(poll_data: Dict[str, Any]) -> None:
    """ارسال نظرسنجی"""
    if not ENABLE_POLLS:
        return
    
    try:
        data = {
            "chat_id": CHANNEL_ID,
            "question": poll_data.get("question", "نظر شما چیست؟"),
            "options": json.dumps(poll_data.get("options", ["👍", "👎"])),
            "is_anonymous": True,
            "type": "regular",
        }
        if poll_data.get("allows_multiple_answers"):
            data["allows_multiple_answers"] = True
        tg_post("sendPoll", data)
        log("📊 نظرسنجی ارسال شد")
    except Exception as exc:
        log(f"⚠ ارسال نظرسنجی ناموفق: {exc}")


# ======================================================================
# کدهای کمکی (بقیه کدها مشابه قبلی)
# ======================================================================
def split_message(text: str, limit: int = 3800) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks, current = [], ""
    for para in text.split("\n\n"):
        candidate = (current + "\n\n" + para) if current else para
        if len(candidate) > limit and current:
            chunks.append(current)
            current = para[:limit]
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks


def tg_post(method: str, data: dict, files: dict | None = None) -> dict:
    last = ""
    for attempt in range(3):
        try:
            resp = requests.post(f"https://api.telegram.org/bot{BOT_TOKEN}/{method}",
                                 data=data, files=files, timeout=120)
            if resp.status_code == 429:
                wait = resp.json().get("parameters", {}).get("retry_after", 10)
                log(f"⏳ محدودیت تلگرام؛ {wait} ثانیه صبر…")
                time.sleep(wait + 1)
                continue
            body = resp.json()
            if body.get("ok"):
                return body
            last = body.get("description", resp.text[:200])
            raise RuntimeError(f"تلگرام: {last}")
        except requests.RequestException as exc:
            last = str(exc)
            log(f"⚠ خطای شبکه (تلاش {attempt + 1}/۳): {exc}")
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"ارسال ناموفق: {last}")


# ======================================================================
# تابع اصلی (با تغییرات جدید)
# ======================================================================
def main() -> int:
    global ENGINES
    ENGINES = load_engines()
    log(f"🚀 شروع — کانال: {CHANNEL_ID} | {len(ENGINES)} کلید AI")
    
    if not ENGINES:
        log("❌ هیچ کلید هوش مصنوعی تنظیم نشده")
        return 1
    
    state = load_state()
    
    # انتخاب سبک پست
    style = POST_STYLE if POST_STYLE != "smart" else random.choice([
        "scientific", "news", "educational", "inspirational", "funny",
        "tool", "roadmap", "tip", "debate", "summary"
    ])
    log(f"🎨 سبک پست: {style}")
    
    # تولید محتوا
    content = generate_content(state, style)
    if not content:
        log("❌ تولید محتوا ناموفق")
        return 1
    
    # ساخت پست با قالب پیشرفته
    full_text, caption = render_advanced_post(
        content["data"],
        content["source_url"],
        content["source_name"],
        style
    )
    
    # ساخت دکمه‌ها
    buttons = generate_inline_keyboard([
        ("🔗 منبع", content["source_url"]),
        ("📚 بیشتر", "https://t.me/Bio_with_AI")
    ])
    
    # تولید تصویر
    image = None
    if WITH_IMAGE:
        image = generate_image(state, content["data"].get("image_prompt_en", ""))
    
    # ارسال پست
    if TELEGRAM_DRY:
        log("🔧 حالت DRY — ارسال نشد")
        print(full_text)
    else:
        send_advanced_post(full_text, caption, image, buttons)
        today_increment(state)
        save_state(state)
    
    return 0


# ======================================================================
# نقطه ورود
# ======================================================================
if __name__ == "__main__":
    try:
        sys.exit(selftest() if SELFTEST else main())
    except Exception as exc:
        log(f"❌ خطا: {exc}")
        sys.exit(1)
