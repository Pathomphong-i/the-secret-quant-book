from __future__ import annotations
# ==============================================================================
# หนังสือ: เลิกพึ่งบอทคนอื่น มาสร้างระบบเทรดของคุณเองด้วย Python: วิเคราะห์หุ้นและสร้างระบบอย่างมีวินัย
# ผู้เขียน: ปฐมพงษ์ พิพัฒน์สุริยวงศ์
# คำเตือน: เนื้อหาและโค้ดในไฟล์นี้จัดทำขึ้นเพื่อการศึกษาและเป็นความคิดเห็นส่วนตัวของผู้เขียนเท่านั้น
#         มิใช่การแนะนำการลงทุน ผู้ลงทุนโปรดศึกษาข้อมูลและความเสี่ยงด้วยตนเอง
# ==============================================================================

"""บทที่ 7–9: การคัดกรองสัญญาณ 3 ชั้น (KAMA), Position Context & Ratchet Stop, และ ATR Risk Sizing"""

# --- Source: script_05.py ---
import numpy as np
import pandas as pd
from dataclasses import dataclass
from enum import Enum


class MarketRegime(Enum):
    BULL_QUIET = "BULL_QUIET"           # ขาขึ้นความผันผวนต่ำ (เหมาะกับ Breakout เต็มกำลัง)
    BULL_VOLATILE = "BULL_VOLATILE"     # ขาขึ้นแต่ผันผวนสูง (เทรดได้แต่ต้องลดขนาดไม้)
    SIDEWAYS_CHOP = "SIDEWAYS_CHOP"     # ตลาดไร้ทิศทาง (คัดกรองเข้มงวดพิเศษ)
    BEAR_CRISIS = "BEAR_CRISIS"         # ตลาดขาลง/วิกฤต (ห้ามเปิดสถานะซื้อแบบ Breakout)


@dataclass
class FilterThresholds:
    breakout_window: int = 20
    vol_lookback: int = 20
    min_rvol: float = 1.5               # ปริมาณซื้อขายต้อง >= 1.5 เท่าของค่าเฉลี่ย 20 วัน
    min_vol_zscore: float = 1.2         # Volume Z-Score >= 1.2 SD
    min_close_location: float = 0.65    # ราคาปิดต้องอยู่ในโซน 35% บนของแท่งเทียน (แรงซื้อชนะ)
    max_pre_squeeze_vcr: float = 0.92   # ก่อนเบรกเอาต์ต้องมีการบีบอัดความผันผวน (ATR_5 / ATR_20 <= 0.92)
    min_expansion_tr_ratio: float = 1.2 # แท่งที่เบรกต้องมีพิสัยกว้างกว่า ATR เฉลี่ย 1.2 เท่า


class MarketRegimeDetector:
    """
    ตัวตรวจจับสภาวะตลาดรวม (Market Regime Filter) จากข้อมูลดัชนีตลาด (เช่น SET Index / S&P 500)
    ใช้การผสมผสานระหว่าง Trend Structure (SMA50 vs SMA200) และ Realized Volatility Regime
    """

    @staticmethod
    def classify_regime(index_df: pd.DataFrame) -> pd.Series:
        close = index_df['close']
        ret = close.pct_change()

        sma_50 = close.rolling(50, min_periods=50).mean()
        sma_200 = close.rolling(200, min_periods=200).mean()

        # คำนวณความผันผวนรายปี (Annualized 20-day Realized Volatility)
        realized_vol_20 = ret.rolling(20, min_periods=20).std() * np.sqrt(252)
        vol_median_252 = realized_vol_20.rolling(252, min_periods=60).median()

        regimes = pd.Series(MarketRegime.SIDEWAYS_CHOP.value, index=index_df.index)

        is_uptrend = (close > sma_200) & (sma_50 >= sma_200 * 0.99)
        is_downtrend = close < sma_200
        is_high_vol = realized_vol_20 > (vol_median_252 * 1.25)

        regimes[is_uptrend & (~is_high_vol)] = MarketRegime.BULL_QUIET.value
        regimes[is_uptrend & is_high_vol] = MarketRegime.BULL_VOLATILE.value
        regimes[is_downtrend & is_high_vol] = MarketRegime.BEAR_CRISIS.value

        return regimes


