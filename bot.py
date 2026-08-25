#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bio with AI — ربات همه‌فن‌حریف کانال تلگرام
============================================
قابلیت‌ها:
  ● پشتیبانی از چند کلید API از سرویس‌های مختلف (جمینای + هر سرویس سازگار با OpenAI
    مثل Grok/xAI ، OpenRouter ، DeepSeek ، OpenAI و…) — اگر یکی به محدودیت خورد
    خودکار سراغ بعدی می‌رود (چرخش + خنک‌سازی کلیدهای خسته)
  ● چهار نوع محتوا:
      news    → خبر داغ زیست‌شناسی / هوش مصنوعی در زیست / محاسبات در زیست
      tip     → ترفند عملی بیوانفورماتیک (ابزار واقعی + لینک رسمی)
      roadmap → رودمپ کامل بر اساس یک مقاله علمی واقعی و تازه
      tool    → معرفی ابزار/سرور/پایگاه داده بیوانفورماتیک
  ● هر پست: منبع واقعی + لینک کانال در انتهای پیام + ایموجی سنجیده
  ● تولید تصویر مرتبط با همان متن (جمینای) و ارسال همراه پست
  ● جلوگیری از تکرار محتوا (state/posted.json)

اجرا: GitHub Actions (رایگان) — کلیدها از Secrets خوانده می‌شوند.
تنظیم AI_CONFIG (در یک Secret به نام AI_CONFIG) — مثال:

{
  "gemini": ["AIza...کلید-۱", "AIza...کلید-۲", "AIza...کلید-۳"],
  "openai_compatible": [
    {"base_url": "https://api.x.ai/v1",        "api_key": "xai-...", "model": "grok-4-fast"},
    {"base_url": "https://openrouter.ai/api/v1", "api_key": "sk-or-...", "model": "deepseek/deepseek-chat-v3-0324:free"}
  ]
}

اگر AI_CONFIG تنظیم نشده باشد ولی GEMINI_API_KEY باشد، همان استفاده می‌شود (سازگاری قدیمی).
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
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()          # حالت قدیمی
AI_CONFIG      = os.environ.get("AI_CONFIG", "").strip()               # حالت چند-سرویسی

GEMINI_TEXT_MODEL   = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash").strip()
GEMINI_IMAGE_MODELS = ["gemini-2.5-flash-image", "gemini-2.0-flash-preview-image-generation"]

MAX_AGE_DAYS   = int(os.environ.get("MAX_AGE_DAYS", "7"))
FORCE_TYPE     = os.environ.get("FORCE_TYPE", "").strip().lower()      # news|tip|roadmap|tool
CONTENT_MIX    = os.environ.get("CONTENT_MIX", "news:5,tip:2,roadmap:2,tool:1")
WITH_IMAGE     = os.environ.get("WITH_IMAGE", "1") == "1"             # تولید تصویر
FULL_TEXT_AFTER_IMAGE = os.environ.get("FULL_TEXT_AFTER_IMAGE", "1") == "1"
BASE_TAGS      = os.environ.get("BASE_TAGS", "#بیوانفورماتیک #زیست_شناسی #هوش_مصنوعی").strip()

DRY_RUN   = "--dry-run" in sys.argv          # فقط انتخاب محتوا، بدون AI/تلگرام
SELFTEST  = "--selftest" in sys.argv         # تست داخلی بدون شبکه
MOCK_LLM  = os.environ.get("MOCK_LLM", "") == "1"          # جایگزینی AI با پاسخ ساختگی
TELEGRAM_DRY = os.environ.get("TELEGRAM_DRY", "") == "1"   # همه‌چیز اجرا ولی پست ارسال نشود

ROOT = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(ROOT, "state", "posted.json")

UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def log(msg: str) -> None:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


# ======================================================================
#  موتورهای هوش مصنوعی (چند کلید / چند سرویس / تعویض خودکار)
# ======================================================================
class Engine:
    def __init__(self, kind: str, api_key: str, model: str, base_url: str = ""):
        self.kind = kind                    # "gemini" | "openai"
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.id = f"{kind}:{model}:{api_key[-6:]}"

    def __repr__(self):
        return f"<{self.kind} {self.model} …{self.api_key[-6:]}>"


def load_engines() -> list[Engine]:
    """ساخت فهرست موتورها از AI_CONFIG (یا GEMINI_API_KEY برای سازگاری قدیمی)."""
    engines: list[Engine] = []
    raw_cfg = os.environ.get("AI_CONFIG", "").strip()
    legacy = os.environ.get("GEMINI_API_KEY", "").strip()
    if raw_cfg:
        cfg = json.loads(raw_cfg)
        for key in cfg.get("gemini", []):
            if str(key).strip():
                engines.append(Engine("gemini", str(key).strip(),
                                      cfg.get("gemini_model", GEMINI_TEXT_MODEL)))
        for e in cfg.get("openai_compatible", []):
            if e.get("api_key") and e.get("base_url") and e.get("model"):
                engines.append(Engine("openai", e["api_key"].strip(), e["model"].strip(), e["base_url"]))
    if not engines and legacy:
        engines.append(Engine("gemini", legacy, GEMINI_TEXT_MODEL))
    return engines


