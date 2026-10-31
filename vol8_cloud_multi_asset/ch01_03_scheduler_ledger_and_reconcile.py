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
order_key = ledger.make_key("2026-10-15", "4PILLAR", "ADVANC", "BUY", slice_idx=1)
print("Attempt 1:", ledger.register_or_block(order_key, "ADVANC", "BUY", 1000))
print("Attempt 2:", ledger.register_or_block(order_key, "ADVANC", "BUY", 1000))


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

# ทดสอบกระทบยอดพอร์ตตอนเช้า (กรณีพบหุ้น BDMS ไม่ตรงกัน 1,000 หุ้น)
res = reconcile_positions_with_broker(
    local_positions={"ADVANC": 1500, "SCB": 2000, "BDMS": 3000},
    broker_positions={"ADVANC": 1500, "SCB": 2000, "BDMS": 2000},
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
msg1 = send_quant_telemetry_alert("CRITICAL", "RECON_FAIL", "Broker Mismatch", {"Symbol": "BDMS", "Diff": -1000}, now_ts=1000.0)
msg2 = send_quant_telemetry_alert("CRITICAL", "RECON_FAIL", "Broker Mismatch", {"Symbol": "BDMS", "Diff": -1000}, now_ts=1015.0)
print("Send 1:", msg1["sent"], "| Preview:", msg1["message"].replace("\n", " | "))
print("Send 2 (15s later):", msg2)


