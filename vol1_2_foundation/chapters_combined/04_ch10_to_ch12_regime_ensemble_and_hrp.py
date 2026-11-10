from __future__ import annotations
# ==============================================================================
# หนังสือ: เลิกพึ่งบอทคนอื่น มาสร้างระบบเทรดของคุณเองด้วย Python: วิเคราะห์หุ้นและสร้างระบบอย่างมีวินัย
# ผู้เขียน: ปฐมพงษ์ พิพัฒน์สุริยวงศ์
# คำเตือน: เนื้อหาและโค้ดในไฟล์นี้จัดทำขึ้นเพื่อการศึกษาและเป็นความคิดเห็นส่วนตัวของผู้เขียนเท่านั้น
#         มิใช่การแนะนำการลงทุน ผู้ลงทุนโปรดศึกษาข้อมูลและความเสี่ยงด้วยตนเอง
# ==============================================================================

"""บทที่ 1–12: สมองกลตรวจจับสภาวะตลาด (Market Regime), สภาโหวต 3 กลยุทธ์ย่อย และการจัดพอร์ต HRP"""

# --- Source: script_08.py ---
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Dict, Optional, Tuple


@dataclass
class RegimeState:
    """โครงสร้างข้อมูลผลลัพธ์การอ่านสภาวะตลาดในแต่ละวัน"""
    timestamp: pd.Timestamp
    regime_label: str                 # 'BULL_TREND', 'SIDEWAYS', 'HIGH_VOL_CRISIS'
    regime_id: int                    # 0 = Sideways, 1 = Bull Trend, 2 = Crisis
    probabilities: Dict[str, float]   # ความน่าจะเป็นของแต่ละโหมด (รวมกันได้ 1.0)
    efficiency_ratio: float           # ค่าประสิทธิภาพการวิ่งของราคา (-1.0 ถึง +1.0)
    vol_zscore: float                 # ระดับความผันผวนสัมพัทธ์ (Z-Score)
    trend_zscore: float               # ความแข็งแกร่งของแนวโน้มเทียบความผันผวน


