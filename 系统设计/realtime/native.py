"""Read only documented market structure and market records, never DY2 reserved areas."""
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import io
import math
from pathlib import Path
import stat
import struct
import time

INDEX = 0x560200
RESERVED_SLOTS = 512
RECORD = struct.Struct("<d8fB")
FIELDS = ["时间", "开盘", "最高", "最低", "收盘", "总量", "总额", "持仓", "买盘量", "标志"]
VALUES = ["open", "high", "low", "close", "volume", "turnover"]
SHANGHAI = timezone(timedelta(hours=8))
HISTORY_HASH = "4b7627330182b5baa9748f51069d1ea58107cfbdbf2332d6db9a7970d33724f7"


def epoch_ms(wall):
    return round(wall.replace(tzinfo=SHANGHAI).timestamp() * 1000)


def local_time(ms):
    return datetime.fromtimestamp(ms/1000, SHANGHAI).strftime("%Y-%m-%d %H:%M:%S")


def _signature(path):
    s = path.stat()
    if path.is_symlink() or not stat.S_ISREG(s.st_mode):
        raise ValueError("SOURCE_PATH: only a regular MIN.DY2 file is accepted")
    return s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns


def _market_bytes(path):
    before = _signature(path)
    if path.name.upper() != "MIN.DY2" or before[2] < INDEX + (RESERVED_SLOTS+1)*41 or (before[2]-INDEX) % 41:
        raise ValueError("SOURCE_LAYOUT: unsupported file size or name")
    with path.open("rb") as f:
        header = f.read(276)
        f.seek(472)
        allocated = f.read(8)
        f.seek(520)
        active = f.read(8)
        f.seek(INDEX + RESERVED_SLOTS*41)
        market = f.read()
    if before != _signature(path):
        raise ValueError("SOURCE_WRITING: file changed while reading")
    return (header, allocated, active, market), before


def read_snapshot(path, stability_delay=.08):
    path = Path(path)
    first, signature = _market_bytes(path)
    time.sleep(stability_delay)
    second, after = _market_bytes(path)
    if signature != after or first != second:
        raise ValueError("SOURCE_WRITING: market content or index is not stable")
    header, allocated, active, market = first
    if struct.unpack_from("<9I", header) != (2, 0x5F5F5F5F, 65536, 41, 1024, 16, INDEX, 1, 10):
        raise ValueError("SOURCE_LAYOUT: unknown market layout")
    for i, name in enumerate(FIELDS):
        offset = 36 + i*24
        kind, size = struct.unpack_from("<2I", header, offset)
        label = header[offset+8:offset+24].split(b"\0")[0].decode("gb18030")
        expected = (1, 8) if i == 0 else (11, 1) if i == 9 else (8, 4)
        if (kind, size, label) != (*expected, name):
            raise ValueError("SOURCE_FIELDS: unexpected field description")
    count, first_slot = struct.unpack("<2I", active)
    allocation, _ = struct.unpack("<2I", allocated)
    capacity = len(market)//41
    if not 0 < count <= capacity or not RESERVED_SLOTS <= first_slot < RESERVED_SLOTS+capacity or not count <= allocation <= capacity:
        raise ValueError("SOURCE_INDEX: invalid active range")
    slots = [(first_slot-RESERVED_SLOTS+i) % capacity for i in range(count)]
    active_slots = set(slots)
    for slot in range(capacity):
        if slot not in active_slots and any(market[slot*41:(slot+1)*41]):
            raise ValueError("SOURCE_UNCOMMITTED: records outside active index")
    rows = []
    for slot in slots:
        date, o, h, l, c, v, a, interest, buying, flag = RECORD.unpack_from(market, slot*41)
        if not all(math.isfinite(x) for x in (date,o,h,l,c,v,a,interest,buying)) or not 25569 < date < 73050 or flag != 0:
            raise ValueError("SOURCE_RECORD: invalid date, flag, or market number")
        wall = datetime(1899,12,30) + timedelta(days=date)
        stamp = epoch_ms(wall)
        aligned = round(stamp/60000)*60000
        if abs(stamp-aligned) > 1 or l <= 0 or h < max(o,c,l) or l > min(o,c) or min(v,a) < 0:
            raise ValueError("SOURCE_RECORD: invalid minute or OHLCV")
        # Match the frozen exporter exactly, while retaining raw market records in the snapshot hash.
        rows.append(dict(ts=aligned, **dict(zip(VALUES, [round(x,2) for x in (o,h,l,c)] + [round(v),round(a)]))))
    if any(a["ts"] >= b["ts"] for a,b in zip(rows,rows[1:])):
        # shortcut: reject an unverified ring ordering; add a new validated layout before supporting it.
        raise ValueError("SOURCE_ORDER: duplicate, conflict, or unsupported ring ordering")
    digest = hashlib.sha256(b"".join(first)).hexdigest()
    return rows, dict(profile="indexed-market-only-v1", count=count, first_slot=first_slot, capacity=capacity,
                      market_snapshot_sha256=digest, modified_ns=signature[3], reserved_bytes_read=False,
                      first=local_time(rows[0]["ts"]), last=local_time(rows[-1]["ts"]))


def read_history(path):
    raw = Path(path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != HISTORY_HASH:
        raise ValueError("HISTORY_HASH: frozen CSV changed")
    rows = []
    for row in csv.DictReader(io.StringIO(raw.decode("utf-8-sig"), newline="")):
        wall = datetime.fromisoformat(row["时间"])
        if wall.tzinfo is not None or wall.second or wall.microsecond:
            raise ValueError("HISTORY_TIME: expected native minute labels")
        rows.append(dict(ts=epoch_ms(wall), **dict(zip(VALUES,[float(row[k]) for k in ["开盘","最高","最低","收盘","成交量","成交额"]]))))
    return rows


def check_lineage(history, incoming, minimum=100):
    baseline = {row["ts"]:row for row in history}
    overlap = [row for row in incoming if row["ts"] in baseline]
    if len(overlap) < minimum:
        raise ValueError("SOURCE_IDENTITY: insufficient exact-lineage overlap")
    for row in overlap:
        if any(row[k] != baseline[row["ts"]][k] for k in VALUES):
            raise ValueError("SOURCE_CONFLICT: incoming market fields changed; do not merge sources")
    sessions = {(local_time(row["ts"])[:10], "am" if local_time(row["ts"])[11:13] < "12" else "pm") for row in overlap}
    if len(sessions) < 2:
        raise ValueError("SOURCE_IDENTITY: overlap must include at least two sessions")
    return dict(status="EXACT_NATIVE_LINEAGE", overlap=len(overlap), session_count=len(sessions),
                fields=VALUES, mismatches=0, unit_mapping="Frozen exporter numerical units; no scaling or time shift")
