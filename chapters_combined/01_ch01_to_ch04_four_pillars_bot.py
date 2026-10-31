from __future__ import annotations
# ==============================================================================
# หนังสือ: โรบอทเทรด ที่โบรกเกอร์ไม่อยากให้คุณเขียน
# ผู้เขียน: ปฐมพงษ์ พิพัฒน์สุริยวงศ์
# คำเตือน: เนื้อหาและโค้ดในไฟล์นี้จัดทำขึ้นเพื่อการศึกษาและเป็นความคิดเห็นส่วนตัวของผู้เขียนเท่านั้น
#         มิใช่การแนะนำการลงทุน ผู้ลงทุนโปรดศึกษาข้อมูลและความเสี่ยงด้วยตนเอง
# ==============================================================================

"""บทที่ 1–4: โครงสร้างบอท 4 เสาหลัก, การทำความสะอาดข้อมูล และ Starter Bot"""

# --- Source: script_01.py ---
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


# --- Source: script_02.py ---
#!/usr/bin/env python3
"""
Starter Concept Bot — พิมพ์เขียวบอทเทรด 4 เสาหลัก (The 4-Pillar Modular Trading Bot)
====================================================================================
ตัวอย่างโค้ดจาก บทที่ 4: หนังสือ "บอทเทรดที่กองทุนไม่อยากให้คุณรู้ (The Secret Quant)"

ประกอบด้วย 4 เสาหลักที่แยกหน้าที่กันอย่างชัดเจน:
1. DataEngine          : ตรวจสอบความสะอาดของข้อมูลราคา OHLCV และคำนวณ Indicators พื้นฐาน
2. SignalEngine        : แปลงกฎการเทรดเป็น Deterministic Logic (Trend + ATR Breakout + Volume)
3. RiskPortfolioEngine : คำนวณขนาดไม้ตามความผันผวน (1% Equity Risk per Trade) และปัด Board Lot 100 หุ้น
4. ExecutionEngine     : ส่งคำสั่งซื้อขายผ่าน Settrade Open API (settrade-v2) หรือโหมด Paper Simulation
"""


from dataclasses import dataclass, field
from typing import Dict, List, Optional
import math
import numpy as np
import pandas as pd


# ============================================================================
# โครงสร้างข้อมูลมาตรฐานสำหรับสื่อสารระหว่าง 4 เสาหลัก (Data Contracts)
# ============================================================================

@dataclass
class TradeSignal:
    symbol: str
    action: str               # "BUY" หรือ "EXIT"
    signal_price: float       # ราคาปิดของแท่งเทียนที่เกิดสัญญาณ
    atr_value: float          # ค่าความผันผวน ATR(14) ณ จุดเกิดสัญญาณ
    suggested_stop: float     # จุดตัดขาดทุนเริ่มต้นที่คำนวณจาก ATR
    reason: str               # เหตุผลชัดเจนที่เกิดสัญญาณ (Deterministic Audit Log)


@dataclass
class OrderIntent:
    symbol: str
    side: str                 # "Buy" หรือ "Sell"
    shares: int               # จำนวนหุ้นที่ผ่านการคำนวณความเสี่ยงและปัดเศษ 100 หุ้นแล้ว
    limit_price: float        # ราคา Limit ที่อนุญาตให้ส่งคำสั่ง
    stop_loss_price: float    # ราคาตัดขาดทุนที่ผูกติดกับไม้นี้
    risk_amount_thb: float    # จำนวนเงินบาทสูงสุดที่ยอมเสียในไม้นี้
    reason: str


@dataclass
class ActivePosition:
    symbol: str
    shares: int
    entry_price: float
    entry_atr: float
    hard_stop_price: float
    highest_price_seen: float
    entry_reason: str


# ============================================================================
# เสาหลักที่ 1: Data Engine (ระบบจัดการข้อมูลและทำความสะอาดราคา)
# ============================================================================

