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

from typing import Any, Dict


def analyze_mda_tone_and_red_flags(
    llm_mda_extract: Dict[str, Any],
) -> Dict[str, Any]:
    """Compute composite MD&A forensic risk score from LLM semantic extraction."""
    f_debt = max(0.0, min(1.0, float(llm_mda_extract.get("debt_covenant_risk", 0.0))))
    f_oneoff = max(0.0, min(1.0, float(llm_mda_extract.get("one_off_gain_reliance", 0.0))))
    f_evasive = max(0.0, min(1.0, float(llm_mda_extract.get("evasive_language_score", 0.0))))
    tone_drop = max(0.0, min(1.0, float(llm_mda_extract.get("qoq_negative_tone_shift", 0.0))))
    going_concern_flag = bool(llm_mda_extract.get("going_concern_warning", False))

    composite_risk = (
        0.35 * f_debt
        + 0.30 * f_oneoff
        + 0.20 * f_evasive
        + 0.15 * tone_drop
    )
    if going_concern_flag:
        composite_risk = 1.0

    return {
        "mda_red_flag_score": round(composite_risk, 4),
        "going_concern_warning": going_concern_flag,
        "risk_level": "CRITICAL" if composite_risk >= 0.50 else ("WARNING" if composite_risk >= 0.30 else "CLEAN"),
        "pass_mda_audit": composite_risk < 0.45,
    }


sample_mda = {
    "debt_covenant_risk": 0.80,
    "one_off_gain_reliance": 0.65,
    "evasive_language_score": 0.50,
    "qoq_negative_tone_shift": 0.40,
    "going_concern_warning": False,
}
print(analyze_mda_tone_and_red_flags(sample_mda))


# ==============================================================================

from typing import Any, Dict


def run_fundamental_hygiene_gate(
    ticker: str,
    de_ratio: float,
    interest_coverage: float,
    sloan_accrual_ratio: float,
    mda_red_flag_score: float,
) -> Dict[str, Any]:
    """Filter out financially distressed or accounting-red-flag stocks."""
    checks = {
        "solvency_de_ok": de_ratio <= 2.50,
        "interest_cov_ok": interest_coverage >= 2.50,
        "cash_accrual_ok": sloan_accrual_ratio <= 0.08,
        "llm_mda_clean": mda_red_flag_score < 0.45,
    }
    failed_reasons = [name for name, passed in checks.items() if not passed]
    approved = len(failed_reasons) == 0

    return {
        "ticker": ticker,
        "approved_for_trading": approved,
        "failed_checks": failed_reasons,
        "position_size_cap_mult": 1.0 if approved else 0.0,
    }


print(run_fundamental_hygiene_gate("STOCK_ALPHA", 0.85, 8.4, -0.03, 0.12))
print(run_fundamental_hygiene_gate("STOCK_COVENANT", 2.10, 2.8, 0.05, 0.78))


# ==============================================================================

from typing import Any, Dict


def compute_cross_asset_stress_zscore(
    yield_change_bps: float,
    spread_change_bps: float,
    fx_depreciation_pct: float,
    norms: Dict[str, tuple[float, float]] | None = None,
) -> Dict[str, Any]:
    """Compute cross-asset macro stress Z-score from Bond, Credit, and FX."""
    default_norms = {
        "yield": (0.0, 12.0),   # (mean_bps, std_bps) over 20d
        "spread": (0.0, 15.0),  # (mean_bps, std_bps) over 20d
        "fx": (0.0, 1.2),       # (mean_pct, std_pct) over 20d
    }
    cfg = norms or default_norms

    z_yield = (yield_change_bps - cfg["yield"][0]) / cfg["yield"][1]
    z_spread = (spread_change_bps - cfg["spread"][0]) / cfg["spread"][1]
    z_fx = (fx_depreciation_pct - cfg["fx"][0]) / cfg["fx"][1]

    composite_z = 0.35 * z_yield + 0.40 * z_spread + 0.25 * z_fx
    if composite_z >= 1.50:
        state = "HIGH_MACRO_STRESS"
    elif composite_z >= 0.80:
        state = "MODERATE_CAUTION"
    else:
        state = "CALM_SUPPORTIVE"

    return {
        "z_bond_yield": round(z_yield, 2),
        "z_credit_spread": round(z_spread, 2),
        "z_fx_usdthb": round(z_fx, 2),
        "macro_stress_zscore": round(composite_z, 3),
        "macro_regime": state,
    }


print(compute_cross_asset_stress_zscore(24.0, 33.0, 2.4))


