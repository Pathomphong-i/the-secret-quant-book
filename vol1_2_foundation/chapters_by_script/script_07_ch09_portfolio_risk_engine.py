import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class ActivePortfolioPosition:
    symbol: str
    sector: str
    shares: int
    entry_price: float
    current_price: float
    active_stop_loss: float

    @property
    def market_value(self) -> float:
        return self.shares * self.current_price

    @property
    def open_risk_amount(self) -> float:
        """
        คำนวณความเสี่ยงเปิด (Open Risk / Heat):
        หากขยับ Stop Loss ขึ้นมาสูงกว่าราคาทุนแล้ว (ล็อกกำไรแล้ว) ความเสี่ยงต่อเงินต้นจะนับเป็น 0
        แต่เพื่อความระมัดระวังที่ถูกต้องและใช้งานได้จริง เราคิดความเสี่ยงจากราคาปัจจุบันลงไปหา active_stop_loss
        """
        risk_per_share = max(0.0, self.current_price - self.active_stop_loss)
        return self.shares * risk_per_share


@dataclass
class RiskEngineConfig:
    risk_per_trade_pct: float = 0.01        # เสี่ยงไม้ละ 1.0% ของมูลค่าพอร์ตสุทธิ
    atr_stop_multiplier: float = 2.5        # ระยะ Stop Loss เริ่มต้น = 2.5 * ATR
    max_position_notional_pct: float = 0.20 # ห้ามซื้อหุ้นตัวเดียวเกิน 20% ของพอร์ต
    max_sector_notional_pct: float = 0.30   # ห้ามถือหุ้นกลุ่มอุตสาหกรรมเดียวกันเกิน 30% ของพอร์ต
    max_portfolio_heat_pct: float = 0.05    # เพดานความเสี่ยงเปิดรวมทั้งพอร์ตสูงสุด 5.0%
    max_pairwise_correlation: float = 0.65  # ห้ามถือหุ้นที่มี Correlation กันเกิน 0.65
    corr_lookback_bars: int = 60            # จำนวนวันย้อนหลังสำหรับคำนวณ Correlation Matrix
    lot_size: int = 100                     # ปัดจำนวนหุ้นเป็น Board Lot (เช่น ตลาดหุ้นไทยทีละ 100 หุ้น)


@dataclass
class AllocationDecision:
    approved: bool
    symbol: str
    recommended_shares: int
    position_notional: float
    initial_stop_price: float
    trade_risk_amount: float
    trade_risk_pct_of_equity: float
    max_corr_with_existing: float
    most_correlated_peer: Optional[str]
    rejection_or_adjustment_note: str


