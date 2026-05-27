from __future__ import annotations

import httpx

_HTTP_OK = 200


class EvolutionClient:
    def __init__(self, base_url: str, api_key: str, instance: str) -> None:
        self._base = base_url.rstrip("/")
        self._key = api_key
        self._instance = instance

    def _headers(self) -> dict[str, str]:
        return {"apikey": self._key, "Content-Type": "application/json"}

    async def send_text(self, to: str, text: str) -> None:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self._base}/message/sendText/{self._instance}",
                headers=self._headers(),
                json={"number": to, "text": text},
            )
        if resp.status_code >= 400:  # noqa: PLR2004
            raise RuntimeError(
                f"Evolution API sendText {resp.status_code}: {resp.text[:200]}"
            )

    async def send_presence(self, to: str, presence: str) -> None:
        """presence: 'composing' | 'paused' | 'available'"""
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"{self._base}/chat/sendPresence/{self._instance}",
                headers=self._headers(),
                json={"number": to, "presence": presence, "delay": 100},
            )

    async def get_group_info(self, group_jid: str) -> dict:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"{self._base}/group/findGroupInfos/{self._instance}",
                headers=self._headers(),
                params={"groupJid": group_jid},
            )
        return resp.json() if resp.status_code == _HTTP_OK else {}

    async def configure_webhook(self, webhook_url: str) -> None:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"{self._base}/webhook/set/{self._instance}",
                headers=self._headers(),
                json={
                    "webhook": {
                        "enabled": True,
                        "url": webhook_url,
                        "webhookByEvents": False,
                        "webhookBase64": False,
                        "events": ["MESSAGES_UPSERT"],
                    }
                },
            )
