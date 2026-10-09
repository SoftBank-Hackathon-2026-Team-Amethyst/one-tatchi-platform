import json

import httpx
import pytest

from app.approvals import Approvals, NotWaitingError, approval_marker
from app.github import GitHub
from app.rollout import NotAllowedError


def make_approvals(
    requests: list[httpx.Request],
    allowed: list[str],
    statuses: list[int],
    comment_status: int = 201,
) -> Approvals:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path.endswith("/deployment_protection_rule"):
            return httpx.Response(statuses.pop(0) if statuses else 204)
        if request.method == "GET":
            return httpx.Response(200, json={"head_sha": "abc123"})
        return httpx.Response(comment_status)

    github = GitHub(
        lambda: "token", "owner/repo", "rollout.yml", "main", httpx.MockTransport(handler)
    )
    return Approvals(github, allowed, attempts=3, interval=0, sleep=lambda _: None)


def test_approve_reviews_protection_rule_with_requester() -> None:
    requests: list[httpx.Request] = []
    make_approvals(requests, [], []).request("approve", "123@prod", "U1", "soul")

    review, run, comment = requests
    assert (review.method, review.url.path) == (
        "POST",
        "/repos/owner/repo/actions/runs/123/deployment_protection_rule",
    )
    body = json.loads(review.content)
    assert body["environment_name"] == "prod"
    assert body["state"] == "approved"
    assert "slack:soul(U1)" in body["comment"]
    # 승인자는 API로 다시 읽을 수 없어서 배포하는 커밋에 표지를 남긴다 (deploy.yml이 읽음)
    assert (run.method, run.url.path) == ("GET", "/repos/owner/repo/actions/runs/123")
    assert (comment.method, comment.url.path) == (
        "POST",
        "/repos/owner/repo/commits/abc123/comments",
    )
    assert (
        approval_marker(123, "prod", "approved", "slack:soul(U1)")
        in json.loads(comment.content)["body"]
    )


def test_marker_format() -> None:
    assert approval_marker(123, "prod", "approved", "slack:soul(U1)") == (
        "<!-- one-tatchi-approval run=123 environment=prod state=approved by=slack:soul(U1) -->"
    )


def test_approval_succeeds_even_if_record_fails() -> None:
    requests: list[httpx.Request] = []
    make_approvals(requests, [], [], comment_status=403).request(
        "approve", "123@prod", "U1", "soul"
    )
    assert len(requests) == 3


def test_reject() -> None:
    requests: list[httpx.Request] = []
    make_approvals(requests, [], []).request("reject", "123@prod", "U1", "soul")
    assert json.loads(requests[0].content)["state"] == "rejected"


def test_retries_until_waiting() -> None:
    # 알림은 배포 job이 승인 대기에 들어가기 직전에 나간다
    requests: list[httpx.Request] = []
    make_approvals(requests, [], [422, 204]).request("approve", "123@prod", "U1", "soul")
    reviews = [r for r in requests if r.url.path.endswith("/deployment_protection_rule")]
    assert len(reviews) == 2


def test_not_waiting_after_retries() -> None:
    requests: list[httpx.Request] = []
    with pytest.raises(NotWaitingError):
        make_approvals(requests, [], [422, 422, 422]).request("approve", "123@prod", "U1", "soul")
    assert len(requests) == 3


def test_rejects_user_not_allowed() -> None:
    requests: list[httpx.Request] = []
    with pytest.raises(NotAllowedError):
        make_approvals(requests, ["U1"], []).request("approve", "123@prod", "U2", "other")
    assert requests == []


@pytest.mark.parametrize("value", ["prod", "abc@prod", "123@", "123"])
def test_parse_rejects_bad_value(value: str) -> None:
    with pytest.raises(ValueError):
        Approvals.parse(value)
