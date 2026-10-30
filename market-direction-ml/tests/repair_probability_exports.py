"""BUG-001: repair derived CSV precision using unchanged frozen models, without fitting."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.common import ROOT, period_name, sha256, write_json
from src.final_report import prediction_frame
from src.predict import baseline_probability, load_bundle, model_probability
from src.train import prepared


def repair_exports(run_id):
    run = ROOT / "reports/evidence" / run_id
    frozen = json.loads((run / "frozen.json").read_text(encoding="utf-8"))
    config = json.loads((run / "config.json").read_text(encoding="utf-8"))
    decisions = json.loads((run / "decisions.json").read_text(encoding="utf-8"))
    old_source = run / "repairs/probability-export/final_report-before-repair.py.txt"
    archive = run / "repairs/probability-export/original-reports-and-predictions.zip"
    report_key = next(key for key in frozen["code_hashes"] if Path(key).as_posix() == "src/final_report.py")
    assert archive.exists() and sha256(old_source) == frozen["code_hashes"][report_key]
    assert sha256(run / "decisions.json") == frozen["decisions_hash"]
    for path, digest in frozen["code_hashes"].items():
        if path != report_key: assert sha256(ROOT / path) == digest
    for name, digest in frozen["source_hashes"].items():
        assert sha256(ROOT.parent / "2026-10-28" / name) == digest
    files, signal_changes = [], 0
    for period in config["periods"]:
        raw, kept, features, _, _ = prepared(config, period)
        mask = kept.bar_position.ge(int(len(raw) * .85))
        inputs = kept.loc[mask].join(features.loc[mask].add_prefix("f_"))
        for decision in [d for d in decisions if d["period"] == period and d["status"] == "OK"]:
            h, name = decision["horizon"], decision["model"]
            path = run / f"predictions/{period_name(period)}-h{h}-{name}.csv"
            before = sha256(path)
            old = pd.read_csv(path)
            if "model_path" in decision:
                model_path = ROOT / decision["model_path"]
                assert sha256(model_path) == decision["model_sha256"]
                bundle = load_bundle(model_path)
                probability = model_probability(bundle, inputs)
                raw_probability = model_probability(bundle, inputs, False)
            else:
                probability = baseline_probability(inputs, name)
                raw_probability = probability
            fixed = prediction_frame(old.rename(columns={"prediction_timestamp": "available_at"}), probability,
                                     raw_probability, decision["threshold"], h, old.model_version.iloc[0])
            np.testing.assert_array_equal(fixed.predicted_direction, old.predicted_direction)
            changed = int(fixed.signal.ne(old.signal).sum())
            signal_changes += changed
            assert changed == 0, "阈值边界信号发生差异，必须单独重算回测与统计"
            np.testing.assert_allclose(fixed.p_up + fixed.p_down, 1., atol=1e-12, rtol=0)
            fixed.to_csv(path, index=False)
            files.append({"file": str(path.relative_to(ROOT)), "before_sha256": before, "after_sha256": sha256(path),
                          "rows": len(fixed), "model_parameters_changed": False, "signal_changes": changed})
    result = {"defect": "BUG-001", "file": report_key,
              "original_sha256": frozen["code_hashes"][report_key], "new_sha256": sha256(ROOT / "src/final_report.py"),
              "models_or_selection_changed": False, "test_was_already_exposed": True,
              "original_outputs_archive_sha256": sha256(archive), "frozen_manifest_unchanged": True,
              "signal_changes": signal_changes, "repaired_files": files,
              "reason": "float64 CSV encoding of original frozen probabilities; no fit, threshold or selection change; original reports archived"}
    write_json(run / "report-repair.json", result)
    print(f"REPAIRED {len(files)} probability exports; directions/signals/models unchanged")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True)
    repair_exports(parser.parse_args().run_id)
