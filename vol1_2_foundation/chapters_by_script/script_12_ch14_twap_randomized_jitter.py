import random
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple


@dataclass
class OrderBookSnapshot:
    """ข้อมูลกระดานเสนอซื้อ-เสนอขาย (Best Bid / Best Ask) ณ วินาทีที่จะยิงคำสั่ง"""
    symbol: str
    best_bid_price: float
    best_bid_vol: int
    best_ask_price: float
    best_ask_vol: int
    tick_size: float = 0.05  # ขนาดช่องราคา (Tick Size) ของหุ้นตัวนั้น

    @property
    def spread_ticks(self) -> float:
        """จำนวนช่องราคาที่ห่างกันระหว่าง Bid กับ Ask"""
        if self.tick_size <= 0:
            return 1.0
        return round((self.best_ask_price - self.best_bid_price) / self.tick_size, 2)

    @property
    def spread_pct(self) -> float:
        """ความกว้างของ Spread คิดเป็นเปอร์เซ็นต์"""
        mid = 0.5 * (self.best_bid_price + self.best_ask_price)
        return ((self.best_ask_price - self.best_bid_price) / mid) if mid > 0 else 0.0

    @property
    def order_book_imbalance(self) -> float:
        """
        Order Book Imbalance (OBI) มีค่าตั้งแต่ -1.0 (แรงขายกดทับ) ถึง +1.0 (แรงซื้อหนุนแน่น)
        """
        total_vol = self.best_bid_vol + self.best_ask_vol
        if total_vol <= 0:
            return 0.0
        return (self.best_bid_vol - self.best_ask_vol) / float(total_vol)

    @property
    def micro_price(self) -> float:
        """ราคายุติธรรมจุลภาคถ่วงน้ำหนักด้วยโวลุ่มฝั่งตรงข้าม (Volume-Weighted Micro-Price)"""
        total_vol = self.best_bid_vol + self.best_ask_vol
        if total_vol <= 0:
            return 0.5 * (self.best_bid_price + self.best_ask_price)
        return (
            (self.best_bid_vol * self.best_ask_price)
            + (self.best_ask_vol * self.best_bid_price)
        ) / float(total_vol)


@dataclass
class ChildOrderSlice:
    """แผนการยิงคำสั่งย่อยแต่ละไม้ (Child Order) ที่ผ่านการซอยและใส่ Jitter แล้ว"""
    slice_index: int
    target_delay_seconds: float
    base_quantity: int
    vwap_weight: float


@dataclass
class ExecutionInstruction:
    """คำสั่งซื้อขายสุทธิที่พร้อมส่งเข้าสู่ Broker API"""
    symbol: str
    side: str                  # 'BUY' หรือ 'SELL'
    order_type: str            # 'LIMIT' (แนะนำเสมอเพื่อคุมราคา)
    limit_price: float         # ราคาที่คำนวณมาอย่างแม่นยำตามสภาพคล่องและ VWAP
    quantity: int              # จำนวนหุ้นที่ปัด Board Lot (100 หุ้น) เรียบร้อยแล้ว
    urgency_mode: str          # 'VWAP_SNIPER_PULLBACK', 'PASSIVE_QUEUE', 'AGGRESSIVE_CROSS', 'HOLD_SPREAD_GUARD'
    intraday_vwap: float       # ค่า 5m VWAP ณ ขณะนั้น
    vwap_zscore: float         # ระยะห่างของราคาปัจจุบันเทียบกับ VWAP (หน่วยเป็น SD)
    obi: float                 # ค่า Order Book Imbalance ณ ขณะนั้น
    reason: str                # คำอธิบายเหตุผลของคำสั่งเพื่อบันทึกใน Audit Log


