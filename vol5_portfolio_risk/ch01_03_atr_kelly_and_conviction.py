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

import math

def compute_safe_kelly_fraction(
    win_rate: float,
    payoff_ratio: float,
    sample_trades: int = 100,
    kelly_multiplier: float = 0.25,
    min_risk_floor: float = 0.0025,
    max_risk_cap: float = 0.0150,
) -> dict[str, float]:
    """คำนวณสัดส่วนความเสี่ยงต่อไม้ด้วย Safe Fractional Kelly พร้อมหักความคลาดเคลื่อน"""
    if not (0.0 < win_rate < 1.0) or payoff_ratio <= 0 or sample_trades < 20:
        return {"raw_kelly": 0.0, "conservative_kelly": 0.0, "safe_risk_pct": 0.0}

    raw_kelly = win_rate - ((1.0 - win_rate) / payoff_ratio)
    win_rate_std_err = math.sqrt((win_rate * (1.0 - win_rate)) / sample_trades)
    conservative_w = max(0.01, win_rate - win_rate_std_err)

    conservative_kelly = conservative_w - ((1.0 - conservative_w) / payoff_ratio)
    if conservative_kelly <= 0:
        return {
            "raw_kelly": round(max(0.0, raw_kelly), 4),
            "conservative_kelly": 0.0,
            "safe_risk_pct": 0.0,
        }

    scaled_kelly = conservative_kelly * kelly_multiplier
    safe_risk_pct = min(max_risk_cap, max(min_risk_floor, scaled_kelly))
    return {
        "raw_kelly": round(raw_kelly, 4),
        "conservative_kelly": round(conservative_kelly, 4),
        "safe_risk_pct": round(safe_risk_pct, 4),
    }


# ==============================================================================

REGIME_MULTIPLIERS: dict[str, float] = {
    "BULL_QUIET": 1.25,
    "BULL_VOLATILE": 1.00,
    "SIDEWAYS": 0.75,
    "BEAR_STRESS": 0.45,
}

def compute_conviction_scaled_size(
    equity: float,
    entry_price: float,
    atr: float,
    conviction_score: float,
    market_regime: str = "BULL_VOLATILE",
    base_risk_pct: float = 0.0080,
    atr_multiplier: float = 2.5,
) -> dict[str, float | int | str]:
    """ปรับขนาดความเสี่ยงและคำนวณจำนวนหุ้นตามคะแนนความมั่นใจและสภาวะตลาด"""
    if conviction_score < 50.0 or market_regime not in REGIME_MULTIPLIERS:
        return {"shares": 0, "effective_risk_pct": 0.0, "status": "REJECTED"}

    clamped_score = min(100.0, max(50.0, conviction_score))
    conv_mult = 0.60 + 0.70 * ((clamped_score - 50.0) / 50.0)
    regime_mult = REGIME_MULTIPLIERS[market_regime]

    raw_risk_pct = base_risk_pct * conv_mult * regime_mult
    effective_risk_pct = min(0.0125, max(0.0035, raw_risk_pct))

    stop_dist = atr * atr_multiplier
    risk_baht = equity * effective_risk_pct
    shares = int((min(risk_baht / stop_dist, (equity * 0.20) / entry_price) // 100) * 100)
    return {
        "shares": shares,
        "effective_risk_pct": round(effective_risk_pct, 4),
        "risk_budget_baht": round(shares * stop_dist, 2),
        "status": "APPROVED" if shares > 0 else "ZERO_LOT",
    }


# ==============================================================================

from dataclasses import dataclass

@dataclass(frozen=True)
class PositionContext:
    symbol: str
    strategy_tag: str
    entry_price: float
    initial_stop_price: float
    atr_at_entry: float
    max_holding_bars: int
    profit_target_r: float | None = None

class PositionContextManager:
    """จัดการและตรวจสอบเงื่อนไขการออกจากสถานะตามบริบทที่บันทึกไว้ตอนเข้าซื้อเท่านั้น"""

    @staticmethod
    def evaluate_context_exit(
        ctx: PositionContext,
        current_close: float,
        bars_held: int,
        ema10_price: float | None = None,
    ) -> dict[str, bool | str | float]:
        r_unit = ctx.entry_price - ctx.initial_stop_price
        current_r = (current_close - ctx.entry_price) / r_unit if r_unit > 0 else 0.0

        if current_close <= ctx.initial_stop_price:
            return {"should_exit": True, "reason": "THESIS_INVALIDATED_STOP", "r_multiple": round(current_r, 2)}

        if ctx.strategy_tag == "MEAN_REVERSION":
            if ema10_price is not None and current_close >= ema10_price:
                return {"should_exit": True, "reason": "MEAN_REVERT_EMA10_TARGET", "r_multiple": round(current_r, 2)}
            if bars_held >= ctx.max_holding_bars:
                return {"should_exit": True, "reason": "MEAN_REVERT_TIME_EXPIRED", "r_multiple": round(current_r, 2)}

        if ctx.profit_target_r is not None and current_r >= ctx.profit_target_r:
            return {"should_exit": True, "reason": "CONTEXT_PROFIT_TARGET_HIT", "r_multiple": round(current_r, 2)}

        return {"should_exit": False, "reason": "HOLD_WITHIN_CONTEXT", "r_multiple": round(current_r, 2)}


