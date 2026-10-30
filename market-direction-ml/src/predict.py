import argparse
import json
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from .common import ROOT, load_config, sha256, write_json
from .data_loader import canonicalize, load_data
from .features import make_features
from .labels import filter_bars


def baseline_probability(data, name):
    if name == "always_up": return np.ones(len(data))
    if name == "always_down": return np.zeros(len(data))
    col = "f_return_1" if name == "previous_direction" else "f_return_5"
    return data[col].ge(0).to_numpy(dtype=float)


def model_probability(bundle, data, calibrated=True):
    p = bundle["estimator"].predict_proba(data[bundle["feature_columns"]])[:, 1]
    if calibrated and bundle.get("calibrator") is not None:
        logit = np.log(np.clip(p, 1e-6, 1 - 1e-6) / np.clip(1 - p, 1e-6, 1))
        p = bundle["calibrator"].predict_proba(logit.reshape(-1, 1))[:, 1]
    return np.asarray(p)


def load_bundle(model_path):
    path = Path(model_path).resolve()
    if not path.is_relative_to((ROOT / "models").resolve()):
        raise ValueError("仅加载本工程models内的可信模型")
    meta_path = path.with_suffix(".json")
    if not meta_path.exists():
        raise ValueError("模型缺少可信元数据")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if sha256(path) != meta["sha256"]:
        raise ValueError("模型文件校验失败")
    return joblib.load(path)


def predict_history(model_path, input_path, as_of, source_identity, output=None, minute_reference=None):
    bundle = load_bundle(model_path)
    if source_identity != bundle["source_identity"]:
        raise ValueError("输入来源与模型不一致")
    period = bundle["period"]
    raw = load_data(input_path)
    minute = load_data(minute_reference) if minute_reference else None
    bars, _ = canonicalize(raw, period, minute)
    as_of = pd.Timestamp(as_of)
    if bars.available_at.gt(as_of).any():
        raise ValueError("输入包含尚未完成K线；请移除后再预测")
    if period and len(bars) > 2:
        minute_diffs = bars.available_at.diff().dt.total_seconds().div(60)
        if minute_diffs.mode().iloc[0] != period:
            raise ValueError("输入K线周期与模型不一致")
    if period == 0 and not raw.timestamp.eq(raw.timestamp.dt.normalize()).all():
        raise ValueError("日线输入应使用原始交易日日期标签")
    kept, ledger, state = filter_bars(bars, period)
    if ledger.status.iloc[-1] == "rule_skip":
        result = {"status": "RULE_SKIP", "latest_complete_bar": str(bars.available_at.iloc[-1]), "rule_state": state}
    else:
        features = make_features(kept).add_prefix("f_")
        if len(kept) <= bundle["warmup"] or features.iloc[-1].isna().any():
            raise ValueError("完整历史不足以构造模型特征")
        p = float(model_probability(bundle, features.iloc[[-1]])[0])
        direction = "up" if p >= .5 else "down"
        confidence = max(p, 1 - p)
        result = {"status": "PREDICTED", "p_up": p, "p_down": 1 - p,
                  "predicted_direction": direction, "confidence": confidence,
                  "signal": direction if confidence >= bundle["threshold"] else "wait",
                  "prediction_horizon": bundle["horizon"], "prediction_timestamp": str(kept.available_at.iloc[-1]),
                  "model_version": bundle["model_version"], "latest_complete_bar": str(bars.available_at.iloc[-1]),
                  "base_close": float(kept.close.iloc[-1]), "source_identity": source_identity,
                  "research_only": True, "rule_state": state,
                  "note": "target time is resolved by future effective bars; no account/trading action"}
    if output:
        output = Path(output).resolve()
        if not output.is_relative_to(ROOT):
            raise ValueError("预测输出必须在本工程内")
        write_json(output, result)
    return result


def main():
    parser = argparse.ArgumentParser(description="完整历史追加后预测；完整重放确保三连状态跨重启一致")
    parser.add_argument("--model", required=True)
    parser.add_argument("--input", required=True)
    parser.add_argument("--as-of", required=True, help="原生时间；不允许输入尚未完成根")
    parser.add_argument("--source-identity", required=True)
    parser.add_argument("--minute-reference")
    parser.add_argument("--output")
    args = parser.parse_args()
    try:
        result = predict_history(args.model, args.input, args.as_of, args.source_identity, args.output, args.minute_reference)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    except (ValueError, OSError, KeyError) as exc:
        parser.exit(2, f"预测失败: {exc}\n")


if __name__ == "__main__":
    main()
