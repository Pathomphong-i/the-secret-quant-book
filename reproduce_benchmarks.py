#!/usr/bin/env python3
"""
reproduce_benchmarks.py
=======================
สคริปต์จำลองตัวเลขสมมติฐานควบคุมเพื่อการศึกษา (Deterministic Educational Simulation Suite)
ประกอบชุดหนังสือ "The Secret Quant: วิเคราะห์หุ้นและสร้างระบบอย่างมีวินัย (ชุด 8 เล่ม)"
ผู้เขียน: ปฐมพงษ์ พิพัฒน์สุริยวงศ์

หมายเหตุความโปร่งใสสำคัญ:
ตัวเลขทั้งหมดในสคริปต์นี้เป็น "ชุดจำลองสมมติฐานควบคุมเพื่อการศึกษา (Illustrative Synthetic Scenarios)"
สร้างขึ้นเพื่อเปรียบเทียบให้เห็นบทบาททางทฤษฎีของการหักต้นทุนแฝง การกรองข้อมูลผิดปกติ การจำกัดขนาดไม้
และการควบคุมความเสี่ยงเมื่อควบคุมตัวแปรอื่นให้คงที่ ไม่ใช่ผลตอบแทนจากการซื้อขายจริงในตลาดหลักทรัพย์
และไม่ใช่การรับประกันผลตอบแทนในอนาคต
"""

from __future__ import annotations
import numpy as np
import pandas as pd


def run_table_b1_architecture_comparison() -> pd.DataFrame:
    """
    ตารางที่ ข.1: ตัวอย่างเปรียบเทียบสถานการณ์จำลอง 3 รูปแบบภายใต้สมมติฐานควบคุมเพื่อการศึกษา
    (สมมติเงินตั้งต้นจำลอง 1,000,000 บาท หักค่าธรรมเนียมจำลอง 0.157% ต่อขา และส่วนต่างราคาจำลอง)
    หมายเหตุ: เป็นตัวเลขสาธิตเชิงแนวคิดเพื่อชี้ให้เห็นผลของการควบคุมความเสี่ยงขาลง (Max Drawdown)
    ไม่ใช่ผลการดำเนินงานจริงและไม่ใช่คำแนะนำการลงทุน
    """
    rows = [
        {
            "tier": "1. พอร์ตจำลองซื้อถือกระจายน้ำหนักเท่ากัน (Equal-Weight Baseline Demo)",
            "ending_equity_thb": 1_420_000,
            "total_return_pct": 42.00,
            "cagr_pct": 7.29,
            "max_dd_pct": -28.40,
            "profit_factor": 1.25,
            "verification_type": "SYNTHETIC_BASELINE_DEMO",
        },
        {
            "tier": "2. ระบบจำลองกฎพื้นฐาน เล่ม 1–2 (ไม่มีตัวกรองสภาวะตลาดและเพดานความเสี่ยงรวม)",
            "ending_equity_thb": 1_485_000,
            "total_return_pct": 48.50,
            "cagr_pct": 8.23,
            "max_dd_pct": -34.10,
            "profit_factor": 1.32,
            "verification_type": "SYNTHETIC_FOUNDATION_DEMO",
        },
        {
            "tier": "3. ระบบจำลองครบ 4 เสาหลัก เล่ม 1–8 (เพิ่มด่านตรวจข้อมูล คุมขนาดไม้ และเพดานความเสี่ยง)",
            "ending_equity_thb": 1_610_000,
            "total_return_pct": 61.00,
            "cagr_pct": 9.99,
            "max_dd_pct": -16.80,
            "profit_factor": 1.54,
            "verification_type": "SYNTHETIC_FULL_PIPELINE_DEMO",
        },
    ]
    return pd.DataFrame(rows)


