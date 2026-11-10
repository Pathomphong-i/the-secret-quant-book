#!/usr/bin/env python3
"""
หนังสือ: เลิกพึ่งบอทคนอื่น มาสร้างระบบเทรดของคุณเองด้วย Python
บทที่ 7: AI, LLM & ข้อมูลทางเลือกวิเคราะห์ข่าวและงบการเงิน (Multi-Modal AI & LLM Quant)
ผู้เขียน: ปฐมพงษ์ พิพัฒน์สุริยวงศ์
รวมซอร์สโค้ดครบทุกบทประจำบทที่ 7 พร้อมรันทดสอบได้ทันที
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