class MultiLayerSignalConfirmator:
    """
    ระบบคัดกรองสัญญาณ 3 ชั้น (Regime + Volatility Compression/Expansion + Volume Anomaly)
    เพื่อแยกสัญญาณ Systematic Breakout แท้ ออกจาก False Breakout
    """

    def __init__(self, thresholds: FilterThresholds = FilterThresholds()):
        self.cfg = thresholds

    @staticmethod
    def _compute_atr(df: pd.DataFrame, window: int) -> pd.Series:
        high, low, close = df['high'], df['low'], df['close']
        prev_close = close.shift(1)
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs()
        ], axis=1).max(axis=1)
        return tr.rolling(window=window, min_periods=window).mean(), tr

    def generate_confirmed_signals(
        self,
        stock_df: pd.DataFrame,
        market_regime_series: pd.Series
    ) -> pd.DataFrame:
        """
        รับข้อมูลหุ้นรายตัวและสถานะตลาดรวม คืนค่าตารางพร้อมผลตรวจสอบทีละชั้น (Audit Trail)
        """
        df = stock_df.copy()
        df['market_regime'] = market_regime_series.reindex(df.index).ffill()

        # -----------------------------------------------------------------
        # 0. สัญญาณดิบ (Raw Price Signal): ราคาปิดทะลุจุดสูงสุด 20 วันก่อนหน้า
        # ใช้ .shift(1) บน rolling max เพื่อเทียบกับแนวต้านของ 20 วันก่อนหน้าจริงๆ
        # -----------------------------------------------------------------
        prior_resistance = df['high'].shift(1).rolling(
            self.cfg.breakout_window, min_periods=self.cfg.breakout_window
        ).max()
        df['raw_breakout'] = df['close'] > prior_resistance

        # -----------------------------------------------------------------
        # ชั้นที่ 1: Market Regime Filter (ห้ามเปิด Long Breakout ในช่วง BEAR_CRISIS)
        # -----------------------------------------------------------------
        df['pass_layer1_regime'] = df['market_regime'].isin([
            MarketRegime.BULL_QUIET.value,
            MarketRegime.BULL_VOLATILE.value,
            MarketRegime.SIDEWAYS_CHOP.value
        ])

        # -----------------------------------------------------------------
        # ชั้นที่ 2: Volatility Compression -> Expansion Filter
        # ตรวจว่าในช่วง 5 แท่งก่อนหน้า มีการบีบอัดของความผันผวน (ATR_5 / ATR_20 <= เกณฑ์)
        # และในแท่งปัจจุบันเกิดการระเบิดของพิสัยราคา (True Range > 1.2 * ATR_20)
        # -----------------------------------------------------------------
        atr_5, tr = self._compute_atr(df, 5)
        atr_20, _ = self._compute_atr(df, 20)

        vcr = atr_5 / atr_20.replace(0, np.nan)
        # เคยเกิด Squeeze ในช่วง 5 วันก่อนหน้าหรือไม่
        recent_squeeze = vcr.shift(1).rolling(5, min_periods=1).min() <= self.cfg.max_pre_squeeze_vcr
        # แท่งปัจจุบันขยายตัวจริงหรือไม่
        current_expansion = tr >= (atr_20.shift(1) * self.cfg.min_expansion_tr_ratio)

        df['pass_layer2_volatility'] = recent_squeeze & current_expansion

        # -----------------------------------------------------------------
        # ชั้นที่ 3: Volume Anomaly & Bar Microstructure (CLV)
        # คำนวณค่าเฉลี่ยและ SD ของ Volume จาก 20 แท่งก่อนหน้า (.shift(1))
        # -----------------------------------------------------------------
        vol_mean_prior = df['volume'].shift(1).rolling(self.cfg.vol_lookback, min_periods=10).mean()
        vol_std_prior = df['volume'].shift(1).rolling(self.cfg.vol_lookback, min_periods=10).std()

        df['rvol'] = df['volume'] / vol_mean_prior.replace(0, np.nan)
        df['vol_zscore'] = (df['volume'] - vol_mean_prior) / vol_std_prior.replace(0, np.nan)

        # Close Location Value (CLV): 0.0 = ปิดที่ Low ของวัน, 1.0 = ปิดที่ High ของวัน
        bar_range = (df['high'] - df['low']).replace(0, np.nan)
        df['clv'] = ((df['close'] - df['low']) / bar_range).fillna(0.0)

        # ในตลาด SIDEWAYS_CHOP บังคับเกณฑ์ Volume เข้มงวดขึ้นอีก 25%
        required_rvol = np.where(
            df['market_regime'] == MarketRegime.SIDEWAYS_CHOP.value,
            self.cfg.min_rvol * 1.25,
            self.cfg.min_rvol
        )

        df['pass_layer3_volume'] = (
            (df['rvol'] >= required_rvol)
            & (df['vol_zscore'] >= self.cfg.min_vol_zscore)
            & (df['clv'] >= self.cfg.min_close_location)
        )

        # -----------------------------------------------------------------
        # สรุปสัญญาณที่ผ่านการยืนยันครบทั้ง 3 ชั้น!
        # -----------------------------------------------------------------
        df['confirmed_signal'] = (
            df['raw_breakout']
            & df['pass_layer1_regime']
            & df['pass_layer2_volatility']
            & df['pass_layer3_volume']
        )

        return df


