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

import numpy as np
from typing import Any

def evaluate_system_health_metrics(
    live_daily_returns: list[float],
    live_slippage_bps: list[float],
    backtest_sharpe: float = 1.60,
    expected_slippage_bps: float = 18.0,
) -> dict[str, Any]:
    """ประมวลผล Rolling Sharpe Ratio และ Slippage Drift เทียบกับค่ามาตรฐานจาก Backtest"""
    rets = np.asarray(live_daily_returns[-60:], dtype=float)
    slips = np.asarray(live_slippage_bps[-20:], dtype=float)

    std_r = float(np.std(rets, ddof=1)) if len(rets) > 1 else 0.0
    rolling_sharpe = float((np.mean(rets) / std_r) * np.sqrt(252)) if std_r > 1e-9 else 0.0
    sharpe_retention = rolling_sharpe / max(backtest_sharpe, 0.01)

    avg_live_slip = float(np.mean(slips)) if len(slips) > 0 else 0.0
    slippage_drift_bps = avg_live_slip - expected_slippage_bps

    status = "HEALTHY"
    if sharpe_retention < 0.25 or slippage_drift_bps > 15.0:
        status = "CRITICAL_DRIFT_REDUCE_SIZE"
    elif sharpe_retention < 0.60 or slippage_drift_bps > 8.0:
        status = "DEGRADED_WARNING"

    return {
        "health_status": status,
        "rolling_60d_sharpe": round(rolling_sharpe, 2),
        "sharpe_retention_pct": round(sharpe_retention * 100, 1),
        "avg_live_slippage_bps": round(avg_live_slip, 1),
        "slippage_drift_bps": round(slippage_drift_bps, 1),
    }

# ทดสอบตรวจสุขภาพบอทเมื่อพบว่าค่า Slippage จริงเริ่มสูงกว่าที่จำลองไว้ใน Backtest
np.random.seed(42)
sample_rets = list(np.random.normal(0.0005, 0.008, 60))
sample_slips = [28.5, 31.0, 26.5, 29.0, 30.5, 27.0, 29.5, 28.0, 30.0, 29.0]
print(evaluate_system_health_metrics(sample_rets, sample_slips))


# ==============================================================================

from typing import Any

def trigger_three_tier_circuit_breaker(
    intraday_return_pct: float,
    peak_drawdown_pct: float,
    consecutive_api_errors: int,
    data_age_seconds: float,
    open_order_ids: list[str] | None = None,
    manual_kill_active: bool = False,
) -> dict[str, Any]:
    """ประเมินระบบตัดไฟฉุกเฉิน 3 ระดับ พร้อมสั่งยกเลิกออเดอร์ค้างทั้งหมดเมื่อเข้าสู่ระดับ 3"""
    reasons: list[str] = []
    pending_orders = list(open_order_ids or [])
    tier = 0

    # ตรวจสอบเงื่อนไขวิกฤตระดับ 3 (Hard Kill-Switch)
    if manual_kill_active:
        tier = 3; reasons.append("MANUAL_KILL_SWITCH_ENGAGED")
    if intraday_return_pct <= -4.0 or peak_drawdown_pct <= -15.0:
        tier = 3; reasons.append(f"CRITICAL_DRAWDOWN (Day: {intraday_return_pct}%, Peak: {peak_drawdown_pct}%)")
    if consecutive_api_errors >= 5:
        tier = 3; reasons.append(f"RUNAWAY_API_ERRORS ({consecutive_api_errors}x)")

    # ตรวจสอบเงื่อนไขระดับ 2 และ 1 (กรณีไม่ติดระดับ 3)
    if tier < 3 and (intraday_return_pct <= -2.5 or peak_drawdown_pct <= -10.0):
        tier = max(tier, 2); reasons.append("ELEVATED_DRAWDOWN_THROTTLE")
    if tier < 3 and (consecutive_api_errors >= 2 or data_age_seconds > 180.0):
        tier = max(tier, 1); reasons.append(f"TECH_ANOMALY (Err:{consecutive_api_errors}, DataAge:{data_age_seconds}s)")

    config = {
        0: ("NORMAL_OPERATION", 1.0, False, True, "MAINTAIN_ACTIVE_PORTFOLIO"),
        1: ("LEVEL_1_PAUSE_NEW_BUYS", 0.0, False, True, "HOLD_EXISTING_ALLOW_STOP_EXITS"),
        2: ("LEVEL_2_THROTTLE_50PCT", 0.5, False, True, "REDUCE_NEW_SIZING_ALLOW_STOP_EXITS"),
        3: ("LEVEL_3_HARD_KILL_SWITCH", 0.0, True, False, "HOLD_EXISTING_WITH_HARD_STOPS_AND_HALT_NEW_ENTRIES"),
    }[tier]

    cancelled_orders = pending_orders if config[2] else []

    return {
        "tier": tier,
        "mode": config[0],
        "buy_size_multiplier": config[1],
        "cancel_all_open_orders": config[2],
        "cancelled_order_ids": cancelled_orders,
        "allow_Automated_new_orders": config[1] > 0,
        "allow_protective_stop_exits": config[3],
        "portfolio_state_action": config[4],
        "triggers": reasons or ["ALL_SYSTEMS_NOMINAL"],
    }

# ทดสอบสถานการณ์: ขาดทุนระหว่างวัน -2.8% (ระดับ 2) เทียบกับกรณีเกิด API Error รัว 5 ครั้งติดพร้อมออเดอร์ค้าง (ระดับ 3)
print("Case A (Drawdown -2.8%):", trigger_three_tier_circuit_breaker(-2.8, -6.5, 0, 12.0, ["ORD-101"]))
print("Case B (API Error 5x):  ", trigger_three_tier_circuit_breaker(-0.5, -3.0, 5, 10.0, ["ORD-101", "ORD-102"]))


# ==============================================================================

import math
from typing import Any

def compute_safe_tfex_contracts(
    account_equity_thb: float,
    s50_index_price: float,
    initial_margin_per_contract: float = 9800.0,
    max_effective_leverage: float = 2.0,
    multiplier: float = 200.0,
) -> dict[str, Any]:
    """คำนวณจำนวนสัญญา TFEX S50 ที่ปลอดภัยภายใต้เพดาน Effective Leverage และระยะห่าง Margin Call"""
    notional_per_contract = s50_index_price * multiplier
    max_notional_allowed = account_equity_thb * max_effective_leverage
    safe_contracts = int(math.floor(max_notional_allowed / notional_per_contract))

    if safe_contracts <= 0:
        return {"safe_contracts": 0, "status": "INSUFFICIENT_EQUITY_FOR_1_CONTRACT"}

    total_notional = safe_contracts * notional_per_contract
    effective_leverage = total_notional / account_equity_thb
    mm_total = safe_contracts * (initial_margin_per_contract * 0.70)
    excess_equity_above_mm = account_equity_thb - mm_total
    points_to_margin_call = excess_equity_above_mm / (safe_contracts * multiplier)

    return {
        "safe_contracts": safe_contracts,
        "notional_value_thb": round(total_notional, 2),
        "effective_leverage_x": round(effective_leverage, 2),
        "points_buffer_to_mm": round(points_to_margin_call, 1),
        "pct_drop_to_margin_call": round((points_to_margin_call / s50_index_price) * 100, 1),
    }

# ทดสอบคำนวณจำนวนสัญญาสำหรับพอร์ตอนุพันธ์ขนาด 500,000 บาท ที่ดัชนี S50 = 900 จุด
print(compute_safe_tfex_contracts(account_equity_thb=500000.0, s50_index_price=900.0))