ENGINES: list[Engine] = load_engines()  # در selftest/main بازخوانی می‌شود


def load_state() -> dict:
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"links": [], "topics": [], "cooldowns": {}}


def save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    state["links"] = state.get("links", [])[-300:]
    state["topics"] = state.get("topics", [])[-300:]
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)


def engine_on_cooldown(state: dict, eng: Engine) -> bool:
    until = state.get("cooldowns", {}).get(eng.id)
    if not until:
        return False
    try:
        if datetime.fromisoformat(until) > datetime.now(timezone.utc):
            return True
    except ValueError:
        return False
    state["cooldowns"].pop(eng.id, None)
    return False


def set_cooldown(state: dict, eng: Engine, minutes: int = 60) -> None:
    state.setdefault("cooldowns", {})[eng.id] = (
        datetime.now(timezone.utc) + timedelta(minutes=minutes)
    ).isoformat()
    log(f"⏸ موتور {eng.id} به مدت {minutes} دقیقه کنار گذاشته شد")


def ordered_engines(state: dict) -> list[Engine]:
    """موتورها به ترتیب تنظیم، ولی موتورهای در حالت خنک‌سازی ته کشیده می‌شوند."""
    ready = [e for e in ENGINES if not engine_on_cooldown(state, e)]
    if not ready:  # همه خسته‌اند → همه را آزاد کن
        state["cooldowns"] = {}
        ready = list(ENGINES)
    return ready


def extract_json(text: str) -> dict:
    """استخراج اولین JSON معتبر از متن پاسخ (حتی اگر داخل ```fence باشد)."""
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip())
    start = text.find("{")
    if start < 0:
        raise ValueError("JSON یافت نشد")
    try:
        return json.loads(text[start:])
    except json.JSONDecodeError:
        dec = json.JSONDecoder()
        obj, _ = dec.raw_decode(text[start:])
        return obj


def llm_gemini(eng: Engine, system: str, user: str) -> str:
    resp = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{eng.model}:generateContent",
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
        data = resp.json()
        return data["candidates"][0]["content"]["parts"][0]["text"]
    raise RuntimeError(f"gemini HTTP {resp.status_code}: {resp.text[:200]}")


