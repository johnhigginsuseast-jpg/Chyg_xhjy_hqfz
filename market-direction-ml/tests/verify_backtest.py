"""Recompute detailed backtest ledgers and check all scenario summaries."""
import argparse
import json

import numpy as np
import pandas as pd

from src.common import ROOT, period_name, write_json


def verify(run_id):
    run = ROOT / "reports/evidence" / run_id
    summary = pd.read_csv(ROOT / "reports/backtest_comparison.csv")
    config = json.loads((run / "config.json").read_text(encoding="utf-8"))
    assert len(summary) == 960 and summary.scenario.nunique() == 4
    checks = []
    for row in summary[summary.selected_by_validation].itertuples():
        stem = f"{period_name(row.period)}-h{row.horizon}-{row.model}-{row.scenario}"
        equity = pd.read_csv(run / f"backtest/{stem}-equity.csv")
        fills = pd.read_csv(run / f"backtest/{stem}-fills.csv")
        trades = pd.read_csv(run / f"backtest/{stem}-trades.csv")
        np.testing.assert_allclose(equity.equity, equity.cash + equity.position_units * equity.mark_close, atol=1e-10, rtol=0)
        assert ((equity.cash == 0) | (equity.position_units == 0)).all()
        if len(fills):
            assert (pd.to_datetime(fills.timestamp) > pd.to_datetime(fills.signal_timestamp)).all()
            assert fills.side.tolist() == ["buy" if i % 2 == 0 else "sell" for i in range(len(fills))]
        fee = row.fee_bps / 10000
        friction = (row.half_spread_bps + row.slippage_bps) / 10000
        for fill in fills.itertuples():
            expected_price = fill.quote_open * (1 + friction if fill.side == "buy" else 1 - friction)
            assert abs(fill.fill_price - expected_price) < 1e-9
            assert abs(fill.fee - fill.fill_price * fill.units * fee) < 1e-10
        if len(trades):
            np.testing.assert_allclose(trades["return"], trades.exit_capital / trades.entry_capital - 1, atol=1e-12, rtol=0)
            np.testing.assert_allclose(trades.pnl, trades.exit_capital - trades.entry_capital, atol=1e-12, rtol=0)
            assert abs(row.win_rate - trades["return"].gt(0).mean()) < 1e-12
            losses = trades.pnl[trades.pnl < 0]
            if len(losses):
                pf = trades.pnl[trades.pnl > 0].sum() / -losses.sum()
                assert abs(row.profit_factor - pf) < 1e-9
            else:
                assert pd.isna(row.profit_factor)
        else:
            assert pd.isna(row.win_rate)
        values = np.r_[1., equity.equity.to_numpy()]
        drawdown = 1 - values / np.maximum.accumulate(values)
        assert abs(row.total_return - (values[-1] - 1)) < 1e-12
        assert abs(row.max_drawdown - drawdown.max()) < 1e-12
        assert row.trade_count == len(trades) and row.fill_count == len(fills)
        assert abs(row.total_fees - fills.fee.sum()) < 1e-10
        checks.append({"period": row.period, "horizon": row.horizon, "model": row.model, "scenario": row.scenario,
                       "fills": len(fills), "trades": len(trades), "status": "MATCH"})
    for _, group in summary.groupby(["period", "horizon", "model"]):
        ordered = group.set_index("scenario").loc[[r["name"] for r in config["fee_scenarios"]]]
        assert (ordered.total_return.diff().dropna() <= 1e-12).all()
    result = {"status": "PASS", "summary_cases": len(summary), "detailed_cases": len(checks),
              "strict_after_signal": True, "fees_and_equity_recomputed": True,
              "fee_sensitivity_monotone": True, "checks": checks}
    write_json(run / "independent-backtest-verification.json", result)
    print(json.dumps({k: result[k] for k in ("status", "summary_cases", "detailed_cases", "fee_sensitivity_monotone")}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    verify(parser.parse_args().run_id)
