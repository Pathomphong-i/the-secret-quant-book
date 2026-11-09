from __future__ import annotations
# ==============================================================================
# หนังสือ: The Secret Quant: วิเคราะห์หุ้นและสร้างระบบอย่างมีวินัย
# ผู้เขียน: ปฐมพงษ์ พิพัฒน์สุริยวงศ์
# คำเตือน: เนื้อหาและโค้ดในไฟล์นี้จัดทำขึ้นเพื่อการศึกษาและเป็นความคิดเห็นส่วนตัวของผู้เขียนเท่านั้น
#         มิใช่การแนะนำการลงทุน ผู้ลงทุนโปรดศึกษาข้อมูลและความเสี่ยงด้วยตนเอง
# ==============================================================================

"""บทที่ 14 & บทส่งท้าย: ระบบ 5m Intraday VWAP Sniper, ตรวจสุขภาพบอท และพอร์ต 2 ตะกร้า"""

# --- Source: script_13.py ---
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class SystemHealthReport:
    """รายงานผลการตรวจสุขภาพประจำวันของระบบเทรดอัตโนมัติ"""
    current_nav: float
    high_water_mark: float
    current_drawdown_pct: float
    circuit_breaker_zone: str        # 'GREEN_NORMAL', 'YELLOW_HALF_RISK', 'RED_HALT_NEW_ENTRIES'
    risk_multiplier: float           # 1.0 (ปกติ), 0.5 (ลดครึ่งหนึ่ง), 0.0 (หยุดเปิดไม้ใหม่)
    avg_recent_slippage_bps: float   # ค่าเฉลี่ย Slippage ล่าสุด (หน่วยเป็น Basis Points: 100 bps = 1%)
    data_integrity_ok: bool
    recommended_action: str


@dataclass
class TwoBucketAllocationPlan:
    """แผนการจัดสรรเงินและรินกำไรระหว่าง 2 ตะกร้า (AI Bot Engine vs Dividend Fortress)"""
    total_nav: float
    investor_age: int
    target_dividend_bucket_pct: float
    target_ai_bucket_pct: float
    target_dividend_value: float
    target_ai_value: float
    profit_skim_to_dividend_baht: float  # จำนวนเงินกำไรที่สั่งรินจากตะกร้า AI เข้าตะกร้าปันผลรอบนี้
    estimated_monthly_passive_income: float


