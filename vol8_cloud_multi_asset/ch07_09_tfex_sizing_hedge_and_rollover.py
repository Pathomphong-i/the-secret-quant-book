#!/usr/bin/env python3
"""
หนังสือ: เลิกพึ่งบอทคนอื่น มาสร้างระบบเทรดของคุณเองด้วย Python
บทที่ 8: การวางระบบ Cloud Production 24/7 และการขยายสู่ TFEX / หุ้นนอก (Cloud Ops & Multi-Asset)
ผู้เขียน: ปฐมพงษ์ พิพัฒน์สุริยวงศ์
รวมซอร์สโค้ดครบทุกหัวข้อประจำบทที่ 8 พร้อมรันทดสอบได้ทันที
"""

from __future__ import annotations
import json, math, os, sqlite3, hashlib
import numpy as np
import pandas as pd

import os
from datetime import datetime, time
from zoneinfo import ZoneInfo

class ProductionMarketScheduler:
    """ระบบจัดการตารางเวลาทำงานอัตโนมัติตามเขตเวลาตลาดหลักทรัพย์ (Asia/Bangkok)"""
    def __init__(self, holidays: set[str] | None = None):
        self.tz = ZoneInfo("Asia/Bangkok")
        self.holidays = holidays or set()
        self.required_env = ["BROKER_API_KEY", "BROKER_SECRET", "TELEGRAM_TOKEN"]

    def validate_environment(self) -> tuple[bool, list[str]]:
        missing = [k for k in self.required_env if not os.getenv(k)]
        return (len(missing) == 0), missing

    def get_current_phase(self, now_dt: datetime | None = None) -> str:
        now = (now_dt or datetime.now(self.tz)).astimezone(self.tz)
        date_str = now.strftime("%Y-%m-%d")
        if now.weekday() >= 5 or date_str in self.holidays:
            return "MARKET_HOLIDAY_SLEEP"

        t = now.time()
        if time(9, 15) <= t < time(9, 55):
            return "PRE_MARKET_RECONCILE"
        if time(10, 15) <= t <= time(12, 30) or time(14, 30) <= t <= time(16, 25):
            return "INTRADAY_EXECUTION_ACTIVE"
        if time(17, 15) <= t <= time(17, 45):
            return "POST_MARKET_REPORTING"
        return "STANDBY_HEARTBEAT"

# ตัวอย่างการทดสอบตารางเวลาทำงานของบอท
os.environ.update({"BROKER_API_KEY": "k1", "BROKER_SECRET": "s1", "TELEGRAM_TOKEN": "t1"})
scheduler = ProductionMarketScheduler(holidays={"2026-04-13", "2026-04-14"})
test_time = datetime(2026, 4, 15, 10, 30, tzinfo=ZoneInfo("Asia/Bangkok"))
print(f"Env Ready: {scheduler.validate_environment()[0]} | Phase: {scheduler.get_current_phase(test_time)}")


# ==============================================================================

from typing import Any

def compute_dynamic_beta_hedge(
    equity_portfolio_value: float,
    portfolio_beta: float,
    s50_index_price: float,
    market_regime: str,
    current_short_contracts: int = 0,
) -> dict[str, Any]:
    """คำนวณจำนวนสัญญา Short S50 Futures อัตโนมัติเพื่อป้องกันความเสี่ยงขาลงตามเรจีมตลาด"""
    hedge_ratio_map = {
        "LOW_VOL_BULL": 0.00,
        "SIDEWAYS_CAUTION": 0.50,
        "HIGH_VOL_CRISIS": 1.00,
    }
    target_hedge_ratio = hedge_ratio_map.get(market_regime, 0.50)
    contract_notional = s50_index_price * 200.0
    beta_adjusted_exposure = equity_portfolio_value * portfolio_beta

    raw_contracts = (target_hedge_ratio * beta_adjusted_exposure) / contract_notional
    target_short_contracts = int(round(raw_contracts))
    delta_contracts = target_short_contracts - current_short_contracts

    action = "HOLD_HEDGE"
    if delta_contracts > 0:
        action = f"OPEN_SHORT_{delta_contracts}_CONTRACTS"
    elif delta_contracts < 0:
        action = f"CLOSE_SHORT_{abs(delta_contracts)}_CONTRACTS"

    return {
        "regime": market_regime, "target_hedge_ratio": target_hedge_ratio,
        "target_short_contracts": target_short_contracts,
        "order_action": action,
        "net_effective_beta": round(portfolio_beta * (1.0 - target_hedge_ratio), 2),
    }

