from __future__ import annotations
# ==============================================================================
# หนังสือ: เลิกพึ่งบอทคนอื่น มาสร้างระบบเทรดของคุณเองด้วย Python: วิเคราะห์หุ้นและสร้างระบบอย่างมีวินัย
# ผู้เขียน: ปฐมพงษ์ พิพัฒน์สุริยวงศ์
# คำเตือน: เนื้อหาและโค้ดในไฟล์นี้จัดทำขึ้นเพื่อการศึกษาและเป็นความคิดเห็นส่วนตัวของผู้เขียนเท่านั้น
#         มิใช่การแนะนำการลงทุน ผู้ลงทุนโปรดศึกษาข้อมูลและความเสี่ยงด้วยตนเอง
# ==============================================================================

"""บทที่ 5–6: ท่อทดสอบ Point-in-Time Backtest ป้องกัน Look-Ahead Bias และ Walk-Forward Validation"""

# --- Source: script_03.py ---
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple


@dataclass
class BacktestConfig:
    initial_capital: float = 1_000_000.0
    commission_pct: float = 0.0015      # ค่าธรรมเนียมซื้อขาย 0.15%
    slippage_bps: float = 10.0          # Slippage 10 basis points (0.10%)
    delist_haircut_pct: float = 0.85    # กรณีหุ้นถูกเพิกถอนกะทันหัน สมมติสูญเสียมูลค่า 85%
    pessimistic_intrabar: bool = True   # หากชนทั้ง SL และ TP ในแท่งเดียวกัน ให้ถือว่าโดน SL ก่อน


class LookAheadBiasAuditor:
    """
    ระบบตรวจสอบ Look-Ahead Bias อัตโนมัติด้วยวิธี Future Perturbation Test (Causality Check)
    มาตรฐานเดียวกับที่ใช้ตรวจสอบ Pipeline ของนักวิจัยในกองทุน Quantitative
    """

    @staticmethod
    def verify_signal_causality(
        df: pd.DataFrame,
        signal_func: Callable[[pd.DataFrame], pd.Series],
        check_points: int = 5,
        tolerance: float = 1e-9
    ) -> Tuple[bool, str]:
        """
        ทดสอบว่าฟังก์ชันสร้างสัญญาณ (signal_func) แอบใช้ข้อมูลอนาคตหรือไม่
        โดยการตัดข้อมูลและสุ่มป่วนข้อมูลหลังจุดเวลา t แล้วตรวจว่าผลลัพธ์ก่อนเวลา t เปลี่ยนหรือไม่
        """
        if len(df) < 30:
            raise ValueError("ข้อมูลสั้นเกินไปสำหรับการตรวจสอบ Causality (ต้องการอย่างน้อย 30 แท่ง)")

        # 1. คำนวณสัญญาณจากชุดข้อมูลเต็ม
        full_signals = signal_func(df.copy())

        # 2. สุ่มจุดเวลา t เพื่อทดสอบว่าข้อมูลหลัง t มีผลต่อสัญญาณ ณ เวลา <= t หรือไม่
        indices = np.linspace(int(len(df) * 0.3), int(len(df) * 0.85), check_points, dtype=int)

        for idx in indices:
            cutoff_time = df.index[idx]

            # ทดสอบที่ 1: ตัดข้อมูลอนาคตทิ้งทั้งหมด (Strict Truncation)
            truncated_df = df.iloc[: idx + 1].copy()
            truncated_signals = signal_func(truncated_df)

            orig_slice = full_signals.iloc[: idx + 1]
            # เปรียบเทียบเฉพาะค่าที่ไม่ใช่ NaN
            valid_mask = ~(orig_slice.isna() & truncated_signals.isna())
            if valid_mask.any():
                diff_trunc = np.abs(
                    orig_slice[valid_mask].fillna(-999999) - truncated_signals[valid_mask].fillna(-999999)
                ).max()
                if diff_trunc > tolerance:
                    return (
                        False,
                        f"[FAILED - Truncation Leak] พบ Look-Ahead Bias ณ เวลา {cutoff_time}: "
                        f"ค่าสัญญาณเปลี่ยนไป {diff_trunc:.6f} เมื่อตัดข้อมูลอนาคตออก!"
                    )

            # ทดสอบที่ 2: ป่วนข้อมูลในอนาคตอย่างรุนแรง (Future Shock Perturbation)
            perturbed_df = df.copy()
            numeric_cols = perturbed_df.select_dtypes(include=[np.number]).columns
            perturbed_df[numeric_cols] = perturbed_df[numeric_cols].astype(float)
            perturbed_df.iloc[idx + 1 :, perturbed_df.columns.get_loc(numeric_cols[0])] *= 50.0
            for col in numeric_cols:
                perturbed_df.loc[perturbed_df.index[idx + 1 :], col] *= np.random.uniform(0.1, 10.0)

            perturbed_signals = signal_func(perturbed_df)
            perturbed_slice = perturbed_signals.iloc[: idx + 1]

            if valid_mask.any():
                diff_perturb = np.abs(
                    orig_slice[valid_mask].fillna(-999999) - perturbed_slice[valid_mask].fillna(-999999)
                ).max()
                if diff_perturb > tolerance:
                    return (
                        False,
                        f"[FAILED - Perturbation Leak] พบ Look-Ahead Bias ณ เวลา {cutoff_time}: "
                        f"ข้อมูลหลังเวลา {cutoff_time} ส่งผลย้อนกลับมาเปลี่ยนสัญญาณในอดีต ({diff_perturb:.6f})!"
                    )

        return True, "[PASSED] ไม่พบ Look-Ahead Bias: ฟังก์ชันสร้างสัญญาณเคารพกฎแห่งเวลา (Strictly Causal) 100%"


