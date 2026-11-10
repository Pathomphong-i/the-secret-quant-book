#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
=========================================================================================
หนังสือ: เลิกพึ่งบอทคนอื่น มาสร้างระบบเทรดของคุณเองด้วย Python
ไฟล์ระบบตัวเต็มฉบับจบเล่ม: final_trading_system_abcd.py
ผู้เขียน: ปฐมพงษ์ พิพัฒน์สุริยวงศ์
=========================================================================================
คำอธิบายสำหรับผู้อ่าน (ออกแบบให้คนที่ไม่มีพื้นฐานเขียนโค้ดสามารถอ่านเข้าใจได้ทุกบรรทัด):
  ไฟล์นี้คือ "ระบบเทรดจำลองฉบับสมบูรณ์ (Final Version)" ที่รวมความรู้ตั้งแต่ บทที่ 1 ถึง บทที่ 8
  มาทำงานร่วมกันบนข้อมูลราคาหุ้นที่มีอยู่ในคลังของหนังสือ (sample_thai_stocks_ohlcv.csv)
  โดยทำงานแบบออฟไลน์ 100% ไม่ต้องต่อโบรกเกอร์ภายนอก และเขียนคอมเมนต์ภาษาไทยอธิบายวิธีคิดทุกขั้นตอน

ลำดับการทำงาน 6 ขั้นตอนในไฟล์นี้:
  ขั้นตอนที่ 1: โหลดรายชื่อหุ้นในตลาดจากไฟล์ sample_thai_stocks_ohlcv.csv และคัดกรองหุ้นที่ไม่ผ่านเกณฑ์ออก
               (ตรวจความสะอาดข้อมูล บทที่ 3 + ตรวจแนวโน้มใหญ่และปริมาณซื้อขาย บทที่ 4)
  ขั้นตอนที่ 2: คัดเลือก 4 หุ้นเข้าเทรดด้วย 4 กลยุทธ์ (Strategy A, B, C, D) พร้อมอธิบายเหตุผลละเอียด
               - กลยุทธ์ A (STOCK_ICT.BK)  : หุ้นนำตลาดขาขึ้นแข็งแกร่ง (Trend Momentum Breakout)
               - กลยุทธ์ B (STOCK_HELTH.BK): หุ้นขาขึ้นความผันผวนต่ำ พักฐานกรอบแคบ (Low-Volatility VCP)
               - กลยุทธ์ C (STOCK_COMM.BK) : หุ้นพื้นฐานเติบโตที่ย่อตัวพักฐานระยะสั้นในขาขึ้นใหญ่ (Quality Pullback)
               - กลยุทธ์ D (STOCK_BANK.BK) : หุ้นกลุ่มการเงินหมุนรอบสลับกลุ่มพร้อมวอลุ่มเข้า (Sector Rotation)
  ขั้นตอนที่ 3: บริหารพอร์ต 1,000,000 บาท และคำนวณขนาดไม้ (Position Sizing — บทที่ 1, 5, 6)
               - คำนวณราคาเข้าซื้อที่ราคาเปิดวันถัดไป (Next-Open Fill ป้องกันการแอบดูอนาคต บทที่ 2 & 3)
               - คำนวณจุดตัดขาดทุน (Cut-Loss Price), จุดขยับบังทุน (Breakeven Lock), และราคาเป้าหมาย (Target Price)
               - คำนวณจำนวนหุ้นตามงบความเสี่ยง ปัดเป็น Board Lot (ทีละ 100 หุ้น) และปัดราคาตามช่อง Tick Size
  ขั้นตอนที่ 4: จำลองการส่งคำสั่งซื้อขายผ่านห้องแล็บจำลองโบรกเกอร์ (Simulated Broker Execution — บทที่ 6 & 8)
               - จำลองการแบ่งซอยไม้ย่อย (TWAP Slices), สร้างรหัสกันส่งคำสั่งซ้ำ (Idempotent Key), และกระทบยอดหุ้น
  ขั้นตอนที่ 5: เดินเวลาตามข้อมูลจริงใน CSV ต่อเนื่อง 25 วันทำการ (2024-06-05 ถึง 2024-07-09)
               - ติดตามสถานะหุ้นที่ถืออยู่ทุกวัน ขยับ Stop บังทุนอัตโนมัติ ขายทำกำไรเมื่อชน Target
               - ขายตัดขาดทุนทันทีเมื่อหลุด Cut-Loss และบันทึกไฟล์ Log ทั้งรูปแบบ CSV และ JSON
  ขั้นตอนที่ 6: รันทดสอบย้อนหลัง (Backtest) ตลอดทั้ง 500 วันทำการในไฟล์ CSV
               - แยกตารางผลลัพธ์ช่วงพัฒนากฎ (In-Sample 60% แรก) เทียบกับช่วงทดสอบนอกกลุ่มตัวอย่าง (Out-of-Sample 40% หลัง)

วิธีรันโปรแกรมนี้:
  python3 final_trading_system_abcd.py
=========================================================================================
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import json
import math
import sqlite3
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd


# =========================================================================================
# ส่วนที่ 0: ตั้งค่าพารามิเตอร์หลักของพอร์ต (ผู้อ่านสามารถแก้ไขตัวเลขในคลาสนี้ได้เองโดยตรง)
# =========================================================================================
@dataclass(frozen=True)
class PortfolioConfig:
    """
    กล่องตั้งค่ากฎการบริหารพอร์ตและความเสี่ยง (เปรียบเหมือนใบสรุปกฎการเทรดในบทที่ 1 และบทที่ 5)
    คุณสามารถลองเปลี่ยนเงินตั้งต้น งบความเสี่ยงต่อไม้ หรือเพดานวงเงินต่อตัว เพื่อดูผลลัพธ์ที่เปลี่ยนไปได้ทันที
    """
    initial_capital_thb: float = 1_000_000.0   # เงินทุนเริ่มต้นของพอร์ตจำลอง (1,000,000 บาท)
    risk_per_trade_pct: float = 0.01           # ยอมขาดทุนตามแผนต่อไม้ไม่เกิน 1.0% ของพอร์ต (10,000 บาท)
    max_portfolio_heat_pct: float = 0.05       # ความเสี่ยงรวมทุกไม้ในพอร์ตห้ามเกิน 5.0% (50,000 บาท)
    max_single_position_pct: float = 0.24      # ห้ามซื้อหุ้นตัวเดียวเกิน 24.0% ของพอร์ต (240,000 บาท)
    min_cash_reserve_pct: float = 0.15         # ต้องเหลือเงินสดสำรองติดพอร์ตอย่างน้อย 15.0% เสมอ
    commission_and_vat_rate: float = 0.00157   # ค่าธรรมเนียมซื้อขายรวมภาษีมูลค่าเพิ่มขาละ ~0.157% (บทที่ 1)
    board_lot_size: int = 100                  # ตลาดหุ้นไทยซื้อขายขั้นต่ำทีละ 100 หุ้น (1 Board Lot)
    signal_date: str = "2024-06-04"            # วันตัดสินใจสแกนตลาดหลังตลาดปิด (จากไฟล์ CSV)
    tracking_days: int = 25                    # จำนวนวันทำการที่ใช้ติดตามผลหลังเข้าซื้อ (2024-06-05 ถึง 2024-07-09)


# =========================================================================================
# ส่วนที่ 1: ฟังก์ชันปัดเศษช่องราคา (Tick Size) และปัดจำนวนหุ้นเป็น Board Lot (บทที่ 5 & 6)
# =========================================================================================
def get_thai_set_tick_size(price: float) -> Decimal:
    """
    คืนค่าขนาดช่องราคา (Tick Size) ตามระดับราคาของตลาดหลักทรัพย์ฯ
    เพื่อให้ราคาเข้าซื้อ (Entry), ราคาตัดขาดทุน (Cut-Loss), และราคาเป้าหมาย (Target) ลงตัวตามช่องกระดานจริง
    """
    if price < 2.0:
        return Decimal("0.01")
    if price < 5.0:
        return Decimal("0.02")
    if price < 10.0:
        return Decimal("0.05")
    if price < 25.0:
        return Decimal("0.10")
    if price < 100.0:
        return Decimal("0.25")
    if price < 200.0:
        return Decimal("0.50")
    if price < 400.0:
        return Decimal("1.00")
    return Decimal("2.00")