class MarketRegimeDetector:
    """
    ระบบตรวจจับสภาวะตลาดที่ถูกต้องและใช้งานได้จริง (Market Regime Detector)
    ผสมผสานคุณลักษณะทางสถิติ 3 มิติ เข้ากับ Bayesian / Markov Regime Transition Filter
    ปราศจาก Look-Ahead Bias 100% (คำนวณจากหน้าต่างข้อมูลในอดีตจนถึงแท่งที่ปิดแล้วเท่านั้น)
    """

    def __init__(
        self,
        er_window: int = 20,
        vol_short_window: int = 20,
        vol_long_window: int = 252,
        trend_window: int = 60,
        transition_stickiness: float = 0.80,
    ):
        self.er_window = er_window
        self.vol_short_window = vol_short_window
        self.vol_long_window = vol_long_window
        self.trend_window = trend_window
        self.transition_stickiness = np.clip(transition_stickiness, 0.50, 0.98)

        # เมทริกซ์ความน่าจะเป็นในการเปลี่ยนสภาวะ (Markov Transition Matrix)
        # สภาวะตลาดมักมีความเฉื่อย (Regime Persistence) ไม่สลับไปมาทุกวัน
        s = self.transition_stickiness
        rem = (1.0 - s) / 2.0
        self.transition_matrix = np.array([
            [s,   rem, rem],  # จาก Sideways (0) -> [Sideways, Bull, Crisis]
            [rem, s,   rem],  # จาก Bull Trend (1) -> [Sideways, Bull, Crisis]
            [rem, rem, s  ],  # จาก Crisis (2) -> [Sideways, Bull, Crisis]
        ])

    def extract_features(self, close_series: pd.Series) -> pd.DataFrame:
        """
        สกัดคุณลักษณะทางสถิติ 3 มิติจากข้อมูลราคาปิด (Close Price)
        ทุกการคำนวณใช้ Rolling Window จากอดีตเท่านั้น ไม่มีข้อมูลอนาคตปนเปื้อน
        """
        df = pd.DataFrame(index=close_series.index)
        df["close"] = close_series.astype(float)
        df["ret"] = df["close"].pct_change()

        # 1. Signed Efficiency Ratio (ทิศทางและประสิทธิภาพการวิ่งของราคา)
        net_change = df["close"].diff(self.er_window)
        abs_daily_move = df["close"].diff(1).abs().rolling(self.er_window).sum()
        df["signed_er"] = (net_change / abs_daily_move.replace(0, np.nan)).fillna(0.0)

        # 2. Realized Volatility & Rolling Vol Z-Score (ดัชนีความผันผวนสัมพัทธ์)
        df["realized_vol"] = df["ret"].rolling(self.vol_short_window).std() * np.sqrt(252)
        vol_mean = df["realized_vol"].rolling(
            self.vol_long_window, min_periods=self.vol_short_window * 2
        ).mean()
        vol_std = df["realized_vol"].rolling(
            self.vol_long_window, min_periods=self.vol_short_window * 2
        ).std().replace(0, np.nan)
        df["vol_zscore"] = ((df["realized_vol"] - vol_mean) / vol_std).fillna(0.0)

        # 3. Volatility-Normalized Trend Score (ผลตอบแทนปรับด้วยความผันผวน)
        rolling_ret = df["close"].pct_change(self.trend_window)
        rolling_period_vol = (
            df["ret"].rolling(self.trend_window).std() * np.sqrt(self.trend_window)
        ).replace(0, np.nan)
        df["trend_zscore"] = (rolling_ret / rolling_period_vol).fillna(0.0)

        return df

    @staticmethod
    def _emission_likelihoods(
        signed_er: float, vol_z: float, trend_z: float
    ) -> np.ndarray:
        """
        คำนวณค่าความน่าจะเป็นที่ข้อมูลสถิติวันนี้จะมาจากแต่ละสภาวะ (Emission Likelihood)
        โดยไม่ต้องใช้ Hard-coded Threshold แบบตัดขาด แต่ใช้ Continuous Soft-Scoring:
        Index 0: SIDEWAYS
        Index 1: BULL_TREND
        Index 2: HIGH_VOL_CRISIS
        """
        # คะแนนความเป็น Crisis: พุ่งสูงขึ้นเมื่อความผันผวนฉีกตัวขึ้น (vol_z > 1.0)
        # หรือเมื่อตลาดดิ่งลงแรงพร้อมประสิทธิภาพขาลงสูง (trend_z < -1.0 หรือ signed_er < -0.35)
        crisis_score = (
            1.2 * max(0.0, vol_z - 0.5)
            + 1.5 * max(0.0, -trend_z - 0.5)
            + 2.0 * max(0.0, -signed_er - 0.25)
        )

        # คะแนนความเป็น Bull Trend: พุ่งสูงขึ้นเมื่อ signed_er เป็นบวกชัดเจน,
        # trend_z เป็นบวกแข็งแกร่ง และความผันผวนไม่ระเบิดเกินควบคุม
        bull_score = (
            2.5 * max(0.0, signed_er)
            + 1.2 * max(0.0, trend_z)
            - 0.8 * max(0.0, vol_z - 1.2)
        )

        # คะแนนความเป็น Sideways: สูงเมื่อราคาแกว่งตัวในกรอบแคบ (|signed_er| ต่ำ)
        # และความผันผวนอยู่ในโซนปกติ
        sideways_score = (
            1.8 * max(0.0, 0.35 - abs(signed_er))
            + 1.0 * max(0.0, 0.8 - abs(trend_z))
            - 0.7 * max(0.0, abs(vol_z) - 1.0)
        )

        logits = np.array([sideways_score, bull_score, crisis_score], dtype=float)
        # แปลงเป็นความน่าจะเป็นด้วย Softmax ที่เสถียรทางตัวเลข
        logits -= np.max(logits)
        exp_scores = np.exp(logits)
        return exp_scores / np.sum(exp_scores)

    def analyze_series(self, close_series: pd.Series) -> pd.DataFrame:
        """
        รันตัวกรอง Markov Regime Filter แบบเรียงตามลำดับเวลาจริง (Recursive Forward Filter)
        คืนค่า DataFrame พร้อมความน่าจะเป็นของทั้ง 3 สภาวะในแต่ละวัน
        """
        feat_df = self.extract_features(close_series)
        n = len(feat_df)

        # ความน่าจะเป็นเริ่มต้น (Prior) แบ่งเท่ากันในวันแรก
        prior_prob = np.array([1.0 / 3.0, 1.0 / 3.0, 1.0 / 3.0])

        prob_sideways = np.zeros(n)
        prob_bull = np.zeros(n)
        prob_crisis = np.zeros(n)
        regime_ids = np.zeros(n, dtype=int)
        regime_labels = []

        label_map = {
            0: "SIDEWAYS",
            1: "BULL_TREND",
            2: "HIGH_VOL_CRISIS",
        }

        for i in range(n):
            row = feat_df.iloc[i]
            # ขั้นที่ 1: Predict step (คูณกับ Markov Transition Matrix จากเมื่อวาน)
            predicted_prob = prior_prob @ self.transition_matrix

            # ขั้นที่ 2: Update step (คูณกับ Emission Likelihood ของข้อมูลวันนี้ตามกฎของ Bayes)
            likelihood = self._emission_likelihoods(
                signed_er=float(row["signed_er"]),
                vol_z=float(row["vol_zscore"]),
                trend_z=float(row["trend_zscore"]),
            )
            posterior = predicted_prob * likelihood
            posterior_sum = np.sum(posterior)
            if posterior_sum > 0:
                posterior /= posterior_sum
            else:
                posterior = predicted_prob

            prior_prob = posterior

            prob_sideways[i] = posterior[0]
            prob_bull[i] = posterior[1]
            prob_crisis[i] = posterior[2]

            r_id = int(np.argmax(posterior))
            regime_ids[i] = r_id
            regime_labels.append(label_map[r_id])

        feat_df["prob_sideways"] = prob_sideways
        feat_df["prob_bull_trend"] = prob_bull
        feat_df["prob_high_vol_crisis"] = prob_crisis
        feat_df["regime_id"] = regime_ids
        feat_df["regime_label"] = regime_labels

        # สำคัญที่สุด: สร้างคอลัมน์สัญญาณสำหรับใช้ตัดสินใจในวันถัดไป (.shift(1))
        # เพื่อรับประกันว่าจะไม่มีการเอาข้อมูลปิดตลาดของวันนี้ไปแอบเทรดตอนเช้าของวันนี้เอง
        feat_df["exec_regime_label"] = feat_df["regime_label"].shift(1).fillna("SIDEWAYS")
        feat_df["exec_prob_bull"] = feat_df["prob_bull_trend"].shift(1).fillna(1.0 / 3.0)
        feat_df["exec_prob_sideways"] = feat_df["prob_sideways"].shift(1).fillna(1.0 / 3.0)
        feat_df["exec_prob_crisis"] = feat_df["prob_high_vol_crisis"].shift(1).fillna(1.0 / 3.0)

        return feat_df


