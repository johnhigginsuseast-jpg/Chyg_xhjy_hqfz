import numpy as np


def boundaries(bars):
    n = len(bars)
    return {"train_end": int(n * .7), "calibration_end": int(n * .775), "test_start": int(n * .85), "end": n}


def samples_for(bars, features, labels, warmup):
    data = bars.copy()
    data["feature_ready"] = np.arange(len(data)) >= warmup
    data["feature_ready"] &= features.notna().all(axis=1)
    return data.join(labels).join(features.add_prefix("f_"))


def window(samples, start, end, cutoff):
    use = samples.bar_position.ge(start) & samples.bar_position.lt(end) & samples.feature_ready & samples.y.notna()
    use &= samples.target_available_at.lt(cutoff)
    return samples.loc[use].copy()


def walk_forward_windows(train_end, folds=5):
    edges = np.linspace(train_end // 2, train_end, folds + 1, dtype=int)
    return [(int(a), int(b)) for a, b in zip(edges[:-1], edges[1:])]


def assert_purged(training, next_start):
    if len(training) and not training.target_available_at.lt(next_start).all():
        raise ValueError("未来标签跨越下一评估边界")
