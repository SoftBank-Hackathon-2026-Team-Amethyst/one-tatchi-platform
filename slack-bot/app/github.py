import time
from collections.abc import Callable

import httpx
import jwt

API = "https://api.github.com"
HEADERS = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}


class AppToken:
    """GitHub App 설치 토큰을 만들고 만료 전까지 재사용합니다 (토큰은 1시간짜리)."""

    def __init__(
        self,
        client_id: str,
        private_key: str,
        repository: str,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.client_id = client_id
        self.private_key = private_key
        self.repository = repository
        self.client = httpx.Client(base_url=API, headers=HEADERS, timeout=10, transport=transport)
        self._token = ""
        self._expires_at = 0.0

    def _jwt(self) -> str:
        now = int(time.time())
        payload = {"iat": now - 60, "exp": now + 540, "iss": self.client_id}
        return jwt.encode(payload, self.private_key, algorithm="RS256")

    def __call__(self) -> str:
        # 만료 5분 전에 새로 받는다
        if self._token and time.time() < self._expires_at - 300:
            return self._token
        auth = {"Authorization": f"Bearer {self._jwt()}"}
        installation = self.client.get(f"/repos/{self.repository}/installation", headers=auth)
        installation.raise_for_status()
        response = self.client.post(
            f"/app/installations/{installation.json()['id']}/access_tokens", headers=auth
        )
        response.raise_for_status()
        self._token = response.json()["token"]
        self._expires_at = time.time() + 3600
        return self._token


class GitHub:
    """대상 레포의 워크플로를 실행하고 PR을 머지하고 운영 배포를 승인합니다.
    봇은 클러스터에 직접 접근하지 않습니다."""

    def __init__(
        self,
        token: Callable[[], str],
        repository: str,
        workflow: str,
        ref: str,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.token = token
        self.repository = repository
        self.workflow = workflow
        self.ref = ref
        self.client = httpx.Client(base_url=API, headers=HEADERS, timeout=10, transport=transport)

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        response = self.client.request(
            method, path, headers={"Authorization": f"Bearer {self.token()}"}, **kwargs
        )
        response.raise_for_status()
        return response

    @property
    def runs_url(self) -> str:
        return f"https://github.com/{self.repository}/actions/workflows/{self.workflow}"

    def pull_url(self, number: int) -> str:
        return f"https://github.com/{self.repository}/pull/{number}"

    def dispatch(self, inputs: dict[str, str]) -> None:
        self._request(
            "POST",
            f"/repos/{self.repository}/actions/workflows/{self.workflow}/dispatches",
            json={"ref": self.ref, "inputs": inputs},
        )

    def merge(self, number: int, method: str) -> None:
        self._request(
            "PUT", f"/repos/{self.repository}/pulls/{number}/merge", json={"merge_method": method}
        )

    def comment(self, number: int, body: str) -> None:
        self._request(
            "POST", f"/repos/{self.repository}/issues/{number}/comments", json={"body": body}
        )

    def run_head_sha(self, run_id: int) -> str:
        return self._request("GET", f"/repos/{self.repository}/actions/runs/{run_id}").json()[
            "head_sha"
        ]

    def commit_comment(self, sha: str, body: str) -> None:
        self._request(
            "POST", f"/repos/{self.repository}/commits/{sha}/comments", json={"body": body}
        )

    def run_url(self, run_id: int) -> str:
        return f"https://github.com/{self.repository}/actions/runs/{run_id}"

    def approve_pull(self, number: int, user_token: str, body: str) -> None:
        # 사용자 토큰(user-to-server)으로 제출해야 CODEOWNERS 리뷰로 인정된다.
        # 봇 토큰을 쓰지 않는다.
        response = self.client.post(
            f"/repos/{self.repository}/pulls/{number}/reviews",
            headers={"Authorization": f"Bearer {user_token}"},
            json={"event": "APPROVE", "body": body},
        )
        response.raise_for_status()

    def review_protection_rule(
        self, run_id: int, environment: str, state: str, comment: str
    ) -> None:
        # 봇이 등록된 custom deployment protection rule만 처리할 수 있다 (Deployments 쓰기 권한).
        self._request(
            "POST",
            f"/repos/{self.repository}/actions/runs/{run_id}/deployment_protection_rule",
            json={"environment_name": environment, "state": state, "comment": comment},
        )


def error_message(error: httpx.HTTPError, limit: int = 300) -> str:
    """GitHub 오류 응답의 message를 사람에게 보여 줄 한 줄로 만든다. 없으면 빈 문자열."""
    if not isinstance(error, httpx.HTTPStatusError):
        return ""
    try:
        message = error.response.json().get("message", "")
    except ValueError:
        return ""
    message = " ".join(str(message).split())
    return message[:limit]
