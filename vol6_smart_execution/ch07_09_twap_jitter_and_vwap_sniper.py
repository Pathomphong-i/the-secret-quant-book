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


