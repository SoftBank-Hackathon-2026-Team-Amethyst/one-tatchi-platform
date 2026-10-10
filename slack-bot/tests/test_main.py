import httpx

from app.github import error_message
from app.main import attempt


def status_error(status: int, body: dict | str) -> httpx.HTTPStatusError:
    request = httpx.Request("PUT", "https://api.github.com/repos/o/r/pulls/52/merge")
    response = (
        httpx.Response(status, json=body, request=request)
        if isinstance(body, dict)
        else httpx.Response(status, text=body, request=request)
    )
    return httpx.HTTPStatusError("boom", request=request, response=response)


def test_error_message_flattens_github_reason() -> None:
    error = status_error(
        405,
        {
            "message": "Repository rule violations found\n\n"
            "Waiting on code owner review from baejun10 and/or soulee-dev.\n\n"
        },
    )
    assert error_message(error) == (
        "Repository rule violations found "
        "Waiting on code owner review from baejun10 and/or soulee-dev."
    )
    assert error_message(status_error(500, "<html>")) == ""
    assert error_message(httpx.ConnectError("down")) == ""


def test_attempt_shows_github_reason() -> None:
    def fail() -> None:
        raise status_error(405, {"message": "Waiting on code owner review from soulee-dev."})

    assert attempt(fail, "PR을 머지하지 못했어요") == (
        "PR을 머지하지 못했어요. GitHub: Waiting on code owner review from soulee-dev."
    )

    def fail_plain() -> None:
        raise status_error(502, "bad gateway")

    assert attempt(fail_plain, "PR을 머지하지 못했어요") == (
        "PR을 머지하지 못했어요. 잠시 후 다시 시도해 주세요."
    )
