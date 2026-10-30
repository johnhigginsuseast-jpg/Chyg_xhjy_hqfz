import argparse
import platform
import sys
from collections import Counter

import pandas as pd

from .common import ROOT, load_config, period_name, sha256, source_file, write_json
from .data_loader import canonicalize, load_data


def audit(config):
    out = ROOT / "data/cleaned"
    out.mkdir(parents=True, exist_ok=True)
    minute = load_data(source_file(config, 1))
    records, errors = [], []
    for period in config["periods"]:
        path = source_file(config, period)
        try:
            raw = load_data(path)
            clean, events = canonicalize(raw, period, minute)
            clean.to_parquet(out / f"{period_name(period)}.parquet", index=False)
            rec = {"period": period, "file": path.name, "sha256": sha256(path), "raw_rows": len(raw),
                   "completed_bars": len(clean), "opening_events": len(events),
                   "first_source": str(raw.timestamp.iloc[0]), "last_source": str(raw.timestamp.iloc[-1]),
                   "first_available": str(clean.available_at.iloc[0]), "last_available": str(clean.available_at.iloc[-1]),
                   "timezone": str(raw.timestamp.dt.tz) if raw.timestamp.dt.tz is not None else "UNCONFIRMED",
                   "timestamp_unit": "minute-resolution datetime text", "zero_volume": int(raw.volume.eq(0).sum()),
                   "volume_min": float(raw.volume.min()), "volume_median": float(raw.volume.median()),
                   "volume_p99": float(raw.volume.quantile(.99)), "volume_max": float(raw.volume.max()),
                   "price_min": float(raw.low.min()), "price_max": float(raw.high.max()),
                   "volume_sum": float(raw.volume.sum()), "clean_volume_sum": float(clean.volume.sum()),
                   "delta_minutes": {str(k): int(v) for k, v in Counter(raw.timestamp.diff().dt.total_seconds().div(60).dropna()).most_common(10)},
                   "adjusted_available_times": int(clean.source_timestamp.ne(clean.available_at).sum()),
                   "structural_errors": 0, "events": events}
            if rec["volume_sum"] != rec["clean_volume_sum"]:
                raise ValueError("清洗成交量不守恒")
            records.append(rec)
            print(f"AUDIT {path.name}: {len(raw)} raw -> {len(clean)} bars, {len(events)} opening events", flush=True)
        except (ValueError, OSError) as exc:
            errors.append({"file": path.name, "error": str(exc)})
    daily = load_data(source_file(config, 0))
    grouped = minute.assign(trade_date=minute.timestamp.dt.normalize() + pd.to_timedelta(minute.timestamp.dt.hour.ge(19).astype(int), unit="D"))
    agg = grouped.groupby("trade_date").agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"), volume=("volume", "sum"))
    mismatch = []
    for row in daily.itertuples():
        if row.timestamp not in agg.index:
            mismatch.append({"date": str(row.timestamp), "issue": "no minute aggregation"})
            continue
        cols = [c for c in ("open", "high", "low", "close") if getattr(row, c) != agg.loc[row.timestamp, c]]
        if cols:
            mismatch.append({"date": str(row.timestamp), "fields": cols,
                             "daily": {c: float(getattr(row, c)) for c in cols},
                             "minute": {c: float(agg.loc[row.timestamp, c]) for c in cols}})
    result = {"research_training_allowed": not errors, "formal_source_authenticated": False,
              "source_identity": config["source_identity"], "python": sys.version, "platform": platform.platform(),
              "calendar_policy": config["calendar_policy"], "symbol_status": config["symbol_status"],
              "timezone_status": config["timezone_status"], "files": records, "errors": errors,
              "daily_minute_ohlc_differences": mismatch,
              "warnings": ["CSV does not authenticate symbol, platform, volume units or non-synthetic quotes",
                           "No records means rest by user instruction; not an independently verified calendar",
                           "Opening events are merged; source and available_at retained; no prices fabricated",
                           "Historical test exposure overlap has not been ruled out"]}
    write_json(ROOT / "reports/evidence/stage1/audit.json", result)
    lines = ["# 数据审计（正式阶段1）", "", "原始数据保持只读。仅允许本地历史研究；来源/代码/时区/单位未独立核实。", "",
             "| 周期 | 原始行 | 完整K线 | 合并开盘事件 | 时间可用性调整 | 结构错误 |", "|---|---:|---:|---:|---:|---:|"]
    for r in records:
        lines.append(f"| {period_name(r['period'])} | {r['raw_rows']} | {r['completed_bars']} | {r['opening_events']} | {r['adjusted_available_times']} | 0 |")
    lines += ["", "## 时间、缺席与清洗", "", "采用用户确认：周六日盘、周日休息，没有记录时间作为休息；不补历史价格。",
              "25条开盘事件并入下一条完整分钟，保留原行映射与量守恒。合成桶以名义结束作为available_at；源时间不改。",
              "日线午夜只是交易日标签，研究中以当日16:00可用；实际开盘从前夜/当日日盘分钟记录推导。",
              "这些是可复核的研究假设，未冒充平台认证。无时区的原生顺序保留，不加入小时/星期特征。", "",
              "## 质量与来源", "", "所有必需数值为有限数，价格为正，量非负，时间严格递增，OHLC关系校验；错误立即阻止相应版本训练。",
              "零量、极值、周期差分、每个源SHA256和事件映射见 [原始机器审计](evidence/stage1/audit.json)。",
              f"日线与同源分钟按前夜归次日聚合的OHLC差异共有{len(mismatch)}个交易日，保留独立日线来源，不静默纠正。",
              "5分钟09-15的20:15原标签与按最后成交生成的20:14标签不同；统一available_at后不提前使用。",
              "成交量单位及合成报价风险无法通过内部一致性证明。最大分钟量235,794的09-21记录保留，不因异常量或预测表现筛除。", "",
              "## 门禁", "", f"研究训练门禁：{'PASS' if not errors else 'FAIL'}（仅数据处理，不等于模型或总体验收通过）。",
              "模型训练、概率及预测能力在本报告产生时尚未验证；最终测试需按冻结清单单次解锁。",
              "此前历史可能暴露，不称全新盲测；真正独立新数据资格仍未验证。", "",
              "完整前期数值与差异清单保留在 [初检报告](evidence/preflight-20261028/data_audit-preliminary.md)。"]
    (ROOT / "reports/data_audit.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if errors:
        raise ValueError(f"严重数据问题，停止训练: {errors}")
    return result


def main():
    parser = argparse.ArgumentParser(description="只读审计并输出带来源映射的派生完整K线")
    parser.add_argument("--config")
    args = parser.parse_args()
    audit(load_config(args.config))


if __name__ == "__main__":
    main()
