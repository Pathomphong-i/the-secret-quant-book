#!/usr/bin/env python3
"""
หนังสือ: เลิกพึ่งบอทคนอื่น มาสร้างระบบเทรดของคุณเองด้วย Python
บทที่ 7: AI, LLM & ข้อมูลทางเลือกวิเคราะห์ข่าวและงบการเงิน (Multi-Modal AI & LLM Quant)
ผู้เขียน: ปฐมพงษ์ พิพัฒน์สุริยวงศ์
รวมซอร์สโค้ดครบทุกหัวข้อประจำบทที่ 7 พร้อมรันทดสอบได้ทันที
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

from typing import Any, Dict, List


def scan_lead_lag_value_chain_opportunities(
    leader_return_5d_pct: float,
    peers_data: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Identify high-quality laggard peers coiling after a sector leader breakout."""
    if leader_return_5d_pct < 5.0:
        return []  # Leader has not broken out strongly enough

    candidates: List[Dict[str, Any]] = []
    for peer in peers_data:
        gap_pct = leader_return_5d_pct - float(peer["return_5d_pct"])
        vol_awakening = float(peer["volume_ratio_20d"]) >= 1.20
        hygiene_ok = bool(peer["hygiene_gate_passed"])

        if (3.5 <= gap_pct <= 12.0) and vol_awakening and hygiene_ok:
            score = float(peer["value_chain_corr"]) * gap_pct
        else:
            score = 0.0

        if score >= 3.0:
            candidates.append({
                "ticker": peer["ticker"],
                "return_gap_pct": round(gap_pct, 2),
                "volume_ratio": peer["volume_ratio_20d"],
                "catch_up_score": round(score, 2),
            })

    return sorted(candidates, key=lambda x: x["catch_up_score"], reverse=True)


peers = [
    {"ticker": "PEER_PRIME", "return_5d_pct": 2.0, "volume_ratio_20d": 1.45, "value_chain_corr": 0.82, "hygiene_gate_passed": True},
    {"ticker": "PEER_TOXIC", "return_5d_pct": 1.0, "volume_ratio_20d": 1.60, "value_chain_corr": 0.80, "hygiene_gate_passed": False},
]
print(scan_lead_lag_value_chain_opportunities(11.0, peers))


# ==============================================================================

from typing import Any, Dict


def run_multimodal_ai_quant_gate(
    ticker: str,
    base_hrp_weight: float,
    hygiene_passed: bool,
    is_sell_on_fact_trap: bool,
    systemic_heat_mult: float,
    sector_rrg_mult: float,
    effective_news_score: float,
    max_single_stock_cap: float = 0.15,
) -> Dict[str, Any]:
    """Master Multi-Modal AI Gate integrating Technical, LLM, Macro, and Sector signals."""
    if not hygiene_passed:
        return {"ticker": ticker, "final_weight": 0.0, "status": "VETO_FUNDAMENTAL_HYGIENE"}
    if is_sell_on_fact_trap:
        return {"ticker": ticker, "final_weight": 0.0, "status": "VETO_SELL_ON_FACT_TRAP"}
    if sector_rrg_mult <= 0.0:
        return {"ticker": ticker, "final_weight": 0.0, "status": "VETO_LAGGING_SECTOR"}

    news_boost = 1.0 + (0.25 * max(-1.0, min(1.0, effective_news_score)))
    raw_weight = base_hrp_weight * systemic_heat_mult * sector_rrg_mult * news_boost
    final_weight = round(min(max_single_stock_cap, max(0.0, raw_weight)), 4)

    exec_algo = "TWAP_SNIPER" if effective_news_score >= 0.50 else "VWAP_PASSIVE"
    return {
        "ticker": ticker,
        "final_weight": final_weight,
        "status": "APPROVED_FOR_EXECUTION",
        "recommended_execution_algo": exec_algo,
    }


print(run_multimodal_ai_quant_gate("SUPER_STAR", 0.10, True, False, 1.0, 1.25, 0.80))
print(run_multimodal_ai_quant_gate("SOF_TRAP", 0.10, True, True, 1.0, 1.25, 0.85))



# ==============================================================================
# [LAST-MILE BRIDGE] โค้ดเชื่อมต่อ Google Gemini API (google-genai) แบบบังคับคืนค่า JSON