if __name__ == "__main__":
    rng = np.random.default_rng(42)
    dates = pd.bdate_range("2024-01-01", periods=260)
    idx_close = 1500.0 + np.cumsum(rng.normal(0.5, 4.0, 260))
    idx_df = pd.DataFrame({"close": idx_close}, index=dates)
    stock_close = 25.0 + np.cumsum(rng.normal(0.05, 0.25, 260))
    stock_close[-1] = stock_close[-2] + 1.10
    stock_df = pd.DataFrame({
        "open": stock_close - 0.15,
        "high": stock_close + 0.20,
        "low": stock_close - 0.25,
        "close": stock_close,
        "volume": np.append(rng.integers(1_000_000, 1_500_000, 259), [3_500_000]),
    }, index=dates)
    confirmator = MultiLayerSignalConfirmator()
    res_df = confirmator.generate_confirmed_signals(stock_df, idx_df)
    print("=== ผลการคัดกรองสัญญาณ 3 ชั้น (MultiLayerSignalConfirmator) ===")
    print(res_df[["close", "market_regime", "rvol", "clv", "raw_breakout", "confirmed_signal"]].tail(5))


# --- Source: script_06.py ---
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


# --- Source: script_07.py ---
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class ActivePortfolioPosition:
    symbol: str
    sector: str
    shares: int
    entry_price: float
    current_price: float
    active_stop_loss: float

    @property
    def market_value(self) -> float:
        return self.shares * self.current_price

    @property
    def open_risk_amount(self) -> float:
        """
        คำนวณความเสี่ยงเปิด (Open Risk / Heat):
        หากขยับ Stop Loss ขึ้นมาสูงกว่าราคาทุนแล้ว (ล็อกกำไรแล้ว) ความเสี่ยงต่อเงินต้นจะนับเป็น 0
        แต่เพื่อความระมัดระวังที่ถูกต้องและใช้งานได้จริง เราคิดความเสี่ยงจากราคาปัจจุบันลงไปหา active_stop_loss
        """
        risk_per_share = max(0.0, self.current_price - self.active_stop_loss)
        return self.shares * risk_per_share


