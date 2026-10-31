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
) -> Dict[str, object]:
    """คำนวณ Level-1 OBI และ Distance-Weighted 5-Level OBI"""
    weights = [math.exp(-decay_lambda * i) for i in range(len(bid_volumes))]

    # Level-1 OBI (เฉพาะช่องหน้าสุด)
    b1, a1 = bid_volumes[0], ask_volumes[0]
    obi_l1 = (b1 - a1) / max(b1 + a1, 1)

    # Multi-Level Weighted OBI (ถ่วงน้ำหนัก 5 ช่อง)
    w_bid = sum(w * v for w, v in zip(weights, bid_volumes))
    w_ask = sum(w * v for w, v in zip(weights, ask_volumes))
    obi_multi = (w_bid - w_ask) / max(w_bid + w_ask, 1e-9)

    if obi_l1 > 0.35 and obi_multi > 0.25:
        pressure = "STRONG_BUY_PRESSURE (แรงรับหนุนแน่น เตรียมเคาะขวาได้)"
    elif obi_l1 < -0.35 and obi_multi < -0.25:
        pressure = "STRONG_SELL_PRESSURE (แรงขายกดหนัก ชะลอการรับมีด)"
    else:
        pressure = "NEUTRAL_BOOK (กระดานสมดุล เหมาะกับการวางตั้งรับ)"

    return {
        "obi_level1": round(obi_l1, 4),
        "obi_weighted_5level": round(obi_multi, 4),
        "book_pressure_state": pressure,
    }


if __name__ == "__main__":
    bids = [850000, 600000, 400000, 200000, 150000]
    asks = [120000, 250000, 300000, 900000, 1200000]
    print(compute_multilevel_obi(bids, asks))


# ==============================================================================

from typing import Dict


def compute_micro_price_and_urgency(
    best_bid: float,
    best_ask: float,
    bid_vol: int,
    ask_vol: int,
    side: str = "BUY",
) -> Dict[str, object]:
    """คำนวณ Micro-Price และตัดสินใจว่าควรวางรับ (Passive) หรือเคาะข้ามช่อง (Aggressive)"""
    mid_price = 0.5 * (best_bid + best_ask)
    spread = max(best_ask - best_bid, 1e-9)
    total_vol = max(bid_vol + ask_vol, 1)

    micro_price = (bid_vol * best_ask + ask_vol * best_bid) / total_vol
    # วัดว่า Micro-Price เอียงไปทางฝั่งไหนคิดเป็นสัดส่วนของ Spread (-0.5 ถึง +0.5)
    micro_shift_ratio = (micro_price - mid_price) / spread

    if side.upper() == "BUY":
        if micro_shift_ratio >= 0.25:
            order_instruction = f"AGGRESSIVE_LIMIT @ {best_ask:.2f} (เคาะขวา)"
        elif micro_shift_ratio <= -0.25:
            order_instruction = f"PASSIVE_HOLD @ {best_bid:.2f} (รอรับหรือถอย 1 ช่อง)"
        else:
            order_instruction = f"PASSIVE_LIMIT @ {best_bid:.2f} (วางรับช่องแรก)"
    else:
        if micro_shift_ratio <= -0.25:
            order_instruction = f"AGGRESSIVE_LIMIT @ {best_bid:.2f} (โยนซ้ายทันที)"
        else:
            order_instruction = f"PASSIVE_LIMIT @ {best_ask:.2f} (วางตั้งขายช่องแรก)"

    return {
        "mid_price": round(mid_price, 4),
        "micro_price": round(micro_price, 4),
        "micro_shift_pct_of_spread": round(micro_shift_ratio * 100.0, 1),
        "order_instruction": order_instruction,
    }


if __name__ == "__main__":
    print(compute_micro_price_and_urgency(25.00, 25.10, 900000, 100000, side="BUY"))


# ==============================================================================

from typing import Dict


