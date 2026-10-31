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
