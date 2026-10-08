import logging
import re
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from app.config import Settings
from app.github import AppToken, GitHub
from app.pulls import Merges
from app.rollout import ACTIONS, NotAllowedError, RolloutRequest, Rollouts, parse_command

logger = logging.getLogger(__name__)


def attempt(call: Callable[[], None], failure: str) -> str | None:
    """조작을 실행하고, 실패하면 사용자에게 보여 줄 문장을 돌려줍니다."""
    try:
        call()
    except NotAllowedError:
        return "이 조작을 실행할 권한이 없어요."
    except httpx.HTTPError:
        logger.exception(failure)
        return f"{failure}. 잠시 후 다시 시도해 주세요."
    return None


def close_buttons(body: dict, respond, text: str) -> None:
    # 같은 요청이 두 번 실행되지 않도록 버튼을 요청 기록으로 바꿉니다.
    message = body["message"]
    blocks = [block for block in message["blocks"] if block["type"] != "actions"]
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": text}]})
    respond(text=message.get("text", text), blocks=blocks, replace_original=True)


def build_app(token: str, rollouts: Rollouts, merges: Merges) -> App:
    app = App(token=token)

    def rollout(request: RolloutRequest, user_id: str, user_name: str) -> tuple[bool, str]:
        error = attempt(
            lambda: rollouts.request(request, user_id, user_name), "워크플로를 실행하지 못했어요"
        )
        if error:
            return False, error
        return True, (
            f"<@{user_id}> 님이 `{request.action}`(`{request.label}`)을 요청했어요. "
            f"<{rollouts.github.runs_url}|실행 목록 보기>"
        )

    @app.command("/rollout")
    def on_command(ack, command, respond):
        ack()
        try:
            request = parse_command(command.get("text", ""))
        except ValueError as error:
            respond(str(error))
            return
        ok, text = rollout(request, command["user_id"], command["user_name"])
        respond(text, response_type="in_channel" if ok else "ephemeral")

    # 버튼은 .github/actions/slack-notify가 만듭니다.
    # action_id는 rollout_<action>, value는 <서비스|all>@<대상>.<환경>입니다.
    @app.action(re.compile(rf"^rollout_({'|'.join(ACTIONS)})$"))
    def on_rollout_button(ack, action, body, respond):
        ack()
        user = body["user"]
        try:
            request = RolloutRequest.parse(
                action["action_id"].removeprefix("rollout_"), action["value"]
            )
        except ValueError:
            respond("버튼 값이 올바르지 않아요.", response_type="ephemeral", replace_original=False)
            return
        ok, text = rollout(request, user["id"], user.get("username", user["id"]))
        if not ok:
            respond(text, response_type="ephemeral", replace_original=False)
            return
        close_buttons(body, respond, text)

    # action_id는 pr_merge, value는 대상 레포의 PR 번호입니다.
    @app.action("pr_merge")
    def on_merge_button(ack, action, body, respond):
        ack()
        user = body["user"]
        number = int(action["value"])
        error = attempt(
            lambda: merges.request(number, user["id"], user.get("username", user["id"])),
            "PR을 머지하지 못했어요 (검사 통과 · 충돌 여부를 확인해 주세요)",
        )
        if error:
            respond(error, response_type="ephemeral", replace_original=False)
            return
        close_buttons(
            body,
            respond,
            f"<@{user['id']}> 님이 <{merges.github.pull_url(number)}|PR #{number}>을 머지했어요.",
        )

    return app


class Health(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        ok = self.path == "/health" and self.server.is_connected()
        self.send_response(200 if ok else 503)
        self.end_headers()

    def log_message(self, format: str, *args) -> None:
        pass


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = Settings()
    if settings.github_app_client_id:
        token = AppToken(
            settings.github_app_client_id,
            settings.github_app_private_key,
            settings.github_repository,
        )
    else:
        token = lambda: settings.github_token  # noqa: E731
    github = GitHub(
        token, settings.github_repository, settings.rollout_workflow, settings.github_ref
    )
    app = build_app(
        settings.slack_bot_token,
        Rollouts(github, settings.allowed_user_ids),
        Merges(github, settings.allowed_user_ids, settings.merge_method),
    )

    # Socket Mode는 봇이 Slack으로 연결을 거는 방식이라 공개 엔드포인트가 필요 없습니다.
    handler = SocketModeHandler(app, settings.slack_app_token)
    handler.connect()

    # App Chart의 프로브가 HTTP를 요구해서 헬스체크만 따로 엽니다.
    server = ThreadingHTTPServer(("0.0.0.0", settings.port), Health)
    server.is_connected = handler.client.is_connected
    server.serve_forever()


if __name__ == "__main__":
    main()
