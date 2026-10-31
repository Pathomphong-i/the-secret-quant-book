#!/usr/bin/env python3
"""
บทที่ 2: การจำลองเปรียบเทียบ (Simulation) เปิดโปงกลลวงบอทเช่ากล่องดำ
เปรียบเทียบ:
1. Black-Box Martingale Bot (โชว์ Win Rate > 90% ด้วยการถัวเฉลี่ยขาลง ไม่ใส่ Stop Loss)
2. White-Box Systematic Bot (Win Rate แค่ ~45-50% แต่คุมความเสี่ยง 1% ต่อไม้ และปล่อยกำไรวิ่ง)
"""

from dataclasses import dataclass
from typing import List
import numpy as np


@dataclass
class SimulationSummary:
    bot_name: str
    total_cycles: int
    win_rate_pct: float
    peak_capital: float
    ending_capital: float
    max_drawdown_pct: float
    survived: bool


def simulate_blackbox_martingale_bot(
    initial_capital: float = 1_000_000.0,
    cycles: int = 120,
    seed: int = 42,
) -> SimulationSummary:
    """
    จำลองบอทเช่ากล่องดำ:
    - ในสภาวะตลาดปกติ (โอกาส 94% ต่อรอบ) บอทจะถัวเฉลี่ยจนกลับมาปิดกำไรเล็กน้อย (+1.2% ของพอร์ต)
    - แต่เมื่อเกิดสภาวะตลาดไหลลงแรงโดยไม่เด้ง (Tail Event โอกาสเพียง 6%)
      การเบิ้ลไม้ถัว 1 -> 2 -> 4 -> 8 ไม้โดยไร้ Stop Loss จะทำให้พอร์ตเสียหายหนัก (-65% ในรอบเดียว)
    """
    rng = np.random.default_rng(seed)
    capital = initial_capital
    peak = initial_capital
    max_dd = 0.0
    wins = 0

    for _ in range(cycles):
        is_tail_crash = rng.random() < 0.06  # โอกาสเกิดวิกฤตลากยาวเพียง 6%
        if not is_tail_crash:
            # ชนะเก็บเหรียญบาท: ได้กำไรรอบละ +1.2%
            capital *= 1.012
            wins += 1
        else:
            # หายนะจากการถัวเฉลี่ยขาลงจนเต็มพอร์ตโดยไม่คัท
            capital *= 0.35  # ขาดทุนหนัก -65% ในรอบเดียว

        peak = max(peak, capital)
        dd = (peak - capital) / peak * 100.0
        max_dd = max(max_dd, dd)

    return SimulationSummary(
        bot_name="Black-Box Rental Bot (Martingale / No Stop-Loss)",
        total_cycles=cycles,
        win_rate_pct=(wins / cycles) * 100.0,
        peak_capital=peak,
        ending_capital=capital,
        max_drawdown_pct=max_dd,
        survived=capital >= initial_capital * 0.5,
    )


def simulate_whitebox_systematic_bot(
    initial_capital: float = 1_000_000.0,
    cycles: int = 120,
    seed: int = 42,
) -> SimulationSummary:
    """
    จำลองบอทที่ออกแบบมาดีที่คุณเขียนเอง:
    - ยอมรับความจริงว่าไม่มีใครรู้อนาคต: Win Rate เพียง ~48%
    - เวลาผิดทาง: ตัดขาดทุนไว (Stop Loss คุมความเสี่ยงเสียแค่ -1.0% ของพอร์ตต่อรอบ)
    - เวลาถูกทาง: ปล่อยกำไรวิ่ง (Asymmetric Payoff เฉลี่ย +2.8% ของพอร์ตต่อรอบที่ชนะ)
    """
    rng = np.random.default_rng(seed)
    capital = initial_capital
    peak = initial_capital
    max_dd = 0.0
    wins = 0

    for _ in range(cycles):
        is_winner = rng.random() < 0.48  # อัตราชนะแค่ 48% (แพ้มากกว่าชนะ!)
        if is_winner:
            capital *= 1.028  # ชนะได้ +2.8% (Risk:Reward = 1 : 2.8)
            wins += 1
        else:
            capital *= 0.990  # แพ้โดนจำกัดความเสี่ยงไว้ที่ -1.0% เสมอ ไม่มีถัวขาลง

        peak = max(peak, capital)
        dd = (peak - capital) / peak * 100.0
        max_dd = max(max_dd, dd)

    return SimulationSummary(
        bot_name="White-Box DIY Quant Bot (Strict 1% Risk / Asymmetric R:R)",
        total_cycles=cycles,
        win_rate_pct=(wins / cycles) * 100.0,
        peak_capital=peak,
        ending_capital=capital,
        max_drawdown_pct=max_dd,
        survived=True,
    )


if __name__ == "__main__":
    blackbox = simulate_blackbox_martingale_bot()
    whitebox = simulate_whitebox_systematic_bot()

    for res in (blackbox, whitebox):
        print(f"=== {res.bot_name} ===")
        print(f"อัตราชนะ (Win Rate)     : {res.win_rate_pct:.1f}%")
        print(f"เงินทุนสูงสุดระหว่างทาง   : {res.peak_capital:,.2f} บาท")
        print(f"เงินทุนสุทธิเมื่อจบ 120 รอบ : {res.ending_capital:,.2f} บาท")
        print(f"Max Drawdown สูงสุด     : -{res.max_drawdown_pct:.2f}%\n")
