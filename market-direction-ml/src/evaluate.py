import argparse
import json

import numpy as np
from sklearn.metrics import (accuracy_score, balanced_accuracy_score, brier_score_loss,
                             confusion_matrix, f1_score, log_loss, matthews_corrcoef,
                             precision_recall_fscore_support, roc_auc_score)


def metrics(y, probability, threshold=.5):
    y = np.asarray(y, dtype=int)
    p = np.asarray(probability, dtype=float)
    if not len(y):
        return {"n": 0, "status": "INSUFFICIENT_DATA"}
    if len(y) != len(p) or not np.isfinite(p).all() or ((p < 0) | (p > 1)).any():
        raise ValueError("概率长度或取值非法")
    prediction = (p >= .5).astype(int)
    keep = np.maximum(p, 1 - p) >= threshold
    precision, recall, _, support = precision_recall_fscore_support(y, prediction, labels=[0, 1], zero_division=0)
    result = {"n": len(y), "status": "OK", "accuracy": float(accuracy_score(y, prediction)),
              "balanced_accuracy": float(balanced_accuracy_score(y, prediction)),
              "mcc": float(matthews_corrcoef(y, prediction)), "f1": float(f1_score(y, prediction, zero_division=0)),
              "auc": float(roc_auc_score(y, p)) if len(set(y)) == 2 else None,
              "auc_note": "defined" if len(set(y)) == 2 else "single_class",
              "log_loss": float(log_loss(y, np.clip(p, 1e-8, 1 - 1e-8), labels=[0, 1])),
              "brier": float(brier_score_loss(y, p)), "signal_count": int(keep.sum()),
              "signal_coverage": float(keep.mean()),
              "signal_accuracy": float(accuracy_score(y[keep], prediction[keep])) if keep.any() else None,
              "confusion_matrix": confusion_matrix(y, prediction, labels=[0, 1]).tolist()}
    for i, name in enumerate(("down", "up")):
        result.update({f"precision_{name}": float(precision[i]), f"recall_{name}": float(recall[i]), f"support_{name}": int(support[i])})
    return result


def select_threshold(y, p, config):
    choices = []
    for threshold in config["thresholds"]:
        score = metrics(y, p, threshold)
        if score.get("signal_count", 0) >= 30 and score.get("signal_coverage", 0) >= config["minimum_signal_coverage"]:
            choices.append((score["signal_accuracy"], -threshold, threshold))
    return max(choices)[2] if choices else .5


def main():
    parser = argparse.ArgumentParser(description="解锁已冻结实验的最终历史留出，仅执行一次")
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    from .final_report import evaluate_frozen
    evaluate_frozen(args.run_id)


if __name__ == "__main__":
    main()
