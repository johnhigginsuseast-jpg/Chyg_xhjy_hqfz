from pathlib import Path
import tempfile
import unittest

from realtime.model import ROOT, MODEL, StudyPredictor
from realtime.native import read_history,local_time


class FrozenModelTests(unittest.TestCase):
    def test_real_frozen_model_matches_original_probability_and_skip(self):
        import pandas as pd
        predictor=StudyPredictor()
        from src.predict import predict_history
        history=read_history(ROOT.parent/'2026-10-28/1分钟K线.csv')
        skipped=predictor.prepare(history)
        original_skip=predict_history(MODEL,ROOT.parent/'2026-10-28/1分钟K线.csv','2026-10-27 16:00','supplied-20261028-native-csv')
        self.assertEqual(skipped['status'],'rule_skip')
        self.assertEqual(original_skip['status'],'RULE_SKIP')
        anchor=int(skipped['kept'].ts.iloc[-1])
        prefix=[r for r in history if r['ts']<=anchor]
        prepared=predictor.prepare(prefix)
        actual=predictor.predict(prepared)
        with tempfile.TemporaryDirectory(dir=ROOT/'runtime')as tmp:
            path=Path(tmp)/'historical-regression-only.csv'
            frame=pd.DataFrame([{**r,'timestamp':local_time(r['ts'])}for r in prefix])
            frame.to_csv(path,index=False,encoding='utf-8-sig')
            expected=predict_history(MODEL,path,local_time(anchor),'supplied-20261028-native-csv')
        self.assertEqual(expected['status'],'PREDICTED')
        self.assertAlmostEqual(expected['p_up'],actual['p_up'],places=12)
        self.assertEqual(expected['signal'],actual['signal'])
        self.assertEqual(expected['base_close'],actual['base_close'])
        self.assertEqual(expected['model_version'],actual['model_version'])


if __name__=='__main__':unittest.main()