@dataclass
class RiskEngineConfig:
    risk_per_trade_pct: float = 0.01        # เสี่ยงไม้ละ 1.0% ของมูลค่าพอร์ตสุทธิ
    atr_stop_multiplier: float = 2.5        # ระยะ Stop Loss เริ่มต้น = 2.5 * ATR
    max_position_notional_pct: float = 0.20 # ห้ามซื้อหุ้นตัวเดียวเกิน 20% ของพอร์ต
    max_sector_notional_pct: float = 0.30   # ห้ามถือหุ้นกลุ่มอุตสาหกรรมเดียวกันเกิน 30% ของพอร์ต
    max_portfolio_heat_pct: float = 0.05    # เพดานความเสี่ยงเปิดรวมทั้งพอร์ตสูงสุด 5.0%
    max_pairwise_correlation: float = 0.65  # ห้ามถือหุ้นที่มี Correlation กันเกิน 0.65
    corr_lookback_bars: int = 60            # จำนวนวันย้อนหลังสำหรับคำนวณ Correlation Matrix
    lot_size: int = 100                     # ปัดจำนวนหุ้นเป็น Board Lot (เช่น ตลาดหุ้นไทยทีละ 100 หุ้น)


@dataclass
class AllocationDecision:
    approved: bool
    symbol: str
    recommended_shares: int
    position_notional: float
    initial_stop_price: float
    trade_risk_amount: float
    trade_risk_pct_of_equity: float
    max_corr_with_existing: float
    most_correlated_peer: Optional[str]
    rejection_or_adjustment_note: str


