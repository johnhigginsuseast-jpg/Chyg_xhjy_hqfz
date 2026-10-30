"""Loopback-only dashboard server. Starting this never starts a collector."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import socket
import sys
from urllib.parse import parse_qs, urlsplit
import uuid

from data import DataError, Reader, ROOT

STATIC = {'/':('index.html','text/html'),'/app.js':('app.js','text/javascript'),'/styles.css':('styles.css','text/css')}


class LocalServer(ThreadingHTTPServer):
    allow_reuse_address = False

    def server_bind(self):
        if sys.platform == 'win32':
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def handler_for(reader):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send_body(self, status, body, mime='application/json'):
            try:
                self.send_response(status)
                self.send_header('Content-Type',mime+'; charset=utf-8')
                self.send_header('Content-Length',str(len(body)))
                self.send_header('Cache-Control','no-store')
                self.send_header('X-Content-Type-Options','nosniff')
                self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'")
                self.end_headers()
                if self.command!='HEAD':self.wfile.write(body)
            except ConnectionError:
                pass

        def error(self, code, status):
            self.send_body(status,json.dumps({'error':code},ensure_ascii=False).encode())

        def do_GET(self):
            host = self.headers.get('Host','')
            allowed={f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
            if (host not in allowed or self.headers.get('Origin',f'http://{host}')!=f'http://{host}'
                    or self.headers.get('Sec-Fetch-Site','none') not in ('none','same-origin')):
                self.error('LOCAL_SAME_ORIGIN_ONLY',403);return
            if len(self.path)>2048:
                self.error('INVALID_PARAMETERS',400);return
            url=urlsplit(self.path)
            if url.path=='/api/dashboard':
                try:
                    response=reader.dashboard(parse_qs(url.query,keep_blank_values=True))
                    body=json.dumps(response,ensure_ascii=False,allow_nan=False).encode()
                    self.send_body(200,body)
                except DataError as exc:self.error(exc.code,exc.status)
                except (ValueError,TypeError):self.error('INVALID_RESPONSE_DATA',503)
                return
            if url.path not in STATIC or url.query:
                self.error('NOT_FOUND',404);return
            name,mime=STATIC[url.path]
            try:
                body=(ROOT/'web'/name).read_bytes()
                if name=='index.html':
                    mode=getattr(reader,'mode','LIVE')
                    html=body.decode('utf-8').replace('<body>',f'<body data-mode="{mode}">')
                    if mode=='DEMO':
                        html=html.replace('正在读取数据模式','DEMO · 演示数据').replace('id="demo-banner" class="notice demo" hidden','id="demo-banner" class="notice demo"')
                    body=html.encode('utf-8')
                self.send_body(200,body,mime)
            except OSError:self.error('STATIC_UNAVAILABLE',503)

        do_HEAD=do_GET
        def do_POST(self):self.error('READ_ONLY',405)
        do_PUT=do_POST
        do_DELETE=do_POST
        do_PATCH=do_POST
        do_OPTIONS=do_POST
    return Handler


def main():
    parser=argparse.ArgumentParser(description='只读行情研究监控；不会启动采集器')
    parser.add_argument('--mode',choices=('live','demo'),default='live')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--scenario',choices=('normal','zero','rest','stale','warmup','error','skip'),default='normal',help='仅演示模式使用')
    args=parser.parse_args()
    if not 1<=args.port<=65535 or (args.mode=='live' and args.scenario!='normal'):
        parser.error('Invalid port or demo-only scenario')
    if args.mode=='demo':
        from demo import seed
        path=ROOT/'runtime'/('demo-'+uuid.uuid4().hex+'.sqlite3')
        config=seed(path,scenario=args.scenario)
        reader=Reader(path,config,mode='DEMO')
    else:reader=Reader()
    try:
        server=LocalServer(('127.0.0.1',args.port),handler_for(reader))
    except OSError:
        print('无法启动：本地端口不可用；未关闭其他程序。',file=sys.stderr)
        return 2
    print(f'http://127.0.0.1:{args.port} | '+('演示数据 DEMO' if args.mode=='demo' else '真实账本只读 · HTTP跨源研究'),flush=True)
    try:server.serve_forever()
    except KeyboardInterrupt:print('网页服务已停止；采集器保持独立。',flush=True)
    finally:server.server_close()
    return 0


if __name__=='__main__':
    sys.exit(main())
