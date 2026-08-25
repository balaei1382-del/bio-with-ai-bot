#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bio with AI — ربات همه‌فن‌حریف کانال تلگرام
با پشتیبانی از Nano Banana برای تولید تصویر
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

import feedparser
import requests

# ----------------------------------------------------------------------
# تنظیمات عمومی
# ----------------------------------------------------------------------
BOT_TOKEN      = os.environ.get("BOT_TOKEN", "").strip()
CHANNEL_ID     = os.environ.get("CHANNEL_ID", "@Bio_with_AI").strip()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
AI_CONFIG      = os.environ.get("AI_CONFIG", "").strip()

FALLBACK_GEMINI_MODELS = [m.strip() for m in os.environ.get("GEMINI_MODELS",
    "gemini-3.6-flash, gemini-3.7-flash, gemini-2.5-flash").split(",") if m.strip()]

# مدل‌های تصویری Nano Banana (به ترتیب اولویت)
NANO_BANANA_MODELS = [
    "gemini-3.1-flash-image",           # جدیدترین Nano Banana
    "gemini-3.1-flash-lite-image",      # نسخه سبک
    "gemini-3.1-flash-image-preview",   # نسخه پیش‌نمایش
    "gemini-3-pro-image",               # نسخه Pro
    "gemini-3-pro-image-preview",       # نسخه Pro پیش‌نمایش
    "gemini-2.5-flash-image",           # Nano Banana اصلی
]

INCLUDE_PRO = os.environ.get("INCLUDE_PRO", "0") == "1"
CHANNEL_LINK_ENV = os.environ.get("CHANNEL_LINK", "").strip()

MAX_AGE_DAYS   = int(os.environ.get("MAX_AGE_DAYS", "10"))
FORCE_TYPE     = os.environ.get("FORCE_TYPE", "").strip().lower()
CONTENT_MIX    = os.environ.get("CONTENT_MIX", "news:4,trend:4,tip:3,roadmap:2,tool:2")
WITH_IMAGE     = os.environ.get("WITH_IMAGE", "1") == "1"
FULL_TEXT_AFTER_IMAGE = os.environ.get("FULL_TEXT_AFTER_IMAGE", "1") == "1"
BASE_TAGS      = os.environ.get("BASE_TAGS", "#بیوانفورماتیک #زیست_شناسی #هوش_مصنوعی").strip()

DAILY_MIN = int(os.environ.get("DAILY_MIN", "20"))
DAILY_MAX = int(os.environ.get("DAILY_MAX", "30"))
FORCE_POST = os.environ.get("FORCE_POST", "") == "1"

DRY_RUN   = "--dry-run" in sys.argv
SELFTEST  = "--selftest" in sys.argv
MOCK_LLM  = os.environ.get("MOCK_LLM", "") == "1"
TELEGRAM_DRY = os.environ.get("TELEGRAM_DRY", "") == "1"

TEHRAN_TZ = timezone(timedelta(hours=3, minutes=30))
ROOT = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(ROOT, "state", "posted.json")

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# ======================================================================
#  موتورهای هوش مصنوعی
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
            raise RuntimeError(f"AI_CONFIG معتبر نیست: {exc}")
        global PINNED_GEMINI_MODELS
        PINNED_GEMINI_MODELS = [str(m).strip() for m in cfg.get("gemini_models", []) if str(m).strip()]
        default_models = PINNED_GEMINI_MODELS or FALLBACK_GEMINI_MODELS
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
        engines.append(Engine("gemini", legacy, PINNED_GEMINI_MODELS or FALLBACK_GEMINI_MODELS))
    return engines


ENGINES: list[Engine] = []
PINNED_GEMINI_MODELS: list[str] = []


# ----------------------------------------------------------------------
#  کشف خودکار مدل‌ها
# ----------------------------------------------------------------------
BAD_GEMINI = ("tts", "embedding", "aqa", "native-audio", "live",
              "veo", "imagen", "learnlm", "gemma", "robotics", "lyria",
              "computer-use", "antigravity", "deep-research")


def _model_version(name: str) -> float:
    m = re.search(r"(\d+(?:\.\d+)?)", name)
    return float(m.group(1)) if m else 0.0


def rank_gemini_models(ids: list[str], pinned: list[str] | None = None) -> list[str]:
    pinned = pinned or []
    ids = list(dict.fromkeys(ids))
    chat, chosen = [], []
    for i in ids:
        s = i.lower()
        if any(b in s for b in BAD_GEMINI):
            continue
        if "image" in s:
            continue  # مدل‌های تصویری جداگانه استفاده می‌شن
        if not INCLUDE_PRO and ("pro" in s or "ultra" in s):
            continue
        if i in pinned and i not in chosen:
            chosen.append(i)
        elif i not in chosen:
            chat.append(i)
    chat.sort(key=lambda i: ("flash" not in i.lower(), -_model_version(i), len(i)))
    return (chosen + chat)[:4]


def refresh_gemini_models(state: dict, force: bool = False) -> None:
    cache = state.setdefault("model_cache", {})
    today = datetime.now(TEHRAN_TZ).strftime("%Y-%m-%d")
    if not force and cache.get("gemini_date") == today and cache.get("gemini_models"):
        return
    for e in ENGINES:
        if e.kind != "gemini":
            continue
        try:
            r = requests.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                params={"key": e.api_key, "pageSize": 200}, timeout=30,
            )
            r.raise_for_status()
            chat_ids = []
            for m in r.json().get("models", []):
                if "generateContent" not in m.get("supportedGenerationMethods", []):
                    continue
                mid = (m.get("name") or "").split("/")[-1]
                if not mid:
                    continue
                if any(b in mid.lower() for b in BAD_GEMINI):
                    continue
                if "image" in mid.lower():
                    continue
                chat_ids.append(mid)
            if chat_ids:
                ranked = rank_gemini_models(chat_ids, PINNED_GEMINI_MODELS)
                cache.update(gemini_date=today, gemini_models=ranked)
                for eng2 in ENGINES:
                    if eng2.kind == "gemini":
                        eng2.models = ranked
                log(f"🔎 مدل‌های متنی: {ranked}")
                return
        except Exception as exc:
            log(f"⚠ کشف مدل‌ها نشد: {str(exc)[:90]}")
    log("⚠ استفاده از مدل‌های پیش‌فرض")


