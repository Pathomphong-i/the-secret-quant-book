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

import math
from typing import Any, Dict


def compute_smart_money_flow_score(
    set_net_flow_5d_mb: float,
    tfex_net_contracts_5d: float,
    nvdr_net_turnover_ratio_5d: float,
) -> Dict[str, Any]:
    """Compute Smart Money Flow score across SET equity, TFEX S50, and NVDR."""
    s_set = math.tanh(set_net_flow_5d_mb / 5000.0)
    s_tfex = math.tanh(tfex_net_contracts_5d / 25000.0)
    s_nvdr = math.tanh(nvdr_net_turnover_ratio_5d / 0.10)

    composite = 0.35 * s_set + 0.35 * s_tfex + 0.30 * s_nvdr
    tfex_divergence_trap = (set_net_flow_5d_mb > 0) and (tfex_net_contracts_5d < -20000)

    return {
        "set_flow_component": round(s_set, 3),
        "tfex_flow_component": round(s_tfex, 3),
        "nvdr_stock_component": round(s_nvdr, 3),
        "smart_money_score": round(composite, 4),
        "tfex_short_hedge_trap": tfex_divergence_trap,
        "institutional_tailwind": composite >= 0.25 and not tfex_divergence_trap,
    }


print(compute_smart_money_flow_score(8500.0, 35000.0, 0.14))
print(compute_smart_money_flow_score(1200.0, -42000.0, -0.08))


# ==============================================================================

import math
from typing import Any, Dict


def evaluate_systemic_risk_radar(
    macro_stress_zscore: float,
    smart_money_score: float,
    llm_macro_news_risk: float,
    base_max_portfolio_heat: float = 0.06,
) -> Dict[str, Any]:
    """Combine Macro Z-score, Smart Money Flow, and LLM Macro Risk to throttle heat."""
    macro_prob = 1.0 / (1.0 + math.exp(-macro_stress_zscore))
    flow_risk = max(0.0, min(1.0, (1.0 - smart_money_score) / 2.0))
    news_risk = max(0.0, min(1.0, llm_macro_news_risk))

    sri = 0.40 * macro_prob + 0.35 * flow_risk + 0.25 * news_risk

    if sri >= 0.70:
        state, heat_mult, min_cash = "CRITICAL", 0.15, 0.80
    elif sri >= 0.45:
        state, heat_mult, min_cash = "ELEVATED", 0.50, 0.45
    else:
        state, heat_mult, min_cash = "LOW", 1.00, 0.10

    return {
        "systemic_risk_index": round(sri, 4),
        "systemic_state": state,
        "heat_multiplier": heat_mult,
        "allowed_portfolio_heat": round(base_max_portfolio_heat * heat_mult, 4),
        "target_min_cash_pct": min_cash,
    }


print(evaluate_systemic_risk_radar(2.1, -0.82, 0.78))
print(evaluate_systemic_risk_radar(-0.4, 0.65, 0.15))


# ==============================================================================

from typing import Any, Dict


def compute_sector_rotation_quadrants(
    sector_rs_stats: Dict[str, Dict[str, float]],
) -> Dict[str, Dict[str, Any]]:
    """Classify sectors into RRG quadrants using RS-Ratio and RS-Momentum."""
    results: Dict[str, Dict[str, Any]] = {}

    for sector, st in sector_rs_stats.items():
        rs_ratio = 100.0 + 10.0 * st["rs_zscore"]
        rs_mom = 100.0 + 10.0 * st["rs_mom_zscore"]

        if rs_ratio >= 100.0 and rs_mom >= 100.0:
            quad, alloc_mult = "LEADING", 1.25
        elif rs_ratio < 100.0 and rs_mom >= 100.0:
            quad, alloc_mult = "IMPROVING", 1.10
        elif rs_ratio >= 100.0 and rs_mom < 100.0:
            quad, alloc_mult = "WEAKENING", 0.65
        else:
            quad, alloc_mult = "LAGGING", 0.00

        results[sector] = {
            "rs_ratio": round(rs_ratio, 2),
            "rs_momentum": round(rs_mom, 2),
            "quadrant": quad,
            "sector_alloc_multiplier": alloc_mult,
        }

    return results


sample_sectors = {
    "ICT": {"rs_zscore": 1.15, "rs_mom_zscore": 0.85},
    "HEALTH": {"rs_zscore": -0.60, "rs_mom_zscore": 0.95},
    "PETRO": {"rs_zscore": -1.30, "rs_mom_zscore": -0.75},
}
print(compute_sector_rotation_quadrants(sample_sectors))


