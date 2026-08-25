#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
تست تولید تصویر با سرویس‌های مختلف
"""

import base64
import json
import os
import re
import sys
import time
import requests
from datetime import datetime

def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}", flush=True)


def test_pollinations(prompt):
    """تست Pollinations.ai - رایگان و بدون نیاز به API key"""
    log("🎨 تست Pollinations.ai (رایگان)...")
    
    try:
        # روش 1: ساده
        url = f"https://image.pollinations.ai/prompt/{requests.utils.quote(prompt)}"
        params = {
            "width": 1024,
            "height": 1024,
            "nologo": "true"
        }
        
        resp = requests.get(url, params=params, timeout=60)
        
        log(f"📥 HTTP {resp.status_code}")
        log(f"📏 حجم پاسخ: {len(resp.content)} بایت")
        
        if resp.status_code == 200 and len(resp.content) > 1000:
            log(f"✅ تصویر ساخته شد: {len(resp.content)} بایت")
            
            # ذخیره تصویر
            with open("test_pollinations.png", "wb") as f:
                f.write(resp.content)
            log("💾 ذخیره شد: test_pollinations.png")
            
            return resp.content
        else:
            log(f"❌ خطا: {resp.text[:200] if resp.text else 'empty'}")
            
    except Exception as e:
        log(f"❌ خطا: {e}")
    
    return None


def test_pollinations_v2(prompt):
    """تست Pollinations.ai با مدل flux"""
    log("🎨 تست Pollinations.ai با مدل flux...")
    
    try:
        url = "https://image.pollinations.ai/prompt/" + requests.utils.quote(prompt)
        params = {
            "width": 1024,
            "height": 1024,
            "model": "flux",
            "nologo": "true",
            "seed": "12345"
        }
        
        resp = requests.get(url, params=params, timeout=60)
        
        log(f"📥 HTTP {resp.status_code}")
        log(f"📏 حجم پاسخ: {len(resp.content)} بایت")
        
        if resp.status_code == 200 and len(resp.content) > 1000:
            log(f"✅ تصویر ساخته شد: {len(resp.content)} بایت")
            
            with open("test_pollinations_flux.png", "wb") as f:
                f.write(resp.content)
            log("💾 ذخیره شد: test_pollinations_flux.png")
            
            return resp.content
        else:
            log(f"❌ خطا: {resp.text[:200] if resp.text else 'empty'}")
            
    except Exception as e:
        log(f"❌ خطا: {e}")
    
    return None


def test_xai_image(prompt, api_key):
    """تست xAI (Grok) برای تولید تصویر"""
    log("🤖 تست xAI (Grok) برای تولید تصویر...")
    
    try:
        url = "https://api.x.ai/v1/images/generations"
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "grok-2-image",
            "prompt": prompt,
            "n": 1,
            "size": "1024x1024"
        }
        
        log(f"📤 ارسال به: {url}")
        log(f"🔑 کلید: ...{api_key[-6:]}")
        
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        
        log(f"📥 HTTP {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            log(f"📄 ساختار پاسخ: {json.dumps(data, ensure_ascii=False)[:300]}")
            
            # بررسی URL
            if "data" in data and len(data["data"]) > 0:
                image_url = data["data"][0].get("url", "")
                if image_url:
                    log(f"🔗 دانلود از: {image_url}")
                    img_resp = requests.get(image_url, timeout=30)
                    if img_resp.status_code == 200 and len(img_resp.content) > 1000:
                        log(f"✅ تصویر دانلود شد: {len(img_resp.content)} بایت")
                        
                        with open("test_xai.png", "wb") as f:
                            f.write(img_resp.content)
                        log("💾 ذخیره شد: test_xai.png")
                        
                        return img_resp.content
            
            # بررسی base64
            if "data" in data and len(data["data"]) > 0:
                b64_data = data["data"][0].get("b64_json", "")
                if b64_data:
                    image = base64.b64decode(b64_data)
                    log(f"✅ تصویر decode شد: {len(image)} بایت")
                    
                    with open("test_xai.png", "wb") as f:
                        f.write(image)
                    log("💾 ذخیره شد: test_xai.png")
                    
                    return image
        else:
            log(f"❌ خطا: {resp.text[:300]}")
            
    except Exception as e:
        log(f"❌ خطا: {e}")
    
    return None


def test_openai_compatible_image(prompt, base_url, api_key, model):
    """تست سرویس‌های OpenAI-compatible برای تولید تصویر"""
    log(f"🎨 تست {base_url} با مدل {model}...")
    
    # روش 1: images/generations endpoint
    try:
        url = f"{base_url}/images/generations"
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": model,
            "prompt": prompt,
            "n": 1,
            "size": "1024x1024"
        }
        
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        
        log(f"📥 HTTP {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            log(f"📄 پاسخ: {json.dumps(data, ensure_ascii=False)[:300]}")
            
            if "data" in data and len(data["data"]) > 0:
                # URL
                image_url = data["data"][0].get("url", "")
                if image_url:
                    img_resp = requests.get(image_url, timeout=30)
                    if img_resp.status_code == 200 and len(img_resp.content) > 1000:
                        log(f"✅ تصویر دانلود شد: {len(img_resp.content)} بایت")
                        return img_resp.content
                
                # base64
                b64_data = data["data"][0].get("b64_json", "")
                if b64_data:
                    image = base64.b64decode(b64_data)
                    log(f"✅ تصویر decode شد: {len(image)} بایت")
                    return image
        else:
            log(f"❌ endpoint تصویر ندارد: {resp.text[:200]}")
            
    except Exception as e:
        log(f"❌ خطا: {e}")
    
    # روش 2: chat/completions با درخواست تصویر
    log("🔄 تلاش با chat/completions...")
    
    try:
        url = f"{base_url}/chat/completions"
        
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": model,
            "messages": [
                {"role": "user", "content": f"Generate an image based on this description and return the image URL: {prompt}"}
            ],
            "max_tokens": 1000
        }
        
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        
        log(f"📥 HTTP {resp.status_code}")
        
        if resp.status_code == 200:
            data = resp.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            log(f"📝 پاسخ: {content[:300]}")
            
            # استخراج URL تصویر از پاسخ
            urls = re.findall(r'https?://[^\s<>"]+?\.(?:png|jpg|jpeg|gif|webp)', content)
            if urls:
                log(f"🔗 URL پیدا شد: {urls[0]}")
                img_resp = requests.get(urls[0], timeout=30)
                if img_resp.status_code == 200 and len(img_resp.content) > 1000:
                    log(f"✅ تصویر دانلود شد: {len(img_resp.content)} بایت")
                    return img_resp.content
        else:
            log(f"❌ خطا: {resp.text[:200]}")
            
    except Exception as e:
        log(f"❌ خطا: {e}")
    
    return None


def main():
    log("=" * 60)
    log("🧪 شروع تست جامع تولید تصویر")
    log("=" * 60)
    
    ai_config_raw = os.environ.get("AI_CONFIG", "")
    prompt = "A beautiful scientific illustration of DNA double helix with glowing blue and green colors, modern infographic style, high quality"
    
    log(f"📝 پرامپت: {prompt}")
    log(f"📏 طول AI_CONFIG: {len(ai_config_raw)}")
    
    # ======================================================================
    # 1. تست Pollinations.ai (رایگان - بدون نیاز به کلید)
    # ======================================================================
    log("\n" + "=" * 60)
    log("1️⃣ تست Pollinations.ai (رایگان)")
    log("=" * 60)
    
    image = test_pollinations(prompt)
    if not image:
        log("\n🔄 تلاش با روش دوم Pollinations...")
        image = test_pollinations_v2(prompt)
    
    if image:
        log("\n✅✅✅ Pollinations.ai کار میکنه!")
        log("💡 از این سرویس برای تولید تصویر در ربات استفاده کن")
        return 0
    
    # ======================================================================
    # 2. تست سرویس‌های OpenAI-compatible از AI_CONFIG
    # ======================================================================
    if ai_config_raw:
        log("\n" + "=" * 60)
        log("2️⃣ تست سرویس‌های OpenAI-compatible")
        log("=" * 60)
        
        try:
            cfg = json.loads(ai_config_raw)
            
            for entry in cfg.get("openai_compatible", []):
                base_url = entry.get("base_url", "")
                api_key = entry.get("api_key", "")
                model = entry.get("model", "")
                
                log(f"\n🔍 تست {base_url} با مدل {model}")
                
                # تست xAI
                if "x.ai" in base_url:
                    log("🤖 این xAI هست - تست اختصاصی")
                    image = test_xai_image(prompt, api_key)
                else:
                    image = test_openai_compatible_image(prompt, base_url, api_key, model)
                
                if image:
                    log(f"\n✅✅✅ {base_url} کار میکنه!")
                    
                    # ذخیره تصویر
                    filename = f"test_{base_url.split('//')[1].split('.')[0]}.png"
                    with open(filename, "wb") as f:
                        f.write(image)
                    log(f"💾 ذخیره شد: {filename}")
                    
                    return 0
                    
        except Exception as e:
            log(f"❌ خطا در پردازش AI_CONFIG: {e}")
    
    # ======================================================================
    # 3. نتیجه نهایی
    # ======================================================================
    log("\n" + "=" * 60)
    log("❌ هیچ سرویسی نتونست تصویر تولید کنه")
    log("=" * 60)
    log("💡 پیشنهادات:")
    log("  1. Pollinations.ai رایگانه - باید کار کنه")
    log("  2. اگه Pollinations کار نکرد، مشکل از شبکه GitHub Actions هست")
    log("  3. میتونی از Unsplash یا Pexels API برای تصاویر استوک استفاده کنی")
    
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
