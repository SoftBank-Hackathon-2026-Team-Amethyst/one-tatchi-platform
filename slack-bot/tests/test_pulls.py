import json

import httpx
import pytest

from app.github import GitHub
from app.pulls import Merges
from app.rollout import NotAllowedError


def make_merges(
    requests: list[httpx.Request], allowed: list[str], merge_status: int = 200
) -> Merges:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(merge_status if request.method == "PUT" else 201)

    github = GitHub(
        lambda: "token", "owner/repo", "rollout.yml", "main", httpx.MockTransport(handler)
    )
    return Merges(github, allowed, "squash")


def test_merge_then_comment_requester() -> None:
    requests: list[httpx.Request] = []
    make_merges(requests, []).request(12, "U1", "soul")

    merge, comment = requests
    assert (merge.method, merge.url.path) == ("PUT", "/repos/owner/repo/pulls/12/merge")
    assert json.loads(merge.content) == {"merge_method": "squash"}
    assert (comment.method, comment.url.path) == ("POST", "/repos/owner/repo/issues/12/comments")
    assert "slack:soul(U1)" in json.loads(comment.content)["body"]


def test_merge_rejects_user_not_allowed() -> None:
    requests: list[httpx.Request] = []
    with pytest.raises(NotAllowedError):
        make_merges(requests, ["U1"]).request(12, "U2", "other")
    assert requests == []


def test_merge_failure_does_not_comment() -> None:
    # 필수 검사 미통과 · 충돌이면 GitHub이 405 · 409를 준다
    requests: list[httpx.Request] = []
    with pytest.raises(httpx.HTTPStatusError):
        make_merges(requests, [], merge_status=405).request(12, "U1", "soul")
    assert [r.method for r in requests] == ["PUT"]
