from __future__ import annotations


class NullProvider:
    model_id = "null"

    async def embed(self, texts: list[str]) -> list[list[float]] | None:
        return None
