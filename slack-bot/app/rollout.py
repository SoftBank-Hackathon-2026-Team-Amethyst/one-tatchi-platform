import re
from dataclasses import dataclass

from app.github import GitHub

# rollout 워크플로(workflow_dispatch)의 action 선택지와 같아야 합니다.
ACTIONS = ("promote", "abort", "undo")

# 버튼 value와 /rollout 대상: <서비스|all>@<배포 대상>.<환경> (예: demo-app-be@aws.test)
# slack-notify가 알림의 target을 그대로 버튼 value로 넣는다.
TARGET = re.compile(
    r"^(?P<release>[a-z0-9][a-z0-9-]*)@(?P<target>[a-z0-9-]+)\.(?P<environment>[a-z0-9-]+)$"
)

USAGE = (
    f"사용법: `/rollout <{'|'.join(ACTIONS)}> <서비스|all>@<대상>.<환경>` "
    "(예: `/rollout promote all@aws.test`)"
)


class NotAllowedError(Exception):
    pass


def check_allowed(allowed_user_ids: list[str], user_id: str) -> None:
    if allowed_user_ids and user_id not in allowed_user_ids:
        raise NotAllowedError(user_id)


def requester(user_id: str, user_name: str) -> str:
    # 워크플로 실행자는 봇(GitHub App)이라, 실제 요청자를 감사 로그에 따로 남깁니다.
    return f"slack:{user_name}({user_id})"


@dataclass(frozen=True)
class RolloutRequest:
    action: str
    release: str
    target: str
    environment: str

    @classmethod
    def parse(cls, action: str, value: str) -> "RolloutRequest":
        match = TARGET.match(value)
        if action not in ACTIONS or not match:
            raise ValueError(USAGE)
        return cls(action, **match.groupdict())

    @property
    def label(self) -> str:
        return f"{self.release}@{self.target}.{self.environment}"


def parse_command(text: str) -> RolloutRequest:
    args = text.split()
    if len(args) != 2:
        raise ValueError(USAGE)
    return RolloutRequest.parse(*args)


class Rollouts:
    def __init__(self, github: GitHub, allowed_user_ids: list[str]) -> None:
        self.github = github
        self.allowed_user_ids = allowed_user_ids

    def request(self, request: RolloutRequest, user_id: str, user_name: str) -> None:
        check_allowed(self.allowed_user_ids, user_id)
        self.github.dispatch(
            {
                "action": request.action,
                "release": request.release,
                "target": request.target,
                "environment": request.environment,
                "requested_by": requester(user_id, user_name),
            }
        )
