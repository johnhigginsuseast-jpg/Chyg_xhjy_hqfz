import numpy as np
import pandas as pd


def filter_bars(bars, period, state=None):
    state = dict(state or {"last_close": None, "run_direction": 0, "run_length": 0, "skip_remaining": 0})
    accepted, ledger = [], []
    for i, row in bars.iterrows():
        status = "accepted"
        if period == 1 and state["skip_remaining"]:
            state["skip_remaining"] -= 1
            status = "rule_skip"
        else:
            close = float(row["close"])
            last = state["last_close"]
            direction = 0 if last is None else int(np.sign(close - last))
            state["run_length"] = state["run_length"] + 1 if direction and direction == state["run_direction"] else int(direction != 0)
            state["run_direction"] = direction
            state["last_close"] = close
            accepted.append(i)
            if period == 1 and state["run_length"] == 3:
                state.update(skip_remaining=2, run_length=0, run_direction=0)
        ledger.append({"bar_position": int(row["bar_position"]), "available_at": row["available_at"], "status": status})
    return bars.loc[accepted].reset_index(drop=True), pd.DataFrame(ledger), state


def make_labels(bars, horizon, known_until=None):
    if horizon < 1:
        raise ValueError("预测跨度必须为正整数")
    target = bars["close"].shift(-horizon)
    target_time = bars["available_at"].shift(-horizon)
    target_position = bars["bar_position"].shift(-horizon)
    if known_until is not None:
        target = target.where(target_time < pd.Timestamp(known_until))
    ret = target.div(bars["close"]).sub(1)
    label = pd.Series(np.nan, index=bars.index)
    label.loc[ret.gt(0)] = 1
    label.loc[ret.lt(0)] = 0
    status = pd.Series("PENDING", index=bars.index)
    status.loc[ret.eq(0)] = "FLAT"
    status.loc[ret.gt(0)] = "UP"
    status.loc[ret.lt(0)] = "DOWN"
    return pd.DataFrame({"y": label, "ret": ret, "label_status": status,
                         "target_available_at": target_time, "target_position": target_position})
