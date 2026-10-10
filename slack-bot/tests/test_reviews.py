import json

import httpx
import pytest

from app.github import GitHub
from app.links import DeviceFlow, Link, Links, LinkStore
from app.reviews import NotLinkedError, Reviews
from app.rollout import NotAllowedError


def make_reviews(
    requests: list[httpx.Request], allowed: list[str], review_status: int = 200
) -> Reviews:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            review_status, json={"message": "Can not approve your own pull request"}
        )

    github = GitHub(
        lambda: "bot-token", "owner/repo", "rollout.yml", "main", httpx.MockTransport(handler)
    )
    links = Links(LinkStore(""), DeviceFlow("Iv-client"), run_in_background=lambda call: None)
    return Reviews(github, links, allowed)


def test_approve_uses_linked_user_token() -> None:
    requests: list[httpx.Request] = []
    reviews = make_reviews(requests, [])
    reviews.links.store.put("U1", Link("soulee-dev", "ghu_user"))

    assert reviews.request(52, "U1", "soul") == "soulee-dev"
    (review,) = requests
    assert (review.method, review.url.path) == ("POST", "/repos/owner/repo/pulls/52/reviews")
    assert review.headers["Authorization"] == "Bearer ghu_user"  # 봇 토큰이 아니다
    body = json.loads(review.content)
    assert body["event"] == "APPROVE"
    assert "slack:soul(U1)" in body["body"]


def test_not_linked_raises_without_calling_github() -> None:
    requests: list[httpx.Request] = []
    with pytest.raises(NotLinkedError):
        make_reviews(requests, []).request(52, "U1", "soul")
    assert requests == []


def test_rejects_user_not_allowed() -> None:
    requests: list[httpx.Request] = []
    with pytest.raises(NotAllowedError):
        make_reviews(requests, ["U1"]).request(52, "U2", "other")
    assert requests == []


def test_revoked_token_forgets_link() -> None:
    requests: list[httpx.Request] = []
    reviews = make_reviews(requests, [], review_status=401)
    reviews.links.store.put("U1", Link("soulee-dev", "ghu_old"))
    with pytest.raises(NotLinkedError):
        reviews.request(52, "U1", "soul")
    assert reviews.links.get("U1") is None


def test_other_github_errors_surface() -> None:
    # 작성자 본인 승인 등은 422로 거부되고, 사유는 attempt()가 사용자에게 보여 준다
    requests: list[httpx.Request] = []
    reviews = make_reviews(requests, [], review_status=422)
    reviews.links.store.put("U1", Link("silano08", "ghu_user"))
    with pytest.raises(httpx.HTTPStatusError):
        reviews.request(52, "U1", "gayeon")
    assert reviews.links.get("U1") is not None