class DataEngine:
    """
    รับผิดชอบการตรวจสอบความสมบูรณ์ของข้อมูลราคา OHLCV
    และคำนวณตัวชี้วัดทางสถิติโดยใช้เฉพาะข้อมูลที่จบแท่งแล้วเท่านั้น
    """

    @staticmethod
    def prepare_clean_features(df: pd.DataFrame) -> pd.DataFrame:
        required_cols = {"open", "high", "low", "close", "volume"}
        missing = required_cols - set(df.columns.str.lower())
        if missing:
            raise ValueError(f"ข้อมูลราคาขาดคอลัมน์สำคัญ: {missing}")

        clean = df.copy()
        clean.columns = [c.lower() for c in clean.columns]

        # 1. กรองแถวที่ราคาติดลบหรือไม่มีการซื้อขายจริงออก (Data Hygiene)
        clean = clean[(clean["close"] > 0) & (clean["high"] >= clean["low"]) & (clean["volume"] >= 0)].copy()
        clean.sort_index(inplace=True)

        # 2. คำนวณเส้นค่าเฉลี่ยเคลื่อนที่สำหรับกรองแนวโน้มใหญ่ (Trend Filter)
        clean["ema_50"] = clean["close"].ewm(span=50, adjust=False).mean()
        clean["ema_200"] = clean["close"].ewm(span=200, adjust=False).mean()

        # 3. คำนวณความผันผวนจริง Average True Range (ATR 14)
        prev_close = clean["close"].shift(1)
        tr1 = clean["high"] - clean["low"]
        tr2 = (clean["high"] - prev_close).abs()
        tr3 = (clean["low"] - prev_close).abs()
        true_range = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        clean["atr_14"] = true_range.rolling(window=14, min_periods=14).mean()

        # 4. คำนวณกรอบราคาสูงสุด 20 วันย้อนหลัง (ใช้ .shift(1) เพื่อป้องกัน Look-Ahead Bias!)
        clean["prev_20d_high"] = clean["high"].shift(1).rolling(window=20, min_periods=20).max()
        clean["avg_vol_20"] = clean["volume"].shift(1).rolling(window=20, min_periods=20).mean()

        return clean.dropna()


# ============================================================================
# เสาหลักที่ 2: Signal Engine (ระบบคัดกรองโอกาสด้วย Deterministic Logic)
# ============================================================================

class SignalEngine:
    """
    แปลงกลยุทธ์เป็นกฎเหล็กที่ปราศจากอารมณ์ 100%:
    - เข้าซื้อเมื่อ: โครงสร้างเป็นขาขึ้น (Close > EMA200 & EMA50 > EMA200)
                  + ราคาทะลุ High 20 วันเกิน 0.25 ATR
                  + Volume มากกว่าค่าเฉลี่ย 20 วันอย่างน้อย 1.5 เท่า
    - ขายออกเมื่อ: ราคาหลุด Hard Stop (Entry - 2.0 ATR) หรือ Trailing Stop (Peak - 3.0 ATR)
    """

    def __init__(
        self,
        breakout_atr_mult: float = 0.25,
        volume_surge_mult: float = 1.50,
        hard_stop_atr_mult: float = 2.00,
        trailing_stop_atr_mult: float = 3.00,
    ) -> None:
        self.breakout_atr_mult = breakout_atr_mult
        self.volume_surge_mult = volume_surge_mult
        self.hard_stop_atr_mult = hard_stop_atr_mult
        self.trailing_stop_atr_mult = trailing_stop_atr_mult

    def evaluate_exit(
        self,
        symbol: str,
        latest_bar: pd.Series,
        position: ActivePosition,
    ) -> Optional[TradeSignal]:
        close_price = float(latest_bar["close"])
        atr = float(latest_bar["atr_14"])

        # อัปเดตราคาสูงสุดที่เคยทำได้ระหว่างถือครองเพื่อเลื่อน Trailing Stop ขึ้น
        position.highest_price_seen = max(position.highest_price_seen, close_price)
        trailing_stop = position.highest_price_seen - (self.trailing_stop_atr_mult * atr)
        effective_stop = max(position.hard_stop_price, trailing_stop)

        if close_price < effective_stop:
            exit_type = "HARD_STOP" if effective_stop == position.hard_stop_price else "TRAILING_STOP"
            return TradeSignal(
                symbol=symbol,
                action="EXIT",
                signal_price=close_price,
                atr_value=atr,
                suggested_stop=effective_stop,
                reason=f"{exit_type}_TRIGGERED (Close {close_price:.2f} < Stop {effective_stop:.2f})",
            )
        return None

    def evaluate_entry(
        self,
        symbol: str,
        latest_bar: pd.Series,
    ) -> Optional[TradeSignal]:
        close_price = float(latest_bar["close"])
        ema_50 = float(latest_bar["ema_50"])
        ema_200 = float(latest_bar["ema_200"])
        atr = float(latest_bar["atr_14"])
        prev_high = float(latest_bar["prev_20d_high"])
        volume = float(latest_bar["volume"])
        avg_vol = float(latest_bar["avg_vol_20"])

        # กฎข้อที่ 1: โครงสร้างแนวโน้มใหญ่ต้องเป็นขาขึ้นชัดเจน
        is_uptrend = (close_price > ema_200) and (ema_50 > ema_200)

        # กฎข้อที่ 2: ราคาปิดเบรกเอาต์กรอบ 20 วันด้วยระยะที่มีนัยสำคัญทางความผันผวน
        breakout_level = prev_high + (self.breakout_atr_mult * atr)
        is_breakout = close_price >= breakout_level

        # กฎข้อที่ 3: มีปริมาณการซื้อขาย (Volume) เข้ามายืนยันของจริง
        is_volume_confirmed = volume >= (self.volume_surge_mult * avg_vol)

        if is_uptrend and is_breakout and is_volume_confirmed:
            initial_stop = close_price - (self.hard_stop_atr_mult * atr)
            return TradeSignal(
                symbol=symbol,
                action="BUY",
                signal_price=close_price,
                atr_value=atr,
                suggested_stop=initial_stop,
                reason=(
                    f"TREND_ATR_BREAKOUT (Close={close_price:.2f} >= {breakout_level:.2f}, "
                    f"Vol={volume / max(avg_vol, 1.0):.2f}x Avg)"
                ),
            )
        return None


