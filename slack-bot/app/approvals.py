import time
from collections.abc import Callable

import httpx

from app.github import GitHub
from app.rollout import check_allowed, requester

# 승인 버튼 value: <워크플로 실행 ID>@<GitHub environment> (예: 123456@prod)
STATES = {"approve": "approved", "reject": "rejected"}


class NotWaitingError(Exception):
    pass


class Approvals:
    """운영 승인 · 거절 버튼. 봇(GitHub App)이 대상 레포 prod environment의 custom deployment
    protection rule로 등록돼 있어야 한다. 승인 대기 알림은 배포 job이 승인 대기에 들어가기 직전에
    나가므로, 아직 대기 전이면 잠시 기다렸다가 다시 시도한다."""

    def __init__(
        self,
        github: GitHub,
        allowed_user_ids: list[str],
        attempts: int = 6,
        interval: float = 5,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.github = github
        self.allowed_user_ids = allowed_user_ids
        self.attempts = attempts
        self.interval = interval
        self.sleep = sleep

    @staticmethod
    def parse(value: str) -> tuple[int, str]:
        run_id, _, environment = value.partition("@")
        if not run_id.isdigit() or not environment:
            raise ValueError(value)
        return int(run_id), environment

    def request(self, decision: str, value: str, user_id: str, user_name: str) -> None:
        check_allowed(self.allowed_user_ids, user_id)
        run_id, environment = self.parse(value)
        verb = "승인" if decision == "approve" else "거절"
        comment = f"Slack에서 `{requester(user_id, user_name)}`이 {verb}했다."
        for attempt in range(self.attempts):
            try:
                self.github.review_protection_rule(run_id, environment, STATES[decision], comment)
                return
            except httpx.HTTPStatusError as error:
                # 아직 승인 대기 전이거나 이미 처리된 실행이면 422
                if error.response.status_code != 422:
                    raise
                if attempt == self.attempts - 1:
                    raise NotWaitingError(run_id) from error
                self.sleep(self.interval)
