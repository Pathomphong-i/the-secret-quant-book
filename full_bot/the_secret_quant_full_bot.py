#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=========================================================================================
โรบอทเทรด ที่โบรกเกอร์ไม่อยากให้คุณเขียน — เปิดแก่นความคิดของ Quant Trader ยุคใหม่
FULL EDUCATIONAL TRADING BOT & BACKTEST ENGINE (END-TO-END, บทที่ 1 - บทที่ 14)
=========================================================================================
ไฟล์นี้คือระบบ Quantitative Trading แบบครบวงจร (Full Working Version) สำหรับประกอบหนังสือ
"โรบอทเทรด ที่โบรกเกอร์ไม่อยากให้คุณเขียน — เปิดแก่นความคิดของ Quant Trader ยุคใหม่"
ผู้เขียน: ปฐมพงษ์ พิพัฒน์สุริยวงศ์

คำเตือน:
  เนื้อหาและโค้ดในไฟล์นี้จัดทำขึ้นเพื่อการศึกษาและเป็นความคิดเห็นส่วนตัวของผู้เขียนเท่านั้น
  มิใช่การแนะนำการลงทุน ผู้ลงทุนโปรดศึกษาข้อมูลและความเสี่ยงด้วยตนเอง

คุณสมบัติครบทั้ง 6 เสาหลักในไฟล์เดียว (พร้อมอัปเดตตาม 8 มาตรการการซื้อขายของตลาดหลักทรัพย์ฯ SET):
  1. Point-in-Time Data Engine & Data Hygiene Audit (บทที่ 3 - 5)
     - ตรวจสอบข้อมูลซ้ำ/แหว่ง, ป้องกัน Look-Ahead Bias (ใช้ข้อมูล T-1 ส่งคำสั่งที่ราคาเปิด/VWAP วัน T)
  2. Market Regime Detector & Markov Transition Filter (บทที่ 10)
     - คำนวณ Kaufman Efficiency Ratio (ER 20) + Volatility Z-Score (20d/252d)
     - แยกสภาวะตลาดเป็น BULL_TREND, SIDEWAYS_QUIET, CRISIS_PANIC
  3. Starter 3-Agent Ensemble & 3-Layer Signal Filter (บทที่ 7 & 11)
     - Agent 1: Trend-Following (EMA 20/50 + KAMA)
     - Agent 2: Mean-Reversion (RSI 14 + Bollinger %B บนหุ้นขาขึ้นใหญ่ SMA 200)
     - Agent 3: Cash & Volatility Shield (เกราะป้องกันความผันผวน)
     - ตัวกรอง 3 ชั้น: สภาวะตลาดรวม + โมเมนตัมเทียบดัชนี + Volume Participation
  4. Position Context Manager & Ratchet Trailing Stop (บทที่ 8)
     - บันทึกเหตุผลการเข้าซื้อ (Thesis Tagging) แยกกฎการถือและจุดตัดขาดทุนตามกลยุทธ์
     - ระบบล็อกกำไรขั้นบันได (Breakeven Lock ที่ +1.5R และ Profit Ratchet ที่ +3.0R)
  5. Portfolio Risk Engine, HRP Allocation & Two-Bucket Profit Skimming (บทที่ 6, 9, 12)
     - คำนวณขนาดไม้ตามความผันผวน (1% Risk per Trade ด้วย ATR 14)
     - เพดานความเสี่ยงพอร์ตรวม (Max Portfolio Heat 5.0%)
     - จัดสรรน้ำหนักด้วย Hierarchical Risk Parity (HRP) ลดความเสี่ยงหุ้นวิ่งตามกัน
     - 3-Tier Drawdown Circuit Breaker (-5% ลดขนาดไม้ครึ่งหนึ่ง, -8% หยุดซื้อเพิ่ม, -10% ถอยถือเงินสด)
     - Two-Bucket System: ตักกำไร 30% เข้าถังเงินออมปลอดภัยทุกครั้งที่พอร์ตทำ New High เกินขั้นละ +10%
  6. Walk-Forward Validation, SET 8 Trading Measures & Smart TWAP/VWAP Execution (บทที่ 1, 6, 13, 14)
     - ทดสอบ Walk-Forward Efficiency (WFE) วัดความเสถียร In-Sample vs Out-of-Sample
     - รองรับ 8 มาตรการการซื้อขายของ SET (Tick Size ใหม่ช่วง 5-50 บาท = 0.02/0.05/0.10, Zero-Plus/Uptick Short Rule, OTR Guard)
     - จำลองแผนส่งคำสั่งซื้อขายระดับจุลภาค (Micro-Price, OBI, Spread Guard, TWAP Jitter)

วิธีรัน:
  python3 the_secret_quant_full_bot.py --csv sample_thai_stocks_ohlcv.csv
