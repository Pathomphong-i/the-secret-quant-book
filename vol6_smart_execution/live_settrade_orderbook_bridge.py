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