class PointInTimeBacktestEngine:
    """
    เอนจินจำลองการเทรดแบบ Point-in-Time ที่ป้องกัน:
    1. Same-bar execution bias (บังคับคำนวณสัญญาณจบแท่ง t และส่งคำสั่งที่ Open ของแท่ง t+1)
    2. Survivorship bias (ตรวจสอบสถานะ is_active_in_universe และ is_delisted รายวัน)
    3. Optimistic intra-bar bias (ตรวจสอบ Stop Loss ก่อน Take Profit ในแท่งเดียวกัน)
    """

    def __init__(self, config: Optional[BacktestConfig] = None):
        self.config = config or BacktestConfig()

    def run_single_asset(
        self,
        df: pd.DataFrame,
        signal_func: Callable[[pd.DataFrame], pd.Series],
        stop_loss_pct: float = 0.05,
        take_profit_pct: float = 0.12
    ) -> pd.DataFrame:
        """
        รัน Backtest รายแท่งเทียนหลังผ่านการตรวจ Look-Ahead Bias แล้ว
        DataFrame ต้องมีคอลัมน์: ['open', 'high', 'low', 'close', 'volume']
        และสามารถมีคอลัมน์เสริมเพื่อป้องกัน Survivorship Bias:
        - 'in_universe': bool (หุ้นอยู่ในดัชนี ณ วันนั้นจริงหรือไม่)
        - 'is_delisted': bool (หุ้นถูกเพิกถอนหรือขึ้นเครื่องหมายห้ามซื้อขายถาวรในวันนั้นหรือไม่)
        """
        # ขั้นตอนที่ 1: ตรวจสอบ Look-Ahead Bias ของฟังก์ชันสัญญาณก่อนอนุญาตให้รัน
        passed, audit_msg = LookAheadBiasAuditor.verify_signal_causality(df, signal_func)
        if not passed:
            raise RuntimeError(f"Backtest ถูกระงับโดยระบบตรวจสอบความเสี่ยง!\nรายละเอียด: {audit_msg}")

        data = df.copy()
        data['raw_signal'] = signal_func(data)
        if 'in_universe' not in data.columns:
            data['in_universe'] = True
        if 'is_delisted' not in data.columns:
            data['is_delisted'] = False

        # ขั้นตอนที่ 2: เลื่อนสัญญาณไป 1 แท่ง (สัญญาณเกิดจาก Close[t-1] เพื่อตัดสินใจซื้อที่ Open[t])
        data['actionable_signal'] = data['raw_signal'].shift(1).fillna(0)
        data['universe_eligible'] = data['in_universe'].shift(1).fillna(False)

        capital = self.config.initial_capital
        shares = 0.0
        entry_price = 0.0
        slippage_rate = self.config.slippage_bps / 10_000.0

        records = []

        for timestamp, row in data.iterrows():
            open_p, high_p, low_p, close_p = row['open'], row['high'], row['low'], row['close']
            sig = row['actionable_signal']
            eligible = row['universe_eligible']
            delisted = row['is_delisted']

            daily_event = "HOLD"

            # กรณีถือหุ้นอยู่: ต้องตรวจสอบเหตุการณ์ไม่คาดฝันและจุดออก (Exit) ก่อนเสมอ
            if shares > 0:
                # 1. ตรวจสอบกรณีหุ้นถูก Delist / ขึ้น SP ยาว (Survivorship Bias Reality)
                if delisted:
                    liquidation_price = close_p * (1.0 - self.config.delist_haircut_pct)
                    proceeds = shares * liquidation_price * (1.0 - self.config.commission_pct)
                    capital += proceeds
                    shares = 0.0
                    entry_price = 0.0
                    daily_event = "FORCED_DELIST_EXIT"
                else:
                    sl_price = entry_price * (1.0 - stop_loss_pct)
                    tp_price = entry_price * (1.0 + take_profit_pct)

                    hit_sl = low_p <= sl_price
                    hit_tp = high_p >= tp_price

                    exit_exec_price = None

                    # 2. ตรวจสอบ Gap Down ทะลุ Stop Loss ตั้งแต่วินาทีเปิดตลาด (ได้ราคา Open ที่แย่กว่า SL!)
                    if open_p <= sl_price:
                        exit_exec_price = open_p * (1.0 - slippage_rate)
                        daily_event = "GAP_DOWN_STOP_LOSS"
                    # 3. หากชนทั้ง SL และ TP ในแท่งเดียวกัน ใช้ Pessimistic Assumption
                    elif hit_sl and hit_tp:
                        if self.config.pessimistic_intrabar:
                            exit_exec_price = sl_price * (1.0 - slippage_rate)
                            daily_event = "PESSIMISTIC_INTRABAR_SL"
                        else:
                            exit_exec_price = tp_price * (1.0 - slippage_rate)
                            daily_event = "OPTIMISTIC_INTRABAR_TP"
                    elif hit_sl:
                        exit_exec_price = sl_price * (1.0 - slippage_rate)
                        daily_event = "STOP_LOSS"
                    elif hit_tp:
                        exit_exec_price = tp_price * (1.0 - slippage_rate)
                        daily_event = "TAKE_PROFIT"
                    elif sig <= 0:
                        # สัญญาณสั่งขายเมื่อจบแท่งก่อนหน้า -> ขายที่ราคาเปิดของแท่งปัจจุบัน
                        exit_exec_price = open_p * (1.0 - slippage_rate)
                        daily_event = "SIGNAL_EXIT_AT_OPEN"

                    if exit_exec_price is not None:
                        proceeds = shares * exit_exec_price * (1.0 - self.config.commission_pct)
                        capital += proceeds
                        shares = 0.0
                        entry_price = 0.0

            # กรณีไม่มีหุ้นในมือ และมีสัญญาณซื้อจากเมื่อวาน + หุ้นอยู่ใน Universe ณ เมื่อวานจริง
            elif shares == 0 and sig > 0 and eligible and not delisted:
                buy_exec_price = open_p * (1.0 + slippage_rate)
                investable_cash = capital / (1.0 + self.config.commission_pct)
                shares = investable_cash / buy_exec_price
                capital = 0.0
                entry_price = buy_exec_price
                daily_event = "BUY_AT_NEXT_OPEN"

            # คำนวณมูลค่าพอร์ตสุทธิ ณ สิ้นวัน (Mark-to-Market)
            equity = capital + (shares * close_p)
            records.append({
                'timestamp': timestamp,
                'equity': equity,
                'shares': shares,
                'event': daily_event
            })

        return pd.DataFrame(records).set_index('timestamp')


