#!/usr/bin/env python3
"""
The Secret Quant: 8-Volume Masterclass Series
เล่มที่ 3: วิศวกรรมข้อมูลและห้องแล็บ Backtest (Data Engineering & Realistic Backtest Lab)
ผู้เขียน: ปฐมพงษ์ พิพัฒน์สุริยวงศ์
รวมซอร์สโค้ดครบทุกบทประจำเล่มที่ 3 พร้อมรันทดสอบได้ทันที
"""

from __future__ import annotations
import json, math, os, sqlite3, hashlib
import numpy as np
import pandas as pd



# ==============================================================================import sqlite3
from pathlib import Path
try:
    import duckdb
except ImportError:
    class _DuckDBShim:
        def connect(self, *_a, **_kw):
            return self
        def execute(self, sql: str):
            import re as _re
            m = _re.search(r"read_parquet\('([^']+)'\)", sql)
            if m:
                import glob as _glob
                files = _glob.glob(m.group(1))
                self._df = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True) if files else pd.DataFrame()
            else:
                self._df = pd.DataFrame()
            return self
        def df(self):
            return self._df
    duckdb = _DuckDBShim()

import pandas as pd

class QuantDataStore:
    def __init__(self, base_dir: str = "./quant_data"):
        self.base_path = Path(base_dir)
        self.parquet_dir = self.base_path / "ohlcv_parquet"
        self.parquet_dir.mkdir(parents=True, exist_ok=True)
        self.sqlite_path = self.base_path / "metadata.db"
        self.duck_con = duckdb.connect(database=":memory:")
        self._init_metadata_db()

    def _init_metadata_db(self) -> None:
        with sqlite3.connect(self.sqlite_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS symbols (
                    symbol_id INTEGER PRIMARY KEY,
                    ticker TEXT NOT NULL,
                    market TEXT NOT NULL,
                    is_active INTEGER DEFAULT 1
                )
            """)

    def save_ohlcv_parquet(self, df: pd.DataFrame, market: str) -> Path:
        file_path = self.parquet_dir / f"{market.lower()}_daily.parquet"
        df.to_parquet(file_path, engine="pyarrow", compression="zstd", index=False)
        return file_path

    def query_ohlcv(self, market: str, tickers: list[str], start_date: str) -> pd.DataFrame:
        file_path = self.parquet_dir / f"{market.lower()}_daily.parquet"
        ticker_list = ", ".join([f"'{t}'" for t in tickers])
        query = f"""
            SELECT trade_date, ticker, open, high, low, close, volume
            FROM read_parquet('{file_path.as_posix()}')
            WHERE ticker IN ({ticker_list}) AND trade_date >= '{start_date}'
            ORDER BY trade_date ASC, ticker ASC
        """
        return self.duck_con.execute(query).df()


from pathlib import Path
import pandas as pd

class IncrementalOHLCVIngestor:
    def __init__(self, parquet_path: str, symbol_map: dict[str, str]):
        self.parquet_path = Path(parquet_path)
        self.symbol_map = symbol_map  # {"TICKER": "SEC_ID"}

    def get_incremental_start_date(self, default_start: str = "2015-01-01") -> str:
        if not self.parquet_path.exists():
            return default_start
        existing_df = pd.read_parquet(self.parquet_path, columns=["trade_date"])
        if existing_df.empty:
            return default_start
        last_date = pd.to_datetime(existing_df["trade_date"]).max()
        return (last_date - pd.Timedelta(days=3)).strftime("%Y-%m-%d")

    def ingest_batch(self, raw_new_df: pd.DataFrame) -> pd.DataFrame:
        df = raw_new_df.copy()
        df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.strftime("%Y-%m-%d")
        df = df[df["volume"] > 0].dropna(subset=["open", "high", "low", "close"])
        df["security_id"] = df["ticker"].map(self.symbol_map)
        df = df.dropna(subset=["security_id"])

        if self.parquet_path.exists():
            old_df = pd.read_parquet(self.parquet_path)
            combined = pd.concat([old_df, df], ignore_index=True)
        else:
            combined = df

        clean_df = combined.drop_duplicates(
            subset=["security_id", "trade_date"], keep="last"
        ).sort_values(["trade_date", "security_id"]).reset_index(drop=True)
        clean_df.to_parquet(self.parquet_path, compression="zstd", index=False)
        return clean_df


from pathlib import Path

import pandas as pd

class MultiDimensionalCatalog:
    def __init__(self, root_dir: str = "./quant_catalog"):
        self.root = Path(root_dir)
        self.con = duckdb.connect(database=":memory:")

    def write_intraday_partitioned(self, df: pd.DataFrame, timeframe: str = "5m") -> None:
        data = df.copy()
        data["year"] = pd.to_datetime(data["bar_timestamp"]).dt.year
        for year, group in data.groupby("year"):
            part_dir = self.root / f"tf={timeframe}" / f"year={year}"
            part_dir.mkdir(parents=True, exist_ok=True)
            group.drop(columns=["year"]).to_parquet(
                part_dir / "bars.parquet", compression="zstd", index=False
            )

    def query_pit_index_ohlcv(
        self, daily_parquet: str, membership_parquet: str, index_name: str
    ) -> pd.DataFrame:
        sql = f"""
            SELECT d.trade_date, d.security_id, m.ticker, d.close, d.volume
            FROM read_parquet('{daily_parquet}') AS d
            INNER JOIN read_parquet('{membership_parquet}') AS m
                ON d.security_id = m.security_id
                AND m.index_name = '{index_name}'
                AND d.trade_date >= m.entry_date
                AND (m.exit_date IS NULL OR d.trade_date <= m.exit_date)
            ORDER BY d.trade_date ASC, d.security_id ASC
        """
        return self.con.execute(sql).df()


import numpy as np
import pandas as pd

def adjust_ohlcv_for_splits_and_xr(
    ohlcv_df: pd.DataFrame, actions_df: pd.DataFrame
) -> pd.DataFrame:
    df = ohlcv_df.sort_values("trade_date").copy().reset_index(drop=True)
    df["event_factor"] = 1.0

    for _, act in actions_df.iterrows():
        ex_date = act["ex_date"]
        if act["action_type"] == "SPLIT":
            factor = act["old_shares"] / act["new_shares"]
        elif act["action_type"] == "XR":
            p_cum = df.loc[df["trade_date"] < ex_date, "close"].iloc[-1]
            terp = (act["old_shares"] * p_cum + act["new_shares"] * act["sub_price"]) / (
                act["old_shares"] + act["new_shares"]
            )
            factor = terp / p_cum
        else:
            factor = 1.0
        df.loc[df["trade_date"] == ex_date, "event_factor"] *= factor

    rev_cum_factor = df["event_factor"].iloc[::-1].cumprod().iloc[::-1]
    df["cum_af"] = rev_cum_factor.shift(-1, fill_value=1.0)
    for col in ["open", "high", "low", "close"]:
        df[f"{col}_adj"] = (df[col] * df["cum_af"]).round(4)
    df["volume_adj"] = np.round(df["volume"] / df["cum_af"]).astype("int64")
    return df


import pandas as pd

def apply_xd_dividend_accounting(
    price_df: pd.DataFrame,
    div_df: pd.DataFrame,
    withholding_tax: float = 0.10,
) -> pd.DataFrame:
    df = price_df.sort_values("trade_date").copy().reset_index(drop=True)
    div_map = div_df.set_index("xd_date")["dps"].to_dict()

    df["gross_dps"] = df["trade_date"].map(div_map).fillna(0.0)
    df["net_dps"] = df["gross_dps"] * (1.0 - withholding_tax)
    prev_close = df["close"].shift(1)

    df["xd_factor"] = 1.0
    valid_xd = (df["net_dps"] > 0) & (prev_close > 0)
    df.loc[valid_xd, "xd_factor"] = 1.0 - (
        df.loc[valid_xd, "net_dps"] / prev_close.loc[valid_xd]
    )

    rev_xd_cum = df["xd_factor"].iloc[::-1].cumprod().iloc[::-1]
    df["cum_xd_af"] = rev_xd_cum.shift(-1, fill_value=1.0)
    df["close_tr_adj"] = (df["close"] * df["cum_xd_af"]).round(4)
    df["total_return_1d"] = (df["close"] + df["net_dps"]) / prev_close - 1.0
    return df


import numpy as np
import pandas as pd

def sanitize_ohlcv_frame(
    df: pd.DataFrame, ceiling_limit: float = 0.305
) -> tuple[pd.DataFrame, pd.DataFrame]:
    clean = df.sort_values("trade_date").copy().reset_index(drop=True)
    price_cols = ["open", "high", "low", "close"]

    valid_positive = (clean[price_cols] > 0).all(axis=1) & (clean["volume"] >= 0)
    quarantine_df = clean.loc[~valid_positive].copy()
    clean = clean.loc[valid_positive].copy().reset_index(drop=True)

    clean["high"] = clean[price_cols].max(axis=1)
    clean["low"] = clean[price_cols].min(axis=1)

    ret_fwd = clean["close"].pct_change()
    ret_next = clean["close"].pct_change(-1)
    is_glitch_spike = (ret_fwd.abs() > ceiling_limit) & (ret_next.abs() > ceiling_limit)

    if is_glitch_spike.any():
        quarantine_df = pd.concat([quarantine_df, clean.loc[is_glitch_spike]])
        clean = clean.loc[~is_glitch_spike].copy().reset_index(drop=True)

    clean["daily_return"] = clean["close"].pct_change().fillna(0.0)
    clean["is_tradable"] = (clean["volume"] > 0) & (
        clean["daily_return"].abs() <= ceiling_limit
    )
    return clean, quarantine_df


import pandas as pd

def run_full_hygiene_pipeline(
    raw_ohlcv: pd.DataFrame,
    actions_df: pd.DataFrame,
    div_df: pd.DataFrame,
    ceiling_limit: float = 0.305,
) -> dict[str, pd.DataFrame]:
    step1_clean, quarantine_df = sanitize_ohlcv_frame(
        raw_ohlcv, ceiling_limit=ceiling_limit
    )
    step2_split_adj = adjust_ohlcv_for_splits_and_xr(step1_clean, actions_df)

    split_for_xd = step2_split_adj.copy()
    for col in ["open", "high", "low", "close"]:
        split_for_xd[col] = split_for_xd[f"{col}_adj"]
    split_for_xd["volume"] = split_for_xd["volume_adj"]

    step3_final = apply_xd_dividend_accounting(
        split_for_xd, div_df, withholding_tax=0.10
    )
    step3_final["turnover_thb"] = (
        step3_final["close_adj"] * step3_final["volume_adj"]
    ).round(2)
    return {
        "golden_ohlcv": step3_final,
        "quarantine_records": quarantine_df,
    }


import pandas as pd

class PointInTimeDataSlicer:
    def __init__(
        self,
        ohlcv_df: pd.DataFrame,
        membership_df: pd.DataFrame,
        fundamentals_df: pd.DataFrame,
    ):
        self.ohlcv = ohlcv_df.sort_values("trade_date").copy()
        self.membership = membership_df.copy()
        self.fundamentals = fundamentals_df.sort_values("announce_date").copy()

    def get_tradable_universe(self, as_of_date: str, index_name: str) -> list[str]:
        m = self.membership
        active = m[
            (m["index_name"] == index_name)
            & (m["entry_date"] <= as_of_date)
            & (m["exit_date"].isna() | (m["exit_date"] >= as_of_date))
        ]
        return sorted(active["security_id"].unique().tolist())

    def get_pit_snapshot(self, as_of_date: str, index_name: str) -> pd.DataFrame:
        universe = self.get_tradable_universe(as_of_date, index_name)
        hist_prices = self.ohlcv[
            (self.ohlcv["trade_date"] <= as_of_date)
            & (self.ohlcv["security_id"].isin(universe))
        ].copy()

        known_fund = (
            self.fundamentals[self.fundamentals["announce_date"] <= as_of_date]
            .groupby("security_id")
            .last()
            .reset_index()
        )
        return hist_prices.merge(
            known_fund[["security_id", "roe", "pe_ratio"]],
            on="security_id",
            how="left",
        )


import numpy as np
import pandas as pd

def run_vectorized_backtest(
    close_matrix: pd.DataFrame,
    target_weights: pd.DataFrame,
    cost_bps_per_leg: float = 25.0,
) -> tuple[pd.DataFrame, dict[str, float]]:
    asset_returns = close_matrix.pct_change().fillna(0.0)
    exec_weights = target_weights.shift(1).fillna(0.0)

    turnover = (exec_weights - exec_weights.shift(1).fillna(0.0)).abs().sum(axis=1)
    cost_rate = cost_bps_per_leg / 10_000.0
    transaction_costs = turnover * cost_rate

    gross_port_ret = (exec_weights * asset_returns).sum(axis=1)
    net_port_ret = gross_port_ret - transaction_costs
    equity_curve = (1.0 + net_port_ret).cumprod()
    running_max = equity_curve.cummax()
    drawdown = (equity_curve / running_max) - 1.0

    n_years = max(len(net_port_ret) / 245.0, 1e-6)
    cagr = float(equity_curve.iloc[-1] ** (1.0 / n_years) - 1.0)
    ann_vol = float(net_port_ret.std(ddof=1) * np.sqrt(245.0))
    sharpe = cagr / ann_vol if ann_vol > 0 else 0.0

    summary = {
        "cagr_pct": round(cagr * 100, 2),
        "sharpe_ratio": round(sharpe, 2),
        "max_drawdown_pct": round(float(drawdown.min()) * 100, 2),
        "avg_daily_turnover_pct": round(float(turnover.mean()) * 100, 2),
    }
    report_df = pd.DataFrame({
        "gross_ret": gross_port_ret,
        "cost": transaction_costs,
        "net_ret": net_port_ret,
        "equity": equity_curve,
        "drawdown": drawdown,
    })
    return report_df, summary


import pandas as pd

class EventDrivenBacktestEngine:
    def __init__(
        self,
        initial_cash: float = 1_000_000.0,
        comm_rate: float = 0.00168,
        slippage_rate: float = 0.0010,
        lot_size: int = 100,
    ):
        self.cash = initial_cash
        self.comm_rate = comm_rate
        self.slip = slippage_rate
        self.lot_size = lot_size
        self.positions: dict[str, int] = {}
        self.pending_orders: list[dict] = []
        self.equity_history: list[dict] = []

    def submit_order(self, ticker: str, side: str, target_budget: float, ref_price: float) -> None:
        raw_shares = int(target_budget // (ref_price * self.lot_size)) * self.lot_size
        if side == "BUY" and raw_shares >= self.lot_size:
            self.pending_orders.append({"ticker": ticker, "side": "BUY", "shares": raw_shares})
        elif side == "SELL" and self.positions.get(ticker, 0) > 0:
            self.pending_orders.append(
                {"ticker": ticker, "side": "SELL", "shares": self.positions[ticker]}
            )

    def step_bar(self, trade_date: str, bar_Snapshot: dict[str, dict]) -> None:
        remaining_orders = []
        for order in self.pending_orders:
            tkr, side, qty = order["ticker"], order["side"], order["shares"]
            bar = bar_Snapshot.get(tkr)
            if not bar or not bar.get("is_tradable", True):
                remaining_orders.append(order)
                continue
            if side == "BUY":
                fill_px = bar["open"] * (1.0 + self.slip)
                total_cost = qty * fill_px * (1.0 + self.comm_rate)
                if self.cash >= total_cost:
                    self.cash -= total_cost
                    self.positions[tkr] = self.positions.get(tkr, 0) + qty
            elif side == "SELL":
                fill_px = bar["open"] * (1.0 - self.slip)
                net_proceeds = qty * fill_px * (1.0 - self.comm_rate)
                self.cash += net_proceeds
                self.positions[tkr] = 0
        self.pending_orders = remaining_orders

        mkt_value = sum(
            qty * bar_Snapshot[t]["close"]
            for t, qty in self.positions.items()
            if qty > 0 and t in bar_Snapshot
        )
        self.equity_history.append({
            "trade_date": trade_date,
            "cash": round(self.cash, 2),
            "market_value": round(mkt_value, 2),
            "total_equity": round(self.cash + mkt_value, 2),
        })


import numpy as np
import pandas as pd

def evaluate_parameter_plateau(
    sharpe_grid: pd.DataFrame, penalty_lambda: float = 1.0
) -> tuple[pd.DataFrame, dict[str, float]]:
    mat = sharpe_grid.to_numpy(dtype=float)
    rows, cols = mat.shape
    plateau_mat = np.full_like(mat, np.nan)

    for r in range(1, rows - 1):
        for c in range(1, cols - 1):
            patch = mat[r - 1 : r + 2, c - 1 : c + 2]
            nbr_mean = float(np.mean(patch))
            nbr_std = float(np.std(patch, ddof=1))
            plateau_mat[r, c] = nbr_mean - (penalty_lambda * nbr_std)

    plateau_df = pd.DataFrame(
        plateau_mat, index=sharpe_grid.index, columns=sharpe_grid.columns
    )
    best_flat_idx = int(np.nanargmax(plateau_mat))
    best_r, best_c = np.unravel_index(best_flat_idx, mat.shape)

    best_info = {
        "best_param_row": sharpe_grid.index[best_r],
        "best_param_col": sharpe_grid.columns[best_c],
        "center_sharpe": round(float(mat[best_r, best_c]), 3),
        "plateau_score": round(float(plateau_mat[best_r, best_c]), 3),
    }
    return plateau_df, best_info


import numpy as np
import pandas as pd

def run_rolling_walk_forward(
    close_series: pd.Series,
    candidate_windows: list[int],
    is_bars: int = 500,
    oos_bars: int = 125,
    min_is_ann_ret: float = 0.02,
) -> tuple[pd.DataFrame, float]:
    ret_series = close_series.pct_change().fillna(0.0)
    records = []
    start_idx = 0

    while start_idx + is_bars + oos_bars <= len(close_series):
        is_end = start_idx + is_bars
        oos_end = is_end + oos_bars
        best_w, best_is_ret = candidate_windows[0], -1e9

        for w in candidate_windows:
            sig = (close_series > close_series.rolling(w).mean()).astype(float).shift(1)
            is_slice_ret = (sig.iloc[start_idx:is_end] * ret_series.iloc[start_idx:is_end]).mean() * 245
            if is_slice_ret > best_is_ret:
                best_is_ret, best_w = float(is_slice_ret), w

        sig_best = (close_series > close_series.rolling(best_w).mean()).astype(float).shift(1)
        oos_slice_ret = float(
            (sig_best.iloc[is_end:oos_end] * ret_series.iloc[is_end:oos_end]).mean() * 245
        )
        # ป้องกันกรณี IS <= 0 หรือใกล้ศูนย์ (เช่น < 2% ต่อปี) ไม่ให้เกิดตัวหารติดลบหรือระเบิดค่าเทียม
        if best_is_ret < min_is_ann_ret:
            wfe = 0.0
            window_status = "INVALID_IS_EDGE"
        else:
            wfe = max(-100.0, min(200.0, (oos_slice_ret / best_is_ret) * 100.0))
            window_status = "VALID"

        records.append({
            "window_start": int(start_idx),
            "best_lookback": int(best_w),
            "is_ann_ret_pct": round(best_is_ret * 100, 2),
            "oos_ann_ret_pct": round(oos_slice_ret * 100, 2),
            "wfe_pct": round(wfe, 1),
            "wfe_status": window_status,
        })
        start_idx += oos_bars

    wf_df = pd.DataFrame(records)
    avg_wfe = round(float(wf_df["wfe_pct"].mean()), 1) if not wf_df.empty else 0.0
    return wf_df, avg_wfe


import numpy as np

def run_monte_carlo_stress_test(
    trade_returns: np.ndarray,
    n_simulations: int = 10_000,
    shock_bps_std: float = 15.0,
    ruin_threshold: float = 0.30,
    seed: int = 42,
) -> dict[str, float]:
    rng = np.random.default_rng(seed)
    n_trades = len(trade_returns)

    sampled = rng.choice(trade_returns, size=(n_simulations, n_trades), replace=True)
    shocks = np.abs(rng.normal(0.0, shock_bps_std / 10_000.0, size=(n_simulations, n_trades)))
    net_paths = np.clip(sampled - shocks, -0.95, None)

    equity_paths = np.cumprod(1.0 + net_paths, axis=1)
    equity_with_start = np.hstack([np.ones((n_simulations, 1)), equity_paths])
    running_peaks = np.maximum.accumulate(equity_with_start, axis=1)
    drawdowns = (equity_with_start / running_peaks) - 1.0
    max_dd_per_sim = np.min(drawdowns, axis=1)

    abs_dd = np.abs(max_dd_per_sim)
    ruin_prob = float(np.mean(abs_dd >= ruin_threshold))

    return {
        "mdd_p50_pct": round(float(np.percentile(abs_dd, 50)) * 100, 2),
        "mdd_p95_pct": round(float(np.percentile(abs_dd, 95)) * 100, 2),
        "mdd_p99_pct": round(float(np.percentile(abs_dd, 99)) * 100, 2),
        "prob_of_ruin_pct": round(ruin_prob * 100, 2),
        "median_terminal_multiple": round(float(np.median(equity_paths[:, -1])), 2),
    }


import numpy as np
import pandas as pd

def run_head_to_head_benchmark(n_days: int = 2450, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    true_ret = rng.normal(loc=0.00065, scale=0.014, size=n_days)
    true_close = 100.0 * np.cumprod(1.0 + true_ret)

    raw_close = true_close.copy()
    split_day = n_days // 2
    raw_close[split_day:] = raw_close[split_day:] / 5.0  # แตกพาร์ 5:1 ณ กึ่งกลางช่วงเวลา

    s_true = pd.Series(true_close)
    s_raw = pd.Series(raw_close)

    # โหมดที่ 1: Naive Dirty Backtest (ไม่ปรับพาร์ + ไม่ shift(1) + ไม่คิดค่าคอมฯ)
    naive_sig = (s_raw > s_raw.rolling(20).mean()).astype(float)
    naive_ret = naive_sig * s_raw.pct_change().fillna(0.0)

    # โหมดที่ 2: Clean Realistic Lab (ปรับพาร์ครบ + shift(1) + หักต้นทุน 25 bps)
    clean_sig = (s_true > s_true.rolling(20).mean()).astype(float).shift(1).fillna(0.0)
    turnover = (clean_sig - clean_sig.shift(1).fillna(0.0)).abs()
    clean_ret = (clean_sig * s_true.pct_change().fillna(0.0)) - (turnover * 0.0025)

    results = []
    for name, r in [("Naive_Dirty_CSV", naive_ret), ("Clean_PIT_Lab", clean_ret)]:
        eq = (1.0 + r).cumprod()
        dd = (eq / eq.cummax()) - 1.0
        cagr = float(eq.iloc[-1] ** (245.0 / n_days) - 1.0)
        vol = float(r.std(ddof=1) * np.sqrt(245.0))
        results.append({
            "mode": name,
            "cagr_pct": round(cagr * 100, 2),
            "sharpe": round(cagr / vol, 2) if vol > 0 else 0.0,
            "max_dd_pct": round(float(dd.min()) * 100, 2),
        })
    return pd.DataFrame(results)



# ==============================================================================
# [LAST-MILE BRIDGE] ดึงข้อมูลหุ้นไทยจริง + ประวัติปันผล (XD) และแตกพาร์ (Split) จาก yfinance
# ==============================================================================
def fetch_thai_stocks_and_corporate_actions(
    symbols: list[str] = ["PTT.BK", "ADVANC.BK", "AOT.BK", "BDMS.BK", "CPALL.BK", "SCB.BK"],
    period: str = "2y",
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    ดึงข้อมูล OHLCV รายวันแบบยังไม่ปรับฐาน (Unadjusted) พร้อมตารางวันแตกพาร์ (Split)
    และวันขึ้นเครื่องหมายปันผล (XD) จาก Yahoo Finance (yfinance) เพื่อส่งเข้าท่อ Volume 3 ได้ทันที
    (หากไม่ได้ต่ออินเทอร์เน็ตหรือไม่ได้ติดตั้ง yfinance จะสร้างข้อมูลจำลองมาตรฐานแทนอัตโนมัติ)
    """
    try:
        import yfinance as yf
        ohlcv_rows, split_rows, div_rows = [], [], []
        for sym in symbols:
            clean_sym = sym.replace(".BK", "")
            tk = yf.Ticker(sym)
            hist = tk.history(period=period, auto_adjust=False)
            if hist.empty:
                raise RuntimeError(f"Empty history for {sym}")
            hist = hist.reset_index()
            for _, r in hist.iterrows():
                dt_str = str(pd.to_datetime(r["Date"]).date())
                ohlcv_rows.append({
                    "trade_date": dt_str, "date": dt_str, "symbol": clean_sym,
                    "open": float(r["Open"]), "high": float(r["High"]),
                    "low": float(r["Low"]), "close": float(r["Close"]),
                    "volume": float(r["Volume"]),
                })
                if float(r.get("Stock Splits", 0.0)) > 0:
                    ratio = float(r["Stock Splits"])
                    split_rows.append({
                        "ex_date": dt_str, "symbol": clean_sym, "action_type": "SPLIT",
                        "old_par": ratio, "new_par": 1.0,
                        "xr_old_shares": 0.0, "xr_new_shares": 0.0, "xr_sub_price": 0.0,
                    })
                if float(r.get("Dividends", 0.0)) > 0:
                    div_rows.append({
                        "xd_date": dt_str, "symbol": clean_sym, "dps": float(r["Dividends"]),
                    })
        return pd.DataFrame(ohlcv_rows), pd.DataFrame(split_rows), pd.DataFrame(div_rows)
    except Exception:
        # Offline fallback so the script always runs out-of-the-box anywhere
        dates = pd.bdate_range("2025-01-02", periods=60).strftime("%Y-%m-%d")
        ohlcv_rows = [
            {"trade_date": d, "date": d, "symbol": "PTT", "open": 34.0, "high": 34.75, "low": 33.75, "close": 34.25, "volume": 45_000_000.0}
            for d in dates
        ]
        split_df = pd.DataFrame(columns=["ex_date", "symbol", "action_type", "old_par", "new_par", "xr_old_shares", "xr_new_shares", "xr_sub_price"])
        div_df = pd.DataFrame([{"xd_date": dates[20], "symbol": "PTT", "dps": 1.20}])
        return pd.DataFrame(ohlcv_rows), split_df, div_df
