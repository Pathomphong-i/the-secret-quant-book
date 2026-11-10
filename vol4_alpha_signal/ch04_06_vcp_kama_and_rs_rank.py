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

def compute_kama_and_atr_slope(
    df: pd.DataFrame, er_period: int = 10, fast: int = 2, slow: int = 30
) -> pd.DataFrame:
    """คำนวณเส้นค่าเฉลี่ยเปลี่ยนเกียร์อัตโนมัติ (KAMA) และความชันเทียบ ATR"""
    close, high, low = df["close"], df["high"], df["low"]
    direction = (close - close.shift(er_period)).abs()
    volatility = close.diff().abs().rolling(er_period).sum()
    er = (direction / volatility.replace(0, np.nan)).fillna(0.0)
    
    sc_fast, sc_slow = 2.0 / (fast + 1.0), 2.0 / (slow + 1.0)
    sc = (er * (sc_fast - sc_slow) + sc_slow) ** 2
    
    kama = np.zeros(len(close))
    kama[:] = np.nan
    first_valid = er_period
    if len(close) > first_valid:
        kama[first_valid] = close.iloc[first_valid]
        for i in range(first_valid + 1, len(close)):
            kama[i] = kama[i - 1] + sc.iloc[i] * (close.iloc[i] - kama[i - 1])
            
    kama_series = pd.Series(kama, index=df.index)
    atr_14 = (high - low).rolling(14).mean()
    norm_slope = (kama_series - kama_series.shift(5)) / (5.0 * atr_14.replace(0, np.nan))
    
    return pd.DataFrame({
        "close": close, "kama": kama_series.round(2),
        "er": er.round(3), "norm_atr_slope": norm_slope.round(3)
    })

if __name__ == "__main__":
    np.random.seed(99)
    c = pd.Series(100 + np.cumsum(np.concatenate([np.random.normal(0, 0.5, 15), np.random.normal(1.2, 0.4, 15)])))
    sample_df = pd.DataFrame({"close": c, "high": c + 0.8, "low": c - 0.8})
    print(compute_kama_and_atr_slope(sample_df).tail(5))


# ==============================================================================

import numpy as np
import pandas as pd

def rank_cross_sectional_rs(
    stock_prices: pd.DataFrame,
    benchmark_price: pd.Series,
    min_valid_bars: int = 120,
    min_universe_size: int = 10,
) -> pd.DataFrame:
    """คำนวณและจัดอันดับ Risk-Adjusted Relative Strength (20d, 60d, 120d) พร้อมกรองจำนวนแท่งขั้นต่ำ"""
    valid_counts = stock_prices.notna().sum()
    eligible_cols = valid_counts[valid_counts >= min_valid_bars].index
    filtered_prices = stock_prices[eligible_cols]
    if filtered_prices.empty:
        return pd.DataFrame(columns=["ret_20d_%", "composite_rs", "rs_rating", "valid_bars", "is_statistically_valid_universe"])

    daily_ret = filtered_prices.pct_change(fill_method=None)
    horizons = {20: 0.50, 60: 0.30, 120: 0.20}
    composite_score = pd.Series(0.0, index=filtered_prices.columns)
    valid_weight_sum = pd.Series(0.0, index=filtered_prices.columns)

    for h, weight in horizons.items():
        if len(filtered_prices) < h or len(benchmark_price.dropna()) < h:
            continue
        stock_ret_h = filtered_prices.iloc[-1] / filtered_prices.iloc[-h] - 1.0
        bench_ret_h = benchmark_price.iloc[-1] / benchmark_price.iloc[-h] - 1.0
        excess_ret = stock_ret_h - bench_ret_h

        vol_h = daily_ret.tail(h).std() * np.sqrt(h)
        rs_h = excess_ret / vol_h.replace(0, np.nan)
        valid_mask = rs_h.notna()
        composite_score[valid_mask] += weight * rs_h[valid_mask]
        valid_weight_sum[valid_mask] += weight

    composite_score = composite_score / valid_weight_sum.replace(0, np.nan)
    rs_percentile = (composite_score.rank(pct=True) * 100.0).round(1)
    is_valid_univ = len(eligible_cols) >= min_universe_size

    result = pd.DataFrame({
        "ret_20d_%": ((filtered_prices.iloc[-1] / filtered_prices.iloc[-20] - 1) * 100).round(2),
        "composite_rs": composite_score.round(3),
        "rs_rating": rs_percentile,
        "valid_bars": valid_counts[eligible_cols].astype(int),
        "is_statistically_valid_universe": is_valid_univ,
    }).dropna(subset=["composite_rs"]).sort_values(by="rs_rating", ascending=False)
    return result

if __name__ == "__main__":
    np.random.seed(21)
    n_days = 130
    bench = pd.Series(1400 * np.exp(np.cumsum(np.random.normal(0.0003, 0.008, n_days))))
    stocks = pd.DataFrame({
        "LEADER_A": 50 * np.exp(np.cumsum(np.random.normal(0.0022, 0.009, n_days))),
        "SPEC_B": 20 * np.exp(np.cumsum(np.random.normal(0.0025, 0.028, n_days))),
        "MARKET_C": 100 * np.exp(np.cumsum(np.random.normal(0.0004, 0.009, n_days))),
        "LAGGARD_D": 30 * np.exp(np.cumsum(np.random.normal(-0.0015, 0.014, n_days))),
    })
    print(rank_cross_sectional_rs(stocks, bench))


# ==============================================================================

# ตัวอย่างฟังก์ชันรวมตัวกรอง Pre-Breakout Quant Watchlist (บทที่ 1 ถึง บทที่ 6)
def filter_pre_breakout_watchlist(metrics_df: pd.DataFrame) -> pd.DataFrame:
    """คัดกรองหุ้นเกรด A ที่ผ่านเกณฑ์ RS, Hurst, ER, KAMA Slope และ VCP"""
    cond_leader = metrics_df["rs_rating"] >= 80.0
    cond_personality = (metrics_df["hurst"] >= 0.53) & (metrics_df["er_20"] >= 0.30)
    cond_trend = metrics_df["norm_atr_slope"] >= 0.15
    cond_vcp = (metrics_df["atr_ratio"] < 0.75) & (metrics_df["squeeze_ratio"] < 1.00)
    
    passed = metrics_df[cond_leader & cond_personality & cond_trend & cond_vcp].copy()
    return passed.sort_values(by="rs_rating", ascending=False)