def load_state() -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"links": [], "topics": [], "cooldowns": {}, "dead_engines": [], "today": {}}


def save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    state["links"] = state.get("links", [])[-400:]
    state["topics"] = state.get("topics", [])[-400:]
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)


def set_cooldown(state: dict, cid: str, minutes: int = 90) -> None:
    state.setdefault("cooldowns", {})[cid] = (
        datetime.now(timezone.utc) + timedelta(minutes=minutes)
    ).isoformat()


def mark_dead(state: dict, eng: Engine) -> None:
    if eng.id not in state.setdefault("dead_engines", []):
        state["dead_engines"].append(eng.id)


def candidate_id(eng: Engine, model: str) -> str:
    return f"{eng.id}|{model}"


def ordered_candidates(state: dict) -> list[tuple[Engine, str]]:
    now = datetime.now(timezone.utc)
    dead = set(state.get("dead_engines", []))
    cands = [(e, m) for e in ENGINES if e.id not in dead for m in e.models]
    ready = [c for c in cands if not state.get("cooldowns", {}).get(candidate_id(*c))]
    if not ready:
        state["cooldowns"] = {}
        ready = cands
    return ready


def extract_json(text: str) -> dict:
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    start = text.find("{")
    if start < 0:
        raise ValueError("JSON یافت نشد")
    try:
        return json.loads(text[start:])
    except json.JSONDecodeError:
        obj, _ = json.JSONDecoder().raw_decode(text[start:])
        return obj


def llm_gemini(eng: Engine, model: str, system: str, user: str) -> str:
    resp = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        params={"key": eng.api_key},
        json={
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {
                "temperature": 0.8, "topP": 0.95, "maxOutputTokens": 4096,
                "responseMimeType": "application/json",
            },
        },
        timeout=120,
    )
    if resp.status_code == 200:
        return resp.json()["candidates"][0]["content"]["parts"][0]["text"]
    raise RuntimeError(f"gemini {model} HTTP {resp.status_code}: {resp.text[:180]}")


def llm_openai(eng: Engine, model: str, system: str, user: str) -> str:
    resp = requests.post(
        f"{eng.base_url}/chat/completions",
        headers={"Authorization": f"Bearer {eng.api_key}"},
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0.8,
            "max_tokens": 4000,
        },
        timeout=150,
    )
    if resp.status_code == 200:
        return resp.json()["choices"][0]["message"]["content"]
    raise RuntimeError(f"{model} HTTP {resp.status_code}: {resp.text[:180]}")


MOCK_RESPONSE = json.dumps({
    "title": "هوش مصنوعی ساختار پروتئین‌ها را در چند ثانیه رمزگشایی می‌کند",
    "body": "پژوهشگران با ترکیب مدل‌های زبانی بزرگ و داده‌های ساختاری موفق شدند فرایند پیش‌بینی ساختار پروتئین را ده‌ها برابر سریع‌تر کنند.",
    "why": "این روش تحلیل شبکه‌های مولکولی را در چند دقیقه انجام می‌دهد.",
    "caption": "مدل تازه هوش مصنوعی، پیش‌بینی ساختار پروتئین را ده‌ها برابر سریع‌تر کرد.",
    "image_prompt_en": "Clean scientific illustration of an AI neural network analyzing a glowing 3D protein structure, modern infographic style, blue and green palette",
    "tags": ["پروتئین", "هوش_مصنوعی", "طراحی_دارو"],
}, ensure_ascii=False)


def call_llm(state: dict, system: str, user: str) -> dict:
    if MOCK_LLM or SELFTEST:
        return extract_json(MOCK_RESPONSE)
    errors = []
    for eng, model in ordered_candidates(state):
        fn = llm_gemini if eng.kind == "gemini" else llm_openai
        try:
            raw = fn(eng, model, system, user)
            parsed = extract_json(raw)
            log(f"✔ پاسخ از {candidate_id(eng, model)}")
            return parsed
        except Exception as exc:
            msg = str(exc)
            errors.append(f"{candidate_id(eng, model)}: {msg[:160]}")
            if " 429" in msg:
                set_cooldown(state, candidate_id(eng, model), minutes=15)
                time.sleep(3)
            elif " 401" in msg or " 403" in msg:
                mark_dead(state, eng)
            else:
                log(f"⚠ {candidate_id(eng, model)}: {msg[:140]}")
                time.sleep(2)
    raise RuntimeError("هیچ‌کدام از موتورهای هوش مصنوعی پاسخ ندادند:\n" + "\n".join(errors[:8]))


# ----------------------------------------------------------------------
# تولید تصویر با Nano Banana (جمینای)
# ----------------------------------------------------------------------
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQAB"
    "h6FO1AAAAABJRU5ErkJggg=="
)


