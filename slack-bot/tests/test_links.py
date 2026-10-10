import json
from collections.abc import Callable

import httpx
import pytest

from app.links import DEVICE_CODE_URL, TOKEN_URL, DeviceFlow, Link, LinkError, Links, LinkStore


class Clock:
    def __init__(self) -> None:
        self.now = 1_000.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds


def make_flow(
    responses: list[dict], clock: Clock, secret: str = ""
) -> tuple[DeviceFlow, list[httpx.Request]]:
    requests: list[httpx.Request] = []
    pending = list(responses)

    def oauth(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if str(request.url) == DEVICE_CODE_URL:
            return httpx.Response(
                200,
                json={
                    "device_code": "dev",
                    "user_code": "ABCD-1234",
                    "verification_uri": "https://github.com/login/device",
                    "interval": 5,
                    "expires_in": 900,
                },
            )
        assert str(request.url) == TOKEN_URL
        return httpx.Response(200, json=pending.pop(0))

    def api(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.url.path == "/user"
        return httpx.Response(200, json={"login": "soulee-dev"})

    flow = DeviceFlow(
        "Iv-client",
        secret,
        transport=httpx.MockTransport(oauth),
        api_transport=httpx.MockTransport(api),
        sleep=clock.sleep,
        now=clock,
    )
    return flow, requests


def test_device_flow_polls_until_token_then_reads_login() -> None:
    clock = Clock()
    flow, requests = make_flow(
        [
            {"error": "authorization_pending"},
            {"error": "slow_down"},
            {"access_token": "ghu_user", "refresh_token": "ghr_x", "expires_in": 28800},
        ],
        clock,
    )
    device = flow.start()
    assert (device.user_code, device.interval) == ("ABCD-1234", 5)

    link = flow.poll(device)
    assert (link.login, link.access_token, link.refresh_token) == (
        "soulee-dev",
        "ghu_user",
        "ghr_x",
    )
    assert link.expires_at == pytest.approx(clock.now + 28800)
    # slow_down 뒤에는 간격이 5초 늘어난다: 5 + 5 + 10
    assert clock.now == pytest.approx(1_000 + 20)
    token_calls = [r for r in requests if str(r.url) == TOKEN_URL]
    assert len(token_calls) == 3
    body = dict(httpx.QueryParams(token_calls[0].content.decode()))
    assert body["grant_type"] == "urn:ietf:params:oauth:grant-type:device_code"
    assert body["device_code"] == "dev"
    user = requests[-1]
    assert user.headers["Authorization"] == "Bearer ghu_user"


def test_device_flow_reports_denied_and_expired() -> None:
    clock = Clock()
    flow, _ = make_flow([{"error": "access_denied", "error_description": "거부"}], clock)
    with pytest.raises(LinkError, match="거부"):
        flow.poll(flow.start())

    clock = Clock()
    flow, _ = make_flow([], clock)
    device = flow.start()
    clock.now = device.expires_at + 1
    with pytest.raises(LinkError, match="만료"):
        flow.poll(device)


def test_refresh_needs_secret_and_keeps_login() -> None:
    clock = Clock()
    flow, _ = make_flow([], clock)
    with pytest.raises(LinkError):
        flow.refresh(Link("soulee-dev", "old", "ghr_x", clock.now))

    flow, requests = make_flow(
        [{"access_token": "ghu_new", "refresh_token": "ghr_new", "expires_in": 100}], clock, "sec"
    )
    link = flow.refresh(Link("soulee-dev", "old", "ghr_x", clock.now))
    assert (link.login, link.access_token, link.refresh_token) == (
        "soulee-dev",
        "ghu_new",
        "ghr_new",
    )
    body = dict(httpx.QueryParams(requests[-1].content.decode()))
    assert (body["grant_type"], body["client_secret"]) == ("refresh_token", "sec")
    assert [r for r in requests if r.url.path == "/user"] == []  # 로그인은 다시 조회하지 않는다


def test_store_roundtrip_and_permissions(tmp_path) -> None:
    path = tmp_path / "links.json"
    store = LinkStore(str(path))
    store.put("U1", Link("soulee-dev", "ghu", "ghr", 5.0))
    assert path.stat().st_mode & 0o777 == 0o600
    assert json.loads(path.read_text())["U1"]["login"] == "soulee-dev"

    again = LinkStore(str(path))
    assert again.get("U1") == Link("soulee-dev", "ghu", "ghr", 5.0)
    again.delete("U1")
    assert LinkStore(str(path)).get("U1") is None
    assert LinkStore("").get("U1") is None  # 경로가 없으면 메모리만


def make_links(flow: DeviceFlow, store: LinkStore | None = None) -> Links:
    def run_now(call: Callable[[], None]) -> None:
        call()

    return Links(store or LinkStore(""), flow, run_in_background=run_now)


def test_begin_links_account_and_notifies() -> None:
    clock = Clock()
    flow, _ = make_flow([{"access_token": "ghu_user", "expires_in": 0}], clock)
    links = make_links(flow)
    notices: list[str] = []

    text = links.begin("U1", notices.append)
    assert "ABCD-1234" in text and "https://github.com/login/device" in text
    assert notices == [
        "GitHub `soulee-dev` 계정을 연결했어요. 이제 리뷰 승인 버튼을 다시 눌러 주세요."
    ]
    assert links.get("U1") == Link("soulee-dev", "ghu_user", "", 0.0)


def test_begin_reports_failure() -> None:
    clock = Clock()
    flow, _ = make_flow([{"error": "access_denied"}], clock)
    links = make_links(flow)
    notices: list[str] = []
    links.begin("U1", notices.append)
    assert notices and "실패" in notices[0]
    assert links.get("U1") is None


def test_get_refreshes_expiring_token_or_forgets() -> None:
    clock = Clock()
    flow, _ = make_flow([{"access_token": "ghu_new", "expires_in": 3600}], clock, "sec")
    links = make_links(flow)
    links.store.put("U1", Link("soulee-dev", "old", "ghr", clock.now + 60))
    assert links.get("U1").access_token == "ghu_new"

    flow, _ = make_flow([], clock)  # secret 없음 → 갱신 불가 → 연결을 지운다
    links = make_links(flow)
    links.store.put("U1", Link("soulee-dev", "old", "ghr", clock.now + 60))
    assert links.get("U1") is None
    assert links.store.get("U1") is None