class PortfolioRiskEngine:
    """
    สมองกลบริหารความเสี่ยงและคำนวณขนาดไม้ที่ถูกต้องและใช้งานได้จริง:
    1. คำนวณ ATR Volatility-Adjusted Position Sizing
    2. ควบคุมเพดานความเสี่ยงรวมของพอร์ต (Portfolio Heat)
    3. ควบคุมการกระจุกตัวรายอุตสาหกรรม (Sector Exposure Cap)
    4. ตรวจสอบเมทริกซ์สหสัมพันธ์ (Pairwise Correlation Matrix Guard)
    """

    def __init__(self, config: RiskEngineConfig = RiskEngineConfig()):
        self.cfg = config

    def compute_current_portfolio_heat(
        self,
        total_equity: float,
        current_positions: Dict[str, ActivePortfolioPosition]
    ) -> float:
        if total_equity <= 0:
            return 1.0
        total_open_risk = sum(pos.open_risk_amount for pos in current_positions.values())
        return total_open_risk / total_equity

    def compute_max_correlation_with_portfolio(
        self,
        candidate_symbol: str,
        existing_symbols: List[str],
        returns_df: pd.DataFrame
    ) -> Tuple[float, Optional[str]]:
        """
        คำนวณค่าสหสัมพันธ์ (Correlation) ของผลตอบแทนรายวันย้อนหลัง 60 วัน
        ระหว่างหุ้นตัวใหม่ที่จะซื้อ กับหุ้นทุกตัวที่ถืออยู่ในพอร์ตปัจจุบัน
        """
        if not existing_symbols or candidate_symbol not in returns_df.columns:
            return 0.0, None

        valid_existing = [s for s in existing_symbols if s in returns_df.columns and s != candidate_symbol]
        if not valid_existing:
            return 0.0, None

        recent_returns = returns_df[[candidate_symbol] + valid_existing].tail(self.cfg.corr_lookback_bars)
        corr_Series = recent_returns.corr()[candidate_symbol].drop(candidate_symbol)

        if corr_Series.isna().all():
            return 0.0, None

        max_peer = str(corr_Series.idxmax())
        max_corr = float(corr_Series.loc[max_peer])
        return max_corr, max_peer

    def evaluate_and_size_order(
        self,
        candidate_symbol: str,
        candidate_sector: str,
        entry_price: float,
        current_atr: float,
        total_equity: float,
        available_cash: float,
        current_positions: Dict[str, ActivePortfolioPosition],
        historical_returns_df: pd.DataFrame
    ) -> AllocationDecision:
        """
        ประเมินความเสี่ยงและคำนวณจำนวนหุ้นที่เหมาะสมที่สุดก่อนส่งคำสั่งซื้อ
        """
        if current_atr <= 0 or entry_price <= 0:
            raise ValueError("entry_price และ current_atr ต้องมากกว่า 0")

        # -----------------------------------------------------------------
        # ขั้นตอนที่ 1: ตรวจสอบ Correlation เทียบกับหุ้นในพอร์ตปัจจุบัน
        # -----------------------------------------------------------------
        existing_syms = list(current_positions.keys())
        max_corr, corr_peer = self.compute_max_correlation_with_portfolio(
            candidate_symbol, existing_syms, historical_returns_df
        )

        if max_corr > self.cfg.max_pairwise_correlation:
            return AllocationDecision(
                approved=False,
                symbol=candidate_symbol,
                recommended_shares=0,
                position_notional=0.0,
                initial_stop_price=0.0,
                trade_risk_amount=0.0,
                trade_risk_pct_of_equity=0.0,
                max_corr_with_existing=round(max_corr, 3),
                most_correlated_peer=corr_peer,
                rejection_or_adjustment_note=(
                    f"[REJECTED - Correlation Guard] หุ้น {candidate_symbol} มีค่า Correlation "
                    f"สูงถึง {max_corr:.2f} เทียบกับ {corr_peer} ที่ถืออยู่ในพอร์ต (เพดานสูงสุด {self.cfg.max_pairwise_correlation})"
                )
            )

        # -----------------------------------------------------------------
        # ขั้นตอนที่ 2: ตรวจสอบเพดานความร้อนของพอร์ต (Portfolio Heat Cap)
        # -----------------------------------------------------------------
        current_heat_pct = self.compute_current_portfolio_heat(total_equity, current_positions)
        remaining_heat_pct = self.cfg.max_portfolio_heat_pct - current_heat_pct

        if remaining_heat_pct <= 0.002:  # เหลือโควตาความเสี่ยงน้อยกว่า 0.2%
            return AllocationDecision(
                approved=False,
                symbol=candidate_symbol,
                recommended_shares=0,
                position_notional=0.0,
                initial_stop_price=0.0,
                trade_risk_amount=0.0,
                trade_risk_pct_of_equity=0.0,
                max_corr_with_existing=round(max_corr, 3),
                most_correlated_peer=corr_peer,
                rejection_or_adjustment_note=(
                    f"[REJECTED - Portfolio Heat Full] ความเสี่ยงเปิดรวมของพอร์ตอยู่ที่ {current_heat_pct*100:.2f}% "
                    f"ชนเพดานสูงสุด {self.cfg.max_portfolio_heat_pct*100:.2f}% แล้ว"
                )
            )

        # ใช้ความเสี่ยงต่อไม้ไม่เกินโควตา Portfolio Heat ที่เหลืออยู่
        effective_risk_pct = min(self.cfg.risk_per_trade_pct, remaining_heat_pct)

        # หากค่า Correlation เริ่มสูง (เช่น 0.50 - 0.65) ให้ลดขนาดความเสี่ยงลง 30% (Correlation Scaling)
        adjustment_notes = []
        if max_corr >= 0.50:
            effective_risk_pct *= 0.70
            adjustment_notes.append(f"ลดขนาดไม้ 30% เนื่องจาก Correlation ปานกลาง ({max_corr:.2f} กับ {corr_peer})")

        # -----------------------------------------------------------------
        # ขั้นตอนที่ 3: คำนวณขนาดไม้ตามความผันผวน ATR (Volatility-Adjusted Sizing)
        # -----------------------------------------------------------------
        stop_distance = self.cfg.atr_stop_multiplier * current_atr
        initial_stop_price = entry_price - stop_distance
        risk_budget_thb = total_equity * effective_risk_pct

        raw_shares_by_risk = risk_budget_thb / stop_distance

        # -----------------------------------------------------------------
        # ขั้นตอนที่ 4: คุมเพดานมูลค่าต่อตัว (Single Position Cap), เพดาน Sector, และเงินสดคงเหลือ
        # -----------------------------------------------------------------
        max_notional_single = total_equity * self.cfg.max_position_notional_pct

        current_sector_value = sum(
            pos.market_value for pos in current_positions.values() if pos.sector == candidate_sector
        )
        remaining_sector_notional = max(
            0.0, (total_equity * self.cfg.max_sector_notional_pct) - current_sector_value
        )

        if remaining_sector_notional < (entry_price * self.cfg.lot_size):
            return AllocationDecision(
                approved=False,
                symbol=candidate_symbol,
                recommended_shares=0,
                position_notional=0.0,
                initial_stop_price=0.0,
                trade_risk_amount=0.0,
                trade_risk_pct_of_equity=0.0,
                max_corr_with_existing=round(max_corr, 3),
                most_correlated_peer=corr_peer,
                rejection_or_adjustment_note=(
                    f"[REJECTED - Sector Cap] กลุ่มอุตสาหกรรม '{candidate_sector}' มีสัดส่วนเต็มเพดาน "
                    f"{self.cfg.max_sector_notional_pct*100:.0f}% ของพอร์ตแล้ว"
                )
            )

        max_allowed_notional = min(max_notional_single, remaining_sector_notional, available_cash)
        max_shares_by_notional = max_allowed_notional / entry_price

        final_raw_shares = min(raw_shares_by_risk, max_shares_by_notional)
        # ปัดลงเป็นจำนวนเต็มของ Board Lot (เช่น ทีละ 100 หุ้น)
        recommended_shares = int(final_raw_shares // self.cfg.lot_size) * self.cfg.lot_size

        if recommended_shares <= 0:
            return AllocationDecision(
                approved=False,
                symbol=candidate_symbol,
                recommended_shares=0,
                position_notional=0.0,
                initial_stop_price=round(initial_stop_price, 4),
                trade_risk_amount=0.0,
                trade_risk_pct_of_equity=0.0,
                max_corr_with_existing=round(max_corr, 3),
                most_correlated_peer=corr_peer,
                rejection_or_adjustment_note="[REJECTED - Insufficient Size] ขนาดไม้หลังหักข้อจำกัดน้อยกว่า 1 Board Lot"
            )

        actual_notional = recommended_shares * entry_price
        actual_risk_thb = recommended_shares * stop_distance
        actual_risk_pct = (actual_risk_thb / total_equity) * 100.0

        if not adjustment_notes:
            adjustment_notes.append("อนุมัติขนาดไม้เต็มโควตาตามมาตรฐาน ATR Volatility Parity")

        return AllocationDecision(
            approved=True,
            symbol=candidate_symbol,
            recommended_shares=recommended_shares,
            position_notional=round(actual_notional, 2),
            initial_stop_price=round(initial_stop_price, 4),
            trade_risk_amount=round(actual_risk_thb, 2),
            trade_risk_pct_of_equity=round(actual_risk_pct, 3),
            max_corr_with_existing=round(max_corr, 3),
            most_correlated_peer=corr_peer,
            rejection_or_adjustment_note="; ".join(adjustment_notes)
        )


# =====================================================================
# ตัวอย่างการจำลองสถานการณ์จริงของโต๊ะ Risk Management
# =====================================================================
if __name__ == "__main__":
    np.random.seed(99)
    n_days = 80
    base_factor = np.random.normal(0.0005, 0.015, n_days)

    # สร้างข้อมูลผลตอบแทนรายวันของหุ้น 4 ตัว:
    # TECH_A และ TECH_B วิ่งตามกันแทบจะ 100% (Correlation สูงมาก)
    # HEALTH_C และ ENERGY_D วิ่งอิสระจากกลุ่มเทคฯ
    returns_data = pd.DataFrame({
        "TECH_A": base_factor + np.random.normal(0, 0.004, n_days),
        "TECH_B": base_factor * 0.95 + np.random.normal(0, 0.004, n_days),
        "HEALTH_C": np.random.normal(0.0006, 0.011, n_days),
        "ENERGY_D": np.random.normal(0.0004, 0.025, n_days),
    })

    risk_engine = PortfolioRiskEngine()

    # สมมติพอร์ตมีมูลค่า 2,000,000 บาท และปัจจุบันถือหุ้น TECH_A อยู่ในพอร์ตแล้ว 1 ตัว
    portfolio_equity = 2_000_000.0
    cash_balance = 1_650_000.0
    active_positions = {
        "TECH_A": ActivePortfolioPosition(
            symbol="TECH_A",
            sector="Technology",
            shares=3500,
            entry_price=100.0,
            current_price=102.0,
            active_stop_loss=95.0
        )
    }

    print("=== ทดสอบที่ 1: บอทส่งสัญญาณซื้อหุ้น TECH_B (ซึ่งวิ่งตาม TECH_A อย่างใกล้ชิด) ===")
    res1 = risk_engine.evaluate_and_size_order(
        candidate_symbol="TECH_B",
        candidate_sector="Technology",
        entry_price=50.0,
        current_atr=1.6,
        total_equity=portfolio_equity,
        available_cash=cash_balance,
        current_positions=active_positions,
        historical_returns_df=returns_data
    )
    print(f"  Approved: {res1.approved} | Shares: {res1.recommended_shares}")
    print(f"  เหตุผล:   {res1.rejection_or_adjustment_note}\n")

    print("=== ทดสอบที่ 2: บอทส่งสัญญาณซื้อหุ้น HEALTH_C (ความผันผวนต่ำ ATR = 0.80 บาท) ===")
    res2 = risk_engine.evaluate_and_size_order(
        candidate_symbol="HEALTH_C",
        candidate_sector="Healthcare",
        entry_price=40.0,
        current_atr=0.80,
        total_equity=portfolio_equity,
        available_cash=cash_balance,
        current_positions=active_positions,
        historical_returns_df=returns_data
    )
    print(f"  Approved: {res2.approved} | Shares: {res2.recommended_shares:,} หุ้น (มูลค่า {res2.position_notional:,.0f} บาท)")
    print(f"  Stop Loss: {res2.initial_stop_price:.2f} บาท | ความเสี่ยงจริง: {res2.trade_risk_amount:,.0f} บาท ({res2.trade_risk_pct_of_equity}% ของพอร์ต)")
    print(f"  เหตุผล:   {res2.rejection_or_adjustment_note}\n")

    print("=== ทดสอบที่ 3: บอทส่งสัญญาณซื้อหุ้น ENERGY_D (ความผันผวนสูงมาก ATR = 3.20 บาท) ===")
    res3 = risk_engine.evaluate_and_size_order(
        candidate_symbol="ENERGY_D",
        candidate_sector="Energy",
        entry_price=40.0,
        current_atr=3.20,
        total_equity=portfolio_equity,
        available_cash=cash_balance,
        current_positions=active_positions,
        historical_returns_df=returns_data
    )
    print(f"  Approved: {res3.approved} | Shares: {res3.recommended_shares:,} หุ้น (มูลค่า {res3.position_notional:,.0f} บาท)")
    print(f"  Stop Loss: {res3.initial_stop_price:.2f} บาท | ความเสี่ยงจริง: {res3.trade_risk_amount:,.0f} บาท ({res3.trade_risk_pct_of_equity}% ของพอร์ต)")
    print(f"  เหตุผล:   {res3.rejection_or_adjustment_note}")
