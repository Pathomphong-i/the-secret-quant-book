#!/usr/bin/env python3
"""
The Secret Quant: 8-Volume Masterclass Series
เล่มที่ 4: สัญญาณเทคนิคเชิงสถิติและการตรวจจับสภาวะตลาด (The Alpha & Technical Signal Engine)
ผู้เขียน: ปฐมพงษ์ พิพัฒน์สุริยวงศ์
รวมซอร์สโค้ดครบทุกบทประจำเล่มที่ 4 พร้อมรันทดสอบได้ทันที
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


# ==============================================================================

import numpy as np
import pandas as pd

def score_atr_pullback_sniper(df: pd.DataFrame) -> pd.DataFrame:
    """คำนวณคะแนนดักซื้อเมื่อหุ้นขาขึ้นย่อตัวลงมาในกรอบ -1.0 ถึง -2.5 ATR"""
    close, high, low, vol = df["close"], df["high"], df["low"], df["volume"]
    sma_20 = close.rolling(20).mean()
    sma_100 = close.rolling(100).mean()
    atr_14 = (high - low).rolling(14).mean().replace(0, np.nan)
    
    rvol = (vol / vol.shift(1).rolling(20).mean().replace(0, np.nan)).fillna(1.0)
    z_pullback = ((close - sma_20) / atr_14).fillna(0.0)
    
    macro_uptrend = (close > sma_100) & (sma_100 > sma_100.shift(10))
    in_sweet_spot = (z_pullback >= -2.50) & (z_pullback <= -1.00)
    low_selling_vol = rvol <= 1.15
    
    # ให้คะแนนสูงสุด (100) เมื่อย่อตัวแถว -1.75 ATR ในขาขึ้นพร้อมโวลุ่มแห้ง
    dist_from_ideal = (z_pullback - (-1.75)).abs()
    raw_score = np.clip(100.0 - (dist_from_ideal * 55.0), 0.0, 100.0)
    sniper_score = np.where(macro_uptrend & in_sweet_spot & low_selling_vol, raw_score, 0.0)
    
    return pd.DataFrame({
        "close": close.round(2), "z_pullback_atr": z_pullback.round(2),
        "rvol": rvol.round(2), "macro_uptrend": macro_uptrend,
        "pullback_score": sniper_score.round(1)
    })

if __name__ == "__main__":
    np.random.seed(33)
    # จำลองหุ้นขาขึ้น 110 วันที่ย่อตัวลงมาเบาๆ ในช่วง 3 วันสุดท้ายด้วยโวลุ่มลดลง
    base_c = np.linspace(50, 75, 110) + np.sin(np.linspace(0, 18, 110)) * 1.8
    base_c[-3:] = [71.8, 70.9, 70.2]
    c = pd.Series(base_c)
    v = pd.Series([1000]*107 + [750, 680, 620])
    df_pb = pd.DataFrame({"close": c, "high": c + 0.9, "low": c - 0.9, "volume": v})
    print(score_atr_pullback_sniper(df_pb).tail(4))


# ==============================================================================

import numpy as np
import pandas as pd

def _calc_rsi(series: pd.Series, period: int) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0.0).rolling(period).mean()
    loss = (-delta.clip(upper=0.0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return (100.0 - (100.0 / (1.0 + rs))).fillna(50.0)

def compute_connors_rsi_signal(df: pd.DataFrame) -> pd.DataFrame:
    """คำนวณ Connors RSI (CRSI) และสัญญาณยืนยันการกลับตัววันแรก"""
    close, high, low = df["close"], df["high"], df["low"]
    rsi_3 = _calc_rsi(close, 3)
    
    # คำนวณจำนวนวันที่ปิดบวก/ลบติดต่อกัน (Up/Down Streak)
    diff = close.diff()
    streak = np.zeros(len(close))
    for i in range(1, len(close)):
        if diff.iloc[i] > 0:
            streak[i] = max(0, streak[i - 1]) + 1
        elif diff.iloc[i] < 0:
            streak[i] = min(0, streak[i - 1]) - 1
    rsi_streak_2 = _calc_rsi(pd.Series(streak, index=df.index), 2)
    
    ret_1d = close.pct_change()
    pct_rank = ret_1d.rolling(20).apply(lambda x: pd.Series(x).rank(pct=True).iloc[-1] * 100.0, raw=False).fillna(50.0)
    
    crsi = (rsi_3 + rsi_streak_2 + pct_rank) / 3.0
    clv = ((close - low) / (high - low).replace(0, np.nan)).fillna(0.5)
    
    setup_yesterday = crsi.shift(1) < 20.0
    trigger_today = (close > high.shift(1)) | ((close > close.shift(1)) & (clv >= 0.65))
    
    return pd.DataFrame({
        "close": close, "streak": streak, "crsi": crsi.round(1),
        "setup_ready": crsi < 20.0, "reversal_buy": setup_yesterday & trigger_today
    })

if __name__ == "__main__":
    c = pd.Series([20.0, 20.2, 20.5, 20.8, 21.0]*4 + [20.6, 20.2, 19.8, 19.5, 20.0])
    df_c = pd.DataFrame({"close": c, "high": c + 0.15, "low": c - 0.15})
    print(compute_connors_rsi_signal(df_c).tail(5))


# ==============================================================================

import numpy as np
import pandas as pd

def combine_multi_agent_alpha_score(
    candidates_df: pd.DataFrame, regime_probs: pd.Series
) -> pd.DataFrame:
    """รวมคะแนนจาก Trend Agent, Pullback Agent และ Cash Shield ตามสภาวะตลาด"""
    p_bull = float(regime_probs.get("BULL_TREND", 0.25))
    p_pull = float(regime_probs.get("PULLBACK", 0.25))
    p_side = float(regime_probs.get("SIDEWAYS", 0.25))
    p_crisis = float(regime_probs.get("HIGH_VOL_CRISIS", 0.25))
    
    w_trend = 0.70 * p_bull + 0.30 * p_pull + 0.25 * p_side
    w_pullback = 0.30 * p_bull + 0.70 * p_pull + 0.55 * p_side
    w_sum = max(w_trend + w_pullback, 1e-6)
    
    s_trend = candidates_df["trend_agent_score"]
    s_pull = candidates_df["pullback_agent_score"]
    s_bonus = np.where((s_trend >= 60) & (s_pull >= 60), 10.0, 0.0)
    
    blended = ((w_trend * s_trend + w_pullback * s_pull) / w_sum) + s_bonus
    cash_shield_factor = 1.0 - (0.85 * p_crisis)
    final_alpha = np.clip(blended * cash_shield_factor, 0.0, 100.0)
    
    tier = np.where(
        final_alpha >= 75.0, "TIER_1_HIGH_CONVICTION",
        np.where(final_alpha >= 55.0, "TIER_2_STANDARD_BUY", "PASS_HOLD_CASH")
    )
    out = candidates_df.copy()
    out["final_alpha_score"] = final_alpha.round(1)
    out["conviction_tier"] = tier
    return out.sort_values(by="final_alpha_score", ascending=False)

if __name__ == "__main__":
    df_cand = pd.DataFrame({
        "symbol": ["STOCK_A_BREAKOUT", "STOCK_B_PULLBACK", "STOCK_C_HYBRID"],
        "trend_agent_score": [92.0, 45.0, 80.0],
        "pullback_agent_score": [15.0, 90.0, 75.0]
    })
    regime = pd.Series({"BULL_TREND": 0.65, "PULLBACK": 0.25, "SIDEWAYS": 0.08, "HIGH_VOL_CRISIS": 0.02})
    print(combine_multi_agent_alpha_score(df_cand, regime))


# ==============================================================================

import pandas as pd

def run_daily_vol4_signal_pipeline(
    market_summary: dict,
    candidates_metrics: pd.DataFrame
) -> pd.DataFrame:
    """รันไปป์ไลน์คัดกรองและรวมคะแนนสัญญาณ Alpha ประจำวัน (End-to-End Runner)"""
    # 1. ประเมินความน่าจะเป็นสภาวะตลาด 4 ฤดูกาล (บทที่ 3)
    regime_probs = compute_regime_probabilities(
        breadth=market_summary["breadth"],
        atr_zscore=market_summary["atr_zscore"],
        index_er20=market_summary["index_er20"]
    )
    
    # 2. คัดกรองเฉพาะหุ้นที่ผ่านเกณฑ์ความแข็งแกร่งขั้นต่ำ RS >= 75
    qualified = candidates_metrics[candidates_metrics["rs_rating"] >= 75.0].copy()
    if qualified.empty:
        return pd.DataFrame()
        
    # 3. คำนวณคะแนนรวม Multi-Agent Alpha Conviction Score (บทที่ 12)
    scored_df = combine_multi_agent_alpha_score(qualified, regime_probs)
    scored_df["dominant_regime"] = regime_probs.idxmax()
    scored_df["crisis_prob"] = float(regime_probs["HIGH_VOL_CRISIS"])
    return scored_df

if __name__ == "__main__":
    mkt = {"breadth": 0.64, "atr_zscore": -0.20, "index_er20": 0.44}
    sample_candidates = pd.DataFrame({
        "symbol": ["PTT_DEMO", "ADVANC_DEMO", "CPALL_DEMO", "BDMS_DEMO"],
        "rs_rating": [92.5, 86.0, 81.5, 62.0],
        "trend_agent_score": [88.0, 74.0, 42.0, 50.0],
        "pullback_agent_score": [30.0, 68.0, 89.0, 40.0],
        "atr_14": [0.75, 3.50, 1.10, 0.60]
    })
    daily_orders = run_daily_vol4_signal_pipeline(mkt, sample_candidates)
    print(daily_orders[["symbol", "rs_rating", "final_alpha_score", "conviction_tier", "dominant_regime"]])