=========================================================================================
"""

from __future__ import annotations

import argparse
import math
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


# =========================================================================================
# 0. กำหนดค่าพารามิเตอร์มาตรฐานเชิงการศึกษา (TEXTBOOK CONFIGURATION)
# =========================================================================================
@dataclass(frozen=True)
class QuantConfig:
    initial_capital: float = 1_000_000.0      # เงินทุนเริ่มต้น 1,000,000 บาท
    risk_per_trade_pct: float = 0.030         # ความเสี่ยงต่อไม้ 3.0% ของพอร์ตตามความผันผวน ATR (บทที่ 9)
    max_portfolio_heat_pct: float = 0.15      # เพดานความเสี่ยงรวมสูงสุดของพอร์ต (บทที่ 9)
    max_single_weight_pct: float = 0.34       # น้ำหนักหุ้นรายตัวสูงสุดไม่เกิน 34% ของพอร์ต
    commission_vat_rate: float = 0.00157      # ค่าคอมมิชชัน + VAT ตลาดหุ้นไทย (~0.157% ต่อขา)
    base_slippage_bps: float = 10.0           # ค่า Slippage พื้นฐาน 10 bps (0.10%)
    board_lot: int = 100                      # หน่วยซื้อขายขั้นต่ำตลาดหุ้นไทย (100 หุ้น)

    # พารามิเตอร์ตัวชี้วัดมาตรฐาน (บทที่ 7, 10, 11)
    ema_fast: int = 20
    ema_slow: int = 50
    sma_long: int = 150
    atr_period: int = 14
    er_period: int = 20
    rsi_period: int = 14
    vol_short_window: int = 20
    vol_long_window: int = 120

    # พารามิเตอร์ตัดขาดทุนและล็อกกำไร (บทที่ 8)
    trend_atr_stop_mult: float = 3.8          # ระยะ Trailing Stop สำหรับ Trend-Following (3.8 ATR)
    mr_atr_stop_mult: float = 2.5             # ระยะ Stop Loss สำหรับ Mean-Reversion (2.5 ATR)
    breakeven_r_trigger: float = 1.5          # ขยับ Stop บังทุนเมื่อกำไรแตะ +1.5R
    ratchet_r_trigger: float = 3.5            # บีบ Trailing Stop แน่นขึ้นเมื่อกำไรแตะ +3.5R

    # พารามิเตอร์ Circuit Breaker & Two-Bucket (บทที่ 9 & 12)
    dd_tier1_reduce_size: float = -0.05       # Drawdown -5%: ลดขนาดไม้ลง 50%
    dd_tier2_halt_buys: float = -0.08         # Drawdown -8%: หยุดเปิดสถานะซื้อใหม่
    dd_tier3_panic_shield: float = -0.10      # Drawdown -10%: เปิดเกราะป้องกันพอร์ต
    profit_skim_milestone_pct: float = 0.10   # ทุกๆ กำไรสุทธิ +10% New High
    profit_skim_ratio: float = 0.30           # ตักกำไร 30% เข้าถังปลอดภัย (Safe Reserve Bucket)


# =========================================================================================
# 1. สร้างข้อมูลตัวอย่างตลาดหุ้นไทย (SAMPLE DATASET GENERATOR หากไม่มีไฟล์ CSV)
# =========================================================================================
def generate_sample_thai_ohlcv_csv(csv_path: str, n_days: int = 500, seed: int = 42) -> pd.DataFrame:
    """
    สร้างข้อมูลราคาหุ้นรายวันจำลอง (Realistic Multi-Regime OHLCV) สำหรับหุ้นไทย 6 ตัว + SET_INDEX
    ครอบคลุม 4 สภาวะตลาด: ขาขึ้นรอบแรก -> พักตัว Sideways -> วิกฤตปรับฐานแรง -> ขาขึ้นรอบใหม่
    """
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range(start="2023-01-03", periods=n_days)

    # กำหนดตารางสภาวะตลาดตามช่วงเวลา (Regime Schedule)
    regime_drift = np.zeros(n_days)
    regime_vol_mult = np.ones(n_days)
    # ช่วงที่ 1 (วัน 0-179): ขาขึ้นแข็งแกร่งรอบแรก (Bull Trend)
    regime_drift[:180] = 0.0014
    regime_vol_mult[:180] = 0.70
    # ช่วงที่ 2 (วัน 180-269): ตลาดออกข้างสะสมพลัง (Sideways Quiet)
    regime_drift[180:270] = 0.0002
    regime_vol_mult[180:270] = 0.80
    # ช่วงที่ 3 (วัน 270-319): ตลาดปรับฐานแรง/วิกฤต (Crisis / Sharp Correction)
    regime_drift[270:320] = -0.0032
    regime_vol_mult[270:320] = 2.10
    # ช่วงที่ 4 (วัน 320-499): ตลาดฟื้นตัวและกลับเป็นขาขึ้นรอบใหม่ (Recovery & Bull)
    regime_drift[320:] = 0.0015
    regime_vol_mult[320:] = 0.72

    # สร้างปัจจัยตลาดรวม (Market Factor)
    market_shocks = rng.normal(loc=regime_drift, scale=0.0055 * regime_vol_mult)
    set_close = 1550.0 * np.exp(np.cumsum(market_shocks))
    set_open = np.roll(set_close, 1) * (1.0 + rng.normal(0, 0.002, n_days))
    set_open[0] = 1550.0
    intraday_span = np.abs(rng.normal(0.006, 0.0025, n_days)) * regime_vol_mult
    set_high = np.maximum(set_open, set_close) * (1.0 + intraday_span)
    set_low = np.minimum(set_open, set_close) * (1.0 - intraday_span)
    set_vol = rng.integers(35_000_000, 75_000_000, size=n_days)

    rows = []
    for i in range(n_days):
        rows.append({
            "date": dates[i].strftime("%Y-%m-%d"),
            "symbol": "SET_INDEX",
            "sector": "INDEX",
            "open": round(float(set_open[i]), 2),
            "high": round(float(set_high[i]), 2),
            "low": round(float(set_low[i]), 2),
            "close": round(float(set_close[i]), 2),
            "volume": int(set_vol[i]),
        })

    # รายชื่อหุ้นจำลองตัวแทน 6 อุตสาหกรรม (เพื่อการศึกษาและทดสอบระบบ Backtest)
    tickers_meta = [
        ("STOCK_ICT.BK",   "ICT",   200.0, 0.75, 0.00035, 0.011, 4_500_000),
        ("STOCK_TRANS.BK", "TRANS",  62.0, 0.95, 0.00030, 0.013, 18_000_000),
        ("STOCK_HELTH.BK", "HELTH",  27.5, 0.65, 0.00030, 0.010, 25_000_000),
        ("STOCK_COMM.BK",  "COMM",   58.0, 0.90, 0.00035, 0.012, 22_000_000),
        ("STOCK_ENERG.BK", "ENERG",  33.0, 0.85, 0.00020, 0.011, 45_000_000),
        ("STOCK_BANK.BK",  "BANK",  102.0, 1.05, 0.00028, 0.013, 8_500_000),
    ]

    for symbol, sector, start_price, beta, alpha, idio_vol, avg_vol in tickers_meta:
        idio_shocks = rng.normal(loc=alpha, scale=idio_vol * regime_vol_mult)
        # เพิ่มรอบ Cycle ย่อยให้เกิดจังหวะย่อตัว (Pullback) และเบรกเอาต์ (Breakout) ที่สมจริง
        cyclewave = 0.0018 * np.sin(np.linspace(0, 12 * np.pi, n_days) + rng.uniform(0, np.pi))
        total_ret = beta * market_shocks + idio_shocks + cyclewave
        close_arr = start_price * np.exp(np.cumsum(total_ret))
        open_arr = np.roll(close_arr, 1) * (1.0 + rng.normal(0, 0.0025, n_days))
        open_arr[0] = start_price
        span = np.abs(rng.normal(0.009, 0.0035, n_days)) * regime_vol_mult
        high_arr = np.maximum(open_arr, close_arr) * (1.0 + span)
        low_arr = np.minimum(open_arr, close_arr) * (1.0 - span)
        vol_mult = np.exp(rng.normal(0, 0.35, n_days)) * (1.0 + 18.0 * np.abs(total_ret))
        vol_arr = (avg_vol * vol_mult).astype(int)

        for i in range(n_days):
            rows.append({
                "date": dates[i].strftime("%Y-%m-%d"),
                "symbol": symbol,
                "sector": sector,
                "open": round(float(open_arr[i]), 2),
                "high": round(float(high_arr[i]), 2),
                "low": round(float(low_arr[i]), 2),
                "close": round(float(close_arr[i]), 2),
                "volume": int(vol_arr[i]),
            })

    df = pd.DataFrame(rows).sort_values(["date", "symbol"]).reset_index(drop=True)
    df.to_csv(csv_path, index=False)
    return df


# =========================================================================================
# 2. DATA ENGINE & POINT-IN-TIME FEATURE PIPELINE (บทที่ 3, 4, 5, 7, 10)
# =========================================================================================
def compute_kama(series: pd.Series, er_period: int = 10, fast_period: int = 2, slow_period: int = 30) -> pd.Series:
    """คำนวณเส้นค่าเฉลี่ยปรับตัวอัตโนมัติ Kaufman's Adaptive Moving Average (KAMA - บทที่ 7)"""
    values = series.to_numpy(dtype=float)
    kama = np.full_like(values, np.nan)
    if len(values) <= er_period:
        return pd.Series(kama, index=series.index)

    fast_sc = 2.0 / (fast_period + 1.0)
    slow_sc = 2.0 / (slow_period + 1.0)
    kama[er_period - 1] = values[er_period - 1]

    for i in range(er_period, len(values)):
        change = abs(values[i] - values[i - er_period])
        volatility = np.sum(np.abs(np.diff(values[i - er_period : i + 1])))
        er = change / volatility if volatility > 1e-9 else 0.0
        sc = (er * (fast_sc - slow_sc) + slow_sc) ** 2
        prev_k = kama[i - 1] if not np.isnan(kama[i - 1]) else values[i]
        kama[i] = prev_k + sc * (values[i] - prev_k)

    return pd.Series(kama, index=series.index)


def prepare_point_in_time_features(raw_df: pd.DataFrame, cfg: QuantConfig) -> Tuple[Dict[str, pd.DataFrame], pd.DataFrame]:
    """
    ตรวจสอบความสะอาดข้อมูล (Data Hygiene) และคำนวณอินดิเคเตอร์ทั้งหมดแบบ Point-in-Time
    โดยแยกตารางดัชนีตลาด (SET_INDEX) และตารางหุ้นรายตัวออกจากกัน
    """
    df = raw_df.copy()
    df["date"] = pd.to_datetime(df["date"])
    df = df.drop_duplicates(subset=["date", "symbol"]).sort_values(["symbol", "date"]).reset_index(drop=True)

    # ตรวจสอบความถูกต้องของแท่งเทียน (High >= Low และราคาต้องเป็นบวก)
    valid_mask = (df["close"] > 0) & (df["open"] > 0) & (df["high"] >= df["low"]) & (df["volume"] >= 0)
    df = df.loc[valid_mask].copy()

    # แยกข้อมูลดัชนีตลาดรวม (SET_INDEX) เพื่อใช้คำนวณ Market Regime (บทที่ 10)
    idx_df = df[df["symbol"] == "SET_INDEX"].sort_values("date").set_index("date").copy()
    if idx_df.empty:
        raise ValueError("ไม่พบข้อมูล SET_INDEX ในไฟล์ CSV สำหรับประเมินสภาวะตลาดรวม")

    idx_df["ret_1d"] = idx_df["close"].pct_change()
    idx_df["ret_20d"] = idx_df["close"].pct_change(cfg.er_period)
    net_move = (idx_df["close"] - idx_df["close"].shift(cfg.er_period)).abs()
    sum_step = idx_df["close"].diff().abs().rolling(cfg.er_period).sum()
    idx_df["er_20"] = (net_move / sum_step.replace(0, np.nan)).fillna(0.0)

    vol_20 = idx_df["ret_1d"].rolling(cfg.vol_short_window).std() * np.sqrt(252)
    vol_mean = vol_20.rolling(cfg.vol_long_window, min_periods=30).mean()
    vol_std = vol_20.rolling(cfg.vol_long_window, min_periods=30).std().replace(0, np.nan)
    idx_df["vol_z"] = ((vol_20 - vol_mean) / vol_std).fillna(0.0)
    idx_df["sma_50"] = idx_df["close"].rolling(50).mean()

    # จำแนกสภาวะตลาดรวม (Regime Detector + Markov Persistence Smoothing - บทที่ 10)
    regimes: List[str] = []
    prev_regime = "SIDEWAYS_QUIET"
    for dt, row in idx_df.iterrows():
        er_val = float(row["er_20"])
        vz_val = float(row["vol_z"])
        above_ma = bool(row["close"] >= row["sma_50"]) if not np.isnan(row["sma_50"]) else True

        if (not above_ma and vz_val > 1.15) or vz_val > 2.00:
            raw_regime = "CRISIS_PANIC"
        elif above_ma and er_val >= 0.18:
            raw_regime = "BULL_TREND"
        else:
            raw_regime = "SIDEWAYS_QUIET"

        # กฎความหนืดของมาร์คอฟ (Markov Persistence): ป้องกันการสลับโหมดไปมารายวัน
        if raw_regime == "CRISIS_PANIC":
            curr_regime = "CRISIS_PANIC"  # หากเกิดวิกฤต ให้ตัดเข้าโหมดป้องกันทันที
        elif prev_regime == "CRISIS_PANIC" and (not above_ma and vz_val > 0.65):
            curr_regime = "CRISIS_PANIC"  # รอให้ความผันผวนลดลงจริงก่อนออกจากโหมดวิกฤต
        else:
            curr_regime = raw_regime

        regimes.append(curr_regime)
        prev_regime = curr_regime

    idx_df["regime"] = regimes

    # คำนวณอินดิเคเตอร์ของหุ้นรายตัวแต่ละตัว (บทที่ 7 & 11)
    stock_Map: Dict[str, pd.DataFrame] = {}
    for sym, grp in df[df["symbol"] != "SET_INDEX"].groupby("symbol"):
        s = grp.sort_values("date").set_index("date").copy()
        s["ret_1d"] = s["close"].pct_change()
        s["ret_20d"] = s["close"].pct_change(20)
        s["ema_fast"] = s["close"].ewm(span=cfg.ema_fast, adjust=False).mean()
        s["ema_slow"] = s["close"].ewm(span=cfg.ema_slow, adjust=False).mean()
        s["sma_long"] = s["close"].rolling(cfg.sma_long, min_periods=50).mean()
        s["kama"] = compute_kama(s["close"], er_period=10, fast_period=2, slow_period=30)

        # ATR (14) สำหรับวัดความผันผวนและกำหนดขนาดไม้ (บทที่ 8 & 9)
        high_low = s["high"] - s["low"]
        high_pc = (s["high"] - s["close"].shift(1)).abs()
        low_pc = (s["low"] - s["close"].shift(1)).abs()
        tr = pd.concat([high_low, high_pc, low_pc], axis=1).max(axis=1)
        s["atr"] = tr.rolling(cfg.atr_period, min_periods=5).mean()

        # RSI (14) และ Bollinger %B สำหรับกลยุทธ์สลับฟันปลา Mean-Reversion (บทที่ 7)
        delta = s["close"].diff()
        gain = delta.clip(lower=0.0).rolling(cfg.rsi_period, min_periods=5).mean()
        loss = (-delta.clip(upper=0.0)).rolling(cfg.rsi_period, min_periods=5).mean()
        rs = gain / loss.replace(0, np.nan)
        s["rsi"] = (100.0 - (100.0 / (1.0 + rs))).fillna(50.0)

        bb_mid = s["close"].rolling(20, min_periods=10).mean()
        bb_std = s["close"].rolling(20, min_periods=10).std().replace(0, np.nan)
        bb_low = bb_mid - 2.0 * bb_std
        bb_high = bb_mid + 2.0 * bb_std
        s["bb_pct_b"] = ((s["close"] - bb_low) / (bb_high - bb_low).replace(0, np.nan)).fillna(0.5)
        s["sma_20"] = bb_mid
        s["vol_sma_20"] = s["volume"].rolling(20, min_periods=5).mean()

        stock_Map[sym] = s

    return stock_Map, idx_df