def generate_image(state: dict, prompt_en: str) -> bytes | None:
    """تولید تصویر با Nano Banana (جمینای) - با retry و تعویض مدل"""
    if MOCK_LLM or SELFTEST:
        return TINY_PNG
    
    gemini_keys = [e for e in ENGINES if e.kind == "gemini" and e.id not in state.get("dead_engines", [])]
    
    if not gemini_keys:
        log("⚠ تصویر: هیچ کلید جمینای زنده‌ای نیست")
        return None
    
    # ترکیب‌های (کلید، مدل) برای تست
    combinations = []
    for eng in gemini_keys:
        for model in NANO_BANANA_MODELS:
            combinations.append((eng, model))
    
    log(f"🎨 تلاش برای تولید تصویر با {len(combinations)} ترکیب کلید/مدل...")
    
    for attempt, (eng, model) in enumerate(combinations):
        log(f"🖼 تلاش {attempt + 1}/{len(combinations)}: {model} روی کلید ...{eng.api_key[-6:]}")
        
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            
            payload = {
                "contents": [{
                    "role": "user",
                    "parts": [{
                        "text": f"Generate a high-quality scientific illustration: {prompt_en}"
                    }]
                }],
                "generationConfig": {
                    "responseModalities": ["IMAGE", "TEXT"],
                    "temperature": 0.4
                }
            }
            
            resp = requests.post(
                url,
                params={"key": eng.api_key},
                json=payload,
                timeout=90
            )
            
            if resp.status_code == 200:
                body = resp.json()
                
                # بررسی تصویر
                candidates = body.get("candidates", [])
                for cand in candidates:
                    parts = cand.get("content", {}).get("parts", [])
                    for part in parts:
                        # روش 1: inlineData
                        if "inlineData" in part:
                            data = part["inlineData"].get("data", "")
                            if data:
                                try:
                                    image = base64.b64decode(data)
                                    if len(image) > 1000:
                                        log(f"✅ تصویر با {model} ساخته شد ({len(image) // 1024} KB)")
                                        return image
                                except Exception as exc:
                                    log(f"⚠ خطای decode: {exc}")
                        
                        # روش 2: fileData
                        if "fileData" in part:
                            file_uri = part["fileData"].get("fileUri", "")
                            if file_uri:
                                log(f"📁 دانلود از: {file_uri}")
                                img_resp = requests.get(file_uri, timeout=30)
                                if img_resp.status_code == 200 and len(img_resp.content) > 1000:
                                    log(f"✅ تصویر دانلود شد ({len(img_resp.content) // 1024} KB)")
                                    return img_resp.content
                
                log(f"⚠ {model}: پاسخ 200 ولی بدون تصویر")
                
            elif resp.status_code == 429:
                log(f"⏳ {model}: محدودیت نرخ - صبر ۵ ثانیه...")
                time.sleep(5)
                continue
                
            elif resp.status_code == 404:
                log(f"❌ {model}: وجود ندارد")
                continue
                
            elif resp.status_code in (401, 403):
                log(f"⛔ کلید ...{eng.api_key[-6:]} نامعتبر")
                mark_dead(state, eng)
                break
                
            else:
                log(f"⚠ {model}: HTTP {resp.status_code} - {resp.text[:100]}")
                continue
                
        except requests.Timeout:
            log(f"⏱ {model}: تایم‌اوت")
            continue
        except Exception as exc:
            log(f"⚠ {model}: خطا - {str(exc)[:100]}")
            continue
        
        # فاصله بین درخواست‌ها
        time.sleep(3)
    
    log("❌ تولید تصویر با همه مدل‌ها ناموفق بود")
    return None


# ======================================================================
#  منابع خبری
# ======================================================================
FEEDS = [
    {"url": "https://www.sciencedaily.com/rss/plants_animals/biology.xml",   "name": "ScienceDaily Biology"},
    {"url": "https://www.sciencedaily.com/rss/computers_math/artificial_intelligence.xml", "name": "ScienceDaily AI"},
    {"url": "https://www.sciencedaily.com/rss/computers_math/computer_science.xml", "name": "ScienceDaily Computers"},
    {"url": "https://www.sciencedaily.com/rss/plants_animals/evolution.xml", "name": "ScienceDaily Evolution"},
    {"url": "https://phys.org/rss-feed/biology-news/",                       "name": "Phys.org Biology"},
    {"url": "https://www.nature.com/nature.rss",                             "name": "Nature"},
    {"url": "https://www.nature.com/nbt.rss",                                "name": "Nature Biotechnology"},
    {"url": "https://www.nature.com/nmeth.rss",                              "name": "Nature Methods"},
    {"url": "https://connect.biorxiv.org/biorxiv_xml.php?subject=bioinformatics", "name": "bioRxiv Bioinformatics"},
    {"url": "https://journals.plos.org/ploscompbiol/feed/atom",              "name": "PLOS Comp Biology"},
]

ROADMAP_FEEDS = {"bioRxiv Bioinformatics", "PLOS Comp Biology", "Nature Methods", "Nature Biotechnology"}

RELEVANT_KEYWORDS = [
    "gene", "genome", "genomic", "genetic", "protein", "dna", "rna", "seq",
    "cell", "cancer", "tumor", "disease", "drug", "vaccine", "evolution",
    "species", "plant", "animal", "microb", "bacteri", "virus", "viral",
    "brain", "neuro", "enzyme", "molecular", "bio", "crispr", "immune",
    "ecolog", "crops", "agricult", "medic", "health", "clinic", "aging",
    "stem cell", " ai ", "ai-", "machine learning", "deep learning",
    "neural network", "algorithm", "computational", "omics", "transcriptom",
    "proteom", "metabolom", "microbiom", "phylogen", "biotech",
]


def is_relevant(title: str, summary: str) -> bool:
    text = (title + " " + summary).lower()
    return any(k in text for k in RELEVANT_KEYWORDS)


