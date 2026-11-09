#!/usr/bin/env python3
"""
tests/test_8vol_audit_suite.py
==============================
Automated Technical & Editorial Audit Verification Suite across all 8 Volumes.
Verifies every P0 and P1 mathematical/engineering edge case identified in the audit:
- P0-1: Deterministic benchmark & controlled ablation reproduction
- P0-2: Point-in-Time news sanitizer (published_at vs received_at, Asia/Bangkok TZ,
        weekend/holiday rollover, lunch break 12:30-14:25, after-hours > 16:25, entity/year masking)
- P0-3: 3-Tier Circuit Breaker & Kill-Switch (open order sweep cancellation & portfolio state action)
- P1-Vol3: Walk-Forward Efficiency (WFE) protection when In-Sample return <= 0 or < min_is_ann_ret
- P1-Vol4: Cross-Sectional RS minimum bar filter (min_valid_bars=120) & universe size flag
- P1-Vol6: Multi-Level OBI protection against empty/Ceiling-Floor order books and < 5 levels
"""

from __future__ import annotations
import sys
import unittest
from pathlib import Path
import numpy as np
import pandas as pd

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from vol3_data_backtest.ch10_12_wfe_and_monte_carlo import run_rolling_walk_forward
from vol4_alpha_signal.ch04_06_vcp_kama_and_rs_rank import rank_cross_sectional_rs
from vol6_smart_execution.ch01_03_friction_impact_and_adverse import compute_multilevel_obi
from vol7_ai_llm_quant.ch01_03_news_schema_sof_and_pit import sanitize_pit_news_prompt
from vol8_cloud_multi_asset.ch04_06_telemetry_health_and_killswitch import trigger_three_tier_circuit_breaker
import reproduce_benchmarks


