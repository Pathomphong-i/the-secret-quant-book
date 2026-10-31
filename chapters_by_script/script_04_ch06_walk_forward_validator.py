import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Callable, Dict, List, Tuple


@dataclass
class WalkForwardFoldResult:
    fold_id: int
    is_start: pd.Timestamp
    is_end: pd.Timestamp
    oos_start: pd.Timestamp
    oos_end: pd.Timestamp
    chosen_params: Tuple[int, int]
    raw_peak_params: Tuple[int, int]
    is_sharpe: float
    oos_sharpe: float
    is_return_ann: float
    oos_return_ann: float


class WalkForwardValidator:
    """
    ระบบทดสอบ Walk-Forward Validation ที่ถูกต้องและใช้งานได้จริง
    พร้อมอัลกอริทึมค้นหา Parameter Stability Plateau (ป้องกันการเลือก Fragile Peak)
    """

    def __init__(
        self,
        is_window_bars: int = 252,       # In-Sample 1 ปี (252 วันทำการ)
        oos_window_bars: int = 63,       # Out-of-Sample 1 ไตรมาส (63 วันทำการ)
        commission_bps: float = 15.0     # ต้นทุนการเทรดรวมต่อขา (15 bps = 0.15%)
    ):
        self.is_window_bars = is_window_bars
        self.oos_window_bars = oos_window_bars
        self.cost_rate = commission_bps / 10_000.0

    @staticmethod
    def _compute_metrics(daily_returns: pd.Series) -> Tuple[float, float]:
        """คำนวณ Annualized Return และ Annualized Sharpe Ratio"""
        if len(daily_returns) < 5 or daily_returns.std() == 0:
            return 0.0, 0.0
        ann_return = float(daily_returns.mean() * 252)
        ann_vol = float(daily_returns.std() * np.sqrt(252))
        sharpe = ann_return / ann_vol if ann_vol > 1e-8 else 0.0
        return ann_return, sharpe

    def evaluate_strategy(
        self,
        df: pd.DataFrame,
        fast_window: int,
        slow_window: int
    ) -> pd.Series:
        """
        ตัวอย่างกลยุทธ์ Trend Breakout / Volatility-Adjusted Momentum
        บังคับ .shift(1) เพื่อป้องกัน Look-Ahead Bias และหักค่าธรรมเนียมเมื่อเปลี่ยนสถานะ
        """
        if fast_window >= slow_window:
            return pd.Series(0.0, index=df.index)

        close = df['close']
        ema_fast = close.ewm(span=fast_window, adjust=False).mean()
        ema_slow = close.ewm(span=slow_window, adjust=False).mean()

        # สัญญาณเกิดเมื่อจบแท่ง t และเข้าถือครองจริงในแท่ง t+1 (.shift(1))
        raw_signal = (ema_fast > ema_slow).astype(float)
        position = raw_signal.shift(1).fillna(0.0)

        # คำนวณการเปลี่ยนสถานะ (Turnover) เพื่อหักค่าคอมมิชชันและ Slippage
        trades = position.diff().abs().fillna(0.0)
        asset_returns = close.pct_change().fillna(0.0)

        net_returns = (position * asset_returns) - (trades * self.cost_rate)
        return net_returns

    def find_stability_plateau_params(
        self,
        is_df: pd.DataFrame,
        fast_grid: List[int],
        slow_grid: List[int]
    ) -> Tuple[Tuple[int, int], Tuple[int, int], float]:
        """
        ค้นหาพารามิเตอร์ด้วยวิธี Parameter Stability Plateau:
        แทนที่จะเลือกจุดที่มี Sharpe สูงสุดโดดๆ (ซึ่งมักเกิดจาก Curve Fitting)
        เราจะคำนวณค่าเฉลี่ยถ่วงน้ำหนักร่วมกับจุดรอบข้าง (3x3 Neighborhood Plateau Score)
        และลงโทษจุดที่มีความแปรปรวนกับเพื่อนบ้านสูง (Cliff Penalty)
        """
        n_fast = len(fast_grid)
        n_slow = len(slow_grid)
        sharpe_matrix = np.full((n_fast, n_slow), np.nan)

        for i, f_win in enumerate(fast_grid):
            for j, s_win in enumerate(slow_grid):
                if f_win >= s_win:
                    continue
                rets = self.evaluate_strategy(is_df, f_win, s_win)
                _, sharpe = self._compute_metrics(rets)
                sharpe_matrix[i, j] = sharpe

        # 1. หาจุดสูงสุดดิบ (Raw Peak - แบบที่มือใหม่ชอบเลือก)
        raw_idx = np.nanargmax(sharpe_matrix)
        raw_i, raw_j = np.unravel_index(raw_idx, sharpe_matrix.shape)
        raw_peak_params = (fast_grid[raw_i], slow_grid[raw_j])

        # 2. คำนวณคะแนน Stability Plateau (เฉลี่ย 3x3 รอบจุดตัวเอง หักลบด้วยความผันผวนของเพื่อนบ้าน)
        plateau_score_matrix = np.full((n_fast, n_slow), -np.inf)

        for i in range(n_fast):
            for j in range(n_slow):
                if np.isnan(sharpe_matrix[i, j]):
                    continue
                i_min, i_max = max(0, i - 1), min(n_fast, i + 2)
                j_min, j_max = max(0, j - 1), min(n_slow, j + 2)
                neighborhood = sharpe_matrix[i_min:i_max, j_min:j_max]
                valid_neighbors = neighborhood[~np.isnan(neighborhood)]

                if len(valid_neighbors) >= 3:
                    neighbor_mean = float(np.mean(valid_neighbors))
                    neighbor_std = float(np.std(valid_neighbors))
                    # สูตร Plateau Score: ให้รางวัลค่าเฉลี่ยกลุ่มสูง และลงโทษจุดที่โดดเดี่ยวหรืออยู่ริมหน้าผา
                    plateau_score_matrix[i, j] = neighbor_mean - (0.5 * neighbor_std)

        best_idx = np.argmax(plateau_score_matrix)
        best_i, best_j = np.unravel_index(best_idx, plateau_score_matrix.shape)
        chosen_params = (fast_grid[best_i], slow_grid[best_j])
        chosen_is_sharpe = float(sharpe_matrix[best_i, best_j])

        return chosen_params, raw_peak_params, chosen_is_sharpe

    def run_walk_forward(
        self,
        df: pd.DataFrame,
        fast_grid: List[int],
        slow_grid: List[int]
    ) -> Tuple[pd.DataFrame, pd.Series, Dict[str, float]]:
        """
        รัน Rolling Walk-Forward Analysis ตลอดชุดข้อมูล
        และคืนค่าตารางสรุปแต่ละ Fold, เส้นผลตอบแทน OOS ต่อเนื่อง, และค่าสถิติ WFE
        """
        total_bars = len(df)
        min_required = self.is_window_bars + self.oos_window_bars
        if total_bars < min_required:
            raise ValueError(f"จำนวนข้อมูล ({total_bars}) น้อยกว่าขั้นต่ำที่ต้องการ ({min_required})")

        fold_results: List[WalkForwardFoldResult] = []
        oos_return_segments: List[pd.Series] = []

        start_idx = 0
        fold_id = 1

        while start_idx + self.is_window_bars + self.oos_window_bars <= total_bars:
            is_end_idx = start_idx + self.is_window_bars
            oos_end_idx = is_end_idx + self.oos_window_bars

            is_slice = df.iloc[start_idx:is_end_idx]
            # ดึงข้อมูลก่อนหน้า OOS เล็กน้อยเป็น Warm-up สำหรับคำนวณ EMA ต่อเนื่องโดยไม่เกิด NaN
            warmup_lookback = max(slow_grid) + 5
            oos_with_warmup = df.iloc[max(0, is_end_idx - warmup_lookback) : oos_end_idx]
            oos_target_index = df.iloc[is_end_idx:oos_end_idx].index

            # ค้นหาพารามิเตอร์บนที่ราบสูง (Plateau) จากเฉพาะข้อมูล In-Sample เท่านั้น!
            chosen_params, raw_peak_params, _ = self.find_stability_plateau_params(
                is_slice, fast_grid, slow_grid
            )

            # วัดผลใน In-Sample
            is_rets = self.evaluate_strategy(is_slice, chosen_params[0], chosen_params[1])
            is_ann_ret, is_sharpe = self._compute_metrics(is_rets)

            # นำพารามิเตอร์ที่เลือกไปทดสอบเดินหน้าใน Out-of-Sample (ห้ามปรับแก้!)
            oos_full_rets = self.evaluate_strategy(oos_with_warmup, chosen_params[0], chosen_params[1])
            oos_rets = oos_full_rets.loc[oos_target_index]
            oos_ann_ret, oos_sharpe = self._compute_metrics(oos_rets)

            oos_return_segments.append(oos_rets)

            fold_results.append(
                WalkForwardFoldResult(
                    fold_id=fold_id,
                    is_start=is_slice.index[0],
                    is_end=is_slice.index[-1],
                    oos_start=oos_target_index[0],
                    oos_end=oos_target_index[-1],
                    chosen_params=chosen_params,
                    raw_peak_params=raw_peak_params,
                    is_sharpe=round(is_sharpe, 3),
                    oos_sharpe=round(oos_sharpe, 3),
                    is_return_ann=round(is_ann_ret * 100, 2),
                    oos_return_ann=round(oos_ann_ret * 100, 2)
                )
            )

            start_idx += self.oos_window_bars
            fold_id += 1

        stitched_oos_returns = pd.concat(oos_return_segments)
        stitched_equity = (1.0 + stitched_oos_returns).cumprod()

        summary_df = pd.DataFrame([vars(f) for f in fold_results])

        mean_is_ret = summary_df['is_return_ann'].mean()
        mean_oos_ret = summary_df['oos_return_ann'].mean()
        mean_is_sharpe = summary_df['is_sharpe'].mean()
        mean_oos_sharpe = summary_df['oos_sharpe'].mean()

        wfe_pct = (mean_oos_ret / mean_is_ret * 100.0) if mean_is_ret > 0 else 0.0
        sharpe_retention_pct = (mean_oos_sharpe / mean_is_sharpe * 100.0) if mean_is_sharpe > 0 else 0.0

        diagnostics = {
            "total_folds": len(fold_results),
            "mean_is_sharpe": round(float(mean_is_sharpe), 3),
            "mean_oos_sharpe": round(float(mean_oos_sharpe), 3),
            "sharpe_retention_pct": round(float(sharpe_retention_pct), 2),
            "walk_forward_efficiency_pct": round(float(wfe_pct), 2),
            "positive_oos_folds_pct": round(float((summary_df['oos_return_ann'] > 0).mean() * 100), 1)
        }

        return summary_df, stitched_equity, diagnostics


