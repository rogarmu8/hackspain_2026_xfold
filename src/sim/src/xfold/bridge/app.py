"""FastAPI application: REST commands + SSE journal + MJPEG viewport.

OpenAPI UI: http://127.0.0.1:8765/docs
Viewport is a separate image channel (not journal). See docs/BRIDGE.md.
"""

from __future__ import annotations

import asyncio
import queue
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse

from xfold.bridge.journal import Journal
from xfold.bridge.mock_driver import MockDriver
from xfold.bridge.runtime import Runtime
from xfold.bridge.schema import (
    BRIDGE_VERSION,
    CommandRequest,
    CommandResponse,
    HealthResponse,
    LaunchBatchRequest,
    LaunchRunRequest,
)
from xfold.bridge.viewport import ViewportHub
from xfold.bridge.viewport_mujoco import MujocoViewportProducer


def _repo_data_dir() -> Path:
    # …/src/sim/src/xfold/bridge/app.py → repo root (five parents up from file).
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pixi.toml").exists() and (parent / "moon.yml").exists():
            return parent / "data" / "journal"
    return here.parents[5] / "data" / "journal"


def create_app(*, persist: bool = True) -> FastAPI:
    journal = Journal(persist_dir=_repo_data_dir() if persist else None)
    runtime = Runtime(journal)
    driver = MockDriver(runtime)
    viewport_hub = ViewportHub()
    viewport_producer = MujocoViewportProducer(runtime, viewport_hub)

    app = FastAPI(
        title="XFOLD bridge",
        version=BRIDGE_VERSION,
        description=(
            "Append-only run journal with REST/SSE, plus optional MuJoCo MJPEG viewport. "
            "See docs/BRIDGE.md."
        ),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.state.journal = journal
    app.state.runtime = runtime
    app.state.driver = driver
    app.state.viewport_hub = viewport_hub
    app.state.viewport_producer = viewport_producer

    @app.on_event("startup")
    def _startup() -> None:
        driver.start()
        if viewport_producer.start():
            runtime.capabilities.viewportStream = True
            print("[viewport] MuJoCo MJPEG stream ready at /viewport/stream", flush=True)
        else:
            runtime.capabilities.viewportStream = False
            print(
                "[viewport] MuJoCo unavailable — install with: moon run install-mujoco "
                "and run bridge via moon run sim:bridge (mujoco env).",
                flush=True,
            )

    @app.on_event("shutdown")
    def _shutdown() -> None:
        viewport_producer.stop()
        driver.stop()

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse()

    @app.get("/capabilities")
    def capabilities() -> dict:
        caps = runtime.capabilities.model_dump()
        caps["viewportStream"] = bool(
            runtime.capabilities.viewportStream and viewport_hub.available
        )
        caps["viewportSource"] = viewport_hub.source
        return caps

    @app.get("/snapshot")
    def snapshot() -> dict:
        snap = runtime.snapshot()
        # Keep capabilities honest for the control room.
        snap["capabilities"] = {
            **snap["capabilities"],
            "viewportStream": bool(
                runtime.capabilities.viewportStream and viewport_hub.available
            ),
        }
        return snap

    @app.get("/viewport/frame")
    def viewport_frame() -> Response:
        got = viewport_hub.latest()
        if not got:
            raise HTTPException(503, "viewport not ready")
        payload, mime, seq = got
        return Response(
            content=payload,
            media_type=mime,
            headers={
                "Cache-Control": "no-store",
                "X-Viewport-Seq": str(seq),
                "X-Viewport-Source": viewport_hub.source,
            },
        )

    @app.get("/viewport/stream")
    def viewport_stream() -> StreamingResponse:
        if not runtime.capabilities.viewportStream:
            raise HTTPException(
                503,
                "viewport stream unavailable (MuJoCo env / Renderer not started)",
            )
        return StreamingResponse(
            viewport_hub.mjpeg_sync(fps=12.0),
            media_type="multipart/x-mixed-replace; boundary=frame",
            headers={
                "Cache-Control": "no-cache, private",
                "Pragma": "no-cache",
                "X-Accel-Buffering": "no",
                "X-Viewport-Source": viewport_hub.source,
            },
        )

    @app.get("/runs")
    def list_runs() -> list:
        return runtime.list_runs()

    @app.get("/runs/{run_id}")
    def get_run(run_id: str) -> dict:
        detail = runtime.get_run(run_id)
        if not detail:
            raise HTTPException(404, "run not found")
        return detail

    @app.get("/batches/{batch_id}")
    def get_batch(batch_id: str) -> dict:
        detail = runtime.get_batch(batch_id)
        if not detail:
            raise HTTPException(404, "batch not found")
        return detail

    @app.get("/experiments")
    def experiments() -> list:
        return runtime.list_experiments()

    @app.post("/runs", status_code=201)
    def post_run(body: LaunchRunRequest) -> dict:
        try:
            return runtime.launch_run(name=body.name, seed=body.seed, scenario=body.scenario)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/batches", status_code=201)
    def post_batch(body: LaunchBatchRequest) -> dict:
        try:
            return runtime.launch_batch(
                name=body.name,
                count=body.count,
                base_seed=body.baseSeed,
                scenario=body.scenario,
            )
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc

    @app.post("/commands", status_code=202, response_model=CommandResponse)
    def post_command(body: CommandRequest) -> CommandResponse | JSONResponse:
        result = runtime.handle_command(body)
        status = result["status"]
        if status == "rejected":
            return JSONResponse(result, status_code=409)
        return CommandResponse.model_validate(result)

    @app.get("/events/stream")
    async def event_stream(
        request: Request,
        after_seq: int = Query(0, ge=0, alias="after_seq"),
    ) -> StreamingResponse:
        q: queue.SimpleQueue = queue.SimpleQueue()

        def on_event(event) -> None:
            q.put(event)

        unsubscribe = journal.subscribe(on_event)

        async def gen() -> AsyncIterator[str]:
            try:
                for event in journal.since(after_seq):
                    payload = event.model_dump_json()
                    yield f"id: {event.seq}\ndata: {payload}\n\n"
                while True:
                    if await request.is_disconnected():
                        break
                    try:
                        event = await asyncio.to_thread(q.get, True, 1.0)
                    except queue.Empty:
                        yield ": keepalive\n\n"
                        continue
                    payload = event.model_dump_json()
                    yield f"id: {event.seq}\ndata: {payload}\n\n"
            finally:
                unsubscribe()

        return StreamingResponse(
            gen(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return app


def main() -> None:
    import uvicorn

    uvicorn.run(
        "xfold.bridge.app:create_app",
        factory=True,
        host="127.0.0.1",
        port=8765,
        log_level="info",
    )


if __name__ == "__main__":
    main()