# ทดสอบคำนวณ Hedge สำหรับพอร์ตหุ้น 2 ล้านบาท (Beta 1.08) เมื่อเข้าสู่โหมด HIGH_VOL_CRISIS
print(compute_dynamic_beta_hedge(2_000_000.0, 1.08, 900.0, "HIGH_VOL_CRISIS", current_short_contracts=0))


# ==============================================================================

from typing import Any

def plan_tfex_series_rollover(
    current_symbol: str,
    position_side: str,
    contracts_held: int,
    days_to_expiry: int,
    spot_set50: float,
    price_near: float,
    price_far: float,
) -> dict[str, Any]:
    """วางแผนการสลับซีรีส์สัญญา TFEX S50 อัตโนมัติก่อนวันหมดอายุและคำนวณค่า Basis"""
    next_code_map = {"H": "M", "M": "U", "U": "Z", "Z": "H"}
    series_char = current_symbol[3]
    year_num = int(current_symbol[4:6])
    next_char = next_code_map[series_char]
    next_year = (year_num + 1) if series_char == "Z" else year_num
    next_symbol = f"S50{next_char}{next_year:02d}"

    basis_points = price_near - spot_set50
    roll_spread_points = price_far - price_near
    should_roll = (contracts_held > 0) and (days_to_expiry <= 5)

    close_side = "BUY_TO_CLOSE" if position_side == "SHORT" else "SELL_TO_CLOSE"
    open_side = "SELL_TO_OPEN" if position_side == "SHORT" else "BUY_TO_OPEN"

    return {
        "rollover_triggered": should_roll,
        "current_series": current_symbol, "next_series": next_symbol,
        "basis_pts": round(basis_points, 2), "roll_spread_pts": round(roll_spread_points, 2),
        "leg1_order": f"{close_side} {contracts_held} {current_symbol}" if should_roll else "NONE",
        "leg2_order": f"{open_side} {contracts_held} {next_symbol}" if should_roll else "NONE",
    }

# ทดสอบกรณีถือ Short S50Z26 จำนวน 12 สัญญา และเหลือเวลาอีก 4 วันก่อนหมดอายุสิ้นปี
print(plan_tfex_series_rollover("S50Z26", "SHORT", 12, days_to_expiry=4, spot_set50=905.0, price_near=904.2, price_far=899.5))


# ==============================================================================

import math
from datetime import datetime, time
from zoneinfo import ZoneInfo
from typing import Any

def adapt_order_for_us_market(
    symbol: str,
    target_budget_usd: float,
    current_price_usd: float,
    allow_fractional: bool = False,
    utc_now: datetime | None = None,
) -> dict[str, Any]:
    """ปรับจูนขนาดออเดอร์ ราคา Limit และตรวจสอบเวลาเปิดตลาดปกติของสหรัฐฯ (NYSE/NASDAQ)"""
    ny_tz = ZoneInfo("America/New_York")
    ny_time = (utc_now or datetime.now(ZoneInfo("UTC"))).astimezone(ny_tz)
    is_regular_hours = (ny_time.weekday() < 5) and (time(9, 30) <= ny_time.time() <= time(16, 0))

    raw_shares = target_budget_usd / max(current_price_usd, 0.01)
    qty = round(raw_shares, 4) if allow_fractional else float(math.floor(raw_shares))
    limit_price = round(current_price_usd * 1.001, 2)  # เผื่อ marketable limit +10 bps ปัดระดับ $0.01

    return {
        "symbol": symbol,
        "ny_local_time": ny_time.strftime("%Y-%m-%d %H:%M %Z"),
        "is_regular_session": is_regular_hours,
        "order_qty": qty,
        "limit_price_usd": limit_price,
        "notional_usd": round(qty * current_price_usd, 2),
    }

# ทดสอบสั่งซื้อ ETF ดัชนี S&P 500 (SPY) ด้วยงบ $2,500 ที่ราคา $585.40 ต่อหุ้น
test_utc = datetime(2026, 7, 15, 14, 30, tzinfo=ZoneInfo("UTC"))  # 10:30 EDT
print("Whole Share:", adapt_order_for_us_market("SPY", 2500.0, 585.40, allow_fractional=False, utc_now=test_utc))
print("Fractional :", adapt_order_for_us_market("SPY", 2500.0, 585.40, allow_fractional=True, utc_now=test_utc))


