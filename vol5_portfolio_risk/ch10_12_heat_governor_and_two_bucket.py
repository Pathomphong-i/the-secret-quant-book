#!/usr/bin/env python3
"""
The Secret Quant: 8-Volume Masterclass Series
เล่มที่ 5: การบริหารพอร์ตโฟลิโอและวิศวกรรมความเสี่ยง (Portfolio Management & Risk Engineering)
ผู้เขียน: ปฐมพงษ์ พิพัฒน์สุริยวงศ์
รวมซอร์สโค้ดครบทุกบทประจำเล่มที่ 5 พร้อมรันทดสอบได้ทันที
"""

from __future__ import annotations
import json, math, os, sqlite3, hashlib
import numpy as np
import pandas as pd

from dataclasses import dataclass
import math

@dataclass(frozen=True)
class ATRPositionResult:
    shares: int
    stop_price: float
    position_value: float
    actual_baht_risk: float
    actual_pct_risk: float

def compute_atr_position_size(
    equity: float,
    entry_price: float,
    atr: float,
    risk_pct: float = 0.01,
    atr_multiplier: float = 2.5,
    max_alloc_pct: float = 0.20,
    board_lot: int = 100,
) -> ATRPositionResult:
    """คำนวณจำนวนหุ้นตามความผันผวน ATR พร้อมเพดานวงเงินและปัดเศษ Board Lot"""
    if equity <= 0 or entry_price <= 0 or atr <= 0:
        raise ValueError("ข้อมูล Equity, ราคาเข้าซื้อ และ ATR ต้องมากกว่า 0")

    risk_budget_baht = equity * risk_pct
    stop_distance = atr * atr_multiplier
    stop_price = round(max(0.01, entry_price - stop_distance), 2)

    raw_shares_by_risk = risk_budget_baht / stop_distance
    raw_shares_by_cap = (equity * max_alloc_pct) / entry_price
    capped_raw_shares = min(raw_shares_by_risk, raw_shares_by_cap)

    final_shares = int(math.floor(capped_raw_shares / board_lot) * board_lot)
    pos_value = round(final_shares * entry_price, 2)
    actual_risk = round(final_shares * (entry_price - stop_price), 2)
    return ATRPositionResult(
        shares=final_shares,
        stop_price=stop_price,
        position_value=pos_value,
        actual_baht_risk=actual_risk,
        actual_pct_risk=round(actual_risk / equity, 4),
    )


# ==============================================================================

def compute_drawdown_risk_governor(
    current_equity: float,
    peak_equity: float,
    base_risk_pct: float = 0.0100,
    base_max_heat: float = 0.0500,
) -> dict[str, float | str | bool]:
    """คำนวณระดับการย่อตัว (Drawdown) และปรับลดขนาดความเสี่ยงและเพดานความร้อนอัตโนมัติ"""
    if current_equity <= 0 or peak_equity <= 0:
        raise ValueError("มูลค่าพอร์ตต้องมากกว่า 0")

    updated_peak = max(peak_equity, current_equity)
    drawdown_pct = (updated_peak - current_equity) / updated_peak

    if drawdown_pct < 0.05:
        tier, mult, allow_all = "TIER_1_GREEN_NORMAL", 1.00, True
    elif drawdown_pct < 0.10:
        tier, mult, allow_all = "TIER_2_YELLOW_HALF_RISK", 0.50, True
    elif drawdown_pct < 0.15:
        tier, mult, allow_all = "TIER_3A_ORANGE_QUARTER_A_PLUS_ONLY", 0.25, False
    else:
        tier, mult, allow_all = "TIER_3B_RED_CIRCUIT_BREAKER_HALT", 0.00, False

    return {
        "updated_peak_equity": round(updated_peak, 2),
        "drawdown_pct": round(drawdown_pct, 4),
        "governor_tier": tier,
        "risk_multiplier": mult,
        "adjusted_risk_pct": round(base_risk_pct * mult, 4),
        "adjusted_max_heat": round(base_max_heat * mult, 4),
        "allow_standard_signals": allow_all,
    }


# ==============================================================================

def rebalance_two_bucket_wealth_system(
    alpha_bucket_equity: float,
    alpha_hwm: float,
    dividend_vault_equity: float,
    skim_ratio: float = 0.25,
    min_growth_trigger: float = 0.05,
) -> dict[str, float | bool | str]:
    """คำนวณการตักกำไรส่วนเกิน (Profit Skimming) จากพอร์ตบอทเข้าสู่พอร์ตปันผลระยะยาว"""
    if alpha_bucket_equity <= 0 or alpha_hwm <= 0 or dividend_vault_equity < 0:
        raise ValueError("ข้อมูลมูลค่าพอร์ตไม่ถูกต้อง")

    growth_over_hwm = (alpha_bucket_equity - alpha_hwm) / alpha_hwm
    if growth_over_hwm < min_growth_trigger:
        return {
            "skimmed_occurred": False,
            "transfer_to_vault_baht": 0.0,
            "new_alpha_equity": round(alpha_bucket_equity, 2),
            "new_alpha_hwm": round(alpha_hwm, 2),
            "new_vault_equity": round(dividend_vault_equity, 2),
            "total_net_worth": round(alpha_bucket_equity + dividend_vault_equity, 2),
        }

    new_profit = alpha_bucket_equity - alpha_hwm
    transfer_baht = round(new_profit * skim_ratio, 2)
    new_alpha = round(alpha_bucket_equity - transfer_baht, 2)
    new_vault = round(dividend_vault_equity + transfer_baht, 2)
    return {
        "skimmed_occurred": True,
        "transfer_to_vault_baht": transfer_baht,
        "new_alpha_equity": new_alpha,
        "new_alpha_hwm": new_alpha,
        "new_vault_equity": new_vault,
        "total_net_worth": round(new_alpha + new_vault, 2),
    }
