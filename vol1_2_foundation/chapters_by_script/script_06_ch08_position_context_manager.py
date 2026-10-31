import pandas as pd
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple


class StrategyType(Enum):
    MOMENTUM_BREAKOUT = "MOMENTUM_BREAKOUT"
    TREND_PULLBACK = "TREND_PULLBACK"
    MEAN_REVERSION_DIP = "MEAN_REVERSION_DIP"


class InvalidationRule(Enum):
    CLOSE_BELOW_BREAKOUT_LEVEL = "CLOSE_BELOW_BREAKOUT_LEVEL"
    CLOSE_BELOW_STRUCTURE_EMA = "CLOSE_BELOW_STRUCTURE_EMA"
    UNDERCUT_REVERSAL_LOW = "UNDERCUT_REVERSAL_LOW"


@dataclass
class PositionContext:
    """
    ป้ายกำกับบริบทของออเดอร์ (Immutable Thesis Contract)
    บันทึกเหตุผลการเข้าซื้อและเงื่อนไขการออกที่ห้ามละเมิดเด็ดขาด
    """
    position_id: str
    symbol: str
    strategy_id: StrategyType
    entry_reason: str
    entry_timestamp: pd.Timestamp
    entry_price: float
    shares: float
    entry_atr: float
    initial_stop_loss: float
    invalidation_rule: InvalidationRule
    invalidation_reference_price: float     # เช่น ราคากรอบแนวต้านที่เบรกขึ้นมา หรือ Low ของแท่งกลับตัว
    time_stop_bars: int                     # จำนวนแท่งสูงสุดที่อนุญาตให้ถือหากราคาไม่วิ่งตามคาด
    min_expected_atr_gain: float = 0.75     # กำไรขั้นต่ำ (เท่าของ ATR) ที่ต้องทำได้ก่อนครบ time_stop
    regime_at_entry: str = "BULL_QUIET"

    # สถานะที่อัปเดตระหว่างถือครอง (State Tracking)
    bars_held: int = 0
    highest_price_since_entry: float = field(init=False)
    active_stop_loss: float = field(init=False)

    def __post_init__(self):
        self.highest_price_since_entry = self.entry_price
        self.active_stop_loss = self.initial_stop_loss
        if self.initial_stop_loss >= self.entry_price:
            raise ValueError("สำหรับสถานะ Long ค่า initial_stop_loss ต้องต่ำกว่า entry_price เสมอ")

    def ratchet_stop_loss(self, candidate_new_stop: float) -> None:
        """
        กฎเหล็ก Ratchet-Only: อนุญาตให้ขยับจุดตัดขาดทุน 'ขึ้น' เพื่อล็อกความเสี่ยง/กำไรเท่านั้น
        ห้ามขยับจุดตัดขาดทุน 'ลง' เพื่อหนีตายเด็ดขาด!
        """
        if candidate_new_stop > self.active_stop_loss:
            self.active_stop_loss = round(candidate_new_stop, 4)


@dataclass
class ExitDecision:
    should_exit: bool
    exit_type: str
    exit_reason_detail: str
    suggested_execution_price: float