if __name__ == "__main__":
    rng = np.random.default_rng(42)
    dates = pd.bdate_range("2024-01-01", periods=300)
    close_s = pd.Series(1500.0 + np.cumsum(rng.normal(0.8, 5.0, 300)), index=dates)
    detector = MarketRegimeDetector()
    regime_df = detector.analyze_series(close_s)
    print("=== ผลการจำแนกสภาวะตลาดด้วย Markov Regime Detector ===")
    print(regime_df[["close", "signed_er", "vol_zscore", "exec_regime_label", "exec_prob_bull"]].tail(5))


# --- Source: script_09.py ---
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
        (`regime_probs` ได้จาก MarketRegimeDetector ในบทที่ 1)
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


# --- Source: script_10.py ---
import numpy as np
import pandas as pd
from typing import Dict, List, Optional


class AdaptivePortfolioAllocator:
    """
    สมองกลจัดสรรน้ำหนักพอร์ตที่ถูกต้องและใช้งานได้จริง (AI Portfolio Allocator)
    รองรับ:
      1. Inverse-Volatility Weighting
      2. Hierarchical Risk Parity (HRP - López de Prado) แบบครบวงจร
      3. Conviction-Tilted Risk Allocation + Regime-Aware Cash Buffer
      4. Portfolio Volatility Targeting & Position Concentration Caps
    """

    def __init__(
        self,
        cov_window: int = 60,
        target_portfolio_vol: float = 0.16,  # เป้าหมายความผันผวนพอร์ต 16% ต่อปี
        max_single_weight: float = 0.25,     # ห้ามถือหุ้นตัวเดียวเกิน 25% ของพอร์ต
        min_position_weight: float = 0.03,   # ถ้าน้ำหนักต่ำกว่า 3% ให้ปัดทิ้งเพื่อประหยัดค่าคอมฯ
    ):
        self.cov_window = cov_window
        self.target_portfolio_vol = target_portfolio_vol
        self.max_single_weight = max_single_weight
        self.min_position_weight = min_position_weight

    # ------------------------------------------------------------------
    # 1. Inverse-Volatility Weighting
    # ------------------------------------------------------------------
    @staticmethod
    def compute_inverse_vol_weights(returns_df: pd.DataFrame) -> pd.Series:
        """คำนวณน้ำหนักผกผันกับความผันผวนรายตัว"""
        vols = returns_df.std() * np.sqrt(252)
        vols = vols.replace(0, np.nan).fillna(vols.median() if len(vols) > 0 else 1.0)
        inv_vol = 1.0 / vols
        return inv_vol / inv_vol.sum()

    # ------------------------------------------------------------------
    # 2. Hierarchical Risk Parity (HRP) - Full Implementation
    # ------------------------------------------------------------------
    @staticmethod
    def _cluster_variance(cov: pd.DataFrame, items: List[str]) -> float:
        """คำนวณความแปรปรวนของกลุ่มย่อย (Cluster Variance) ด้วยน้ำหนัก Inverse-Variance ภายในกลุ่ม"""
        sub_cov = cov.loc[items, items]
        diag_var = np.diag(sub_cov.values)
        inv_diag = 1.0 / np.where(diag_var > 1e-12, diag_var, 1e-12)
        w = inv_diag / np.sum(inv_diag)
        return float(w.T @ sub_cov.values @ w)

    @staticmethod
    def _quasi_diagonal_order(dist_matrix: np.ndarray) -> List[int]:
        """
        จัดเรียงลำดับดัชนีสินทรัพย์ด้วย Single-Linkage Hierarchical Clustering Tree
        เพื่อให้สินทรัพย์ที่มีความสัมพันธ์ใกล้ชิดกันเรียงอยู่ติดกันบนแกนเมทริกซ์
        """
        n = dist_matrix.shape[0]
        if n <= 1:
            return list(range(n))

        # เริ่มต้นให้แต่ละสินทรัพย์เป็นคลัสเตอร์เดี่ยวของตัวเอง
        clusters: List[List[int]] = [[i] for i in range(n)]
        dist = dist_matrix.copy().astype(float)
        np.fill_diagonal(dist, np.inf)

        # รวมคลัสเตอร์ที่อยู่ใกล้กันที่สุดทีละคู่จนเหลือต้นไม้เดียว
        while len(clusters) > 1:
            min_d = np.inf
            merge_pair = (0, 1)
            for i in range(len(clusters)):
                for j in range(i + 1, len(clusters)):
                    # Single-linkage distance ระหว่างคลัสเตอร์ i และ j
                    d_ij = min(dist[a, b] for a in clusters[i] for b in clusters[j])
                    if d_ij < min_d:
                        min_d = d_ij
                        merge_pair = (i, j)

            idx_a, idx_b = merge_pair
            clusters[idx_a] = clusters[idx_a] + clusters[idx_b]
            clusters.pop(idx_b)

        return clusters[0]

    def compute_hrp_weights(self, returns_df: pd.DataFrame) -> pd.Series:
        """
        คำนวณน้ำหนักพอร์ตด้วย Hierarchical Risk Parity (HRP):
        ขั้นที่ 1: คำนวณ Correlation Distance Matrix
        ขั้นที่ 2: จัดเรียงลำดับสินทรัพย์ (Quasi-Diagonalization)
        ขั้นที่ 3: แบ่งครึ่งงบความเสี่ยงซ้ำๆ จากบนลงล่าง (Recursive Bisection)
        """
        cols = list(returns_df.columns)
        if len(cols) == 0:
            return pd.Series(dtype=float)
        if len(cols) == 1:
            return pd.Series({cols[0]: 1.0})

        cov = returns_df.cov() * 252.0
        corr = returns_df.corr().fillna(0.0).clip(-1.0, 1.0)

        # ขั้นที่ 1: แปลงสหสัมพันธ์เป็นระยะห่างทางเรขาคณิต d_ij = sqrt(0.5 * (1 - corr_ij))
        dist_corr = np.sqrt(np.clip(0.5 * (1.0 - corr.values), 0.0, 1.0))
        # วัดระยะห่างยุคลิดระหว่างคอลัมน์ของเมทริกซ์ระยะห่างอีกชั้นเพื่อความเสถียร
        n = len(cols)
        euclidean_dist = np.zeros((n, n))
        for i in range(n):
            for j in range(i + 1, n):
                d = np.linalg.norm(dist_corr[:, i] - dist_corr[:, j])
                euclidean_dist[i, j] = d
                euclidean_dist[j, i] = d

        # ขั้นที่ 2: Quasi-Diagonalization
        ordered_indices = self._quasi_diagonal_order(euclidean_dist)
        sorted_items = [cols[idx] for idx in ordered_indices]

        # ขั้นที่ 3: Recursive Bisection
        weights = pd.Series(1.0, index=sorted_items, dtype=float)
        clustered_items: List[List[str]] = [sorted_items]

        while len(clustered_items) > 0:
            # แยกคลัสเตอร์ที่มีสมาชิกมากกว่า 1 ตัวออกเป็นซ้ายและขวาอย่างละครึ่ง
            next_clusters: List[List[str]] = []
            for cluster in clustered_items:
                if len(cluster) > 1:
                    mid = len(cluster) // 2
                    next_clusters.append(cluster[:mid])
                    next_clusters.append(cluster[mid:])
            clustered_items = next_clusters

            # จัดสรรน้ำหนักระหว่างคู่กิ่งซ้ายและกิ่งขวาตามสัดส่วนผกผันความแปรปรวน
            for i in range(0, len(clustered_items), 2):
                left_items = clustered_items[i]
                right_items = clustered_items[i + 1]

                var_left = self._cluster_variance(cov, left_items)
                var_right = self._cluster_variance(cov, right_items)

                alpha = 1.0 - (var_left / max(var_left + var_right, 1e-12))
                weights[left_items] *= alpha
                weights[right_items] *= (1.0 - alpha)

        return weights.reindex(cols) / weights.sum()

    # ------------------------------------------------------------------
    # 3. การรวมร่าง: HRP + AI Conviction + Regime Cash Buffer
    # ------------------------------------------------------------------
    def allocate_portfolio(
        self,
        price_history_df: pd.DataFrame,
        ai_convictions: Dict[str, float],
        regime_probs: Dict[str, float],
        method: str = "HRP",
    ) -> Dict[str, float]:
        """
        คำนวณสัดส่วนเงินลงทุนสุทธิของแต่ละหุ้นและสัดส่วนเงินสดสำรอง (CASH)
        - price_history_df: ตารางราคาปิดย้อนหลัง (คอลัมน์ = ชื่อหุ้น)
        - ai_convictions: คะแนนความมั่นใจจากสภาบอทของแต่ละหุ้น (คัดเฉพาะตัวที่เป็นบวก)
        - regime_probs: ความน่าจะเป็นของสภาวะตลาดปัจจุบัน
        """
        # คัดเฉพาะหุ้นที่มีคะแนนความมั่นใจเป็นบวก
        active_symbols = [
            sym for sym, score in ai_convictions.items()
            if score > 0.05 and sym in price_history_df.columns
        ]

        if not active_symbols:
            return {"CASH": 1.0}

        recent_prices = price_history_df[active_symbols].tail(self.cov_window + 1)
        returns_df = recent_prices.pct_change().dropna(how="all").fillna(0.0)

        # 1. คำนวณน้ำหนักฐานด้านความเสี่ยง (Risk-Based Base Weights)
        if method.upper() == "HRP" and len(active_symbols) >= 2:
            base_weights = self.compute_hrp_weights(returns_df)
        else:
            base_weights = self.compute_inverse_vol_weights(returns_df)

        # 2. ถ่วงน้ำหนักผสมกับความมั่นใจของสภา AI (Conviction Tilt)
        conviction_series = pd.Series({s: ai_convictions[s] for s in active_symbols})
        tilted_weights = base_weights * conviction_series
        if tilted_weights.sum() <= 0:
            return {"CASH": 1.0}
        tilted_weights /= tilted_weights.sum()

        # 3. คำนวณสัดส่วนการถือหุ้นรวมสูงสุดตามสภาวะตลาด และความผันผวนของพอร์ต
        p_crisis = float(regime_probs.get("HIGH_VOL_CRISIS", 0.0))
        p_sideways = float(regime_probs.get("SIDEWAYS", 0.0))

        # ลดเพดานการถือหุ้นรวมเมื่อตลาดมีความเสี่ยงวิกฤตหรือไซด์เวย์หนัก
        regime_exposure_cap = np.clip(1.0 - (1.20 * p_crisis) - (0.25 * p_sideways), 0.0, 1.0)

        # คำนวณความผันผวนคาดการณ์ของพอร์ตรวม (Ex-Ante Portfolio Volatility)
        cov_matrix = returns_df.cov().values * 252.0
        w_vec = tilted_weights.values
        realized_port_vol = float(np.sqrt(max(w_vec.T @ cov_matrix @ w_vec, 1e-8)))

        # Volatility Scaling Factor: ถ้าพอร์ตเหวี่ยงแรงกว่าเป้าหมาย ให้ลดหน้าตักรวมลงอัตโนมัติ
        vol_scaling_factor = min(1.0, self.target_portfolio_vol / realized_port_vol)
        total_equity_exposure = float(regime_exposure_cap * vol_scaling_factor)

        # 4. คูณสัดส่วนหุ้นรายตัวและบังคับเพดานสูงสุดต่อตัว (Concentration Cap)
        final_weights = (tilted_weights * total_equity_exposure).clip(upper=self.max_single_weight)

        # ตัดหุ้นที่ได้น้ำหนักน้อยเกินไปออกเพื่อไม่ให้เสียค่าคอมมิชชั่นจุกจิก
        final_weights = final_weights[final_weights >= self.min_position_weight]

        allocation: Dict[str, float] = {
            sym: round(float(w), 4) for sym, w in final_weights.items()
        }
        invested_sum = sum(allocation.values())
        allocation["CASH"] = round(max(0.0, 1.0 - invested_sum), 4)

        return allocation


