#!/usr/bin/env python3
"""
หนังสือ: เลิกพึ่งบอทคนอื่น มาสร้างระบบเทรดของคุณเองด้วย Python
บทที่ 4: สัญญาณเทคนิคเชิงสถิติและการตรวจจับสภาวะตลาด (The Alpha & Technical Signal Engine)
ผู้เขียน: ปฐมพงษ์ พิพัฒน์สุริยวงศ์
รวมซอร์สโค้ดครบทุกหัวข้อประจำบทที่ 4 พร้อมรันทดสอบได้ทันที
"""

from __future__ import annotations
import json, math, os, sqlite3, hashlib
import numpy as np
import pandas as pd

import numpy as np
import pandas as pd

def compute_efficiency_ratio_and_snr(close: pd.Series) -> pd.DataFrame:
    """คำนวณ Kaufman Efficiency Ratio (10d, 20d) และ Signal-to-Noise Ratio"""
    daily_abs_change = close.diff().abs()
    
    dir_10 = (close - close.shift(10)).abs()
    vol_10 = daily_abs_change.rolling(window=10).sum()
    er_10 = (dir_10 / vol_10.replace(0, np.nan)).fillna(0.0)
    
    dir_20 = (close - close.shift(20)).abs()
    vol_20 = daily_abs_change.rolling(window=20).sum()
    er_20 = (dir_20 / vol_20.replace(0, np.nan)).fillna(0.0)
    
    snr_10 = er_10 / (1.0 - er_10 + 1e-6)
    regime_label = np.where(
        er_10 >= 0.45, "CLEAN_TREND",
        np.where(er_10 >= 0.25, "MODERATE_TREND", "NOISY_CHOP")
    )
    return pd.DataFrame({
        "close": close, "er_10": er_10.round(3),
        "er_20": er_20.round(3), "snr_10": snr_10.round(2),
        "trend_quality": regime_label
    })

if __name__ == "__main__":
    np.random.seed(42)
    trend_prices = pd.Series(100 + np.cumsum(np.random.normal(0.8, 0.9, 30)))
    df_er = compute_efficiency_ratio_and_snr(trend_prices)
    print(df_er.tail(5))


# ==============================================================================

import numpy as np
import pandas as pd

def evaluate_rvol_and_clv_breakout(df: pd.DataFrame) -> pd.DataFrame:
    """ตรวจสอบคุณภาพการเบรกเอาต์ด้วย RVOL >= 1.5 และ CLV >= 0.65"""
    high, low, close, vol = df["high"], df["low"], df["close"], df["volume"]
    
    avg_vol_20 = vol.shift(1).rolling(20).mean()
    rvol = (vol / avg_vol_20.replace(0, np.nan)).fillna(1.0)
    
    candle_range = (high - low).replace(0, np.nan)
    clv = ((close - low) / candle_range).fillna(0.5)
    
    resistance_20 = high.shift(1).rolling(20).max()
    price_breakout = close > resistance_20
    
    signal_type = np.where(
        price_breakout & (rvol >= 1.50) & (clv >= 0.65), "GENUINE_BREAKOUT",
        np.where(
            (high > resistance_20) & (rvol >= 1.50) & (clv < 0.40), "FAKEOUT_TRAP",
            np.where(price_breakout & (rvol < 1.20), "LOW_VOL_BREAKOUT", "NEUTRAL")
        )
    )
    return pd.DataFrame({
        "close": close, "rvol": rvol.round(2),
        "clv": clv.round(2), "breakout_status": signal_type
    })

if __name__ == "__main__":
    np.random.seed(5)
    df_sample = pd.DataFrame({
        "high": [10.2]*20 + [10.8, 10.9], "low": [9.8]*20 + [10.1, 10.0],
        "close": [10.0]*20 + [10.75, 10.15], "volume": [1000]*20 + [2200, 2500]
    })
    print(evaluate_rvol_and_clv_breakout(df_sample).tail(3))


# ==============================================================================

import numpy as np
import pandas as pd