def llm_openai(eng: Engine, system: str, user: str) -> str:
    resp = requests.post(
        f"{eng.base_url}/chat/completions",
        headers={"Authorization": f"Bearer {eng.api_key}"},
        json={
            "model": eng.model,
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
        data = resp.json()
        return data["choices"][0]["message"]["content"]
    raise RuntimeError(f"{eng.model} HTTP {resp.status_code}: {resp.text[:200]}")


# پاسخ‌های ساختگی برای --selftest / MOCK_LLM
MOCK_RESPONSE = json.dumps({
    "title": "هوش مصنوعی ساختار پروتئین‌ها را در چند ثانیه رمزگشایی می‌کند",
    "body": "پژوهشگران با ترکیب مدل‌های زبانی بزرگ و داده‌های ساختاری موفق شدند فرایند پیش‌بینی ساختار پروتئین را ده‌ها برابر سریع‌تر کنند. این دستاورد مسیر طراحی داروهای تازه را کوتاه‌تر می‌کند.",
    "why": "این روش تحلیل شبکه‌های مولکولی را که پیشتر هفته‌ها طول می‌کشید در چند دقیقه انجام می‌دهد.",
    "caption": "مدل تازه هوش مصنوعی، پیش‌بینی ساختار پروتئین را ده‌ها برابر سریع‌تر کرد؛ گامی بزرگ برای طراحی دارو.",
    "image_prompt_en": "Clean scientific illustration of an AI neural network analyzing a glowing 3D protein structure, modern infographic style, blue and green palette",
    "tags": ["پروتئین", "هوش_مصنوعی", "طراحی_دارو"],
}, ensure_ascii=False)


def call_llm(state: dict, system: str, user: str) -> dict:
    """فراخوانی LLM با چرخش خودکار بین همه موتورها؛ خروجی همیشه JSON پارس‌شده است."""
    if MOCK_LLM or SELFTEST:
        return extract_json(MOCK_RESPONSE)
    errors = []
    for eng in ordered_engines(state):
        fn = llm_gemini if eng.kind == "gemini" else llm_openai
        for attempt in range(2):
            try:
                raw = fn(eng, system, user)
                parsed = extract_json(raw)
                log(f"✔ پاسخ از موتور {eng.id}")
                return parsed
            except Exception as exc:
                msg = str(exc)
                errors.append(f"{eng.id}: {msg}")
                # محدودیت نرخ/سهمیه → کلید را خنک کن و برو سراغ بعدی
                if " 429" in msg or " 402" in msg or "RESOURCE_EXHAUSTED" in msg:
                    set_cooldown(state, eng, minutes=90)
                    break
                # کلید نامعتبر → بی‌صدا موتور بعدی
                if " 401" in msg or " 403" in msg:
                    log(f"⛔ کلید {eng.id} نامعتبر/غیرفعال است")
                    break
                # خطای گذرا → یک تلاش مجدد روی همین موتور
                if attempt == 0:
                    time.sleep(4)
        # موتور بعدی...
    raise RuntimeError("هیچ‌کدام از موتورهای هوش مصنوعی پاسخ ندادند:\n" + "\n".join(errors[:6]))


# ----------------------------------------------------------------------
# تولید تصویر با جمینای (فقط موتورهای جمینای)
# ----------------------------------------------------------------------
TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR4nGNgYGBgAAAABQAB"
    "h6FO1AAAAABJRU5ErkJggg=="
)


def generate_image(state: dict, prompt_en: str) -> bytes | None:
    """تلاش برای ساخت تصویر با مدل‌های تصویری جمینای؛ در شکست، None برمی‌گردد."""
    if MOCK_LLM or SELFTEST:
        return TINY_PNG
    gemini_engines = [e for e in ordered_engines(state) if e.kind == "gemini"]
    for eng in gemini_engines:
        for model in GEMINI_IMAGE_MODELS:
            try:
                resp = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                    params={"key": eng.api_key},
                    json={
                        "contents": [{"role": "user", "parts": [{"text": prompt_en}]}],
                        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
                    },
                    timeout=180,
                )
                if resp.status_code != 200:
                    raise RuntimeError(f"HTTP {resp.status_code}")
                parts = resp.json()["candidates"][0]["content"]["parts"]
                for p in parts:
                    inline = p.get("inlineData") or {}
                    if inline.get("data"):
                        data = base64.b64decode(inline["data"])
                        log(f"🖼 تصویر ساخته شد ({len(data) // 1024} KB) با {model}")
                        return data
                raise RuntimeError("پاسخ تصویر خالی بود")
            except Exception as exc:
                log(f"⚠ تصویر با {model} روی …{eng.api_key[-6:]} نشد: {exc}")
    return None


# ======================================================================
#  منابع خبری (RSS)
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

# فیدهایی که مقاله‌شان برای «رودمپ» مناسب‌ترند (مقاله متدولوژیک/تحلیلی)
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
                link = (getattr(e, "link", "") or "").strip()
                if not title or not link:
                    continue
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


