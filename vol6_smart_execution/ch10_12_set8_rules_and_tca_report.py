#!/usr/bin/env python3
"""
The Secret Quant: 8-Volume Masterclass Series
เล่มที่ 6: โครงสร้างกระดานซื้อขายและอัลกอริทึมส่งคำสั่ง (Smart Execution & Order Book Microstructure)
ผู้เขียน: ปฐมพงษ์ พิพัฒน์สุริยวงศ์
รวมซอร์สโค้ดครบทุกบทประจำเล่มที่ 6 พร้อมรันทดสอบได้ทันที
"""

from __future__ import annotations
import json, math, os, sqlite3, hashlib
import numpy as np
import pandas as pd

from typing import Dict


def compute_total_roundtrip_friction(
    best_bid: float,
    best_ask: float,
    order_shares: int,
    top_book_shares: int,
    tick_size: float,
    comm_rate_one_way: float = 0.0008,  # 0.08% ต่อขา (ก่อน VAT)
    vat_rate: float = 0.07,
) -> Dict[str, float]:
    """คำนวณต้นทุนรวมไป-กลับ (Explicit + Implicit) หน่วยเป็น % และ bps"""
    mid_price = 0.5 * (best_bid + best_ask)
    explicit_rt = 2.0 * comm_rate_one_way * (1.0 + vat_rate)
    spread_pct = (best_ask - best_bid) / mid_price

    # ประเมิน Queue Spillover หากจำนวนหุ้นที่สั่งเกินคิวช่องแรก
    overflow_ratio = max(0.0, (order_shares / max(top_book_shares, 1)) - 1.0)
    extra_ticks_per_leg = 0.5 * overflow_ratio
    slippage_rt = (2.0 * extra_ticks_per_leg * tick_size) / mid_price

    total_friction_pct = (explicit_rt + spread_pct + slippage_rt) * 100.0
    return {
        "mid_price": round(mid_price, 4),
        "explicit_cost_bps": round(explicit_rt * 10000, 2),
        "spread_cost_bps": round(spread_pct * 10000, 2),
        "slippage_cost_bps": round(slippage_rt * 10000, 2),
        "total_friction_pct": round(total_friction_pct, 3),
    }


# ==============================================================================
# Snippet 6.13: Kyle's Lambda, Amihud Illiquidity & VPIN Toxicity (López de Prado AFML Ch. 19)
# ==============================================================================
def compute_kyle_amihud_and_vpin(
    prices: np.ndarray,
    volumes: np.ndarray,
    n_buckets: int = 10,
) -> dict:
    """
    คำนวณตัวชี้วัดโครงสร้างจุลภาคของตลาด (Microstructural Features — López de Prado AFML Ch. 19):
    1. Kyle's Lambda (Price Impact per Unit Signed Order Flow)
    2. Amihud's Illiquidity Ratio (|Return| per Million THB Dollar Volume)
    3. Bulk-Volume VPIN (Volume-Synchronized Probability of Informed Trading)
    """
    from scipy.stats import norm
    p = np.asarray(prices, dtype=float)
    v = np.asarray(volumes, dtype=float)
    if len(p) < 10 or len(p) != len(v) or np.any(p <= 0):
        return {"kyle_lambda": 0.0, "amihud_illiq_per_m": 0.0, "vpin": 0.0, "high_toxicity_alert": False}

    dp = np.diff(p)
    ret = dp / p[:-1]
    vol_sub = np.maximum(v[1:], 1.0)
    dollar_vol_m = (p[1:] * vol_sub) / 1e6

    signs = np.where(dp > 0, 1.0, np.where(dp < 0, -1.0, 0.0))
    for i in range(1, len(signs)):
        if signs[i] == 0.0:
            signs[i] = signs[i - 1] if signs[i - 1] != 0.0 else 1.0
    signed_vol = signs * vol_sub
    denom = float(np.sum(signed_vol ** 2))
    kyle_lambda = float(np.maximum(0.0, np.sum(dp * signed_vol) / denom)) if denom > 0 else 0.0

    amihud_illiq = float(np.mean(np.abs(ret) / np.maximum(dollar_vol_m, 1e-6)))

    sigma_dp = float(np.std(dp, ddof=1)) if len(dp) > 1 else 1e-6
    z_scores = dp / max(sigma_dp, 1e-6)
    buy_frac = norm.cdf(z_scores)
    v_buy = vol_sub * buy_frac
    v_sell = vol_sub * (1.0 - buy_frac)

    k = max(2, min(int(n_buckets), len(vol_sub)))
    chunks_b = np.array_split(v_buy, k)
    chunks_s = np.array_split(v_sell, k)
    chunks_v = np.array_split(vol_sub, k)
    imbalances = [abs(float(np.sum(cb) - np.sum(cs))) / max(float(np.sum(cv)), 1.0) for cb, cs, cv in zip(chunks_b, chunks_s, chunks_v)]
    vpin = float(np.clip(np.mean(imbalances), 0.0, 1.0))

    return {
        "kyle_lambda": round(kyle_lambda, 8),
        "amihud_illiq_per_m": round(amihud_illiq, 6),
        "vpin": round(vpin, 4),
        "high_toxicity_alert": bool(vpin >= 0.65),
    }


