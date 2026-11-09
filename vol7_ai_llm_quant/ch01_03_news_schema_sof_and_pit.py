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
from datetime import date, datetime, time, timedelta
from typing import Any, Dict
from zoneinfo import ZoneInfo

BKK_TZ = ZoneInfo("Asia/Bangkok")


def _next_set_trading_day(d: date, holidays: set[str]) -> date:
    """เลื่อนไปหาวันทำการถัดไปของตลาดหลักทรัพย์ฯ (ข้ามเสาร์-อาทิตย์ และวันหยุดนักขัตฤกษ์)"""
    cur = d
    while cur.weekday() >= 5 or cur.isoformat() in holidays:
        cur += timedelta(days=1)
    return cur


def sanitize_pit_news_prompt(
    raw_text: str,
    pub_timestamp: str,
    tickers_to_mask: list[str],
    received_timestamp: str | None = None,
    set_holidays: set[str] | None = None,
) -> Dict[str, Any]:
    """Anonymize entities/years and align PIT session using available_at, Asia/Bangkok TZ & SET calendar."""
    holidays = set_holidays or set()
    sanitized = raw_text
    for idx, ticker in enumerate(tickers_to_mask, start=1):
        pattern = re.compile(rf"\b{re.escape(ticker)}\b", re.IGNORECASE)
        sanitized = pattern.sub(f"[ENTITY_{idx}]", sanitized)

    # Mask 4-digit years (e.g., 2020-2029 or 2563-2572) to reduce direct date memorization
    sanitized = re.sub(r"\b(20\d{2}|25\d{2})\b", "[YEAR]", sanitized)

    pub_dt = datetime.fromisoformat(pub_timestamp)
    if pub_dt.tzinfo is None:
        pub_dt = pub_dt.replace(tzinfo=BKK_TZ)
    else:
        pub_dt = pub_dt.astimezone(BKK_TZ)

    if received_timestamp:
        rec_dt = datetime.fromisoformat(received_timestamp)
        rec_dt = rec_dt.replace(tzinfo=BKK_TZ) if rec_dt.tzinfo is None else rec_dt.astimezone(BKK_TZ)
        avail_dt = max(pub_dt, rec_dt)
    else:
        avail_dt = pub_dt

    avail_date = avail_dt.date()
    avail_time = avail_dt.time()
    is_trading_day = (avail_date.weekday() < 5) and (avail_date.isoformat() not in holidays)

    if not is_trading_day:
        next_day = _next_set_trading_day(avail_date + timedelta(days=1), holidays)
        session = f"{next_day.isoformat()}_MORNING_ATO_OPEN"
    elif avail_time < time(9, 55):
        session = f"{avail_date.isoformat()}_MORNING_ATO_OPEN"
    elif avail_time <= time(12, 30):
        session = f"{avail_date.isoformat()}_MORNING_INTRADAY_NEXT_BAR"
    elif avail_time < time(14, 25):
        session = f"{avail_date.isoformat()}_AFTERNOON_ATO2_OPEN"
    elif avail_time <= time(16, 25):
        session = f"{avail_date.isoformat()}_AFTERNOON_INTRADAY_NEXT_BAR"
    else:
        next_day = _next_set_trading_day(avail_date + timedelta(days=1), holidays)
        session = f"{next_day.isoformat()}_MORNING_ATO_OPEN"

    return {
        "published_at": pub_dt.isoformat(),
        "available_at": avail_dt.isoformat(),
        "effective_trade_session": session,
        "sanitized_prompt_text": sanitized,
    }


sample_news = "In 2023, OMEGA announced Q3 revenue expansion of 22% YoY."
print(
    sanitize_pit_news_prompt(
        sample_news,
        pub_timestamp="2023-10-20T17:40:00+07:00",
        tickers_to_mask=["OMEGA"],
        received_timestamp="2023-10-20T17:42:15+07:00",
        set_holidays={"2023-10-23"},  # วันปิยมหาราช (วันจันทร์หยุด -> เลื่อนไปอังคาร 24 ต.ค.)
    )
)


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


