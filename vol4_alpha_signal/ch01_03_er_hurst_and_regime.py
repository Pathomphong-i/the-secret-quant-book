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

def estimate_hurst_exponent(close: pd.Series, max_lag: int = 20) -> float:
    """คำนวณค่า Hurst Exponent (H) จากความชันระหว่าง log(lag) และ log(std)"""
    log_price = np.log(close.dropna().values)
    if len(log_price) < max_lag * 2:
        return 0.50
    
    lags = np.arange(2, max_lag + 1)
    tau_dispersion = [
        np.std(log_price[lag:] - log_price[:-lag]) for lag in lags
    ]
    poly_fit = np.polyfit(np.log(lags), np.log(tau_dispersion), 1)
    hurst_val = float(np.clip(poly_fit[0], 0.05, 0.95))
    return round(hurst_val, 3)

if __name__ == "__main__":
    np.random.seed(7)
    # จำลองหุ้นนิสัยวิ่งตามเทรนด์ (Momentum / Autocorrelated Returns)
    steps = np.random.normal(0.002, 0.015, 150)
    for i in range(1, len(steps)):
        steps[i] += 0.35 * steps[i - 1]
    trending_stock = pd.Series(100 * np.exp(np.cumsum(steps)))
    
    h_score = estimate_hurst_exponent(trending_stock, max_lag=20)
    style = "TRENDING" if h_score > 0.55 else ("MEAN_REVERT" if h_score < 0.45 else "RANDOM")
    print(f"Hurst Exponent: {h_score:.3f} -> Stock Personality: {style}")


# ==============================================================================

import numpy as np
import pandas as pd

def compute_regime_probabilities(
    breadth: float, atr_zscore: float, index_er20: float
) -> pd.Series:
    """คำนวณความน่าจะเป็นของ 4 สภาวะตลาดด้วย Softmax Scoring Model"""
    score_bull = (
        3.0 * (breadth - 0.55) - 0.8 * max(0.0, atr_zscore) + 2.0 * (index_er20 - 0.30)
    )
    score_pullback = (
        1.5 * (breadth - 0.45) + 0.8 * np.clip(atr_zscore, 0.0, 1.2) - 1.2 * abs(index_er20 - 0.25)
    )
    score_sideways = (
        -2.5 * abs(breadth - 0.45) - 1.0 * abs(atr_zscore) + 2.0 * (0.25 - index_er20)
    )
    score_crisis = (
        3.5 * (0.35 - breadth) + 1.8 * max(0.0, atr_zscore - 1.0)
    )
    
    raw_scores = np.array([score_bull, score_pullback, score_sideways, score_crisis])
    exp_scores = np.exp(raw_scores - np.max(raw_scores))
    probs = exp_scores / np.sum(exp_scores)
    return pd.Series(
        probs.round(3),
        index=["BULL_TREND", "PULLBACK", "SIDEWAYS", "HIGH_VOL_CRISIS"]
    )

if __name__ == "__main__":
    p_bull = compute_regime_probabilities(breadth=0.72, atr_zscore=-0.4, index_er20=0.52)
    p_crisis = compute_regime_probabilities(breadth=0.18, atr_zscore=2.4, index_er20=0.48)
    print("วันตลาดขาขึ้นสดใส:\n", p_bull.to_dict())
    print("วันเกิดวิกฤตตลาดผันผวนสูง:\n", p_crisis.to_dict())


# ==============================================================================

import numpy as np
import pandas as pd

def detect_vcp_compression(df: pd.DataFrame) -> pd.DataFrame:
    """ตรวจจับการบีบตัวของความผันผวน (VCP) ด้วย ATR Ratio และ BB/KC Squeeze"""
    high, low, close = df["high"], df["low"], df["close"]
    prev_close = close.shift(1)
    
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    
    atr_5 = tr.rolling(5).mean()
    atr_20 = tr.rolling(20).mean()
    atr_ratio = (atr_5 / atr_20.replace(0, np.nan)).fillna(1.0)
    
    std_20 = close.rolling(20).std()
    bb_width = 4.0 * std_20
    kc_width = 3.0 * atr_20
    squeeze_ratio = (bb_width / kc_width.replace(0, np.nan)).fillna(1.0)
    
    near_high = close >= (close.rolling(20).max() * 0.96)
    is_vcp_ready = (atr_ratio < 0.75) & (squeeze_ratio < 1.00) & near_high
    
    return pd.DataFrame({
        "close": close, "atr_ratio": atr_ratio.round(3),
        "squeeze_ratio": squeeze_ratio.round(3), "vcp_ready": is_vcp_ready
    })

if __name__ == "__main__":
    np.random.seed(12)
    # จำลองราคาหุ้นที่แกว่งกว้าง 15 วันแรก แล้วบีบตัวแคบลง 10 วันหลังใกล้จุดสูงสุด
    rng = np.concatenate([np.random.uniform(1.5, 2.5, 15), np.random.uniform(0.3, 0.6, 10)])
    c = pd.Series(np.linspace(100, 108, 25))
    sample_df = pd.DataFrame({"high": c + rng, "low": c - rng, "close": c})
    print(detect_vcp_compression(sample_df).tail(5))