class SmartTWAPVWAPExecutor:
    """
    บอทส่งคำสั่งซื้อขายอัจฉริยะ (Smart TWAP & 5m Intraday VWAP Sniper Executor)
    ออกแบบมาเพื่อ:
      1. ซ่อนรอยเท้าคำสั่งด้วย TWAP / VWAP Volume Profile Slicing พร้อมสุ่ม Jitter
      2. ดักจังหวะย่อตัวใต้เส้น 5m Intraday VWAP เพื่อให้ได้ต้นทุนถูกกว่าค่าเฉลี่ยตลาด
      3. อ่าน Order Book Imbalance & Micro-Price เพื่อเลือกวาง Bid หรือเคาะ Offer อย่างฉลาด
      4. ปัดจำนวนหุ้นให้ลงตัวกับ Board Lot (100 หุ้น) และป้องกันการถ่าง Spread
    """

    def __init__(
        self,
        board_lot: int = 100,
        max_spread_ticks: float = 3.0,
        max_participation_rate: float = 0.05,  # ไม่กินโวลุ่มเกิน 5% ของแท่ง 5 นาที
        time_jitter_pct: float = 0.25,         # สุ่มแกว่งเวลาส่งคำสั่ง +/- 25%
        size_jitter_pct: float = 0.20,         # สุ่มแกว่งขนาดไม้ย่อย +/- 20%
        random_seed: Optional[int] = None,
    ):
        self.board_lot = max(1, int(board_lot))
        self.max_spread_ticks = max_spread_ticks
        self.max_participation_rate = max_participation_rate
        self.time_jitter_pct = np.clip(time_jitter_pct, 0.0, 0.45)
        self.size_jitter_pct = np.clip(size_jitter_pct, 0.0, 0.40)
        self._rng = random.Random(random_seed)

    # ------------------------------------------------------------------
    # ส่วนที่ 1: คำนวณ 5m Intraday VWAP และกรอบ Standard Deviation Bands
    # ------------------------------------------------------------------
    @staticmethod
    def compute_intraday_5m_vwap(df_5m: pd.DataFrame) -> pd.DataFrame:
        """
        คำนวณเส้น Intraday VWAP และกรอบส่วนเบี่ยงเบนมาตรฐาน (+/- 1 SD, +/- 2 SD)
        จากข้อมูลแท่งเทียน 5 นาทีของวันปัจจุบัน (columns: ['high', 'low', 'close', 'volume'])
        """
        df = df_5m.copy()
        typical_price = (df["high"] + df["low"] + df["close"]) / 3.0
        vol = df["volume"].clip(lower=0.0)

        cum_pv = (typical_price * vol).cumsum()
        cum_vol = vol.cumsum().replace(0, np.nan)
        vwap = (cum_pv / cum_vol).ffill().fillna(df["close"])

        # คำนวณ Volume-Weighted Variance และ Standard Deviation รอบเส้น VWAP
        cum_p2v = ((typical_price ** 2) * vol).cumsum()
        vwap_var = ((cum_p2v / cum_vol) - (vwap ** 2)).clip(lower=1e-8)
        vwap_std = np.sqrt(vwap_var)

        df["typical_price"] = typical_price
        df["vwap"] = vwap
        df["vwap_std"] = vwap_std
        df["vwap_upper_1sd"] = vwap + 1.0 * vwap_std
        df["vwap_lower_1sd"] = vwap - 1.0 * vwap_std
        df["vwap_upper_2sd"] = vwap + 2.0 * vwap_std
        df["vwap_lower_2sd"] = vwap - 2.0 * vwap_std
        df["vwap_zscore"] = ((df["close"] - vwap) / vwap_std.replace(0, np.nan)).fillna(0.0)

        return df

    # ------------------------------------------------------------------
    # ส่วนที่ 2: การปัดเศษหุ้นตามกฎ Board Lot (100 หุ้น) และ SET Tick Size (8 มาตรการใหม่)
    # ------------------------------------------------------------------
    @staticmethod
    def get_set_tick_size(price: float) -> float:
        """
        คืนค่าขนาดช่องราคา (Tick Size) ตามเกณฑ์ 8 มาตรการการซื้อขายของตลาดหลักทรัพย์ฯ (SET 795-eight-trading-measures)
        - ปรับลด Tick Size สำหรับหุ้นราคา 5.00 - <50.00 บาท (0.02 / 0.05 / 0.10 บาท)
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

    def round_to_board_lot(self, raw_qty: float) -> int:
        """ปัดจำนวนหุ้นลงให้เป็นทวีคูณของ Board Lot (เช่น 100 หุ้น)"""
        if raw_qty < self.board_lot:
            return 0
        return int(raw_qty // self.board_lot) * self.board_lot

    @staticmethod
    def round_to_tick(price: float, tick_size: Optional[float] = None, direction: str = "NEAREST") -> float:
        """ปัดทศนิยมราคาให้ตรงตามช่อง Tick Size ของตลาดหลักทรัพย์"""
        effective_tick = tick_size if (tick_size is not None and tick_size > 0) else SmartTWAPVWAPExecutor.get_set_tick_size(price)
        steps = price / effective_tick
        if direction == "DOWN":
            rounded_steps = np.floor(steps + 1e-9)
        elif direction == "UP":
            rounded_steps = np.ceil(steps - 1e-9)
        else:
            rounded_steps = np.round(steps)
        return round(float(rounded_steps * effective_tick), 4)

    # ------------------------------------------------------------------
    # ส่วนที่ 3: สร้างตารางซอยไม้ TWAP / VWAP พร้อมสุ่ม Jitter ป้องกัน HFT ดักจับ
    # ------------------------------------------------------------------
    def generate_execution_schedule(
        self,
        total_quantity: int,
        duration_minutes: int = 60,
        num_slices: int = 6,
        mode: str = "VWAP_SMILE",
        custom_volume_profile: Optional[List[float]] = None,
    ) -> List[ChildOrderSlice]:
        """
        แตกคำสั่งใหญ่ (Parent Order) ออกเป็นไม้ย่อย (Child Orders)
        พร้อมใส่ Randomized Time Jitter และ Size Perturbation โดยที่ผลรวมหุ้นสุดท้ายครบตรงเป๊ะ
        """
        total_lot_qty = self.round_to_board_lot(total_quantity)
        if total_lot_qty <= 0 or num_slices <= 0:
            return []

        # ถ้ายอดซื้อน้อยมาก (เช่น แค่ 100-200 หุ้น) ไม่ต้องซอยไม้ให้เปลืองเวลา
        max_possible_slices = max(1, total_lot_qty // self.board_lot)
        actual_slices = min(num_slices, max_possible_slices)

        # 1. กำหนดน้ำหนักโปรไฟล์ปริมาณการซื้อขาย (Volume Profile Weights)
        if custom_volume_profile and len(custom_volume_profile) == actual_slices:
            raw_weights = np.array(custom_volume_profile, dtype=float)
        elif mode.upper() == "VWAP_SMILE" and actual_slices >= 3:
            # สร้างเส้นโค้ง U-Shape (Volume Smile): หนักช่วงต้นและช่วงท้าย เบาช่วงกลาง
            x = np.linspace(-1.0, 1.0, actual_slices)
            raw_weights = 1.0 + 0.65 * (x ** 2)
        else:
            # โหมด TWAP มาตรฐาน: น้ำหนักเริ่มต้นเท่ากันทุกรอบ
            raw_weights = np.ones(actual_slices, dtype=float)

        # 2. ใส่ Size Perturbation (สุ่มบิดขนาดไม้ +/- size_jitter_pct เพื่อซ่อนรอยเท้า)
        perturbed_weights = np.array([
            w * (1.0 + self._rng.uniform(-self.size_jitter_pct, self.size_jitter_pct))
            for w in raw_weights
        ])
        perturbed_weights = np.clip(perturbed_weights, 0.1, None)
        norm_weights = perturbed_weights / np.sum(perturbed_weights)

        # 3. แปลงน้ำหนักเป็นจำนวนหุ้นที่ลงตัวกับ Board Lot (100 หุ้น) และรวมได้เท่ากับ total_lot_qty เป๊ะ
        raw_slice_qtys = [
            self.round_to_board_lot(total_lot_qty * w) for w in norm_weights
        ]
        # เกลี่ยเศษหุ้นที่เหลือ (Remainder Lots) เข้าไปตามลำดับน้ำหนักมากสุด
        allocated = sum(raw_slice_qtys)
        remainder_lots = (total_lot_qty - allocated) // self.board_lot
        order_by_weight = np.argsort(-norm_weights)
        for idx in range(int(remainder_lots)):
            target_i = int(order_by_weight[idx % actual_slices])
            raw_slice_qtys[target_i] += self.board_lot

        # 4. คำนวณเวลาส่งคำสั่งแต่ละรอบพร้อมสุ่ม Time Jitter
        base_interval_sec = (duration_minutes * 60.0) / float(actual_slices)
        schedule: List[ChildOrderSlice] = []
        cumulative_sec = 0.0

        for i in range(actual_slices):
            if raw_slice_qtys[i] <= 0:
                continue
            jitter_factor = 1.0 + self._rng.uniform(-self.time_jitter_pct, self.time_jitter_pct)
            step_sec = max(5.0, base_interval_sec * jitter_factor)
            if i > 0:
                cumulative_sec += step_sec

            schedule.append(
                ChildOrderSlice(
                    slice_index=len(schedule) + 1,
                    target_delay_seconds=round(cumulative_sec, 1),
                    base_quantity=int(raw_slice_qtys[i]),
                    vwap_weight=round(float(norm_weights[i]), 4),
                )
            )

        return schedule

    # ------------------------------------------------------------------
    # ส่วนที่ 4: สมองกลตัดสินใจยิงไม้ย่อย (5m VWAP Sniper + Order Book Imbalance)
    # ------------------------------------------------------------------
    def decide_child_order(
        self,
        side: str,
        planned_slice_qty: int,
        remaining_parent_qty: int,
        df_5m_intraday: pd.DataFrame,
        order_book: OrderBookSnapshot,
    ) -> ExecutionInstruction:
        """
        ตัดสินใจราคา Limit Price และปรับขนาดไม้ย่อยแบบเรียลไทม์สำหรับรอบการยิงปัจจุบัน
        โดยผสานข้อมูล 5m Intraday VWAP เข้ากับโครงสร้าง Order Book (Bid/Offer/OBI)
        """
        side = side.upper()
        vwap_df = self.compute_intraday_5m_vwap(df_5m_intraday)
        latest_bar = vwap_df.iloc[-1]

        intraday_vwap = float(latest_bar["vwap"])
        vwap_z = float(latest_bar["vwap_zscore"])
        obi = float(order_book.order_book_imbalance)
        tick = order_book.tick_size

        # 1. ด่านป้องกันแรก: Spread Guard (ถ้า Bid-Ask ถ่างกว้างผิดปกติ ห้ามโยนคำสั่งไล่ราคา)
        if order_book.spread_ticks > self.max_spread_ticks:
            passive_price = (
                order_book.best_bid_price if side == "BUY" else order_book.best_ask_price
            )
            return ExecutionInstruction(
                symbol=order_book.symbol,
                side=side,
                order_type="LIMIT",
                limit_price=passive_price,
                quantity=0,  # ชะลอการยิงในวินาทีที่กระดานกลวง
                urgency_mode="HOLD_SPREAD_GUARD",
                intraday_vwap=round(intraday_vwap, 4),
                vwap_zscore=round(vwap_z, 3),
                obi=round(obi, 3),
                reason=(
                    f"Spread ถ่างกว้าง {order_book.spread_ticks} ช่องราคา "
                    f"(เกินเพดาน {self.max_spread_ticks} ช่อง) ชะลอการส่งคำสั่งเพื่อป้องกัน Slippage"
                ),
            )

        # 2. ปรับขนาดไม้ตามตำแหน่งราคาเทียบกับเส้น 5m Intraday VWAP (Sniper Dynamic Sizing)
        adjusted_qty = float(planned_slice_qty)

        if side == "BUY":
            if vwap_z <= -0.5:
                # ราคาย่อตัวลงมาต่ำกว่าเส้น Intraday VWAP (Discount Zone!)
                # ขยายขนาดไม้ย่อยขึ้น 35% เพื่อเก็บของถูกกว่าค่าเฉลี่ยตลาด
                adjusted_qty *= 1.35
                urgency = "VWAP_SNIPER_PULLBACK"
            elif vwap_z >= 1.2:
                # ราคาวิ่งฉีกขึ้นไปแพงกว่า VWAP เกิน +1.2 SD
                # ลดขนาดไม้ย่อยลงครึ่งหนึ่ง ไม่ไล่ราคาบนยอดคลื่นสั้น
                adjusted_qty *= 0.50
                urgency = "PASSIVE_QUEUE"
            else:
                urgency = "PASSIVE_QUEUE" if obi < 0.35 else "AGGRESSIVE_CROSS"
        else:  # กรณีฝั่งขาย (SELL)
            if vwap_z >= 0.5:
                # ราคาดีดขึ้นเหนือ VWAP (Premium Zone!) เร่งการรินขายได้ราคาดี
                adjusted_qty *= 1.35
                urgency = "VWAP_SNIPER_PULLBACK"
            elif vwap_z <= -1.2:
                adjusted_qty *= 0.50
                urgency = "PASSIVE_QUEUE"
            else:
                urgency = "PASSIVE_QUEUE" if obi > -0.35 else "AGGRESSIVE_CROSS"

        # 3. จำกัดขนาดไม้ไม่ให้เกินเพดานสภาพคล่องของฝั่งตรงข้ามในกระดาน เพื่อไม่ให้กวาดช่องราคา
        opposite_depth = order_book.best_ask_vol if side == "BUY" else order_book.best_bid_vol
        liquidity_cap_qty = max(self.board_lot, int(opposite_depth * 0.25))
        final_qty = self.round_to_board_lot(
            min(adjusted_qty, float(remaining_parent_qty), float(liquidity_cap_qty))
        )
        if final_qty == 0 and remaining_parent_qty >= self.board_lot:
            final_qty = self.board_lot

        # 4. กำหนดราคา Limit Price ที่คมกริบตาม Order Book Imbalance (OBI) และ VWAP
        if side == "BUY":
            if urgency == "VWAP_SNIPER_PULLBACK" and obi >= 0.15:
                # ราคาย่อลงมาต่ำกว่า VWAP แล้ว และแรงซื้อในกระดานเริ่มหนุนกลับ -> เคาะเก็บที่ Ask ได้เลย
                limit_price = order_book.best_ask_price
                reason = (
                    f"Sniper Pullback: ราคาต่ำกว่า 5m VWAP ({vwap_z:.2f} SD) "
                    f"และ OBI พลิกเป็นบวก ({obi:+.2f}) เคาะเก็บที่ Offer ทันที"
                )
            elif obi >= 0.45 and vwap_z <= 0.8:
                # Bid หนุนแน่นมาก Offer กำลังจะแตก -> ชิงเก็บที่ Offer ก่อนเปลี่ยนช่อง
                limit_price = order_book.best_ask_price
                urgency = "AGGRESSIVE_CROSS"
                reason = f"OBI หนุนฝั่งซื้อรุนแรง ({obi:+.2f}) ชิงเก็บที่ Best Ask ก่อนราคาขยับหนี"
            else:
                # ตั้งรอรับที่ Best Bid เพื่อประหยัด Bid-Ask Spread
                limit_price = order_book.best_bid_price
                reason = (
                    f"ตั้งรับ Passive ที่ Best Bid เพื่อเก็บ Spread "
                    f"(VWAP Z={vwap_z:+.2f}, OBI={obi:+.2f})"
                )
        else:  # SELL
            if urgency == "VWAP_SNIPER_PULLBACK" and obi <= -0.15:
                limit_price = order_book.best_bid_price
                reason = (
                    f"Sniper Premium Sell: ราคาสูงกว่า 5m VWAP ({vwap_z:+.2f} SD) "
                    f"รินขายที่ Best Bid ได้ราคาดีกว่าค่าเฉลี่ยตลาด"
                )
            elif obi <= -0.45 and vwap_z >= -0.8:
                limit_price = order_book.best_bid_price
                urgency = "AGGRESSIVE_CROSS"
                reason = f"แรงขายกดดันกระดาน ({obi:+.2f}) ชิงระบายของที่ Best Bid ทันที"
            else:
                limit_price = order_book.best_ask_price
                reason = (
                    f"ตั้งวางขาย Passive ที่ Best Ask เพื่อได้ราคาดีขึ้น 1 ช่อง "
                    f"(VWAP Z={vwap_z:+.2f}, OBI={obi:+.2f})"
                )

        limit_price = self.round_to_tick(limit_price, tick)

        return ExecutionInstruction(
            symbol=order_book.symbol,
            side=side,
            order_type="LIMIT",
            limit_price=limit_price,
            quantity=final_qty,
            urgency_mode=urgency,
            intraday_vwap=round(intraday_vwap, 4),
            vwap_zscore=round(vwap_z, 3),
            obi=round(obi, 3),
            reason=reason,
        )


if __name__ == "__main__":
    executor = SmartTWAPVWAPExecutor(random_seed=42)
    schedule = executor.generate_execution_schedule(total_quantity=2400, duration_minutes=30, num_slices=4)
    print("=== ตารางซอยไม้ส่งคำสั่งซื้อขายอัจฉริยะ (SmartTWAPVWAPExecutor + SET 8 Measures Tick Size) ===")
    for s in schedule:
        print(f"  - ไม้ที่ {s.slice_index}: Delay={s.target_delay_seconds:.1f}s | จำนวน={s.base_quantity} หุ้น (Weight={s.vwap_weight:.2f})")
    for sample_p in [4.90, 7.50, 18.20, 32.00, 75.00]:
        print(f"  - ราคาหุ้น {sample_p:>6.2f} บาท -> SET Tick Size ใหม่ = {executor.get_set_tick_size(sample_p):.2f} บาท")
