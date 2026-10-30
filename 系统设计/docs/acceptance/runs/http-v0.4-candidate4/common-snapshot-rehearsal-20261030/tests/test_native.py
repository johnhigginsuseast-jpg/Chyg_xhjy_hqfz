from datetime import datetime, timedelta
from pathlib import Path
import struct
import tempfile
import unittest

from realtime.native import INDEX, RECORD, FIELDS, read_snapshot, check_lineage


class NativeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "MIN.DY2"
        self.make_file()

    def make_file(self, count=2, first=512, capacity=4, bad_flag=0):
        with self.path.open("wb") as f:
            f.truncate(INDEX+(512+capacity)*41)
            f.write(struct.pack("<9I",2,0x5F5F5F5F,65536,41,1024,16,INDEX,1,10))
            for i,name in enumerate(FIELDS):
                kind,size=(1,8) if i==0 else (11,1) if i==9 else (8,4)
                f.write(struct.pack("<2I",kind,size)+name.encode("gb18030").ljust(16,b"\0"))
            f.seek(472);f.write(struct.pack("<2I",capacity,512))
            f.seek(520);f.write(struct.pack("<2I",count,first))
            for i in range(min(count,capacity)):
                slot=(first-512+i)%capacity
                date=(datetime(2026,10,28,9,31)+timedelta(minutes=i)-datetime(1899,12,30)).total_seconds()/86400
                f.seek(INDEX+(512+slot)*41)
                f.write(RECORD.pack(date,100,102,99,101,123,12423,1,0,bad_flag))

    def test_read_market_only_and_rounding(self):
        # Non-market reserved bytes are deliberately nonzero and must not be inspected.
        with self.path.open("r+b") as f:
            f.seek(1000);f.write(b"NOT_MARKET_NOT_FOR_READING")
        rows,meta=read_snapshot(self.path,stability_delay=0)
        self.assertEqual(len(rows),2)
        self.assertEqual(rows[0]["close"],101)
        self.assertEqual(meta["last"],"2026-10-28 09:32:00")
        self.assertFalse(meta["reserved_bytes_read"])

    def test_unknown_layout_and_partial_tail_rejected(self):
        with self.path.open("r+b") as f:f.write(b"xxxx")
        with self.assertRaisesRegex(ValueError,"SOURCE_LAYOUT"):read_snapshot(self.path,0)
        self.make_file()
        with self.path.open("ab") as f:f.write(b"x")
        with self.assertRaisesRegex(ValueError,"SOURCE_LAYOUT"):read_snapshot(self.path,0)

    def test_invalid_indices_flags_and_order(self):
        self.make_file(count=5)
        with self.assertRaisesRegex(ValueError,"SOURCE_INDEX"):read_snapshot(self.path,0)
        self.make_file(bad_flag=1)
        with self.assertRaisesRegex(ValueError,"SOURCE_RECORD"):read_snapshot(self.path,0)
        self.make_file()
        with self.path.open("r+b") as f:
            f.seek(INDEX+512*41);first=f.read(41)
            f.seek(INDEX+513*41);f.write(first)
        with self.assertRaisesRegex(ValueError,"SOURCE_ORDER"):read_snapshot(self.path,0)

    def test_uncommitted_and_wrapped_active_slots(self):
        self.make_file(first=515,count=2)
        rows,_=read_snapshot(self.path,0)
        self.assertLess(rows[0]["ts"],rows[1]["ts"])
        with self.path.open("r+b") as f:f.seek(INDEX+513*41);f.write(b"x")
        with self.assertRaisesRegex(ValueError,"SOURCE_UNCOMMITTED"):read_snapshot(self.path,0)

    def test_lineage_requires_exact_fields_and_two_sessions(self):
        rows,_=read_snapshot(self.path,0)
        with self.assertRaisesRegex(ValueError,"two sessions"):check_lineage(rows,rows,2)
        rows[1]["ts"]+=4*60*60000
        self.assertEqual(check_lineage(rows,rows,2)["mismatches"],0)
        modified=[dict(r)for r in rows];modified[0]["volume"]+=1
        with self.assertRaisesRegex(ValueError,"SOURCE_CONFLICT"):check_lineage(rows,modified,2)
        with self.assertRaisesRegex(ValueError,"insufficient"):check_lineage(rows,rows,100)


if __name__=="__main__":unittest.main()
