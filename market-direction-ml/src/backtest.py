import argparse
import json

import numpy as np
import pandas as pd

from .common import ROOT, period_name, write_json


def simulate(bars, predictions, costs):
    components = [float(costs[k]) for k in ("fee_bps", "half_spread_bps", "slippage_bps")]
    if not np.isfinite(components).all() or min(components) < 0 or sum(components) >= 10000:
        raise ValueError("费用组件必须有限、非负且合计小于10000bps")
    if not set(predictions.signal.unique()) <= {"up", "down", "wait"}:
        raise ValueError("模拟信号只能为up/down/wait")
    if bars.empty or predictions.empty or (bars[["open", "close"]] <= 0).any().any():
        raise ValueError("模拟需要非空预测及正价格")
    fee, friction = components[0] / 10000, sum(components[1:]) / 10000
    quotes = bars[["open_at", "available_at", "open", "close", "bar_position"]].sort_values("open_at").copy()
    signals = predictions[["prediction_timestamp", "signal"]].copy()
    signals["prediction_timestamp"] = pd.to_datetime(signals.prediction_timestamp)
    if signals.prediction_timestamp.duplicated().any():
        raise ValueError("模拟信号时间重复")
    quotes = quotes.loc[quotes.available_at.ge(signals.prediction_timestamp.min())]
    timeline = pd.merge_asof(quotes, signals.sort_values("prediction_timestamp"), left_on="open_at",
                             right_on="prediction_timestamp", direction="backward", allow_exact_matches=False)
    cash, units, entry_cash, entry_time = 1., 0., 0., None
    fills, trades, curve = [], [], []
    for row in timeline.itertuples():
        desired = row.signal == "up"
        if desired and units == 0:
            price = row.open * (1 + friction)
            entry_cash, entry_time = cash, row.open_at
            units = cash / (price * (1 + fee))
            charged = units * price * fee
            fills.append({"timestamp": row.open_at, "signal_timestamp": row.prediction_timestamp, "side": "buy",
                          "quote_open": row.open, "fill_price": price, "units": units, "fee": charged})
            cash = 0.
        elif not desired and units > 0:
            price = row.open * (1 - friction)
            charged = units * price * fee
            cash = units * price - charged
            fills.append({"timestamp": row.open_at, "signal_timestamp": row.prediction_timestamp, "side": "sell",
                          "quote_open": row.open, "fill_price": price, "units": units, "fee": charged})
            trades.append({"entry_time": entry_time, "exit_time": row.open_at, "pnl": cash - entry_cash,
                           "return": cash / entry_cash - 1, "entry_capital": entry_cash, "exit_capital": cash})
            units = 0.
        curve.append({"timestamp": row.available_at, "equity": cash + units * row.close, "position_units": units,
                      "cash": cash, "mark_close": row.close})
    if not curve:
        raise ValueError("没有可用于模拟的时段")
    equity = pd.DataFrame(curve)
    fills = pd.DataFrame(fills, columns=["timestamp", "signal_timestamp", "side", "quote_open", "fill_price", "units", "fee"])
    trades = pd.DataFrame(trades, columns=["entry_time", "exit_time", "pnl", "return", "entry_capital", "exit_capital"])
    if len(fills) and not fills.timestamp.gt(fills.signal_timestamp).all():
        raise ValueError("成交不能早于或等于信号可用时刻")
    values = np.r_[1., equity.equity.to_numpy()]
    drawdown = values / np.maximum.accumulate(values) - 1
    win, loss = trades.loc[trades["return"].gt(0)], trades.loc[trades["return"].lt(0)]
    avg_win = float(win["return"].mean()) if len(win) else None
    avg_loss = float(loss["return"].mean()) if len(loss) else None
    result = {"trade_count": len(trades), "fill_count": len(fills), "win_rate": float(trades["return"].gt(0).mean()) if len(trades) else None,
              "average_win": avg_win, "average_loss": avg_loss,
              "payoff_ratio": avg_win / abs(avg_loss) if avg_win is not None and avg_loss is not None else None,
              "total_return": float(values[-1] - 1), "max_drawdown": float(-drawdown.min()),
              "profit_factor": float(win.pnl.sum() / -loss.pnl.sum()) if len(loss) else None,
              "profit_factor_note": "defined" if len(loss) else "undefined_no_realized_losses",
              "open_position_units": float(units), "total_fees": float(fills.fee.sum()),
              "terminal_equity": float(values[-1]), "terminal_policy": "mark_to_market_without_fictitious_exit_fill"}
    return result, equity, fills, trades