class PositionContextManager:
    """
    เอนจินควบคุมวินัยการออกของบอทที่ออกแบบมาดี:
    'เข้าด้วยเหตุผลอะไร ต้องตรวจสอบและออกด้วยเหตุผลนั้น'
    """

    def __init__(self):
        self.open_positions: Dict[str, PositionContext] = {}
        self.closed_audit_log: List[Dict] = []

    def register_entry(self, ctx: PositionContext) -> None:
        if ctx.position_id in self.open_positions:
            raise KeyError(f"Position ID {ctx.position_id} มีอยู่ในระบบแล้ว")
        self.open_positions[ctx.position_id] = ctx

    def evaluate_bar_for_position(
        self,
        position_id: str,
        bar_timestamp: pd.Timestamp,
        open_p: float,
        high_p: float,
        low_p: float,
        close_p: float,
        current_atr: float,
        sma_20: float,
        ema_50: float,
        current_market_regime: str
    ) -> ExitDecision:
        """
        ตรวจสอบเงื่อนไขการออกของแต่ละไม้ ณ สิ้นแท่งเทียน โดยอ้างอิงจาก PositionContext เดิมตอนเข้าซื้อ
        """
        ctx = self.open_positions[position_id]
        ctx.bars_held += 1
        if high_p > ctx.highest_price_since_entry:
            ctx.highest_price_since_entry = high_p

        # -----------------------------------------------------------------
        # ลำดับที่ 1: ตรวจสอบ Hard / Ratcheted Stop Loss (การปกป้องเงินต้นสูงสุด)
        # -----------------------------------------------------------------
        if open_p <= ctx.active_stop_loss:
            return self._trigger_exit(
                ctx, bar_timestamp, "GAP_BELOW_STOP_LOSS",
                f"ราคาเปิด ({open_p:.2f}) กระโดดหลุด Stop Loss ({ctx.active_stop_loss:.2f}) [เหตุผลเข้า: {ctx.entry_reason}]",
                open_p
            )
        if low_p <= ctx.active_stop_loss:
            return self._trigger_exit(
                ctx, bar_timestamp, "HARD_OR_TRAILING_STOP",
                f"ราคาต่ำสุดของแท่ง ({low_p:.2f}) ชนจุด Stop Loss ({ctx.active_stop_loss:.2f}) [เหตุผลเข้า: {ctx.entry_reason}]",
                ctx.active_stop_loss
            )

        # -----------------------------------------------------------------
        # ลำดับที่ 2: ตรวจสอบ Thesis Invalidation Rule (สมมติฐานการเข้าซื้อพังทลาย)
        # -----------------------------------------------------------------
        if ctx.invalidation_rule == InvalidationRule.CLOSE_BELOW_BREAKOUT_LEVEL:
            # เข้าเพราะ Breakout แต่ราคาปิดตบกลับลงมาต่ำกว่ากรอบที่เบรกขึ้นไป -> False Breakout!
            if close_p < ctx.invalidation_reference_price:
                return self._trigger_exit(
                    ctx, bar_timestamp, "THESIS_INVALIDATED_FALSE_BREAKOUT",
                    f"เข้าเพราะ {ctx.entry_reason} แต่ราคาปิด ({close_p:.2f}) หลุดกลับลงใต้ระดับ Breakout ({ctx.invalidation_reference_price:.2f})",
                    close_p
                )

        elif ctx.invalidation_rule == InvalidationRule.CLOSE_BELOW_STRUCTURE_EMA:
            if close_p < ema_50:
                return self._trigger_exit(
                    ctx, bar_timestamp, "THESIS_INVALIDATED_TREND_BROKEN",
                    f"เข้าเพราะ {ctx.entry_reason} แต่ราคาปิด ({close_p:.2f}) หลุดเส้นโครงสร้าง EMA50 ({ema_50:.2f})",
                    close_p
                )

        elif ctx.invalidation_rule == InvalidationRule.UNDERCUT_REVERSAL_LOW:
            if close_p < ctx.invalidation_reference_price:
                return self._trigger_exit(
                    ctx, bar_timestamp, "THESIS_INVALIDATED_DIP_FAILED",
                    f"เข้าช้อนเพราะ {ctx.entry_reason} แต่ราคาหลุดฐานกลับตัว ({ctx.invalidation_reference_price:.2f}) ห้ามเปลี่ยนเป็นถือยาวเด็ดขาด!",
                    close_p
                )

        # -----------------------------------------------------------------
        # ลำดับที่ 3: ตรวจสอบ Time Stop (เวลาหมดอายุของสมมติฐาน / Dead Money)
        # -----------------------------------------------------------------
        unrealized_gain = close_p - ctx.entry_price
        required_gain = ctx.min_expected_atr_gain * ctx.entry_atr
        if ctx.bars_held >= ctx.time_stop_bars and unrealized_gain < required_gain:
            return self._trigger_exit(
                ctx, bar_timestamp, "TIME_STOP_EXPIRED",
                f"ถือครบ {ctx.bars_held} แท่งตามโควตาของ {ctx.strategy_id.value} แต่กำไร ({unrealized_gain:.2f}) ไม่ถึงเกณฑ์ขั้นต่ำ ({required_gain:.2f})",
                close_p
            )

        # -----------------------------------------------------------------
        # ลำดับที่ 4: ตรวจสอบกฎการทำกำไรและการขยับ Trailing Stop ตามกลยุทธ์ที่เข้า
        # -----------------------------------------------------------------
        if ctx.strategy_id == StrategyType.MEAN_REVERSION_DIP:
            # สาย Mean Reversion: เมื่อราคาเด้งกลับไปชนค่าเฉลี่ย SMA 20 คือจบภารกิจ ต้องขายทำกำไรทันที!
            if high_p >= sma_20:
                exec_p = max(open_p, sma_20)
                return self._trigger_exit(
                    ctx, bar_timestamp, "MEAN_REVERSION_TARGET_HIT",
                    f"บรรลุเป้าหมาย Mean Reversion: ราคากลับคืนสู่ค่าเฉลี่ย SMA20 ({sma_20:.2f}) ตามเหตุผลที่เข้าซื้อ",
                    exec_p
                )

        elif ctx.strategy_id in (StrategyType.MOMENTUM_BREAKOUT, StrategyType.TREND_PULLBACK):
            # สายรันเทรนด์: ใช้ Chandelier Exit (ล็อกตามจุดสูงสุดลบด้วย k * ATR)
            # หากตลาดรวมเปลี่ยนเป็น BEAR_CRISIS ให้บีบ Trailing Stop ให้แคบลงทันทีเพื่อล็อกกำไร!
            atr_mult = 2.0 if current_market_regime == "BEAR_CRISIS" else 3.0
            chandelier_stop = ctx.highest_price_since_entry - (atr_mult * current_atr)
            ctx.ratchet_stop_loss(chandelier_stop)

        return ExitDecision(
            should_exit=False,
            exit_type="HOLD_WITH_DISCIPLINE",
            exit_reason_detail=f"สมมติฐาน [{ctx.strategy_id.value}] ยังคงอยู่ (Active SL: {ctx.active_stop_loss:.2f}, Held: {ctx.bars_held}/{ctx.time_stop_bars} bars)",
            suggested_execution_price=close_p
        )

    def _trigger_exit(
        self,
        ctx: PositionContext,
        timestamp: pd.Timestamp,
        exit_type: str,
        detail: str,
        exec_price: float
    ) -> ExitDecision:
        pnl_pct = ((exec_price - ctx.entry_price) / ctx.entry_price) * 100.0
        self.closed_audit_log.append({
            "position_id": ctx.position_id,
            "symbol": ctx.symbol,
            "strategy_id": ctx.strategy_id.value,
            "entry_reason": ctx.entry_reason,
            "exit_type": exit_type,
            "exit_detail": detail,
            "bars_held": ctx.bars_held,
            "entry_price": ctx.entry_price,
            "exit_price": round(exec_price, 4),
            "pnl_pct": round(pnl_pct, 2),
            "exit_timestamp": timestamp
        })
        del self.open_positions[ctx.position_id]
        return ExitDecision(
            should_exit=True,
            exit_type=exit_type,
            exit_reason_detail=detail,
            suggested_execution_price=exec_price
        )