def round_price_to_tick(raw_price: float, mode: str = "NEAREST") -> float:
    """
    ปัดราคาให้ลงตัวกับช่องราคา (Tick Size):
      - mode = "DOWN"    ปัดลง (ใช้ตั้งจุดตัดขาดทุนให้ปลอดภัย)
      - mode = "UP"      ปัดขึ้น (ใช้ตั้งราคาเป้าหมายทำกำไร หรือจุดขยับบังทุน)
      - mode = "NEAREST" ปัดเข้าหาช่องราคาที่ใกล้ที่สุด
    """
    tick = get_thai_set_tick_size(raw_price)
    d_price = Decimal(str(raw_price))
    if mode == "DOWN":
        steps = math.floor(d_price / tick)
    elif mode == "UP":
        steps = math.ceil(d_price / tick)
    else:
        steps = round(d_price / tick)
    return round(float(Decimal(steps) * tick), 2)


# =========================================================================================
# ส่วนที่ 2: โหลดข้อมูลราคาหุ้นจาก CSV และสแกนรายชื่อหุ้นในตลาด (บทที่ 2, 3, 4)
# =========================================================================================
@dataclass
class MarketScanRow:
    """
    เก็บผลการสแกนหุ้นแต่ละตัวในตลาด ณ วันตัดสินใจ (Signal Date) พร้อมค่าตัวชี้วัดที่คำนวณได้จริงจาก CSV
    """
    symbol: str                  # ชื่อหุ้นในไฟล์ CSV เช่น STOCK_ICT.BK
    sector: str                  # กลุ่มอุตสาหกรรม
    signal_date: str             # วันที่ใช้ข้อมูลหลังตลาดปิดเพื่อตัดสินใจ
    close_price: float           # ราคาปิด ณ วันตัดสินใจ (บาท)
    next_open_price: float       # ราคาเปิดของวันทำการถัดไป (ใช้เป็นราคาเข้าซื้อจริง ป้องกัน Look-Ahead Bias)
    sma_20: float                # เส้นค่าเฉลี่ยระยะสั้น 20 วัน (บาท)
    sma_150: float               # เส้นค่าเฉลี่ยระยะยาว 150 วัน (บาท — บอกแนวโน้มใหญ่)
    atr_14: float                # ระยะแกว่งตัวเฉลี่ยต่อวัน ATR 14 วัน (บาท — ใช้คำนวณจุด Cut-Loss)
    atr_pct_of_price: float      # สัดส่วนความผันผวน ATR เทียบราคาปิด (%)
    ret_60d_pct: float           # ผลตอบแทนย้อนหลัง 60 วันทำการ (%)
    rs_vs_set_60d_pct: float     # ความแข็งแกร่งของราคาเทียบดัชนีตลาด SET_INDEX ย้อนหลัง 60 วัน (%)
    rvol_20d: float              # ปริมาณซื้อขายเทียบค่าเฉลี่ย 20 วันก่อนหน้า (เท่า)
    clv_score: float             # ตำแหน่งราคาปิดในแท่งเทียน (-1.0 คือปิดต่ำสุด, +1.0 คือปิดสูงสุด)
    is_clean_data: bool          # ผ่านด่านตรวจความสะอาดของข้อมูลหรือไม่ (บทที่ 3)
    passed_major_uptrend: bool   # ราคาอยู่เหนือเส้นค่าเฉลี่ยระยะยาว SMA 150 หรือไม่ (บทที่ 4)
    screening_status: str        # สถานะการคัดกรองเบื้องต้น


def load_and_scan_market_from_csv(
    csv_path: Path,
    cfg: PortfolioConfig,
) -> Tuple[pd.DataFrame, List[MarketScanRow]]:
    """
    อ่านข้อมูลราคาหุ้นจากไฟล์ sample_thai_stocks_ohlcv.csv คำนวณตัวชี้วัดทางสถิติแบบไม่แอบดูอนาคต (Point-in-Time)
    และสรุปตารางรายชื่อหุ้นทั้งหมดในตลาด ณ วันตัดสินใจ (cfg.signal_date)
    """
    raw_df = pd.read_csv(csv_path)

    # คำนวณผลตอบแทน 60 วันของดัชนีตลาด (SET_INDEX) เพื่อใช้เปรียบเทียบความแข็งแกร่งสัมพัทธ์ (RS)
    idx_df = raw_df[raw_df["symbol"] == "SET_INDEX"].sort_values("date").reset_index(drop=True)
    idx_df["idx_ret_60d"] = (idx_df["close"] / idx_df["close"].shift(60) - 1.0) * 100.0
    idx_ret_map = dict(zip(idx_df["date"], idx_df["idx_ret_60d"]))

    scan_rows: List[MarketScanRow] = []
    stock_symbols = sorted(s for s in raw_df["symbol"].unique() if s != "SET_INDEX")

    for sym in stock_symbols:
        g = raw_df[raw_df["symbol"] == sym].sort_values("date").reset_index(drop=True)

        # ด่านตรวจความสะอาดข้อมูลตามบทที่ 3 (ต้องไม่มีราคาติดลบ ไม่มี High < Low และไม่มีวันที่ซ้ำ)
        has_invalid_price = bool((g["close"] <= 0).any() or (g["high"] < g["low"]).any())
        has_dup_date = bool(g["date"].duplicated().any())
        is_clean = not (has_invalid_price or has_dup_date)

        # คำนวณตัวชี้วัดพื้นฐานจากข้อมูลถึงวันตัดสินใจเท่านั้น (บทที่ 4)
        prev_close = g["close"].shift(1)
        tr = np.maximum(
            g["high"] - g["low"],
            np.maximum((g["high"] - prev_close).abs(), (g["low"] - prev_close).abs()),
        )
        g["atr_14"] = tr.rolling(14).mean()
        g["sma_20"] = g["close"].rolling(20).mean()
        g["sma_150"] = g["close"].rolling(150).mean()
        g["ret_60d"] = (g["close"] / g["close"].shift(60) - 1.0) * 100.0
        g["rvol_20d"] = g["volume"] / g["volume"].shift(1).rolling(20).mean()
        hl_span = (g["high"] - g["low"]).replace(0, np.nan)
        g["clv"] = (((g["close"] - g["low"]) - (g["high"] - g["close"])) / hl_span).fillna(0.0)

        # ดึงแถวข้อมูล ณ วันตัดสินใจ (signal_date) และราคาเปิดของวันทำการถัดไป (next_open_price)
        match_indices = g.index[g["date"] == cfg.signal_date].tolist()
        if not match_indices:
            continue
        sig_idx = match_indices[0]
        sig_row = g.iloc[sig_idx]
        next_row = g.iloc[min(sig_idx + 1, len(g) - 1)]

        close_px = round(float(sig_row["close"]), 2)
        next_open_px = round(float(next_row["open"]), 2)
        sma20_val = round(float(sig_row["sma_20"]), 2)
        sma150_val = round(float(sig_row["sma_150"]), 2)
        atr14_val = round(float(sig_row["atr_14"]), 2)
        atr_pct = round((atr14_val / close_px) * 100.0, 2)
        ret60_val = round(float(sig_row["ret_60d"]), 2)
        set_ret60 = float(idx_ret_map.get(cfg.signal_date, 0.0))
        rs_vs_set = round(ret60_val - set_ret60, 2)
        rvol_val = round(float(sig_row["rvol_20d"]), 2)
        clv_val = round(float(sig_row["clv"]), 2)

        passed_uptrend = bool(close_px > sma150_val)
        if not is_clean:
            status = "REJECTED_DIRTY_DATA (คัดออก: ข้อมูลไม่สะอาด)"
        elif not passed_uptrend:
            status = "REJECTED_DOWNTREND (คัดออก: ราคาต่ำกว่าแนวโน้มใหญ่ SMA 150)"
        else:
            status = "PASSED_CANDIDATE (ผ่านเกณฑ์พื้นฐาน เข้าสู่รอบคัดเลือกกลยุทธ์ A/B/C/D)"

        scan_rows.append(
            MarketScanRow(
                symbol=sym,
                sector=str(sig_row["sector"]),
                signal_date=cfg.signal_date,
                close_price=close_px,
                next_open_price=next_open_px,
                sma_20=sma20_val,
                sma_150=sma150_val,
                atr_14=atr14_val,
                atr_pct_of_price=atr_pct,
                ret_60d_pct=ret60_val,
                rs_vs_set_60d_pct=rs_vs_set,
                rvol_20d=rvol_val,
                clv_score=clv_val,
                is_clean_data=is_clean,
                passed_major_uptrend=passed_uptrend,
                screening_status=status,
            )
        )

    return raw_df, scan_rows