# =====================================================================
# ตัวอย่างการทดสอบ: เปรียบเทียบฟังก์ชันที่โกงอนาคต vs ฟังก์ชันที่ถูกต้อง
# =====================================================================
if __name__ == "__main__":
    np.random.seed(42)
    dates = pd.date_range("2022-01-01", periods=100, freq="B")
    close_prices = 100 * np.cumprod(1 + np.random.normal(0.0005, 0.02, len(dates)))
    sample_df = pd.DataFrame({
        'open': close_prices * np.random.uniform(0.99, 1.01, len(dates)),
        'high': close_prices * np.random.uniform(1.01, 1.03, len(dates)),
        'low': close_prices * np.random.uniform(0.97, 0.99, len(dates)),
        'close': close_prices,
        'volume': np.random.randint(100_000, 1_000_000, len(dates))
    }, index=dates)

    # 1. ฟังก์ชันที่แอบมี Look-Ahead Bias (ใช้ค่าเฉลี่ยของทั้งตารางมา Normalize)
    def leaky_signal(d: pd.DataFrame) -> pd.Series:
        full_mean = d['close'].mean()  # <-- รู้อนาคตของทั้งตาราง!
        full_std = d['close'].std()
        z_score = (d['close'] - full_mean) / full_std
        return (z_score < -1.0).astype(float)

    # 2. ฟังก์ชันที่ถูกต้องตามหลัก Point-in-Time (ใช้เฉพาะ Rolling 20 วันย้อนหลัง)
    def causal_signal(d: pd.DataFrame) -> pd.Series:
        roll_mean = d['close'].rolling(window=20, min_periods=20).mean()
        roll_std = d['close'].rolling(window=20, min_periods=20).std()
        z_score = (d['close'] - roll_mean) / roll_std
        return (z_score < -1.0).astype(float)

    print("1) ตรวจสอบฟังก์ชัน leaky_signal:")
    ok1, msg1 = LookAheadBiasAuditor.verify_signal_causality(sample_df, leaky_signal)
    print("   ผลลัพธ์:", msg1)

    print("\n2) ตรวจสอบฟังก์ชัน causal_signal:")
    ok2, msg2 = LookAheadBiasAuditor.verify_signal_causality(sample_df, causal_signal)
    print("   ผลลัพธ์:", msg2)


# --- Source: script_04.py ---
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


