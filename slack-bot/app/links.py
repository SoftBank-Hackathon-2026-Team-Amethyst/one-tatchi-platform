import json
import logging
import os
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass

import httpx

from app.github import API, HEADERS

# GitHub App의 device flow. 봇은 Socket Mode라 공개 콜백 주소가 없어서, 사용자가 브라우저에서 코드를
# 입력하고 봇이 결과를 폴링하는 방식으로 사용자 토큰을 받는다.
# GitHub App 설정에서 "Enable Device Flow"를 켜야 한다.
DEVICE_CODE_URL = "https://github.com/login/device/code"
TOKEN_URL = "https://github.com/login/oauth/access_token"
GRANT_DEVICE = "urn:ietf:params:oauth:grant-type:device_code"

logger = logging.getLogger(__name__)


class LinkError(Exception):
    """사용자가 승인하지 않았거나 코드가 만료된 경우."""


@dataclass
class Link:
    """Slack 사용자에 연결된 GitHub 계정. 토큰은 그 사람 권한으로만 동작한다(user-to-server)."""

    login: str
    access_token: str
    refresh_token: str = ""
    expires_at: float = 0.0  # 0이면 만료 없음 (GitHub App 설정에서 토큰 만료를 끈 경우)

    def expiring(self, margin: float = 300) -> bool:
        return self.expires_at > 0 and time.time() > self.expires_at - margin


@dataclass(frozen=True)
class DeviceCode:
    device_code: str
    user_code: str
    verification_uri: str
    interval: float
    expires_at: float


class LinkStore:
    """Slack 사용자 ID → Link.

    파일이 없거나 경로가 비어 있으면 메모리에만 둔다(재시작하면 다시 연결)."""

    def __init__(self, path: str = "") -> None:
        self.path = path
        self._links: dict[str, Link] = {}
        self._lock = threading.Lock()
        self._load()

    def _load(self) -> None:
        if not self.path or not os.path.exists(self.path):
            return
        try:
            with open(self.path, encoding="utf-8") as file:
                raw = json.load(file)
            self._links = {user: Link(**link) for user, link in raw.items()}
        except (OSError, ValueError, TypeError):
            logger.exception("연결 저장 파일을 읽지 못했어요: %s", self.path)

    def _save(self) -> None:
        if not self.path:
            return
        tmp = f"{self.path}.tmp"
        with open(tmp, "w", encoding="utf-8", opener=lambda p, f: os.open(p, f, 0o600)) as file:
            json.dump({user: asdict(link) for user, link in self._links.items()}, file)
        os.replace(tmp, self.path)

    def get(self, user_id: str) -> Link | None:
        with self._lock:
            return self._links.get(user_id)

    def put(self, user_id: str, link: Link) -> None:
        with self._lock:
            self._links[user_id] = link
            self._save()

    def delete(self, user_id: str) -> None:
        with self._lock:
            if self._links.pop(user_id, None) is not None:
                self._save()