# ======================================================================
#  بانک ابزارها (برای ترفند و معرفی ابزار) — لینک‌ها واقعی و رسمی‌اند
# ======================================================================
TOPIC_BANK = [
    {"name": "Galaxy Project", "url": "https://usegalaxy.org", "fa": "سرور آنلاین تحلیل داده‌های ژنومیک بدون نیاز به کدنویسی"},
    {"name": "NCBI BLAST", "url": "https://blast.ncbi.nlm.nih.gov/Blast.cgi?CMD=Web&PAGE_TYPE=BlastDocs", "fa": "ابزار جست‌وجوی تشابه توالی‌های بیولوژیکی"},
    {"name": "AlphaFold DB", "url": "https://alphafold.ebi.ac.uk", "fa": "پایگاه پیش‌بینی ساختار پروتئین با هوش مصنوعی"},
    {"name": "UniProt", "url": "https://www.uniprot.org", "fa": "جامع‌ترین پایگاه داده اطلاعات پروتئین‌ها"},
    {"name": "Ensembl", "url": "https://www.ensembl.org", "fa": "پایگاه داده ژنوم و حاشیه‌نویسی ژن"},
    {"name": "UCSC Genome Browser", "url": "https://genome.ucsc.edu", "fa": "مرورگر بصری ژنوم"},
    {"name": "KEGG", "url": "https://www.genome.jp/kegg", "fa": "پایگاه مسیرهای متابولیک و عملکردی"},
    {"name": "STRING", "url": "https://string-db.org", "fa": "تحلیل شبکه‌های برهم‌کنش پروتئین-پروتئین"},
    {"name": "Biopython", "url": "https://biopython.org", "fa": "کتابخانه پایتون برای داده‌های بیولوژیکی"},
    {"name": "Bioconda", "url": "https://bioconda.github.io", "fa": "نصب هزاران ابزار بیوانفورماتیک با Conda"},
    {"name": "Galaxy Training", "url": "https://training.galaxyproject.org", "fa": "آموزش‌های رایگان تحلیل ژنومیک"},
    {"name": "QIIME 2", "url": "https://qiime2.org", "fa": "پلتفرم تحلیل داده‌های میکروبیوم"},
    {"name": "Snakemake", "url": "https://snakemake.github.io", "fa": "مدیریت ورک‌فلو برای تحلیل تکرارپذیر"},
    {"name": "Nextflow", "url": "https://www.nextflow.io", "fa": "ورک‌فلو موازی برای داده‌های حجیم"},
    {"name": "GATK", "url": "https://gatk.broadinstitute.org", "fa": "ابزارکیت تنوع‌یابی ژنومی"},
    {"name": "Cytoscape", "url": "https://cytoscape.org", "fa": "بصری‌سازی شبکه‌های مولکولی"},
    {"name": "PyMOL", "url": "https://pymol.org", "fa": "تصویرسازی حرفه‌ای ساختار پروتئین"},
    {"name": "GROMACS", "url": "https://www.gromacs.org", "fa": "شبیه‌سازی دینامیک مولکولی"},
    {"name": "IQ-TREE", "url": "http://www.iqtree.org", "fa": "ساخت درخت فیلوژنتیک"},
    {"name": "InterPro", "url": "https://www.ebi.ac.uk/interpro", "fa": "تحلیل دامنه‌های پروتئینی"},
    {"name": "Reactome", "url": "https://reactome.org", "fa": "پایگاه مسیرهای بیولوژیکی"},
    {"name": "Gene Ontology", "url": "http://geneontology.org", "fa": "واژه‌نامه استاندارد عملکرد ژن‌ها"},
    {"name": "DAVID", "url": "https://david.ncifcrf.gov", "fa": "غنی‌سازی عملکردی فهرست‌های ژنی"},
    {"name": "DESeq2", "url": "https://bioconductor.org/packages/release/bioc/html/DESeq2.html", "fa": "تحلیل افتراقی بیان ژن در R"},
    {"name": "Seurat", "url": "https://satijalab.org/seurat", "fa": "تحلیل داده تک‌سلولی در R"},
    {"name": "Scanpy", "url": "https://scanpy.readthedocs.io", "fa": "تحلیل داده تک‌سلولی در پایتون"},
    {"name": "ColabFold", "url": "https://colabfold.colab.google", "fa": "اجرای AlphaFold2 رایگان در گوگل‌کولب"},
    {"name": "antiSMASH", "url": "https://antismash.secondarymetabolites.org", "fa": "شناسایی خوشه‌های ژنی متابولیت ثانویه"},
    {"name": "BUSCO", "url": "https://busco.ezlab.org", "fa": "ارزیابی کیفیت ژنوم"},
    {"name": "Prokka", "url": "https://github.com/tseemann/prokka", "fa": "حاشیه‌نویسی سریع ژنوم پروکاریوتی"},
    {"name": "MG-RAST", "url": "https://www.mg-rast.org", "fa": "تحلیل ابری داده‌های متاژنومیک"},
    {"name": "EMBL-EBI Services", "url": "https://www.ebi.ac.uk/services", "fa": "مجموعه سرویس‌های بیوانفورماتیک اروپا"},
    {"name": "NCBI", "url": "https://www.ncbi.nlm.nih.gov", "fa": "بزرگ‌ترین مجموعه پایگاه‌های داده بیولوژیکی"},
    {"name": "PubMed", "url": "https://pubmed.ncbi.nlm.nih.gov", "fa": "جست‌وجوی مقالات علوم زیستی"},
    {"name": "BWA", "url": "https://github.com/lh3/bwa", "fa": "هم‌ترازسازی سریع توالی‌های DNA به ژنوم مرجع"},
    {"name": "Samtools", "url": "https://www.htslib.org", "fa": "ابزارهای پردازش فایل‌های SAM/BAM"},
    {"name": "FastQC", "url": "https://www.bioinformatics.babraham.ac.uk/projects/fastqc", "fa": "کنترل کیفیت داده‌های توالی‌یابی"},
    {"name": "RCSB PDB", "url": "https://www.rcsb.org", "fa": "پایگاه داده ساختارهای سه‌بعدی پروتئین"},
    {"name": "ChEMBL", "url": "https://www.ebi.ac.uk/chembl", "fa": "پایگاه داده بیوالفعال مولکول‌های دارویی"},
    {"name": "GTEx", "url": "https://gtexportal.org", "fa": "پایگاه بیان ژن در بافت‌های سالم انسان"},
]

TIP_ANGLES = [
    "یک ترفند کمترشناخته‌شده اما بسیار کاربردی",
    "یک اشتباه رایج کاربران و روش درست انجام کار",
    "یک بهینه‌سازی سرعت یا حافظه واقعی",
    "یک گردش‌کاری (workflow) پیشنهادی گام‌به‌گام برای یک کار روزمره",
    "یک قابلیت مخفی یا گزینه پیشرفته که کاربران عادی نمی‌دانند",
    "یک ترفند خط فرمان یا چندخط کد که کار را ساده می‌کند",
]


