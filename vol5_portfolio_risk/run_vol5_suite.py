#!/usr/bin/env python3
"""
หนังสือ: เลิกพึ่งบอทคนอื่น มาสร้างระบบเทรดของคุณเองด้วย Python
บทที่ 5: การบริหารพอร์ตโฟลิโอและวิศวกรรมความเสี่ยง (Portfolio Management & Risk Engineering)
ผู้เขียน: ปฐมพงษ์ พิพัฒน์สุริยวงศ์
รวมซอร์สโค้ดครบทุกหัวข้อประจำบทที่ 5 พร้อมรันทดสอบได้ทันที
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


# ==============================================================================

import numpy as np

def quasi_diagonalize_clusters(dist_matrix: np.ndarray) -> list[int]:
    """จัดกลุ่มหุ้นตามลำดับชั้น (Hierarchical Clustering) และคืนค่าลำดับหุ้นแบบ Quasi-Diagonal"""
    n = dist_matrix.shape[0]
    clusters: list[list[int]] = [[i] for i in range(n)]

    profile_dist = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            d = float(np.linalg.norm(dist_matrix[:, i] - dist_matrix[:, j]))
            profile_dist[i, j] = profile_dist[j, i] = d

    while len(clusters) > 1:
        best_pair = (0, 1)
        min_d = float("inf")
        for c1 in range(len(clusters)):
            for c2 in range(c1 + 1, len(clusters)):
                sub_d = [profile_dist[idx1, idx2] for idx1 in clusters[c1] for idx2 in clusters[c2]]
                avg_d = sum(sub_d) / len(sub_d)
                if avg_d < min_d:
                    min_d = avg_d
                    best_pair = (c1, c2)

        idx_a, idx_b = best_pair
        merged_cluster = clusters[idx_a] + clusters[idx_b]
        clusters[idx_a] = merged_cluster
        clusters.pop(idx_b)

    return clusters[0]


# ==============================================================================

import numpy as np

def _cluster_variance(cov_matrix: np.ndarray, cluster_indices: list[int]) -> float:
    """คำนวณความแปรปรวนรวมของกลุ่มย่อยด้วยน้ำหนัก Inverse-Variance"""
    sub_cov = cov_matrix[np.ix_(cluster_indices, cluster_indices)]
    inv_diag = 1.0 / np.maximum(np.diag(sub_cov), 1e-8)
    local_weights = inv_diag / np.sum(inv_diag)
    return float(local_weights @ sub_cov @ local_weights)

def hrp_recursive_bisection(
    cov_matrix: np.ndarray,
    sorted_indices: list[int],
) -> np.ndarray:
    """แบ่งงบประมาณน้ำหนักพอร์ตจากบนลงล่างด้วยอัลกอริทึม HRP Recursive Bisection"""
    n = cov_matrix.shape[0]
    weights = np.ones(n, dtype=float)
    active_clusters: list[list[int]] = [sorted_indices]

    while len(active_clusters) > 0:
        next_clusters: list[list[int]] = []
        for cluster in active_clusters:
            if len(cluster) > 1:
                mid = len(cluster) // 2
                left_c, right_c = cluster[:mid], cluster[mid:]
                next_clusters.extend([left_c, right_c])

                v_left = _cluster_variance(cov_matrix, left_c)
                v_right = _cluster_variance(cov_matrix, right_c)
                alpha_left = 1.0 - (v_left / (v_left + v_right))

                weights[left_c] *= alpha_left
                weights[right_c] *= (1.0 - alpha_left)
        active_clusters = next_clusters

    return np.round(weights / np.sum(weights), 4)


# ==============================================================================

from typing import Any

def check_portfolio_heat_and_sector_cap(
    equity: float,
    open_positions: list[dict[str, Any]],
    candidate_trade: dict[str, Any],
    max_total_heat: float = 0.050,
    max_sector_heat: float = 0.020,
    max_sector_alloc: float = 0.300,
) -> dict[str, bool | float | str]:
    """ตรวจสอบเพดานความร้อนพอร์ตรวม (<= 5%) และความเข้มข้นรายกลุ่มอุตสาหกรรมก่อนเปิดไม้ใหม่"""
    current_heat_baht = 0.0
    sector_heat_baht = 0.0
    sector_value_baht = 0.0
    cand_sector = candidate_trade["sector"]

    for pos in open_positions:
        open_risk = max(0.0, pos["shares"] * (pos["entry_price"] - pos["current_stop"]))
        pos_val = pos["shares"] * pos["current_price"]
        current_heat_baht += open_risk
        if pos["sector"] == cand_sector:
            sector_heat_baht += open_risk
            sector_value_baht += pos_val

    cand_risk = max(0.0, candidate_trade["shares"] * (candidate_trade["entry_price"] - candidate_trade["stop_price"]))
    cand_val = candidate_trade["shares"] * candidate_trade["entry_price"]

    proj_total_heat = (current_heat_baht + cand_risk) / equity
    proj_sector_heat = (sector_heat_baht + cand_risk) / equity
    proj_sector_alloc = (sector_value_baht + cand_val) / equity

    if proj_total_heat > max_total_heat:
        return {"approved": False, "reason": "PORTFOLIO_HEAT_CAP_EXCEEDED", "projected_heat": round(proj_total_heat, 4)}
    if proj_sector_heat > max_sector_heat or proj_sector_alloc > max_sector_alloc:
        return {"approved": False, "reason": "SECTOR_CONCENTRATION_EXCEEDED", "projected_heat": round(proj_total_heat, 4)}

    return {"approved": True, "reason": "APPROVED_WITHIN_HEAT_LIMITS", "projected_heat": round(proj_total_heat, 4)}


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
