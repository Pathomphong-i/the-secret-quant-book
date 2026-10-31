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


