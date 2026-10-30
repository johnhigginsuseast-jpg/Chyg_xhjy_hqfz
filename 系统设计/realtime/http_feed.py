"""Public client HTTP feed; explicit cross-source research, original numbers retained."""
from datetime import datetime,timedelta
from email.utils import parsedate_to_datetime
import hashlib
import http.client
import json
import math
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

from .ledger import canonical
from .native import SHANGHAI

HOST='yt.scdzscxt.com'
SOURCE='HTTP_CROSS_SOURCE_RESEARCH'
SYMBOL='531'
NAME='印江花果红茶二期'
TIME_POLICY='OBSERVED_RAW_OPEN_PLUS_60S_CLOSE_V1'
BOUNDARY_POLICY='QUARANTINE_SINGLE_PRICE_TERMINAL_EVENTS_V1'
MAX_BODY=2*1024*1024


class FeedError(ValueError):
    def __init__(self,code,retry_after=3):
        self.code,self.retry_after=code,retry_after
        super().__init__(code)


def parse_payload(payload,received_ms,server_date):
    if not isinstance(payload,dict) or str(payload.get('symbol'))!=SYMBOL or payload.get('name')!=NAME or payload.get('code')!=0:
        raise FeedError('HTTP_IDENTITY_OR_STATUS_REJECTED')
    try:
        server=parsedate_to_datetime(server_date)
        if server.tzinfo is None or abs(received_ms-int(server.timestamp()*1000))>10000:
            raise ValueError()
    except (TypeError,ValueError,OverflowError):
        raise FeedError('HTTP_CLOCK_UNCONFIRMED')from None
    rows=[]
    if not isinstance(payload.get('data'),list):raise FeedError('HTTP_ROW_SCHEMA_REJECTED')
    for item in payload['data']:
        if not isinstance(item,list)or len(item)<8:
            raise FeedError('HTTP_ROW_SCHEMA_REJECTED')
        values=[item[0],*item[2:8]]
        if any(isinstance(x,bool)or not isinstance(x,(int,float))or not math.isfinite(x)for x in values):
            raise FeedError('HTTP_NONFINITE_OR_TYPE_REJECTED')
        raw_ts,o,h,l,c,v,a=values
        if int(raw_ts)!=raw_ts or raw_ts%60000 or raw_ts<=946684800000 or raw_ts>received_ms+60000:
            raise FeedError('HTTP_TIME_REJECTED')
        if l<=0 or h<max(o,c,l)or l>min(o,c)or min(v,a)<0:
            raise FeedError('HTTP_OHLCV_REJECTED')
        row=dict(raw_ts=int(raw_ts),ts=int(raw_ts)+60000,open=o,high=h,low=l,close=c,volume=v,turnover=a)
        wall=datetime.fromtimestamp(raw_ts/1000,SHANGHAI)
        minute=wall.hour*60+wall.minute
        if minute in (690,960,1260):
            if (not rows or rows[-1]['raw_ts']+60000!=raw_ts or len({o,h,l,c})!=1
                    or rows[-1]['close']!=c):
                raise FeedError('HTTP_UNQUALIFIED_BOUNDARY_RECORD')
            row['quarantine_reason']='NON_MINUTE_SINGLE_PRICE_AT_NOMINAL_SESSION_END'
        elif not (570<=minute<690 or 810<=minute<960 or 1140<=minute<1260):
            raise FeedError('HTTP_UNQUALIFIED_SESSION_RECORD')
        if wall.weekday()==6 or (wall.weekday()==5 and minute>=1140):
            raise FeedError('HTTP_UNQUALIFIED_SESSION_RECORD')
        rows.append(row)
    if not rows or any(a['ts']>=b['ts']for a,b in zip(rows,rows[1:])):
        raise FeedError('HTTP_EMPTY_DUPLICATE_OR_ORDER_REJECTED')
    metadata=dict(source_id=SOURCE,symbol=SYMBOL,name=NAME,period=1,time_policy=TIME_POLICY,
                  received_ms=received_ms,server_date=server_date,rows=len(rows),
                  market_snapshot_sha256=hashlib.sha256(canonical(rows).encode()).hexdigest(),
                  boundary_policy=BOUNDARY_POLICY,quarantined_boundary_rows=sum('quarantine_reason'in r for r in rows),
                  domain_shift_acknowledged=True,actual_units='HTTP raw numeric units; physical unit names unconfirmed')
    return rows,metadata


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):
        return None


