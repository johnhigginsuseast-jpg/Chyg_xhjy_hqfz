from datetime import datetime
from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import Mock

import pandas as pd

from realtime.__main__ import http_bootstrap,worker_lock,workspace_path,code_hash
from realtime.native import epoch_ms
from realtime.http_feed import SOURCE,NAME,SYMBOL,TIME_POLICY


class CliTests(unittest.TestCase):
    def test_bootstrap_is_http_only_frozen_and_does_not_publish(self):
        base=epoch_ms(datetime(2026,10,28,13,31))
        rows=[dict(ts=base+i*60000,raw_ts=base+(i-1)*60000,open=100,high=100,low=100,close=100,volume=1,turnover=100)for i in range(100)]
        meta=dict(received_ms=rows[-1]['ts']-30000,actual_units='RAW',source_id=SOURCE,symbol=SYMBOL,name=NAME,time_policy=TIME_POLICY)
        feed=Mock();feed.fetch.return_value=(rows,meta)
        predictor=Mock();predictor.prepare.return_value=dict(kept=pd.DataFrame(rows[:-1]),state={'run':0},status='accepted')
        with tempfile.TemporaryDirectory()as temp:
            deployment=http_bootstrap(Path(temp),predictor,feed)
            snapshot=json.loads((Path(temp)/'bootstrap.json').read_text(encoding='utf-8'))
            self.assertEqual(len(snapshot['rows']),99)
            self.assertEqual(snapshot['rows'][-1]['ts'],rows[-2]['ts'])
            self.assertEqual(deployment['source'],SOURCE)
            self.assertTrue(deployment['domain_shift_acknowledged'])
            self.assertEqual(deployment['code_sha256'],code_hash())
            self.assertFalse((Path(temp)/'forward.sqlite3').exists())
            predictor.predict.assert_not_called()

    def test_one_worker_and_output_scope(self):
        with tempfile.TemporaryDirectory()as temp:
            runtime=Path(temp)
            with worker_lock(runtime):
                with self.assertRaisesRegex(ValueError,'running collector'):
                    with worker_lock(runtime):pass
            with worker_lock(runtime):pass
        with self.assertRaisesRegex(ValueError,'stay in'):workspace_path('../escape.sqlite3')


if __name__=='__main__':unittest.main()