def detect_pocket_pivot_accumulation(df: pd.DataFrame) -> pd.DataFrame:
    """คำนวณ Up/Down Volume Ratio (20d) และตรวจจับสัญญาณซื้อล่วงหน้า Pocket Pivot"""
    close, high, low, vol = df["close"], df["high"], df["low"], df["volume"]
    price_diff = close.diff()
    
    up_vol = np.where(price_diff > 0, vol, 0.0)
    down_vol = np.where(price_diff < 0, vol, 0.0)
    
    udvr_20 = (
        pd.Series(up_vol, index=df.index).rolling(20).sum() /
        pd.Series(down_vol, index=df.index).rolling(20).sum().replace(0, np.nan)
    ).fillna(1.0)
    
    max_down_vol_10 = pd.Series(down_vol, index=df.index).shift(1).rolling(10).max()
    clv = ((close - low) / (high - low).replace(0, np.nan)).fillna(0.5)
    sma_20 = close.rolling(20).mean()
    
    is_pocket_pivot = (
        (price_diff > 0) &
        (vol > max_down_vol_10) &
        (udvr_20 >= 1.25) &
        (clv >= 0.60) &
        (close >= sma_20 * 0.98)
    )
    return pd.DataFrame({
        "close": close, "vol": vol, "udvr_20": udvr_20.round(2),
        "max_down_vol_10": max_down_vol_10, "pocket_pivot": is_pocket_pivot
    })

if __name__ == "__main__":
    np.random.seed(18)
    c = pd.Series([10.0, 9.9, 10.1, 10.0, 10.2, 10.1, 10.2, 10.1, 10.3, 10.2]*2 + [10.45])
    v = pd.Series([800, 600, 1100, 500, 1200, 450, 950, 400, 1300, 550]*2 + [1650])
    df_pp = pd.DataFrame({"close": c, "high": c + 0.1, "low": c - 0.1, "volume": v})
    print(detect_pocket_pivot_accumulation(df_pp).tail(3))


# ==============================================================================

import numpy as np
import pandas as pd

def check_post_breakout_follow_through(
    post_closes: list[float],
    breakout_close: float,
    breakout_low: float,
    pivot_resistance: float,
    atr_14: float
) -> dict:
    """ประเมินแรงส่ง 3 วันแรกหลังเบรกเอาต์และตรวจจับ Failed Breakout"""
    latest_close = post_closes[-1]
    min_close = min(post_closes)
    thrust_ratio = (latest_close - breakout_close) / max(atr_14, 1e-6)
    
    failed_pivot = min_close < (pivot_resistance - 0.25 * atr_14)
    failed_low = min_close < breakout_low
    
    if failed_pivot or failed_low:
        status = "FAILED_BREAKOUT_EXIT_ALL"
        recommended_stop = latest_close
    elif thrust_ratio >= 0.75:
        status = "STRONG_FOLLOW_THROUGH_HOLD"
        recommended_stop = max(breakout_close, pivot_resistance)
    else:
        status = "NORMAL_DIGESTION_KEEP_STOP"
        recommended_stop = breakout_low
        
    return {
        "days_tracked": len(post_closes),
        "latest_close": round(latest_close, 2),
        "thrust_ratio_atr": round(thrust_ratio, 2),
        "status": status,
        "recommended_stop": round(recommended_stop, 2)
    }

if __name__ == "__main__":
    # กรณีที่ 1: หุ้นเบรกเอาต์ที่ 50.0 (แนวต้าน 49.5, Low 48.8, ATR 1.2) แล้ววิ่งต่อ 3 วัน
    res_good = check_post_breakout_follow_through([50.5, 50.8, 51.4], 50.0, 48.8, 49.5, 1.2)
    # กรณีที่ 2: หุ้นเบรกเอาต์แล้วโดนตบหลุดกลับเข้ากรอบเดิมในวันที่ 2
    res_fail = check_post_breakout_follow_through([49.8, 48.6], 50.0, 48.8, 49.5, 1.2)
    print("Case 1 (Good):", res_good)
    print("Case 2 (Fail):", res_fail)


