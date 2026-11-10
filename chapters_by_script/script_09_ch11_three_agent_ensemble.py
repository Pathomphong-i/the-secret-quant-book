import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Dict


@dataclass
class CouncilDecision:
    """ผลการตัดสินใจของสภา 3 สมองย่อยสำหรับหุ้น 1 ตัว ณ สิ้นวัน"""
    symbol: str
    regime_label: str
    trend_agent_score: float       # คะแนนจาก Agent 1 (-1.0 ถึง +1.0)
    reversion_agent_score: float   # คะแนนจาก Agent 2 (-1.0 ถึง +1.0)
    cash_shield_factor: float      # ตัวคูณความปลอดภัยจาก Agent 3 (0.0 ถึง 1.0)
    composite_conviction: float    # คะแนนความมั่นใจสุทธิหลังถ่วงน้ำหนักตามสภาวะตลาด
    action: str                    # 'BUY_OR_HOLD', 'REDUCE', 'EXIT_TO_CASH'
    atr_stop_distance: float       # ระยะตัดขาดทุนที่ยืดหดตาม ATR
    suggested_risk_fraction: float # สัดส่วนความเสี่ยงที่ควรจัดสรรให้ไม้นี้


class StarterThreeAgentCouncil:
    """
    ตัวอย่างบอทเริ่มต้น 3 สมองย่อย (Starter 3-Agent Ensemble Council):
      - Agent 1: Adaptive Trend Follower (ใช้เส้น KAMA ที่ปรับความไวตาม Efficiency Ratio)
      - Agent 2: Mean-Reversion Sniper (ดักจังหวะย่อตัวในโครงสร้างที่ไม่พัง)
      - Agent 3: Cash & Volatility Shield (หรี่หน้าตักอัตโนมัติเมื่อเกิดภาวะวิกฤต)
    """

    def __init__(
        self,
        er_window: int = 20,
        atr_window: int = 14,
        base_risk_per_trade: float = 0.01,  # เสี่ยงเริ่มต้น 1% ของพอร์ตต่อไม้
    ):
        self.er_window = er_window
        self.atr_window = atr_window
        self.base_risk_per_trade = base_risk_per_trade

    def compute_adaptive_indicators(self, df_ohlcv: pd.DataFrame) -> pd.DataFrame:
        """
        คำนวณพารามิเตอร์แบบยืดหยุ่น (Dynamic Parameters):
        1. Kaufman's Adaptive Moving Average (KAMA) ที่ปรับความเร็วเองตามตลาด
        2. Average True Range (ATR) สำหรับยืดหดระยะ Stop Loss และขนาดไม้
        3. Dynamic Z-Score ของระยะห่างราคาสำหรับ Agent สายดักย่อ
        """
        df = df_ohlcv.copy()
        close = df["close"].astype(float)
        high = df["high"].astype(float)
        low = df["low"].astype(float)

        # 1. คำนวณ Efficiency Ratio (ER)
        direction = close.diff(self.er_window).abs()
        volatility = close.diff(1).abs().rolling(self.er_window).sum()
        er = (direction / volatility.replace(0, np.nan)).fillna(0.0)
        df["er"] = er

        # 2. คำนวณเส้น KAMA (ปรับสปีดระหว่าง EMA 2 วัน กับ EMA 30 วัน ตามค่า ER)
        fast_sc = 2.0 / (2.0 + 1.0)
        slow_sc = 2.0 / (30.0 + 1.0)
        sc = ((er * (fast_sc - slow_sc)) + slow_sc) ** 2

        kama = np.zeros(len(df))
        close_vals = close.values
        sc_vals = sc.values
        kama[0] = close_vals[0]
        for i in range(1, len(df)):
            kama[i] = kama[i - 1] + sc_vals[i] * (close_vals[i] - kama[i - 1])
        df["kama"] = kama

        # 3. คำนวณ Average True Range (ATR)
        prev_close = close.shift(1)
        tr = pd.concat([
            (high - low),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ], axis=1).max(axis=1)
        df["atr"] = tr.rolling(self.atr_window, min_periods=1).mean()

        # 4. คำนวณระยะห่างจากค่าเฉลี่ยในหน่วยของ ATR (ATR-Normalized Deviation)
        df["kama_dist_atr"] = (close - df["kama"]) / df["atr"].replace(0, np.nan)
        df["kama_slope_atr"] = df["kama"].diff(5) / df["atr"].replace(0, np.nan)

        return df

    def evaluate_agents(
        self,
        symbol: str,
        df_ohlcv: pd.DataFrame,
        regime_probs: Dict[str, float],
    ) -> CouncilDecision:
        """
        ให้สมองย่อยทั้ง 3 ตัวลงคะแนนเสียง แล้วถ่วงน้ำหนักด้วยความน่าจะเป็นของสภาวะตลาด
        (`regime_probs` ได้จาก MarketRegimeDetector ในบทที่ 4)
        """
        df = self.compute_adaptive_indicators(df_ohlcv)
        latest = df.iloc[-1]

        dist_atr = float(latest["kama_dist_atr"])
        slope_atr = float(latest["kama_slope_atr"])
        er_val = float(latest["er"])
        atr_val = float(latest["atr"])

        # ------------------------------------------------------------------
        # Agent 1: Adaptive Trend Follower
        # ชอบเมื่อราคาอยู่เหนือเส้น KAMA, ความชัน KAMA เป็นบวก และ ER มีประสิทธิภาพสูง
        # ------------------------------------------------------------------
        raw_trend = 0.6 * np.tanh(dist_atr * 0.7) + 0.4 * np.tanh(slope_atr * 0.8)
        trend_agent_score = float(np.clip(raw_trend * (0.5 + 0.5 * er_val), -1.0, 1.0))

        # ------------------------------------------------------------------
        # Agent 2: Mean-Reversion Pullback Sniper
        # ชอบดักซื้อเมื่อราคาย่อตัวลงมาต่ำกว่า KAMA ประมาณ 1.0 ถึง 2.5 ATR
        # แต่โครงสร้างหลักยังไม่พังทลาย (slope_atr ไม่ได้ดิ่งเหวเกิน -1.5)
        # ------------------------------------------------------------------
        if -2.8 <= dist_atr <= -0.5 and slope_atr > -1.2:
            # ยิ่งย่อลงมาในโซนได้เปรียบ คะแนนดักย่อยิ่งเป็นบวก
            reversion_agent_score = float(np.clip(-dist_atr / 2.5, 0.0, 1.0))
        elif dist_atr > 2.2:
            # ราคาวิ่งฉีกตัวออกห่างค่าเฉลี่ยมากเกินไป เตือนระวังการย่อตัว
            reversion_agent_score = float(np.clip(-(dist_atr - 2.0) / 2.0, -1.0, 0.0))
        else:
            reversion_agent_score = 0.0

        # ------------------------------------------------------------------
        # Agent 3: Cash & Volatility Shield
        # อ่านความน่าจะเป็นของโหมดวิกฤต (Crisis Probability) เพื่อสั่งหรี่หน้าตัก
        # ------------------------------------------------------------------
        p_bull = float(regime_probs.get("BULL_TREND", 1.0 / 3.0))
        p_side = float(regime_probs.get("SIDEWAYS", 1.0 / 3.0))
        p_crisis = float(regime_probs.get("HIGH_VOL_CRISIS", 1.0 / 3.0))

        # ถ้าความน่าจะเป็นวิกฤตพุ่งสูง ตัวคูณความปลอดภัยจะลดลงเข้าใกล้ 0 ทันที
        cash_shield_factor = float(np.clip(1.0 - (p_crisis * 1.35), 0.0, 1.0))

        # ------------------------------------------------------------------
        # สภารวมคะแนนโหวตตามสภาพอากาศตลาด (Regime-Conditioned Voting)
        # ในโหมด Bull Trend -> ให้น้ำหนัก Agent 1 นำ
        # ในโหมด Sideways   -> ให้น้ำหนัก Agent 2 นำ
        # และคูณด้วยเกราะป้องกันเงินสดของ Agent 3 เสมอ
        # ------------------------------------------------------------------
        active_weight_sum = max(p_bull + p_side, 1e-6)
        w_trend = p_bull / active_weight_sum
        w_reversion = p_side / active_weight_sum

        raw_conviction = (w_trend * trend_agent_score) + (w_reversion * reversion_agent_score)
        composite_conviction = float(raw_conviction * cash_shield_factor)

        # กำหนดชื่อสภาวะตลาดหลัก
        regime_label = max(regime_probs.items(), key=lambda x: x[1])[0]

        # ------------------------------------------------------------------
        # Dynamic ATR Stop & Volatility-Scaled Risk Fraction
        # ------------------------------------------------------------------
        # ในโหมดเทรนด์ให้ระยะหายใจกว้างขึ้น (2.5 ATR) ในโหมดไซด์เวย์/วิกฤตบีบแคบลง (1.8 ATR)
        atr_multiplier = 2.5 if regime_label == "BULL_TREND" else 1.8
        atr_stop_distance = float(atr_multiplier * atr_val)

        if cash_shield_factor < 0.25 or composite_conviction < -0.15:
            action = "EXIT_TO_CASH"
            suggested_risk = 0.0
        elif composite_conviction >= 0.20:
            action = "BUY_OR_HOLD"
            suggested_risk = float(self.base_risk_per_trade * composite_conviction)
        else:
            action = "REDUCE"
            suggested_risk = 0.0

        return CouncilDecision(
            symbol=symbol,
            regime_label=regime_label,
            trend_agent_score=round(trend_agent_score, 4),
            reversion_agent_score=round(reversion_agent_score, 4),
            cash_shield_factor=round(cash_shield_factor, 4),
            composite_conviction=round(composite_conviction, 4),
            action=action,
            atr_stop_distance=round(atr_stop_distance, 4),
            suggested_risk_fraction=round(suggested_risk, 5),
        )


if __name__ == "__main__":
    rng = np.random.default_rng(42)
    dates = pd.bdate_range("2024-01-01", periods=120)
    close = 50.0 + np.cumsum(rng.normal(0.12, 0.45, 120))
    df_sample = pd.DataFrame({
        "open": close - 0.2,
        "high": close + 0.4,
        "low": close - 0.4,
        "close": close,
        "volume": rng.integers(1_000_000, 3_000_000, 120),
    }, index=dates)
    council = StarterThreeAgentCouncil()
    decision = council.evaluate_agents(
        symbol="SAMPLE_STOCK",
        df_ohlcv=df_sample,
        regime_probs={"BULL_TREND": 0.72, "SIDEWAYS": 0.20, "HIGH_VOL_CRISIS": 0.08},
    )
    print("=== ผลการตัดสินใจของสภา 3 กลยุทธ์ย่อย (StarterThreeAgentCouncil) ===")
    print(decision)
