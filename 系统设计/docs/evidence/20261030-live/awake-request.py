"""Prepared one-time request; run only after fresh user approval for 2026-10-30."""
import ctypes
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import time

ZONE = timezone(timedelta(hours=8))
DEADLINE = datetime(2026, 10, 30, 16, 5, tzinfo=ZONE)
LOG = Path(r'D:\mycode\沧海易购1\系统设计\runtime\http-research\awake-20261030.jsonl')
STOP = LOG.with_suffix('.stop')


def emit(kind, **fields):
    with LOG.open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(dict(kind=kind, at=datetime.now(ZONE).isoformat(),
                                     pid=os.getpid(), **fields), ensure_ascii=False)+'\n')


def main():
    remaining = (DEADLINE-datetime.now(ZONE)).total_seconds()
    if not 0 < remaining <= 21600:
        raise ValueError('Expired or outside this one-time approval window')
    LOG.parent.mkdir(parents=True, exist_ok=True)
    stop = time.monotonic()+remaining
    set_state = ctypes.WinDLL('kernel32').SetThreadExecutionState
    set_state.argtypes = [ctypes.c_uint32]
    set_state.restype = ctypes.c_uint32
    previous = set_state(0x80000001)
    if not previous:
        raise OSError('Sleep-prevention request failed')
    try:
        emit('ACTIVE', until=DEADLINE.isoformat(), flags=0x80000001, previous=previous)
        while time.monotonic() < stop and datetime.now(ZONE) < DEADLINE and not STOP.exists():
            time.sleep(min(20, max(0, stop-time.monotonic())))
    finally:
        cleared = set_state(0x80000000)
        emit('CLEARED', success=bool(cleared), returned_state=cleared)
        if not cleared:
            raise OSError('Sleep-prevention request could not be cleared')


if __name__ == '__main__':
    main()
