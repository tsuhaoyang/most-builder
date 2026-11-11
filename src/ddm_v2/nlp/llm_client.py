"""OpenAI-compatible structured completion client（附錄 A4 能力階梯）。"""
from __future__ import annotations

import json
import time
from typing import Any, Literal

import httpx

from ddm_v2.nlp.planner_ports import LLMRawResponse

ResponseFormatMode = Literal["json_schema", "json_object", "none"]


class OpenAICompatClient:
    """POST {base_url}/v1/chat/completions — 不綁供應商網域。"""

    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str | None = None,
        response_format_mode: ResponseFormatMode = "json_object",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._model = model
        self._api_key = api_key
        self._mode: ResponseFormatMode = response_format_mode

    async def structured_completion(
        self,
        *,
        system: str,
        user: str,
        json_schema: dict[str, Any],
        temperature: float,
        timeout_s: float,
        few_shots: list[tuple[str, str]] | None = None,
    ) -> LLMRawResponse:
        messages: list[dict[str, str]] = [{"role": "system", "content": system}]
        if self._mode in {"json_object", "none"}:
            # 把 schema 附進 system，補強無 strict json_schema 的後端
            messages[0]["content"] = (
                system
                + "\n\n# Output JSON Schema\n"
                + json.dumps(json_schema, ensure_ascii=False)
            )
        for u, a in few_shots or []:
            messages.append({"role": "user", "content": u})
            messages.append({"role": "assistant", "content": a})
        messages.append({"role": "user", "content": user})

        body: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": 2048,
        }
        if self._mode == "json_schema":
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "wi_plan",
                    "strict": True,
                    "schema": json_schema,
                },
            }
        elif self._mode == "json_object":
            body["response_format"] = {"type": "json_object"}

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        t0 = time.perf_counter()
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.post(
                f"{self._base_url}/v1/chat/completions",
                json=body,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
        latency = (time.perf_counter() - t0) * 1000

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ValueError(f"malformed LLM response envelope: {exc}") from exc
        if not isinstance(content, str):
            raise ValueError("LLM content is not a string")
        usage = data.get("usage") or {}
        model = data.get("model") or self._model
        return LLMRawResponse(
            content=content,
            model=str(model),
            usage=usage if isinstance(usage, dict) else {},
            latency_ms=round(latency, 2),
            response_format_mode=self._mode,
        )
