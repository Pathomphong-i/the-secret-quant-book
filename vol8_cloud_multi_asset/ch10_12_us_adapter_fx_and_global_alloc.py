#!/usr/bin/env python3
"""
The Secret Quant: 8-Volume Masterclass Series
เล่มที่ 8: การวางระบบ Cloud Production 24/7 และการขยายสู่ TFEX / หุ้นนอก (Cloud Ops & Multi-Asset)
ผู้เขียน: ปฐมพงษ์ พิพัฒน์สุริยวงศ์
รวมซอร์สโค้ดครบทุกบทประจำเล่มที่ 8 พร้อมรันทดสอบได้ทันที
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

def compute_fx_adjusted_portfolio_risk(
    r_usd_pct: float,
    r_fx_pct: float,
    vol_usd_pct: float,
    vol_fx_pct: float,
    corr_usd_fx: float = -0.25,
    usdthb_zscore: float = 0.0,
) -> dict[str, Any]:
    """คำนวณผลตอบแทนและความผันผวนในรูปเงินบาท (THB) พร้อมแนะนำสัดส่วน FX Hedge"""
    r_u, r_f = r_usd_pct / 100.0, r_fx_pct / 100.0
    r_thb_pct = ((1.0 + r_u) * (1.0 + r_f) - 1.0) * 100.0

    var_thb = (vol_usd_pct ** 2) + (vol_fx_pct ** 2) + (2.0 * corr_usd_fx * vol_usd_pct * vol_fx_pct)
    vol_thb_pct = float(np.sqrt(max(var_thb, 0.0)))

    # แนะนำเฮดจ์ค่าเงินเฉพาะเมื่อ USD/THB แพงผิดปกติ (Z-score > 1.5) เพื่อล็อกเรตเงินบาทอ่อน
    fx_hedge_ratio = 0.50 if usdthb_zscore >= 1.5 else (0.25 if usdthb_zscore >= 0.8 else 0.00)

    return {
        "return_usd_pct": round(r_usd_pct, 2),
        "return_fx_pct": round(r_fx_pct, 2),
        "net_return_thb_pct": round(r_thb_pct, 2),
        "volatility_usd_pct": round(vol_usd_pct, 2),
        "volatility_thb_pct": round(vol_thb_pct, 2),
        "recommended_fx_hedge_ratio": fx_hedge_ratio,
    }

# ทดสอบกรณีวิกฤตที่ความสัมพันธ์ระหว่างหุ้นสหรัฐฯ กับ USD/THB เป็นลบ (-0.25) และดอลลาร์แพงมาก (Z=1.8)
print(compute_fx_adjusted_portfolio_risk(r_usd_pct=12.0, r_fx_pct=-2.0, vol_usd_pct=16.0, vol_fx_pct=6.5, corr_usd_fx=-0.25, usdthb_zscore=1.8))


# ==============================================================================

from typing import Any

def allocate_global_multi_asset_portfolio(
    total_capital_thb: float,
    market_regime: str,
    asset_vols_pct: dict[str, float],
) -> dict[str, Any]:
    """จัดสรรเงินทุนพอร์ต Global Multi-Asset อัตโนมัติด้วย Inverse-Vol + Regime Tilt"""
    regime_tilts = {
        "LOW_VOL_BULL": {"TH_EQUITY": 2.2, "US_EQUITY": 2.5, "GOLD_GLD": 0.8, "CASH_TBILLS": 0.2},
        "SIDEWAYS_CAUTION": {"TH_EQUITY": 1.2, "US_EQUITY": 1.2, "GOLD_GLD": 1.4, "CASH_TBILLS": 0.6},
        "HIGH_VOL_CRISIS": {"TH_EQUITY": 0.5, "US_EQUITY": 0.4, "GOLD_GLD": 1.8, "CASH_TBILLS": 1.5},
    }[market_regime]

    raw_scores: dict[str, float] = {}
    for asset, tilt in regime_tilts.items():
        vol = max(asset_vols_pct.get(asset, 15.0), 2.0)  # ป้องกันตัวหารใกล้ศูนย์สำหรับ Cash
        raw_scores[asset] = (1.0 / vol) * tilt

    total_score = sum(raw_scores.values())
    weights = {k: round((v / total_score) * 100.0, 1) for k, v in raw_scores.items()}
    alloc_thb = {k: round((v / total_score) * total_capital_thb, 0) for k, v in raw_scores.items()}
    tfex_hedge_pct = {"LOW_VOL_BULL": 0, "SIDEWAYS_CAUTION": 50, "HIGH_VOL_CRISIS": 100}[market_regime]

    return {
        "regime": market_regime,
        "weights_pct": weights,
        "allocation_thb": alloc_thb,
        "tfex_short_hedge_pct_of_th_equity": tfex_hedge_pct,
    }

# ทดสอบจัดสรรพอร์ตโกลบอล 5 ล้านบาท เปรียบเทียบระหว่างยามตลาดสดใส (BULL) กับยามวิกฤต (CRISIS)
vols = {"TH_EQUITY": 14.0, "US_EQUITY": 16.0, "GOLD_GLD": 13.0, "CASH_TBILLS": 4.0}
print("BULL  :", allocate_global_multi_asset_portfolio(5_000_000, "LOW_VOL_BULL", vols)["weights_pct"])
print("CRISIS:", allocate_global_multi_asset_portfolio(5_000_000, "HIGH_VOL_CRISIS", vols)["weights_pct"])


# ==============================================================================

from typing import Any

def run_daily_cloud_production_cycle(
    total_capital_thb: float,
    local_pos: dict[str, int],
    broker_pos: dict[str, int],
    intraday_ret_pct: float,
    market_regime: str,
    s50_price: float,
) -> dict[str, Any]:
    """รันวงจรการทำงานประจำวันของบอท Cloud Production ครบตั้งแต่ Reconcile จนถึง Global & TFEX Hedge"""
    # 1. ตรวจสอบยอดหุ้นตรงกับโบรกเกอร์ก่อนเริ่มวัน
    mismatches = {k: broker_pos.get(k, 0) - local_pos.get(k, 0) for k in set(local_pos) | set(broker_pos) if local_pos.get(k, 0) != broker_pos.get(k, 0)}
    if mismatches:
        return {"status": "HALT_RECONCILE_MISMATCH", "mismatches": mismatches}

    # 2. ตรวจสอบเบรกเกอร์ฉุกเฉิน (Circuit Breaker)
    if intraday_ret_pct <= -4.0:
        return {"status": "LEVEL_3_KILL_SWITCH_ENGAGED", "cancel_all": True}
    size_mult = 0.50 if intraday_ret_pct <= -2.5 else 1.00

    # 3. คำนวณสัดส่วนพอร์ตโกลบอลและสัญญา Short TFEX Hedge
    th_weight = {"LOW_VOL_BULL": 0.35, "SIDEWAYS_CAUTION": 0.25, "HIGH_VOL_CRISIS": 0.15}[market_regime]
    hedge_ratio = {"LOW_VOL_BULL": 0.00, "SIDEWAYS_CAUTION": 0.50, "HIGH_VOL_CRISIS": 1.00}[market_regime]
    th_equity_val = total_capital_thb * th_weight * size_mult
    short_s50_contracts = int(round((th_equity_val * hedge_ratio) / (s50_price * 200.0)))

    return {
        "status": "EXECUTION_READY", "regime": market_regime,
        "buy_multiplier": size_mult, "th_equity_budget_thb": round(th_equity_val, 0),
        "target_short_s50_contracts": short_s50_contracts,
    }

# ทดสอบรันวงจรหลักสำหรับพอร์ต 5 ล้านบาทในสภาวะเฝ้าระวัง (SIDEWAYS_CAUTION)
print(run_daily_cloud_production_cycle(5_000_000, {"ALPHA": 2000}, {"ALPHA": 2000}, -1.2, "SIDEWAYS_CAUTION", 900.0))
