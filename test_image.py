#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
اسکریپت تست تصویر - برای دیباگ مشکل تولید تصویر
این اسکریپت رو جداگانه اجرا کن تا بفهمی مشکل کجاست
"""

import base64
import json
import os
import sys
import time
import requests

def log(msg):
    print(f"[TEST] {msg}", flush=True)

def test_gemini_image_generation(api_key, model):
    """تست تولید تصویر با جمینای"""
    log(f"🔍 تست تولید تصویر با مدل: {model}")
    
    prompt = "A simple scientific illustration of DNA double helix, clean modern style, blue and green colors"
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    
    payload = {
        "contents": [{
            "role": "user",
            "parts": [{
                "text": f"Generate an image: {prompt}"
            }]
        }],
        "generationConfig": {
            "responseModalities": ["IMAGE", "TEXT"],
            "temperature": 0.4
        }
    }
    
    try:
        log(f"📤 ارسال درخواست به: {url}")
        log(f"🔑 کلید: ...{api_key[-6:]}")
        
        resp = requests.post(
            url,
            params={"key": api_key},
            json=payload,
            timeout=60
        )
        
        log(f"📥 وضعیت پاسخ: HTTP {resp.status_code}")
        
        if resp.status_code == 200:
            body = resp.json()
            log(f"📄 ساختار پاسخ: {json.dumps(body, ensure_ascii=False)[:500]}")
            
            # بررسی بخش‌های مختلف پاسخ
            candidates = body.get("candidates", [])
            if not candidates:
                log("❌ هیچ candidate در پاسخ نیست")
                return None
            
            log(f"👥 تعداد candidates: {len(candidates)}")
            
            for i, candidate in enumerate(candidates):
                content = candidate.get("content", {})
                parts = content.get("parts", [])
                log(f"📦 Candidate {i}: {len(parts)} بخش")
                
                for j, part in enumerate(parts):
                    log(f"  بخش {j}: {list(part.keys())}")
                    
                    # روش 1: inlineData
                    if "inlineData" in part:
                        inline_data = part["inlineData"]
                        log(f"  📊 inlineData: mimeType={inline_data.get('mimeType', 'N/A')}, data_length={len(inline_data.get('data', ''))}")
                        
                        if inline_data.get("data"):
                            try:
                                image_data = base64.b64decode(inline_data["data"])
                                log(f"  ✅ تصویر decode شد: {len(image_data)} بایت")
                                
                                # ذخیره تصویر
                                with open("test_image.png", "wb") as f:
                                    f.write(image_data)
                                log(f"  💾 تصویر در test_image.png ذخیره شد")
                                
                                return image_data
                            except Exception as e:
                                log(f"  ❌ خطای decode: {e}")
                    
                    # روش 2: fileData
                    if "fileData" in part:
                        file_data = part["fileData"]
                        log(f"  📁 fileData: {file_data}")
                        
                        if file_data.get("fileUri"):
                            file_uri = file_data["fileUri"]
                            log(f"  🔗 دانلود از: {file_uri}")
                            
                            try:
                                img_resp = requests.get(file_uri, timeout=30)
                                if img_resp.status_code == 200:
                                    log(f"  ✅ تصویر دانلود شد: {len(img_resp.content)} بایت")
                                    return img_resp.content
                            except Exception as e:
                                log(f"  ❌ خطای دانلود: {e}")
                    
                    # متن در پاسخ
                    if "text" in part:
                        log(f"  📝 متن: {part['text'][:200]}")
            
            log("⚠️ پاسخ 200 بود ولی تصویری پیدا نشد")
            
        else:
            log(f"❌ خطا: {resp.text[:500]}")
            
            # اگر مدل وجود نداره
            if resp.status_code == 404:
                log(f"💡 مدل {model} وجود ندارد!")
            
            # اگر دسترسی نداریم
            elif resp.status_code == 403:
                log(f"💡 کلید اجازه دسترسی به {model} را ندارد!")
            
            # اگر محدودیت نرخ
            elif resp.status_code == 429:
                log(f"💡 محدودیت نرخ برای {model}!")
            
    except Exception as e:
        log(f"❌ خطای غیرمنتظره: {e}")
    
    return None


def test_telegram_send(bot_token, channel_id, image_data):
    """تست ارسال تصویر به تلگرام"""
    log(f"🔍 تست ارسال تصویر به تلگرام")
    
    if not image_data:
        log("❌ تصویری برای ارسال نیست")
        return False
    
    url = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
    
    try:
        # ذخیره موقت تصویر
        with open("test_upload.png", "wb") as f:
            f.write(image_data)
        
        log(f"📤 ارسال تصویر ({len(image_data)} بایت) به {channel_id}")
        
        with open("test_upload.png", "rb") as photo:
            resp = requests.post(
                url,
                data={
                    "chat_id": channel_id,
                    "caption": "🧪 تست تصویر",
                    "parse_mode": "HTML"
                },
                files={"photo": photo},
                timeout=30
            )
        
        log(f"📥 پاسخ تلگرام: HTTP {resp.status_code}")
        
        if resp.status_code == 200:
            body = resp.json()
            if body.get("ok"):
                log("✅ تصویر با موفقیت به تلگرام ارسال شد!")
                return True
            else:
                log(f"❌ خطای تلگرام: {body}")
        else:
            log(f"❌ خطای HTTP: {resp.text[:500]}")
            
    except Exception as e:
        log(f"❌ خطا: {e}")
    
    return False


def discover_available_models(api_key):
    """کشف مدل‌های در دسترس برای این کلید"""
    log("🔍 کشف مدل‌های در دسترس...")
    
    try:
        resp = requests.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            params={"key": api_key, "pageSize": 200},
            timeout=30
        )
        
        if resp.status_code == 200:
            models = resp.json().get("models", [])
            log(f"📋 {len(models)} مدل پیدا شد")
            
            # مدل‌هایی که تصویر تولید می‌کنن
            image_models = []
            chat_models = []
            
            for model in models:
                name = model.get("name", "").split("/")[-1]
                methods = model.get("supportedGenerationMethods", [])
                
                if "image" in name.lower() or "imagen" in name.lower():
                    image_models.append(name)
                elif "generateContent" in methods:
                    chat_models.append(name)
            
            log(f"🖼 مدل‌های تصویری: {image_models}")
            log(f"💬 مدل‌های متنی: {chat_models[:10]}")
            
            return image_models, chat_models
        else:
            log(f"❌ خطا در کشف مدل‌ها: {resp.text[:200]}")
            
    except Exception as e:
        log(f"❌ خطا: {e}")
    
    return [], []


def main():
    """تابع اصلی تست"""
    log("🧪 شروع تست جامع تصویر")
    log("=" * 60)
    
    # دریافت تنظیمات
    ai_config_raw = os.environ.get("AI_CONFIG", "")
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    bot_token = os.environ.get("BOT_TOKEN", "")
    channel_id = os.environ.get("CHANNEL_ID", "@Bio_with_AI")
    
    # استخراج کلیدهای جمینای
    gemini_keys = []
    
    if ai_config_raw:
        try:
            cfg = json.loads(ai_config_raw)
            for entry in cfg.get("gemini", []):
                if isinstance(entry, dict):
                    key = entry.get("api_key", "").strip()
                    if key:
                        gemini_keys.append(key)
                else:
                    key = str(entry).strip()
                    if key:
                        gemini_keys.append(key)
        except:
            pass
    
    if not gemini_keys and gemini_key:
        gemini_keys.append(gemini_key)
    
    if not gemini_keys:
        log("❌ هیچ کلید جمینای پیدا نشد!")
        return 1
    
    log(f"🔑 {len(gemini_keys)} کلید جمینای پیدا شد")
    
    # تست هر کلید
    for i, key in enumerate(gemini_keys):
        log("=" * 60)
        log(f"🔑 تست کلید {i+1}: ...{key[-6:]}")
        
        # کشف مدل‌های در دسترس
        image_models, chat_models = discover_available_models(key)
        
        # اگر مدل تصویری کشف شد، تست کن
        if image_models:
            for model in image_models[:3]:  # تست ۳ مدل اول
                log("-" * 40)
                image_data = test_gemini_image_generation(key, model)
                
                if image_data and bot_token:
                    # تست ارسال به تلگرام
                    test_telegram_send(bot_token, channel_id, image_data)
                    return 0
        else:
            log("⚠️ هیچ مدل تصویری کشف نشد! تلاش با مدل‌های پیش‌فرض...")
            
            # مدل‌های پیش‌فرض
            default_models = [
                "gemini-2.0-flash-exp-image-generation",
                "gemini-2.0-flash-preview-image-generation",
                "gemini-1.5-flash",
            ]
            
            for model in default_models:
                log("-" * 40)
                image_data = test_gemini_image_generation(key, model)
                
                if image_data and bot_token:
                    test_telegram_send(bot_token, channel_id, image_data)
                    return 0
    
    log("=" * 60)
    log("❌ تست کامل شد - هیچ تصویری تولید نشد")
    log("💡 نکات دیباگ:")
    log("  1. کلید API را چک کن - شاید دسترسی تصویر ندارد")
    log("  2. مدل‌های تصویری جدیدتر را امتحان کن")
    log("  3. شاید نیاز به فعال‌سازی سرویس تصویر در Google Cloud Console داری")
    log("  4. محدودیت نرخ را چک کن")
    
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("⏹ متوقف شد")
    except Exception as e:
        log(f"❌ خطای مهلک: {e}")
        sys.exit(1)
