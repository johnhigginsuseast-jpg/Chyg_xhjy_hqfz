import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str, allow_nan=False), encoding="utf-8")
    temp.replace(path)


def load_config(path=None):
    path = Path(path) if path else ROOT / "configs/default.json"
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    config["data_path"] = str((ROOT / config["data_dir"]).resolve())
    if config["allow_short"]:
        raise ValueError("本版只支持做多模拟；做空资格未核实")
    if not 1 <= config["threads"] <= 4:
        raise ValueError("CPU threads 必须在1到4之间")
    return config


def period_name(period):
    return "daily" if period == 0 else f"{period}min"


def source_file(config, period):
    return Path(config["data_path"]) / ("日线.csv" if period == 0 else f"{period}分钟K线.csv")
