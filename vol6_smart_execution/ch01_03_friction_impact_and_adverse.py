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


if __name__ == "__main__":
    res = compute_total_roundtrip_friction(24.90, 25.00, 30000, 20000, 0.10)
    print(f"Total Round-Trip Friction: {res['total_friction_pct']}% | Detail: {res}")


# ==============================================================================

import math
from typing import Dict


def estimate_market_impact_bps(
    order_shares: int,
    adv_shares: int,
    daily_volatility: float,
    y_coeff: float = 0.75,
    max_impact_budget_bps: float = 25.0,
) -> Dict[str, float]:
    """ประเมิน Market Impact (bps) และคำนวณจำนวนหุ้นสูงสุดที่ไม่เกินงบ Slippage"""
    participation_rate = order_shares / max(adv_shares, 1)
    est_impact_bps = (
        y_coeff * daily_volatility * math.sqrt(participation_rate) * 10000.0
    )

    # คำนวณย้อนกลับหาจำนวนหุ้นสูงสุดที่ทำให้ Impact ไม่เกิน max_impact_budget_bps
    max_part_rate = (
        max_impact_budget_bps / (y_coeff * daily_volatility * 10000.0)
    ) ** 2
    raw_max_shares = int(adv_shares * max_part_rate)
    safe_board_lot_shares = (raw_max_shares // 100) * 100

    return {
        "participation_pct": round(participation_rate * 100.0, 3),
        "estimated_impact_bps": round(est_impact_bps, 2),
        "max_safe_shares": safe_board_lot_shares,
        "is_over_budget": float(est_impact_bps > max_impact_budget_bps),
    }


if __name__ == "__main__":
    check = estimate_market_impact_bps(
        order_shares=80000, adv_shares=4000000, daily_volatility=0.022
    )
    print(f"Impact Analysis: {check}")


# ==============================================================================

from typing import Dict


def evaluate_adverse_selection_risk(
    spread_bps: float,
    expected_alpha_bps: float,
    fill_prob_passive: float,
    adverse_drop_bps: float,
) -> Dict[str, object]:
    """เปรียบเทียบต้นทุนคาดหวังระหว่างการวางรับ (Passive) กับการเคาะขวา (Aggressive)"""
    # ต้นทุนคาดหวังหากวางรับ = (โอกาสได้ของ * ขาดทุนโดนทุบใส่) + (โอกาสตกรถ * กำไรที่หลุดมือ)
    passive_adverse_cost = fill_prob_passive * adverse_drop_bps
    passive_missed_alpha_cost = (1.0 - fill_prob_passive) * expected_alpha_bps
    total_passive_cost_bps = passive_adverse_cost + passive_missed_alpha_cost

    # ต้นทุนหากเคาะขวาซื้อทันที = จ่ายครึ่งหรือเต็ม Spread เพื่อการันตีได้ของ 100%
    aggressive_cost_bps = spread_bps

    if adverse_drop_bps > expected_alpha_bps * 0.8 and fill_prob_passive > 0.75:
        action = "HOLD_AND_WAIT (ระวังโดนเทขายใส่คิวรับ)"
    elif total_passive_cost_bps > aggressive_cost_bps:
        action = "CROSS_SPREAD_AGGRESSIVE (ยอมเคาะขวาคุ้มกว่าตกรถ)"
    else:
        action = "JOIN_BEST_BID_PASSIVE (วางรับที่ Best Bid ประหยัดต้นทุน)"

    return {
        "passive_expected_cost_bps": round(total_passive_cost_bps, 2),
        "aggressive_cost_bps": round(aggressive_cost_bps, 2),
        "recommended_action": action,
    }


if __name__ == "__main__":
    decision = evaluate_adverse_selection_risk(
        spread_bps=40.0,
        expected_alpha_bps=120.0,
        fill_prob_passive=0.20,
        adverse_drop_bps=15.0,
    )
    print(f"Execution Mode Decision: {decision}")


# ==============================================================================

import math
from typing import Dict, List


def compute_multilevel_obi(
    bid_volumes: List[int],
    ask_volumes: List[int],
    decay_lambda: float = 0.5,
    expected_levels: int = 5,
) -> Dict[str, object]:
    """คำนวณ Level-1 OBI และ Distance-Weighted Multi-Level OBI พร้อมป้องกันกระดานว่างหรือมีไม่ครบช่อง"""
    clean_bids = [max(0, int(v)) for v in (bid_volumes or [])]
    clean_asks = [max(0, int(v)) for v in (ask_volumes or [])]

    # กรณีกระดานว่างเปล่าข้างใดข้างหนึ่ง (เช่น ชน Ceiling/Floor หรือช่วง Halted)
    if not clean_bids or not clean_asks or (sum(clean_bids) == 0 and sum(clean_asks) == 0):
        return {
            "obi_level1": 0.0,
            "obi_weighted_5level": 0.0,
            "valid_levels_used": 0,
            "is_thin_book_warning": True,
            "book_pressure_state": "EMPTY_OR_LOCKED_BOOK (กระดานว่างหรือชน Ceiling/Floor — ห้ามส่งคำสั่ง)",
        }

    # ปรับจำนวนระดับที่ใช้คำนวณตามจำนวนช่องที่มีข้อมูลจริง (หรือเติม 0 ให้ครบ expected_levels)
    n_levels = max(len(clean_bids), len(clean_asks), expected_levels)
    padded_bids = clean_bids + [0] * (n_levels - len(clean_bids))
    padded_asks = clean_asks + [0] * (n_levels - len(clean_asks))
    weights = [math.exp(-decay_lambda * i) for i in range(n_levels)]

    b1, a1 = padded_bids[0], padded_asks[0]
    obi_l1 = (b1 - a1) / (b1 + a1) if (b1 + a1) > 0 else 0.0

    w_bid = sum(w * v for w, v in zip(weights, padded_bids))
    w_ask = sum(w * v for w, v in zip(weights, padded_asks))
    obi_multi = (w_bid - w_ask) / (w_bid + w_ask) if (w_bid + w_ask) > 0 else 0.0

    valid_levels = min(len(clean_bids), len(clean_asks))
    is_thin_book = valid_levels < expected_levels

    if obi_l1 > 0.35 and obi_multi > 0.25:
        pressure = "STRONG_BUY_PRESSURE (แรงรับหนุนแน่น เตรียมเคาะขวาได้)"
    elif obi_l1 < -0.35 and obi_multi < -0.25:
        pressure = "STRONG_SELL_PRESSURE (แรงขายกดหนัก ชะลอการรับมีด)"
    else:
        pressure = "NEUTRAL_BOOK (กระดานสมดุล เหมาะกับการวางตั้งรับ)"

    return {
        "obi_level1": round(obi_l1, 4),
        "obi_weighted_5level": round(obi_multi, 4),
        "valid_levels_used": valid_levels,
        "is_thin_book_warning": is_thin_book,
        "book_pressure_state": pressure,
    }


if __name__ == "__main__":
    bids = [850000, 600000, 400000, 200000, 150000]
    asks = [120000, 250000, 300000, 900000, 1200000]
    print(compute_multilevel_obi(bids, asks))


