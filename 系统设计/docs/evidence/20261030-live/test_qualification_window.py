"""Synthetic selection checks only; no model, network, or live-ledger writes."""
import importlib.util
from pathlib import Path
import unittest

p=Path(__file__).with_name('qualification_window.py')
spec=importlib.util.spec_from_file_location('qualification_window',p)
q=importlib.util.module_from_spec(spec);spec.loader.exec_module(q)


class WindowSelectionTests(unittest.TestCase):
    def rows(self,n):
        return [dict(anchor_ms=i,accepted=True,published=True) for i in range(1,n+1)]

    def test_first_sixty_keeps_late_attempt_and_does_not_choose_later_run(self):
        rows=self.rows(130);rows[10]['eligible']=False;rows[60]['published']=False
        result=q.select_window(rows,set(range(1,131)))
        self.assertEqual(result['anchors'],list(range(1,61)))
        self.assertIn(11,result['anchors'])

    def test_gap_breaks_and_skip_does_not_count_or_break(self):
        rows=self.rows(100);rows[29]['published']=False;rows[39]['accepted']=False;rows[39]['published']=False
        result=q.select_window(rows,set(range(1,101)))
        self.assertEqual(result['anchors'],[i for i in range(31,92) if i!=40])
        self.assertEqual(len(result['anchors']),60)

    def test_future_target_prevents_mature_window(self):
        result=q.select_window(self.rows(60),set(range(1,60)))
        self.assertEqual(result['waiting'],[60])

    def test_fifty_nine_is_not_sixty(self):
        result=q.select_window(self.rows(59),set(range(1,60)))
        self.assertEqual(result['anchors'],[])


if __name__=='__main__':unittest.main()
