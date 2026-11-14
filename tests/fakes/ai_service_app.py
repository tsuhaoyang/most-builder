"""假 ai_service（ASGI app）：在測試裡模擬 `POST /v1/llm/structured-completion` 的線上行為。

只實作 MOST 依賴的那一支端點與 ai_service 的錯誤信封（api spec §2.2、§4.1）。以
`httpx.ASGITransport(app=...)` 交給 `AiServiceClient(transport=...)` 使用，不開真的 port。

行為由 `FakeAiService.script` 控制：一個 list，每個請求依序取一個「劇本」，用完就重複最後一個。
劇本是 `Reply`（status、body、headers）或特殊字串：

- `"ok:<case_id>"`：回 golden 檔裡該案例的回應
- `"redirect"`：302 到別的 host
- `"huge"`：回超過大小上限的本文
- `"text500"`：純文字 500（非信封）
- `"slow"`：睡到超過 client 總時限

每個收到的請求都記在 `received`（headers 與 body），供測試斷言「送了什麼」。
"""
from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response

GOLDEN_PATH = Path(__file__).resolve().parents[1] / "contract" / "ai_service" / "golden" / "structured_completion_cases.json"


def golden_cases() -> dict[str, dict[str, Any]]:
    data = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    return {c["id"]: c for c in data["cases"]}


def error_body(code: str, message: str = "error", detail: Any = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "detail": detail}}


@dataclass
class Reply:
    status: int
    body: Any
    headers: dict[str, str] = field(default_factory=dict)


@dataclass
class FakeAiService:
    script: list[Any] = field(default_factory=lambda: ["ok:fewshot-zh-0"])
    received: list[dict[str, Any]] = field(default_factory=list)
    slow_s: float = 5.0

    def app(self) -> FastAPI:
        app = FastAPI()
        cases = golden_cases()

        @app.post("/v1/llm/structured-completion")
        async def structured_completion(request: Request) -> Response:
            body = await request.json()
            self.received.append({"headers": dict(request.headers), "body": body})
            step = self.script[min(len(self.received) - 1, len(self.script) - 1)]
            if isinstance(step, Reply):
                if isinstance(step.body, str):
                    return PlainTextResponse(step.body, status_code=step.status, headers=step.headers)
                return JSONResponse(step.body, status_code=step.status, headers=step.headers)
            if step.startswith("ok:"):
                return JSONResponse(cases[step[3:]]["response"])
            if step == "redirect":
                return Response(status_code=302, headers={"location": "https://elsewhere.example/steal"})
            if step == "huge":
                return PlainTextResponse("x" * (300 * 1024))
            if step == "text500":
                return PlainTextResponse("Internal Server Error", status_code=500)
            if step == "slow":
                await asyncio.sleep(self.slow_s)
                return JSONResponse(cases["fewshot-zh-0"]["response"])
            raise AssertionError(f"unknown fake script step: {step}")

        return app
