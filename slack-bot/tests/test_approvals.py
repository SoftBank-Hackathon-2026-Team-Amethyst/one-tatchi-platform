import json

import httpx
import pytest

from app.approvals import Approvals, NotWaitingError
from app.github import GitHub
from app.rollout import NotAllowedError


def make_approvals(
    requests: list[httpx.Request], allowed: list[str], statuses: list[int]
) -> Approvals:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(statuses.pop(0) if statuses else 204)

    github = GitHub(
        lambda: "token", "owner/repo", "rollout.yml", "main", httpx.MockTransport(handler)
    )
    return Approvals(github, allowed, attempts=3, interval=0, sleep=lambda _: None)


def test_approve_reviews_protection_rule_with_requester() -> None:
    requests: list[httpx.Request] = []
    make_approvals(requests, [], []).request("approve", "123@prod", "U1", "soul")

    (review,) = requests
    assert (review.method, review.url.path) == (
        "POST",
        "/repos/owner/repo/actions/runs/123/deployment_protection_rule",
    )
    body = json.loads(review.content)
    assert body["environment_name"] == "prod"
    assert body["state"] == "approved"
    assert "slack:soul(U1)" in body["comment"]


def test_reject() -> None:
    requests: list[httpx.Request] = []
    make_approvals(requests, [], []).request("reject", "123@prod", "U1", "soul")
    assert json.loads(requests[0].content)["state"] == "rejected"


def test_retries_until_waiting() -> None:
    # 알림은 배포 job이 승인 대기에 들어가기 직전에 나간다
    requests: list[httpx.Request] = []
    make_approvals(requests, [], [422, 204]).request("approve", "123@prod", "U1", "soul")
    assert len(requests) == 2


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