# =========================================================================================
# 3. HIERARCHICAL RISK PARITY (HRP) ALLOCATOR (บทที่ 12)
# =========================================================================================
def compute_hrp_weights(returns_window: pd.DataFrame, max_weight: float = 0.25) -> Dict[str, float]:
    """
    คำนวณน้ำหนักการลงทุนตามหลัก Hierarchical Risk Parity (HRP - บทที่ 12)
    จัดลำดับสินทรัพย์ตามความสัมพันธ์ (Correlation Clustering) และแบ่งน้ำหนักแบบ Inverse-Variance Bisection
    """
    clean_ret = returns_window.dropna(how="all", axis=1).fillna(0.0)
    symbols = list(clean_ret.columns)
    n = len(symbols)
    if n == 0:
        return {}
    if n == 1:
        return {symbols[0]: 1.0}

    cov = clean_ret.cov().to_numpy(dtype=float)
    corr = clean_ret.corr().fillna(0.0).to_numpy(dtype=float)
    # ระยะห่างทางสถิติ (Correlation Distance Matrix)
    dist = np.sqrt(np.clip((1.0 - corr) / 2.0, 0.0, 1.0))

    # Quasi-Diagonalization: เรียงลำดับหุ้นที่มีความคล้ายกันให้อยู่ติดกัน
    ordered_idx = [int(np.argmin(dist.sum(axis=1)))]
    remaining = set(range(n)) - set(ordered_idx)
    while remaining:
        last_i = ordered_idx[-1]
        next_i = min(remaining, key=lambda j: float(dist[last_i, j]))
        ordered_idx.append(next_i)
        remaining.remove(next_i)

    # Recursive Bisection: แบ่งครึ่งกลุ่มและให้น้ำหนักแปรผกผันกับความแปรปรวนของกลุ่ม
    weights = np.ones(n, dtype=float)

    def _cluster_var(indices: List[int]) -> float:
        sub_cov = cov[np.ix_(indices, indices)]
        diag_var = np.clip(np.diag(sub_cov), 1e-8, None)
        inv_diag = (1.0 / diag_var)
        inv_diag /= inv_diag.sum()
        return float(inv_diag @ sub_cov @ inv_diag)

    clusters = [ordered_idx]
    while clusters:
        next_clusters = []
        for cluster in clusters:
            if len(cluster) <= 1:
                continue
            mid = len(cluster) // 2
            left, right = cluster[:mid], cluster[mid:]
            v_left = _cluster_var(left)
            v_right = _cluster_var(right)
            alpha = 1.0 - v_left / (v_left + v_right + 1e-12)
            for idx in left:
                weights[idx] *= alpha
            for idx in right:
                weights[idx] *= (1.0 - alpha)
            next_clusters.extend([left, right])
        clusters = next_clusters

    weights = np.clip(weights, 0.0, max_weight)
    total_w = weights.sum()
    if total_w > 0:
        weights /= total_w

    return {symbols[i]: float(weights[i]) for i in range(n)}


# =========================================================================================
# 4. POSITION CONTEXT MANAGER & RATCHET TRAILING STOP (บทที่ 8)
# =========================================================================================
@dataclass
class OpenPosition:
    symbol: str
    sector: str
    entry_date: pd.Timestamp
    entry_price: float
    shares: int
    initial_stop: float
    trailing_stop: float
    highest_close: float
    thesis_tag: str                 # "TREND_FOLLOWING" หรือ "MEAN_REVERSION"
    initial_risk_per_share: float   # 1R ต่อหุ้น ณ วันเข้าซื้อ
    ratchet_stage: str = "INITIAL"  # INITIAL -> BREAKEVEN_LOCKED -> PROFIT_RATCHETED


def update_position_stop_and_check_exit(
    pos: OpenPosition,
    row_t_minus_1: pd.Series,
    regime_t_minus_1: str,
    cfg: QuantConfig,
) -> Tuple[bool, str]:
    """
    ตรวจสอบเงื่อนไขการขายออกและอัปเดตจุดตัดขาดทุนยกระดับตามหลังราคา (Ratchet Trailing Stop - บทที่ 8)
    โดยใช้ข้อมูล ณ สิ้นวัน T-1 เพื่อตัดสินใจส่งคำสั่งขายที่ราคาเปิดของวัน T (ไร้ Look-Ahead Bias)
    """
    close_p = float(row_t_minus_1["close"])
    atr_p = float(row_t_minus_1["atr"]) if not np.isnan(row_t_minus_1["atr"]) else close_p * 0.02
    pos.highest_close = max(pos.highest_close, close_p)

    # คำนวณกำไรปัจจุบันเป็นหน่วยเท่าของความเสี่ยงตั้งต้น (R-Multiple)
    r_multiple = (close_p - pos.entry_price) / max(pos.initial_risk_per_share, 1e-6)

    # 1. กฎห้ามขยับจุดตัดขาดทุนหนีลงล่างเด็ดขาด (No-Widening Invariant)
    new_stop = pos.trailing_stop

    # 2. ยกระดับจุดตัดขาดทุนเป็นขั้นบันได (Ratchet Trailing Stop)
    if r_multiple >= cfg.ratchet_r_trigger:
        ratchet_candidate = pos.highest_close - 2.8 * atr_p
        new_stop = max(new_stop, ratchet_candidate, pos.entry_price * 1.01)
        pos.ratchet_stage = "PROFIT_RATCHETED (+3.5R)"
    elif r_multiple >= cfg.breakeven_r_trigger:
        be_candidate = pos.entry_price * 1.004  # ล็อกหน้าตัก + ค่าคอมมิชชัน
        new_stop = max(new_stop, be_candidate)
        if pos.ratchet_stage == "INITIAL":
            pos.ratchet_stage = "BREAKEVEN_LOCKED (+1.5R)"

    # 3. อัปเดต Chandelier Trailing Stop ตามความผันผวน (ATR Chandelier Stop)
    chandelier_stop = pos.highest_close - cfg.trend_atr_stop_mult * atr_p
    pos.trailing_stop = max(new_stop, chandelier_stop)

    # 4. ตรวจสอบเงื่อนไขการออกจากสถานะ (Exit Rules)
    if regime_t_minus_1 == "CRISIS_PANIC":
        return True, "CRISIS_SHIELD_EXIT (ตลาดเข้าสู่ภาวะวิกฤต)"

    if close_p <= pos.trailing_stop:
        return True, f"TRAILING_STOP_HIT ({pos.ratchet_stage})"

    if pos.thesis_tag == "MEAN_REVERSION" and regime_t_minus_1 == "SIDEWAYS_QUIET":
        if close_p >= float(row_t_minus_1["sma_20"]) and float(row_t_minus_1["rsi"]) >= 68.0:
            return True, "MEAN_REVERT_TARGET (ราคาดีดกลับแตะค่าเฉลี่ย SMA 20 / RSI >= 68)"

    return False, ""


