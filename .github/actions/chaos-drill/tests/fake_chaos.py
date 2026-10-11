"""장애 훈련 테스트용 가짜 BE 파드. 사용: python3 fake_chaos.py <키>
demo-app의 /api/chaos와 같은 동작을 흉내 낸다. 상태는 FAKE_CHAOS_DIR/<키>.json에 두어
port-forward마다 새 프로세스가 떠도 파드의 메모리 상태처럼 이어진다.

환경변수
  FAKE_CHAOS_DIR       상태 파일 폴더 (필수)
  FAKE_CHAOS_DISABLED  쉼표로 구분한 키 또는 all. CHAOS_ENABLED가 꺼진 파드: enabled false, POST는 404
  FAKE_CHAOS_STUCK     쉼표로 구분한 키. reset이 장애를 풀지 못하는 파드 (해제 확인 실패 테스트)
  FAKE_INFO_FAIL       쉼표로 구분한 키. /api/info가 500 (blue 에러율 테스트)

바인드한 뒤 kubectl port-forward와 같은 형식으로 알린다.  Forwarding from 127.0.0.1:<포트> -> 8000
"""

import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

KEY = sys.argv[1]
STATE = os.path.join(os.environ["FAKE_CHAOS_DIR"], f"{KEY}.json")
ZERO = {"latencyMs": 0, "errorRate": 0, "dbError": False}


def listed(var):
    v = os.environ.get(var, "")
    return v == "all" or KEY in [x for x in v.split(",") if x]


ENABLED = not listed("FAKE_CHAOS_DISABLED")
STUCK = listed("FAKE_CHAOS_STUCK")
INFO_FAIL = listed("FAKE_INFO_FAIL")


def load():
    try:
        with open(STATE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return dict(ZERO)


def save(state):
    with open(STATE, "w") as f:
        json.dump(state, f)


class Handler(BaseHTTPRequestHandler):
    def _send(self, status, body):
        data = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _read(self):
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length) or b"{}") if length else {}

    def do_GET(self):
        if self.path == "/api/chaos":
            return self._send(200, {**load(), "enabled": ENABLED})
        if self.path == "/health":
            return self._send(200, {"status": "ok", "database": "connected"})
        if self.path == "/api/info":
            if INFO_FAIL:
                return self._send(500, {"error": "boom"})
            return self._send(200, {"dbConnected": True})
        return self._send(200, {})

    def do_POST(self):
        body = self._read()
        if self.path == "/api/chaos" and ENABLED:
            state = load()
            if isinstance(body.get("latencyMs"), (int, float)):
                state["latencyMs"] = max(0, body["latencyMs"])
            if isinstance(body.get("errorRate"), (int, float)):
                state["errorRate"] = min(1, max(0, body["errorRate"]))
            if isinstance(body.get("dbError"), bool):
                state["dbError"] = body["dbError"]
            save(state)
            return self._send(200, {**state, "enabled": ENABLED})
        if self.path == "/api/chaos/reset" and ENABLED:
            if not STUCK:
                save(dict(ZERO))
            return self._send(200, {**load(), "enabled": ENABLED})
        if self.path.startswith("/api/chaos"):
            return self._send(404, {"message": "Route not found"})
        return self._send(201 if body else 400, {})

    def log_message(self, *args):
        pass


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
print(f"Forwarding from 127.0.0.1:{server.server_address[1]} -> 8000", flush=True)
server.serve_forever()
