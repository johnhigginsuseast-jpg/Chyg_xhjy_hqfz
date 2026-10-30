"""Redraw the frozen numerical results with legible date ticks; no model changes."""
import json

import pandas as pd

from src.backtest import simulate
from src.common import ROOT, period_name, sha256, write_json
from src.final_report import diagnostic_figure, plt
import matplotlib.dates as mdates


def main():
    run = ROOT / "reports/evidence/study-20261028-v1"
    frozen = json.loads((run / "frozen.json").read_text(encoding="utf-8"))
    repair = json.loads((run / "report-repair.json").read_text(encoding="utf-8"))
    for entry in repair["repaired_files"]:
        assert sha256(ROOT / entry["file"]) == entry["after_sha256"]
    paths = [ROOT / p for p in json.loads((run / "prediction-files.json").read_text(encoding="utf-8"))]
    count = 0
    for champion in frozen["champions"]:
        period, h, selected = champion["period"], champion["horizon"], champion["model"]
        prefix = f"{period_name(period)}-h{h}-"
        predictions = {p.stem[len(prefix):]: pd.read_csv(p) for p in paths if p.name.startswith(prefix)}
        diagnostic_figure(predictions, selected, ROOT / f"reports/figures/{period_name(period)}-h{h}.png")
        count += 1
    summary = pd.read_csv(ROOT / "reports/backtest_comparison.csv")
    config = json.loads((run / "config.json").read_text(encoding="utf-8"))
    costs = next(c for c in config["fee_scenarios"] if c["name"] == "10bps")
    for row in summary[summary.selected_by_validation & summary.scenario.eq("10bps")].itertuples():
        prefix = f"{period_name(row.period)}-h{row.horizon}-{row.model}"
        equity = pd.read_csv(run / f"backtest/{prefix}-10bps-equity.csv")
        predictions = pd.read_csv(run / f"predictions/{prefix}.csv")
        predictions.signal = "up"
        bars = pd.read_parquet(ROOT / f"data/cleaned/{period_name(row.period)}.parquet")
        hold_result, hold, _, _ = simulate(bars, predictions, costs)
        assert abs(hold_result["total_return"] - row.buy_hold_return) < 1e-12
        fig, ax = plt.subplots(figsize=(10, 4), constrained_layout=True)
        ax.plot(pd.to_datetime(equity.timestamp), equity.equity, label=f"Validation-selected {row.model}")
        ax.plot(pd.to_datetime(hold.timestamp), hold.equity, label="Buy and hold")
        ax.set(title=f"{period_name(row.period)} h={row.horizon}; 10bps nominal one-way costs", ylabel="Normalized equity")
        locator = mdates.AutoDateLocator(minticks=3, maxticks=6)
        ax.xaxis.set_major_locator(locator)
        ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
        ax.legend()
        fig.savefig(ROOT / f"reports/figures/backtest-{period_name(row.period)}-h{row.horizon}.png", dpi=120)
        plt.close(fig)
        count += 1
    old = repair["new_sha256"]
    repair.setdefault("report_only_revisions", []).append({"defect": "BUG-002", "before_sha256": old,
                                                           "after_sha256": sha256(ROOT / "src/final_report.py"),
                                                           "reason": "date tick formatting only; all prediction file hashes unchanged"})
    repair["new_sha256"] = sha256(ROOT / "src/final_report.py")
    write_json(run / "report-repair.json", repair)
    write_json(run / "figure-layout-verification.json", {"status": "REDRAWN_PENDING_VISUAL_CHECK", "figures": count,
                                                        "predictions_changed": False, "models_changed": False})
    print(f"Redrawn {count} figures; numerical predictions and benchmark returns unchanged")


if __name__ == "__main__":
    main()