def clean_source_url(link: str, source_name: str = "") -> str:
    if not link:
        return ""
    link = link.strip()
    if "nature.com" in link:
        link = re.sub(r'\?.*$', '', link)
        if link.endswith(('.rss', '.xml')):
            link = link.rsplit('.', 1)[0]
        return link
    elif "sciencedaily.com" in link:
        return re.sub(r'\?.*$', '', link)
    elif "biorxiv.org" in link:
        if "content" in link and not link.endswith(".full"):
            return link + ".full"
        return link
    elif "phys.org" in link:
        return link
    elif "plos.org" in link:
        return link
    elif "trends.google.com" in link:
        return link
    elif "news.ycombinator.com" in link or "hnrss.org" in link:
        return link
    if link.endswith(('.xml', '.rss', '.atom')):
        link = link.rsplit('.', 1)[0]
    return link


def fetch_feed_items(only_roadmap_pool: bool = False) -> list[dict]:
    cutoff = datetime.now(timezone.utc) - timedelta(days=MAX_AGE_DAYS)
    items = []
    for feed in FEEDS:
        if only_roadmap_pool and feed["name"] not in ROADMAP_FEEDS:
            continue
        try:
            resp = requests.get(feed["url"], timeout=30, headers={"User-Agent": UA})
            resp.raise_for_status()
            parsed = feedparser.parse(resp.content)
            count = 0
            for e in parsed.entries:
                title = (getattr(e, "title", "") or "").strip()
                raw_link = (getattr(e, "link", "") or "").strip()
                if not title or not raw_link:
                    continue
                link = clean_source_url(raw_link, feed["name"])
                summary = re.sub(r"<[^>]+>", " ", getattr(e, "summary", "") or "").strip()[:2000]
                pub = getattr(e, "published_parsed", None) or getattr(e, "updated_parsed", None)
                if pub is not None and datetime(*pub[:6], tzinfo=timezone.utc) < cutoff:
                    continue
                if not is_relevant(title, summary):
                    continue
                items.append({"title": title, "link": link, "summary": summary, "source": feed["name"]})
                count += 1
            log(f"✔ {feed['name']}: {count} مورد تازه")
        except Exception as exc:
            log(f"✖ {feed['name']}: خطا ({exc})")
    random.shuffle(items)
    return items


TREND_FEEDS = [
    {"url": "https://trends.google.com/trending/rss?geo=US", "name": "Google Trends (US)"},
    {"url": "https://trends.google.com/trending/rss?geo=GB", "name": "Google Trends (UK)"},
    {"url": "https://hnrss.org/frontpage", "name": "Hacker News"},
]


def fetch_trend_items() -> list[dict]:
    items = []
    for feed in TREND_FEEDS:
        try:
            resp = requests.get(feed["url"], timeout=20, headers={"User-Agent": UA})
            resp.raise_for_status()
            parsed = feedparser.parse(resp.content)
            count = 0
            for e in parsed.entries[:15]:
                title = (getattr(e, "title", "") or "").strip()
                raw_link = (getattr(e, "link", "") or "").strip()
                if not title or not raw_link:
                    continue
                link = clean_source_url(raw_link, feed["name"])
                summary = re.sub(r"<[^>]+>", " ", getattr(e, "summary", "") or "").strip()[:1000]
                items.append({"title": title, "link": link, "summary": summary, "source": feed["name"]})
                count += 1
            log(f"✔ {feed['name']}: {count} ترند")
        except Exception as exc:
            log(f"✖ {feed['name']}: خطا ({exc})")
    random.shuffle(items)
    return items


