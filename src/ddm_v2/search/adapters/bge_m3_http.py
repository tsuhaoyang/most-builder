from __future__ import annotations

import os

import httpx


class BgeM3HttpProvider:
    model_id = "bge-m3"

    def __init__(self, url: str | None = None):
        self._url = url or os.getenv("EMBEDDING_URL", "http://localhost:8080")

    async def embed(self, texts: list[str]) -> list[list[float]] | None:
        try:
            async with httpx.AsyncClient(timeout=10.0) as c:
                r = await c.post(f"{self._url}/embed", json={"inputs": texts})
                r.raise_for_status()
                data = r.json()
                if not isinstance(data, list) or not data or not isinstance(data[0], list):
                    return None
                return data
        except Exception:
            return None
