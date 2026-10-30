from pathlib import Path

import numpy as np
import pandas as pd

ALIASES = {"时间": "timestamp", "日期": "timestamp", "datetime": "timestamp", "date": "timestamp",
           "开盘": "open", "最高": "high", "最低": "low", "收盘": "close", "成交量": "volume",
           "成交额": "turnover", "分钟数": "constituents"}
REQUIRED = ["timestamp", "open", "high", "low", "close", "volume"]
SESSIONS = [(571, 690), (811, 960), (1141, 1260)]


def load_data(path):
    path = Path(path)
    if path.suffix.lower() == ".csv":
        frame = pd.read_csv(path, encoding="utf-8-sig")
    elif path.suffix.lower() in (".xlsx", ".xls"):
        frame = pd.read_excel(path)
    elif path.suffix.lower() == ".parquet":
        frame = pd.read_parquet(path)
    else:
        raise ValueError("仅支持 CSV、Excel、Parquet")
    frame.columns = [ALIASES.get(str(c).strip().lower(), str(c).strip().lower()) for c in frame.columns]
    if frame.columns.duplicated().any():
        raise ValueError("字段映射后存在重复列")
    missing = set(REQUIRED) - set(frame.columns)
    if missing:
        raise ValueError(f"缺少必需字段: {', '.join(sorted(missing))}")
    if frame.empty:
        raise ValueError("行情文件为空")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
    if frame["timestamp"].isna().any():
        raise ValueError("时间字段含空值或非法时间")
    if frame["timestamp"].duplicated().any():
        raise ValueError("存在重复时间，需审计处理后才能训练")
    if not frame["timestamp"].is_monotonic_increasing:
        raise ValueError("行情时间必须严格递增")
    for col in REQUIRED[1:] + [c for c in ("turnover", "constituents") if c in frame]:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
        if not np.isfinite(frame[col].to_numpy(dtype=float)).all():
            raise ValueError(f"{col} 含缺失值或非有限数")
    if (frame[["open", "high", "low", "close"]] <= 0).any().any() or (frame["volume"] < 0).any():
        raise ValueError("价格必须为正，成交量不得为负")
    if ((frame["low"] > frame[["open", "close"]].min(axis=1)) |
        (frame["high"] < frame[["open", "close"]].max(axis=1)) |
        (frame["low"] > frame["high"])).any():
        raise ValueError("OHLC高低价逻辑不一致")
    if "turnover" in frame and (frame["turnover"] < 0).any():
        raise ValueError("成交额不得为负")
    frame["raw_position"] = np.arange(len(frame))
    return frame


def canonicalize(frame, period, minute_reference=None):
    frame = frame.copy()
    frame["source_timestamp"] = frame["timestamp"]
    frame["raw_positions"] = frame["raw_position"].astype(str)
    events = []
    if period == 1:
        opening = frame["timestamp"].dt.strftime("%H:%M").isin(["13:30", "19:00"])
        for i in frame.index[opening]:
            row = frame.loc[i]
            if row[["open", "high", "low", "close"]].nunique() != 1:
                raise ValueError("开盘事件不是单价记录，无法按已登记策略合并")
            if i + 1 not in frame.index or frame.loc[i + 1, "timestamp"] != row["timestamp"] + pd.Timedelta(minutes=1):
                raise ValueError("开盘事件缺少下一根完整分钟，停止训练")
            frame.loc[i + 1, "open"] = row["open"]
            frame.loc[i + 1, "high"] = max(row["high"], frame.loc[i + 1, "high"])
            frame.loc[i + 1, "low"] = min(row["low"], frame.loc[i + 1, "low"])
            for col in ("volume", "turnover"):
                if col in frame:
                    frame.loc[i + 1, col] += row[col]
            frame.loc[i + 1, "raw_positions"] = f"{int(row['raw_position'])},{int(frame.loc[i + 1, 'raw_position'])}"
            events.append({"raw_position": int(row["raw_position"]), "timestamp": str(row["timestamp"]),
                           "status": "opening_event_merged", "into": str(frame.loc[i + 1, "timestamp"])})
        frame = frame.loc[~opening].copy()
    available, opened = [], []
    for timestamp in frame["timestamp"]:
        day = timestamp.normalize()
        if timestamp.weekday() == 6 or (timestamp.weekday() == 5 and timestamp.hour >= 19):
            raise ValueError(f"用户已确认的休市时段出现记录: {timestamp}")
        if period == 0:
            available.append(day + pd.Timedelta(hours=16))
            if minute_reference is None:
                raise ValueError("日线需同源分钟记录确认实际开盘时间")
            mt = minute_reference["timestamp"]
            members = minute_reference.loc[((mt >= day - pd.Timedelta(hours=5)) & (mt <= day - pd.Timedelta(hours=3))) |
                                           ((mt >= day + pd.Timedelta(hours=9, minutes=30)) & (mt <= day + pd.Timedelta(hours=16)))]
            if members.empty:
                raise ValueError("日线交易日找不到同源分钟记录")
            first = members["timestamp"].iloc[0]
            opened.append(first if first.strftime("%H:%M") in ("09:30", "13:30", "19:00") else first - pd.Timedelta(minutes=1))
        else:
            minute = timestamp.hour * 60 + timestamp.minute
            session = next(((a, b) for a, b in SESSIONS if a <= minute <= b), None)
            if session is None:
                raise ValueError(f"非交易时段完整K线: {timestamp}")
            a, b = session
            start = a + ((minute - a) // period) * period
            end = min(start + period - 1, b)
            available.append(day + pd.Timedelta(minutes=end))
            opened.append(day + pd.Timedelta(minutes=start - 1))
    frame["available_at"] = available
    frame["open_at"] = opened
    if frame["available_at"].duplicated().any():
        raise ValueError("规范桶结束时间重复，停止训练")
    frame = frame.reset_index(drop=True)
    frame["bar_position"] = np.arange(len(frame))
    return frame, events