# ======================================================================
#  بانک ابزارها
# ======================================================================
TOPIC_BANK = [
    {"name": "Galaxy Project", "url": "https://usegalaxy.org", "fa": "سرور آنلاین تحلیل داده‌های ژنومیک"},
    {"name": "NCBI BLAST", "url": "https://blast.ncbi.nlm.nih.gov/Blast.cgi", "fa": "جست‌وجوی تشابه توالی"},
    {"name": "AlphaFold DB", "url": "https://alphafold.ebi.ac.uk", "fa": "پیش‌بینی ساختار پروتئین"},
    {"name": "UniProt", "url": "https://www.uniprot.org", "fa": "پایگاه داده پروتئین"},
    {"name": "Ensembl", "url": "https://www.ensembl.org", "fa": "پایگاه ژنوم"},
    {"name": "UCSC Genome Browser", "url": "https://genome.ucsc.edu", "fa": "مرورگر ژنوم"},
    {"name": "KEGG", "url": "https://www.genome.jp/kegg", "fa": "مسیرهای متابولیک"},
    {"name": "STRING", "url": "https://string-db.org", "fa": "شبکه پروتئین"},
    {"name": "Biopython", "url": "https://biopython.org", "fa": "کتابخانه پایتون"},
    {"name": "Bioconda", "url": "https://bioconda.github.io", "fa": "نصب ابزار بیوانفورماتیک"},
    {"name": "QIIME 2", "url": "https://qiime2.org", "fa": "تحلیل میکروبیوم"},
    {"name": "Snakemake", "url": "https://snakemake.github.io", "fa": "مدیریت ورک‌فلو"},
    {"name": "Nextflow", "url": "https://www.nextflow.io", "fa": "ورک‌فلو موازی"},
    {"name": "GATK", "url": "https://gatk.broadinstitute.org", "fa": "تنوع‌یابی ژنومی"},
    {"name": "Cytoscape", "url": "https://cytoscape.org", "fa": "شبکه‌های مولکولی"},
    {"name": "PyMOL", "url": "https://pymol.org", "fa": "تصویرسازی پروتئین"},
    {"name": "GROMACS", "url": "https://www.gromacs.org", "fa": "دینامیک مولکولی"},
    {"name": "IQ-TREE", "url": "http://www.iqtree.org", "fa": "درخت فیلوژنتیک"},
    {"name": "InterPro", "url": "https://www.ebi.ac.uk/interpro", "fa": "دامنه پروتئینی"},
    {"name": "Reactome", "url": "https://reactome.org", "fa": "مسیرهای بیولوژیکی"},
    {"name": "Gene Ontology", "url": "http://geneontology.org", "fa": "واژه‌نامه ژن"},
    {"name": "DAVID", "url": "https://david.ncifcrf.gov", "fa": "غنی‌سازی ژنی"},
    {"name": "DESeq2", "url": "https://bioconductor.org/packages/release/bioc/html/DESeq2.html", "fa": "بیان افتراقی ژن"},
    {"name": "Seurat", "url": "https://satijalab.org/seurat", "fa": "تک‌سلولی در R"},
    {"name": "Scanpy", "url": "https://scanpy.readthedocs.io", "fa": "تک‌سلولی در پایتون"},
    {"name": "ColabFold", "url": "https://colabfold.colab.google", "fa": "AlphaFold2 رایگان"},
    {"name": "BUSCO", "url": "https://busco.ezlab.org", "fa": "کیفیت ژنوم"},
    {"name": "Prokka", "url": "https://github.com/tseemann/prokka", "fa": "حاشیه‌نویسی ژنوم"},
    {"name": "BWA", "url": "https://github.com/lh3/bwa", "fa": "هم‌ترازسازی DNA"},
    {"name": "Samtools", "url": "https://www.htslib.org", "fa": "پردازش SAM/BAM"},
    {"name": "FastQC", "url": "https://www.bioinformatics.babraham.ac.uk/projects/fastqc", "fa": "کنترل کیفیت"},
    {"name": "RCSB PDB", "url": "https://www.rcsb.org", "fa": "ساختار پروتئین"},
    {"name": "ChEMBL", "url": "https://www.ebi.ac.uk/chembl", "fa": "مولکول دارویی"},
    {"name": "GTEx", "url": "https://gtexportal.org", "fa": "بیان ژن بافت"},
]

TIP_ANGLES = [
    "یک ترفند کمترشناخته‌شده اما بسیار کاربردی",
    "یک اشتباه رایج کاربران و روش درست انجام کار",
    "یک بهینه‌سازی سرعت یا حافظه واقعی",
    "یک گردش‌کاری پیشنهادی گام‌به‌گام",
    "یک قابلیت مخفی یا گزینه پیشرفته",
    "یک ترفند خط فرمان یا چندخط کد",
]


# ======================================================================
#  ساخت پست
# ======================================================================
SYSTEM_PROMPT = """تو ادمین یک کانال تلگرام فارسی‌زبان به نام «Bio with AI» هستی؛ مخاطبانت دانشجویان، پژوهشگران و علاقه‌مندان زیست‌شناسی، بیوانفورماتیک و هوش مصنوعی‌اند.

لحن: مثل یک آدم واقعی و باحال که خیلی علم بلده صحبت کن، نه مثل یک روبات. جمله اول باید مثل قلاب باشه.

قواعد:
۱. علمی و دقیق باش؛ اما هرگز خشک و رسمی ننویس.
۲. هیچ داده یا ادعایی را از خودت نساز.
۳. ایموجی را زنده و به‌جا به‌کار ببر (تا ۴-۵ تا).
۴. از قالب‌بندی تلگرام استفاده کن:
   - **پررنگ** → <b>
   - __زیرخط__ → <u>
   - ~~خط‌خورده~~ → <s>
   - `کد` → <code>
   - ||اسپویلر|| → <tg-spoiler>
۵. پاسخ را فقط و فقط به شکل JSON معتبر بده."""


def sanitize_tags(tags: list[str]) -> str:
    clean = []
    for t in tags or []:
        t = str(t).strip().replace(" ", "_")
        t = re.sub(r"[^\w\u0600-\u06FF_]", "", t)
        if len(t) > 2 and not t.isdigit():
            clean.append("#" + t)
        if len(clean) >= 4:
            break
    return " ".join(clean)


def esc(text: str) -> str:
    return html.escape(str(text or ""), quote=False)


def format_inline(text: str) -> str:
    t = esc(text)
    t = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = re.sub(r"__(.+?)__", r"<u>\1</u>", t)
    t = re.sub(r"~~(.+?)~~", r"<s>\1</s>", t)
    t = re.sub(r"`([^`\n]+?)`", r"<code>\1</code>", t)
    t = re.sub(r"\|\|(.+?)\|\|", r"<tg-spoiler>\1</tg-spoiler>", t)
    return t


def render_code(code: dict | None) -> str:
    if not isinstance(code, dict):
        return ""
    snippet = str(code.get("snippet") or "").strip()
    if not snippet:
        return ""
    lang = re.sub(r"[^a-zA-Z0-9_+-]", "", str(code.get("lang") or "")).lower()
    cls = f' class="language-{lang}"' if lang else ""
    return f"<pre><code{cls}>{esc(snippet)}</code></pre>"


def esc_url(url: str) -> str:
    url = (url or "").strip()
    if not url.startswith("http"):
        url = "https://example.com"
    return html.escape(url, quote=True)


def channel_link() -> str:
    if CHANNEL_LINK_ENV:
        return CHANNEL_LINK_ENV
    if CHANNEL_ID.startswith("@"):
        return f'https://t.me/{CHANNEL_ID[1:]}'
    return ""


