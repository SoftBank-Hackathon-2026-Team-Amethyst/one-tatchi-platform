"""diagnose 테스트용 가짜 Claude Messages API. 사용: python3 fake_claude.py <모드> <요청 저장 파일>

모드
  ok         정상 요약 (앞에 thinking 블록 포함)
  long       상한을 넘는 요약 · 근거 · 조치
  secret     요약에 비밀값 형태가 섞임
  err500     HTTP 500
  slow       3초 늦게 정상 응답
  badjson    text 블록이 형식에 맞지 않음 (알 수 없는 분류)
  notjson    text 블록이 JSON이 아님
  refusal    stop_reason: refusal
  max_tokens stop_reason: max_tokens

바인드한 뒤 첫 줄에 "listening 127.0.0.1:<포트>"를 출력한다. 받은 요청(헤더 일부 + 본문)은 <요청 저장 파일>에 남긴다.
"""

import json
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODE, CAPTURE = sys.argv[1], sys.argv[2]

ANSWER = {
    "category": "migration",
    "summary": "demo-app-be의 마이그레이션 Job이 3번 실패해 helm upgrade가 중단됐다.",
    "evidence": ["Error: UPGRADE FAILED: pre-upgrade hooks failed: resource Job/test/demo-app-be-migration not ready."],
    "actions": ["kubectl -n test logs job/demo-app-be-migration 로 전체 오류 확인"],
    "confidence": "high",
}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        with open(CAPTURE, "w") as f:
            json.dump({"path": self.path, "api_key": self.headers.get("x-api-key"),
                       "version": self.headers.get("anthropic-version"), "beta": self.headers.get("anthropic-beta"),
                       "body": json.loads(body)}, f, ensure_ascii=False)
        if MODE == "err500":
            return self._send(500, {"type": "error", "error": {"type": "api_error", "message": "boom"}})
        if MODE == "slow":
            time.sleep(3)
        answer = dict(ANSWER)
        if MODE == "long":
            answer.update(summary="가" * 900, evidence=[f"줄{i} " + "x" * 500 for i in range(12)],
                          actions=[f"조치{i} " + "y" * 400 for i in range(9)] + [" "])
        elif MODE == "secret":
            answer["summary"] = "DATABASE_URL=postgresql://app:Leaked1Pass@db:5432/app 로 접속하지 못했다."
        elif MODE == "badjson":
            answer["category"] = "network"
        text = "{요약" if MODE == "notjson" else json.dumps(answer, ensure_ascii=False)
        stop = {"refusal": "refusal", "max_tokens": "max_tokens"}.get(MODE, "end_turn")
        self._send(200, {"type": "message", "role": "assistant", "stop_reason": stop,
                         "content": [{"type": "thinking", "thinking": ""}, {"type": "text", "text": text}]})

    def _send(self, status, payload):
        data = json.dumps(payload, ensure_ascii=False).encode()
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
