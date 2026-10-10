import httpx

from app.github import GitHub
from app.links import Links
from app.rollout import check_allowed, requester


class NotLinkedError(Exception):
    """Slack 사용자에 연결된 GitHub 계정이 없다(또는 토큰이 더 이상 유효하지 않다)."""


class Reviews:
    """janto PR 알림의 리뷰 승인 버튼. 봇(GitHub App)의 리뷰는 CODEOWNERS 조건을 채우지 못하므로,
    버튼을 누른 사람이 연결해 둔 GitHub 계정으로 Approve 리뷰를 제출한다."""

    def __init__(self, github: GitHub, links: Links, allowed_user_ids: list[str]) -> None:
        self.github = github
        self.links = links
        self.allowed_user_ids = allowed_user_ids

    def request(self, number: int, user_id: str, user_name: str) -> str:
        """승인 리뷰를 남기고 사용한 GitHub 로그인을 돌려준다."""
        check_allowed(self.allowed_user_ids, user_id)
        link = self.links.get(user_id)
        if link is None:
            raise NotLinkedError(user_id)
        body = f"Slack에서 `{requester(user_id, user_name)}`이 승인했다."
        try:
            self.github.approve_pull(number, link.access_token, body)
        except httpx.HTTPStatusError as error:
            if error.response.status_code == 401:
                # 토큰이 취소 · 만료됐다. 연결을 지우고 다시 연결하게 한다.
                self.links.forget(user_id)
                raise NotLinkedError(user_id) from error
            raise
        return link.login