# =====================================================================
# ตัวอย่างการรัน Walk-Forward Validation
# =====================================================================
if __name__ == "__main__":
    np.random.seed(7)
    # จำลองข้อมูลราคา 4 ปี (ประมาณ 1,008 วันทำการ) ที่มีทั้งช่วงเทรนด์และช่วงพักตัว
    n_days = 1008
    dates = pd.date_range("2021-01-01", periods=n_days, freq="B")
    regime_drift = np.where(np.sin(np.linspace(0, 6 * np.pi, n_days)) > -0.3, 0.0012, -0.0008)
    daily_noise = np.random.normal(0, 0.014, n_days)
    prices = 100 * np.cumprod(1 + regime_drift + daily_noise)

    market_df = pd.DataFrame({'close': prices}, index=dates)

    validator = WalkForwardValidator(is_window_bars=252, oos_window_bars=63)
    fast_candidates = [8, 12, 16, 20, 24, 28]
    slow_candidates = [40, 50, 60, 70, 80, 90, 100]

    folds_table, oos_equity, report = validator.run_walk_forward(
        market_df, fast_candidates, slow_candidates
    )

    print("=== สรุปผลการทดสอบ Walk-Forward รายหน้าต่าง (Fold) ===")
    print(folds_table[['fold_id', 'chosen_params', 'raw_peak_params', 'is_sharpe', 'oos_sharpe']])
    print("\n=== ดัชนีชี้วัดความทนทานของระบบ (Systematic Robustness Report) ===")
    for k, v in report.items():
        print(f"  - {k}: {v}")