class TestEightVolumeAuditSuite(unittest.TestCase):
    def test_p0_1_reproduce_benchmarks(self) -> None:
        df_b1 = reproduce_benchmarks.run_table_b1_architecture_comparison()
        self.assertEqual(len(df_b1), 3)
        ablations = reproduce_benchmarks.get_table_b2_controlled_ablations()
        self.assertEqual(len(ablations), 6)
        sim1 = reproduce_benchmarks.simulate_controlled_ablation_series(seed=2026)
        sim2 = reproduce_benchmarks.simulate_controlled_ablation_series(seed=2026)
        self.assertEqual(sim1, sim2)

    def test_p0_2_pit_news_timestamp_holiday_and_latency(self) -> None:
        # 1. Friday after-hours news (17:40) + Monday holiday (2023-10-23) -> Tuesday 2023-10-24 MORNING_ATO_OPEN
        res = sanitize_pit_news_prompt(
            raw_text="In 2023, ALPHA_CORP announced Q3 revenue expansion of 22% YoY.",
            pub_timestamp="2023-10-20T17:40:00+07:00",
            tickers_to_mask=["ALPHA_CORP"],
            received_timestamp="2023-10-20T17:42:15+07:00",
            set_holidays={"2023-10-23"},
        )
        self.assertEqual(res["effective_trade_session"], "2023-10-24_MORNING_ATO_OPEN")
        self.assertIn("[ENTITY_1]", res["sanitized_prompt_text"])
        self.assertIn("[YEAR]", res["sanitized_prompt_text"])
        self.assertNotIn("ALPHA_CORP", res["sanitized_prompt_text"])

        # 2. Lunch break news (13:10) -> AFTERNOON_ATO2_OPEN
        res_lunch = sanitize_pit_news_prompt(
            raw_text="BETA_CORP reports interim dividend.",
            pub_timestamp="2023-10-25T13:05:00+07:00",
            tickers_to_mask=["BETA_CORP"],
            received_timestamp="2023-10-25T13:10:00+07:00",
        )
        self.assertEqual(res_lunch["effective_trade_session"], "2023-10-25_AFTERNOON_ATO2_OPEN")

        # 3. Ingestion latency pushes 16:20 published news to 16:28 received -> next trading day open
        res_delayed = sanitize_pit_news_prompt(
            raw_text="GAMMA_CORP passenger growth rises.",
            pub_timestamp="2023-10-25T16:20:00+07:00",
            tickers_to_mask=["GAMMA_CORP"],
            received_timestamp="2023-10-25T16:28:00+07:00",
        )
        self.assertEqual(res_delayed["effective_trade_session"], "2023-10-26_MORNING_ATO_OPEN")

    def test_p0_3_circuit_breaker_cancels_open_orders(self) -> None:
        # Tier 3 Kill-Switch must cancel all pending open_order_ids
        res_tier3 = trigger_three_tier_circuit_breaker(
            intraday_return_pct=-4.5,
            peak_drawdown_pct=-16.0,
            consecutive_api_errors=5,
            data_age_seconds=15.0,
            open_order_ids=["ORD-001", "ORD-002", "ORD-003"],
        )
        self.assertEqual(res_tier3["tier"], 3)
        self.assertTrue(res_tier3["cancel_all_open_orders"])
        self.assertEqual(res_tier3["cancelled_order_ids"], ["ORD-001", "ORD-002", "ORD-003"])
        self.assertEqual(
            res_tier3["portfolio_state_action"],
            "HOLD_EXISTING_WITH_HARD_STOPS_AND_HALT_NEW_ENTRIES",
        )

        # Tier 2 Throttle keeps open orders intact
        res_tier2 = trigger_three_tier_circuit_breaker(
            intraday_return_pct=-2.8,
            peak_drawdown_pct=-6.5,
            consecutive_api_errors=0,
            data_age_seconds=10.0,
            open_order_ids=["ORD-001"],
        )
        self.assertEqual(res_tier2["tier"], 2)
        self.assertFalse(res_tier2["cancel_all_open_orders"])
        self.assertEqual(res_tier2["cancelled_order_ids"], [])

    def test_p1_vol3_wfe_negative_in_sample_guard(self) -> None:
        # Monotonically falling series -> In-Sample return is <= 0 -> WFE must be 0.0 and INVALID_IS_EDGE
        falling_prices = pd.Series(np.linspace(100.0, 40.0, 700))
        wf_df, avg_wfe = run_rolling_walk_forward(
            falling_prices, candidate_windows=[10, 20], is_bars=400, oos_bars=100
        )
        self.assertFalse(wf_df.empty)
        self.assertEqual(avg_wfe, 0.0)
        self.assertTrue((wf_df["wfe_status"] == "INVALID_IS_EDGE").all())

    def test_p1_vol4_rs_min_bars_and_universe_flag(self) -> None:
        np.random.seed(42)
        n_days = 130
        bench = pd.Series(1400 * np.exp(np.cumsum(np.random.normal(0.0002, 0.008, n_days))))
        stocks = pd.DataFrame({
            "VALID_A": 50 * np.exp(np.cumsum(np.random.normal(0.0015, 0.010, n_days))),
            "VALID_B": 30 * np.exp(np.cumsum(np.random.normal(0.0005, 0.012, n_days))),
            "SHORT_IPO": [np.nan] * 80 + list(20 * np.exp(np.cumsum(np.random.normal(0.002, 0.01, 50)))),
        })
        df_rs = rank_cross_sectional_rs(stocks, bench, min_valid_bars=120, min_universe_size=10)
        self.assertNotIn("SHORT_IPO", df_rs.index)
        self.assertIn("VALID_A", df_rs.index)
        self.assertFalse(bool(df_rs["is_statistically_valid_universe"].iloc[0]))

    def test_p1_vol6_obi_empty_and_partial_orderbook(self) -> None:
        # Empty order book (e.g., locked at Ceiling/Floor or pre-open)
        empty_res = compute_multilevel_obi([], [])
        self.assertEqual(empty_res["valid_levels_used"], 0)
        self.assertTrue(empty_res["is_thin_book_warning"])
        self.assertIn("EMPTY_OR_LOCKED_BOOK", str(empty_res["book_pressure_state"]))

        # Partial 2-level book
        partial_res = compute_multilevel_obi([50000, 20000], [10000, 15000])
        self.assertEqual(partial_res["valid_levels_used"], 2)
        self.assertTrue(partial_res["is_thin_book_warning"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