# =====================================================================
# ตัวอย่างการใช้งานจริง: บังคับบอทตัดขายเมื่อเกิด False Breakout หรือหมดเวลา
# =====================================================================
if __name__ == "__main__":
    pcm = PositionContextManager()

    # เปิดสถานะซื้อหุ้น XYZ ด้วยกลยุทธ์ MOMENTUM_BREAKOUT ที่ราคา 51.00 บาท (เบรกแนวต้าน 50.00 บาท)
    pos_ctx = PositionContext(
        position_id="ORD-2026-001",
        symbol="XYZ",
        strategy_id=StrategyType.MOMENTUM_BREAKOUT,
        entry_reason="Breakout เหนือแนวต้าน 50.00 บาท พร้อม RVOL 2.3x และ Volatility Squeeze",
        entry_timestamp=pd.Timestamp("2026-03-02"),
        entry_price=51.00,
        shares=2000,
        entry_atr=1.50,
        initial_stop_loss=48.00,                    # Hard SL ที่ 2 ATR (48.00 บาท)
        invalidation_rule=InvalidationRule.CLOSE_BELOW_BREAKOUT_LEVEL,
        invalidation_reference_price=50.00,         # ถ้าปิดหลุด 50.00 บาท แปลว่าเบรกหลอก!
        time_stop_bars=5,
        min_expected_atr_gain=0.8
    )
    pcm.register_entry(pos_ctx)

    # วันถัดมา: ราคาถูกทุบปิดที่ 49.50 บาท (ยังไม่ถึง Hard SL ที่ 48.00 แต่หลุดระดับ Breakout 50.00 แล้ว!)
    decision = pcm.evaluate_bar_for_position(
        position_id="ORD-2026-001",
        bar_timestamp=pd.Timestamp("2026-03-03"),
        open_p=51.20,
        high_p=51.50,
        low_p=49.30,
        close_p=49.50,
        current_atr=1.55,
        sma_20=48.90,
        ema_50=47.50,
        current_market_regime="BULL_QUIET"
    )
    print(f"ผลการตัดสินใจ: should_exit={decision.should_exit}")
    print(f"ประเภทการออก: {decision.exit_type}")
    print(f"รายละเอียด:   {decision.exit_reason_detail}")
