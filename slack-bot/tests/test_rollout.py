import json

import httpx
import pytest

from app.github import GitHub
from app.rollout import NotAllowedError, RolloutRequest, Rollouts, parse_command


def make_github(requests: list[httpx.Request], status: int = 204) -> GitHub:
    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(status)

    return GitHub(
        lambda: "token", "owner/repo", "rollout.yml", "main", httpx.MockTransport(handler)
    )


def test_parse_command() -> None:
    assert parse_command("promote all@aws.test") == RolloutRequest("promote", "all", "aws", "test")
    assert parse_command("undo demo-app-be@onprem.prod") == RolloutRequest(
        "undo", "demo-app-be", "onprem", "prod"
    )


@pytest.mark.parametrize(
    "text",
    ["", "promote", "deploy all@aws.test", "promote all", "promote all@aws", "promote a@b.c d"],
)
def test_parse_command_rejects_invalid(text: str) -> None:
    with pytest.raises(ValueError, match="사용법"):
        parse_command(text)


def test_button_value_is_notify_target() -> None:
    # slack-notify는 알림 target(<서비스>@<대상>.<환경>)을 버튼 value로 넣는다
    request = RolloutRequest.parse("abort", "demo-app-fe@aws.test")
    assert request.label == "demo-app-fe@aws.test"


def test_request_dispatches_workflow() -> None:
    requests: list[httpx.Request] = []
    Rollouts(make_github(requests), []).request(
        RolloutRequest("promote", "demo-app-be", "aws", "test"), "U1", "soul"
    )

    (request,) = requests
    assert request.url.path == "/repos/owner/repo/actions/workflows/rollout.yml/dispatches"
    assert request.headers["Authorization"] == "Bearer token"
    assert json.loads(request.content) == {
        "ref": "main",
        "inputs": {
            "action": "promote",
            "release": "demo-app-be",
            "target": "aws",
            "environment": "test",
            "requested_by": "slack:soul(U1)",
        },
    }


def test_request_rejects_user_not_allowed() -> None:
    requests: list[httpx.Request] = []
    rollouts = Rollouts(make_github(requests), ["U1"])
    request = RolloutRequest("promote", "all", "aws", "test")

    with pytest.raises(NotAllowedError):
        rollouts.request(request, "U2", "other")
    assert requests == []

    rollouts.request(request, "U1", "soul")
    assert len(requests) == 1


def test_request_raises_when_github_fails() -> None:
    with pytest.raises(httpx.HTTPStatusError):
        Rollouts(make_github([], status=403), []).request(
            RolloutRequest("abort", "all", "aws", "test"), "U1", "soul"
        )