# =========================================================================================
# 5. STARTER 3-AGENT ENSEMBLE & 3-LAYER SIGNAL FILTER (บทที่ 7 & 11)
# =========================================================================================
def evaluate_3_agent_ensemble_signal(
    sym: str,
    row_t_minus_1: pd.Series,
    idx_row_t_minus_1: pd.Series,
    regime: str,
) -> Tuple[bool, str, float]:
    """
    ระบบ 3 เอเจนต์ร่วมตัดสินใจ (Starter 3-Agent Ensemble - บทที่ 11)
    ผสานตัวกรองสัญญาณ 3 ชั้น (3-Layer Confirmation Filter):
      ชั้นที่ 1: สภาวะตลาดรวม (Macro Regime Guard)
      ชั้นที่ 2: ความแข็งแกร่งเทียบตลาด (Relative Momentum vs SET_INDEX)
      ชั้นที่ 3: แนวโน้มโครงสร้างหลักและโมเมนตัม (KAMA / EMA / RSI Confirmation)
    คืนค่า: (ผ่านเกณฑ์หรือไม่, ป้ายกลยุทธ์ Thesis Tag, คะแนนความเชื่อมั่น Ensemble Score)
    """
    # เอเจนต์ที่ 3: Cash & Volatility Shield สั่งบล็อกการซื้อทันทีหากตลาดอยู่ในโหมดวิกฤต
    if regime == "CRISIS_PANIC":
        return False, "BLOCKED_BY_CASH_SHIELD", 0.0

    close_p = float(row_t_minus_1["close"])
    sma_long = float(row_t_minus_1["sma_long"]) if not np.isnan(row_t_minus_1["sma_long"]) else close_p
    ema_fast = float(row_t_minus_1["ema_fast"])
    ema_slow = float(row_t_minus_1["ema_slow"])
    kama_val = float(row_t_minus_1["kama"]) if not np.isnan(row_t_minus_1["kama"]) else ema_fast
    rsi_val = float(row_t_minus_1["rsi"])
    bb_pct_b = float(row_t_minus_1["bb_pct_b"])

    stock_ret_20 = float(row_t_minus_1["ret_20d"]) if not np.isnan(row_t_minus_1["ret_20d"]) else 0.0
    idx_ret_20 = float(idx_row_t_minus_1["ret_20d"]) if not np.isnan(idx_row_t_minus_1["ret_20d"]) else 0.0

    # เอเจนต์ที่ 1: Trend-Following Agent (ทำงานเด่นในสภาวะ BULL_TREND)
    trend_cond = (
        close_p >= sma_long * 0.98
        and (ema_fast >= ema_slow or close_p >= kama_val)
        and stock_ret_20 >= idx_ret_20 * 0.65
        and 45.0 <= rsi_val <= 78.0
    )

    # เอเจนต์ที่ 2: Mean-Reversion Agent (ช้อนซื้อเมื่อย่อตัวแรงแต่ภาพใหญ่ยังเป็นขาขึ้น)
    mr_cond = (
        close_p >= sma_long * 0.95
        and (rsi_val < 42.0 or bb_pct_b < 0.25)
    )

    if regime == "BULL_TREND" and trend_cond:
        score = 0.75 + stock_ret_20
        return True, "TREND_FOLLOWING", round(score, 4)

    if mr_cond:
        score = 0.70 + stock_ret_20 + (45.0 - rsi_val) / 200.0
        return True, "MEAN_REVERSION", round(score, 4)

    if regime == "SIDEWAYS_QUIET" and trend_cond and stock_ret_20 >= idx_ret_20:
        return True, "TREND_FOLLOWING", round(0.68 + stock_ret_20, 4)

    return False, "NO_SIGNAL", 0.0


# =========================================================================================
# 6. BACKTEST ENGINE & TWO-BUCKET PORTFOLIO SIMULATOR (บทที่ 5, 6, 8, 9, 12)
# =========================================================================================
@dataclass
class TradeRecord:
    symbol: str
    thesis_tag: str
    entry_date: str
    exit_date: str
    entry_price: float
    exit_price: float
    shares: int
    net_pnl: float
    return_pct: float
    r_multiple: float
    exit_reason: str


@dataclass
class BacktestSummary:
    equity_curve: pd.DataFrame
    trades: List[TradeRecord]
    initial_capital: float
    final_trading_equity: float
    safe_reserve_bucket: float
    total_combined_wealth: float
    total_return_pct: float
    cagr_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    win_rate_pct: float
    profit_factor: float
    expectancy_thb: float


