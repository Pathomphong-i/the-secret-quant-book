#!/usr/bin/env python3
"""
The Secret Quant: 8-Volume Masterclass Series
เล่มที่ 7: AI, LLM & ข้อมูลทางเลือกวิเคราะห์ข่าวและงบการเงิน (Multi-Modal AI & LLM Quant)
ผู้เขียน: ปฐมพงษ์ พิพัฒน์สุริยวงศ์
รวมซอร์สโค้ดครบทุกบทประจำเล่มที่ 7 พร้อมรันทดสอบได้ทันที
"""

from __future__ import annotations
import json, math, os, sqlite3, hashlib
import numpy as np
import pandas as pd

import json
from typing import Any, Dict


def parse_news_to_structured_signal(
    raw_llm_json: str,
    verified_weight: float = 1.0,
    unverified_weight: float = 0.4,
) -> Dict[str, Any]:
    """Validate LLM JSON output against strict schema and compute news alpha."""
    data = json.loads(raw_llm_json)
    required_keys = {
        "sentiment_score",
        "materiality_score",
        "catalyst_type",
        "is_verified_contract",
    }
    if not required_keys.issubset(data.keys()):
        raise ValueError(f"Missing schema keys: {required_keys - set(data.keys())}")

    sentiment = max(-1.0, min(1.0, float(data["sentiment_score"])))
    materiality = max(0.0, min(1.0, float(data["materiality_score"])))
    is_verified = bool(data["is_verified_contract"])
    lambd = verified_weight if is_verified else unverified_weight
    effective_score = round(sentiment * materiality * lambd, 4)

    return {
        "catalyst_type": str(data["catalyst_type"]),
        "sentiment_score": sentiment,
        "materiality_score": materiality,
        "is_verified_contract": is_verified,
        "effective_news_score": effective_score,
        "is_actionable": abs(effective_score) >= 0.35,
    }


sample_output = '{"sentiment_score": 0.85, "materiality_score": 0.90, "catalyst_type": "EARNINGS_CORE", "is_verified_contract": true}'
print(parse_news_to_structured_signal(sample_output))


# ==============================================================================
import os

def call_gemini_structured_json(
    system_prompt: str,
    user_text: str,
    api_key: str | None = None,
    model_name: str = "gemini-2.5-flash",
) -> str:
    """
    ส่ง System Prompt และข้อความข่าว/MD&A เข้าสู่ Google Gemini API โดยบังคับ
    temperature=0.0 และ response_mime_type="application/json" เพื่อส่งต่อเข้าฟังก์ชัน
    parse_news_to_structured_signal() หรือ analyze_mda_tone_and_red_flags() ได้ทันที
    (หากยังไม่ได้ตั้งค่า GEMINI_API_KEY จะคืนค่า JSON ตัวอย่างเพื่อให้ทดสอบท่อโค้ดได้ทันที)
    """
    key = api_key or os.environ.get("GEMINI_API_KEY", "").strip()
    if key:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=key)
        resp = client.models.generate_content(
            model=model_name,
            contents=user_text,
            config=types.GenerateContentConfig(
                system_instruction=system_prompt,
                temperature=0.0,
                response_mime_type="application/json",
            ),
        )
        return resp.text or "{}"
    return json.dumps({
        "sentiment_score": 0.85,
        "materiality_score": 0.90,
        "catalyst_type": "EARNINGS_BEAT",
        "is_verified_contract": True,
        "rationale": "กำไรสุทธิไตรมาสล่าสุดเติบโต +34% YoY พร้อมตัวเลขคำสั่งซื้อดาต้าเซ็นเตอร์ชัดเจน",
    }, ensure_ascii=False)

if __name__ == "__main__":
    raw_json_from_llm = call_gemini_structured_json(
        system_prompt="You are a quantitative financial news extractor. Return strict JSON.",
        user_text="บริษัทประกาศกำไรไตรมาส 3 เติบโต 34% YoY จากยอดขายกลุ่ม Cloud Data Center",
    )
    print("[Gemini API Bridge] Parsed Signal:", parse_news_to_structured_signal(raw_json_from_llm))