def execution_safety_gate(
    current_time_hhmm: str,
    best_bid: float,
    best_ask: float,
    tick_size: float,
    top_book_shares: int,
    desired_order_shares: int,
    max_spread_ticks: int = 2,
    depth_cap_ratio: float = 0.25,
) -> Dict[str, object]:
    """ด่านตรวจความปลอดภัยก่อนส่งคำสั่ง: เวลาเปิดตลาด, Spread Guard และ Depth Cap"""
    spread_ticks = round((best_ask - best_bid) / max(tick_size, 1e-6))

    # 1. ตรวจสอบช่วงเวลาผันผวนสูง 15 นาทีแรกหลังเปิดตลาดเช้า (10:00 - 10:14)
    if "10:00" <= current_time_hhmm < "10:15":
        return {
            "status": "BLOCKED_OPENING_COOLDOWN",
            "approved_shares": 0,
            "reason": "อยู่ในช่วง 10:00-10:15 น. กระดานยังผันผวนและ Spread กว้าง",
        }

    # 2. ตรวจสอบความกว้างของ Bid-Ask Spread (Spread Guard)
    if spread_ticks > max_spread_ticks:
        return {
            "status": "BLOCKED_WIDE_SPREAD",
            "approved_shares": 0,
            "reason": f"ช่องราคาห่างกัน {spread_ticks} Ticks เกินเพดาน {max_spread_ticks} Ticks",
        }

    # 3. จำกัดขนาดไม้ไม่ให้เกินสัดส่วน Depth Cap ของช่องแรก และปัดเป็น Board Lot (100 หุ้น)
    max_allowed_raw = int(top_book_shares * depth_cap_ratio)
    capped_shares = min(desired_order_shares, max_allowed_raw)
    approved_board_lot = (capped_shares // 100) * 100

    return {
        "status": "APPROVED" if approved_board_lot >= 100 else "BLOCKED_THIN_DEPTH",
        "spread_ticks": spread_ticks,
        "approved_shares": approved_board_lot,
        "reason": "ผ่านเกณฑ์ความปลอดภัยพร้อมส่งคำสั่ง",
    }


if __name__ == "__main__":
    gate = execution_safety_gate("10:35", 25.00, 25.10, 0.10, 40000, 15000)
    print(f"Safety Gate Result: {gate}")


# ==============================================================================

import random
from typing import Dict, List


def generate_twap_jitter_schedule(
    total_shares: int,
    duration_seconds: int,
    num_slices: int,
    time_jitter_pct: float = 0.20,
    size_jitter_pct: float = 0.25,
    seed: int = 42,
) -> List[Dict[str, float]]:
    """สร้างตารางทยอยส่งคำสั่ง TWAP พร้อมสุ่มพรางเวลาและขนาดไม้ (Board Lot 100)"""
    rng = random.Random(seed)
    base_interval = duration_seconds / num_slices
    base_shares = total_shares / num_slices
    schedule: List[Dict[str, float]] = []
    allocated_shares = 0

    for i in range(1, num_slices + 1):
        # สุ่มเลื่อนเวลา +- time_jitter_pct ของช่วงเวลาต่อไม้
        t_offset = rng.uniform(-time_jitter_pct, time_jitter_pct) * base_interval
        exec_time_sec = max(1.0, round(i * base_interval + t_offset, 1))

        if i < num_slices:
            raw_q = base_shares * (1.0 + rng.uniform(-size_jitter_pct, size_jitter_pct))
            slice_shares = max(100, int(round(raw_q / 100.0)) * 100)
            slice_shares = min(slice_shares, total_shares - allocated_shares - 100 * (num_slices - i))
            allocated_shares += slice_shares
        else:
            # ไม้สุดท้ายเก็บเศษที่เหลือทั้งหมดให้ครบ total_shares พอดี
            slice_shares = total_shares - allocated_shares

        schedule.append({"slice_no": i, "exec_sec": exec_time_sec, "shares": slice_shares})
    return schedule


if __name__ == "__main__":
    plan = generate_twap_jitter_schedule(10000, duration_seconds=300, num_slices=5)
    for row in plan:
        print(row)


# ==============================================================================

from typing import Dict, List


def generate_volume_profile_vwap_slices(
    total_shares: int,
    bucket_weights: Dict[str, float],
) -> List[Dict[str, object]]:
    """คำนวณขนาดไม้ย่อยตามสัดส่วน Intraday Volume Smile ของตลาดหุ้นไทย"""
    weight_sum = sum(bucket_weights.values())
    normalized = {k: v / weight_sum for k, v in bucket_weights.items()}

    slices: List[Dict[str, object]] = []
    allocated = 0
    buckets = list(normalized.items())

    for idx, (time_window, w) in enumerate(buckets):
        if idx < len(buckets) - 1:
            raw_shares = total_shares * w
            lot_shares = int(round(raw_shares / 100.0)) * 100
            lot_shares = max(0, min(lot_shares, total_shares - allocated))
            allocated += lot_shares
        else:
            lot_shares = total_shares - allocated

        slices.append({
            "time_window": time_window,
            "volume_weight_pct": round(w * 100.0, 2),
            "target_shares": lot_shares,
        })
    return slices


if __name__ == "__main__":
    set_profile = {
        "10:00-10:30": 0.18, "10:30-11:00": 0.11, "11:00-11:30": 0.08,
        "11:30-12:30": 0.09, "14:30-15:00": 0.09, "15:00-15:30": 0.10,
        "15:30-16:00": 0.13, "16:00-16:30": 0.15, "16:30-ATC": 0.07,
    }
    for s in generate_volume_profile_vwap_slices(100000, set_profile):
        print(s)


# ==============================================================================

from typing import Dict, List, Tuple


def intraday_vwap_sniper_step(
    bars_5m: List[Tuple[float, float, float, int]],  # [(high, low, close, volume), ...]
    current_bid: float,
    current_ask: float,
    obi_5level: float,
    base_slice_shares: int,
) -> Dict[str, object]:
    """คำนวณ Real-Time Intraday VWAP จากแท่ง 5 นาที และตัดสินใจจังหวะยิงคำสั่งซื้อ"""
    cum_pv = sum(((h + l + c) / 3.0) * v for h, l, c, v in bars_5m)
    cum_vol = sum(v for _, _, _, v in bars_5m)
    intraday_vwap = cum_pv / max(cum_vol, 1)

    mid_price = 0.5 * (current_bid + current_ask)
    vwap_diff_bps = ((mid_price - intraday_vwap) / intraday_vwap) * 10000.0

    # เงื่อนไข Sniper: ราคาถูกกว่าหรือเท่ากับ VWAP และแรงซื้อในกระดานเป็นบวก
    if vwap_diff_bps <= 5.0 and obi_5level > 0.15:
        mode = f"SNIPER_AGGRESSIVE_BUY @ {current_ask:.2f}"
        multiplier = 1.5
    elif vwap_diff_bps > 50.0 and obi_5level < 0.0:
        mode = f"PATIENT_DELAY_PASSIVE @ {current_bid:.2f}"
        multiplier = 0.5
    else:
        mode = f"STANDARD_PASSIVE_BID @ {current_bid:.2f}"
        multiplier = 1.0

    exec_shares = (int(base_slice_shares * multiplier) // 100) * 100
    return {
        "intraday_vwap": round(intraday_vwap, 4),
        "price_vs_vwap_bps": round(vwap_diff_bps, 2),
        "execution_mode": mode,
        "slice_shares": max(100, exec_shares),
    }


if __name__ == "__main__":
    sample_bars = [(25.2, 24.9, 25.0, 500000), (25.3, 25.0, 25.1, 400000), (25.1, 24.8, 24.9, 300000)]
    print(intraday_vwap_sniper_step(sample_bars, 24.90, 25.00, obi_5level=0.32, base_slice_shares=10000))


# ==============================================================================

import math
from decimal import Decimal
from typing import Dict


def get_set_tick_size(price: float, use_fine_5_to_50_table: bool = True) -> Decimal:
    """คืนค่าขนาดช่องราคา (Tick Size) ของตลาดหุ้นไทยตามระดับราคา"""
    if price < 2.0:
        return Decimal("0.01")
    if price < 5.0:
        return Decimal("0.02")
    if price < 10.0:
        return Decimal("0.02") if use_fine_5_to_50_table else Decimal("0.05")
    if price < 25.0:
        return Decimal("0.05") if use_fine_5_to_50_table else Decimal("0.10")
    if price < 50.0:
        return Decimal("0.10") if use_fine_5_to_50_table else Decimal("0.25")
    if price < 100.0:
        return Decimal("0.25")
    if price < 200.0:
        return Decimal("0.50")
    if price < 400.0:
        return Decimal("1.00")
    return Decimal("2.00")


def round_to_set_tick_and_board_lot(
    raw_price: float, raw_shares: int, side: str = "BUY"
) -> Dict[str, object]:
    """ปัดราคาให้ตรงช่อง Tick Size (BUY ปัดลง, SELL ปัดขึ้น) และปัดจำนวนหุ้นเป็น Board Lot 100"""
    tick = get_set_tick_size(raw_price)
    d_price = Decimal(str(raw_price))
    steps = math.floor(d_price / tick) if side.upper() == "BUY" else math.ceil(d_price / tick)
    valid_price = float(Decimal(steps) * tick)
    board_lot_shares = (max(0, int(raw_shares)) // 100) * 100
    return {"valid_price": round(valid_price, 2), "tick_size": float(tick), "board_lot_shares": board_lot_shares}


if __name__ == "__main__":
    print(round_to_set_tick_and_board_lot(25.14, 12580, side="BUY"))


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
# ==============================================================================
def parse_settrade_bid_offer_snapshot(msg: dict) -> tuple[float, float, list[int], list[int]]:
    """
    แปลงข้อมูล Bid-Offer 5 ช่องราคาจาก Settrade Open API (REST / MQTT Realtime)
    ให้เป็น (best_bid, best_ask, bid_vols_5, ask_vols_5) พร้อมส่งเข้า
    compute_multilevel_obi() และ compute_micro_price_and_urgency() ในเล่มที่ 6 ได้ทันที
    """
    best_bid = float(msg.get("bid_price_1", msg.get("bid1", 0.0)) or 0.0)
    best_ask = float(msg.get("ask_price_1", msg.get("offer1", 0.0)) or 0.0)
    bid_vols = [int(msg.get(f"bid_volume_{i}", msg.get(f"bid_vol{i}", 0)) or 0) for i in range(1, 6)]
    ask_vols = [int(msg.get(f"ask_volume_{i}", msg.get(f"offer_vol{i}", 0)) or 0) for i in range(1, 6)]
    return best_bid, best_ask, bid_vols, ask_vols

if __name__ == "__main__":
    sample_settrade_msg = {
        "symbol": "ADVANC",
        "bid_price_1": 218.0, "bid_volume_1": 85_000,
        "bid_price_2": 217.0, "bid_volume_2": 62_000,
        "bid_price_3": 216.0, "bid_volume_3": 54_000,
        "bid_price_4": 215.0, "bid_volume_4": 48_000,
        "bid_price_5": 214.0, "bid_volume_5": 40_000,
        "ask_price_1": 219.0, "ask_volume_1": 22_000,
        "ask_price_2": 220.0, "ask_volume_2": 31_000,
        "ask_price_3": 221.0, "ask_volume_3": 28_000,
        "ask_price_4": 222.0, "ask_volume_4": 35_000,
        "ask_price_5": 223.0, "ask_volume_5": 45_000,
    }
    b_p, a_p, b_vols, a_vols = parse_settrade_bid_offer_snapshot(sample_settrade_msg)
    print("[Settrade Bridge] OBI 5-Level:", compute_multilevel_obi(b_vols, a_vols))
    print("[Settrade Bridge] Micro-Price:", compute_micro_price_and_urgency(b_p, a_p, b_vols[0], a_vols[0]))
