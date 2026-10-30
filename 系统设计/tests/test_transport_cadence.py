"""Synthetic clock/transport only; no real requests, models, or ledger writes."""
from contextlib import redirect_stdout
import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
import tempfile
import unittest
from unittest.mock import Mock, patch

from realtime import __main__ as cli
from realtime.http_feed import FeedError, SOURCE


class TransportCadenceTests(unittest.TestCase):
    def starts(self, code, elapsed, retry_after):
        ticks, starts = [0.0], []

        def fetch(**kwargs):
            starts.append(ticks[0])
            if len(starts) == 3:
                raise KeyboardInterrupt
            ticks[0] += elapsed
            raise FeedError(code, retry_after)

        def sleep(seconds):
            ticks[0] += seconds

        with tempfile.TemporaryDirectory(dir=cli.ROOT/'runtime') as directory:
            root = Path(directory)
            approval = root/'docs/baselines/v0.4/confirmation.json'
            approval.parent.mkdir(parents=True)
            approval.write_bytes(b'QA_APPROVAL_HASH_ONLY')
            body = json.dumps(dict(rows=[], quarantined_rows=[])).encode()
            (root/'bootstrap.json').write_bytes(body)
            config = dict(id='QA_REPLAY_CADENCE', mode='REPLAY', source=SOURCE, enabled_at_ms=0,
                          model_sha256='0'*64, code_sha256='0'*64,
                          bootstrap_sha256=hashlib.sha256(body).hexdigest(),
                          approval_sha256=hashlib.sha256(approval.read_bytes()).hexdigest())
            config_path = root/'deployment.json'
            config_path.write_text(json.dumps(config), encoding='utf-8')
            ledger = Mock(deployment=config)
            ledger.summary.return_value = dict(hit_rate=None, HIT=0, scored=0,
                                               effect_sample_insufficient=True, mode='REPLAY')
            ledger.recent.return_value = []
            factory = Mock()
            factory.return_value.__enter__ = Mock(return_value=ledger)
            factory.return_value.__exit__ = Mock(return_value=False)
            engine = Mock()
            engine.state.side_effect = lambda status, detail=None: dict(status=status, detail=detail)
            args = SimpleNamespace(backup=None, status=False, once=False)
            predictor = SimpleNamespace(bundle={'model_version': 'QA_ONLY_NO_MODEL'})
            with patch.object(cli, 'ROOT', root), patch.object(cli, 'code_hash', return_value='0'*64), \
                    patch.object(cli, 'Ledger', factory), patch.object(cli, 'Engine', return_value=engine), \
                    patch.object(cli.time, 'monotonic', side_effect=lambda: ticks[0]), \
                    patch.object(cli.time, 'time', side_effect=lambda: 1793271600+ticks[0]), \
                    patch.object(cli.time, 'sleep', side_effect=sleep), redirect_stdout(io.StringIO()):
                cli.run(args, root, config_path, predictor, SimpleNamespace(fetch=fetch))
        return starts

    def test_slow_transport_error_uses_elapsed_poll_interval(self):
        self.assertEqual(self.starts('HTTP_TRANSPORT_ERROR', 8, 3), [0, 8, 16])

    def test_fast_transport_error_keeps_three_second_start_cadence(self):
        self.assertEqual(self.starts('HTTP_TRANSPORT_ERROR', 1, 3), [0, 3, 6])

    def test_throttle_hint_waits_after_response(self):
        self.assertEqual(self.starts('HTTP_THROTTLED', 1, 7), [0, 8, 16])

    def test_http_status_waits_after_response(self):
        self.assertEqual(self.starts('HTTP_STATUS_502', 1, 60), [0, 61, 122])


if __name__ == '__main__':
    unittest.main()
