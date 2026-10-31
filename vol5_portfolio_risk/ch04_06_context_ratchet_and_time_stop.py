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

def update_ratchet_trailing_stop(
    entry_price: float,
    initial_stop: float,
    prev_stop: float,
    highest_close: float,
    current_close: float,
    current_atr: float,
    normal_mult: float = 3.0,
    parabolic_mult: float = 2.0,
) -> dict[str, float | bool | str]:
    """คำนวณและอัปเดตจุดล็อกกำไรแบบเฟืองทางเดียว (Chandelier + Breakeven + Parabolic)"""
    r_unit = entry_price - initial_stop
    if r_unit <= 0:
        raise ValueError("initial_stop ต้องต่ำกว่า entry_price เสมอ")

    highest_close = max(highest_close, current_close)
    max_r_reached = (highest_close - entry_price) / r_unit

    active_mult = parabolic_mult if max_r_reached >= 3.5 else normal_mult
    chandelier_stop = highest_close - (active_mult * current_atr)

    breakeven_floor = (entry_price + 0.15 * r_unit) if max_r_reached >= 1.5 else initial_stop
    new_stop = round(max(prev_stop, chandelier_stop, breakeven_floor), 2)
    triggered = current_close <= new_stop
    return {
        "new_stop": new_stop,
        "highest_close": round(highest_close, 2),
        "max_r_reached": round(max_r_reached, 2),
        "stop_triggered": triggered,
        "mode": "PARABOLIC" if max_r_reached >= 3.5 else ("BREAKEVEN_LOCKED" if max_r_reached >= 1.5 else "INITIAL"),
    }


# ==============================================================================

import math

def evaluate_time_and_partial_exit(
    current_shares: int,
    entry_price: float,
    initial_stop: float,
    current_close: float,
    bars_held: int,
    partial_taken: bool = False,
    time_stop_bars: int = 10,
    min_progress_r: float = 0.50,
    partial_target_r: float = 2.00,
    board_lot: int = 100,
) -> dict[str, int | float | bool | str]:
    """ประเมินการตัดออกตามเวลา (Time Stop) และการแบ่งขายทำกำไร 1/3 ที่ +2R"""
    r_unit = entry_price - initial_stop
    current_r = (current_close - entry_price) / r_unit if r_unit > 0 else 0.0

    if not partial_taken and bars_held >= time_stop_bars and current_r < min_progress_r:
        return {
            "action": "EXIT_ALL_TIME_STOP",
            "shares_to_sell": current_shares,
            "remaining_shares": 0,
            "partial_taken": partial_taken,
            "current_r": round(current_r, 2),
        }

    if not partial_taken and current_r >= partial_target_r and current_shares >= board_lot * 2:
        raw_sell = current_shares / 3.0
        shares_to_sell = max(board_lot, int(math.floor(raw_sell / board_lot) * board_lot))
        remaining = current_shares - shares_to_sell
        return {
            "action": "PARTIAL_PROFIT_SCALE_OUT",
            "shares_to_sell": shares_to_sell,
            "remaining_shares": remaining,
            "partial_taken": True,
            "current_r": round(current_r, 2),
        }

    return {
        "action": "HOLD_CORE_POSITION",
        "shares_to_sell": 0,
        "remaining_shares": current_shares,
        "partial_taken": partial_taken,
        "current_r": round(current_r, 2),
    }


# ==============================================================================

import numpy as np

def compute_correlation_distance_matrix(
    returns_matrix: np.ndarray,
) -> dict[str, np.ndarray | float]:
    """คำนวณเมทริกซ์สหสัมพันธ์ (Correlation) และเมทริกซ์ระยะห่าง (Distance Matrix d_ij)"""
    if returns_matrix.ndim != 2 or returns_matrix.shape[0] < 10:
        raise ValueError("returns_matrix ต้องเป็นตาราง 2 มิติ (จำนวนวัน x จำนวนหุ้น) อย่างน้อย 10 วัน")

    corr_matrix = np.corrcoef(returns_matrix, rowvar=False)
    corr_matrix = np.clip(corr_matrix, -1.0, 1.0)
    np.fill_diagonal(corr_matrix, 1.0)

    dist_matrix = np.sqrt(0.5 * (1.0 - corr_matrix))
    np.fill_diagonal(dist_matrix, 0.0)

    n_assets = corr_matrix.shape[0]
    off_diag_mask = ~np.eye(n_assets, dtype=bool)
    avg_corr = float(np.mean(corr_matrix[off_diag_mask]))
    return {
        "corr_matrix": np.round(corr_matrix, 4),
        "dist_matrix": np.round(dist_matrix, 4),
        "avg_pairwise_corr": round(avg_corr, 4),
    }


