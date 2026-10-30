from datetime import datetime,timezone
from email.utils import format_datetime
import json
import unittest
from unittest.mock import patch

from realtime.http_feed import HttpFeed,FeedError,parse_payload,NAME,SOURCE

NOW=1793192050000
DATE=format_datetime(datetime.fromtimestamp(NOW/1000,timezone.utc),usegmt=True)
BASE=1793192040000


def payload():
    return dict(code=0,symbol='531',name=NAME,ticket='NEVER_PERSIST_THIS',
                data=[[BASE-60000,99,100,102,99,101,20,2020,0],[BASE,101,101,103,100,102,5,510,0]])


class HttpFeedTests(unittest.TestCase):
    def test_raw_values_and_explicit_close_label_mapping(self):
        rows,meta=parse_payload(payload(),NOW,DATE)
        self.assertEqual(rows[-1]['raw_ts'],BASE)
        self.assertEqual(rows[-1]['ts'],BASE+60000)
        self.assertEqual(rows[-1]['volume'],5)
        self.assertEqual(rows[-1]['turnover'],510)
        self.assertEqual(meta['source_id'],SOURCE)
        self.assertNotIn('NEVER_PERSIST_THIS',json.dumps([rows,meta]))

    def test_identity_clock_bad_fields_and_chronology_rejected(self):
        cases=[]
        wrong=payload();wrong['symbol']='533';cases.append((wrong,DATE))
        wrong=payload();wrong['name']='OTHER';cases.append((wrong,DATE))
        wrong=payload();wrong['data'][0][3]=90;cases.append((wrong,DATE))
        wrong=payload();wrong['data'][0][6]=-1;cases.append((wrong,DATE))
        wrong=payload();wrong['data'][0][6]=float('nan');cases.append((wrong,DATE))
        wrong=payload();wrong['data'][0][6]=True;cases.append((wrong,DATE))
        wrong=payload();wrong['data'].reverse();cases.append((wrong,DATE))
        wrong=payload();wrong['data'][1][0]=wrong['data'][0][0];cases.append((wrong,DATE))
        cases.append((payload(),'Wed, 28 Oct 2026 00:00:00 GMT'))
        for body,date in cases:
            with self.subTest(body=body),self.assertRaises(FeedError):parse_payload(body,NOW,date)

    def test_fixed_public_endpoint_and_retry_after(self):
        feed=HttpFeed();self.addCleanup(feed.close)
        with patch.object(feed,'_read',return_value=(429,{'Retry-After':'120'},b'')):
            with self.assertRaises(FeedError)as result:feed.fetch()
            self.assertEqual(result.exception.retry_after,120)
        with patch.object(feed,'_read',return_value=(200,{'Date':DATE},json.dumps(payload()).encode()))as request,patch('realtime.http_feed.time.time',return_value=NOW/1000):
            rows,meta=feed.fetch()
            path=request.call_args.args[0]
            self.assertIn('contractId=531',path)
            self.assertIn('period=0',path)
            self.assertEqual(len(rows),2)

    def test_nonminute_boundary_event_is_retained_and_abnormal_one_rejected(self):
        terminal=BASE+6*60000
        body=dict(code=0,symbol='531',name=NAME,data=[
            [terminal-60000,99,100,102,99,101,20,2020],
            [terminal,101,101,101,101,101,3,303]])
        now=terminal+70000
        date=format_datetime(datetime.fromtimestamp(now/1000,timezone.utc),usegmt=True)
        rows,meta=parse_payload(body,now,date)
        self.assertIn('quarantine_reason',rows[-1])
        self.assertEqual(rows[-1]['volume'],3)
        self.assertEqual(meta['quarantined_boundary_rows'],1)
        body['data'][-1][3]=102
        with self.assertRaisesRegex(FeedError,'UNQUALIFIED_BOUNDARY'):parse_payload(body,now,date)


if __name__=='__main__':unittest.main()
