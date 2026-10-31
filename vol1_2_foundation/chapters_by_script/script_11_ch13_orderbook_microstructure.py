from typing import List
import numpy as np
import pandas as pd


def evaluate_walk_forward_matrix(
    equity_returns: pd.Series,
    is_windows_days: List[int] = [252, 378, 504],
    oos_windows_days: List[int] = [63, 126],
) -> pd.DataFrame:
    """
    ฟังก์ชันสร้างตาราง Walk-Forward Efficiency Matrix (WFE)
    เพื่อพิสูจน์ว่าระบบมีความเสถียรในข้อมูลนอกกลุ่มตัวอย่าง (Out-of-Sample) จริงหรือไม่
    """
    records = []
    clean_ret = equity_returns.dropna()

    for is_len in is_windows_days:
        for oos_len in oos_windows_days:
            is_sharpes = []
            oos_sharpes = []
            start_idx = 0

            while start_idx + is_len + oos_len <= len(clean_ret):
                is_slice = clean_ret.iloc[start_idx : start_idx + is_len]
                oos_slice = clean_ret.iloc[start_idx + is_len : start_idx + is_len + oos_len]

                is_std = is_slice.std()
                oos_std = oos_slice.std()

                is_sr = (is_slice.mean() / is_std * np.sqrt(252)) if is_std > 1e-8 else 0.0
                oos_sr = (oos_slice.mean() / oos_std * np.sqrt(252)) if oos_std > 1e-8 else 0.0

                is_sharpes.append(is_sr)
                oos_sharpes.append(oos_sr)
                start_idx += oos_len  # เลื่อนหน้าต่างไปข้างหน้าเท่ากับระยะเวลา OOS

            avg_is_sr = float(np.mean(is_sharpes)) if is_sharpes else 0.0
            avg_oos_sr = float(np.mean(oos_sharpes)) if oos_sharpes else 0.0
            wfe_ratio = (avg_oos_sr / avg_is_sr * 100.0) if avg_is_sr > 0.1 else 0.0
            win_folds_pct = (
                float(np.mean([1.0 if s > 0 else 0.0 for s in oos_sharpes]) * 100.0)
                if oos_sharpes else 0.0
            )

            records.append({
                "IS_Days": is_len,
                "OOS_Days": oos_len,
                "Folds": len(oos_sharpes),
                "Avg_IS_Sharpe": round(avg_is_sr, 2),
                "Avg_OOS_Sharpe": round(avg_oos_sr, 2),
                "WFE_Percent": round(wfe_ratio, 1),
                "Positive_OOS_Folds_%": round(win_folds_pct, 1),
                "Status": "ROBUST_ADAPTIVE" if (wfe_ratio >= 50.0 and win_folds_pct >= 70.0) else "CHECK_OVERFIT",
            })

    return pd.DataFrame(records)


if __name__ == "__main__":
    rng = np.random.default_rng(42)
    sample_rets = pd.Series(rng.normal(0.0008, 0.009, 756))
    print("=== ตารางทดสอบ Walk-Forward Efficiency Matrix (WFE) ===")
    print(evaluate_walk_forward_matrix(sample_rets).to_string(index=False))