# ======================================================================
#  ساخت پست — دستورهای سیستم و انواع محتوا
# ======================================================================
SYSTEM_PROMPT = """تو سردبیر یک کانال تلگرام فارسی‌زبان دانشگاهی به نام «Bio with AI» هستی؛ مخاطبانت دانشجویان، پژوهشگران و علاقه‌مندان زیست‌شناسی، بیوانفورماتیک و هوش مصنوعی‌اند.

قواعد ناگسستنی:
۱. علمی و دقیق بنویس؛ سطح دانشگاهی اما روان و قابل فهم. اصطلاح تخصصی انگلیسی مهم را یک بار داخل پرانتز بیاور.
۲. هیچ داده، آمار یا ادعایی را از خودت نساز. فقط بر مبنای داده ورودی و دانش عمومی تثبیت‌شده بنویس. اگر چیزی نامعلوم است، حدس نزن.
۳. ایموجی را سنجیده به کار ببر: حداکثر ۲ ایموجی داخل متن اصلی. عنوان‌ها بدون ایموجی باشند (قالب خودکار اضافه می‌کند).
۴. جمله‌های کوتاه، پاراگراف‌های منظم، بدون اغراق‌گویی تبلیغاتی.
۵. پاسخ را فقط و فقط به شکل JSON معتبر بده؛ هیچ متن اضافی خارج از JSON ننویس."""


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


def esc_url(url: str) -> str:
    url = (url or "").strip()
    return html.escape(url if url.startswith("http") else "https://example.com", quote=True)


def channel_link() -> str:
    if CHANNEL_ID.startswith("@"):
        return f'https://t.me/{CHANNEL_ID[1:]}'
    return "https://t.me/Bio_with_AI"


def footer(source_url: str, source_name: str) -> str:
    return (
        f'🔗 <b>منبع:</b> <a href="{esc_url(source_url)}">{esc(source_name)}</a>\n'
        f'📌 <b>کانال:</b> <a href="{channel_link()}">{CHANNEL_ID.lstrip("@")}</a>'
    )


def render_post(d: dict, source_url: str, source_name: str, emoji: str = "🧬") -> str:
    """قالب نهایی یک پیام متنی کامل."""
    tags = (sanitize_tags(d.get("tags")) + " " + BASE_TAGS).strip()
    parts = [f"{emoji} <b>{esc(d['title'])}</b>", "", esc(d["body"])]
    if d.get("why"):
        parts += ["", f"💡 <b>چرا مهم است؟</b> {esc(d['why'])}"]
    parts += ["", tags, "", footer(source_url, source_name)]
    post = "\n".join(parts)
    if len(post) > 4000:
        post = post[:3990] + "\n…"
    return post


def render_roadmap(d: dict, source_url: str, source_name: str) -> str:
    """قالب ویژه پست رودمپ."""
    num_emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣"]
    lines = [f"🗺 <b>{esc(d['title'])}</b>", "", esc(d.get("intro", "")), "", "🎯 <b>مسیر پیشنهادی:</b>"]
    for i, step in enumerate(d.get("steps", [])[:8]):
        if isinstance(step, dict):
            head, body = step.get("title", ""), step.get("detail", "")
        else:
            head, body = str(step), ""
        marker = num_emojis[i] if i < len(num_emojis) else "▫️"
        lines.append(f"{marker} <b>{esc(head)}</b>")
        if body:
            lines.append(f"   {esc(body)}")
    if d.get("final"):
        lines += ["", f"✅ <b>سخن پایانی:</b> {esc(d['final'])}"]
    tags = (sanitize_tags(d.get("tags")) + " " + BASE_TAGS).strip()
    lines += ["", tags, "", footer(source_url, source_name)]
    post = "\n".join(lines)
    if len(post) > 4000:
        post = post[:3990] + "\n…"
    return post


def build_caption(d: dict, source_url: str, source_name: str, emoji: str) -> str:
    """زیرنویس تصویر — حداکثر ۱۰۲۴ کاراکتر (محدودیت تلگرام)."""
    cap = (
        f"{emoji} <b>{esc(d['title'])}</b>\n\n"
        f"{esc(d.get('caption') or d['body'])}\n\n"
        + footer(source_url, source_name)
    )
    if len(cap) > 1000:
        cap = cap[:990].rsplit(" ", 1)[0] + "…\n\n" + footer(source_url, source_name)
    return cap


