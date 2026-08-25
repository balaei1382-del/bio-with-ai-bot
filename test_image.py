#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
تست ساده تولید تصویر با جمینای
"""

import base64
import json
import os
import sys
import requests

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)

def main():
    print("=" * 60)
    print("🧪 شروع تست تصویر")
    print("=" * 60)
    
    # چک کردن متغیرهای محیطی
    ai_config = os.environ.get("AI_CONFIG", "")
    gemini_key = os.environ.get("GEMINI_API_KEY", "")
    bot_token = os.environ.get("BOT_TOKEN", "")
    
    print(f"AI_CONFIG length: {len(ai_config)}")
    print(f"GEMINI_API_KEY length: {len(gemini_key)}")
    print(f"BOT_TOKEN length: {len(bot_token)}")
    
    # استخراج کلید جمینای
    keys = []
    
    if ai_config:
        try:
            cfg = json.loads(ai_config)
            for entry in cfg.get("gemini", []):
                if isinstance(entry, dict):
                    key = entry.get("api_key", "")
                    if key:
                        keys.append(key)
                        print(f"✅ کلید از AI_CONFIG: ...{key[-6:]}")
                elif isinstance(entry, str) and entry:
                    keys.append(entry)
                    print(f"✅ کلید از AI_CONFIG (string): ...{entry[-6:]}")
        except Exception as e:
            print(f"❌ خطا در پارس AI_CONFIG: {e}")
    
    if not keys and gemini_key:
        keys.append(gemini_key)
        print(f"✅ کلید از GEMINI_API_KEY: ...{gemini_key[-6:]}")
    
    if not keys:
        print("❌ هیچ کلیدی پیدا نشد!")
        return 1
    
    print(f"\n📊 تعداد کلیدها: {len(keys)}")
    
    # تست تولید تصویر
    for key in keys:
        print(f"\n🔑 تست کلید: ...{key[-6:]}")
        
        # مدلهای مختلف
        models = [
            "gemini-2.0-flash-exp-image-generation",
            "gemini-2.0-flash-preview-image-generation",
            "gemini-1.5-flash",
            "gemini-2.0-flash",
            "gemini-1.5-pro",
        ]
        
        for model in models:
            print(f"\n  📝 تست مدل: {model}")
            
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
            
            payload = {
                "contents": [{
                    "role": "user",
                    "parts": [{
                        "text": "Generate a simple scientific illustration of DNA"
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
                    timeout=30
                )
                
                print(f"  📥 HTTP {resp.status_code}")
                
                if resp.status_code == 200:
                    body = resp.json()
                    
                    # چاپ ساختار پاسخ
                    print(f"  📄 پاسخ: {json.dumps(body, ensure_ascii=False)[:300]}")
                    
                    # بررسی تصویر
                    candidates = body.get("candidates", [])
                    for cand in candidates:
                        parts = cand.get("content", {}).get("parts", [])
                        for part in parts:
                            if "inlineData" in part:
                                data = part["inlineData"].get("data", "")
                                if data:
                                    image = base64.b64decode(data)
                                    print(f"  ✅ تصویر پیدا شد: {len(image)} بایت")
                                    
                                    # ذخیره
                                    with open("test_image.png", "wb") as f:
                                        f.write(image)
                                    print(f"  💾 ذخیره شد: test_image.png")
                                    return 0
                            
                            if "text" in part:
                                print(f"  📝 متن: {part['text'][:200]}")
                    
                    print(f"  ⚠️ پاسخ 200 ولی بدون تصویر")
                    
                elif resp.status_code == 404:
                    print(f"  ❌ مدل وجود ندارد")
                    continue
                    
                elif resp.status_code == 403:
                    print(f"  ❌ دسترسی ندارید")
                    continue
                    
                elif resp.status_code == 429:
                    print(f"  ⏳ محدودیت نرخ، ۲ ثانیه صبر...")
                    import time
                    time.sleep(2)
                    continue
                    
                else:
                    print(f"  ❌ خطا: {resp.text[:200]}")
                    continue
                    
            except Exception as e:
                print(f"  ❌ خطا: {e}")
                continue
    
    print("\n❌ هیچ تصویری تولید نشد")
    return 1

if __name__ == "__main__":
    from datetime import datetime
    try:
        sys.exit(main())
    except Exception as e:
        print(f"❌ خطای مهلک: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
