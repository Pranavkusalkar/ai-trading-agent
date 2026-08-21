"""
Walk-Forward Tester (Spec section 25)
Prevents overfitting by testing on out-of-sample data.

Rolling walk-forward example:
  Window 1: Train 2023 → Validate 2024-H1 → OOS 2024-H2
  Window 2: Train 2023+2024-H1 → Validate 2024-H2 → OOS 2025-H1
  ...

Usage:
    wft    = WalkForwardTester("NIFTY", df, n_windows=3)
    result = wft.run()
"""

import logging
from src.backtesting.engine  import BacktestSimulator
from src.backtesting.metrics import calculate_metrics, format_report

log = logging.getLogger(__name__)


class WalkForwardTester:
    """
    Splits the dataset into overlapping train/validate/OOS windows
    and runs a backtest on each OOS period.
    Aggregates results to assess robustness across different market regimes.
    """

    def __init__(
        self,
        symbol:         str,
        df,
        n_windows:      int   = 3,
        train_pct:      float = 0.60,
        validate_pct:   float = 0.20,
        oos_pct:        float = 0.20,
        capital:        float = 500_000,
        min_confidence: float = 65.0,
        risk_pct:       float = 0.005,
    ):
        self.symbol         = symbol
        self.df             = df
        self.n_windows      = n_windows
        self.train_pct      = train_pct
        self.validate_pct   = validate_pct
        self.oos_pct        = oos_pct
        self.capital        = capital
        self.min_confidence = min_confidence
        self.risk_pct       = risk_pct

    def run(self) -> dict:
        """Run all walk-forward windows and return aggregated results."""
        n      = len(self.df)
        window = n // (self.n_windows + 1)
        results = []

        for w in range(self.n_windows):
            train_end    = window * (w + 1)
            validate_end = train_end    + int(window * self.validate_pct / self.oos_pct)
            oos_end      = validate_end + int(window * self.oos_pct      / self.oos_pct)
            oos_end      = min(oos_end, n)

            if oos_end - validate_end < 50:
                log.warning(f"Window {w+1}: OOS period too short, skipping")
                continue

            train_df    = self.df.iloc[:train_end]
            validate_df = self.df.iloc[train_end:validate_end]
            oos_df      = self.df.iloc[validate_end:oos_end]

            log.info(
                f"Walk-forward window {w+1}/{self.n_windows} | "
                f"train={len(train_df)} validate={len(validate_df)} oos={len(oos_df)} bars"
            )

            # Run backtest only on OOS data
            sim = BacktestSimulator(
                symbol         = self.symbol,
                df             = oos_df.reset_index(drop=True),
                capital        = self.capital,
                min_confidence = self.min_confidence,
                risk_pct       = self.risk_pct,
            )
            result = sim.run()
            result["window"]       = w + 1
            result["train_bars"]   = len(train_df)
            result["validate_bars"]= len(validate_df)
            result["oos_bars"]     = len(oos_df)
            results.append(result)

        return self._aggregate(results)

    def _aggregate(self, results: list[dict]) -> dict:
        if not results:
            return {"error": "No walk-forward windows completed"}

        all_trades = []
        for r in results:
            all_trades.extend(r.get("trades", []))

        agg_metrics = calculate_metrics(all_trades, self.capital)

        window_summaries = []
        for r in results:
            m = r["metrics"]
            window_summaries.append({
                "window":       r["window"],
                "oos_bars":     r["oos_bars"],
                "total_trades": m["total_trades"],
                "win_rate":     m["win_rate"],
                "net_pnl":      m["net_pnl"],
                "profit_factor": m["profit_factor"],
                "sharpe_ratio": m["sharpe_ratio"],
            })

        # Consistency score — how many windows were profitable
        profitable_windows = sum(
            1 for r in results if r["metrics"]["net_pnl"] > 0
        )
        consistency = round(profitable_windows / len(results) * 100, 1)

        return {
            "symbol":               self.symbol,
            "n_windows":            len(results),
            "profitable_windows":   profitable_windows,
            "consistency_pct":      consistency,
            "aggregate_metrics":    agg_metrics,
            "window_summaries":     window_summaries,
            "aggregate_report":     format_report(agg_metrics, self.symbol, "Walk-Forward Aggregate"),
        }
