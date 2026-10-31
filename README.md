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
