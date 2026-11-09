"""Checks for the offline learning path; no network or third-party dependencies."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("learning_lab", Path(__file__).resolve().parents[1] / "learning_lab.py")
lab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lab)


class LearningLabTests(unittest.TestCase):
    def test_cash_ledger_matches_manual_arithmetic(self):
        result = lab.backtest(lab.sample_bars())
        # Buy 100 at 22.1, sell 100 at 21.1, buy 100 at 24.1; mark at 25.
        self.assertAlmostEqual(result["ending_cash"], 10000-2210-2.21+2110-2.11-2410-2.41)
        self.assertEqual(result["ending_equity"], 9983.27)
        self.assertEqual(result["total_fees"], 6.73)
        self.assertEqual(result["shares_held"], 100)

    def test_signals_precede_fills_and_future_changes_do_not_change_past(self):
        rows = lab.sample_bars()
        original = lab.backtest(rows)["trades"]
        rows[-1] = dict(rows[-1], close=1, low=.5)
        altered = lab.backtest(rows)["trades"]
        self.assertEqual(original, altered)
        self.assertTrue(all(t["fill_day"] > t["signal_day"] for t in original))

    def test_audit_quarantines_without_repairing_input(self):
        rows = lab.sample_bars()
        broken = dict(rows[0], day=9, high=1)
        original = broken.copy()
        clean, rejected = lab.audit_bars(rows + [rows[0].copy(), broken])
        self.assertEqual(len(clean), 8)
        self.assertEqual({r["reason"] for r in rejected}, {"duplicate_day", "invalid_ohlc_range"})
        self.assertEqual(broken, original)

    def test_cash_and_risk_caps(self):
        self.assertEqual(lab.size_position(100000, .01, 20, 2, 6000)["shares"], 300)
        self.assertEqual(lab.size_position(100000, .01, 20, 2, 1000)["shares"], 0)
        with self.assertRaises(ValueError):
            lab.size_position(100000, .01, 20, 0, 6000)

    def test_split_preserves_quantity_and_lots(self):
        for quantity in (0, 100, 200, 1000):
            pieces = lab.split_order(quantity)
            self.assertEqual(sum(pieces), quantity)
            self.assertTrue(all(q >= 0 and q % 100 == 0 for q in pieces))
        with self.assertRaises(ValueError):
            lab.split_order(100, lot=0)

    def test_news_must_be_received_before_decision(self):
        record = dict(source_id="x", published_at="2026-01-05T09:00:00+07:00",
                      received_at="2026-01-05T09:03:00+07:00", evidence="text", label="unclear")
        self.assertEqual(lab.validate_news(record, "2026-01-05T09:01:00+07:00")["status"], "REVIEW")
        self.assertEqual(lab.validate_news(record, "2026-01-05T09:05:00+07:00")["status"], "READY_FOR_HUMAN_REVIEW")
        self.assertEqual(lab.validate_news(record, "2026-01-05T09:05:00")["status"], "REVIEW")
        record["evidence"] = ""
        self.assertEqual(lab.validate_news(record, "2026-01-05T09:05:00+07:00")["status"], "REVIEW")
        record["evidence"] = 123
        record["label"] = []
        self.assertEqual(lab.validate_news(record, "2026-01-05T09:05:00+07:00")["status"], "REVIEW")

    def test_full_chain_is_repeatable_and_stops_on_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            for n in range(1, 9):
                path, result = lab.run(n, directory)
            first = path.read_bytes()
            lab.run(8, directory)
            self.assertEqual(path.read_bytes(), first)
            self.assertEqual(result["ledger_records"], 1)
            self.assertEqual(result["reconciliation"], "MISMATCH")
            self.assertFalse(result["new_orders_allowed"])

    def test_missing_and_changed_inputs_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "run --volume 1"):
                lab.run(2, directory)
            path, _ = lab.run(1, directory)
            record = json.loads(path.read_text())
            record["result"]["net_profit"] = 999
            path.write_text(json.dumps(record))
            with self.assertRaisesRegex(ValueError, "Changed result"):
                lab.run(2, directory)

    def test_four_book_edition_chain_matches_eight_stages(self):
        with tempfile.TemporaryDirectory() as d_books, tempfile.TemporaryDirectory() as d_stages:
            for b in range(1, 5):
                pairs = lab.run_book(b, d_books)
                self.assertEqual(len(pairs), 2)
            for s in range(1, 9):
                lab.run(s, d_stages)
            for fname in lab.FILES:
                self.assertEqual((Path(d_books) / fname).read_bytes(),
                                 (Path(d_stages) / fname).read_bytes())

    def test_single_book_run_all_matches_parts_chain(self):
        with tempfile.TemporaryDirectory() as d_all, tempfile.TemporaryDirectory() as d_parts:
            all_res = lab.run_all(d_all)
            self.assertEqual(len(all_res), 8)
            for p in range(1, 9):
                lab.run(p, d_parts)
            for fname in lab.FILES:
                self.assertEqual((Path(d_all) / fname).read_bytes(),
                                 (Path(d_parts) / fname).read_bytes())


if __name__ == "__main__":
    unittest.main()
