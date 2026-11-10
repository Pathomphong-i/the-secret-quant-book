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
        
    # 3. คำนวณคะแนนรวม Multi-Agent Alpha Conviction Score (บทที่ 4)
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