class PortfolioRiskEngine:
    """
    สมองกลบริหารความเสี่ยงและคำนวณขนาดไม้ที่ถูกต้องและใช้งานได้จริง:
    1. คำนวณ ATR Volatility-Adjusted Position Sizing
    2. ควบคุมเพดานความเสี่ยงรวมของพอร์ต (Portfolio Heat)
    3. ควบคุมการกระจุกตัวรายอุตสาหกรรม (Sector Exposure Cap)
    4. ตรวจสอบเมทริกซ์สหสัมพันธ์ (Pairwise Correlation Matrix Guard)
    """

    def __init__(self, config: RiskEngineConfig = RiskEngineConfig()):
        self.cfg = config

    def compute_current_portfolio_heat(
        self,
        total_equity: float,
        current_positions: Dict[str, ActivePortfolioPosition]
    ) -> float:
        if total_equity <= 0:
            return 1.0
        total_open_risk = sum(pos.open_risk_amount for pos in current_positions.values())
        return total_open_risk / total_equity

    def compute_max_correlation_with_portfolio(
        self,
        candidate_symbol: str,
        existing_symbols: List[str],
        returns_df: pd.DataFrame
    ) -> Tuple[float, Optional[str]]:
        """
        คำนวณค่าสหสัมพันธ์ (Correlation) ของผลตอบแทนรายวันย้อนหลัง 60 วัน
        ระหว่างหุ้นตัวใหม่ที่จะซื้อ กับหุ้นทุกตัวที่ถืออยู่ในพอร์ตปัจจุบัน
        """
        if not existing_symbols or candidate_symbol not in returns_df.columns:
            return 0.0, None

        valid_existing = [s for s in existing_symbols if s in returns_df.columns and s != candidate_symbol]
        if not valid_existing:
            return 0.0, None

        recent_returns = returns_df[[candidate_symbol] + valid_existing].tail(self.cfg.corr_lookback_bars)
        corr_Series = recent_returns.corr()[candidate_symbol].drop(candidate_symbol)

        if corr_Series.isna().all():
            return 0.0, None

        max_peer = str(corr_Series.idxmax())
        max_corr = float(corr_Series.loc[max_peer])
        return max_corr, max_peer

    def evaluate_and_size_order(
        self,
        candidate_symbol: str,
        candidate_sector: str,
        entry_price: float,
        current_atr: float,
        total_equity: float,
        available_cash: float,
        current_positions: Dict[str, ActivePortfolioPosition],
        historical_returns_df: pd.DataFrame
    ) -> AllocationDecision:
        """
        ประเมินความเสี่ยงและคำนวณจำนวนหุ้นที่เหมาะสมที่สุดก่อนส่งคำสั่งซื้อ
        """
        if current_atr <= 0 or entry_price <= 0:
            raise ValueError("entry_price และ current_atr ต้องมากกว่า 0")

        # -----------------------------------------------------------------
        # ขั้นตอนที่ 1: ตรวจสอบ Correlation เทียบกับหุ้นในพอร์ตปัจจุบัน
        # -----------------------------------------------------------------
        existing_syms = list(current_positions.keys())
        max_corr, corr_peer = self.compute_max_correlation_with_portfolio(
            candidate_symbol, existing_syms, historical_returns_df
        )

        if max_corr > self.cfg.max_pairwise_correlation:
            return AllocationDecision(
                approved=False,
                symbol=candidate_symbol,
                recommended_shares=0,
                position_notional=0.0,
                initial_stop_price=0.0,
                trade_risk_amount=0.0,
                trade_risk_pct_of_equity=0.0,
                max_corr_with_existing=round(max_corr, 3),
                most_correlated_peer=corr_peer,
                rejection_or_adjustment_note=(
                    f"[REJECTED - Correlation Guard] หุ้น {candidate_symbol} มีค่า Correlation "
                    f"สูงถึง {max_corr:.2f} เทียบกับ {corr_peer} ที่ถืออยู่ในพอร์ต (เพดานสูงสุด {self.cfg.max_pairwise_correlation})"
                )
            )

        # -----------------------------------------------------------------
        # ขั้นตอนที่ 2: ตรวจสอบเพดานความร้อนของพอร์ต (Portfolio Heat Cap)
        # -----------------------------------------------------------------
        current_heat_pct = self.compute_current_portfolio_heat(total_equity, current_positions)
        remaining_heat_pct = self.cfg.max_portfolio_heat_pct - current_heat_pct

        if remaining_heat_pct <= 0.002:  # เหลือโควตาความเสี่ยงน้อยกว่า 0.2%
            return AllocationDecision(
                approved=False,
                symbol=candidate_symbol,
                recommended_shares=0,
                position_notional=0.0,
                initial_stop_price=0.0,
                trade_risk_amount=0.0,
                trade_risk_pct_of_equity=0.0,
                max_corr_with_existing=round(max_corr, 3),
                most_correlated_peer=corr_peer,
                rejection_or_adjustment_note=(
                    f"[REJECTED - Portfolio Heat Full] ความเสี่ยงเปิดรวมของพอร์ตอยู่ที่ {current_heat_pct*100:.2f}% "
                    f"ชนเพดานสูงสุด {self.cfg.max_portfolio_heat_pct*100:.2f}% แล้ว"
                )
            )

        # ใช้ความเสี่ยงต่อไม้ไม่เกินโควตา Portfolio Heat ที่เหลืออยู่
        effective_risk_pct = min(self.cfg.risk_per_trade_pct, remaining_heat_pct)

        # หากค่า Correlation เริ่มสูง (เช่น 0.50 - 0.65) ให้ลดขนาดความเสี่ยงลง 30% (Correlation Scaling)
        adjustment_notes = []
        if max_corr >= 0.50:
            effective_risk_pct *= 0.70
            adjustment_notes.append(f"ลดขนาดไม้ 30% เนื่องจาก Correlation ปานกลาง ({max_corr:.2f} กับ {corr_peer})")

        # -----------------------------------------------------------------
        # ขั้นตอนที่ 3: คำนวณขนาดไม้ตามความผันผวน ATR (Volatility-Adjusted Sizing)
        # -----------------------------------------------------------------
        stop_distance = self.cfg.atr_stop_multiplier * current_atr
        initial_stop_price = entry_price - stop_distance
        risk_budget_thb = total_equity * effective_risk_pct

        raw_shares_by_risk = risk_budget_thb / stop_distance

        # -----------------------------------------------------------------
        # ขั้นตอนที่ 4: คุมเพดานมูลค่าต่อตัว (Single Position Cap), เพดาน Sector, และเงินสดคงเหลือ
        # -----------------------------------------------------------------
        max_notional_single = total_equity * self.cfg.max_position_notional_pct

        current_sector_value = sum(
            pos.market_value for pos in current_positions.values() if pos.sector == candidate_sector
        )
        remaining_sector_notional = max(
            0.0, (total_equity * self.cfg.max_sector_notional_pct) - current_sector_value
        )

        if remaining_sector_notional < (entry_price * self.cfg.lot_size):
            return AllocationDecision(
                approved=False,
                symbol=candidate_symbol,
                recommended_shares=0,
                position_notional=0.0,
                initial_stop_price=0.0,
                trade_risk_amount=0.0,
                trade_risk_pct_of_equity=0.0,
                max_corr_with_existing=round(max_corr, 3),
                most_correlated_peer=corr_peer,
                rejection_or_adjustment_note=(
                    f"[REJECTED - Sector Cap] กลุ่มอุตสาหกรรม '{candidate_sector}' มีสัดส่วนเต็มเพดาน "
                    f"{self.cfg.max_sector_notional_pct*100:.0f}% ของพอร์ตแล้ว"
                )
            )

        max_allowed_notional = min(max_notional_single, remaining_sector_notional, available_cash)
        max_shares_by_notional = max_allowed_notional / entry_price

        final_raw_shares = min(raw_shares_by_risk, max_shares_by_notional)
        # ปัดลงเป็นจำนวนเต็มของ Board Lot (เช่น ทีละ 100 หุ้น)
        recommended_shares = int(final_raw_shares // self.cfg.lot_size) * self.cfg.lot_size

        if recommended_shares <= 0:
            return AllocationDecision(
                approved=False,
                symbol=candidate_symbol,
                recommended_shares=0,
                position_notional=0.0,
                initial_stop_price=round(initial_stop_price, 4),
                trade_risk_amount=0.0,
                trade_risk_pct_of_equity=0.0,
                max_corr_with_existing=round(max_corr, 3),
                most_correlated_peer=corr_peer,
                rejection_or_adjustment_note="[REJECTED - Insufficient Size] ขนาดไม้หลังหักข้อจำกัดน้อยกว่า 1 Board Lot"
            )

        actual_notional = recommended_shares * entry_price
        actual_risk_thb = recommended_shares * stop_distance
        actual_risk_pct = (actual_risk_thb / total_equity) * 100.0

        if not adjustment_notes:
            adjustment_notes.append("อนุมัติขนาดไม้เต็มโควตาตามมาตรฐาน ATR Volatility Parity")

        return AllocationDecision(
            approved=True,
            symbol=candidate_symbol,
            recommended_shares=recommended_shares,
            position_notional=round(actual_notional, 2),
            initial_stop_price=round(initial_stop_price, 4),
            trade_risk_amount=round(actual_risk_thb, 2),
            trade_risk_pct_of_equity=round(actual_risk_pct, 3),
            max_corr_with_existing=round(max_corr, 3),
            most_correlated_peer=corr_peer,
            rejection_or_adjustment_note="; ".join(adjustment_notes)
        )


# =====================================================================
# ตัวอย่างการจำลองสถานการณ์จริงของโต๊ะ Risk Management
# =====================================================================
if __name__ == "__main__":
    np.random.seed(99)
    n_days = 80
    base_factor = np.random.normal(0.0005, 0.015, n_days)

    # สร้างข้อมูลผลตอบแทนรายวันของหุ้น 4 ตัว:
    # TECH_A และ TECH_B วิ่งตามกันแทบจะ 100% (Correlation สูงมาก)
    # HEALTH_C และ ENERGY_D วิ่งอิสระจากกลุ่มเทคฯ
    returns_data = pd.DataFrame({
        "TECH_A": base_factor + np.random.normal(0, 0.004, n_days),
        "TECH_B": base_factor * 0.95 + np.random.normal(0, 0.004, n_days),
        "HEALTH_C": np.random.normal(0.0006, 0.011, n_days),
        "ENERGY_D": np.random.normal(0.0004, 0.025, n_days),
    })

    risk_engine = PortfolioRiskEngine()

    # สมมติพอร์ตมีมูลค่า 2,000,000 บาท และปัจจุบันถือหุ้น TECH_A อยู่ในพอร์ตแล้ว 1 ตัว
    portfolio_equity = 2_000_000.0
    cash_balance = 1_650_000.0
    active_positions = {
        "TECH_A": ActivePortfolioPosition(
            symbol="TECH_A",
            sector="Technology",
            shares=3500,
            entry_price=100.0,
            current_price=102.0,
            active_stop_loss=95.0
        )
    }

    print("=== ทดสอบที่ 1: บอทส่งสัญญาณซื้อหุ้น TECH_B (ซึ่งวิ่งตาม TECH_A อย่างใกล้ชิด) ===")
    res1 = risk_engine.evaluate_and_size_order(
        candidate_symbol="TECH_B",
        candidate_sector="Technology",
        entry_price=50.0,
        current_atr=1.6,
        total_equity=portfolio_equity,
        available_cash=cash_balance,
        current_positions=active_positions,
        historical_returns_df=returns_data
    )
    print(f"  Approved: {res1.approved} | Shares: {res1.recommended_shares}")
    print(f"  เหตุผล:   {res1.rejection_or_adjustment_note}\n")

    print("=== ทดสอบที่ 2: บอทส่งสัญญาณซื้อหุ้น HEALTH_C (ความผันผวนต่ำ ATR = 0.80 บาท) ===")
    res2 = risk_engine.evaluate_and_size_order(
        candidate_symbol="HEALTH_C",
        candidate_sector="Healthcare",
        entry_price=40.0,
        current_atr=0.80,
        total_equity=portfolio_equity,
        available_cash=cash_balance,
        current_positions=active_positions,
        historical_returns_df=returns_data
    )
    print(f"  Approved: {res2.approved} | Shares: {res2.recommended_shares:,} หุ้น (มูลค่า {res2.position_notional:,.0f} บาท)")
    print(f"  Stop Loss: {res2.initial_stop_price:.2f} บาท | ความเสี่ยงจริง: {res2.trade_risk_amount:,.0f} บาท ({res2.trade_risk_pct_of_equity}% ของพอร์ต)")
    print(f"  เหตุผล:   {res2.rejection_or_adjustment_note}\n")

    print("=== ทดสอบที่ 3: บอทส่งสัญญาณซื้อหุ้น ENERGY_D (ความผันผวนสูงมาก ATR = 3.20 บาท) ===")
    res3 = risk_engine.evaluate_and_size_order(
        candidate_symbol="ENERGY_D",
        candidate_sector="Energy",
        entry_price=40.0,
        current_atr=3.20,
        total_equity=portfolio_equity,
        available_cash=cash_balance,
        current_positions=active_positions,
        historical_returns_df=returns_data
    )
    print(f"  Approved: {res3.approved} | Shares: {res3.recommended_shares:,} หุ้น (มูลค่า {res3.position_notional:,.0f} บาท)")
    print(f"  Stop Loss: {res3.initial_stop_price:.2f} บาท | ความเสี่ยงจริง: {res3.trade_risk_amount:,.0f} บาท ({res3.trade_risk_pct_of_equity}% ของพอร์ต)")
    print(f"  เหตุผล:   {res3.rejection_or_adjustment_note}")


