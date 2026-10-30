"""Mock-only tests: never issue a Windows power request."""
from datetime import timedelta
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

from tools import acceptance_awake_20261029 as awake


class AwakeTests(unittest.TestCase):
    def run_helper(self, now, ticks, sleep=None, returns=(0x80000000, 0x80000001)):
        api = Mock(side_effect=returns)
        self.api = api
        clock = Mock()
        clock.now.return_value = now
        with tempfile.TemporaryDirectory(dir=awake.LOG.parents[1]) as directory:
            log = Path(directory)/'mock-only.jsonl'
            with patch.object(awake, 'datetime', clock), patch.object(awake, 'LOG', log), \
                    patch.object(awake.ctypes, 'WinDLL', return_value=Mock(SetThreadExecutionState=api), create=True) as dll, \
                    patch.object(awake.time, 'monotonic', side_effect=ticks), \
                    patch.object(awake.time, 'sleep', sleep or Mock()):
                awake.main()
            return api, dll, log.read_text(encoding='utf-8')

    def test_expiry_clears_only_system_request(self):
        api, _, log = self.run_helper(awake.DEADLINE-timedelta(seconds=1), [0, 2])
        self.assertEqual([call.args[0] for call in api.call_args_list], [0x80000001, 0x80000000])
        self.assertIn('"kind": "ACTIVE"', log)
        self.assertIn('"kind": "CLEARED"', log)

    def test_interrupt_clears_request(self):
        with self.assertRaises(KeyboardInterrupt):
            self.run_helper(awake.DEADLINE-timedelta(seconds=1), [0, 0, 0], Mock(side_effect=KeyboardInterrupt))
        self.assertEqual([call.args[0] for call in self.api.call_args_list], [0x80000001, 0x80000000])

    def test_failed_request_is_not_treated_as_active(self):
        with self.assertRaises(OSError):
            self.run_helper(awake.DEADLINE-timedelta(seconds=1), [0], returns=(0,))
        self.assertEqual([call.args[0] for call in self.api.call_args_list], [0x80000001])

    def test_expired_window_never_calls_power_api(self):
        clock = Mock()
        clock.now.return_value = awake.DEADLINE
        with patch.object(awake, 'datetime', clock), patch.object(awake.ctypes, 'WinDLL', create=True) as dll:
            with self.assertRaises(ValueError):
                awake.main()
            dll.assert_not_called()


if __name__ == '__main__':
    unittest.main()
