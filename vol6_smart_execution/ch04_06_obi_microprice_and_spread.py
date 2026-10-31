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