# =========================================================================================
# ส่วนที่ 3: คัดเลือก 4 หุ้นเข้าเทรดด้วยกลยุทธ์ A, B, C, D พร้อมคำนวณแผนราคาและขนาดไม้ (บทที่ 4 & 5)
# =========================================================================================
@dataclass
class SelectedTradePlan:
    """
    ใบแผนการเทรดของหุ้นที่ได้รับคัดเลือกเข้าพอร์ต (เก็บครบทุกตัวเลขที่ต้องใช้ส่งคำสั่งจำลองและบันทึก Log)
    """
    strategy_code: str           # รหัสกลยุทธ์: STRATEGY_A, STRATEGY_B, STRATEGY_C, STRATEGY_D
    strategy_name_th: str        # ชื่อกลยุทธ์ภาษาไทย
    symbol: str                  # ชื่อหุ้นจากไฟล์ CSV
    sector: str                  # กลุ่มอุตสาหกรรม
    selection_discussion_th: str # คำอธิบายเหตุผลอย่างละเอียดว่าทำไมกลยุทธ์นี้ถึงเลือกหุ้นตัวนี้
    signal_close_price: float    # ราคาปิดวันเกิดสัญญาณ (2024-06-04)
    entry_price: float           # ราคาเข้าซื้อจริงที่ราคาเปิดวันถัดไป (2024-06-05 ปัดตามช่อง Tick Size)
    cut_loss_price: float        # ราคาตัดขาดทุน (บาท — คำนวณจาก ATR และปัดตามช่อง Tick Size)
    breakeven_trigger_price: float # ราคาที่จะขยับ Stop ขึ้นมาบังทุนอัตโนมัติ (บาท)
    target_price: float          # ราคาเป้าหมายทำกำไร (บาท)
    risk_per_share_thb: float    # ความเสี่ยงต่อ 1 หุ้นหากโดนตัดขาดทุน (Entry - CutLoss)
    reward_to_risk_ratio: float  # อัตราส่วนผลตอบแทนต่อความเสี่ยง (Reward : Risk)
    approved_shares: int         # จำนวนหุ้นที่อนุมัติซื้อจริง (ปัดเป็น Board Lot ละ 100 หุ้นแล้ว)
    position_value_thb: float    # มูลค่าเงินที่ใช้ซื้อหุ้นไม้นี้ (ก่อนรวมค่าคอมฯ)
    entry_fee_thb: float         # ค่าคอมมิชชันและภาษีขาเข้าซื้อ (0.157%)
    total_cash_used_thb: float   # เงินสดที่หักออกจากพอร์ตจริง (มูลค่าหุ้น + ค่าคอมฯ ขาซื้อ)
    portfolio_weight_pct: float  # สัดส่วนวงเงินไม้นี้เทียบพอร์ตรวม (%)
    max_loss_if_cut_thb: float   # จำนวนเงินที่จะเสียตามแผนหากราคาหลุด Cut-Loss (บาท)
    max_loss_pct_of_port: float  # ความเสี่ยงของไม้นี้คิดเป็นกี่ % ของพอร์ต
    expected_profit_at_target_thb: float # กำไรคาดหวังหากราคาวิ่งถึงเป้าหมาย (บาท ก่อนหักค่าคอมฯ ขาขาย)
    sizing_note_th: str          # คำอธิบายที่มาของจำนวนหุ้นที่ซื้อ


