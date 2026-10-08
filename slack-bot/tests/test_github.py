import time

import httpx
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.github import AppToken


def make_key() -> tuple[str, rsa.RSAPublicKey]:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ).decode()
    return pem, key.public_key()


def test_app_token_exchanges_jwt_and_caches() -> None:
    pem, public = make_key()
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/repos/owner/repo/installation":
            return httpx.Response(200, json={"id": 42})
        return httpx.Response(201, json={"token": "ghs_installation"})

    token = AppToken("Iv-client", pem, "owner/repo", httpx.MockTransport(handler))

    assert token() == "ghs_installation"
    assert token() == "ghs_installation"  # 만료 전에는 다시 받지 않는다
    installation, access = requests
    assert access.url.path == "/app/installations/42/access_tokens"

    claims = jwt.decode(
        installation.headers["Authorization"].removeprefix("Bearer "), public, algorithms=["RS256"]
    )
    assert claims["iss"] == "Iv-client"
    assert claims["exp"] - time.time() < 600  # GitHub은 10분 넘는 JWT를 거부한다
