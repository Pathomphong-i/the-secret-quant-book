#!/usr/bin/env python3
"""
========================================================================================
The Secret Quant: 8-Volume Masterclass Series — Master End-to-End Pipeline Runner
ผู้เขียน: ปฐมพงษ์ พิพัฒน์สุริยวงศ์
========================================================================================
สคริปต์แม่แบบบูรณาการ (Master Glue Script) ที่เชื่อมโยงโค้ดจากหนังสือทั้ง 8 เล่มเข้าด้วยกัน:
  - เล่มที่ 3 (08_vol3_...): ดึงข้อมูล + ตรวจความสะอาด + ปรับฐานปันผล/แตกพาร์ (Data & Hygiene)
  - เล่มที่ 4 (09_vol4_...): คำนวณ ER, Hurst, Regime, VCP, KAMA, RVOL/CLV & Ensemble Alpha
  - เล่มที่ 7 (12_vol7_...): กรองข่าวด้วย Gemini LLM JSON, ตรวจงบการเงิน & เรดาร์มหภาค (Master AI Gate)
  - เล่มที่ 5 (10_vol5_...): จัดพอร์ต HRP, คำนวณขนาดไม้ ATR/Safe Kelly & ตรวจเพดาน Portfolio Heat <= 5%
  - เล่มที่ 6 (11_vol6_...): ตรวจกระดาน 5-Level OBI, Micro-Price, ซอยไม้ TWAP & กฎ SET 8 มาตรการใหม่
  - เล่มที่ 8 (13_vol8_...): บันทึกคำสั่งแบบ Idempotent SHA-256, คำนวณเกราะ TFEX Hedge & พอร์ตโกลบอล
========================================================================================
"""

from __future__ import annotations
import contextlib
import importlib.util
import io
import sys
from pathlib import Path
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent


FOLDER_MAP = {
    "08_vol3_data_engineering_and_backtest_lab.py": "vol3_data_backtest/run_vol3_suite.py",
    "09_vol4_alpha_and_technical_signal_engine.py": "vol4_alpha_signal/run_vol4_suite.py",
    "10_vol5_portfolio_management_and_risk_engine.py": "vol5_portfolio_risk/run_vol5_suite.py",
    "11_vol6_smart_execution_and_settrade_bridge.py": "vol6_smart_execution/run_vol6_suite.py",
    "12_vol7_multimodal_ai_and_gemini_client.py": "vol7_ai_llm_quant/run_vol7_suite.py",
    "13_vol8_cloud_ops_tfex_and_global_multi_asset.py": "vol8_cloud_multi_asset/run_vol8_suite.py",
}