if __name__ == "__main__":
    rng = np.random.default_rng(42)
    dates = pd.bdate_range("2024-01-01", periods=100)
    prices_df = pd.DataFrame({
        "STOCK_UTIL": 30.0 * np.exp(np.cumsum(rng.normal(0.0004, 0.008, 100))),
        "STOCK_ICT": 200.0 * np.exp(np.cumsum(rng.normal(0.0005, 0.010, 100))),
        "STOCK_FIN_1": 45.0 * np.exp(np.cumsum(rng.normal(0.0006, 0.022, 100))),
        "STOCK_FIN_2": 40.0 * np.exp(np.cumsum(rng.normal(0.0006, 0.022, 100))),
    }, index=dates)
    allocator = AdaptivePortfolioAllocator()
    weights = allocator.allocate_portfolio(
        price_history_df=prices_df,
        ai_convictions={"STOCK_UTIL": 0.75, "STOCK_ICT": 0.80, "STOCK_FIN_1": 0.65, "STOCK_FIN_2": 0.65},
        regime_probs={"BULL_TREND": 0.70, "SIDEWAYS": 0.20, "HIGH_VOL_CRISIS": 0.10},
        method="HRP",
    )
    print("=== สัดส่วนการจัดพอร์ตด้วย Hierarchical Risk Parity (HRP) ===")
    for k, v in weights.items():
        print(f"  - {k:<12}: {v * 100.0:>5.2f}%")


