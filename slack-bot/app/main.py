import logging
import re
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import httpx
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from app.approvals import Approvals, NotWaitingError
from app.config import Settings
from app.github import AppToken, GitHub, error_message
from app.links import DeviceFlow, Links, LinkStore
from app.pulls import Merges
from app.reviews import NotLinkedError, Reviews
from app.rollout import ACTIONS, NotAllowedError, RolloutRequest, Rollouts, parse_command

logger = logging.getLogger(__name__)


def attempt(call: Callable[[], None], failure: str) -> str | None:
    """조작을 실행하고, 실패하면 사용자에게 보여 줄 문장을 돌려줍니다."""
    try:
        call()
    except NotAllowedError:
        return "이 조작을 실행할 권한이 없어요."
    except NotWaitingError:
        return "승인 대기 중인 배포가 없어요. 이미 처리됐거나 아직 대기 전이에요."
    except httpx.HTTPError as error:
        logger.exception(failure)
        # GitHub이 거부한 이유(필수 리뷰 · 검사 · 충돌 등)를 그대로 보여 준다.
        # 숨기면 원인을 찾을 수 없다.
        reason = error_message(error)
        if reason:
            return f"{failure}. GitHub: {reason}"
        return f"{failure}. 잠시 후 다시 시도해 주세요."
    return None


def add_context(body: dict, respond, text: str) -> None:
    # 버튼은 남기고(머지가 아직 남았다) 처리 기록만 덧붙입니다.
    message = body["message"]
    blocks = [block for block in message["blocks"] if block["type"] != "actions"]
    actions = [block for block in message["blocks"] if block["type"] == "actions"]
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": text}]})
    respond(text=message.get("text", text), blocks=blocks + actions, replace_original=True)


def close_buttons(body: dict, respond, text: str) -> None:
    # 같은 요청이 두 번 실행되지 않도록 버튼을 요청 기록으로 바꿉니다.
    message = body["message"]
    blocks = [block for block in message["blocks"] if block["type"] != "actions"]
    blocks.append({"type": "context", "elements": [{"type": "mrkdwn", "text": text}]})
    respond(text=message.get("text", text), blocks=blocks, replace_original=True)


def build_app(
    token: str,
    rollouts: Rollouts,
    merges: Merges,
    approvals: Approvals,
    reviews: Reviews | None = None,
) -> App:
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
            "PR을 머지하지 못했어요",
        )
        if error:
            respond(error, response_type="ephemeral", replace_original=False)
            return
        close_buttons(
            body,
            respond,
            f"<@{user['id']}> 님이 <{merges.github.pull_url(number)}|PR #{number}>을 머지했어요.",
        )

    # 리뷰 승인. action_id는 pr_approve, value는 PR 번호.
    # 누른 사람의 GitHub 계정으로 Approve 리뷰를 남깁니다
    # (CODEOWNERS 리뷰는 봇 신원으로는 인정되지 않습니다).
    # 연결이 없으면 device flow 안내를 보냅니다.
    @app.action("pr_approve")
    def on_review_button(ack, action, body, respond):
        ack()
        if reviews is None:
            respond(
                "리뷰 승인 버튼이 설정되지 않았어요.",
                response_type="ephemeral",
                replace_original=False,
            )
            return
        user = body["user"]
        number = int(action["value"])
        name = user.get("username", user["id"])
        ephemeral = lambda text: respond(text, response_type="ephemeral", replace_original=False)  # noqa: E731
        login = ""

        def approve() -> None:
            nonlocal login
            login = reviews.request(number, user["id"], name)

        try:
            error = attempt(approve, "PR을 승인하지 못했어요")
        except NotLinkedError:
            ephemeral(reviews.links.begin(user["id"], ephemeral))
            return
        if error:
            ephemeral(error)
            return
        add_context(
            body,
            respond,
            f"<@{user['id']}> 님이 GitHub `{login}` 계정으로 "
            f"<{reviews.github.pull_url(number)}|PR #{number}>을 승인했어요. "
            "이제 머지할 수 있어요.",
        )

    # GitHub 계정 연결을 미리 해 두는 명령 (manifest.yaml의 /github-link).
    @app.command("/github-link")
    def on_link_command(ack, command, respond):
        ack()
        if reviews is None:
            respond("리뷰 승인 버튼이 설정되지 않았어요.")
            return
        link = reviews.links.get(command["user_id"])
        if link and command.get("text", "").strip() != "reset":
            respond(
                f"이미 GitHub `{link.login}` 계정이 연결돼 있어요. "
                "다시 연결하려면 `/github-link reset`."
            )
            return
        reviews.links.forget(command["user_id"])
        respond(reviews.links.begin(command["user_id"], respond))

    # 운영 승인 · 거절. action_id는 deploy_<approve|reject>, value는 <실행 ID>@<environment>입니다.
    @app.action(re.compile(r"^deploy_(approve|reject)$"))
    def on_approval_button(ack, action, body, respond):
        ack()
        user = body["user"]
        decision = action["action_id"].removeprefix("deploy_")
        try:
            run_id, environment = Approvals.parse(action["value"])
        except ValueError:
            respond("버튼 값이 올바르지 않아요.", response_type="ephemeral", replace_original=False)
            return
        error = attempt(
            lambda: approvals.request(
                decision, action["value"], user["id"], user.get("username", user["id"])
            ),
            "운영 배포를 승인 · 거절하지 못했어요",
        )
        if error:
            respond(error, response_type="ephemeral", replace_original=False)
            return
        verb = "승인" if decision == "approve" else "거절"
        close_buttons(
            body,
            respond,
            f"<@{user['id']}> 님이 `{environment}` 배포를 {verb}했어요. "
            f"<{approvals.github.run_url(run_id)}|실행 보기>",
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
    reviews = None
    if settings.github_app_client_id:
        # 리뷰 승인은 GitHub App의 device flow로 사용자 토큰을 받아야 해서 App 인증일 때만 켠다.
        links = Links(
            LinkStore(settings.link_store_path),
            DeviceFlow(settings.github_app_client_id, settings.github_app_client_secret),
        )
        reviews = Reviews(github, links, settings.allowed_user_ids)
    app = build_app(
        settings.slack_bot_token,
        Rollouts(github, settings.allowed_user_ids),
        Merges(github, settings.allowed_user_ids, settings.merge_method),
        Approvals(github, settings.allowed_user_ids),
        reviews,
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
