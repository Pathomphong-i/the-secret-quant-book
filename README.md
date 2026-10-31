# โรบอทเทรด ที่โบรกเกอร์ไม่อยากให้คุณเขียน — เปิดแก่นความคิดของ Quant Trader ยุคใหม่

**ผู้เขียน:** ปฐมพงษ์ พิพัฒน์สุริยวงศ์

> **คำเตือน:** เนื้อหาและโค้ดในคลังซอร์สโค้ดนี้จัดทำขึ้นเพื่อการศึกษาและเป็นความคิดเห็นส่วนตัวของผู้เขียนเท่านั้น มิใช่การแนะนำการลงทุน ผู้ลงทุนโปรดศึกษาข้อมูลและความเสี่ยงด้วยตนเอง

---

## 📁 โครงสร้างโฟลเดอร์ (Folder Structure)

คลังซอร์สโค้ดนี้จัดแยกเป็นโฟลเดอร์อย่างเป็นระเบียบ เพื่อให้ผู้อ่านสามารถดาวน์โหลดและรันทดสอบตามเนื้อหาในแต่ละบทได้ทันที:

```text
the-secret-quant-book/
├── full_bot/
│   └── the_secret_quant_full_bot.py           # ระบบบอทเทรดฉบับสมบูรณ์ครบทั้ง 14 บท (รันได้ทันที)
├── data/
│   └── sample_thai_stocks_ohlcv.csv           # ข้อมูลราคาหุ้นจำลองย้อนหลัง 500 วันทำการ (3,500 แถว) สำหรับทำ Backtest
├── chapters_combined/                         # โค้ดรวมตามกลุ่มบทเรียน (6 ไฟล์หลัก)
│   ├── 01_ch01_to_ch04_four_pillars_bot.py
│   ├── 02_ch05_to_ch06_pit_backtest_and_wfe.py
│   ├── 03_ch07_to_ch09_signals_context_and_risk.py
│   ├── 04_ch10_to_ch12_regime_ensemble_and_hrp.py
│   ├── 05_ch13_to_ch14_twap_vwap_set8_executor.py
│   └── 06_epilogue_health_and_two_bucket.py
├── chapters_by_script/                        # โค้ดแยกย่อยรายบท (Script 01 – 13)
│   ├── script_01_ch04_sqlite_parquet_store.py
│   ├── script_02_ch04_data_hygiene_split_adjust.py
│   ├── script_03_ch05_point_in_time_backtest.py
│   ├── script_04_ch06_walk_forward_validator.py
│   ├── script_05_ch07_multi_layer_signal_filter.py
│   ├── script_06_ch08_position_context_manager.py
│   ├── script_07_ch09_portfolio_risk_engine.py
│   ├── script_08_ch10_market_regime_detector.py
│   ├── script_09_ch11_three_agent_ensemble.py
│   ├── script_10_ch12_hrp_portfolio_allocator.py
│   ├── script_11_ch13_orderbook_microstructure.py
│   ├── script_12_ch14_twap_randomized_jitter.py
│   └── script_13_ch14_intraday_5m_vwap_sniper.py
└── requirements.txt                           # รายการไลบรารีมาตรฐานที่ใช้
```

---

## 🚀 วิธีติดตั้งและรันโค้ดสำหรับมือใหม่ (Quick Start)

```bash
# 1. โคลนคลังซอร์สโค้ดลงเครื่องคอมพิวเตอร์
git clone https://github.com/Pathomphong-i/the-secret-quant-book.git
cd the-secret-quant-book

# 2. สร้าง Virtual Environment และติดตั้งไลบรารี
python3 -m venv .venv
source .venv/bin/activate   # (สำหรับ Windows ใช้: .venv\Scripts\activate)
pip install -r requirements.txt

# 3. รันบอทตัวเต็มพร้อมข้อมูล Backtest ในโฟลเดอร์ data/ ได้ทันที
python3 full_bot/the_secret_quant_full_bot.py --csv data/sample_thai_stocks_ohlcv.csv

# 4. หรือรันโค้ดแยกตามบทในโฟลเดอร์ chapters_combined/ หรือ chapters_by_script/
python3 chapters_combined/01_ch01_to_ch04_four_pillars_bot.py
python3 chapters_by_script/script_03_ch05_point_in_time_backtest.py
```

---

## 📊 ผลลัพธ์การรันทดสอบบอทตัวเต็ม (`the_secret_quant_full_bot.py` + `sample_thai_stocks_ohlcv.csv`)

