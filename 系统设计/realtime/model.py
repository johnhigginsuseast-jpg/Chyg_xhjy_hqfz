"""Reuse frozen study kernels after the caller verifies the approved source binding."""
import hashlib
import json
from pathlib import Path
import sys

from .native import SHANGHAI, local_time

ROOT = Path(__file__).resolve().parents[1]
STUDY = ROOT.parent / "market-direction-ml"
MODEL = STUDY / "models/study-20261028-v1/1min-h1-logistic.joblib"
MODEL_HASH = "d79afdbc7936dbd8692f903c37c0948de3c06c9579f671ed8bbb6f1f884b1ba7"


class StudyPredictor:
    def __init__(self):
        sys.path.insert(0, str(STUDY))
        from src.predict import load_bundle
        self.baseline = json.loads((ROOT / "docs/evidence/20261028-preflight/model-baseline-sha256.json").read_text(encoding="utf-8"))
        self.verify()
        self.bundle = load_bundle(MODEL)
        if self.bundle["period"] != 1 or self.bundle["horizon"] != 1 or self.bundle["source_identity"] != "supplied-20261028-native-csv":
            raise ValueError("MODEL_IDENTITY: unexpected frozen study")

    def verify(self):
        for path,expected in self.baseline.items():
            if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
                raise ValueError("MODEL_DRIFT: frozen model/code/config changed")
        if hashlib.sha256(MODEL.read_bytes()).hexdigest() != MODEL_HASH:
            raise ValueError("MODEL_HASH: unexpected model")

    def prepare(self, rows):
        import pandas as pd
        from src.data_loader import canonicalize
        from src.labels import filter_bars
        self.verify()
        frame = pd.DataFrame([{**row, "timestamp": local_time(row["ts"])} for row in rows])
        frame["timestamp"] = pd.to_datetime(frame["timestamp"])
        frame["raw_position"] = range(len(frame))
        if frame.timestamp.iloc[-1].strftime("%H:%M") in ("13:30", "19:00"):
            frame = frame.iloc[:-1].copy()
        bars,_ = canonicalize(frame, 1)
        kept,ledger,state = filter_bars(bars, 1)
        kept["ts"] = [round(t.to_pydatetime().replace(tzinfo=SHANGHAI).timestamp()*1000) for t in kept.available_at]
        latest = round(bars.available_at.iloc[-1].to_pydatetime().replace(tzinfo=SHANGHAI).timestamp()*1000)
        return dict(kept=kept, latest=latest, status=ledger.status.iloc[-1], state=state)

    def predict(self, prepared):
        from src.features import make_features
        from src.predict import model_probability
        kept = prepared["kept"]
        features = make_features(kept).add_prefix("f_")
        if len(kept) <= self.bundle["warmup"] or features.iloc[-1].isna().any():
            raise ValueError("WARMUP: insufficient complete accepted history")
        p = float(model_probability(self.bundle, features.iloc[[-1]])[0])
        direction = "up" if p >= .5 else "down"
        return dict(p_up=p, signal=direction if max(p,1-p) >= self.bundle["threshold"] else "wait",
                    base_close=float(kept.close.iloc[-1]), model_version=self.bundle["model_version"],
                    feature_sha256=hashlib.sha256(features.iloc[[-1]].to_csv(index=False).encode()).hexdigest())