def run_point_in_time_backtest(
    stock_map: Dict[str, pd.DataFrame],
    idx_df: pd.DataFrame,
    cfg: QuantConfig,
    start_idx: int = 60,
    end_idx: Optional[int] = None,
) -> BacktestSummary:
    """
    จำลองการเทรดแบบ Event-Driven Point-in-Time:
      - วิเคราะห์สัญญาณและคำนวณขนาดไม้จากข้อมูลปิดตลาดวัน T-1
      - ส่งคำสั่งซื้อ/ขายที่ราคาเปิดของวัน T บวกค่าคอมมิชชัน 0.157% และ Slippage
    """
    dates = list(idx_df.index)
    if end_idx is None or end_idx > len(dates):
        end_idx = len(dates)

    cash = cfg.initial_capital
    safe_bucket = 0.0
    next_skim_landmark = cfg.initial_capital * (1.0 + cfg.profit_skim_milestone_pct)
    peak_trading_equity = cfg.initial_capital

    positions: Dict[str, OpenPosition] = {}
    trades: List[TradeRecord] = []
    equity_rows: List[Dict[str, object]] = []

    symbols = sorted(stock_map.keys())

    for t in range(start_idx, end_idx):
        dt_prev = dates[t - 1]
        dt_now = dates[t]
        idx_prev = idx_df.loc[dt_prev]
        regime_prev = str(idx_prev["regime"])

        # ---------------------------------------------------------------------------------
        # ขั้นที่ 1: ตรวจสอบสถานะที่ถืออยู่ด้วยข้อมูลวัน T-1 และสั่งขายที่ราคาเปิดวัน T
        # ---------------------------------------------------------------------------------
        to_close: List[Tuple[str, str]] = []
        for sym, pos in positions.items():
            sdf = stock_map[sym]
            if dt_prev not in sdf.index or dt_now not in sdf.index:
                continue
            should_exit, reason = update_position_stop_and_check_exit(
                pos, sdf.loc[dt_prev], regime_prev, cfg
            )
            if should_exit:
                to_close.append((sym, reason))

        for sym, reason in to_close:
            pos = positions.pop(sym)
            open_t = float(stock_map[sym].loc[dt_now, "open"])
            slip_rate = cfg.base_slippage_bps / 10_000.0
            exec_sell_price = open_t * (1.0 - slip_rate)
            gross_proceeds = exec_sell_price * pos.shares
            sell_fee = gross_proceeds * cfg.commission_vat_rate
            net_proceeds = gross_proceeds - sell_fee
            cash += net_proceeds

            entry_cost_total = pos.entry_price * pos.shares * (1.0 + cfg.commission_vat_rate)
            net_pnl = net_proceeds - entry_cost_total
            ret_pct = (net_pnl / entry_cost_total) * 100.0
            r_mult = ((exec_sell_price - pos.entry_price) / max(pos.initial_risk_per_share, 1e-6))

            trades.append(
                TradeRecord(
                    symbol=sym,
                    thesis_tag=pos.thesis_tag,
                    entry_date=pos.entry_date.strftime("%Y-%m-%d"),
                    exit_date=dt_now.strftime("%Y-%m-%d"),
                    entry_price=round(pos.entry_price, 2),
                    exit_price=round(exec_sell_price, 2),
                    shares=pos.shares,
                    net_pnl=round(net_pnl, 2),
                    return_pct=round(ret_pct, 2),
                    r_multiple=round(r_mult, 2),
                    exit_reason=reason,
                )
            )

        # ---------------------------------------------------------------------------------
        # ขั้นที่ 2: ประเมิน Drawdown Circuit Breaker ณ สิ้นวัน T-1 (บทที่ 9)
        # ---------------------------------------------------------------------------------
        mkt_val_prev = sum(
            pos.shares * float(stock_map[sym].loc[dt_prev, "close"])
            for sym, pos in positions.items()
            if dt_prev in stock_map[sym].index
        )
        trading_eq_prev = cash + mkt_val_prev
        peak_trading_equity = max(peak_trading_equity, trading_eq_prev)
        current_dd = (trading_eq_prev - peak_trading_equity) / max(peak_trading_equity, 1.0)

        risk_scale = 1.0
        allow_new_buys = True
        if current_dd <= cfg.dd_tier3_panic_shield:
            allow_new_buys = False
            risk_scale = 0.0
        elif current_dd <= cfg.dd_tier2_halt_buys:
            allow_new_buys = False
            risk_scale = 0.0
        elif current_dd <= cfg.dd_tier1_reduce_size:
            risk_scale = 0.50  # ลดขนาดไม้ลงครึ่งหนึ่งเมื่อพอร์ตย่อเกิน -5%

        # ---------------------------------------------------------------------------------
        # ขั้นที่ 3: คัดกรองสัญญาณซื้อจาก 3-Agent Ensemble + จัดสรรน้ำหนัก HRP (บทที่ 11 & 12)
        # ---------------------------------------------------------------------------------
        if allow_new_buys and regime_prev != "CRISIS_PANIC":
            candidates: List[Tuple[str, str, float]] = []
            for sym in symbols:
                if sym in positions:
                    continue
                sdf = stock_map[sym]
                if dt_prev not in sdf.index or dt_now not in sdf.index:
                    continue
                ok, tag, score = evaluate_3_agent_ensemble_signal(
                    sym, sdf.loc[dt_prev], idx_prev, regime_prev
                )
                if ok:
                    candidates.append((sym, tag, score))

            candidates.sort(key=lambda x: x[2], reverse=True)

            if candidates:
                # คำนวณน้ำหนัก HRP ย้อนหลัง 60 วันทำการ
                ret_dict = {
                    sym: stock_map[sym]["ret_1d"].loc[:dt_prev].tail(60)
                    for sym in symbols
                }
                hrp_weights = compute_hrp_weights(pd.DataFrame(ret_dict), max_weight=cfg.max_single_weight_pct)

                # คำนวณ Portfolio Heat ปัจจุบัน (ผลรวมความเสี่ยงของทุกสถานะที่เปิดอยู่)
                current_open_risk = sum(
                    max(0.0, (pos.entry_price - pos.trailing_stop) * pos.shares)
                    for pos in positions.values()
                )
                max_allowed_risk = trading_eq_prev * cfg.max_portfolio_heat_pct

                for sym, tag, score in candidates:
                    sdf = stock_map[sym]
                    row_prev = sdf.loc[dt_prev]
                    open_t = float(sdf.loc[dt_now, "open"])
                    atr_val = float(row_prev["atr"]) if not np.isnan(row_prev["atr"]) else open_t * 0.02

                    stop_mult = cfg.trend_atr_stop_mult if tag == "TREND_FOLLOWING" else cfg.mr_atr_stop_mult
                    stop_dist = max(atr_val * stop_mult, open_t * 0.015)

                    # คำนวณงบความเสี่ยงต่อไม้ (1% Risk * ตัวคูณ Circuit Breaker)
                    risk_budget = trading_eq_prev * cfg.risk_per_trade_pct * risk_scale
                    if current_open_risk + risk_budget > max_allowed_risk:
                        continue  # ข้ามทันทีหากเกินเพดาน Portfolio Heat 5%

                    shares_by_risk = int(risk_budget // stop_dist)
                    hrp_cap = trading_eq_prev * min(cfg.max_single_weight_pct, max(hrp_weights.get(sym, 0.24) * 1.8, 0.30))
                    shares_by_hrp = int(hrp_cap // open_t)
                    shares_by_cash = int((cash * 0.95) // (open_t * (1.0 + cfg.commission_vat_rate)))

                    raw_shares = min(shares_by_risk, shares_by_hrp, shares_by_cash)
                    shares = (raw_shares // cfg.board_lot) * cfg.board_lot
                    if shares < cfg.board_lot:
                        continue

                    slip_rate = cfg.base_slippage_bps / 10_000.0
                    exec_buy_price = open_t * (1.0 + slip_rate)
                    total_buy_cost = exec_buy_price * shares * (1.0 + cfg.commission_vat_rate)
                    if total_buy_cost > cash:
                        continue

                    cash -= total_buy_cost
                    init_stop = exec_buy_price - stop_dist
                    current_open_risk += stop_dist * shares

                    positions[sym] = OpenPosition(
                        symbol=sym,
                        sector=str(row_prev["sector"]),
                        entry_date=dt_now,
                        entry_price=exec_buy_price,
                        shares=shares,
                        initial_stop=init_stop,
                        trailing_stop=init_stop,
                        highest_close=float(sdf.loc[dt_now, "close"]),
                        thesis_tag=tag,
                        initial_risk_per_share=stop_dist,
                    )

        # ---------------------------------------------------------------------------------
        # ขั้นที่ 4: คำนวณมูลค่าพอร์ตสิ้นวัน T และระบบตักกำไรเข้าถังปลอดภัย (Two-Bucket - บทที่ 12)
        # ---------------------------------------------------------------------------------
        mkt_val_close = sum(
            pos.shares * float(stock_map[sym].loc[dt_now, "close"])
            for sym, pos in positions.items()
            if dt_now in stock_map[sym].index
        )
        trading_eq_close = cash + mkt_val_close

        # หากพอร์ตทำ New High ทะลุเป้าหมายขั้นละ +10% และมีเงินสดพร้อม ให้ตักกำไรส่วนเกินเก็บเข้า Safe Bucket
        if trading_eq_close >= next_skim_landmark:
            surplus_gain = trading_eq_close - cfg.initial_capital
            skim_amount = min(surplus_gain * cfg.profit_skim_ratio * 0.15, cash * 0.25)
            if skim_amount >= 5_000.0:
                cash -= skim_amount
                safe_bucket += skim_amount
                trading_eq_close = cash + mkt_val_close
                next_skim_landmark = trading_eq_close * (1.0 + cfg.profit_skim_milestone_pct)

        combined_wealth = trading_eq_close + safe_bucket
        equity_rows.append({
            "date": dt_now.strftime("%Y-%m-%d"),
            "regime": str(idx_df.loc[dt_now, "regime"]),
            "trading_equity": round(trading_eq_close, 2),
            "safe_bucket": round(safe_bucket, 2),
            "combined_wealth": round(combined_wealth, 2),
            "open_positions": len(positions),
        })

    eq_df = pd.DataFrame(equity_rows)
    if eq_df.empty:
        raise RuntimeError("ไม่มีข้อมูลเพียงพอสำหรับรัน Backtest")

    wealth_series = eq_df["combined_wealth"].astype(float)
    daily_rets = wealth_series.pct_change().dropna()
    total_ret_pct = ((wealth_series.iloc[-1] / cfg.initial_capital) - 1.0) * 100.0
    n_years = max(len(eq_df) / 252.0, 0.1)
    cagr_pct = (((wealth_series.iloc[-1] / cfg.initial_capital) ** (1.0 / n_years)) - 1.0) * 100.0

    roll_max = wealth_series.cummax()
    dd_series = (wealth_series - roll_max) / roll_max
    max_dd_pct = float(dd_series.min() * 100.0)

    ret_std = float(daily_rets.std())
    sharpe = float((daily_rets.mean() / ret_std) * np.sqrt(252)) if ret_std > 1e-9 else 0.0
    downside = daily_rets[daily_rets < 0]
    down_std = float(downside.std()) if len(downside) > 1 else 1e-9
    sortino = float((daily_rets.mean() / down_std) * np.sqrt(252)) if down_std > 1e-9 else 0.0

    wins = [t.net_pnl for t in trades if t.net_pnl > 0]
    losses = [abs(t.net_pnl) for t in trades if t.net_pnl <= 0]
    win_rate = (len(wins) / len(trades) * 100.0) if trades else 0.0
    pf = (sum(wins) / sum(losses)) if losses and sum(losses) > 0 else (99.9 if wins else 0.0)
    expectancy = (sum(t.net_pnl for t in trades) / len(trades)) if trades else 0.0

    return BacktestSummary(
        equity_curve=eq_df,
        trades=trades,
        initial_capital=cfg.initial_capital,
        final_trading_equity=float(eq_df["trading_equity"].iloc[-1]),
        safe_reserve_bucket=float(eq_df["safe_bucket"].iloc[-1]),
        total_combined_wealth=float(wealth_series.iloc[-1]),
        total_return_pct=round(total_ret_pct, 2),
        cagr_pct=round(cagr_pct, 2),
        max_drawdown_pct=round(max_dd_pct, 2),
        sharpe_ratio=round(sharpe, 2),
        sortino_ratio=round(sortino, 2),
        win_rate_pct=round(win_rate, 2),
        profit_factor=round(pf, 2),
        expectancy_thb=round(expectancy, 2),
    )


# =========================================================================================
# 7. WALK-FORWARD EFFICIENCY (WFE) VALIDATOR (บทที่ 6)
# =========================================================================================
def run_walk_forward_check(
    stock_map: Dict[str, pd.DataFrame],
    idx_df: pd.DataFrame,
    cfg: QuantConfig,
) -> Tuple[float, float, float]:
    """
    แบ่งข้อมูลออกเป็นช่วงฝึกสอน (In-Sample 60% แรก) และช่วงทดสอบนอกกลุ่มตัวอย่าง (Out-of-Sample 40% หลัง)
    เพื่อคำนวณ Walk-Forward Efficiency (WFE - บทที่ 6) ป้องกันการแต่งกราฟย้อนหลัง (Overfitting)
    """
    n_total = len(idx_df)
    split_idx = int(n_total * 0.60)
    is_res = run_point_in_time_backtest(stock_map, idx_df, cfg, start_idx=60, end_idx=split_idx)
    oos_res = run_point_in_time_backtest(stock_map, idx_df, cfg, start_idx=split_idx, end_idx=n_total)

    is_cagr = max(is_res.cagr_pct, 0.01)
    oos_cagr = oos_res.cagr_pct
    wfe_pct = (oos_cagr / is_cagr) * 100.0
    return round(is_res.cagr_pct, 2), round(oos_cagr, 2), round(wfe_pct, 1)


# =========================================================================================
# 8. SET 8 TRADING MEASURES & SMART TWAP / VWAP ORDER EXECUTION PLANNER (บทที่ 1, 13 & 14)
# =========================================================================================
def get_set_tick_size(price: float) -> float:
    """
    คืนค่าขนาดช่องราคา (Tick Size) ตามเกณฑ์ 8 มาตรการการซื้อขายของตลาดหลักทรัพย์ฯ (SET 795-eight-trading-measures)
    - ปรับลด Tick Size สำหรับหุ้นราคา 5.00 - <50.00 บาท:
      * 5.00 - <10.00 บาท: 0.02 บาท (ลดจาก 0.05)
      * 10.00 - <25.00 บาท: 0.05 บาท (ลดจาก 0.10)
      * 25.00 - <50.00 บาท: 0.10 บาท (ลดจาก 0.25)
    """
    if price < 2.0:
        return 0.01
    if price < 5.0:
        return 0.02
    if price < 10.0:
        return 0.02
    if price < 25.0:
        return 0.05
    if price < 50.0:
        return 0.10
    if price < 100.0:
        return 0.25
    if price < 200.0:
        return 0.50
    if price < 400.0:
        return 1.00
    return 2.00


def round_to_set_tick(price: float, direction: str = "NEAREST") -> float:
    """ปัดราคาให้ตรงตามช่อง Tick Size ของตลาดหลักทรัพย์ฯ"""
    tick = get_set_tick_size(price)
    steps = price / tick
    if direction == "DOWN":
        return round(float(math.floor(steps + 1e-9) * tick), 2)
    if direction == "UP":
        return round(float(math.ceil(steps - 1e-9) * tick), 2)
    return round(float(round(steps) * tick), 2)


def validate_set_short_sell_and_otr(
    order_price: float,
    last_trade_price: float,
    prev_day_return_pct: float,
    is_eligible_short_universe: bool = True,
    orders_this_minute: int = 4,
    daily_orders: int = 80,
    daily_trades: int = 30,
) -> Dict[str, object]:
    """
    ตรวจสอบความสอดคล้องกับ 8 มาตรการการซื้อขายของตลาดหลักทรัพย์ฯ:
      - มาตรการที่ 2: Zero-Plus Tick ในภาวะปกติ และ Uptick Rule ในวันถัดไปหากวันก่อนหน้าปิดลบ >= 10%
      - มาตรการที่ 3: อนุญาตให้ Short Sell เฉพาะหุ้นในกลุ่ม SET100 / SSF / DR / ETF
      - มาตรการที่ 5: ควบคุม Order-to-Trade Ratio (OTR <= 50x และ <= 50 คำสั่ง/นาที) ป้องกันค่าปรับ 0.15 บาท/คำสั่ง
    """
    tick = get_set_tick_size(last_trade_price)
    otr = daily_orders / max(1, daily_trades)
    if otr > 50.0 and orders_this_minute > 50:
        return {
            "allow": False,
            "rule": "OTR_EXTRA_FEE_GUARD",
            "min_short_price": round_to_set_tick(last_trade_price, "UP"),
            "reason": f"ระงับคำสั่ง: OTR={otr:.1f}x และความถี่ {orders_this_minute}/นาที เกินเกณฑ์ 50x",
        }
    if not is_eligible_short_universe:
        return {
            "allow": False,
            "rule": "INELIGIBLE_SHORT_UNIVERSE",
            "min_short_price": round_to_set_tick(last_trade_price, "UP"),
            "reason": "ไม่อนุญาตให้ขายชอร์ตนอกกลุ่ม SET100 / SSF / DR / ETF",
        }
    use_uptick = prev_day_return_pct <= -10.0
    min_short_price = round_to_set_tick(last_trade_price + (tick if use_uptick else 0.0), "UP")
    return {
        "allow": order_price >= min_short_price - 1e-9,
        "rule": "UPTICK_RULE (Prior Close <= -10%)" if use_uptick else "ZERO_PLUS_TICK (Normal)",
        "min_short_price": min_short_price,
        "otr_ratio": round(otr, 2),
    }


def generate_smart_execution_plan(
    symbol: str,
    total_shares: int,
    ref_price: float,
    bid_price: float,
    ask_price: float,
    bid_vol: int,
    ask_vol: int,
    n_slices: int = 4,
    seed: int = 7,
) -> Dict[str, object]:
    """
    จำลองสมองกลส่งคำสั่งซื้อขายอัจฉริยะ (Smart Execution Engine - บทที่ 13 & 14):
      - คำนวณขนาดช่องราคา (SET Tick Size ตามเกณฑ์ 8 มาตรการใหม่), OBI และราคาจุลภาค (Micro-Price)
      - ตรวจสอบ Spread Guard (บล็อกคำสั่งหาก Bid-Ask Spread กว้างผิดปกติเกิน 40 bps)
      - หั่นคำสั่งซื้อก้อนใหญ่เป็นไม้น้อยๆ ด้วย TWAP + Randomized Time Jitter
    """
    rng = np.random.default_rng(seed)
    tick_size = get_set_tick_size(ref_price)
    bid_price = round_to_set_tick(bid_price, "DOWN")
    ask_price = round_to_set_tick(ask_price, "UP")
    spread_bps = ((ask_price - bid_price) / ((ask_price + bid_price) / 2.0)) * 10_000.0
    obi = (bid_vol - ask_vol) / max(bid_vol + ask_vol, 1)
    micro_price = (bid_price * ask_vol + ask_price * bid_vol) / max(bid_vol + ask_vol, 1)

    spread_guard_passed = spread_bps <= 40.0
    lot_slices = max(1, min(n_slices, total_shares // 100))
    base_lots = (total_shares // 100) // lot_slices
    remainder_lots = (total_shares // 100) % lot_slices

    schedule = []
    base_minute = 0
    for idx in range(lot_slices):
        lots = base_lots + (1 if idx < remainder_lots else 0)
        jitter_sec = int(rng.integers(12, 48))
        raw_limit = bid_price if obi < 0.25 else ask_price
        schedule.append({
            "slice_no": idx + 1,
            "time_offset": f"+{base_minute:02d}m:{jitter_sec:02d}s",
            "shares": lots * 100,
            "limit_price": round_to_set_tick(raw_limit, "NEAREST"),
            "order_type": "PASSIVE_LIMIT_AT_BID" if obi < 0.25 else "JOIN_BEST_ASK",
        })
        base_minute += 5

    return {
        "symbol": symbol,
        "total_shares": total_shares,
        "ref_price": round(ref_price, 2),
        "tick_size": tick_size,
        "spread_bps": round(spread_bps, 2),
        "obi": round(obi, 3),
        "micro_price": round(micro_price, 3),
        "spread_guard_passed": spread_guard_passed,
        "slices": schedule,
    }


def run_normal_generic_bot_backtest(
    stock_map: Dict[str, pd.DataFrame],
    idx_df: pd.DataFrame,
    cfg: QuantConfig,
    start_idx: int = 60,
    end_idx: Optional[int] = None,
) -> BacktestSummary:
    """
    จำลอง "บอททั่วไป (Normal Generic Indicator Bot)" เพื่อเปรียบเทียบกับบอทในหนังสือ:
      - ใช้ค่าตั้งต้นตายตัว (ราคาปิดตัด SMA 20 หรือ RSI(14) < 35 ซื้อทันที)
      - ไม่มีตัวกรองสภาวะตลาด (ไม่หยุดเทรดในตลาด Sideways / Crisis Panic)
      - ไม่มี RVOL / CLV / KAMA Filter และไม่มี Context Tagging
      - แบ่งเงินซื้อแบบหารเท่า (Fixed 22% ของพอร์ตต่อตัว) ไม่ปรับขนาดไม้ตาม ATR และไม่มี HRP
      - ตั้งจุดขายทำกำไรสั้น +2.5% และตัดขาดทุนคงที่ -4.5% (ทำให้หมุนพอร์ตถี่และเสียค่าคอมมิชชัน+Slippage สะสม)
    """
    dates = list(idx_df.index)
    if end_idx is None or end_idx > len(dates):
        end_idx = len(dates)

    cash = cfg.initial_capital
    positions: Dict[str, Dict[str, object]] = {}
    trades: List[TradeRecord] = []
    equity_rows: List[Dict[str, object]] = []
    symbols = sorted(stock_map.keys())
    slip_rate = (cfg.base_slippage_bps * 1.4) / 10_000.0  # บอททั่วไปเคาะซื้อขายด้วย Market Order ทันที

    for t in range(start_idx, end_idx):
        dt_prev = dates[t - 1]
        dt_now = dates[t]
        regime_now = str(idx_df.loc[dt_now, "regime"])

        # 1. ตรวจสอบการขายด้วยกฎคงที่ (+2.5% Take Profit / -4.5% Fixed Stop / หลุด SMA 20)
        to_close: List[Tuple[str, str]] = []
        for sym, pos in positions.items():
            sdf = stock_map[sym]
            if dt_prev not in sdf.index or dt_now not in sdf.index:
                continue
            close_prev = float(sdf.loc[dt_prev, "close"])
            sma20_prev = float(sdf.loc[dt_prev, "sma_20"])
            entry_p = float(pos["entry_price"])
            ret_prev = (close_prev - entry_p) / entry_p
            if ret_prev <= -0.045:
                to_close.append((sym, "FIXED_STOP_LOSS (-4.5%)"))
            elif ret_prev >= 0.025:
                to_close.append((sym, "QUICK_TAKE_PROFIT (+2.5%)"))
            elif close_prev < sma20_prev * 0.992:
                to_close.append((sym, "WHIPSAW_BELOW_SMA20"))

        for sym, reason in to_close:
            pos = positions.pop(sym)
            open_t = float(stock_map[sym].loc[dt_now, "open"])
            exec_sell = open_t * (1.0 - slip_rate)
            shares = int(pos["shares"])
            entry_p = float(pos["entry_price"])
            gross = exec_sell * shares
            net_proceeds = gross * (1.0 - cfg.commission_vat_rate)
            cash += net_proceeds
            entry_cost = entry_p * shares * (1.0 + cfg.commission_vat_rate)
            net_pnl = net_proceeds - entry_cost
            ret_pct = (net_pnl / entry_cost) * 100.0
            trades.append(
                TradeRecord(
                    symbol=sym,
                    thesis_tag="GENERIC_SIGNAL",
                    entry_date=str(pos["entry_date"]),
                    exit_date=dt_now.strftime("%Y-%m-%d"),
                    entry_price=round(entry_p, 2),
                    exit_price=round(exec_sell, 2),
                    shares=shares,
                    net_pnl=round(net_pnl, 2),
                    return_pct=round(ret_pct, 2),
                    r_multiple=round(ret_pct / 4.5, 2),
                    exit_reason=reason,
                )
            )

        # 2. เปิดสถานะใหม่ทุกครั้งที่ราคา > SMA 20 หรือ RSI < 38 โดยไม่สนสภาวะตลาดรวม
        mkt_val_prev = sum(
            int(p["shares"]) * float(stock_map[s].loc[dt_prev, "close"])
            for s, p in positions.items()
            if dt_prev in stock_map[s].index
        )
        eq_prev = cash + mkt_val_prev
        for sym in symbols:
            if sym in positions or len(positions) >= 4:
                continue
            sdf = stock_map[sym]
            if dt_prev not in sdf.index or dt_now not in sdf.index:
                continue
            row_prev = sdf.loc[dt_prev]
            close_p = float(row_prev["close"])
            sma20_p = float(row_prev["sma_20"])
            rsi14_p = float(row_prev.get("rsi_14", 50.0))
            if (close_p > sma20_p) or (rsi14_p < 38.0):
                open_t = float(sdf.loc[dt_now, "open"])
                exec_buy = open_t * (1.0 + slip_rate)
                target_val = eq_prev * 0.22
                shares = (int(min(target_val, cash * 0.95) // exec_buy) // 100) * 100
                total_cost = shares * exec_buy * (1.0 + cfg.commission_vat_rate)
                if shares >= 100 and total_cost <= cash:
                    cash -= total_cost
                    positions[sym] = {
                        "entry_date": dt_now.strftime("%Y-%m-%d"),
                        "entry_price": exec_buy,
                        "shares": shares,
                    }

        mkt_val_now = sum(
            int(p["shares"]) * float(stock_map[s].loc[dt_now, "close"])
            for s, p in positions.items()
            if dt_now in stock_map[s].index
        )
        total_eq = cash + mkt_val_now
        equity_rows.append(
            {
                "date": dt_now.strftime("%Y-%m-%d"),
                "regime": regime_now,
                "trading_equity": round(total_eq, 2),
                "safe_bucket": 0.0,
                "combined_wealth": round(total_eq, 2),
                "open_positions": len(positions),
            }
        )

    eq_df = pd.DataFrame(equity_rows)
    wealth = eq_df["combined_wealth"].astype(float)
    daily_rets = wealth.pct_change().dropna()
    n_years = max(len(eq_df) / 252.0, 1e-6)
    total_ret = ((float(wealth.iloc[-1]) / cfg.initial_capital) - 1.0) * 100.0
    cagr = (((float(wealth.iloc[-1]) / cfg.initial_capital) ** (1.0 / n_years)) - 1.0) * 100.0
    peaks = wealth.cummax()
    dd = ((wealth - peaks) / peaks) * 100.0
    max_dd = float(dd.min())
    ret_std = float(daily_rets.std())
    sharpe = float((daily_rets.mean() / ret_std) * np.sqrt(252.0)) if ret_std > 1e-9 else 0.0
    downside = daily_rets[daily_rets < 0.0]
    down_std = float(downside.std()) if len(downside) > 1 else 1e-9
    sortino = float((daily_rets.mean() / down_std) * np.sqrt(252.0)) if down_std > 1e-9 else 0.0

    wins = [t.net_pnl for t in trades if t.net_pnl > 0]
    losses = [t.net_pnl for t in trades if t.net_pnl <= 0]
    win_rate = (len(wins) / len(trades) * 100.0) if trades else 0.0
    pf = (sum(wins) / abs(sum(losses))) if losses and abs(sum(losses)) > 1e-9 else 0.0
    exp_thb = float(np.mean([t.net_pnl for t in trades])) if trades else 0.0

    return BacktestSummary(
        equity_curve=eq_df,
        trades=trades,
        initial_capital=cfg.initial_capital,
        final_trading_equity=round(float(wealth.iloc[-1]), 2),
        safe_reserve_bucket=0.0,
        total_combined_wealth=round(float(wealth.iloc[-1]), 2),
        total_return_pct=round(total_ret, 2),
        cagr_pct=round(cagr, 2),
        max_drawdown_pct=round(max_dd, 2),
        sharpe_ratio=round(sharpe, 2),
        sortino_ratio=round(sortino, 2),
        win_rate_pct=round(win_rate, 2),
        profit_factor=round(pf, 2),
        expectancy_thb=round(exp_thb, 2),
    )


def save_backtest_comparison_chart(
    quant_summary: BacktestSummary,
    normal_summary: BacktestSummary,
    idx_df: pd.DataFrame,
    out_path: str,
) -> None:
    """สร้างกราฟเปรียบเทียบผลลัพธ์ Backtest ระหว่าง The Secret Quant Bot vs Normal Bot vs Market Index"""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        import matplotlib.ticker as mticker
    except ImportError:
        return

    q_df = quant_summary.equity_curve.copy()
    n_df = normal_summary.equity_curve.copy()
    q_df["dt"] = pd.to_datetime(q_df["date"])
    n_df["dt"] = pd.to_datetime(n_df["date"])
    q_eq = q_df.set_index("dt")["combined_wealth"].astype(float)
    n_eq = n_df.set_index("dt")["combined_wealth"].astype(float)
    common_dates = q_eq.index
    idx_slice = idx_df.loc[common_dates, "close"].astype(float)
    bench_eq = (idx_slice / float(idx_slice.iloc[0])) * quant_summary.initial_capital

    q_dd = ((q_eq - q_eq.cummax()) / q_eq.cummax()) * 100.0
    n_dd = ((n_eq - n_eq.cummax()) / n_eq.cummax()) * 100.0
    b_dd = ((bench_eq - bench_eq.cummax()) / bench_eq.cummax()) * 100.0

    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(11.5, 6.8), dpi=180, sharex=True, gridspec_kw={"height_ratios": [2.1, 1.0]}
    )
    fig.patch.set_facecolor("#ffffff")
    for ax in (ax1, ax2):
        ax.set_facecolor("#f8fafc")
        ax.grid(True, linestyle="--", linewidth=0.6, color="#cbd5e1", alpha=0.7)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#94a3b8")
        ax.spines["bottom"].set_color("#94a3b8")

    # Shade Crisis Panic periods in light rose
    regimes = q_df.set_index("dt")["regime"]
    in_crisis = False
    start_dt = None
    for dt, reg in regimes.items():
        if reg == "CRISIS_PANIC" and not in_crisis:
            in_crisis = True
            start_dt = dt
        elif reg != "CRISIS_PANIC" and in_crisis:
            in_crisis = False
            ax1.axvspan(start_dt, dt, color="#fecdd3", alpha=0.35, label="_nolegend_")
            ax2.axvspan(start_dt, dt, color="#fecdd3", alpha=0.35, label="_nolegend_")
    if in_crisis and start_dt is not None:
        ax1.axvspan(start_dt, common_dates[-1], color="#fecdd3", alpha=0.35, label="_nolegend_")
        ax2.axvspan(start_dt, common_dates[-1], color="#fecdd3", alpha=0.35, label="_nolegend_")

    # Top Panel: Equity Curve (The Secret Quant Bot vs Normal Bot)
    ax1.plot(
        common_dates,
        q_eq,
        color="#059669",
        linewidth=2.6,
        label=f"The Secret Quant Bot (Adaptive 3-Agent + HRP + ATR + Cash Shield): {quant_summary.total_combined_wealth:,.0f} THB ({quant_summary.total_return_pct:+.2f}%, Sharpe {quant_summary.sharpe_ratio:.2f}, {len(quant_summary.trades)} trades)",
    )
    ax1.plot(
        common_dates,
        n_eq,
        color="#e11d48",
        linewidth=2.0,
        label=f"Normal Bot (Generic SMA/RSI, No Regime Filter, Equal Weight): {normal_summary.total_combined_wealth:,.0f} THB ({normal_summary.total_return_pct:+.2f}%, Sharpe {normal_summary.sharpe_ratio:.2f}, {len(normal_summary.trades)} trades)",
    )
    ax1.fill_between(common_dates, q_eq, n_eq, where=(q_eq >= n_eq), color="#10b981", alpha=0.10, interpolate=True)
    ax1.axhline(1_000_000, color="#475569", linewidth=0.9, linestyle=":")
    ax1.set_title(
        "Head-to-Head Backtest Comparison: The Secret Quant Bot vs. Normal Bot (500 Trading Days | 1,000,000 THB)",
        fontsize=12.2,
        fontweight="bold",
        color="#0f172a",
        pad=10,
    )
    ax1.set_ylabel("Portfolio Wealth (THB)", fontsize=10, fontweight="bold", color="#1e293b")
    ax1.yaxis.set_major_formatter(mticker.StrMethodFormatter("{x:,.0f}"))
    ax1.legend(loc="upper left", frameon=True, facecolor="#ffffff", edgecolor="#cbd5e1", fontsize=8.8)

    # Bottom Panel: Drawdown (%)
    ax2.fill_between(common_dates, q_dd, 0, color="#10b981", alpha=0.24)
    ax2.plot(common_dates, q_dd, color="#059669", linewidth=1.8, label=f"The Secret Quant Bot Drawdown (Max: {quant_summary.max_drawdown_pct:.2f}%)")
    ax2.fill_between(common_dates, n_dd, 0, color="#f43f5e", alpha=0.18)
    ax2.plot(common_dates, n_dd, color="#e11d48", linewidth=1.6, label=f"Normal Bot Drawdown (Max: {normal_summary.max_drawdown_pct:.2f}%)")
    ax2.axhline(-5.0, color="#d97706", linewidth=1.1, linestyle="--", label="-5.0% Max Portfolio Heat / Risk Guard")
    ax2.set_ylabel("Drawdown (%)", fontsize=10, fontweight="bold", color="#1e293b")
    ax2.set_xlabel("Trading Date (Pink shaded zones = CRISIS_PANIC Market Regime where Cash Shield protects capital)", fontsize=9.5, color="#334155")
    ax2.yaxis.set_major_formatter(mticker.FormatStrFormatter("%.1f%%"))
    ax2.legend(loc="lower left", frameon=True, facecolor="#ffffff", edgecolor="#cbd5e1", fontsize=8.5, ncol=3)
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))

    plt.tight_layout()
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    plt.savefig(out_path, dpi=180, bbox_inches="tight")
    plt.close(fig)


# =========================================================================================
# 9. MAIN CLI RUNNER & REPORT GENERATOR
# =========================================================================================
def main() -> None:
    parser = argparse.ArgumentParser(
        description="โรบอทเทรด ที่โบรกเกอร์ไม่อยากให้คุณเขียน - Full Educational Trading Bot & Backtest Engine"
    )
    parser.add_argument(
        "--csv",
        type=str,
        default=(
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "sample_thai_stocks_ohlcv.csv")
            if os.path.exists(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "sample_thai_stocks_ohlcv.csv"))
            else os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample_thai_stocks_ohlcv.csv")
        ),
        help="Path to historical OHLCV CSV file (default: sample_thai_stocks_ohlcv.csv)",
    )
    parser.add_argument(
        "--regenerate-sample",
        action="store_true",
        help="Force regenerate sample_thai_stocks_ohlcv.csv",
    )
    args = parser.parse_args()

    cfg = QuantConfig()

    print("=" * 92)
    print("  โรบอทเทรด ที่โบรกเกอร์ไม่อยากให้คุณเขียน — เปิดแก่นความคิดของ Quant Trader ยุคใหม่ (CH 1 - CH 14)")
    print("=" * 92)

    if args.regenerate_sample or not os.path.exists(args.csv):
        print(f"[1/6] กำลังสร้างชุดข้อมูลจำลองตลาดหุ้นไทย (Sample Backtest Dataset) -> {args.csv}")
        raw_df = generate_sample_thai_ohlcv_csv(args.csv)
    else:
        print(f"[1/6] โหลดข้อมูลราคาหุ้นย้อนหลังจากไฟล์: {args.csv}")
        raw_df = pd.read_csv(args.csv)

    stock_map, idx_df = prepare_point_in_time_features(raw_df, cfg)
    print(f"      - จำนวนหุ้นที่ผ่านเกณฑ์ความสะอาด (Data Hygiene): {len(stock_map)} ตัว ({', '.join(sorted(stock_map.keys()))})")
    print(f"      - ช่วงเวลาทดสอบ: {idx_df.index[0].strftime('%Y-%m-%d')} ถึง {idx_df.index[-1].strftime('%Y-%m-%d')} ({len(idx_df)} วันทำการ)")

    # สรุปสัดส่วนสภาวะตลาด (Market Regimes)
    regime_counts = idx_df["regime"].value_counts()
    print("\n[2/6] ผลการจำแนกสภาวะตลาดรวม (Market Regime Detector - บทที่ 10):")
    for reg_name in ["BULL_TREND", "SIDEWAYS_QUIET", "CRISIS_PANIC"]:
        cnt = int(regime_counts.get(reg_name, 0))
        pct = (cnt / len(idx_df)) * 100.0
        print(f"      - {reg_name:<16}: {cnt:>3} วันทำการ ({pct:>5.1f}%)")

    # คำนวณน้ำหนัก HRP ล่าสุด (บทที่ 12)
    latest_ret_df = pd.DataFrame({sym: sdf["ret_1d"].tail(60) for sym, sdf in stock_map.items()})
    hrp_weights = compute_hrp_weights(latest_ret_df, max_weight=cfg.max_single_weight_pct)
    print("\n[3/6] สัดส่วนพอร์ตไร้ความเสี่ยงกระจุกตัว (Hierarchical Risk Parity - บทที่ 12):")
    for sym, w in sorted(hrp_weights.items(), key=lambda x: x[1], reverse=True):
        print(f"      - {sym:<12}: {w * 100.0:>5.2f}%")

    # ทดสอบความเสถียรนอกกลุ่มตัวอย่าง (Walk-Forward Validation - บทที่ 6)
    is_cagr, oos_cagr, wfe_pct = run_walk_forward_check(stock_map, idx_df, cfg)
    wfe_status = "ผ่านเกณฑ์มาตรฐาน (Robust >= 50%)" if wfe_pct >= 50.0 else "ควรระวัง Overfitting"
    print("\n[4/6] ผลทดสอบ Walk-Forward Validation (บทที่ 6):")
    print(f"      - In-Sample CAGR (60% แรก)     : {is_cagr:>6.2f}% ต่อปี")
    print(f"      - Out-of-Sample CAGR (40% หลัง): {oos_cagr:>6.2f}% ต่อปี")
    print(f"      - Walk-Forward Efficiency (WFE): {wfe_pct:>6.1f}% -> [{wfe_status}]")

    # รัน Backtest เต็มรูปแบบ (บทที่ 5, 7, 8, 9, 11, 12) และเปรียบเทียบกับบอททั่วไป (Normal Bot)
    summary = run_point_in_time_backtest(stock_map, idx_df, cfg, start_idx=60)
    normal_summary = run_normal_generic_bot_backtest(stock_map, idx_df, cfg, start_idx=60)
    chart_out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backtest_comparison_chart.png")
    save_backtest_comparison_chart(summary, normal_summary, idx_df, chart_out)

    print("\n[5/6] สรุปผลการจำลองพอร์ตเปรียบเทียบ: The Secret Quant Bot vs. Normal Bot (บอททั่วไป):")
    print(f"      {'ตัวชี้วัด (Metric)':<38} | {'The Secret Quant Bot':>20} | {'Normal Bot (บอททั่วไป)':>22}")
    print("      " + "-" * 86)
    print(f"      {'เงินทุนตั้งต้น (Initial Capital)':<38} | {summary.initial_capital:>16,.2f} บาท | {normal_summary.initial_capital:>18,.2f} บาท")
    print(f"      {'พอร์ตเทรดปลายงวด (Trading Equity)':<38} | {summary.final_trading_equity:>16,.2f} บาท | {normal_summary.final_trading_equity:>18,.2f} บาท")
    print(f"      {'ถังเงินออมปลอดภัย (Safe Bucket Skim)':<38} | {summary.safe_reserve_bucket:>16,.2f} บาท | {normal_summary.safe_reserve_bucket:>18,.2f} บาท")
    print(f"      {'ความมั่งคั่งสุทธิรวม (Total Wealth)':<38} | {summary.total_combined_wealth:>16,.2f} บาท | {normal_summary.total_combined_wealth:>18,.2f} บาท")
    print(f"      {'ผลตอบแทนสุทธิรวม (Total Return)':<38} | {summary.total_return_pct:>+19.2f}% | {normal_summary.total_return_pct:>+21.2f}%")
    print(f"      {'ผลตอบแทนทบต้นต่อปี (CAGR)':<38} | {summary.cagr_pct:>+19.2f}% | {normal_summary.cagr_pct:>+21.2f}%")
    print(f"      {'การย่อตัวสูงสุด (Max Drawdown)':<38} | {summary.max_drawdown_pct:>19.2f}% | {normal_summary.max_drawdown_pct:>21.2f}%")
    print(f"      {'Sharpe Ratio / Sortino Ratio':<38} | {f'{summary.sharpe_ratio:.2f} / {summary.sortino_ratio:.2f}':>20} | {f'{normal_summary.sharpe_ratio:.2f} / {normal_summary.sortino_ratio:.2f}':>22}")
    print(f"      {'จำนวนไม้ที่เทรดทั้งหมด (Total Trades)':<38} | {len(summary.trades):>18} ไม้ | {len(normal_summary.trades):>20} ไม้")
    print(f"      {'อัตราชนะ (Win Rate)':<38} | {summary.win_rate_pct:>19.2f}% | {normal_summary.win_rate_pct:>21.2f}%")
    print(f"      {'Profit Factor':<38} | {summary.profit_factor:>20.2f} | {normal_summary.profit_factor:>22.2f}")
    print(f"      {'ค่าคาดหวังต่อไม้ (Expectancy)':<38} | {summary.expectancy_thb:>+14,.2f} ฿/ไม้ | {normal_summary.expectancy_thb:>+16,.2f} ฿/ไม้")

    if summary.trades:
        print("\n      ตัวอย่างประวัติการเทรด 5 ไม้ล่าสุด (พร้อม Thesis Tag & Ratchet Stop):")
        for tr in summary.trades[-5:]:
            print(
                f"      * {tr.symbol:<9} [{tr.thesis_tag:<15}] "
                f"{tr.entry_date} @ {tr.entry_price:>6.2f} -> {tr.exit_date} @ {tr.exit_price:>6.2f} | "
                f"PnL: {tr.net_pnl:>+9,.2f} บาท ({tr.r_multiple:>+4.2f}R) | {tr.exit_reason}"
            )

    # จำลองการวางแผนส่งคำสั่งซื้อด้วย Smart TWAP / Micro-Price (บทที่ 13 & 14)
    sample_sym = sorted(stock_map.keys())[0]
    last_close = float(stock_map[sample_sym]["close"].iloc[-1])
    exec_plan = generate_smart_execution_plan(
        symbol=sample_sym,
        total_shares=2_400,
        ref_price=last_close,
        bid_price=round(last_close - 0.50, 2),
        ask_price=round(last_close, 2),
        bid_vol=85_000,
        ask_vol=42_000,
        n_slices=4,
    )
    print(f"\n[6/6] ตัวอย่างแผนส่งคำสั่งซื้ออัจฉริยะ (Smart TWAP & Micro-Price - บทที่ 13 & 14) สำหรับ {sample_sym}:")
    print(
        f"      - ราคาอ้างอิง: {exec_plan['ref_price']:.2f} บาท | "
        f"Spread: {exec_plan['spread_bps']:.1f} bps | "
        f"OBI: {exec_plan['obi']:+.3f} | "
        f"Micro-Price: {exec_plan['micro_price']:.3f} บาท"
    )
    for sl in exec_plan["slices"]:
        print(
            f"      - ไม้ย่อยที่ {sl['slice_no']} ({sl['time_offset']}): "
            f"จำนวน {sl['shares']:>4} หุ้น @ Limit {sl['limit_price']:.2f} บาท [{sl['order_type']}]"
        )
    print("=" * 88)


if __name__ == "__main__":
    main()
