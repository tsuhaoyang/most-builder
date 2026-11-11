from __future__ import annotations

from typing import Protocol


class EmbeddingProvider(Protocol):
    model_id: str

    async def embed(self, texts: list[str]) -> list[list[float]] | None:
        """None = 服務不可用；呼叫端必須容忍"""
        ...