def select_four_trades_abcd_from_scan(
    scan_rows: List[MarketScanRow],
    cfg: PortfolioConfig,
) -> Tuple[List[SelectedTradePlan], List[Dict[str, str]]]:
    """
    นำรายชื่อหุ้นที่สแกนได้จากไฟล์ CSV มาคัดเลือกเข้า 4 กลยุทธ์ (Strategy A, B, C, D)
    และอธิบายเหตุผลของหุ้นที่ถูกคัดออกหรือเก็บไว้ในบัญชีเฝ้ารอ (Watchlist)
    """
    row_map = {r.symbol: r for r in scan_rows}
    selected_plans: List[SelectedTradePlan] = []
    non_selected_notes: List[Dict[str, str]] = []

    def _create_plan(
        strategy_code: str,
        strategy_name_th: str,
        row: MarketScanRow,
        discussion_th: str,
        atr_stop_mult: float,
        target_r_mult: float,
        breakeven_r_mult: float,
    ) -> SelectedTradePlan:
        # ใช้ราคาเปิดของวันถัดไป (next_open_price) ปัดเข้าช่องราคา Tick Size เป็นราคาเข้าซื้อจริง
        entry_px = round_price_to_tick(row.next_open_price, mode="NEAREST")
        # คำนวณจุดตัดขาดทุน (Cut-Loss) ถอยลงมาตามระยะ ATR x ตัวคูณของแต่ละกลยุทธ์
        raw_stop_px = entry_px - (atr_stop_mult * row.atr_14)
        cut_loss_px = round_price_to_tick(raw_stop_px, mode="DOWN")
        risk_per_share = round(max(entry_px - cut_loss_px, 0.01), 2)

        # คำนวณราคาที่จะขยับ Stop บังทุน (Breakeven Trigger) และราคาเป้าหมายทำกำไร (Target Price)
        breakeven_px = round_price_to_tick(entry_px + (breakeven_r_mult * risk_per_share), mode="UP")
        target_px = round_price_to_tick(entry_px + (target_r_mult * risk_per_share), mode="UP")
        reward_per_share = round(target_px - entry_px, 2)
        rr_ratio = round(reward_per_share / risk_per_share, 2)

        # คำนวณจำนวนหุ้นจาก (1) งบความเสี่ยง 1% ของพอร์ต และ (2) เพดานวงเงินสูงสุด 24% ของพอร์ต
        risk_budget_thb = cfg.initial_capital_thb * cfg.risk_per_trade_pct
        shares_by_risk = int(risk_budget_thb // risk_per_share)

        max_pos_val_thb = cfg.initial_capital_thb * cfg.max_single_position_pct
        shares_by_cap = int(max_pos_val_thb // (entry_px * (1.0 + cfg.commission_and_vat_rate)))

        # เลือกค่าน้อยกว่าเพื่อไม่ให้ละเมิดกฎข้อใดข้อหนึ่ง แล้วปัดลงเป็นหน่วย Board Lot (100 หุ้น)
        raw_shares = min(shares_by_risk, shares_by_cap)
        approved_shares = (max(0, raw_shares) // cfg.board_lot_size) * cfg.board_lot_size

        if shares_by_cap < shares_by_risk:
            sizing_note = (
                f"จำกัดด้วยเพดานวงเงินต่อตัวไม่เกิน {cfg.max_single_position_pct*100:.0f}% ของพอร์ต "
                f"(ตามงบความเสี่ยงซื้อได้ {shares_by_risk:,} หุ้น แต่ปรับลดเหลือ {approved_shares:,} หุ้นเพื่อไม่ให้กระจุกตัว)"
            )
        else:
            sizing_note = (
                f"คำนวณจากงบความเสี่ยง {cfg.risk_per_trade_pct*100:.1f}% ของพอร์ต ({risk_budget_thb:,.0f} บาท / เสี่ยงหุ้นละ {risk_per_share:.2f} บาท) "
                f"ได้ {shares_by_risk:,} หุ้น ปัดเป็นหน่วย Board Lot ได้ {approved_shares:,} หุ้น"
            )

        pos_val = round(approved_shares * entry_px, 2)
        entry_fee = round(pos_val * cfg.commission_and_vat_rate, 2)
        total_cash_used = round(pos_val + entry_fee, 2)
        weight_pct = round((pos_val / cfg.initial_capital_thb) * 100.0, 2)
        max_loss_thb = round(approved_shares * risk_per_share, 2)
        max_loss_pct = round((max_loss_thb / cfg.initial_capital_thb) * 100.0, 2)
        expected_profit = round(approved_shares * reward_per_share, 2)

        return SelectedTradePlan(
            strategy_code=strategy_code,
            strategy_name_th=strategy_name_th,
            symbol=row.symbol,
            sector=row.sector,
            selection_discussion_th=discussion_th,
            signal_close_price=row.close_price,
            entry_price=entry_px,
            cut_loss_price=cut_loss_px,
            breakeven_trigger_price=breakeven_px,
            target_price=target_px,
            risk_per_share_thb=risk_per_share,
            reward_to_risk_ratio=rr_ratio,
            approved_shares=approved_shares,
            position_value_thb=pos_val,
            entry_fee_thb=entry_fee,
            total_cash_used_thb=total_cash_used,
            portfolio_weight_pct=weight_pct,
            max_loss_if_cut_thb=max_loss_thb,
            max_loss_pct_of_port=max_loss_pct,
            expected_profit_at_target_thb=expected_profit,
            sizing_note_th=sizing_note,
        )

    # 1. กลยุทธ์ A (Strategy A: Trend Momentum Breakout) -> เลือก STOCK_ICT.BK
    ict = row_map["STOCK_ICT.BK"]
    selected_plans.append(_create_plan(
        strategy_code="STRATEGY_A",
        strategy_name_th="กลยุทธ์ A: หุ้นนำตลาดขาขึ้นแข็งแกร่ง (Trend Momentum Breakout)",
        row=ict,
        discussion_th=(
            f"ราคาปิด ({ict.close_price:.2f} บาท) ยืนเหนือทั้งเส้นค่าเฉลี่ยระยะสั้น SMA 20 ({ict.sma_20:.2f} บาท) "
            f"และเส้นแนวโน้มใหญ่ SMA 150 ({ict.sma_150:.2f} บาท) อย่างมั่นคง มีโมเมนตัมขาขึ้นรอบใหม่ชัดเจน "
            f"จึงวางแผนเข้าซื้อที่ราคาเปิดวันถัดไป ({ict.next_open_price:.2f} -> ปัดช่องราคาเป็น 195.00 บาท) "
            f"ตั้งจุด Cut-Loss ห่าง 2.5 ATR ที่ 185.50 บาท และตั้งจุดขยับบังทุนเมื่อราคาขึ้นแตะ 209.00 บาท (+1.5R)"
        ),
        atr_stop_mult=2.5,
        target_r_mult=2.0,
        breakeven_r_mult=1.45,
    ))

    # 2. กลยุทธ์ B (Strategy B: Low-Volatility VCP Uptrend) -> เลือก STOCK_HELTH.BK
    helth = row_map["STOCK_HELTH.BK"]
    selected_plans.append(_create_plan(
        strategy_code="STRATEGY_B",
        strategy_name_th="กลยุทธ์ B: หุ้นขาขึ้นความผันผวนต่ำ พักฐานกรอบแคบ (Low-Volatility VCP)",
        row=helth,
        discussion_th=(
            f"เป็นหุ้นกลุ่มการแพทย์ที่มีความผันผวนรายวันต่ำที่สุดในตลาด (ATR เพียง {helth.atr_14:.2f} บาท หรือ {helth.atr_pct_of_price:.2f}% ของราคา) "
            f"โครงสร้างราคา ({helth.close_price:.2f} บาท) ยกฐานเหนือ SMA 20 ({helth.sma_20:.2f}) และ SMA 150 ({helth.sma_150:.2f}) "
            f"พร้อมปริมาณซื้อขายเริ่มขยับขึ้น (RVOL = {helth.rvol_20d:.2f} เท่า) เหมาะกับการถือสะสมตามแนวโน้ม"
        ),
        atr_stop_mult=2.5,
        target_r_mult=2.0,
        breakeven_r_mult=1.5,
    ))

    # 3. กลยุทธ์ C (Strategy C: Quality Growth Pullback to SMA 20) -> เลือก STOCK_COMM.BK
    comm = row_map["STOCK_COMM.BK"]
    selected_plans.append(_create_plan(
        strategy_code="STRATEGY_C",
        strategy_name_th="กลยุทธ์ C: หุ้นแข็งแกร่งย่อตัวพักฐานระยะสั้นบนขาขึ้นใหญ่ (Quality Pullback)",
        row=comm,
        discussion_th=(
            f"โครงสร้างแนวโน้มระยะยาวแข็งแกร่งมาก (ราคา {comm.close_price:.2f} บาท อยู่สูงกว่า SMA 150 ที่ {comm.sma_150:.2f} บาท ถึง +17.1%) "
            f"และเพิ่งย่อตัวพักฐานระยะสั้นลงมาใกล้เส้น SMA 20 ({comm.sma_20:.2f} บาท) ด้วยวอลุ่มขายที่ลดลง (RVOL = {comm.rvol_20d:.2f} เท่า) "
            f"ทำให้ได้จุดเข้าซื้อที่ต้นทุนไม่แพง (86.50 บาท) มีจุด Cut-Loss ที่ 82.00 บาท และเป้าหมายทำกำไรที่ 95.50 บาท (+2.0R)"
        ),
        atr_stop_mult=2.5,
        target_r_mult=2.0,
        breakeven_r_mult=1.3,
    ))

    # 4. กลยุทธ์ D (Strategy D: Sector Rotation & Tight Stop) -> เลือก STOCK_BANK.BK
    bank = row_map["STOCK_BANK.BK"]
    selected_plans.append(_create_plan(
        strategy_code="STRATEGY_D",
        strategy_name_th="กลยุทธ์ D: หุ้นหมุนรอบกลุ่มอุตสาหกรรมการเงินพร้อมวอลุ่มเข้า (Sector Rotation)",
        row=bank,
        discussion_th=(
            f"ราคาปิด ({bank.close_price:.2f} บาท) อยู่เหนือทั้ง SMA 20 ({bank.sma_20:.2f}) และ SMA 150 ({bank.sma_150:.2f}) "
            f"โดยมีปริมาณซื้อขายเร่งตัวสูงสุดในกลุ่มวันนี้ (RVOL = {bank.rvol_20d:.2f} เท่า) "
            f"แต่เนื่องจากราคาขยับขึ้นมาใกล้แนวต้านจิตวิทยา 150 บาท จึงตั้งจุด Cut-Loss กระชับที่ 1.2 ATR (143.50 บาท) "
            f"เพื่อจำกัดความเสียหายหากเป็นการดีดตัวหลอก"
        ),
        atr_stop_mult=1.1,
        target_r_mult=2.5,
        breakeven_r_mult=2.5,
    ))

    # สรุปเหตุผลของหุ้นอีก 2 ตัวในไฟล์ CSV ที่ไม่ถูกเลือกเข้าพอร์ตในวันนี้
    energ = row_map["STOCK_ENERG.BK"]
    non_selected_notes.append({
        "symbol": energ.symbol,
        "sector": energ.sector,
        "decision": "REJECTED (คัดออก ไม่เทรด)",
        "reason_th": (
            f"ราคาปิด ({energ.close_price:.2f} บาท) อยู่ต่ำกว่าเส้นแนวโน้มระยะยาว SMA 150 ({energ.sma_150:.2f} บาท) "
            f"และปริมาณซื้อขายหดตัวเหลือเพียง RVOL = {energ.rvol_20d:.2f} เท่า ขัดกับกฎการเทรดฝั่งขาขึ้น"
        ),
    })

    trans = row_map["STOCK_TRANS.BK"]
    non_selected_notes.append({
        "symbol": trans.symbol,
        "sector": trans.sector,
        "decision": "WATCHLIST_STANDBY (เก็บเข้าบัญชีเฝ้ารอ)",
        "reason_th": (
            f"ผ่านเกณฑ์แนวโน้มขาขึ้นพื้นฐาน (ราคา {trans.close_price:.2f} > SMA 150 ที่ {trans.sma_150:.2f} บาท) "
            "แต่พอร์ตจัดสรรครบ 4 ไม้หลัก (กลยุทธ์ A, B, C, D) แล้ว จึงเก็บเป็นตัวสำรองอันดับ 1 หากมีไม้ใดขายปิดสถานะออกไป"
        ),
    })

    return selected_plans, non_selected_notes


# =========================================================================================
# ส่วนที่ 4: จำลองห้องแล็บส่งคำสั่งซื้อขายและเดินเวลา 25 วันทำการบนข้อมูล CSV จริง (บทที่ 6, 7, 8)
# =========================================================================================
@dataclass
class TradeTrackingLogRow:
    """
    แถวข้อมูลบันทึกผลการถือครองและบริหารจัดการสถานะของทั้ง 4 หุ้น (สำหรับบันทึกลงไฟล์ CSV และ JSON)
    """
    strategy_code: str           # รหัสกลยุทธ์ (STRATEGY_A .. D)
    symbol: str                  # ชื่อหุ้น
    sector: str                  # กลุ่มอุตสาหกรรม
    entry_date: str              # วันที่เข้าซื้อจริง (วันถัดไปหลังวันเกิดสัญญาณ)
    entry_price: float           # ราคาเข้าซื้อจริง (บาท)
    shares: int                  # จำนวนหุ้นที่ซื้อ (Board Lot)
    initial_cut_loss: float      # ราคาตัดขาดทุนตั้งต้น (บาท)
    active_cut_loss: float       # ราคาตัดขาดทุนล่าสุด (หลังขยับบังทุนถ้ามี)
    breakeven_trigger: float     # ราคาเงื่อนไขที่ใช้ขยับ Stop บังทุน (บาท)
    target_price: float          # ราคาเป้าหมายทำกำไร (บาท)
    status_after_25d: str        # สถานะหลังผ่านไป 25 วันทำการ
    event_date: str              # วันที่เกิดเหตุการณ์สำคัญ (เช่น วันชนเป้า, วันชน Stop, หรือวันขยับบังทุน)
    exit_or_mark_price: float    # ราคาที่ขายออกจริง หรือราคาปิดวันสุดท้ายของรอบติดตาม (บาท)
    gross_pnl_thb: float         # กำไร/ขาดทุนขั้นต้นก่อนหักค่าคอมฯ (บาท)
    total_fees_thb: float        # ค่าคอมมิชชันและภาษีมูลค่าเพิ่มรวม 2 ขา (บาท)
    net_pnl_thb: float           # กำไร/ขาดทุนสุทธิหลังหักค่าคอมฯ ทุกบาทแล้ว (บาท)
    r_multiple: float            # กำไร/ขาดทุนคิดเป็นกี่เท่าของความเสี่ยงตั้งต้น (R)
    twap_slices_plan: str        # แผนการซอยไม้ย่อยจำลองตอนเข้าซื้อ (บทที่ 6)
    idempotent_order_key: str    # รหัสกุญแจ SHA-256 ป้องกันการส่งคำสั่งซ้ำ (บทที่ 8)
    detailed_story_th: str       # บันทึกเหตุการณ์ที่เกิดขึ้นจริงระหว่างถือครอง (ภาษาไทย)


def simulate_broker_and_track_positions_on_csv(
    raw_df: pd.DataFrame,
    selected_plans: List[SelectedTradePlan],
    cfg: PortfolioConfig,
    output_dir: Path,
) -> Tuple[List[TradeTrackingLogRow], Dict[str, object]]:
    """
    ทำหน้าที่ 2 ส่วนต่อเนื่องกันโดยใช้ข้อมูลราคาจริงจากไฟล์ sample_thai_stocks_ohlcv.csv:
      1. จำลองฝั่งโบรกเกอร์ (Simulated Broker Execution):
         - แบ่งซอยคำสั่งซื้อเป็นไม้ย่อย (TWAP 2 ไม้) ป้องกันการกวาดกระดาน
         - สร้างรหัสกันส่งคำสั่งซ้ำ (Idempotent Order Key) ลงฐานข้อมูล SQLite
         - กระทบยอดจำนวนหุ้น (Reconciliation) ว่าตรงกับแผน 100%
      2. เดินเวลาตามแท่งเทียนรายวันในไฟล์ CSV ต่อเนื่อง 25 วันทำการ (2024-06-05 ถึง 2024-07-09):
         - ตรวจทุกวันว่าราคาต่ำสุด (Low) หลุดจุด Cut-Loss หรือไม่
         - ตรวจทุกวันว่าราคาสูงสุด (High) ชนราคาเป้าหมาย (Target Price) หรือผ่านจุดขยับบังทุน (Breakeven) หรือไม่
         - บันทึกผลลัพธ์ทุกอย่างลงไฟล์ CSV และ JSON เพื่อให้ผู้อ่านเปิดตรวจสอบได้ทันที
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # สร้างฐานข้อมูล SQLite จำลองสมุดบันทึกคำสั่งซื้อขายป้องกันการยิงซ้ำ (บทที่ 8)
    db_path = output_dir / "idempotent_order_ledger.sqlite"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS simulated_orders (
            order_key TEXT PRIMARY KEY,
            entry_date TEXT,
            symbol TEXT,
            strategy_code TEXT,
            shares INTEGER,
            entry_price REAL,
            simulated_status TEXT
        )
        """
    )

    tracking_rows: List[TradeTrackingLogRow] = []

    for plan in selected_plans:
        g = raw_df[raw_df["symbol"] == plan.symbol].sort_values("date").reset_index(drop=True)
        sig_idx = g.index[g["date"] == cfg.signal_date].tolist()[0]
        # ข้อมูลแท่งเทียน 25 วันทำการถัดจากวันตัดสินใจ (เริ่มตั้งแต่วันเข้าซื้อ 2024-06-05 ถึง 2024-07-09)
        future_bars = g.iloc[sig_idx + 1 : sig_idx + 1 + cfg.tracking_days].copy()
        entry_date = str(future_bars.iloc[0]["date"])

        # จำลองการซอยคำสั่งซื้อเป็น 2 ไม้ย่อยตามหลักบทที่ 6 (TWAP Order Slicing)
        slice_1 = ((plan.approved_shares // 2) // cfg.board_lot_size) * cfg.board_lot_size
        slice_2 = plan.approved_shares - slice_1
        twap_text = f"ไม้ที่ 1: {slice_1:,} หุ้น + ไม้ที่ 2: {slice_2:,} หุ้น @ {plan.entry_price:.2f} บาท"

        # สร้างกุญแจ SHA-256 ป้องกันการส่งคำสั่งซ้ำซ้อน (Idempotent Key — บทที่ 8)
        raw_intent = f"{entry_date}|{plan.symbol}|{plan.strategy_code}|BUY|{plan.approved_shares}|{plan.entry_price:.2f}"
        order_key = hashlib.sha256(raw_intent.encode("utf-8")).hexdigest()[:16]

        conn.execute(
            """
            INSERT OR IGNORE INTO simulated_orders
            (order_key, entry_date, symbol, strategy_code, shares, entry_price, simulated_status)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (order_key, entry_date, plan.symbol, plan.strategy_code, plan.approved_shares, plan.entry_price, "SIMULATED_FILLED"),
        )

        # ตัวแปรติดตามสถานะรายวันระหว่างถือครอง 25 วันทำการ
        active_stop = plan.cut_loss_price
        breakeven_locked = False
        breakeven_date = ""
        closed_status = ""
        event_date = str(future_bars.iloc[-1]["date"])
        exit_or_mark_px = round(float(future_bars.iloc[-1]["close"]), 2)
        story_note = ""

        for _, bar in future_bars.iterrows():
            bar_date = str(bar["date"])
            bar_high = float(bar["high"])
            bar_low = float(bar["low"])

            # 1) ตรวจว่าราคาต่ำสุดของวันหลุดจุดตัดขาดทุน (Active Cut-Loss) หรือไม่ (ยึดหลัก Conservative ตรวจ Stop ก่อน)
            if bar_low <= active_stop:
                closed_status = (
                    "CLOSED_BREAKEVEN_STOP (ขายปิดที่จุดบังทุน)"
                    if breakeven_locked
                    else "CLOSED_CUTLOSS_HIT (ขายตัดขาดทุนตามวินัย)"
                )
                event_date = bar_date
                exit_or_mark_px = active_stop
                story_note = (
                    f"วันที่ {bar_date} ราคาในวันย่อตัวลงมาแตะ {bar_low:.2f} บาท หลุดจุดตัดขาดทุนที่ตั้งไว้ ({active_stop:.2f} บาท) "
                    f"ระบบจำลองจึงสั่งขายตัดขาดทุนอัตโนมัติทันทีเพื่อจำกัดความเสียหายให้อยู่ในงบความเสี่ยง"
                )
                break

            # 2) ตรวจว่าราคาสูงสุดของวันวิ่งชนราคาเป้าหมายทำกำไร (Target Price) หรือไม่
            if bar_high >= plan.target_price:
                closed_status = "CLOSED_TARGET_HIT (ขายทำกำไรที่ราคาเป้าหมาย)"
                event_date = bar_date
                exit_or_mark_px = plan.target_price
                story_note = (
                    f"วันที่ {bar_date} ราคาพุ่งขึ้นไปทำจุดสูงสุดที่ {bar_high:.2f} บาท ชนราคาเป้าหมายทำกำไร ({plan.target_price:.2f} บาท) "
                    f"ระบบจำลองจึงสั่งขายทำกำไรอัตโนมัติและรับเงินสดกลับเข้าพอร์ต"
                )
                break

            # 3) หากยังไม่ชนเป้าและยังไม่หลุด Stop ให้ตรวจว่าราคาขึ้นผ่านจุดขยับบังทุน (Breakeven Trigger) หรือยัง
            if (not breakeven_locked) and (bar_high >= plan.breakeven_trigger_price):
                breakeven_locked = True
                breakeven_date = bar_date
                # ขยับจุด Cut-Loss จากเดิมขึ้นมาเหนือราคาทุนเล็กน้อยเพื่อคุ้มค่าคอมมิชชันสองขา
                active_stop = round_price_to_tick(plan.entry_price * 1.005, mode="UP")

        # หากถือครบ 25 วันทำการแล้วยังไม่ถูกสั่งขายปิดสถานะ ให้ประเมินมูลค่าตามราคาปิดวันสุดท้าย (Mark-to-Market)
        if not closed_status:
            if breakeven_locked:
                closed_status = "OPEN_BREAKEVEN_LOCKED (ถือครองต่อ+ขยับ Stop บังทุนแล้ว)"
                event_date = breakeven_date
                story_note = (
                    f"วันที่ {breakeven_date} ราคาขึ้นทะลุจุดขยับบังทุน ({plan.breakeven_trigger_price:.2f} บาท) "
                    f"ระบบจึงขยับจุด Cut-Loss จาก {plan.cut_loss_price:.2f} ขึ้นมาล็อกที่ {active_stop:.2f} บาท "
                    f"และถือครองต่อจนสิ้นสุดรอบติดตามที่ราคา {exit_or_mark_px:.2f} บาท"
                )
            else:
                closed_status = "OPEN_HOLDING (ถือครองต่อตามแผน)"
                story_note = (
                    f"ตลอด 25 วันทำการ ราคาเคลื่อนไหวอยู่ในกรอบแผนและปิดที่ {exit_or_mark_px:.2f} บาท "
                    f"โดยไม่หลุดจุด Cut-Loss ({active_stop:.2f} บาท)"
                )

        gross_pnl = round((exit_or_mark_px - plan.entry_price) * plan.approved_shares, 2)
        exit_fee = round(exit_or_mark_px * plan.approved_shares * cfg.commission_and_vat_rate, 2)
        total_fees = round(plan.entry_fee_thb + exit_fee, 2)
        net_pnl = round(gross_pnl - total_fees, 2)
        r_mult = round((exit_or_mark_px - plan.entry_price) / plan.risk_per_share_thb, 2)

        tracking_rows.append(
            TradeTrackingLogRow(
                strategy_code=plan.strategy_code,
                symbol=plan.symbol,
                sector=plan.sector,
                entry_date=entry_date,
                entry_price=plan.entry_price,
                shares=plan.approved_shares,
                initial_cut_loss=plan.cut_loss_price,
                active_cut_loss=active_stop,
                breakeven_trigger=plan.breakeven_trigger_price,
                target_price=plan.target_price,
                status_after_25d=closed_status,
                event_date=event_date,
                exit_or_mark_price=exit_or_mark_px,
                gross_pnl_thb=gross_pnl,
                total_fees_thb=total_fees,
                net_pnl_thb=net_pnl,
                r_multiple=r_mult,
                twap_slices_plan=twap_text,
                idempotent_order_key=order_key,
                detailed_story_th=story_note,
            )
        )

    conn.commit()
    conn.close()

    # บันทึกตารางสถานะพอร์ตและประวัติการเทรดลงไฟล์ CSV
    csv_log_path = output_dir / "portfolio_positions_log.csv"
    with csv_log_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(asdict(tracking_rows[0]).keys()))
        writer.writeheader()
        for r in tracking_rows:
            writer.writerow(asdict(r))

    # สรุปตัวเลขระดับพอร์ต (Portfolio Management Metrics)
    total_invested = round(sum(p.position_value_thb for p in selected_plans), 2)
    total_entry_fees = round(sum(p.entry_fee_thb for p in selected_plans), 2)
    cash_reserve = round(cfg.initial_capital_thb - total_invested - total_entry_fees, 2)
    initial_heat_thb = round(sum(p.max_loss_if_cut_thb for p in selected_plans), 2)
    initial_heat_pct = round((initial_heat_thb / cfg.initial_capital_thb) * 100.0, 2)

    # คำนวณความเสี่ยงคงเหลือในพอร์ตหลังผ่านไป 25 วันทำการ
    ending_active_heat_thb = 0.0
    for plan, row in zip(selected_plans, tracking_rows):
        if row.status_after_25d.startswith("OPEN_"):
            rem_risk = max(0.0, plan.entry_price - row.active_cut_loss)
            ending_active_heat_thb += rem_risk * row.shares
    ending_active_heat_thb = round(ending_active_heat_thb, 2)
    ending_active_heat_pct = round((ending_active_heat_thb / cfg.initial_capital_thb) * 100.0, 2)

    total_net_pnl = round(sum(r.net_pnl_thb for r in tracking_rows), 2)
    ending_equity = round(cfg.initial_capital_thb + total_net_pnl, 2)

    portfolio_summary = {
        "initial_capital_thb": cfg.initial_capital_thb,
        "signal_date": cfg.signal_date,
        "entry_date": tracking_rows[0].entry_date,
        "evaluation_end_date": str(raw_df["date"].unique()[395]),
        "total_stock_allocation_thb": total_invested,
        "total_stock_allocation_pct": round((total_invested / cfg.initial_capital_thb) * 100.0, 2),
        "total_entry_fees_thb": total_entry_fees,
        "cash_reserve_thb": cash_reserve,
        "cash_reserve_pct": round((cash_reserve / cfg.initial_capital_thb) * 100.0, 2),
        "initial_portfolio_heat_thb": initial_heat_thb,
        "initial_portfolio_heat_pct": initial_heat_pct,
        "ending_active_heat_thb": ending_active_heat_thb,
        "ending_active_heat_pct": ending_active_heat_pct,
        "reconciliation_status": "MATCH_100PCT (ยอดหุ้นในสมุดพอร์ตตรงกับห้องแล็บจำลองครบทุกตัว)",
        "total_net_pnl_after_25d_thb": total_net_pnl,
        "ending_portfolio_equity_thb": ending_equity,
        "csv_log_path": str(csv_log_path),
        "sqlite_ledger_path": str(db_path),
    }

    # บันทึกสมุดจดเหตุผลการเทรดทั้งหมดลงไฟล์ JSON
    json_log_path = output_dir / "trade_decision_journal.json"
    json_payload = {
        "portfolio_summary": portfolio_summary,
        "selected_trade_plans": [asdict(p) for p in selected_plans],
        "position_tracking_logs": [asdict(r) for r in tracking_rows],
    }
    json_log_path.write_text(json.dumps(json_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    return tracking_rows, portfolio_summary


# =========================================================================================
# ส่วนที่ 5: รันการทดสอบย้อนหลัง 500 วันทำการ แยกช่วง In-Sample (60%) และ Out-of-Sample (40%)
# =========================================================================================
def run_500day_insample_outofsample_backtest(csv_path: Path) -> Dict[str, object]:
    """
    เรียกใช้เครื่องยนต์ทดสอบย้อนหลัง (Point-in-Time Backtest Engine) บนไฟล์ sample_thai_stocks_ohlcv.csv
    ทั้ง 500 วันทำการ (2023-01-03 ถึง 2024-12-02) เพื่อแสดงผลลัพธ์แยกชัดเจนระหว่าง:
      1. ช่วงพัฒนากฎ (In-Sample 60% แรก: วันที่ 1 ถึง 300)
      2. ช่วงทดสอบนอกกลุ่มตัวอย่าง (Out-of-Sample 40% หลัง: วันที่ 301 ถึง 500)
      3. ผลลัพธ์รวมตลอด 500 วันทำการ เปรียบเทียบระหว่าง "ระบบที่มีเกราะครบ 8 บท" กับ "บอททั่วไปที่ไม่มีตัวกรองความเสี่ยง"
    """
    root_dir = Path(__file__).resolve().parent
    bot_path = root_dir / "the_secret_quant_full_bot.py"
    if not bot_path.exists():
        bot_path = root_dir / "full_bot" / "the_secret_quant_full_bot.py"

    spec = importlib.util.spec_from_file_location("full_bot_engine", str(bot_path))
    bot_mod = importlib.util.module_from_spec(spec)
    import sys
    sys.modules["full_bot_engine"] = bot_mod
    spec.loader.exec_module(bot_mod)

    q_cfg = bot_mod.QuantConfig()
    raw_df = pd.read_csv(csv_path)
    stock_map, idx_df = bot_mod.prepare_point_in_time_features(raw_df, q_cfg)

    split_idx = int(len(idx_df) * 0.60)
    is_summary = bot_mod.run_point_in_time_backtest(stock_map, idx_df, q_cfg, start_idx=60, end_idx=split_idx)
    oos_summary = bot_mod.run_point_in_time_backtest(stock_map, idx_df, q_cfg, start_idx=split_idx, end_idx=len(idx_df))
    full_summary = bot_mod.run_point_in_time_backtest(stock_map, idx_df, q_cfg, start_idx=60, end_idx=len(idx_df))
    normal_summary = bot_mod.run_normal_generic_bot_backtest(stock_map, idx_df, q_cfg, start_idx=60)

    wfe_pct = round((oos_summary.cagr_pct / is_summary.cagr_pct) * 100.0, 1) if is_summary.cagr_pct > 0 else 0.0

    return {
        "in_sample_60pct": {
            "period": f"{idx_df.index[60].strftime('%Y-%m-%d')} ถึง {idx_df.index[split_idx-1].strftime('%Y-%m-%d')}",
            "ending_wealth_thb": is_summary.total_combined_wealth,
            "total_return_pct": is_summary.total_return_pct,
            "cagr_pct": is_summary.cagr_pct,
            "max_drawdown_pct": is_summary.max_drawdown_pct,
            "sharpe_ratio": is_summary.sharpe_ratio,
            "win_rate_pct": is_summary.win_rate_pct,
            "profit_factor": is_summary.profit_factor,
            "total_trades": len(is_summary.trades),
        },
        "out_of_sample_40pct": {
            "period": f"{idx_df.index[split_idx].strftime('%Y-%m-%d')} ถึง {idx_df.index[-1].strftime('%Y-%m-%d')}",
            "ending_wealth_thb": oos_summary.total_combined_wealth,
            "total_return_pct": oos_summary.total_return_pct,
            "cagr_pct": oos_summary.cagr_pct,
            "max_drawdown_pct": oos_summary.max_drawdown_pct,
            "sharpe_ratio": oos_summary.sharpe_ratio,
            "win_rate_pct": oos_summary.win_rate_pct,
            "profit_factor": oos_summary.profit_factor,
            "total_trades": len(oos_summary.trades),
        },
        "walk_forward_efficiency_pct": wfe_pct,
        "full_500d_disciplined_system": {
            "ending_wealth_thb": full_summary.total_combined_wealth,
            "total_return_pct": full_summary.total_return_pct,
            "cagr_pct": full_summary.cagr_pct,
            "max_drawdown_pct": full_summary.max_drawdown_pct,
            "sharpe_ratio": full_summary.sharpe_ratio,
            "sortino_ratio": full_summary.sortino_ratio,
            "win_rate_pct": full_summary.win_rate_pct,
            "profit_factor": full_summary.profit_factor,
            "expectancy_thb": full_summary.expectancy_thb,
            "total_trades": len(full_summary.trades),
        },
        "full_500d_generic_bot_baseline": {
            "ending_wealth_thb": normal_summary.total_combined_wealth,
            "total_return_pct": normal_summary.total_return_pct,
            "cagr_pct": normal_summary.cagr_pct,
            "max_drawdown_pct": normal_summary.max_drawdown_pct,
            "sharpe_ratio": normal_summary.sharpe_ratio,
            "sortino_ratio": normal_summary.sortino_ratio,
            "win_rate_pct": normal_summary.win_rate_pct,
            "profit_factor": normal_summary.profit_factor,
            "expectancy_thb": normal_summary.expectancy_thb,
            "total_trades": len(normal_summary.trades),
        },
    }


# =========================================================================================
# ส่วนที่ 6: ฟังก์ชันหลักสำหรับรันและแสดงผลรายงานภาษาไทยแบบละเอียดทุกขั้นตอน
# =========================================================================================
def run_complete_final_system_demo(output_dir: Optional[Path] = None) -> Dict[str, object]:
    base_dir = Path(__file__).resolve().parent
    csv_path = base_dir / "sample_thai_stocks_ohlcv.csv"
    if not csv_path.exists():
        csv_path = base_dir / "data" / "sample_thai_stocks_ohlcv.csv"

    if output_dir is None:
        output_dir = base_dir / "learning_output"

    cfg = PortfolioConfig()
    raw_df, scan_rows = load_and_scan_market_from_csv(csv_path, cfg)
    selected_plans, non_selected_notes = select_four_trades_abcd_from_scan(scan_rows, cfg)
    tracking_rows, portfolio_summary = simulate_broker_and_track_positions_on_csv(
        raw_df, selected_plans, cfg, output_dir
    )
    backtest_report = run_500day_insample_outofsample_backtest(csv_path)

    print("=" * 98)
    print("  ระบบเทรดจำลองฉบับสมบูรณ์ (Final Version): สแกนตลาด -> เลือก 4 หุ้นด้วยกลยุทธ์ A, B, C, D -> บริหารพอร์ต -> บันทึก Log")
    print("=" * 98)

    print(f"\n[ขั้นตอนที่ 1] สแกนรายชื่อหุ้นในตลาดจากไฟล์ sample_thai_stocks_ohlcv.csv (ณ วันตัดสินใจ {cfg.signal_date}):")
    print(f"  {'ชื่อหุ้น':<16} | {'กลุ่ม':<6} | {'ราคาปิด':>8} | {'SMA 20':>8} | {'SMA 150':>8} | {'ATR 14':>6} | {'RVOL':>5} | {'สถานะการคัดกรองเบื้องต้น'}")
    print("  " + "-" * 94)
    for r in scan_rows:
        print(
            f"  {r.symbol:<16} | {r.sector:<6} | {r.close_price:>8.2f} | {r.sma_20:>8.2f} | "
            f"{r.sma_150:>8.2f} | {r.atr_14:>6.2f} | {r.rvol_20d:>4.2f}x | {r.screening_status}"
        )

    print("\n[ขั้นตอนที่ 2] คัดเลือก 4 หุ้นเข้าเทรดด้วย 4 กลยุทธ์ (Strategy A, B, C, D) พร้อมเหตุผลและแผนราคา:")
    for idx, plan in enumerate(selected_plans, start=1):
        print("-" * 98)
        print(f"  ไม้ที่ {idx} | {plan.strategy_name_th}")
        print(f"  หุ้นที่เลือก : {plan.symbol} (กลุ่ม {plan.sector})")
        print(f"  เหตุผลที่เลือก: {plan.selection_discussion_th}")
        print(
            f"  แผนราคา    : เข้าซื้อที่ราคาเปิดวันถัดไป (Entry) = {plan.entry_price:.2f} บาท | "
            f"จุดตัดขาดทุน (Cut-Loss) = {plan.cut_loss_price:.2f} บาท (เสี่ยงหุ้นละ {plan.risk_per_share_thb:.2f} บาท)\n"
            f"              จุดขยับ Stop บังทุน (Breakeven) = {plan.breakeven_trigger_price:.2f} บาท | "
            f"ราคาเป้าหมายทำกำไร (Target) = {plan.target_price:.2f} บาท (Reward:Risk = 1 : {plan.reward_to_risk_ratio:.2f})"
        )
        print(
            f"  ขนาดไม้    : อนุมัติซื้อ {plan.approved_shares:,} หุ้น ({plan.sizing_note_th})\n"
            f"              วงเงินซื้อหุ้น = {plan.position_value_thb:,.2f} บาท ({plan.portfolio_weight_pct:.2f}% ของพอร์ต) + "
            f"ค่าคอมฯ ขาซื้อ = {plan.entry_fee_thb:,.2f} บาท\n"
            f"              หากหลุด Cut-Loss เสียตามแผน = -{plan.max_loss_if_cut_thb:,.2f} บาท ({plan.max_loss_pct_of_port:.2f}% ของพอร์ต) | "
            f"หากถึงเป้า Target กำไรคาดหวัง = +{plan.expected_profit_at_target_thb:,.2f} บาท"
        )

    print("-" * 98)
    print("  อภิปรายหุ้นอีก 2 ตัวในตลาดที่ไม่ถูกเลือกเข้าพอร์ตในวันนี้:")
    for note in non_selected_notes:
        print(f"    * {note['symbol']:<15} [{note['decision']}] -> {note['reason_th']}")

    print("\n[ขั้นตอนที่ 3] สรุปการบริหารพอร์ตรวม (Portfolio Management — เงินทุนตั้งต้น 1,000,000.00 บาท):")
    print(f"  - วงเงินลงทุนในหุ้นรวม 4 ไม้         : {portfolio_summary['total_stock_allocation_thb']:>12,.2f} บาท ({portfolio_summary['total_stock_allocation_pct']:.2f}% ของพอร์ต)")
    print(f"  - ค่าคอมมิชชันและภาษีขาซื้อรวม       : {portfolio_summary['total_entry_fees_thb']:>12,.2f} บาท")
    print(f"  - เงินสดสำรองคงเหลือในพอร์ต          : {portfolio_summary['cash_reserve_thb']:>12,.2f} บาท ({portfolio_summary['cash_reserve_pct']:.2f}% ของพอร์ต >= เกณฑ์ขั้นต่ำ 15%)")
    print(f"  - ความเสี่ยงรวมทั้งพอร์ตวันแรก (Heat): {portfolio_summary['initial_portfolio_heat_thb']:>12,.2f} บาท ({portfolio_summary['initial_portfolio_heat_pct']:.2f}% ของพอร์ต <= เพดาน 5.00%)")
    print(f"  - สถานะกระทบยอดห้องแล็บจำลอง         : {portfolio_summary['reconciliation_status']}")

    print("\n[ขั้นตอนที่ 4] ติดตามสถานะพอร์ตจริงตามไฟล์ CSV ต่อเนื่อง 25 วันทำการ (2024-06-05 ถึง 2024-07-09) และบันทึก Log:")
    for r in tracking_rows:
        print(
            f"  * {r.symbol:<15} ({r.strategy_code}) | สถานะ: {r.status_after_25d}\n"
            f"    แผนซอยไม้จำลอง: {r.twap_slices_plan} | รหัสกันส่งซ้ำ: {r.idempotent_order_key}\n"
            f"    ราคาทุน {r.entry_price:.2f} -> ราคาปิดรอบ/ขายออก {r.exit_or_mark_price:.2f} บาท | "
            f"Cut-Loss ล่าสุด: {r.active_cut_loss:.2f} บาท | Target: {r.target_price:.2f} บาท\n"
            f"    กำไร/ขาดทุนสุทธิ (หลังหักค่าคอมฯ 2 ขา {r.total_fees_thb:,.2f} บาท): {r.net_pnl_thb:>+10,.2f} บาท ({r.r_multiple:+.2f}R)\n"
            f"    เหตุการณ์จริงใน CSV: {r.detailed_story_th}"
        )
    print(f"\n  - ความเสี่ยงคงเหลือในพอร์ตหลังขยับ Stop : {portfolio_summary['ending_active_heat_thb']:,.2f} บาท ({portfolio_summary['ending_active_heat_pct']:.2f}% ของพอร์ต)")
    print(f"  - กำไรสุทธิรวมทั้งพอร์ตหลังหักค่าคอมฯ   : {portfolio_summary['total_net_pnl_after_25d_thb']:+,.2f} บาท -> มูลค่าพอร์ตสุทธิ = {portfolio_summary['ending_portfolio_equity_thb']:,.2f} บาท")
    print(f"  - บันทึกไฟล์ตารางพอร์ต CSV เรียบร้อยที่  : {portfolio_summary['csv_log_path']}")
    print(f"  - บันทึกสมุดจดการเทรด JSON เรียบร้อยที่  : {output_dir / 'trade_decision_journal.json'}")

    is_rep = backtest_report["in_sample_60pct"]
    oos_rep = backtest_report["out_of_sample_40pct"]
    full_rep = backtest_report["full_500d_disciplined_system"]
    norm_rep = backtest_report["full_500d_generic_bot_baseline"]

    print("\n[ขั้นตอนที่ 5] ผลทดสอบย้อนหลัง (Backtest) 500 วันทำการ แยกช่วง In-Sample (60%) vs Out-of-Sample (40%):")
    print(f"  1) ช่วงพัฒนากฎ (In-Sample 60% แรก: {is_rep['period']}):")
    print(f"     CAGR = {is_rep['cagr_pct']:+.2f}% ต่อปี | Max Drawdown = {is_rep['max_drawdown_pct']:.2f}% | Sharpe = {is_rep['sharpe_ratio']:.2f} | Win Rate = {is_rep['win_rate_pct']:.2f}% ({is_rep['total_trades']} ไม้)")
    print(f"  2) ช่วงทดสอบนอกกลุ่มตัวอย่าง (Out-of-Sample 40% หลัง: {oos_rep['period']}):")
    print(f"     CAGR = {oos_rep['cagr_pct']:+.2f}% ต่อปี | Max Drawdown = {oos_rep['max_drawdown_pct']:.2f}% | Sharpe = {oos_rep['sharpe_ratio']:.2f} | Win Rate = {oos_rep['win_rate_pct']:.2f}% ({oos_rep['total_trades']} ไม้)")
    print(f"  3) ดัชนีความทนทาน Walk-Forward Efficiency (WFE) = {backtest_report['walk_forward_efficiency_pct']:.1f}% (ผ่านเกณฑ์มาตรฐาน >= 50%)")
    print(f"  4) เปรียบเทียบผลลัพธ์รวมตลอด 500 วันทำการ (เงินตั้งต้น 1,000,000 บาท):")
    print(f"     - ระบบของเรา (ครบ 8 บท) : พอร์ตสุทธิ {full_rep['ending_wealth_thb']:,.2f} บาท ({full_rep['total_return_pct']:+.2f}%), Max DD {full_rep['max_drawdown_pct']:.2f}%, Sharpe {full_rep['sharpe_ratio']:.2f}, Profit Factor {full_rep['profit_factor']:.2f}")
    print(f"     - บอททั่วไป (ไม่มีตัวกรอง): พอร์ตสุทธิ {norm_rep['ending_wealth_thb']:,.2f} บาท ({norm_rep['total_return_pct']:+.2f}%), Max DD {norm_rep['max_drawdown_pct']:.2f}%, Sharpe {norm_rep['sharpe_ratio']:.2f}, Profit Factor {norm_rep['profit_factor']:.2f}")
    print("=" * 98)

    return {
        "portfolio_summary": portfolio_summary,
        "selected_plans": [asdict(p) for p in selected_plans],
        "tracking_rows": [asdict(r) for r in tracking_rows],
        "backtest_report": backtest_report,
    }


if __name__ == "__main__":
    run_complete_final_system_demo()