def footer(source_url: str, source_name: str) -> str:
    link = channel_link()
    name = CHANNEL_ID.lstrip("@") if CHANNEL_ID.startswith("@") else "Bio with AI"
    chan = (f'📌 <b>کانال:</b> <a href="{html.escape(link, quote=True)}">{esc(name)}</a>'
            if link else "📌 <b>کانال:</b> Bio with AI")
    return (
        f'🔗 <b>منبع:</b> <a href="{esc_url(source_url)}">{esc(source_name)}</a>\n'
        + chan
    )


def render_post(d: dict, source_url: str, source_name: str, emoji: str = "🧬") -> str:
    tags = (sanitize_tags(d.get("tags")) + " " + BASE_TAGS).strip()
    parts = [f"{emoji} <b>{esc(d['title'])}</b>"]
    if d.get("hook"):
        parts += ["", f"<i>{format_inline(d['hook'])}</i>"]
    parts += ["", format_inline(d["body"])]
    if d.get("why"):
        qtag = "blockquote expandable" if len(d["why"]) > 140 else "blockquote"
        parts += ["", "💡 <b>چرا مهم است؟</b>", f"<{qtag}>{format_inline(d['why'])}</{qtag.split()[0]}>"]
    code_block = render_code(d.get("code"))
    if code_block:
        parts += ["", code_block]
    if d.get("fun_fact"):
        parts += ["", "🎁 <b>یک نکته جالب</b> (لمس کن):", f"<tg-spoiler>{format_inline(d['fun_fact'])}</tg-spoiler>"]
    parts += ["", tags, "", footer(source_url, source_name)]
    post = "\n".join(parts)
    if len(post) > 4000:
        post = post[:3990] + "\n…"
    return post


def render_roadmap(d: dict, source_url: str, source_name: str) -> str:
    num_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣"]
    lines = [f"🗺 <b>{esc(d['title'])}</b>"]
    if d.get("hook"):
        lines += ["", f"<i>{format_inline(d['hook'])}</i>"]
    lines += ["", format_inline(d.get("intro", "")), "", "🎯 <b>مسیر پیشنهادی:</b>"]
    for i, step in enumerate(d.get("steps", [])[:8]):
        if isinstance(step, dict):
            head, body = step.get("title", ""), step.get("detail", "")
        else:
            head, body = str(step), ""
        marker = num_emojis[i] if i < len(num_emojis) else "▫️"
        lines.append(f"{marker} <b>{esc(head)}</b>")
        if body:
            lines.append(f"   {format_inline(body)}")
    if d.get("final"):
        lines += ["", "✅ <b>سخن پایانی:</b>", f"<blockquote>{format_inline(d['final'])}</blockquote>"]
    code_block = render_code(d.get("code"))
    if code_block:
        lines += ["", code_block]
    if d.get("fun_fact"):
        lines += ["", "🎁 <b>یک نکته جالب</b> (لمس کن):", f"<tg-spoiler>{format_inline(d['fun_fact'])}</tg-spoiler>"]
    tags = (sanitize_tags(d.get("tags")) + " " + BASE_TAGS).strip()
    lines += ["", tags, "", footer(source_url, source_name)]
    post = "\n".join(lines)
    if len(post) > 4000:
        post = post[:3990] + "\n…"
    return post


def build_caption(d: dict, source_url: str, source_name: str, emoji: str) -> str:
    cap = (
        f"{emoji} <b>{esc(d['title'])}</b>\n\n"
        f"{format_inline(d.get('caption') or d['body'])}\n\n"
        + footer(source_url, source_name)
    )
    if len(cap) > 1000:
        cap = cap[:990].rsplit(" ", 1)[0] + "…\n\n" + footer(source_url, source_name)
    return cap


COMMON_JSON_FIELDS = """,
  "hook": "یک جمله کوتاه و قلاب‌مانند برای ابتدای پست — حداکثر ۱۲ کلمه",
  "fun_fact": "یک نکته جالب واقعی؛ اگر نیست رشته خالی",
  "caption": "خلاصه ۳-۴ خطی برای زیرنویس تصویر",
  "image_prompt_en": "توضیح انگلیسی یک جمله‌ای برای ساخت تصویر علمی",
  "tags": ["سه یا چهار هشتگ فارسی"],
  "poll_question": "سوال نظرسنجی؛ اگر مناسب نیست رشته خالی",
  "poll_options": ["گزینه‌های نظرسنجی؛ اگر poll_question خالی است آرایه خالی"]"""


def build_news(state: dict, item: dict) -> tuple[dict, str, str, str]:
    prompt = f"""خبر علمی زیر را به پست تلگرامی فارسی تبدیل کن.

عنوان: {item['title']}
منبع: {item['source']}
لینک: {item['link']}
خلاصه: {item['summary']}

JSON با این ساختار:
{{
  "title": "عنوان فارسی (حداکثر ۱۰ کلمه)",
  "body": "متن ۴-۷ خطی"{COMMON_JSON_FIELDS}
}}"""
    d = call_llm(state, SYSTEM_PROMPT, prompt)
    return d, item["link"], item["source"], "🧬"


def build_tip(state: dict, tool: dict, angle: str) -> tuple[dict, str, str, str]:
    prompt = f"""پست «ترفند بیوانفورماتیک» بنویس.

ابزار: {tool['name']} ({tool['url']})
موضوع: {tool['fa']}
زاویه: {angle}

JSON:
{{
  "title": "عنوان ترفند",
  "body": "متن ۴-۸ خطی",
  "why": "اهمیت",
  "code": {{"lang": "python/bash/r یا خالی", "snippet": "کد کوتاه یا خالی"}}{COMMON_JSON_FIELDS}
}}"""
    d = call_llm(state, SYSTEM_PROMPT, prompt)
    return d, tool["url"], f"مستندات {tool['name']}", "💻"


