#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
تست کامل تولید تصویر با Nano Banana - جستجو در همه مدل‌ها
"""

import base64
import json
import os
import sys
import time
import requests
from datetime import datetime

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def test_model(api_key, model_name, prompt):
    """تست یک مدل خاص"""
    log(f"\n  📝 تست مدل: {model_name}")
    
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
    
    payload = {
        "contents": [{
            "role": "user",
            "parts": [{
                "text": f"Generate a high-quality image: {prompt}"
            }]
        }],
        "generationConfig": {
            "responseModalities": ["IMAGE", "TEXT"],
            "temperature": 0.4
        }
    }
    
    try:
        resp = requests.post(
            url,
            params={"key": api_key},
            json=payload,
            timeout=60
        )
        
        log(f"  📥 HTTP {resp.status_code}")
        
        if resp.status_code == 200:
            body = resp.json()
            
            # بررسی کامل پاسخ
            candidates = body.get("candidates", [])
            for cand_idx, cand in enumerate(candidates):
                parts = cand.get("content", {}).get("parts", [])
                log(f"  📦 Candidate {cand_idx}: {len(parts)} بخش")
                
                for part_idx, part in enumerate(parts):
                    # روش 1: inlineData
                    if "inlineData" in part:
                        data = part["inlineData"].get("data", "")
                        mime = part["inlineData"].get("mimeType", "unknown")
                        log(f"  📊 inlineData: mime={mime}, size={len(data)}")
                        
                        if data:
                            try:
                                image = base64.b64decode(data)
                                log(f"  ✅ تصویر decode شد: {len(image)} بایت")
                                
                                with open(f"test_{model_name}.png", "wb") as f:
                                    f.write(image)
                                log(f"  💾 ذخیره شد: test_{model_name}.png")
                                
                                return image
                            except Exception as e:
                                log(f"  ❌ خطای decode: {e}")
                    
                    # روش 2: fileData
                    if "fileData" in part:
                        file_uri = part["fileData"].get("fileUri", "")
                        log(f"  📁 fileData: {file_uri}")
                        
                        if file_uri:
                            try:
                                img_resp = requests.get(file_uri, timeout=30)
                                if img_resp.status_code == 200:
                                    log(f"  ✅ دانلود شد: {len(img_resp.content)} بایت")
                                    return img_resp.content
                            except Exception as e:
                                log(f"  ❌ خطای دانلود: {e}")
                    
                    # روش 3: متن
                    if "text" in part:
                        text = part["text"][:150]
                        log(f"  📝 متن: {text}")
            
            log(f"  ⚠️ پاسخ 200 ولی بدون تصویر")
            return None
            
        elif resp.status_code == 404:
            log(f"  ❌ مدل وجود ندارد (404)")
            return None
            
        elif resp.status_code == 403:
            log(f"  ❌ دسترسی ندارید (403)")
            return None
            
        elif resp.status_code == 429:
            log(f"  ⏳ محدودیت نرخ (429)")
            return None
            
        elif resp.status_code == 400:
            log(f"  ❌ درخواست بد (400): {resp.text[:200]}")
            return None
            
        else:
            log(f"  ❌ خطای {resp.status_code}: {resp.text[:200]}")
            return None
            
    except requests.Timeout:
        log(f"  ⏱ تایم‌اوت")
        return None
    except Exception as e:
        log(f"  ❌ خطا: {str(e)[:200]}")
        return None


def discover_all_models(api_key):
    """کشف همه مدل‌های در دسترس"""
    log("\n🔍 کشف همه مدل‌های در دسترس...")
    
    try:
        resp = requests.get(
            "https://generativelanguage.googleapis.com/v1beta/models",
            params={"key": api_key, "pageSize": 200},
            timeout=30
        )
        
        if resp.status_code == 200:
            models = resp.json().get("models", [])
            log(f"📋 {len(models)} مدل پیدا شد")
            
            all_models = []
            for model in models:
                name = model.get("name", "").split("/")[-1]
                methods = model.get("supportedGenerationMethods", [])
                display_name = model.get("displayName", "")
                
                all_models.append({
                    "name": name,
                    "display_name": display_name,
                    "methods": methods
                })
                
                log(f"  📌 {name} - {display_name}")
                log(f"     methods: {methods}")
            
            return all_models
        else:
            log(f"❌ خطا در کشف: HTTP {resp.status_code}")
            return []
            
    except Exception as e:
        log(f"❌ خطا: {e}")
        return []


def main():
    log("=" * 60)
    log("🧪 تست جامع تولید تصویر با Nano Banana")
    log("=" * 60)
    
    ai_config_raw = os.environ.get("AI_CONFIG", "")
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    
    # استخراج کلیدهای جمینای
    keys = []
    
    if ai_config_raw:
        try:
            cfg = json.loads(ai_config_raw)
            for entry in cfg.get("gemini", []):
                if isinstance(entry, dict):
                    key = entry.get("api_key", "")
                    if key:
                        keys.append(key)
                        log(f"✅ کلید از AI_CONFIG: ...{key[-6:]}")
                elif isinstance(entry, str) and entry:
                    keys.append(entry)
                    log(f"✅ کلید از AI_CONFIG: ...{entry[-6:]}")
        except Exception as e:
            log(f"❌ خطا در پارس AI_CONFIG: {e}")
    
    if not keys and gemini_key:
        keys.append(gemini_key)
        log(f"✅ کلید از GEMINI_API_KEY: ...{gemini_key[-6:]}")
    
    if not keys:
        log("❌ هیچ کلیدی پیدا نشد!")
        return 1
    
    log(f"\n📊 تعداد کلیدها: {len(keys)}")
    
    prompt = "A beautiful scientific illustration of DNA double helix, modern infographic style, blue and green colors, high quality"
    
    # مدل‌های احتمالی Nano Banana
    nano_banana_candidates = [
        "gemini-2.5-flash-image",
        "gemini-2.5-flash-image-generation",
        "gemini-2.5-flash-preview-image",
        "gemini-2.5-flash-preview-image-generation",
        "gemini-2.5-pro-image",
        "gemini-2.5-pro-image-generation",
        "gemini-2.0-flash-image",
        "gemini-2.0-flash-image-generation",
        "gemini-2.0-flash-preview-image-generation",
        "gemini-2.0-flash-exp-image-generation",
        "gemini-3-pro-image",
        "gemini-3-flash-image",
        "gemini-3-pro-image-generation",
        "gemini-3-flash-image-generation",
        "gemini-pro-image",
        "gemini-flash-image",
        "nano-banana",
        "nano-banana-pro",
        "nano-banana-flash",
    ]
    
    # تست هر کلید
    for key_idx, key in enumerate(keys):
        log(f"\n{'=' * 60}")
        log(f"🔑 کلید {key_idx + 1}: ...{key[-6:]}")
        log(f"{'=' * 60}")
        
        # اول کشف مدل‌های در دسترس
        all_models = discover_all_models(key)
        
        # مدل‌هایی که اسمشون شبیه image هست
        image_models = [m["name"] for m in all_models if "image" in m["name"].lower()]
        log(f"\n🖼 مدل‌های تصویری کشف شده: {image_models}")
        
        # تست مدل‌های کشف شده
        for model in image_models:
            image = test_model(key, model, prompt)
            if image:
                log(f"\n✅✅✅ مدل {model} کار میکنه!")
                log(f"💾 تصویر ذخیره شد: test_{model}.png")
                return 0
            time.sleep(1)  # فاصله بین تست‌ها
        
        # اگه مدل تصویری کشف نشد، مدل‌های کاندید رو تست کن
        if not image_models:
            log(f"\n⚠️ مدل تصویری کشف نشد! تست مدل‌های کاندید...")
            
            for model in nano_banana_candidates:
                image = test_model(key, model, prompt)
                if image:
                    log(f"\n✅✅✅ مدل {model} کار میکنه!")
                    return 0
                time.sleep(1)
    
    log("\n❌ هیچ مدلی نتونست تصویر تولید کنه")
    log("💡 پیشنهاد:")
    log("  1. کلید API رو چک کن - شاید دسترسی تصویر نداری")
    log("  2. به Google Cloud Console برو و Image Generation API رو فعال کن")
    log("  3. از کلید دیگه‌ای استفاده کن")
    
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("⏹ متوقف شد")
    except Exception as e:
        log(f"❌ خطای مهلک: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
