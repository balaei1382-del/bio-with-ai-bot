#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
تست تولید تصویر با Nano Banana (جمینای)
"""

import base64
import json
import os
import sys
import requests
from datetime import datetime

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def main():
    log("=" * 60)
    log("🧪 تست تولید تصویر با Nano Banana")
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
                        log(f"✅ کلید: ...{key[-6:]}")
                elif isinstance(entry, str) and entry:
                    keys.append(entry)
                    log(f"✅ کلید: ...{entry[-6:]}")
        except Exception as e:
            log(f"❌ خطا در پارس AI_CONFIG: {e}")
    
    if not keys and gemini_key:
        keys.append(gemini_key)
        log(f"✅ کلید: ...{gemini_key[-6:]}")
    
    if not keys:
        log("❌ هیچ کلیدی پیدا نشد!")
        return 1
    
    log(f"\n📊 تعداد کلیدها: {len(keys)}")
    
    # مدل‌های Nano Banana
    nano_banana_models = [
        "gemini-2.5-flash-image",           # Nano Banana جدید
        "gemini-2.5-flash-preview-image",   # نسخه پیش‌نمایش
        "gemini-2.0-flash-preview-image-generation",
        "gemini-2.0-flash-exp-image-generation",
        "gemini-2.5-pro-image",              # نسخه Pro
        "gemini-2.5-flash-image-generation",
        "gemini-3-pro-image",                # جدیدترین
        "gemini-3-flash-image",
    ]
    
    prompt = "A beautiful scientific illustration of DNA double helix with glowing blue and green colors, modern infographic style, high quality, detailed"
    
    for key in keys:
        log(f"\n🔑 تست کلید: ...{key[-6:]}")
        
        for model in nano_banana_models:
            log(f"\n  📝 تست مدل: {model}")
            
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            
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
                    params={"key": key},
                    json=payload,
                    timeout=60
                )
                
                log(f"  📥 HTTP {resp.status_code}")
                
                if resp.status_code == 200:
                    body = resp.json()
                    
                    # بررسی تصویر
                    candidates = body.get("candidates", [])
                    for cand in candidates:
                        parts = cand.get("content", {}).get("parts", [])
                        for part in parts:
                            if "inlineData" in part:
                                data = part["inlineData"].get("data", "")
                                if data:
                                    image = base64.b64decode(data)
                                    log(f"  ✅ تصویر پیدا شد: {len(image)} بایت")
                                    
                                    with open("test_nano_banana.png", "wb") as f:
                                        f.write(image)
                                    log(f"  💾 ذخیره شد: test_nano_banana.png")
                                    return 0
                            
                            if "fileData" in part:
                                file_uri = part["fileData"].get("fileUri", "")
                                if file_uri:
                                    log(f"  📁 دانلود از: {file_uri}")
                                    img_resp = requests.get(file_uri, timeout=30)
                                    if img_resp.status_code == 200:
                                        log(f"  ✅ دانلود شد: {len(img_resp.content)} بایت")
                                        return 0
                            
                            if "text" in part:
                                log(f"  📝 متن: {part['text'][:200]}")
                    
                    log(f"  ⚠️ پاسخ 200 ولی بدون تصویر")
                    
                elif resp.status_code == 404:
                    log(f"  ❌ مدل وجود ندارد")
                    continue
                    
                elif resp.status_code == 403:
                    log(f"  ❌ دسترسی ندارید")
                    continue
                    
                elif resp.status_code == 429:
                    log(f"  ⏳ محدودیت نرخ")
                    continue
                    
                else:
                    log(f"  ❌ خطا: {resp.text[:200]}")
                    
            except Exception as e:
                log(f"  ❌ خطا: {e}")
                continue
    
    log("\n❌ هیچ مدلی نتونست تصویر تولید کنه")
    return 1

if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        log(f"❌ خطای مهلک: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