def build_roadmap(state: dict, paper: dict) -> tuple[dict, str, str, str]:
    prompt = f"""رودمپ فارسی بر اساس مقاله زیر بنویس.

عنوان: {paper['title']}
منبع: {paper['source']}
لینک: {paper['link']}
خلاصه: {paper['summary']}

JSON:
{{
  "title": "عنوان رودمپ",
  "intro": "دو خط مقدمه",
  "steps": [{{"title": "گام", "detail": "توضیح"}}, ... ۵-۷ گام],
  "final": "جمع‌بندی"{COMMON_JSON_FIELDS}
}}"""
    d = call_llm(state, SYSTEM_PROMPT, prompt)
    return d, paper["link"], paper["source"], "🗺"


def build_tool(state: dict, tool: dict) -> tuple[dict, str, str, str]:
    prompt = f"""معرفی ابزار بیوانفورماتیک بنویس.

ابزار: {tool['name']} ({tool['url']})
موضوع: {tool['fa']}

JSON:
{{
  "title": "عنوان",
  "body": "معرفی ۵-۸ خطی",
  "why": "اهمیت",
  "code": {{"lang": "زبان", "snippet": "کد نصب یا شروع"}}{COMMON_JSON_FIELDS}
}}"""
    d = call_llm(state, SYSTEM_PROMPT, prompt)
    return d, tool["url"], f"وب‌سایت {tool['name']}", "🛠"


def build_trend(state: dict, item: dict) -> tuple[dict, str, str, str]:
    prompt = f"""ترند داغ امروز را به پست تبدیل کن.

عنوان: {item['title']}
منبع: {item['source']}
لینک: {item['link']}
خلاصه: {item['summary']}

JSON:
{{
  "title": "عنوان ترند",
  "body": "۴-۷ خط",
  "why": "اهمیت"{COMMON_JSON_FIELDS}
}}"""
    d = call_llm(state, SYSTEM_PROMPT, prompt)
    return d, item["link"], item["source"], "🔥"


# ======================================================================
#  تلگرام
# ======================================================================
TG = "https://api.telegram.org/bot" + BOT_TOKEN


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
            resp = requests.post(f"{TG}/{method}", data=data, files=files, timeout=120)
            if resp.status_code == 429:
                wait = resp.json().get("parameters", {}).get("retry_after", 10)
                log(f"⏳ محدودیت تلگرام؛ {wait} ثانیه صبر…")
                time.sleep(wait + 1)
                continue
            body = resp.json()
            if body.get("ok"):
                return body
            description = body.get("description", "")
            if "parse" in description.lower():
                plain = re.sub(r"<[^>]+>", "", data.get("text") or data.get("caption") or "")
                data = {k: v for k, v in data.items() if k not in ("parse_mode", "link_preview_options")}
                for key in ("text", "caption"):
                    if key in data:
                        data[key] = plain
                log("⚠ خطای HTML؛ ارسال بدون قالب‌بندی…")
                resp = requests.post(f"{TG}/{method}", data=data, files=files, timeout=120)
                body = resp.json()
                if body.get("ok"):
                    return body
            last = description or resp.text[:200]
            raise RuntimeError(f"تلگرام: {last}")
        except requests.RequestException as exc:
            last = str(exc)
            log(f"⚠ خطای شبکه (تلاش {attempt + 1}/۳): {exc}")
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"ارسال ناموفق: {last}")


def build_reply_markup(source_url: str = "") -> str | None:
    buttons = []
    if source_url and source_url.startswith("http"):
        buttons.append({"text": "🔗 منبع کامل", "url": source_url})
    link = channel_link()
    if link:
        buttons.append({"text": "📢 عضویت در کانال", "url": link})
    if not buttons:
        return None
    return json.dumps({"inline_keyboard": [buttons]}, ensure_ascii=False)


def send_chat_action(action: str) -> None:
    try:
        tg_post("sendChatAction", {"chat_id": CHANNEL_ID, "action": action})
    except Exception:
        pass


def send_poll(question: str, options: list[str]) -> None:
    try:
        tg_post("sendPoll", {
            "chat_id": CHANNEL_ID,
            "question": question[:290],
            "options": json.dumps([o[:95] for o in options[:10]], ensure_ascii=False),
            "is_anonymous": "true",
            "allows_multiple_answers": "false",
        })
        log("📊 نظرسنجی ارسال شد")
    except Exception as exc:
        log(f"⚠ نظرسنجی ناموفق: {exc}")


def send_text(text: str, source_url: str = "") -> None:
    chunks = split_message(text)
    markup = build_reply_markup(source_url)
    for i, chunk in enumerate(chunks):
        data = {
            "chat_id": CHANNEL_ID,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true" if i > 0 else "false",
        }
        if markup and i == len(chunks) - 1:
            data["reply_markup"] = markup
        tg_post("sendMessage", data)
        log(f"📤 پیام متنی ({i + 1}/{len(chunks)})")


def send_photo(image: bytes, caption: str, full_text: str, source_url: str = "") -> None:
    sent = False
    try:
        data = {"chat_id": CHANNEL_ID, "caption": caption[:1024], "parse_mode": "HTML"}
        markup = build_reply_markup(source_url)
        if markup:
            data["reply_markup"] = markup
        tg_post("sendPhoto", data, files={"photo": ("image.png", image, "image/png")})
        sent = True
        log("🖼 تصویر ارسال شد")
    except Exception as exc:
        log(f"⚠ ارسال تصویر ناموفق ({exc})")
    if not sent or FULL_TEXT_AFTER_IMAGE:
        send_text(full_text, source_url if not sent else "")


