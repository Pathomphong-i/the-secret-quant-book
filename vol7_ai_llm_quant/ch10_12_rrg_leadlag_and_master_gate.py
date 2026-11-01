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

# ==============================================================================
# Snippet 7.11B: Tech Supply Chain Revenue Spillover & Kalman Filter Dynamic Beta
# ==============================================================================
def compute_supply_chain_lead_lag_and_kalman_spread(
    supplier_revenues_12m: dict[str, list[float]],
    adjacency_weights: dict[str, float],
    upstream_prices: np.ndarray,
    downstream_prices: np.ndarray,
    delta_q: float = 1e-4,
    obs_var_r: float = 1e-3,
) -> dict:
    """
    คำนวณสัญญาณอัลฟ่าจากเครือข่ายห่วงโซ่อุปทานเทคโนโลยี (Tech Supply Chain Quant Blueprint):
    1. Cross-Asset Supplier Revenue Momentum Z-Score (Taiwan/Korea Monthly Revenue Spillover)
    2. Kalman Filter Dynamic Beta & Standardized Innovation Z-Score (Ernest Chan Ch. 3)
    """
    weighted_rev_z = 0.0
    total_w = 0.0
    for sup_id, rev_hist in supplier_revenues_12m.items():
        arr = np.asarray(rev_hist, dtype=float)
        w = float(adjacency_weights.get(sup_id, 0.0))
        if len(arr) >= 6 and w > 0:
            ma_12 = float(np.mean(arr))
            sd_12 = float(np.std(arr, ddof=1))
            z_sup = (float(arr[-1]) - ma_12) / sd_12 if sd_12 > 1e-9 else 0.0
            weighted_rev_z += w * z_sup
            total_w += w
    rev_spillover_signal = float(weighted_rev_z / total_w) if total_w > 0 else 0.0

    x_arr = np.log(np.asarray(upstream_prices, dtype=float))
    y_arr = np.log(np.asarray(downstream_prices, dtype=float))
    n = min(len(x_arr), len(y_arr))
    if n < 10:
        return {"rev_spillover_z": round(rev_spillover_signal, 3), "kalman_beta": 1.0, "spread_z": 0.0, "action": "HOLD"}

    beta_state = np.array([0.0, 1.0], dtype=float)
    p_cov = np.eye(2, dtype=float) * 0.1
    q_cov = np.eye(2, dtype=float) * float(delta_q)
    z_score_last = 0.0

    for t in range(n):
        p_pred = p_cov + q_cov
        x_vec = np.array([1.0, x_arr[t]], dtype=float)

        y_pred = float(x_vec @ beta_state)
        err = float(y_arr[t] - y_pred)
        f_var = float(x_vec @ p_pred @ x_vec.T + obs_var_r)
        z_score_last = err / np.sqrt(max(f_var, 1e-12))

        k_gain = (p_pred @ x_vec) / max(f_var, 1e-12)
        beta_state = beta_state + k_gain * err
        p_cov = (np.eye(2) - np.outer(k_gain, x_vec)) @ p_pred

    if abs(z_score_last) > 3.5:
        action = "STRUCTURAL_BREAK_STOP"
    elif z_score_last < -2.0 and rev_spillover_signal > 0.5:
        action = "LONG_LAGGARD_CATCHUP"
    elif z_score_last > 2.0:
        action = "SHORT_OVEREXTENDED_OR_TRIM"
    elif abs(z_score_last) <= 0.25:
        action = "EXIT_MEAN_REVERTED"
    else:
        action = "HOLD"

    return {
        "rev_spillover_z": round(rev_spillover_signal, 3),
        "kalman_alpha": round(float(beta_state[0]), 4),
        "kalman_beta": round(float(beta_state[1]), 4),
        "spread_z": round(float(z_score_last), 3),
        "action": action,
    }