# ============================================================================
# เสาหลักที่ 3: Risk & Portfolio Engine (หัวใจหลัก: หน้าตักและการคุมความเสี่ยง)
# ============================================================================

class RiskPortfolioEngine:
    """
    ควบคุมความเสี่ยงของพอร์ตอย่างเคร่งครัด:
    - จำกัดความเสี่ยงต่อไม้ไว้ไม่เกิน risk_per_trade_pct (เช่น 1.0% ของพอร์ต)
    - จำกัดจำนวนหุ้นที่ถือพร้อมกันสูงสุด (max_positions)
    - ปัดเศษจำนวนหุ้นเป็นทวีคูณของ 100 หุ้น (SET Board Lot) เสมอ
    """

    def __init__(
        self,
        initial_cash: float = 500_000.0,
        risk_per_trade_pct: float = 0.01,
        max_positions: int = 5,
        max_position_weight_pct: float = 0.25,
        board_lot_size: int = 100,
    ) -> None:
        self.cash: float = initial_cash
        self.risk_per_trade_pct = risk_per_trade_pct
        self.max_positions = max_positions
        self.max_position_weight_pct = max_position_weight_pct
        self.board_lot_size = board_lot_size
        self.positions: Dict[str, ActivePosition] = {}

    def get_total_equity(self, latest_prices: Dict[str, float]) -> float:
        market_value = sum(
            pos.shares * latest_prices.get(sym, pos.entry_price)
            for sym, pos in self.positions.items()
        )
        return self.cash + market_value

    def size_and_approve_order(
        self,
        signal: TradeSignal,
        latest_prices: Dict[str, float],
    ) -> Optional[OrderIntent]:
        # หากเป็นสัญญาณสั่งขาย (EXIT) ให้อนุมัติขายเต็มจำนวนที่ถืออยู่ทันที
        if signal.action == "EXIT":
            pos = self.positions.get(signal.symbol)
            if not pos:
                return None
            return OrderIntent(
                symbol=signal.symbol,
                side="Sell",
                shares=pos.shares,
                limit_price=signal.signal_price,
                stop_loss_price=signal.suggested_stop,
                risk_amount_thb=0.0,
                reason=signal.reason,
            )

        # หากเป็นสัญญาณซื้อ (BUY) ต้องผ่านด่านตรวจความเสี่ยง 4 ด่าน
        if signal.symbol in self.positions:
            return None  # ด่านที่ 1: ห้ามซื้อถัวหุ้นเดิมซ้ำซ้อนโดยไร้แผน
        if len(self.positions) >= self.max_positions:
            return None  # ด่านที่ 2: พอร์ตถือหุ้นเต็มจำนวนสล็อตแล้ว

        total_equity = self.get_total_equity(latest_prices)
        risk_budget_thb = total_equity * self.risk_per_trade_pct
        risk_per_share = signal.signal_price - signal.suggested_stop

        if risk_per_share <= 0:
            return None

        # ด่านที่ 3: คำนวณจำนวนหุ้นตามความเสี่ยง 1% และจำกัดน้ำหนักไม่ให้กระจุกตัวเกิน 25% ของพอร์ต
        raw_shares_by_risk = risk_budget_thb / risk_per_share
        max_capital_for_slot = min(self.cash * 0.98, total_equity * self.max_position_weight_pct)
        raw_shares_by_capital = max_capital_for_slot / signal.signal_price

        safe_raw_shares = min(raw_shares_by_risk, raw_shares_by_capital)

        # ด่านที่ 4: ปัดลงเป็นทวีคูณของ Board Lot (100 หุ้น)
        lots = math.floor(safe_raw_shares / self.board_lot_size)
        final_shares = lots * self.board_lot_size

        if final_shares < self.board_lot_size:
            return None  # เงินสดหรือขนาดพอร์ตไม่พอซื้อขั้นต่ำ 100 หุ้นอย่างปลอดภัย

        actual_risk_thb = final_shares * risk_per_share
        return OrderIntent(
            symbol=signal.symbol,
            side="Buy",
            shares=final_shares,
            limit_price=signal.signal_price,
            stop_loss_price=signal.suggested_stop,
            risk_amount_thb=actual_risk_thb,
            reason=signal.reason,
        )