def simulate_controlled_ablation_series(
    n_days: int = 2450,
    ann_return_target: float = 0.08,
    ann_vol_target: float = 0.14,
    seed: int = 2026,
) -> dict[str, float]:
    """
    จำลองเส้นทางผลตอบแทนสุ่มภายใต้สมมติฐานควบคุม (Controlled Synthetic Path)
    ด้วย Deterministic RNG Seed เพื่อให้ผู้อ่านรันซ้ำและตรวจสอบสูตรคำนวณ CAGR, Sharpe, MaxDD ได้ตรงกัน
    """
    rng = np.random.default_rng(seed)
    daily_mu = ann_return_target / 245.0
    daily_sigma = ann_vol_target / np.sqrt(245.0)
    rets = rng.normal(daily_mu, daily_sigma, size=n_days)
    eq = np.cumprod(1.0 + rets)
    peaks = np.maximum.accumulate(eq)
    dd = (eq / peaks) - 1.0
    realized_cagr = float(eq[-1] ** (245.0 / n_days) - 1.0)
    realized_vol = float(np.std(rets, ddof=1) * np.sqrt(245.0))
    return {
        "sim_cagr_pct": round(realized_cagr * 100, 1),
        "sim_sharpe": round(realized_cagr / max(realized_vol, 1e-9), 2),
        "sim_max_dd_pct": round(float(np.min(dd)) * 100, 1),
    }


def get_table_b2_controlled_ablations() -> dict[str, pd.DataFrame]:
    """
    ตารางที่ ข.2 ประจำเล่มที่ 3 ถึง เล่มที่ 8 (ชุดจำลองสมมติฐานควบคุมเพื่อเปรียบเทียบทีละองค์ประกอบ)
    ใช้สำหรับอธิบายแนวคิดการแยกทดสอบทีละโมดูล (Ablation Study) ไม่ใช่การรับรองผลกำไรในตลาดจริง
    """
    return {
        "Vol 3 (Data Hygiene & Backtest Validation Demo)": pd.DataFrame([
            {"configuration": "1. ทดสอบบนข้อมูลดิบที่ยังไม่ปรับแตกพาร์และเผลอใช้ข้อมูลอนาคต", "in_sample_cagr_pct": 26.4, "oos_cagr_pct": -5.2, "max_dd_pct": -36.5, "wfe_pct": 0.0},
            {"configuration": "2. ปรับฐานข้อมูลถูกต้อง แต่เลือกพารามิเตอร์จากจุดสูงสุดเดี่ยว", "in_sample_cagr_pct": 16.2, "oos_cagr_pct": 3.8, "max_dd_pct": -24.1, "wfe_pct": 23.5},
            {"configuration": "3. ข้อมูลตามเวลาจริง + เลือกช่วงพารามิเตอร์ที่เสถียร + Walk-Forward", "in_sample_cagr_pct": 10.8, "oos_cagr_pct": 7.9, "max_dd_pct": -15.4, "wfe_pct": 73.1},
        ]),
        "Vol 4 (Statistical Signal Filtering Demo)": pd.DataFrame([
            {"configuration": "1. ใช้เส้นค่าเฉลี่ยตัดกันเดี่ยวในทุกสภาวะตลาด", "cagr_pct": 3.2, "win_rate_pct": 33.0, "profit_factor": 1.06, "max_dd_pct": -28.5, "sharpe": 0.25},
            {"configuration": "2. ซื้อเมื่อทะลุกรอบราคา 20 วัน โดยไม่กรองปริมาณซื้อขาย", "cagr_pct": 6.5, "win_rate_pct": 38.5, "profit_factor": 1.21, "max_dd_pct": -22.0, "sharpe": 0.52},
            {"configuration": "3. กรองสภาวะตลาด + ปริมาณซื้อขายสัมพัทธ์ (RVOL) + ตำแหน่งราคาปิด (CLV)", "cagr_pct": 9.8, "win_rate_pct": 48.0, "profit_factor": 1.48, "max_dd_pct": -14.8, "sharpe": 0.94},
        ]),
        "Vol 5 (Position Sizing & Portfolio Risk Demo)": pd.DataFrame([
            {"configuration": "1. สัญญาณชุดเดียวกัน + ซื้อไม้ละเท่ากันโดยไม่คำนึงความผันผวน", "cagr_pct": 6.8, "max_dd_pct": -27.4, "sharpe": 0.54, "calmar": 0.25},
            {"configuration": "2. สัญญาณชุดเดียวกัน + คำนวณขนาดไม้ตาม ATR (งบความเสี่ยง 1%)", "cagr_pct": 8.6, "max_dd_pct": -17.9, "sharpe": 0.82, "calmar": 0.48},
            {"configuration": "3. ATR Sizing + กระจายน้ำหนักความเสี่ยง + เพดานความเสี่ยงพอร์ตรวม 5%", "cagr_pct": 9.6, "max_dd_pct": -12.8, "sharpe": 1.05, "calmar": 0.75},
        ]),
        "Vol 6 (Order Book & Execution Cost Demo)": pd.DataFrame([
            {"configuration": "1. ส่งคำสั่งซื้อรวดเดียวตอนเปิดตลาดโดยไม่เช็กส่วนต่างราคา", "avg_friction_pct": 0.95, "net_cagr_pct": 5.8, "sharpe": 0.51},
            {"configuration": "2. ตั้งรอรับฝั่ง Bid อย่างเดียวตลอดทั้งวัน (เสี่ยงไม่ได้หุ้นขาขึ้น)", "avg_friction_pct": 0.44, "net_cagr_pct": 7.4, "sharpe": 0.72},
            {"configuration": "3. ตรวจความกว้าง Spread + แบ่งซอยคำสั่งย่อยตามเวลาและปริมาณซื้อขาย", "avg_friction_pct": 0.38, "net_cagr_pct": 9.1, "sharpe": 0.92},
        ]),
        "Vol 7 (Structured News & Financial Hygiene Demo)": pd.DataFrame([
            {"configuration": "1. ใช้สัญญาณราคาและปริมาณซื้อขายเพียงอย่างเดียว", "cagr_pct": 8.2, "win_rate_pct": 45.0, "max_dd_pct": -18.4, "sharpe": 0.78},
            {"configuration": "2. เพิ่มด่านคัดกรองคุณภาพกระแสเงินสดและภาระหนี้พื้นฐาน", "cagr_pct": 9.1, "win_rate_pct": 48.5, "max_dd_pct": -15.6, "sharpe": 0.91},
            {"configuration": "3. เพิ่มการตรวจเวลาข่าว Point-in-Time และด่านทบทวนข้อมูลประกอบ", "cagr_pct": 9.9, "win_rate_pct": 50.5, "max_dd_pct": -13.9, "sharpe": 1.02},
        ]),
        "Vol 8 (Operational Safeguards & Multi-Asset Demo)": pd.DataFrame([
            {"configuration": "1. พอร์ตสินทรัพย์เดียวโดยไม่มีระบบกระทบยอดและสวิตช์หยุดฉุกเฉิน", "cagr_pct": 7.5, "max_dd_pct": -22.6, "sharpe": 0.64},
            {"configuration": "2. เพิ่มการกระทบยอดอัตโนมัติและการจำลองป้องกันความเสี่ยงขาลงบางส่วน", "cagr_pct": 8.4, "max_dd_pct": -14.5, "sharpe": 0.88},
            {"configuration": "3. กระจายความเสี่ยงหลายสินทรัพย์จำลองและคุมเพดานความผันผวนรวม", "cagr_pct": 9.2, "max_dd_pct": -11.8, "sharpe": 1.04},
        ]),
    }


