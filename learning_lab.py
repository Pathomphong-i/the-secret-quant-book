#!/usr/bin/env python3
"""Offline exercises for the Complete 4-Volume Edition (8 stages). Python 3.10+; stdlib only.

Every price, fee and policy threshold is invented for teaching. No market data,
broker, messaging, cloud or model API is used. Outputs are not investment signals.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path

VERSION = "editorial-2026-11-10-v1"
FILES = ["01_costs.json", "02_backtest.json", "03_data_audit.json",
         "04_signals.json", "05_risk.json", "06_execution.json",
         "07_news_review.json", "08_operations.json"]
BOOK_STAGES = {1: (1, 2), 2: (3, 4), 3: (5, 6), 4: (7, 8)}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def sample_bars():
    closes = [20., 21., 20., 22., 23., 21., 24., 25.]
    rows = []
    for i, close in enumerate(closes):
        opening = closes[i - 1] + .1 if i else 20.
        rows.append(dict(day=i + 1, open=round(opening, 2),
                         high=round(max(opening, close) + .2, 2),
                         low=round(min(opening, close) - .2, 2),
                         close=close, volume=1000 + i * 100))
    return rows


def backtest(rows, fee_rate=.001, quantity=100, initial_cash=10000.):
    """Close signal, next open fill; long/cash only; final holdings marked to close."""
    if len(rows) < 4 or fee_rate < 0 or quantity <= 0:
        raise ValueError("Need at least four bars, a nonnegative fee and positive quantity")
    cash, held, pending = initial_cash, 0, None
    trades, curve = [], [initial_cash]
    for i, row in enumerate(rows):
        if pending:
            side, signal_day = pending
            price = row["open"]
            value = price * quantity
            fee = value * fee_rate
            if side == "BUY" and held == 0 and cash >= value + fee:
                cash -= value + fee
                held = quantity
                trades.append(dict(side=side, signal_day=signal_day, fill_day=row["day"],
                                   price=price, quantity=quantity, fee=round(fee, 4)))
            elif side == "SELL" and held:
                cash += value - fee
                held = 0
                trades.append(dict(side=side, signal_day=signal_day, fill_day=row["day"],
                                   price=price, quantity=quantity, fee=round(fee, 4)))
        pending = None
        curve.append(cash + held * row["close"])
        if i >= 2:
            average = sum(r["close"] for r in rows[i - 2:i + 1]) / 3
            want_stock = row["close"] > average
            if want_stock != bool(held):
                pending = ("BUY" if want_stock else "SELL", row["day"])
    peak, max_drawdown = curve[0], 0.
    for equity in curve:
        peak = max(peak, equity)
        max_drawdown = min(max_drawdown, equity / peak - 1)
    return dict(initial_cash=initial_cash, ending_cash=round(cash, 4),
                shares_held=held, ending_equity=round(curve[-1], 4),
                total_fees=round(sum(t["fee"] for t in trades), 4),
                total_return=round(curve[-1] / initial_cash - 1, 8),
                max_drawdown=round(max_drawdown, 8), trades=trades,
                pending_unfilled_signal=pending,
                assumptions="Invented bars; next open fills in full; no spread, impact, dividend or tax beyond the assumed fee; final holding is not sold")


def audit_bars(rows):
    seen, clean, rejected = set(), [], []
    for row in rows:
        reason = None
        values = [row[k] for k in ("open", "high", "low", "close", "volume")]
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in values):
            reason = "non_finite_or_nonnumeric"
        elif min(values[:4]) <= 0 or row["volume"] < 0:
            reason = "invalid_price_or_volume"
        elif row["low"] > min(row["open"], row["close"]) or row["high"] < max(row["open"], row["close"]) or row["low"] > row["high"]:
            reason = "invalid_ohlc_range"
        elif row["day"] in seen:
            reason = "duplicate_day"
        if reason:
            rejected.append(dict(row=row, reason=reason))
        else:
            clean.append(row.copy())
            seen.add(row["day"])
    return sorted(clean, key=lambda x: x["day"]), rejected


def size_position(equity, risk_fraction, entry, stop_distance, cash, lot=100):
    if min(equity, entry, stop_distance, lot) <= 0 or cash < 0 or not 0 < risk_fraction <= 1:
        raise ValueError("Invalid sizing inputs")
    risk_budget = equity * risk_fraction
    shares = math.floor(min(risk_budget / stop_distance, cash / entry) / lot) * lot
    return dict(shares=shares, risk_budget=risk_budget,
                planned_loss=round(shares * stop_distance, 4),
                notional=round(shares * entry, 4),
                note="Cash cap omits fees; planned loss is not a maximum loss guarantee")


def split_order(quantity, slots=3, lot=100):
    if lot <= 0 or slots <= 0 or quantity < 0 or quantity % lot:
        raise ValueError("Quantity must be nonnegative whole lots")
    units, extra = divmod(quantity // lot, slots)
    return [(units + (i < extra)) * lot for i in range(slots)]


def validate_news(record, as_of):
    required = {"source_id", "published_at", "received_at", "evidence", "label"}
    if not required <= record.keys():
        return dict(status="REVIEW", reason="missing_fields")
    if any(not isinstance(record[key], str) or not record[key].strip() for key in required):
        return dict(status="REVIEW", reason="invalid_field_types_or_empty_values")
    if not isinstance(as_of, str):
        return dict(status="REVIEW", reason="invalid_timestamp")
    try:
        published = datetime.fromisoformat(record["published_at"])
        received = datetime.fromisoformat(record["received_at"])
        cutoff = datetime.fromisoformat(as_of)
        if any(x.tzinfo is None for x in (published, received, cutoff)):
            raise ValueError("Timezone required")
        if received < published or max(published, received) > cutoff:
            return dict(status="REVIEW", reason="not_available_at_decision_time")
    except (ValueError, TypeError):
        return dict(status="REVIEW", reason="invalid_timestamp")
    if record["label"] not in {"positive", "negative", "unclear"} or not record["evidence"] or not record["source_id"]:
        return dict(status="REVIEW", reason="invalid_label_or_evidence")
    return dict(status="READY_FOR_HUMAN_REVIEW", reason="structure_and_time_checks_only")


def stage(volume, previous):
    if volume == 1:
        buy, sell, quantity, rate = 20., 21., 100, .001
        fees = (buy + sell) * quantity * rate
        return dict(buy=buy, sell=sell, quantity=quantity, fee_rate=rate,
                    gross_profit=(sell-buy)*quantity, fees=fees,
                    net_profit=round((sell-buy)*quantity-fees, 4), synthetic=True)
    if volume == 2:
        rows = sample_bars()
        rate = previous[1]["fee_rate"]
        return dict(bars=rows, fee_rate=rate, with_costs=backtest(rows, rate),
                    without_costs=backtest(rows, 0), synthetic=True)
    if volume == 3:
        raw = previous[2]["bars"]
        dirty = raw + [raw[2].copy(), dict(raw[3], day=9, close=-1)]
        clean, rejected = audit_bars(dirty)
        return dict(input_rows=len(dirty), accepted_rows=len(clean),
                    rejected_rows=len(rejected), bars=clean, quarantine=rejected,
                    audited_backtest=backtest(clean, previous[2]["fee_rate"]), synthetic=True)
    if volume == 4:
        rows = previous[3]["bars"]
        current, prior = rows[-1], rows[-4:-1]
        tr = [max(rows[i]["high"]-rows[i]["low"],
                  abs(rows[i]["high"]-rows[i-1]["close"]),
                  abs(rows[i]["low"]-rows[i-1]["close"])) for i in range(len(rows)-3, len(rows))]
        atr = sum(tr)/3
        return dict(day=current["day"], close=current["close"],
                    prior_high=max(r["high"] for r in prior),
                    breakout=current["close"] > max(r["high"] for r in prior),
                    atr_simple_3=round(atr, 6),
                    note="Feature calculation on invented bars; not a validated trading strategy", synthetic=True)
    if volume == 5:
        feature = previous[4]
        distance = 2*feature["atr_simple_3"]
        sizing = size_position(100000., .01, feature["close"], distance, 100000.)
        return dict(**sizing, entry=feature["close"], stop_distance=distance,
                    equity=100000., risk_fraction=.01, lot=100, synthetic=True)
    if volume == 6:
        sizing = previous[5]
        quantities = split_order(sizing["shares"])
        fills = [dict(quantity=q, price=25.+i*.1) for i,q in enumerate(quantities) if q]
        filled = sum(f["quantity"] for f in fills)
        avg = sum(f["quantity"]*f["price"] for f in fills)/filled if filled else None
        return dict(quantities=quantities, fills=fills, filled_quantity=filled,
                    average_fill=avg, arrival_price=25.,
                    shortfall_before_fees=round(sum((f["price"]-25.)*f["quantity"] for f in fills), 4),
                    obi=(300-100)/(300+100), microprice=(25.*300+24.9*100)/400,
                    note="Fills are stipulated for an arithmetic exercise; no order reaches a market", synthetic=True)
    if volume == 7:
        news = dict(source_id="fictional-news-001", published_at="2026-01-05T09:00:00+07:00",
                    received_at="2026-01-05T09:03:00+07:00",
                    evidence="บริษัทสมมติรายงานรายได้เพิ่มขึ้น แต่ไม่ระบุตัวเลขกำไร", label="unclear")
        return dict(news=news, at_0901=validate_news(news, "2026-01-05T09:01:00+07:00"),
                    at_0905=validate_news(news, "2026-01-05T09:05:00+07:00"),
                    prior_stage_filled_quantity=previous[6]["filled_quantity"],
                    note="Handwritten fixture; no language model called; schema validity does not establish truth", synthetic=True)
    execution = previous[6]
    intent = dict(intent_id="exercise-order-001", account="PAPER", symbol="SYNTHETIC",
                  side="BUY", quantity=execution["filled_quantity"])
    key = digest(intent)
    ledger = {}
    for _ in range(2):
        ledger.setdefault(key, dict(intent, state="SIMULATED_FILLED"))
    expected = execution["filled_quantity"]
    observed = max(0, expected-100)
    mismatch = expected != observed
    news = previous[7]["at_0905"]["status"]
    return dict(repeated_intents=2, ledger_records=len(ledger), order_key=key,
                expected_shares=expected, broker_fixture_shares=observed,
                reconciliation="MISMATCH" if mismatch else "MATCH",
                new_orders_allowed=False, news_status=news,
                stop_reason="Reconciliation mismatch; human review required",
                example_fx_return=(1+.05)*(1-.03)-1,
                hedge_contracts_unrounded=1000000*1.1/(900*200),
                note="In-memory teaching ledger, invented broker snapshot; not durable storage or exactly-once execution", synthetic=True)


def run(volume, output):
    output = Path(output)
    previous, hashes = {}, {}
    for i in range(1, volume):
        path = output / FILES[i-1]
        if not path.exists():
            raise ValueError(f"Missing {path.name}; run --volume {i} first")
        record = json.loads(path.read_text(encoding="utf-8"))
        if record.get("version") != VERSION or record.get("volume") != i:
            raise ValueError(f"Wrong version/stage in {path.name}; rerun from volume 1")
        if record.get("inputs") != hashes:
            raise ValueError(f"Stale dependencies in {path.name}; rerun from volume {i}")
        if record.get("result_sha256") != digest(record["result"]):
            raise ValueError(f"Changed result in {path.name}; rerun volume {i}")
        previous[i] = record["result"]
        hashes[path.name] = digest(record)
    result = stage(volume, previous)
    record = dict(version=VERSION, volume=volume, inputs=hashes,
                  result=result, result_sha256=digest(result))
    output.mkdir(parents=True, exist_ok=True)
    path = output / FILES[volume-1]
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    return path, result


def run_book(book, output):
    if book not in BOOK_STAGES:
        raise ValueError(f"Unknown book {book}; choose 1..4")
    return [run(stage_num, output) for stage_num in BOOK_STAGES[book]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--book", type=int, choices=range(1, 5),
                       help="Run both practice stages of Book 1..4 in order")
    group.add_argument("--stage", "--volume", dest="volume", type=int, choices=range(1, 9),
                       help="Run an individual practice stage 1..8")
    parser.add_argument("--output", type=Path, default=Path("learning_output"))
    args = parser.parse_args()
    try:
        if args.book is not None:
            outputs = run_book(args.book, args.output)
            for idx, (path, result) in enumerate(outputs, start=1):
                print(f"Book {args.book} (Part {idx}): {path}")
                print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            path, result = run(args.volume, args.output)
            print(f"Stage {args.volume}: {path}")
            print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, KeyError, json.JSONDecodeError) as exc:
        parser.exit(2, f"Exercise stopped: {exc}\n")


if __name__ == "__main__":
    main()