เมื่อรันคำสั่ง `python3 full_bot/the_secret_quant_full_bot.py --csv data/sample_thai_stocks_ohlcv.csv` ระบบจะจำลองการเทรดแบบ **Point-in-Time Event-Driven Backtest** (คำนวณสัญญาณ ณ สิ้นวัน `T-1` และส่งคำสั่งซื้อขายที่ราคาเปิดวัน `T` พร้อมหักค่าธรรมเนียม `0.157%` และ `Slippage`) บนข้อมูลจำลอง 500 วันทำการ (6 หลักทรัพย์ตัวแทนกลุ่มอุตสาหกรรม + ดัชนีตลาด `SET_INDEX`):

### สรุปตัวชี้วัดหลักจากการทดสอบ (Key Performance Metrics)

| ตัวชี้วัด (Metric) | ผลลัพธ์จากการรันทดสอบ | คำอธิบาย |
| :--- | :---: | :--- |
| **เงินทุนตั้งต้น (`Initial Capital`)** | `1,000,000.00 บาท` | พอร์ตเริ่มต้นสำหรับการทดสอบระบบ |
| **พอร์ตเทรดปลายงวด (`Trading Equity`)** | `1,144,359.36 บาท` | มูลค่าพอร์ตส่วนเก็งกำไรเชิงระบบ (Bucket #1) |
| **ถังเงินออมปลอดภัย (`Safe Bucket Skim`)** | `7,803.58 บาท` | กำไรที่ถูกดูดออกไปล็อกเก็บในถังปลอดภัยอัตโนมัติ (Bucket #2) |
| **ความมั่งคั่งสุทธิรวม (`Total Wealth`)** | **`1,152,162.94 บาท` (`+15.22%`)** | มูลค่ารวมสุทธิหลังหักค่าคอมมิชชัน VAT และ Slippage ครบทุกไม้ |
| **ผลตอบแทนทบต้นต่อปี (`CAGR`)** | **`+8.45% ต่อปี`** | อัตราการเติบโตทบต้นต่อปี |
| **การย่อตัวสูงสุด (`Max Drawdown`)** | **`-4.22%`** | ควบคุม Drawdown ให้อยู่ต่ำกว่าเพดานความเสี่ยง `-5.0%` ด้วย `ATR Sizing` + `HRP` + `Cash Shield` |
| **Sharpe Ratio / Sortino Ratio** | **`1.98` / `3.21`** | ผลตอบแทนเทียบความผันผวนอยู่ในเกณฑ์เสถียรสูง |
| **อัตราชนะ (`Win Rate`) & `Profit Factor`** | **`56.86%` (51 ไม้) / `PF 1.62`** | ค่าคาดหวังสุทธิ (`Expectancy`) เฉลี่ย **`+1,324.44 บาท/ไม้`** |
| **Walk-Forward Efficiency (`WFE`)** | **`233.5%` (ผ่านเกณฑ์ `>= 50%`)** | ช่วงทดสอบนอกกลุ่มตัวอย่าง (`Out-of-Sample CAGR 12.00%`) ไม่เกิดอาการ Overfitting |

### ตัวอย่างผลลัพธ์บนหน้าจอ Terminal จริง (Full Terminal Output)

```text
============================================================================================
  โรบอทเทรด ที่โบรกเกอร์ไม่อยากให้คุณเขียน — เปิดแก่นความคิดของ Quant Trader ยุคใหม่ (CH 1 - CH 14)
============================================================================================
[1/6] โหลดข้อมูลราคาหุ้นย้อนหลังจากไฟล์: data/sample_thai_stocks_ohlcv.csv
      - จำนวนหุ้นที่ผ่านเกณฑ์ความสะอาด (Data Hygiene): 6 ตัว (STOCK_BANK.BK, STOCK_COMM.BK, STOCK_ENERG.BK, STOCK_HELTH.BK, STOCK_ICT.BK, STOCK_TRANS.BK)
      - ช่วงเวลาทดสอบ: 2023-01-03 ถึง 2024-12-02 (500 วันทำการ)

[2/6] ผลการจำแนกสภาวะตลาดรวม (Market Regime Detector - บทที่ 10):
      - BULL_TREND      : 298 วันทำการ ( 59.6%)
      - SIDEWAYS_QUIET  : 100 วันทำการ ( 20.0%)
      - CRISIS_PANIC    : 102 วันทำการ ( 20.4%)

[3/6] สัดส่วนพอร์ตไร้ความเสี่ยงกระจุกตัว (Hierarchical Risk Parity - บทที่ 12):
      - STOCK_HELTH.BK: 28.66%
      - STOCK_ICT.BK: 24.40%
      - STOCK_ENERG.BK: 16.93%
      - STOCK_COMM.BK: 12.58%
      - STOCK_BANK.BK: 10.48%
      - STOCK_TRANS.BK:  6.95%

[4/6] ผลทดสอบ Walk-Forward Validation (บทที่ 6):
      - In-Sample CAGR (60% แรก)     :   5.14% ต่อปี
      - Out-of-Sample CAGR (40% หลัง):  12.00% ต่อปี
      - Walk-Forward Efficiency (WFE):  233.5% -> [ผ่านเกณฑ์มาตรฐาน (Robust >= 50%)]

[5/6] สรุปผลการจำลองพอร์ตเต็มรูปแบบ (Point-in-Time Backtest & Two-Bucket System):
      - เงินทุนตั้งต้น (Initial Capital)       :   1,000,000.00 บาท
      - พอร์ตเทรดปลายงวด (Trading Equity)    :   1,144,359.36 บาท
      - ถังเงินออมปลอดภัย (Safe Bucket Skim) :       7,803.58 บาท
      - ความมั่งคั่งสุทธิรวม (Total Wealth)   :   1,152,162.94 บาท
      - ผลตอบแทนสุทธิรวม (Total Return)      :         15.22%
      - ผลตอบแทนทบต้นต่อปี (CAGR)            :          8.45%
      - การย่อตัวสูงสุด (Max Drawdown)       :         -4.22%
      - Sharpe Ratio / Sortino Ratio        :   1.98 / 3.21
      - จำนวนไม้ที่เทรดทั้งหมด (Total Trades) :             51 ไม้
      - อัตราชนะ (Win Rate)                 :         56.86%
      - Profit Factor                       :           1.62
      - ค่าคาดหวังต่อไม้ (Expectancy)        :       1,324.44 บาท/ไม้

      ตัวอย่างประวัติการเทรด 5 ไม้ล่าสุด (พร้อม Thesis Tag & Ratchet Stop):
      * STOCK_ENERG.BK [MEAN_REVERSION ] 2024-10-16 @  32.94 -> 2024-10-22 @  33.69 | PnL: +3,768.70 บาท (+0.51R) | MEAN_REVERT_TARGET (ราคาดีดกลับแตะค่าเฉลี่ย SMA 20 / RSI >= 65)
      * STOCK_COMM.BK [MEAN_REVERSION ] 2024-10-25 @  98.18 -> 2024-10-28 @  99.83 | PnL: +2,145.79 บาท (+0.39R) | MEAN_REVERT_TARGET (ราคาดีดกลับแตะค่าเฉลี่ย SMA 20 / RSI >= 65)
      * STOCK_ICT.BK [TREND_FOLLOWING] 2024-06-12 @ 200.15 -> 2024-11-01 @ 225.11 | PnL: +21,867.34 บาท (+2.14R) | TRAILING_STOP_HIT (PROFIT_RATCHETED (+3R))
      * STOCK_BANK.BK [MEAN_REVERSION ] 2024-10-14 @ 141.24 -> 2024-11-01 @ 133.18 | PnL: -9,344.77 บาท (-1.17R) | TRAILING_STOP_HIT (INITIAL)
      * STOCK_ICT.BK [MEAN_REVERSION ] 2024-11-01 @ 225.57 -> 2024-11-07 @ 233.34 | PnL: +6,345.55 บาท (+0.87R) | MEAN_REVERT_TARGET (ราคาดีดกลับแตะค่าเฉลี่ย SMA 20 / RSI >= 65)

[6/6] ตัวอย่างแผนส่งคำสั่งซื้ออัจฉริยะ (Smart TWAP & Micro-Price - บทที่ 13 & 14) สำหรับ STOCK_BANK.BK:
      - ราคาอ้างอิง: 138.83 บาท | Spread: 72.2 bps | OBI: +0.339 | Micro-Price: 138.669 บาท
      - ไม้ย่อยที่ 1 (+00m:46s): จำนวน  600 หุ้น @ Limit 139.00 บาท [JOIN_BEST_ASK]
      - ไม้ย่อยที่ 2 (+05m:34s): จำนวน  600 หุ้น @ Limit 139.00 บาท [JOIN_BEST_ASK]
      - ไม้ย่อยที่ 3 (+10m:36s): จำนวน  600 หุ้น @ Limit 139.00 บาท [JOIN_BEST_ASK]
      - ไม้ย่อยที่ 4 (+15m:44s): จำนวน  600 หุ้น @ Limit 139.00 บาท [JOIN_BEST_ASK]
========================================================================================
```