if __name__ == "__main__":
    print("=" * 88)
    print("หมายเหตุ: ข้อมูลจำลองสมมติฐานควบคุมเพื่อการศึกษาเท่านั้น (ไม่ใช่ผลตอบแทนจริงและไม่ใช่คำแนะนำการลงทุน)")
    print("=" * 88)
    print("1. ตารางที่ ข.1: ตัวอย่างเปรียบเทียบสถานการณ์จำลอง 3 รูปแบบ")
    print("-" * 88)
    df_b1 = run_table_b1_architecture_comparison()
    print(df_b1.to_string(index=False))

    print("\n" + "=" * 88)
    print("2. ตารางที่ ข.2: ชุดจำลองเปรียบเทียบผลของแต่ละองค์ประกอบ (Controlled Synthetic Ablation Demo)")
    print("-" * 88)
    for vol_title, df_b2 in get_table_b2_controlled_ablations().items():
        print(f"\n--- {vol_title} ---")
        print(df_b2.to_string(index=False))

    print("\n" + "=" * 88)
    print("3. ตัวอย่างการสุ่มจำลองเส้นทางผลตอบแทนซ้ำได้ (Deterministic Synthetic Path, seed=2026)")
    print("-" * 88)
    print(simulate_controlled_ablation_series(seed=2026))
