from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    slack_bot_token: str
    slack_app_token: str

    # 조작할 대상 레포 (owner/repo). 이 레포의 워크플로를 실행하고 PR을 머지한다.
    github_repository: str
    github_ref: str = "main"
    # 대상 레포에서 platform 재사용 워크플로 rollout.yml을 호출하는 워크플로 파일 이름
    rollout_workflow: str = "rollout.yml"
    merge_method: str = "squash"

    # GitHub 인증: GitHub App(권장, 팀 봇 one-tatchi-bot) 또는 토큰(로컬 시험용) 중 하나
    github_app_client_id: str = ""
    github_app_private_key: str = ""
    github_token: str = ""

    # 비어 있으면 채널에 있는 누구나 조작할 수 있습니다.
    allowed_user_ids: list[str] = []
    port: int = 8000

    @model_validator(mode="after")
    def _github_auth(self) -> "Settings":
        if not self.github_token and not (
            self.github_app_client_id and self.github_app_private_key
        ):
            raise ValueError(
                "GitHub 인증이 필요합니다: GITHUB_APP_CLIENT_ID + GITHUB_APP_PRIVATE_KEY "
                "또는 GITHUB_TOKEN"
            )
        return self