# ======================================================================
#  انتخاب نوع محتوا
# ======================================================================
CONTENT_TYPES = ("news", "trend", "tip", "roadmap", "tool")


def pick_type() -> str:
    if FORCE_TYPE in CONTENT_TYPES:
        return FORCE_TYPE
    weights = []
    for part in CONTENT_MIX.split(","):
        name, _, w = part.partition(":")
        name = name.strip().lower()
        if name in CONTENT_TYPES and w.strip().isdigit():
            weights.append((name, int(w.strip())))
    if not weights:
        return "news"
    return random.choices([n for n, _ in weights], weights=[w for _, w in weights], k=1)[0]


def today_gate(state: dict) -> bool:
    if os.environ.get("ENABLE_DAILY_CAP", "0") != "1":
        return True
    td = state.setdefault("today", {})
    today = datetime.now(TEHRAN_TZ).strftime("%Y-%m-%d")
    if td.get("date") != today:
        td.update(date=today, count=0,
                  target=random.randint(min(DAILY_MIN, DAILY_MAX), max(DAILY_MIN, DAILY_MAX)))
        log(f"🗓 هدف امروز: {td['target']} پست")
    if os.environ.get("FORCE_POST", "") == "1":
        return True
    if td["count"] >= td["target"]:
        log(f"📅 سقف امروز پر شده")
        return False
    return True


def today_increment(state: dict) -> None:
    state.setdefault("today", {})["count"] = state.get("today", {}).get("count", 0) + 1


# ======================================================================
#  برنامه اصلی
# ======================================================================
def main() -> int:
    global ENGINES
    ENGINES = load_engines()
    log(f"🚀 شروع — کانال: {CHANNEL_ID} | کلیدها: {len(ENGINES)}")

    if not ENGINES:
        log("❌ هیچ کلیدی تنظیم نشده")
        return 1

    state = load_state()
    refresh_gemini_models(state)

    if not today_gate(state):
        return 0

    ctype = pick_type()
    log(f"📂 نوع محتوا: {ctype}")

    d = source_url = source_name = emoji = None

    if ctype == "trend":
        pool = fetch_trend_items()
        fresh = [i for i in pool if i["link"] not in state.get("links", [])]
        if not fresh:
            ctype = "news"
        else:
            item = random.choice(fresh)
            d, source_url, source_name, emoji = build_trend(state, item)
            state.setdefault("links", []).append(item["link"])

    if ctype in ("news", "roadmap"):
        pool = fetch_feed_items(only_roadmap_pool=(ctype == "roadmap"))
        if ctype == "roadmap" and not pool:
            pool = fetch_feed_items()
        fresh = [i for i in pool if i["link"] not in state.get("links", [])]
        if not fresh:
            ctype = "tool"
        else:
            item = random.choice(fresh)
            if ctype == "news":
                d, source_url, source_name, emoji = build_news(state, item)
            else:
                d, source_url, source_name, emoji = build_roadmap(state, item)
            state.setdefault("links", []).append(item["link"])

    if ctype == "tip":
        unused = [t for t in TOPIC_BANK if t["name"] not in state.get("topics", [])]
        if not unused:
            state["topics"] = []
            unused = TOPIC_BANK
        tool = random.choice(unused)
        d, source_url, source_name, emoji = build_tip(state, tool, random.choice(TIP_ANGLES))
        state.setdefault("topics", []).append(tool["name"])

    if ctype == "tool":
        unused = [t for t in TOPIC_BANK if t["name"] not in state.get("topics", [])]
        if not unused:
            state["topics"] = []
            unused = TOPIC_BANK
        tool = random.choice(unused)
        d, source_url, source_name, emoji = build_tool(state, tool)
        state.setdefault("topics", []).append(tool["name"])

    if d is None:
        raise RuntimeError("نوع محتوا ناشناخته")

    if ctype == "roadmap":
        full_text = render_roadmap(d, source_url, source_name)
    else:
        full_text = render_post(d, source_url, source_name, emoji)
    caption = build_caption(d, source_url, source_name, emoji)

    log("=" * 60)
    log("پست نهایی:")
    print(full_text)
    log("=" * 60)

    # تولید تصویر با Nano Banana
    image = None
    if WITH_IMAGE:
        if not TELEGRAM_DRY:
            send_chat_action("upload_photo")
        image = generate_image(state, d.get("image_prompt_en") or d.get("title", ""))
        if image and not TELEGRAM_DRY:
            os.makedirs(os.path.join(ROOT, "state"), exist_ok=True)
            with open(os.path.join(ROOT, "state", "last_image.png"), "wb") as f:
                f.write(image)

    # ارسال
    if TELEGRAM_DRY:
        log("🔧 حالت TELEGRAM_DRY")
    elif image:
        send_photo(image, caption, full_text, source_url)
    else:
        log("📷 بدون تصویر؛ ارسال متنی")
        send_text(full_text, source_url)

    # نظرسنجی
    poll_q = str(d.get("poll_question") or "").strip()
    poll_opts = [str(o).strip() for o in (d.get("poll_options") or []) if str(o).strip()]
    if not TELEGRAM_DRY and poll_q and len(poll_opts) >= 2:
        send_poll(poll_q, poll_opts)

    if not TELEGRAM_DRY:
        today_increment(state)
        save_state(state)
    log("🏁 پایان موفق")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:
        log(f"❌ خطای مهلک: {exc}")
        sys.exit(1)