class SystemHealthAndTwoBucketManager:
    """
    ระบบผู้พิทักษ์พอร์ตระยะยาว (System Health Monitor & Two-Bucket Wealth Engine)
    ทำหน้าที่:
      1. ตรวจสอบสัญญาณชีพจรของบอทและสั่งทำงาน Drawdown Circuit Breaker 3 ระดับ
      2. บริหารโครงสร้างพอร์ต 2 ตะกร้า (ตะกร้าหุ้นปันผล + ตะกร้าบอท Adaptive AI)
      3. คำนวณการรินกำไรสุทธิเมื่อสร้างจุดสูงสุดใหม่ (High-Water Mark Profit Skimming)
      4. ล็อกเพดานสภาพคล่องของตะกร้า AI ไม่ให้ใหญ่เกินกระดานตลาดหุ้น
    """

    def __init__(
        self,
        historical_max_dd_pct: float = 0.12,   # Max Drawdown ปกติจาก Walk-Forward (เช่น 12%)
        max_acceptable_slippage_bps: float = 65.0,  # เพดาน Slippage เฉลี่ยสูงสุดที่ยอมรับได้ (0.65%)
        ai_bucket_liquidity_cap: float = 25_000_000.0,  # เพดานเงินสูงสุดในตะกร้า AI (25 ล้านบาท)
        net_dividend_yield_annual: float = 0.055,       # อัตราปันผลสุทธิคาดหวังของตะกร้าที่ 1 (5.5%/ปี)
    ):
        self.historical_max_dd_pct = max(0.05, historical_max_dd_pct)
        self.max_acceptable_slippage_bps = max_acceptable_slippage_bps
        self.ai_bucket_liquidity_cap = ai_bucket_liquidity_cap
        self.net_dividend_yield_annual = net_dividend_yield_annual

    def check_system_health(
        self,
        nav_history: pd.Series,
        recent_slippage_bps_list: list,
        latest_prices_df: pd.DataFrame,
    ) -> SystemHealthReport:
        """
        ตรวจสุขภาพบอทประจำวันและประเมินสถานะ Drawdown Circuit Breaker
        """
        current_nav = float(nav_history.iloc[-1])
        hwm = float(nav_history.cummax().iloc[-1])
        dd_pct = (hwm - current_nav) / hwm if hwm > 0 else 0.0

        # 1. ตรวจสอบความสมบูรณ์ของข้อมูลราคา (Data Feed Sanity Check)
        data_ok = True
        if latest_prices_df.isnull().any().any() or (latest_prices_df <= 0).any().any():
            data_ok = False
        elif len(latest_prices_df) >= 2:
            daily_jump = latest_prices_df.pct_change().iloc[-1].abs().max()
            if daily_jump > 0.32:  # เกินเพดาน Ceiling/Floor 30% ของตลาดหุ้นไทย (อาจเกิดจากแตกพาร์)
                data_ok = False

        # 2. ตรวจสอบค่าเฉลี่ย Slippage ล่าสุด
        avg_slip_bps = (
            float(np.mean(recent_slippage_bps_list[-20:]))
            if recent_slippage_bps_list else 0.0
        )

        # 3. ประเมินโซน Drawdown Circuit Breaker 3 ระดับ
        yellow_threshold = 1.25 * self.historical_max_dd_pct
        red_threshold = 1.60 * self.historical_max_dd_pct

        if not data_ok:
            zone = "RED_HALT_NEW_ENTRIES"
            risk_mult = 0.0
            msg = "ตรวจพบข้อมูลราคาผิดปกติ (Data Integrity Alert) สั่งระงับการส่งคำสั่งชั่วคราว"
        elif dd_pct >= red_threshold:
            zone = "RED_HALT_NEW_ENTRIES"
            risk_mult = 0.0
            msg = (
                f"Drawdown ปัจจุบัน ({dd_pct*100:.1f}%) เกินเพดาน Red Breaker ({red_threshold*100:.1f}%) "
                f"สั่งหยุดเปิดสถานะซื้อใหม่และถือเงินสดรอการตรวจสอบ"
            )
        elif dd_pct >= yellow_threshold or avg_slip_bps > self.max_acceptable_slippage_bps:
            zone = "YELLOW_HALF_RISK"
            risk_mult = 0.5
            msg = (
                f"เข้าสู่โหมดระมัดระวัง (DD={dd_pct*100:.1f}%, Slippage={avg_slip_bps:.1f} bps) "
                f"ลดขนาดความเสี่ยงต่อไม้ลงเหลือ 50% อัตโนมัติ"
            )
        else:
            zone = "GREEN_NORMAL"
            risk_mult = 1.0
            msg = "สุขภาพระบบปกติสมบูรณ์ เดินเครื่องเต็มกำลัง 100%"

        return SystemHealthReport(
            current_nav=round(current_nav, 2),
            high_water_mark=round(hwm, 2),
            current_drawdown_pct=round(dd_pct * 100.0, 2),
            circuit_breaker_zone=zone,
            risk_multiplier=risk_mult,
            avg_recent_slippage_bps=round(avg_slip_bps, 2),
            data_integrity_ok=data_ok,
            recommended_action=msg,
        )

    def compute_two_bucket_plan(
        self,
        investor_age: int,
        current_dividend_bucket_val: float,
        current_ai_bucket_val: float,
        previous_ai_hwm: float,
        retirement_age: int = 45,
    ) -> TwoBucketAllocationPlan:
        """
        คำนวณสัดส่วนพอร์ต 2 ตะกร้าตามช่วงอายุ และสั่งรินกำไร (Profit Skimming)
        จากตะกร้าบอท AI ไปเติมเข้าตะกร้าหุ้นปันผลโดยอัตโนมัติ
        """
        total_nav = current_dividend_bucket_val + current_ai_bucket_val

        # 1. กำหนดสัดส่วนเป้าหมายตามช่วงอายุและขนาดพอร์ต (Lifecycle Glidepath)
        if investor_age < retirement_age - 2 and total_nav < 3_500_000:
            # ช่วงสร้างตัวเร่งการทบต้น: เน้นตะกร้า AI เต็มกำลัง
            target_div_pct = 0.0
        elif investor_age < retirement_age:
            # ช่วงเตรียมเกษียณ (Pre-Retirement Glidepath): ค่อยๆ ขยับตะกร้าปันผลสู่ 35%-50%
            target_div_pct = 0.35
        elif investor_age < 70:
            # ช่วงวัยเกษียณรับเงินเดือน (Two-Bucket Cashflow Mode)
            target_div_pct = 0.55
        else:
            # ช่วงวัยพิทักษ์มรดกส่งต่อให้ลูก (Legacy Fortress Mode)
            target_div_pct = 0.85

        # 2. คำนวณการรินกำไรสุทธิเมื่อตะกร้า AI ทำจุดสูงสุดใหม่ (Profit Skimming 25%)
        profit_skim = 0.0
        if current_ai_bucket_val > previous_ai_hwm and investor_age >= retirement_age - 3:
            new_profit = current_ai_bucket_val - previous_ai_hwm
            profit_skim = 0.25 * new_profit

        # 3. บังคับเพดานสภาพคล่อง (Liquidity Cap): ถ้าเงินในตะกร้า AI เกิน 25 ล้านบาท
        # ให้ปัดส่วนที่เกินทั้งหมดเข้าตะกร้าหุ้นปันผลทันทีเพื่อไม่ให้เกิด Slippage ในกระดาน
        target_ai_val = total_nav * (1.0 - target_div_pct)
        if target_ai_val > self.ai_bucket_liquidity_cap:
            target_ai_val = self.ai_bucket_liquidity_cap

        target_div_val = total_nav - target_ai_val
        actual_target_div_pct = (target_div_val / total_nav) if total_nav > 0 else 0.0
        actual_target_ai_pct = 1.0 - actual_target_div_pct

        # คำนวณยอดเงินที่ต้องโอนจากตะกร้า AI ไปซื้อหุ้นปันผลเพิ่มในรอบนี้
        rebalance_gap = max(0.0, target_div_val - current_dividend_bucket_val)
        transfer_to_dividend = max(profit_skim, rebalance_gap)
        transfer_to_dividend = min(transfer_to_dividend, current_ai_bucket_val)

        # ประเมินกระแสเงินสดปันผลต่อเดือนจากตะกร้าปันผลหลังปรับสมดุล
        projected_div_bucket = current_dividend_bucket_val + transfer_to_dividend
        monthly_passive_income = (projected_div_bucket * self.net_dividend_yield_annual) / 12.0

        return TwoBucketAllocationPlan(
            total_nav=round(total_nav, 2),
            investor_age=investor_age,
            target_dividend_bucket_pct=round(actual_target_div_pct * 100.0, 1),
            target_ai_bucket_pct=round(actual_target_ai_pct * 100.0, 1),
            target_dividend_value=round(target_div_val, 2),
            target_ai_value=round(target_ai_val, 2),
            profit_skim_to_dividend_baht=round(transfer_to_dividend, 2),
            estimated_monthly_passive_income=round(monthly_passive_income, 2),
        )


if __name__ == "__main__":
    mgr = SystemHealthAndTwoBucketManager()
    nav_s = pd.Series([1_000_000, 1_080_000, 1_150_000, 1_120_000])
    prices_df = pd.DataFrame({"STOCK_A": [25.0, 25.5, 26.0], "STOCK_B": [50.0, 50.5, 51.0]})
    health = mgr.check_system_health(nav_s, [12.0, 15.0, 10.0], prices_df)
    plan = mgr.compute_two_bucket_plan(
        investor_age=45,
        current_dividend_bucket_val=2_000_000.0,
        current_ai_bucket_val=3_500_000.0,
        previous_ai_hwm=3_100_000.0,
    )
    print("=== รายงานตรวจสุขภาพระบบและแผนพอร์ต 2 ตะกร้า (SystemHealthAndTwoBucketManager) ===")
    print("Health:", health)
    print("Two-Bucket Plan:", plan)