# ============================================================================
# เสาหลักที่ 4: Execution Engine (ระบบส่งคำสั่งซื้อขายจริงผ่าน API / Paper Mode)
# ============================================================================

class ExecutionEngine:
    """
    ทำหน้าที่ส่งคำสั่งซื้อขายไปยังโบรกเกอร์ (รองรับทั้งโหมด Paper Simulation
    และการเชื่อมต่อ Settrade Open API v2 สำหรับใช้งานจริง)
    """

    def __init__(
        self,
        paper_trading: bool = True,
        commission_rate: float = 0.00168,  # 0.157% + VAT 7%
        settrade_equity_account: Optional[object] = None,
        pin: str = "000000",
    ) -> None:
        self.paper_trading = paper_trading
        self.commission_rate = commission_rate
        self.settrade_equity_account = settrade_equity_account
        self.pin = pin
        self.execution_logs: List[str] = []

    def execute_order(
        self,
        intent: OrderIntent,
        portfolio: RiskPortfolioEngine,
        atr_value: float,
    ) -> bool:
        gross_value = intent.shares * intent.limit_price
        commission = gross_value * self.commission_rate

        # กรณีเชื่อมต่อโบรกเกอร์จริงผ่าน Settrade Open API (settrade-v2)
        if not self.paper_trading and self.settrade_equity_account is not None:
            self.settrade_equity_account.place_order(
                pin=self.pin,
                symbol=intent.symbol,
                side=intent.side,
                volume=intent.shares,
                price=intent.limit_price,
                price_type="Limit",
                validity_type="Day",
            )

        # อัปเดตสถานะพอร์ตและเงินสดทันที
        if intent.side == "Buy":
            total_cost = gross_value + commission
            if total_cost > portfolio.cash:
                return False
            portfolio.cash -= total_cost
            portfolio.positions[intent.symbol] = ActivePosition(
                symbol=intent.symbol,
                shares=intent.shares,
                entry_price=intent.limit_price,
                entry_atr=atr_value,
                hard_stop_price=intent.stop_loss_price,
                highest_price_seen=intent.limit_price,
                entry_reason=intent.reason,
            )
            log_msg = (
                f"[EXECUTE BUY]  {intent.symbol} | {intent.shares:,} หุ้น @ {intent.limit_price:.2f} ฿ | "
                f"Stop={intent.stop_loss_price:.2f} ฿ | Risk={intent.risk_amount_thb:,.0f} ฿ | {intent.reason}"
            )
            self.execution_logs.append(log_msg)
            print(log_msg)
            return True

        elif intent.side == "Sell":
            pos = portfolio.positions.pop(intent.symbol, None)
            if pos is None:
                return False
            net_proceeds = gross_value - commission
            portfolio.cash += net_proceeds
            pnl_thb = net_proceeds - (pos.shares * pos.entry_price * (1.0 + self.commission_rate))
            pnl_pct = (intent.limit_price / pos.entry_price - 1.0) * 100.0
            log_msg = (
                f"[EXECUTE SELL] {intent.symbol} | {intent.shares:,} หุ้น @ {intent.limit_price:.2f} ฿ | "
                f"Net PnL={pnl_thb:+,.2f} ฿ ({pnl_pct:+.2f}%) | {intent.reason}"
            )
            self.execution_logs.append(log_msg)
            print(log_msg)
            return True

        return False


