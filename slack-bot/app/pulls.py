from app.github import GitHub
from app.rollout import check_allowed, requester


class Merges:
    """janto PR 알림의 머지 버튼. 머지 규칙(필수 검사 등)은 GitHub 브랜치 보호가 그대로 지킨다."""

    def __init__(self, github: GitHub, allowed_user_ids: list[str], method: str) -> None:
        self.github = github
        self.allowed_user_ids = allowed_user_ids
        self.method = method

    def request(self, number: int, user_id: str, user_name: str) -> None:
        check_allowed(self.allowed_user_ids, user_id)
        self.github.merge(number, self.method)
        # 머지한 주체는 봇이라, 버튼을 누른 사람을 PR에 남긴다.
        self.github.comment(number, f"Slack에서 `{requester(user_id, user_name)}`이 머지했다.")
