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

import hashlib
import sqlite3

class IdempotentOrderLedger:
    """สมุดบัญชี SQLite WAL ป้องกันการส่งคำสั่งซื้อขายซ้ำซ้อนเมื่อระบบรีสตาร์ต"""
    def __init__(self, db_path: str = ":memory:"):
        self.conn = sqlite3.connect(db_path)
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("""
            CREATE TABLE IF NOT EXISTS order_ledger (
                client_order_id TEXT PRIMARY KEY,
                symbol TEXT, side TEXT, qty INTEGER,
                status TEXT, broker_order_id TEXT
            )
        """)

    @staticmethod
    def make_key(trade_date: str, strategy: str, symbol: str, side: str, slice_idx: int) -> str:
        raw = f"{trade_date}|{strategy}|{symbol}|{side}|{slice_idx}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]

    def register_or_block(self, key: str, symbol: str, side: str, qty: int) -> tuple[bool, str]:
        row = self.conn.execute(
            "SELECT status FROM order_ledger WHERE client_order_id = ?", (key,)
        ).fetchone()
        if row is not None:
            return False, f"BLOCKED_DUPLICATE (Existing status: {row[0]})"
        with self.conn:
            self.conn.execute(
                "INSERT INTO order_ledger VALUES (?, ?, ?, ?, 'PENDING_SEND', NULL)",
                (key, symbol, side, qty),
            )
        return True, "REGISTERED_READY_TO_SEND"

# ทดสอบการป้องกันคำสั่งซ้ำซ้อนเมื่อบอทพยายามส่งไม้เดิมซ้ำ
ledger = IdempotentOrderLedger()
order_key = ledger.make_key("2026-10-15", "4PILLAR", "BETA", "BUY", slice_idx=1)
print("Attempt 1:", ledger.register_or_block(order_key, "BETA", "BUY", 1000))
print("Attempt 2:", ledger.register_or_block(order_key, "BETA", "BUY", 1000))


# ==============================================================================

from typing import Any

def reconcile_positions_with_broker(
    local_positions: dict[str, int],
    broker_positions: dict[str, int],
    local_cash: float,
    broker_cash: float,
    cash_tolerance: float = 50.0,
) -> dict[str, Any]:
    """ตรวจสอบความตรงกันของจำนวนหุ้นและเงินสดระหว่างฐานข้อมูลบอทกับโบรกเกอร์จริง"""
    all_symbols = sorted(set(local_positions.keys()) | set(broker_positions.keys()))
    position_mismatches: dict[str, dict[str, int]] = {}

    for sym in all_symbols:
        q_local = local_positions.get(sym, 0)
        q_broker = broker_positions.get(sym, 0)
        if q_local != q_broker:
            position_mismatches[sym] = {
                "local": q_local, "broker": q_broker, "diff": q_broker - q_local
            }

    cash_diff = abs(local_cash - broker_cash)
    cash_ok = cash_diff <= cash_tolerance
    is_clean = (len(position_mismatches) == 0) and cash_ok

    return {
        "status": "READY_TO_TRADE" if is_clean else "HALT_RECONCILIATION_MISMATCH",
        "allow_execution": is_clean,
        "cash_diff_thb": round(cash_diff, 2),
        "position_mismatches": position_mismatches,
    }

# ทดสอบกระทบยอดพอร์ตตอนเช้า (กรณีพบหุ้น THETA ไม่ตรงกัน 1,000 หุ้น)
res = reconcile_positions_with_broker(
    local_positions={"BETA": 1500, "KAPPA": 2000, "THETA": 3000},
    broker_positions={"BETA": 1500, "KAPPA": 2000, "THETA": 2000},
    local_cash=125000.0, broker_cash=125012.45,
)
print(f"Status: {res['status']} | Allow Trade: {res['allow_execution']}")
print(f"Mismatches: {res['position_mismatches']}")


# ==============================================================================

import time
from typing import Any

_ALERT_COOLDOWN_STATE: dict[str, float] = {}

def send_quant_telemetry_alert(
    severity: str,
    event_key: str,
    title: str,
    metrics: dict[str, Any],
    now_ts: float | None = None,
) -> dict[str, Any]:
    """ส่งข้อความแจ้งเตือนสถานะบอทเข้ามือถือพร้อมกลไก Rate-Limit ป้องกันการสแปม"""
    cooldown_map = {"INFO": 300.0, "WARNING": 180.0, "CRITICAL": 60.0}
    now = now_ts if now_ts is not None else time.time()
    cd = cooldown_map.get(severity, 180.0)
    last_ts = _ALERT_COOLDOWN_STATE.get(event_key, -1e9)

    if (now - last_ts) < cd:
        return {"sent": False, "reason": f"RATE_LIMITED (Wait {cd - (now - last_ts):.0f}s)"}

    icon = {"INFO": "[OK]", "WARNING": "[WARN]", "CRITICAL": "[ALERT]"}.get(severity, "[LOG]")
    lines = [f"{icon} *{severity}: {title}*"]
    for k, v in metrics.items():
        lines.append(f"• {k}: `{v}`")
    payload_text = "\n".join(lines)

    _ALERT_COOLDOWN_STATE[event_key] = now
    return {"sent": True, "silent": (severity == "INFO"), "message": payload_text}

# ทดสอบส่งแจ้งเตือนพอร์ตตอนเช้า และทดสอบระบบป้องกันการส่งข้อความซ้ำรัวๆ
msg1 = send_quant_telemetry_alert("CRITICAL", "RECON_FAIL", "Broker Mismatch", {"Symbol": "THETA", "Diff": -1000}, now_ts=1000.0)
msg2 = send_quant_telemetry_alert("CRITICAL", "RECON_FAIL", "Broker Mismatch", {"Symbol": "THETA", "Diff": -1000}, now_ts=1015.0)
print("Send 1:", msg1["sent"], "| Preview:", msg1["message"].replace("\n", " | "))
print("Send 2 (15s later):", msg2)


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