# ----------------------  پرامپت‌های هر نوع محتوا  ----------------------
COMMON_JSON_FIELDS = """,
  "caption": "خلاصه ۳ تا ۴ خطی همین مطلب برای زیرنویس تصویر؛ حداکثر ۷۰۰ کاراکتر",
  "image_prompt_en": "توضیح انگلیسی یک جمله‌ای برای ساخت تصویر علمی مرتبط با همین مطلب؛ سبک اینفوگرافیک تمیز و مدرن، بدون متن داخل تصویر",
  "tags": ["سه یا چهار هشتگ فارسی مرتبط، بدون علامت #"]"""


def build_news(state: dict, item: dict) -> tuple[dict, str, str, str]:
    prompt = f"""خبر علمی زیر را به یک پست تلگرامی فارسی تبدیل کن.

عنوان: {item['title']}
منبع: {item['source']}
لینک: {item['link']}
خلاصه انگلیسی: {item['summary']}

JSON با این ساختار:
{{
  "title": "عنوان فارسی جذاب و دقیق (حداکثر ۱۰ کلمه)",
  "body": "متن ۴ تا ۷ خطی: چه اتفاقی افتاده، چگونه، و چه اهمیتی دارد. اگر به هوش مصنوعی، محاسبات یا بیوانفورماتیک مربوط است حتماً روشن بگو.",
  "why": "یک تا دو جمله درباره اهمیت برای زیست‌شناسان و بیوانفورماتیک‌دان‌ها"{COMMON_JSON_FIELDS}
}}"""
    d = call_llm(state, SYSTEM_PROMPT, prompt)
    return d, item["link"], item["source"], "🧬"


def build_tip(state: dict, tool: dict, angle: str) -> tuple[dict, str, str, str]:
    prompt = f"""یک پست «ترفند بیوانفورماتیک» بنویس.

ابزار: {tool['name']} (وب‌سایت رسمی: {tool['url']})
موضوع ابزار: {tool['fa']}
زاویه موردنظر: {angle}

قواعد: ترفند باید واقعاً در همین ابزار وجود داشته باشد و قابل انجام باشد؛ چیزی از خودت نساز. اگر خط فرمان یا کد لازم است، دقیق و کوتاه بیاور.

JSON با این ساختار:
{{
  "title": "عنوان فارسی مثل: ترفند طلایی BLAST برای ... (حداکثر ۱۰ کلمه)",
  "body": "متن ۴ تا ۸ خطی: مشکل یا نیاز، ترفند دقیق، و نحوه اجرا؛ مراحل را مرتب و خوانا بنویس",
  "why": "یک تا دو جمله: با این ترفند چه زمانی یا منبعی صرفه‌جویی می‌شود"{COMMON_JSON_FIELDS}
}}"""
    d = call_llm(state, SYSTEM_PROMPT, prompt)
    return d, tool["url"], f"مستندات رسمی {tool['name']}", "💻"


def build_roadmap(state: dict, paper: dict) -> tuple[dict, str, str, str]:
    prompt = f"""بر اساس مقاله علمی تازه زیر، یک «رودمپ کامل» فارسی بنویس: اگر کسی بخواهد وارد حوزه این مقاله شود یا آن را بازتولید کند، باید چه مسیری را طی کند.

عنوان مقاله: {paper['title']}
منبع: {paper['source']}
لینک: {paper['link']}
چکیده/خلاصه: {paper['summary']}

قواعد: هر مهارت و ابزاری که نام می‌بری باید واقعی و شناخته‌شده باشد؛ لینک نساز (فقط نام ببر). گام‌ها باید مشخص، عملی و به‌ترتیب باشند.

JSON با این ساختار:
{{
  "title": "عنوان فارسی رودمپ (مثلاً: رودمپ ورود به ... بر پایه مقاله جدید Nature)",
  "intro": "دو خط: این مقاله چه کرده و این رودمپ برای کیست",
  "steps": [
    {{"title": "عنوان کوتاه گام ۱", "detail": "توضیح ۱-۲ خطی دقیق این گام"}}，
    ... بین ۵ تا ۷ گام ...
  ],
  "final": "یک تا دو جمله جمع‌بندی انگیزشی اما علمی و واقع‌بینانه"{COMMON_JSON_FIELDS}
}}"""
    d = call_llm(state, SYSTEM_PROMPT, prompt)
    return d, paper["link"], paper["source"], "🗺"