if __name__ == "__main__":
    res = compute_total_roundtrip_friction(24.90, 25.00, 30000, 20000, 0.10)
    print(f"Total Round-Trip Friction: {res['total_friction_pct']}% | Detail: {res}")


# ==============================================================================

from typing import Dict


def validate_set_compliance_rules(
    symbol_in_set100: bool,
    order_type: str,  # "BUY", "SELL", หรือ "SHORT_SELL"
    order_price: float,
    last_trade_price: float,
    tick_size: float,
    prev_day_return_pct: float,
    total_order_events: int,
    total_matched_trades: int,
    max_otr_limit: float = 40.0,
) -> Dict[str, object]:
    """ตรวจสอบกฎ SET Compliance: Eligible Short, Dynamic Uptick (-10%) และ OTR Guard"""
    current_otr = total_order_events / max(total_matched_trades, 1)
    if current_otr >= max_otr_limit:
        return {"approved": False, "rule_triggered": "OTR_GUARD_EXCEEDED", "min_valid_price": order_price}

    if order_type.upper() == "SHORT_SELL":
        if not symbol_in_set100:
            return {"approved": False, "rule_triggered": "NOT_IN_ELigible_SET100", "min_valid_price": 0.0}

        # หากวันก่อนหน้าร่วง >= 10% ต้องใช้ Uptick Rule (Last + 1 Tick) มิฉะนั้นใช้ Zero-Plus Tick (Last)
        use_uptick = prev_day_return_pct <= -10.0
        min_short_price = round(last_trade_price + (tick_size if use_uptick else 0.0), 2)
        rule_name = "UPTICK_RULE_ACTIVE" if use_uptick else "ZERO_PLUS_TICK_ACTIVE"

        if order_price < min_short_price - 1e-6:
            return {"approved": False, "rule_triggered": rule_name, "min_valid_price": min_short_price}
        return {"approved": True, "rule_triggered": rule_name, "min_valid_price": min_short_price}

    return {"approved": True, "rule_triggered": "STANDARD_LONG_COMPLIANT", "min_valid_price": order_price}


if __name__ == "__main__":
    res = validate_set_compliance_rules(True, "SHORT_SELL", 25.00, 25.00, 0.10, -11.5, 120, 10)
    print(f"Compliance Check: {res}")


# ==============================================================================

from typing import Dict, List, Tuple


def compute_tca_execution_report(
    side: str,
    arrival_price: float,
    market_vwap: float,
    target_shares: int,
    child_fills: List[Tuple[float, int]],  # [(fill_price, filled_shares), ...]
    explicit_fee_bps: float = 8.56,
) -> Dict[str, object]:
    """คำนวณรายงาน TCA: Implementation Shortfall, VWAP Slippage และ Fill Rate"""
    filled_shares = sum(q for _, q in child_fills)
    if filled_shares == 0:
        return {"fill_rate_pct": 0.0, "status": "ZERO_FILL_MISSED_TRADE"}

    avg_exec_price = sum(p * q for p, q in child_fills) / filled_shares
    direction = 1.0 if side.upper() == "BUY" else -1.0

    arrival_slip_bps = direction * ((avg_exec_price - arrival_price) / arrival_price) * 10000.0
    vwap_slip_bps = direction * ((avg_exec_price - market_vwap) / market_vwap) * 10000.0
    total_is_bps = arrival_slip_bps + explicit_fee_bps
    fill_rate_pct = (filled_shares / max(target_shares, 1)) * 100.0

    tuning_advice = (
        "INCREASE_URGENCY (เพิ่มความไวการเคาะ)"
        if fill_rate_pct < 75.0 or arrival_slip_bps > 35.0
        else "OPTIMAL_EXECUTION (สมดุลดีเยี่ยม)"
    )
    return {
        "avg_exec_price": round(avg_exec_price, 4),
        "fill_rate_pct": round(fill_rate_pct, 2),
        "arrival_slippage_bps": round(arrival_slip_bps, 2),
        "vwap_slippage_bps": round(vwap_slip_bps, 2),
        "total_is_bps": round(total_is_bps, 2),
        "feedback_tuning": tuning_advice,
    }


if __name__ == "__main__":
    fills = [(24.90, 4000), (25.00, 3500), (25.00, 2500)]
    print(compute_tca_execution_report("BUY", 25.00, 25.04, 10000, fills))



# ==============================================================================
# [LAST-MILE BRIDGE] เชื่อมต่อกระดานซื้อขายจริง Settrade Open API (5-Level Bid/Offer)