def _load_mod(mod_name: str, filename: str):
    """โหลดโมดูลของแต่ละเล่มจากโฟลเดอร์แยกเล่ม (หรือไฟล์ระดับ Root) โดยปิดการแสดงผลรายบทชั่วคราว"""
    structured_rel = FOLDER_MAP.get(filename, filename)
    target_path = BASE_DIR / structured_rel if (BASE_DIR / structured_rel).exists() else BASE_DIR / filename
    spec = importlib.util.spec_from_file_location(mod_name, str(target_path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    with contextlib.redirect_stdout(io.StringIO()):
        spec.loader.exec_module(mod)
    return mod


def run_8vol_masterclass_pipeline() -> None:
    print("=" * 92)
    print("🚀 THE SECRET QUANT: 8-VOLUME MASTERCLASS — END-TO-END PIPELINE RUNNER (VOL 1 TO VOL 8)")
    print("=" * 92)

    v3 = _load_mod("vol3_data", "08_vol3_data_engineering_and_backtest_lab.py")
    v4 = _load_mod("vol4_signal", "09_vol4_alpha_and_technical_signal_engine.py")
    v5 = _load_mod("vol5_risk", "10_vol5_portfolio_management_and_risk_engine.py")
    v6 = _load_mod("vol6_exec", "11_vol6_smart_execution_and_settrade_bridge.py")
    v7 = _load_mod("vol7_ai", "12_vol7_multimodal_ai_and_gemini_client.py")
    v8 = _load_mod("vol8_cloud", "13_vol8_cloud_ops_tfex_and_global_multi_asset.py")

    # 1. [เล่มที่ 3] ดึงข้อมูลและทำความสะอาดผ่าน Sanity Filter (Data Engineering & Hygiene)
    raw_df, _, _ = v3.fetch_thai_stocks_and_corporate_actions(symbols=["BETA.BK"], period="6mo")
    clean_df, quarantine_df = v3.sanitize_ohlcv_frame(raw_df)
    print(
        f"[1/6 เล่มที่ 3 - Data & Hygiene] ดึงและคัดกรองข้อมูลสะอาดสำเร็จ: {len(clean_df)} แท่งเทียน "
        f"(tradable={int(clean_df['is_tradable'].sum())}, กักกัน={len(quarantine_df)})"
    )

    # 2. [เล่มที่ 4] คำนวณสภาวะตลาด (Softmax Regime) และรวมคะแนน Alpha Conviction
    regime_probs = v4.compute_regime_probabilities(breadth=0.68, atr_zscore=-0.30, index_er20=0.58)
    dominant_regime = str(regime_probs.idxmax())
    candidates_df = pd.DataFrame([
        {"symbol": "BETA", "trend_agent_score": 84.0, "pullback_agent_score": 72.0}
    ])
    alpha_df = v4.combine_multi_agent_alpha_score(candidates_df, regime_probs)
    alpha_score = float(alpha_df.loc[0, "final_alpha_score"])
    alpha_tier = str(alpha_df.loc[0, "conviction_tier"])
    print(
        f"[2/6 เล่มที่ 4 - Alpha Signal  ] โหมดตลาด={dominant_regime} (P={regime_probs[dominant_regime]:.3f}) "
        f"| Final Alpha={alpha_score:.2f} ({alpha_tier})"
    )

    # 3. [เล่มที่ 7] กรองข่าวด้วย LLM JSON + งบการเงิน + เรดาร์ความเสี่ยงมหภาค (Master AI Gate)
    raw_llm = v7.call_gemini_structured_json(
        system_prompt="Return strict quantitative news JSON.",
        user_text="BETA รายงานกำไรสุทธิเติบโตแข็งแกร่งและกระแสเงินสดจากการดำเนินงานสูงกว่าคาด",
    )
    news_sig = v7.parse_news_to_structured_signal(raw_llm)
    ai_gate = v7.run_multimodal_ai_quant_gate(
        ticker="BETA",
        base_hrp_weight=0.14,
        hygiene_passed=True,
        is_sell_on_fact_trap=False,
        systemic_heat_mult=1.0,
        sector_rrg_mult=1.15,
        effective_news_score=float(news_sig["effective_news_score"]),
    )
    print(
        f"[3/6 เล่มที่ 7 - Multi-Modal AI] สถานะ AI Gate={ai_gate['status']} "
        f"| น้ำหนักพอร์ตหลังปรับ={ai_gate['final_weight']*100:.2f}% | แนะนำอัลกอริทึม={ai_gate['recommended_execution_algo']}"
    )

    # 4. [เล่มที่ 5] คำนวณขนาดไม้ ATR Conviction Sizing และตรวจสอบเพดานความเสี่ยงต่อไม้
    sizing = v5.compute_conviction_scaled_size(
        equity=2_000_000.0,
        entry_price=218.0,
        atr=3.50,
        conviction_score=alpha_score,
        market_regime="BULL_QUIET",
    )
    print(
        f"[4/6 เล่มที่ 5 - Portfolio Risk] จำนวนหุ้นอนุมัติ={sizing['shares']:,} หุ้น "
        f"| งบความเสี่ยง={sizing['risk_budget_baht']:,.0f} บาท (Effective Risk={sizing['effective_risk_pct']*100:.2f}%)"
    )

    # 5. [เล่มที่ 6] ตรวจสอบกระดาน 5-Level OBI, Micro-Price, กฎ Tick/Board Lot และซอยไม้ TWAP
    b_p, a_p, b_vols, a_vols = v6.parse_settrade_bid_offer_snapshot({
        "bid_price_1": 218.0, "bid_volume_1": 85_000, "bid_volume_2": 62_000, "bid_volume_3": 54_000, "bid_volume_4": 48_000, "bid_volume_5": 40_000,
        "ask_price_1": 219.0, "ask_volume_1": 22_000, "ask_volume_2": 31_000, "ask_volume_3": 28_000, "ask_volume_4": 35_000, "ask_volume_5": 45_000,
    })
    micro = v6.compute_micro_price_and_urgency(b_p, a_p, b_vols[0], a_vols[0], side="BUY")
    rounded = v6.round_to_set_tick_and_board_lot(raw_price=b_p, raw_shares=int(sizing["shares"]), side="BUY")
    twap_plan = v6.generate_twap_jitter_schedule(
        total_shares=int(rounded["board_lot_shares"]), duration_seconds=1200, num_slices=4, seed=42
    )
    print(
        f"[5/6 เล่มที่ 6 - Smart Exec    ] Micro-Price={micro['micro_price']:.3f} ({micro['order_instruction']}) "
        f"| ซอยคำสั่ง TWAP={len(twap_plan)} ไม้ย่อย @ {rounded['valid_price']:.2f} บาท"
    )

    # 6. [เล่มที่ 8] บันทึกคำสั่งลง Idempotent SQLite WAL Ledger และคำนวณสัดส่วนพอร์ต Global Multi-Asset
    ledger = v8.IdempotentOrderLedger(db_path=":memory:")
    order_key = ledger.make_key("2026-11-02", "VOL1_TO_8_MASTER", "BETA", "BUY", slice_idx=1)
    ok_send, ledger_status = ledger.register_or_block(order_key, "BETA", "BUY", int(rounded["board_lot_shares"]))
    global_alloc = v8.allocate_global_multi_asset_portfolio(
        total_capital_thb=5_000_000.0,
        market_regime="LOW_VOL_BULL",
        asset_vols_pct={"TH_EQUITY": 14.0, "US_EQUITY": 16.0, "GOLD_GLD": 13.0, "CASH_TBILLS": 4.0},
    )
    print(
        f"[6/6 เล่มที่ 8 - Cloud & Global] สถานะคำสั่ง={ledger_status} (Key={order_key}) "
        f"| Global Weights={global_alloc['weights_pct']}"
    )
    print("=" * 92)
    print("✅ รันท่อประมวลผลครบทั้ง 8 เล่ม (End-to-End 8-Volume Masterclass Pipeline) สำเร็จสมบูรณ์ 100%!")
    print("=" * 92)


if __name__ == "__main__":
    run_8vol_masterclass_pipeline()
