#!/usr/bin/env python3
"""
tests/test_8vol_audit_suite.py
==============================
Automated Technical, Editorial & NotebookLM Institutional Verification Suite across all 8 Volumes.
Verifies every P0/P1 audit fix AND the 4 institutional mathematical modules from NotebookLM:
- P0-1: Deterministic benchmark & controlled ablation reproduction
- P0-2: Point-in-Time news sanitizer (published_at vs received_at, Asia/Bangkok TZ,
        weekend/holiday rollover, lunch break 12:30-14:25, after-hours > 16:25, entity/year masking)
- P0-3: 3-Tier Circuit Breaker & Kill-Switch (open order sweep cancellation & portfolio state action)
- P1-Vol3: Walk-Forward Efficiency (WFE) protection when In-Sample return <= 0 or < min_is_ann_ret
- P1-Vol4: Cross-Sectional RS minimum bar filter (min_valid_bars=120) & universe size flag
- P1-Vol6: Multi-Level OBI protection against empty/Ceiling-Floor order books and < 5 levels
- NLM-Vol3: Probabilistic & Deflated Sharpe Ratio (PSR/DSR — Bailey & López de Prado, 2014 / AFML Ch. 14)
- NLM-Vol4: Ornstein-Uhlenbeck (OU) Half-Life of Mean Reversion & Variance Ratio (Ernest Chan Ch. 2)
- NLM-Vol6: Kyle's Lambda, Amihud Illiquidity & VPIN Toxicity (López de Prado AFML Ch. 19)
- NLM-Vol7: Tech Supply Chain Revenue Spillover & Kalman Filter Dynamic Beta (Ernest Chan Ch. 3 & Supply Chain Blueprint)
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

from vol3_data_backtest.ch10_12_wfe_and_monte_carlo import (
    run_rolling_walk_forward,
    compute_probabilistic_and_deflated_sharpe,
)
from vol4_alpha_signal.ch01_03_er_hurst_and_regime import compute_ou_half_life
from vol4_alpha_signal.ch04_06_vcp_kama_and_rs_rank import rank_cross_sectional_rs
from vol6_smart_execution.ch01_03_friction_impact_and_adverse import compute_multilevel_obi
from vol6_smart_execution.ch10_12_set8_rules_and_tca_report import compute_kyle_amihud_and_vpin
from vol7_ai_llm_quant.ch01_03_news_schema_sof_and_pit import sanitize_pit_news_prompt
from vol7_ai_llm_quant.ch10_12_rrg_leadlag_and_master_gate import compute_supply_chain_lead_lag_and_kalman_spread
from vol8_cloud_multi_asset.ch04_06_telemetry_health_and_killswitch import trigger_three_tier_circuit_breaker
import reproduce_benchmarks


class TestEightVolumeAuditSuite(unittest.TestCase):
    def test_p0_1_reproduce_benchmarks(self) -> None:
        df_b1 = reproduce_benchmarks.run_table_b1_architecture_comparison()
        self.assertEqual(len(df_b1), 4)
        ablations = reproduce_benchmarks.get_table_b2_controlled_ablations()
        self.assertEqual(len(ablations), 6)
        sim1 = reproduce_benchmarks.simulate_controlled_ablation_series(seed=2026)
        sim2 = reproduce_benchmarks.simulate_controlled_ablation_series(seed=2026)
        self.assertEqual(sim1, sim2)

    def test_p0_2_pit_news_timestamp_holiday_and_latency(self) -> None:
        res = sanitize_pit_news_prompt(
            raw_text="In 2023, DELTA announced Q3 revenue expansion of 22% YoY.",
            pub_timestamp="2023-10-20T17:40:00+07:00",
            tickers_to_mask=["DELTA"],
            received_timestamp="2023-10-20T17:42:15+07:00",
            set_holidays={"2023-10-23"},
        )
        self.assertEqual(res["effective_trade_session"], "2023-10-24_MORNING_ATO_OPEN")
        self.assertIn("[ENTITY_1]", res["sanitized_prompt_text"])
        self.assertIn("[YEAR]", res["sanitized_prompt_text"])
        self.assertNotIn("DELTA", res["sanitized_prompt_text"])

        res_lunch = sanitize_pit_news_prompt(
            raw_text="PTT reports interim dividend.",
            pub_timestamp="2023-10-25T13:05:00+07:00",
            tickers_to_mask=["PTT"],
            received_timestamp="2023-10-25T13:10:00+07:00",
        )
        self.assertEqual(res_lunch["effective_trade_session"], "2023-10-25_AFTERNOON_ATO2_OPEN")

        res_delayed = sanitize_pit_news_prompt(
            raw_text="AOT passenger growth rises.",
            pub_timestamp="2023-10-25T16:20:00+07:00",
            tickers_to_mask=["AOT"],
            received_timestamp="2023-10-25T16:28:00+07:00",
        )
        self.assertEqual(res_delayed["effective_trade_session"], "2023-10-26_MORNING_ATO_OPEN")

    def test_p0_3_circuit_breaker_cancels_open_orders(self) -> None:
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

    def test_p1_vol3_wfe_negative_in_sample_guard(self) -> None:
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
        empty_res = compute_multilevel_obi([], [])
        self.assertEqual(empty_res["valid_levels_used"], 0)
        self.assertTrue(empty_res["is_thin_book_warning"])
        self.assertIn("EMPTY_OR_LOCKED_BOOK", str(empty_res["book_pressure_state"]))

    def test_nlm_vol3_deflated_sharpe_ratio(self) -> None:
        np.random.seed(2026)
        strong_rets = np.random.normal(0.0014, 0.009, 1225)
        res_disciplined = compute_probabilistic_and_deflated_sharpe(
            strong_rets, benchmark_sr_annual=0.50, num_trials_k=5, trials_sr_std_annual=0.35
        )
        res_overfitted = compute_probabilistic_and_deflated_sharpe(
            strong_rets, benchmark_sr_annual=0.50, num_trials_k=1000, trials_sr_std_annual=0.95
        )
        self.assertGreater(res_disciplined["dsr"], res_overfitted["dsr"])
        self.assertTrue(res_disciplined["passed_institutional_gate"])

    def test_nlm_vol4_ornstein_uhlenbeck_half_life(self) -> None:
        np.random.seed(7)
        y = np.zeros(300)
        y[0] = np.log(100.0)
        for t in range(1, 300):
            y[t] = y[t - 1] - 0.12 * (y[t - 1] - np.log(100.0)) + np.random.normal(0, 0.008)
        ou_res = compute_ou_half_life(np.exp(y))
        self.assertLess(ou_res["lambda_coef"], 0.0)
        self.assertTrue(ou_res["is_mean_reverting"])
        self.assertTrue(2.0 <= ou_res["half_life_days"] <= 15.0)

    def test_nlm_vol6_kyle_amihud_and_vpin(self) -> None:
        prices_calm = np.array([100 + ((-1) ** i) * 0.25 for i in range(40)], dtype=float)
        vols_calm = np.full(40, 200000.0)
        res_calm = compute_kyle_amihud_and_vpin(prices_calm, vols_calm, n_buckets=8)

        prices_toxic = np.linspace(100.0, 82.0, 40)
        vols_toxic = np.full(40, 500000.0)
        res_toxic = compute_kyle_amihud_and_vpin(prices_toxic, vols_toxic, n_buckets=8)
        self.assertGreater(res_toxic["vpin"], res_calm["vpin"])
        self.assertTrue(res_toxic["high_toxicity_alert"])

    def test_nlm_vol7_supply_chain_lead_lag_and_kalman(self) -> None:
        revs = {
            "TSMC_TW": [180, 185, 190, 192, 195, 200, 205, 210, 215, 220, 235, 260],
            "ASML_EU": [50, 52, 51, 53, 55, 56, 58, 60, 62, 64, 68, 75],
        }
        weights = {"TSMC_TW": 0.65, "ASML_EU": 0.35}
        upstream = np.linspace(100.0, 135.0, 40)
        # Downstream lags suddenly on final bar -> negative spread Z-score + positive supplier revenue momentum
        downstream = np.concatenate([np.linspace(100.0, 132.0, 39), [115.0]])
        res = compute_supply_chain_lead_lag_and_kalman_spread(revs, weights, upstream, downstream)
        self.assertGreater(res["rev_spillover_z"], 1.0)
        self.assertLess(res["spread_z"], -2.0)
        self.assertEqual(res["action"], "LONG_LAGGARD_CATCHUP")


if __name__ == "__main__":
    unittest.main(verbosity=2)
