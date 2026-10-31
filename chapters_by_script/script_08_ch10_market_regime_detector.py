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