def build_tool(state: dict, tool: dict) -> tuple[dict, str, str, str]:
    prompt = f"""یک پست معرفی علمی-آموزشی بنویس درباره این ابزار بیوانفورماتیک.

ابزار: {tool['name']} (لینک رسمی: {tool['url']})
موضوع: {tool['fa']}

قواعد: فقط قابلیت‌های واقعی و مستند این ابزار را بنویس؛ رایگان/متن‌باز/آنلاین بودن را اگر می‌دانی ذکر کن.

JSON با این ساختار:
{{
  "title": "عنوان فارسی (مثل: ابزار هفته: Galaxy؛ آزمایشگاه بیوانفورماتیک در مرورگر)",
  "body": "معرفی ۵ تا ۸ خطی: چیست، چه مشکلی حل می‌کند، برای چه کسانی، یک نکته کاربردی شروع",
  "why": "یک تا دو جمله درباره جایگاه ابزار در پژوهش"{COMMON_JSON_FIELDS}
}}"""
    d = call_llm(state, SYSTEM_PROMPT, prompt)
    return d, tool["url"], f"وب‌سایت رسمی {tool['name']}", "🛠"


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
            if "parse" in description.lower():      # خطای HTML → ارسال بدون قالب‌بندی
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
            log(f"⚠ خطای شبکه تلگرام (تلاش {attempt + 1}/۳): {exc}")
            time.sleep(5 * (attempt + 1))
    raise RuntimeError(f"ارسال به تلگرام پس از تلاش‌های مکرر ناموفق بود: {last}")


def send_text(text: str) -> None:
    chunks = split_message(text)
    for i, chunk in enumerate(chunks):
        data = {
            "chat_id": CHANNEL_ID,
            "text": chunk,
            "parse_mode": "HTML",
            "disable_web_page_preview": "true" if i > 0 else "false",
        }
        tg_post("sendMessage", data)
        log(f"📤 پیام متنی ارسال شد ({i + 1}/{len(chunks)})")


def send_photo(image: bytes, caption: str, full_text: str) -> None:
    sent = False
    try:
        tg_post("sendPhoto", {
            "chat_id": CHANNEL_ID,
            "caption": caption[:1024],
            "parse_mode": "HTML",
        }, files={"photo": ("image.png", image, "image/png")})
        sent = True
        log("🖼 تصویر با موفقیت ارسال شد")
    except Exception as exc:
        log(f"⚠ ارسال تصویر ناموفق ({exc})؛ ارسال متنی…")
    if not sent or FULL_TEXT_AFTER_IMAGE:
        send_text(full_text)


# ======================================================================
#  انتخاب نوع محتوا بر اساس وزن‌ها
# ======================================================================
def pick_type() -> str:
    if FORCE_TYPE in ("news", "tip", "roadmap", "tool"):
        return FORCE_TYPE
    weights = []
    for part in CONTENT_MIX.split(","):
        name, _, w = part.partition(":")
        name = name.strip().lower()
        if name in ("news", "tip", "roadmap", "tool") and w.strip().isdigit():
            weights.append((name, int(w.strip())))
    if not weights:
        return "news"
    names = [n for n, _ in weights]
    vals = [w for _, w in weights]
    return random.choices(names, weights=vals, k=1)[0]


# ======================================================================
#  برنامه اصلی
# ======================================================================
def main() -> int:
    global ENGINES
    ENGINES = load_engines()
    log(f"🚀 شروع — کانال: {CHANNEL_ID} | موتورهای AI: {len(ENGINES)} | نوع: "
        + (FORCE_TYPE or "خودکار (وزنی)"))

    if not ENGINES:
        log("❌ هیچ کلید هوش مصنوعی تنظیم نشده (AI_CONFIG یا GEMINI_API_KEY)")
        return 1

    state = load_state()
    ctype = pick_type()
    log(f"📂 نوع محتوای امروز: {ctype}")

    # ---------- انتخاب ماده خام ----------
    d = source_url = source_name = emoji = None

    if ctype in ("news", "roadmap"):
        pool = fetch_feed_items(only_roadmap_pool=(ctype == "roadmap"))
        if ctype == "roadmap" and not pool:
            log("استخر رودمپ خالی بود؛ از کل استخر استفاده می‌شود")
            pool = fetch_feed_items()
        fresh = [i for i in pool if i["link"] not in state.get("links", [])]
        log(f"📰 {len(pool)} مورد پیدا شد، {len(fresh)} مورد پست‌نشده")
        if not fresh:
            ctype = "tool"      # سقوط نرم به معرفی ابزار
            log("خبر تازه‌ای نمانده بود → معرفی ابزار")
        else:
            item = random.choice(fresh)
            if DRY_RUN:
                log(f"— حالت آزمایشی ({ctype})؛ مورد انتخاب‌شده:")
                print(json.dumps(item, ensure_ascii=False, indent=2))
                return 0
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
        if DRY_RUN:
            log(f"— حالت آزمایشی (tip)؛ ابزار: {tool['name']} | زاویه: {random.choice(TIP_ANGLES)}")
            return 0
        d, source_url, source_name, emoji = build_tip(state, tool, random.choice(TIP_ANGLES))
        state.setdefault("topics", []).append(tool["name"])

    if ctype == "tool":
        unused = [t for t in TOPIC_BANK if t["name"] not in state.get("topics", [])]
        if not unused:
            state["topics"] = []
            unused = TOPIC_BANK
        tool = random.choice(unused)
        if DRY_RUN:
            log(f"— حالت آزمایشی (tool)؛ ابزار: {tool['name']}")
            return 0
        d, source_url, source_name, emoji = build_tool(state, tool)
        state.setdefault("topics", []).append(tool["name"])

    if d is None:
        raise RuntimeError("نوع محتوا ناشناخته است")

    # ---------- ساخت پست نهایی ----------
    if ctype == "roadmap":
        full_text = render_roadmap(d, source_url, source_name)
    else:
        full_text = render_post(d, source_url, source_name, emoji)
    caption = build_caption(d, source_url, source_name, emoji)

    log("=" * 60)
    log("پست نهایی:")
    print(full_text)
    log("=" * 60)

    # ---------- تصویر ----------
    image = None
    if WITH_IMAGE:
        image = generate_image(state, d.get("image_prompt_en") or d.get("title", ""))
        if image and not TELEGRAM_DRY:
            os.makedirs(os.path.join(ROOT, "state"), exist_ok=True)
            with open(os.path.join(ROOT, "state", "last_image.png"), "wb") as f:
                f.write(image)

    # ---------- ارسال ----------
    if TELEGRAM_DRY:
        log("🔧 حالت TELEGRAM_DRY — ارسال واقعی انجام نشد")
    elif image:
        send_photo(image, caption, full_text)
    else:
        log("📷 بدون تصویر (ناموفق یا غیرفعال)؛ ارسال متنی")
        send_text(full_text)

    if not TELEGRAM_DRY:
        save_state(state)
    log("🏁 پایان — همه‌چیز موفق")
    return 0


