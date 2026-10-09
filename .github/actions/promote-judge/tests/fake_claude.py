"""judge 테스트용 가짜 Claude Messages API. 사용: python3 fake_claude.py <모드> <요청 저장 파일>

모드
  promote | abort  해당 decision으로 정상 응답 (앞에 thinking 블록 포함)
  err500           HTTP 500
  slow             5초 늦게 정상 응답
  badjson          text 블록이 스키마에 맞지 않음
  refusal          stop_reason: refusal

바인드한 뒤 첫 줄에 "listening 127.0.0.1:<포트>"를 출력한다.
받은 요청(헤더 일부 + 본문)은 <요청 저장 파일>에 JSON으로 남긴다.
"""

import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODE, CAPTURE = sys.argv[1], sys.argv[2]


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        with open(CAPTURE, "w") as f:
            json.dump({
                "path": self.path,
                "api_key": self.headers.get("x-api-key"),
                "version": self.headers.get("anthropic-version"),
                "beta": self.headers.get("anthropic-beta"),
                "body": json.loads(body),
            }, f)
        if MODE == "err500":
            return self._send(500, {"type": "error", "error": {"type": "api_error", "message": "boom"}})
        if MODE == "slow":
            time.sleep(5)
        stop = "refusal" if MODE == "refusal" else "end_turn"
        if MODE == "badjson":
            text = json.dumps({"decision": "maybe"})
        else:
            decision = "abort" if MODE == "abort" else "promote"
            text = json.dumps({"decision": decision, "reason": f"가짜 판단: {decision}"}, ensure_ascii=False)
        self._send(200, {
            "type": "message", "role": "assistant", "stop_reason": stop,
            "content": [{"type": "thinking", "thinking": ""}, {"type": "text", "text": text}],
        })

    def _send(self, status, payload):
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *args):
        pass


server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
print(f"listening 127.0.0.1:{server.server_address[1]}", flush=True)
server.serve_forever()