def run_backtest(run_id):
    run = ROOT / "reports/evidence" / run_id
    if not (run / "final-test-completed.json").exists():
        raise ValueError("先完成冻结最终方向评估，再进行回测")
    config = json.loads((run / "config.json").read_text(encoding="utf-8"))
    if config["allow_short"]:
        raise ValueError("未核实做空资格，模拟仅支持做多")
    frozen = json.loads((run / "frozen.json").read_text(encoding="utf-8"))
    decisions = json.loads((run / "decisions.json").read_text(encoding="utf-8"))
    selected = {(r["period"], r["horizon"]): r["model"] for r in frozen["champions"]}
    output = run / "backtest"
    output.mkdir(exist_ok=False)
    results, selected_curves = [], {}
    for period in config["periods"]:
        bars = pd.read_parquet(ROOT / f"data/cleaned/{period_name(period)}.parquet")
        for h in config["horizons"]:
            case = [d for d in decisions if d["period"] == period and d["horizon"] == h and d["status"] == "OK"]
            if (period, h) not in selected:
                selected[(period, h)] = max(case, key=lambda d: d["validation"].get("accuracy", -1))["model"]
            for decision in case:
                name = decision["model"]
                predictions = pd.read_csv(run / f"predictions/{period_name(period)}-h{h}-{name}.csv")
                benchmark = predictions.copy()
                benchmark["signal"] = "up"
                for costs in config["fee_scenarios"]:
                    result, equity, fills, trades = simulate(bars, predictions, costs)
                    hold, hold_equity, _, _ = simulate(bars, benchmark, costs)
                    results.append(dict(period=period, horizon=h, model=name, scenario=costs["name"], **costs,
                                        buy_hold_return=hold["total_return"], buy_hold_max_drawdown=hold["max_drawdown"],
                                        excess_return=result["total_return"] - hold["total_return"],
                                        selected_by_validation=name == selected[(period, h)], **result))
                    if name == selected[(period, h)]:
                        stem = f"{period_name(period)}-h{h}-{name}-{costs['name']}"
                        equity.to_csv(output / f"{stem}-equity.csv", index=False)
                        fills.to_csv(output / f"{stem}-fills.csv", index=False)
                        trades.to_csv(output / f"{stem}-trades.csv", index=False)
                        if costs["name"] == "10bps":
                            selected_curves[(period, h)] = (name, equity, hold_equity)
            print(f"BACKTEST {period_name(period)} h={h}: {len(case)} models, {len(config['fee_scenarios'])} costs", flush=True)
    table = pd.DataFrame(results)
    table.to_csv(ROOT / "reports/backtest_comparison.csv", index=False)
    from .final_report import plt
    import matplotlib.dates as mdates
    for (period, h), (name, equity, hold) in selected_curves.items():
        fig, ax = plt.subplots(figsize=(10, 4), constrained_layout=True)
        ax.plot(pd.to_datetime(equity.timestamp), equity.equity, label=f"Validation-selected {name}")
        ax.plot(pd.to_datetime(hold.timestamp), hold.equity, label="Buy and hold")
        ax.set(title=f"{period_name(period)} h={h}; 10bps nominal one-way costs", ylabel="Normalized equity")
        locator = mdates.AutoDateLocator(minticks=3, maxticks=6)
        ax.xaxis.set_major_locator(locator)
        ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(locator))
        ax.legend()
        fig.savefig(ROOT / f"reports/figures/backtest-{period_name(period)}-h{h}.png", dpi=120)
        plt.close(fig)
    chosen = table[table.selected_by_validation]
    lines = ["# 模拟回测报告", "", "仅用于研究，不连接账户或真实委托。方向评估完成后才单独开发和运行本模块。",
             "模型/阈值保持冻结；全部已产生预测的模型都在同一规则下模拟，不按测试收益挑选模型或跨度。", "",
             "## 成交与费用假设", "", "信号在完整K线结束后可用；成交使用严格晚于信号时刻的下一条真实记录的开盘，不用已结束根收盘无条件成交。",
             "由于只有OHLC，下一桶开盘与当前收盘的时间边界相同时不能假设赶上该开盘；采用更保守的后续可用开盘，因此h=1预测的目标可能在成交前结束。方向命中不等于可获利。",
             "每次按当时已知的最新信号持有一个做多仓位：up买入/持有，down或wait退出/空仓，无重叠资金。规则跳过根不产生输入或预测，但其真实行情可用于既有信号的执行和权益估值。",
             "初始资金归一为1，允许模拟分数数量；不能视为平台真实合约/最小手数已验证。持仓末尾仅按最后完整根收盘估值，不伪造成交；交易胜率只统计已平仓交易，期末未平仓单列。",
             "手续费按成交金额双边计，半点差+滑点调整买卖执行价。0/5/10/20bps是用户未提供真实成本时采用的假设组件之和，乘法计费后的有效成本略有不同。默认不做空。",
             "买入持有使用相同起始信号可用时刻、可成交开盘、资金与费用；所有权益估值包含真实规则跳过根，最大回撤不因跳过预测而隐藏。", "",
             "| 周期 | h | 验证选中模型 | 场景 | 平仓数 | 胜率 | 总收益 | 最大回撤 | 买入持有 |", "|---|---:|---|---|---:|---:|---:|---:|---:|"]
    for r in chosen.itertuples():
        win = "无已平仓交易" if pd.isna(r.win_rate) else f"{r.win_rate:.4f}"
        lines.append(f"| {period_name(r.period)} | {r.horizon} | {r.model} | {r.scenario} | {r.trade_count} | {win} | {r.total_return:.4f} | {r.max_drawdown:.4f} | {r.buy_hold_return:.4f} |")
    lines += ["", "全部模型费用敏感性、均盈亏/盈亏比/PF/费用/未平仓见backtest_comparison.csv；验证选中组合的逐成交、逐交易及权益曲线在实验backtest目录。",
              "无已平仓/无亏损时相应指标为未定义而非伪造零或无限优良表现。费用可能改变持仓资金与交易序列的金额，收益与命中率不是同一指标。",
              "来源真实性、时区、交易日历、真实成本、实际流动性/可做空及实时执行均未认证。当前数据未验证出稳定可用的预测信号。"]
    (ROOT / "reports/backtest_report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    write_json(run / "backtest-completed.json", {"status": "COMPLETED", "cases": len(results), "real_trading": False})


def main():
    parser = argparse.ArgumentParser(description="独立的只做多模拟，下一严格可成交开盘，支持费用/点差/滑点")
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    run_backtest(args.run_id)


if __name__ == "__main__":
    main()
