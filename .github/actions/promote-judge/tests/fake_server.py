"""smoke 테스트용 가짜 green. 사용: python3 fake_server.py <모드> [--forward-line]

모드
  ok      모든 경로 200 (POST는 201). /health는 {"status":"ok","database":"connected"}, /api/info는 {"dbConnected":true}
  fail    /api/info만 500, 나머지는 ok와 같음
  slow    모든 요청을 3초 늦게 200
  memory  DB가 안 붙은 green. 상태 코드는 ok와 같지만 /health는 database=fallback-memory, /api/info는 dbConnected=false
  text    /health가 JSON이 아닌 본문("OK")으로 200

포트는 비어 있는 것을 고른다. 바인드한 뒤 첫 줄에 kubectl port-forward와 같은 형식으로 알린다.
  Forwarding from 127.0.0.1:<포트> -> 8000
"""

import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODE = sys.argv[1] if len(sys.argv) > 1 else "ok"


class Handler(BaseHTTPRequestHandler):
    def _reply(self, ok_status):
        if MODE == "slow":
            time.sleep(3)
        status = 500 if MODE == "fail" and self.path == "/api/info" else ok_status
        length = int(self.headers.get("Content-Length") or 0)
        if length:
            self.rfile.read(length)
        body = self._body()
        self.send_response(status)
        self.send_header("Content-Type", "text/plain" if MODE == "text" else "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self):
        connected = MODE != "memory"
        if self.path == "/health":
            if MODE == "text":
                return b"OK"
            return json.dumps({"status": "ok" if connected else "degraded",
                               "database": "connected" if connected else "fallback-memory"}).encode()
        if self.path == "/api/info":
            return json.dumps({"dbConnected": connected, "version": "v1"}).encode()
        return b"{}"

    def do_GET(self):
        self._reply(200)

    def do_POST(self):
        self._reply(201)

    def log_message(self, *args):
        pass


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
print(f"Forwarding from 127.0.0.1:{server.server_address[1]} -> 8000", flush=True)
server.serve_forever()