class HttpFeed:
    def __init__(self):
        self.context=ssl.create_default_context()
        self.connection=None
        self.proxy=urllib.request.getproxies().get('https')
        if urllib.request.proxy_bypass(HOST):self.proxy=None
        # Proxy credentials, if configured, stay inside the standard transport and are never logged.
        parsed=urllib.parse.urlsplit(self.proxy)if self.proxy else None
        self.standard=bool(parsed and (parsed.scheme!='http'or '@'in parsed.netloc))
        self.opener=urllib.request.build_opener(urllib.request.HTTPSHandler(context=self.context),NoRedirect())

    def close(self):
        if self.connection:self.connection.close()
        self.connection=None

    def _read(self,path):
        if self.standard:
            try:
                with self.opener.open('https://'+HOST+path,timeout=8)as response:
                    return response.status,dict(response.headers),response.read(MAX_BODY+1)
            except urllib.error.HTTPError as response:
                try:return response.code,dict(response.headers),b''
                finally:response.close()
        if self.connection is None:
            if self.proxy:
                proxy=urllib.parse.urlsplit(self.proxy)
                self.connection=http.client.HTTPSConnection(proxy.hostname,proxy.port or 80,timeout=8,context=self.context)
                self.connection.set_tunnel(HOST,443)
            else:self.connection=http.client.HTTPSConnection(HOST,timeout=8,context=self.context)
        self.connection.request('GET',path,headers={'Accept':'application/json','User-Agent':'LocalMarketForwardResearch/0.4'})
        response=self.connection.getresponse()
        result=response.status,dict(response.getheaders()),response.read(MAX_BODY+1)
        if response.will_close:self.close()
        return result

    def fetch(self,bootstrap=False):
        now=datetime.now(SHANGHAI)
        if bootstrap:
            path='/qtfront_tq/kline?'+urllib.parse.urlencode(dict(symbol=SYMBOL,period=0,count=6000))
        else:
            params=dict(contractId=SYMBOL,period=0,count=30,first=(now+timedelta(minutes=2)).strftime('%Y%m%d%H%M'))
            path='/qtfront_tq/klinePage?'+urllib.parse.urlencode(params)
        started=time.monotonic()
        try:status,headers,body=self._read(path)
        except (OSError,http.client.HTTPException,urllib.error.URLError):
            self.close()
            raise FeedError('HTTP_TRANSPORT_ERROR')from None
        received=int(time.time()*1000)
        headers={k.lower():v for k,v in headers.items()}
        if status==429:
            delay=60
            try:delay=max(3,float(headers['retry-after']))
            except (KeyError,ValueError):
                try:delay=max(3,parsedate_to_datetime(headers.get('retry-after')).timestamp()-received/1000)
                except (TypeError,ValueError,OverflowError):pass
            if not math.isfinite(delay):delay=60
            raise FeedError('HTTP_THROTTLED',retry_after=delay)
        if status!=200:raise FeedError('HTTP_STATUS_'+str(status),retry_after=60)
        if len(body)>MAX_BODY:
            self.close()
            raise FeedError('HTTP_RESPONSE_TOO_LARGE')
        try:payload=json.loads(body)
        except (ValueError,UnicodeError):raise FeedError('HTTP_JSON_REJECTED')from None
        rows,metadata=parse_payload(payload,received,headers.get('date'))
        metadata.update(request_path=path,fetch_seconds=round(time.monotonic()-started,6),
                        transport='standard_https'if self.standard else 'persistent_https')
        return rows,metadata
