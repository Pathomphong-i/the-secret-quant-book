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