# ======================================================================
#  تست داخلی:  python3 bot.py --selftest
# ======================================================================
def selftest() -> int:
    log("🧪 selftest شروع شد")
    # ۱) پارس AI_CONFIG
    sample_cfg = json.dumps({
        "gemini": ["AIza-test-key-111111", "AIza-test-key-222222"],
        "openai_compatible": [
            {"base_url": "https://api.x.ai/v1", "api_key": "xai-abc123", "model": "grok-4-fast"},
        ],
    })
    os.environ["AI_CONFIG"] = sample_cfg
    global ENGINES
    ENGINES = load_engines()
    assert len(ENGINES) == 3, f"موتورها: {len(ENGINES)}"
    log(f"✔ پارس AI_CONFIG: {len(ENGINES)} موتور → {[e.id for e in ENGINES]}")

    # ۲) چرخش و خنک‌سازی
    state = load_state()
    set_cooldown(state, ENGINES[0], minutes=60)
    assert ENGINES[0] not in ordered_engines(state)
    state["cooldowns"] = {}
    assert ENGINES[0] in ordered_engines(state)
    log("✔ منطق خنک‌سازی/چرخش موتورها درست کار می‌کند")

    # ۳) پارس JSON حتی داخل fence
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('متن اضافه {"a": {"b": 2}} ادامه') == {"a": {"b": 2}}
    log("✔ استخراج JSON از پاسخ‌های آلوده درست است")

    # ۴) رندر انواع پست
    d = extract_json(MOCK_RESPONSE)
    p1 = render_post(d, "https://example.com/p", "Nature Methods", "🧬")
    p2 = render_roadmap(
        {**d, "intro": "مقدمه تست", "steps": [
            {"title": "یادگیری پایتون", "detail": "شروع با Biopython"},
            {"title": "آموزش آمار", "detail": "مبانی آمار زیستی"},
        ], "final": "جمع‌بندی"},
        "https://example.com/r", "bioRxiv")
    cap = build_caption(d, "https://example.com/p", "Nature Methods", "🧬")
    assert "t.me/Bio_with_AI" in p1 and "t.me/Bio_with_AI" in p2 and "t.me/Bio_with_AI" in cap
    assert "منبع" in p1 and "کانال" in p1
    assert len(cap) <= 1024, f"caption بلند است: {len(cap)}"
    assert all(len(c) <= 4000 for c in split_message(p1 * 3))
    log(f"✔ رندر پست‌ها درست است (متن: {len(p1)}، رودمپ: {len(p2)}، کپشن: {len(cap)} کاراکتر)")
    print("\n——— نمونه پست خبری ———\n" + p1)
    print("\n——— نمونه رودمپ ———\n" + p2)
    print("\n——— نمونه کپشن تصویر ———\n" + cap)

    # ۵) انتخاب نوع وزنی
    counts = {t: 0 for t in ("news", "tip", "roadmap", "tool")}
    for _ in range(10000):
        counts[pick_type()] += 1
    log(f"✔ توزیع وزنی در ۱۰۰۰۰ انتخاب: {counts}")
    log("🧪 selftest کامل شد — همه‌چیز سالم است ✔")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(selftest() if SELFTEST else main())
    except Exception as exc:
        log(f"❌ خطای مهلک: {exc}")
        sys.exit(1)