# ============================================================================
# ตัวควบคุมหลัก (Bot Orchestrator): ร้อยเรียงทั้ง 4 เสาหลักเข้าด้วยกัน
# ============================================================================

class StarterTradingBotOrchestrator:
    def __init__(self, initial_cash: float = 500_000.0) -> None:
        self.data_engine = DataEngine()
        self.signal_engine = SignalEngine()
        self.portfolio_engine = RiskPortfolioEngine(initial_cash=initial_cash)
        self.execution_engine = ExecutionEngine(paper_trading=True)

    def run_daily_cycle(self, market_data_by_symbol: Dict[str, pd.DataFrame]) -> None:
        cleaned_bars: Dict[str, pd.Series] = {}
        latest_prices: Dict[str, float] = {}

        # ขั้นที่ 1: Data Engine ทำความสะอาดและเตรียมข้อมูลล่าสุดของทุกตัว
        for symbol, raw_df in market_data_by_symbol.items():
            clean_df = self.data_engine.prepare_clean_features(raw_df)
            if not clean_df.empty:
                latest_bar = clean_df.iloc[-1]
                cleaned_bars[symbol] = latest_bar
                latest_prices[symbol] = float(latest_bar["close"])

        # ขั้นที่ 2: ตรวจสอบสัญญาณขาย (EXIT) ของหุ้นที่ถืออยู่ในพอร์ตก่อนเสมอ (Risk First!)
        for symbol in list(self.portfolio_engine.positions.keys()):
            if symbol not in cleaned_bars:
                continue
            pos = self.portfolio_engine.positions[symbol]
            exit_signal = self.signal_engine.evaluate_exit(symbol, cleaned_bars[symbol], pos)
            if exit_signal:
                intent = self.portfolio_engine.size_and_approve_order(exit_signal, latest_prices)
                if intent:
                    self.execution_engine.execute_order(
                        intent, self.portfolio_engine, exit_signal.atr_value
                    )

        # ขั้นที่ 3: สแกนหาสัญญาณซื้อ (BUY) ในหุ้นที่ผ่านเกณฑ์และคำนวณขนาดไม้ตามความเสี่ยง
        for symbol, latest_bar in cleaned_bars.items():
            if symbol in self.portfolio_engine.positions:
                continue
            entry_signal = self.signal_engine.evaluate_entry(symbol, latest_bar)
            if entry_signal:
                intent = self.portfolio_engine.size_and_approve_order(entry_signal, latest_prices)
                if intent:
                    self.execution_engine.execute_order(
                        intent, self.portfolio_engine, entry_signal.atr_value
                    )


if __name__ == "__main__":
    # ตัวอย่างการจำลองข้อมูลราคาหุ้น 250 วันเพื่อทดสอบการทำงานของบอท 4 เสาหลัก
    rng = np.random.default_rng(7)
    dates = pd.date_range("2025-01-01", periods=250, freq="B")
    trend_prices = 20.0 + np.cumsum(rng.normal(0.06, 0.35, size=250))
    trend_prices[-1] = trend_prices[-2] + 1.25  # จำลองแท่งเบรกเอาต์วันล่าสุด

    sample_df = pd.DataFrame(
        {
            "open": trend_prices - 0.15,
            "high": trend_prices + 0.30,
            "low": trend_prices - 0.30,
            "close": trend_prices,
            "volume": np.append(rng.integers(1_000_000, 1_500_000, size=249), [3_200_000]),
        },
        index=dates,
    )

    bot = StarterTradingBotOrchestrator(initial_cash=500_000.0)
    bot.run_daily_cycle({"SAMPLE_SET_STOCK": sample_df})
    print("=== ผลการรันวงจรบอท 4 เสาหลัก (StarterTradingBotOrchestrator) ===")
    print(f"เงินสดคงเหลือ: {bot.portfolio_engine.cash:,.2f} บาท | สถานะถือครอง: {list(bot.portfolio_engine.positions.keys())}")
    for pos in bot.portfolio_engine.positions.values():
        print(f"  - {pos.symbol}: {pos.shares:,} หุ้น @ {pos.entry_price:.2f} บาท | Stop Loss: {pos.stop_loss:.2f} บาท ({pos.entry_reason})")