class DeviceFlow:
    """device flow로 사용자 토큰을 받고, client secret이 있으면 만료 전에 갱신한다."""

    def __init__(
        self,
        client_id: str,
        client_secret: str = "",
        transport: httpx.BaseTransport | None = None,
        api_transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], float] = time.time,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.sleep = sleep
        self.now = now
        self.oauth = httpx.Client(
            headers={"Accept": "application/json"}, timeout=10, transport=transport
        )
        self.api = httpx.Client(base_url=API, headers=HEADERS, timeout=10, transport=api_transport)

    def start(self) -> DeviceCode:
        response = self.oauth.post(DEVICE_CODE_URL, data={"client_id": self.client_id})
        response.raise_for_status()
        data = response.json()
        return DeviceCode(
            device_code=data["device_code"],
            user_code=data["user_code"],
            verification_uri=data["verification_uri"],
            interval=float(data.get("interval", 5)),
            expires_at=self.now() + float(data.get("expires_in", 900)),
        )

    def poll(self, device: DeviceCode) -> Link:
        interval = device.interval
        while True:
            self.sleep(interval)
            if self.now() > device.expires_at:
                raise LinkError("코드가 만료됐어요")
            response = self.oauth.post(
                TOKEN_URL,
                data={
                    "client_id": self.client_id,
                    "device_code": device.device_code,
                    "grant_type": GRANT_DEVICE,
                },
            )
            response.raise_for_status()
            data = response.json()
            error = data.get("error")
            if not error:
                return self._link(data)
            if error == "authorization_pending":
                continue
            if error == "slow_down":
                interval += 5
                continue
            raise LinkError(data.get("error_description") or error)

    def refresh(self, link: Link) -> Link:
        if not link.refresh_token or not self.client_secret:
            raise LinkError("토큰을 갱신할 수 없어요")
        response = self.oauth.post(
            TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "refresh_token",
                "refresh_token": link.refresh_token,
            },
        )
        response.raise_for_status()
        data = response.json()
        if data.get("error"):
            raise LinkError(data.get("error_description") or data["error"])
        return self._link(data, login=link.login)

    def _link(self, data: dict, login: str = "") -> Link:
        token = data["access_token"]
        expires_in = float(data.get("expires_in") or 0)
        if not login:
            user = self.api.get("/user", headers={"Authorization": f"Bearer {token}"})
            user.raise_for_status()
            login = user.json()["login"]
        return Link(
            login=login,
            access_token=token,
            refresh_token=data.get("refresh_token", ""),
            expires_at=self.now() + expires_in if expires_in else 0.0,
        )


class Links:
    """Slack 사용자의 GitHub 계정 연결.

    연결이 없으면 device flow를 시작하고 완료를 백그라운드에서 기다린다."""

    def __init__(
        self,
        store: LinkStore,
        flow: DeviceFlow,
        run_in_background: Callable[[Callable[[], None]], None] | None = None,
    ) -> None:
        self.store = store
        self.flow = flow
        self.run_in_background = run_in_background or _spawn

    def get(self, user_id: str) -> Link | None:
        link = self.store.get(user_id)
        if link and link.expiring():
            try:
                link = self.flow.refresh(link)
                self.store.put(user_id, link)
            except (LinkError, httpx.HTTPError):
                logger.exception("GitHub 토큰을 갱신하지 못했어요 (%s)", user_id)
                self.store.delete(user_id)
                return None
        return link

    def forget(self, user_id: str) -> None:
        self.store.delete(user_id)

    def begin(self, user_id: str, notify: Callable[[str], None]) -> str:
        """device flow를 시작하고 사용자에게 보여 줄 안내를 돌려준다.

        완료 · 실패는 notify로 알린다."""
        device = self.flow.start()

        def wait() -> None:
            try:
                link = self.flow.poll(device)
            except LinkError as error:
                notify(f"GitHub 연결에 실패했어요: {error}. 버튼을 다시 눌러 새 코드를 받으세요.")
                return
            except httpx.HTTPError:
                logger.exception("GitHub 연결 폴링에 실패했어요 (%s)", user_id)
                notify("GitHub 연결 중 오류가 났어요. 잠시 후 다시 시도해 주세요.")
                return
            self.store.put(user_id, link)
            notify(
                f"GitHub `{link.login}` 계정을 연결했어요. 이제 리뷰 승인 버튼을 다시 눌러 주세요."
            )

        self.run_in_background(wait)
        minutes = max(1, int((device.expires_at - self.flow.now()) // 60))
        return (
            f"GitHub 계정이 아직 연결되지 않았어요. <{device.verification_uri}|여기>에서 코드 "
            f"`{device.user_code}` 를 입력해 주세요 ({minutes}분 안에). 연결되면 알려 드릴게요."
        )


def _spawn(call: Callable[[], None]) -> None:
    threading.Thread(target=call, daemon=True).start()
