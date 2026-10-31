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

from typing import Any, Dict


def detect_sell_on_fact_divergence(
    news_score: float,
    bid_vol: float,
    ask_vol: float,
    last_price: float,
    intraday_vwap: float,
) -> Dict[str, Any]:
    """Detect Sell-on-Fact distribution traps using LLM news + Order Book."""
    total_depth = bid_vol + ask_vol
    obi = (bid_vol - ask_vol) / total_depth if total_depth > 0 else 0.0
    below_vwap = last_price < intraday_vwap

    is_sell_on_fact = (news_score >= 0.70) and (obi < -0.25) and below_vwap
    is_confirmed_catalyst = (news_score >= 0.70) and (obi >= 0.15) and (not below_vwap)

    if is_sell_on_fact:
        regime = "SELL_ON_FACT_TRAP"
        allow_long = False
    elif is_confirmed_catalyst:
        regime = "CONFIRMED_BULLISH_CATALYST"
        allow_long = True
    else:
        regime = "NEUTRAL_OR_MIXED"
        allow_long = False

    return {
        "obi": round(obi, 4),
        "price_vs_vwap_pct": round((last_price / intraday_vwap - 1.0) * 100, 2),
        "regime": regime,
        "allow_long": allow_long,
    }


print(detect_sell_on_fact_divergence(0.82, 120_000, 310_000, 24.60, 25.10))


# ==============================================================================

import re
from datetime import datetime, time
from typing import Any, Dict


def sanitize_pit_news_prompt(
    raw_text: str,
    pub_timestamp: str,
    tickers_to_mask: list[str],
) -> Dict[str, Any]:
    """Anonymize entities/years to prevent LLM leakage and align PIT session."""
    sanitized = raw_text
    for idx, ticker in enumerate(tickers_to_mask, start=1):
        pattern = re.compile(rf"\b{re.escape(ticker)}\b", re.IGNORECASE)
        sanitized = pattern.sub(f"[ENTITY_{idx}]", sanitized)

    # Mask 4-digit years (e.g., 2020-2029 or 2563-2572) to block time memory
    sanitized = re.sub(r"\b(20\d{2}|25\d{2})\b", "[YEAR]", sanitized)

    dt = datetime.fromisoformat(pub_timestamp)
    pub_time = dt.time()
    if pub_time < time(9, 55):
        session = f"{dt.date()}_MORNING_OPEN"
    elif pub_time <= time(16, 25):
        session = f"{dt.date()}_INTRADAY_NEXT_BAR"
    else:
        session = f"{dt.date()}_NEXT_TRADING_DAY_OPEN"

    return {
        "published_at": pub_timestamp,
        "effective_trade_session": session,
        "sanitized_prompt_text": sanitized,
    }


sample_news = "In 2023, DELTA announced Q3 revenue expansion of 22% YoY."
print(sanitize_pit_news_prompt(sample_news, "2023-10-25T17:40:00", ["DELTA"]))


# ==============================================================================

from typing import Any, Dict


def evaluate_earnings_cash_quality(
    net_profit: float,
    operating_cash_flow: float,
    total_assets: float,
    receivables_growth_pct: float,
    revenue_growth_pct: float,
) -> Dict[str, Any]:
    """Detect Sloan accrual anomalies and paper-profit manipulation risks."""
    if total_assets <= 0:
        raise ValueError("total_assets must be positive.")

    ccr = operating_cash_flow / net_profit if net_profit > 0 else -1.0
    sloan_accrual_ratio = (net_profit - operating_cash_flow) / total_assets
    ar_divergence = receivables_growth_pct - revenue_growth_pct

    red_flags = []
    if net_profit > 0 and operating_cash_flow < 0:
        red_flags.append("NEGATIVE_OCF_WITH_POSITIVE_PROFIT")
    if sloan_accrual_ratio > 0.08:
        red_flags.append("HIGH_SLOAN_ACCRUAL_ANOMALY")
    if ar_divergence > 20.0:
        red_flags.append("ABNORMAL_RECEIVABLES_SURGE")

    return {
        "cash_conversion_ratio": round(ccr, 3),
        "sloan_accrual_ratio": round(sloan_accrual_ratio, 4),
        "ar_vs_rev_divergence_pct": round(ar_divergence, 2),
        "red_flags": red_flags,
        "is_cash_healthy": len(red_flags) == 0 and ccr >= 0.75,
    }


print(evaluate_earnings_cash_quality(500.0, -340.0, 5000.0, 58.0, 10.0))


