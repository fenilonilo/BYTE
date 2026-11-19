from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from main import app

if TYPE_CHECKING:
    from pathlib import Path

MASTER = "m" * 40
P = "/api/v1"


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    monkeypatch.chdir(tmp_path)  # data/devices.json lands in the test's own folder
    for name in ("BYTE_PROJECTS", "BYTE_DATABASE_URL", "BYTE_PIPER_MODEL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("BYTE_API_TOKEN", MASTER)
    monkeypatch.setenv("BYTE_OPENAI_API_KEY", "sk-test")
    return TestClient(app)


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def login(client: TestClient) -> dict[str, str]:
    res = client.post(P + "/auth/login", headers=bearer(MASTER))
    assert res.status_code == 200
    return res.json()


@pytest.mark.unit
def test_only_the_master_token_signs_a_device_in(client: TestClient) -> None:
    with client:
        assert client.post(P + "/auth/login").status_code == 401
        pair = login(client)
        assert pair["expires_in"] == 3600
        assert (
            client.post(P + "/auth/login", headers=bearer(pair["access_token"])).status_code == 401
        )


@pytest.mark.unit
def test_an_access_token_opens_routes_and_sockets(client: TestClient) -> None:
    with client:
        access = login(client)["access_token"]
        assert client.get(P + "/reminders", headers=bearer(access)).status_code == 200
        assert client.get(P + "/reminders", headers=bearer("z" * 43)).status_code == 401
        with client.websocket_connect(
            P + "/ws/notifications", subprotocols=["bearer", access]
        ) as ws:
            assert ws.accepted_subprotocol == "bearer"
        with (
            pytest.raises(WebSocketDisconnect),
            client.websocket_connect(P + "/ws/notifications", subprotocols=["bearer", "z" * 43]),
        ):
            pass


@pytest.mark.unit
def test_refresh_renews_and_logout_revokes(client: TestClient) -> None:
    with client:
        pair = login(client)
        renewed = client.post(P + "/auth/refresh", json={"refresh_token": pair["refresh_token"]})
        assert renewed.status_code == 200
        assert renewed.json()["refresh_token"] == pair["refresh_token"]
        assert (
            client.get(P + "/reminders", headers=bearer(renewed.json()["access_token"])).status_code
            == 200
        )
        out = client.post(P + "/auth/logout", json={"refresh_token": pair["refresh_token"]})
        assert out.status_code == 204
        again = client.post(P + "/auth/refresh", json={"refresh_token": pair["refresh_token"]})
        assert again.status_code == 401
        assert client.post(P + "/auth/refresh", json={"refresh_token": ""}).status_code == 422
