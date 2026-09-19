"""FastAPI application: REST commands + SSE journal + MJPEG viewport + recording seek.

OpenAPI UI: http://127.0.0.1:8765/docs
Viewport = live MJPEG. Recording seek = replay channel. See docs/BRIDGE.md.
"""

from __future__ import annotations

import asyncio
import base64
import queue
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse

from xfold.bridge.journal import Journal
from xfold.bridge.line_driver import LineDriver
from xfold.bridge.photo import find_photo
from xfold.bridge.mock_driver import MockDriver
from xfold.bridge.press_driver import PressBridgeDriver
from xfold.bridge.runtime import Runtime
from xfold.bridge.schema import (
    BRIDGE_VERSION,
    CommandRequest,
    CommandResponse,
    HealthResponse,
    LaunchBatchRequest,
    LaunchRunRequest,
)
from xfold.bridge.sim_session import SimSession
from xfold.bridge.trajectory import load_trajectory_meta, nearest_sample
from xfold.bridge.viewport import ViewportHub
from xfold.bridge.viewport_mujoco import MujocoViewportProducer


def _repo_data_dir() -> Path:
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pixi.toml").exists() and (parent / "moon.yml").exists():
            return parent / "data" / "journal"
    return here.parents[5] / "data" / "journal"


def create_app(*, persist: bool = True) -> FastAPI:
    journal = Journal(persist_dir=_repo_data_dir() if persist else None)
    runtime = Runtime(journal)
    session = SimSession()
    viewport_hub = ViewportHub()
    viewport_producer = MujocoViewportProducer(session, viewport_hub)

    # Driver chosen at startup once SimSession tries to load MuJoCo.
    driver: LineDriver | PressBridgeDriver | MockDriver | None = None

    app = FastAPI(
        title="XFOLD bridge",
        version=BRIDGE_VERSION,
        description=(
            "Append-only run journal with REST/SSE, MuJoCo MJPEG viewport, "
            "and trajectory recording seek. See docs/BRIDGE.md."
        ),
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=[
            "X-Viewport-Seq",
            "X-Viewport-Source",
            "X-Viewport-Age-Ms",
            "ETag",
        ],
    )

    app.state.journal = journal
    app.state.runtime = runtime
    app.state.session = session
    app.state.viewport_hub = viewport_hub
    app.state.viewport_producer = viewport_producer

    @app.on_event("startup")
    def _startup() -> None:
        nonlocal driver
        # Driver follows whichever scene SimSession managed to compile:
        #   line       -> LineDriver       (belt, press, folder, bagger)
        #   press_cell -> PressBridgeDriver (older arm cell)
        #   anything else -> MockDriver
        started = session.start()
        kind = session.kind if started else "none"

        if kind in ("line", "press_cell"):
            driver = (
                LineDriver(runtime, session)
                if kind == "line"
                else PressBridgeDriver(runtime, session)
            )
            driver.start()
            app.state.driver = driver
            # Probe offscreen GL before the producer thread exists: on a box
            # without it, MuJoCo aborts the process rather than raising.
            if session.probe_render() and viewport_producer.start():
                runtime.capabilities.viewportStream = True
                print(
                    "[viewport] long-poll JPEG at /viewport/frame "
                    "(MJPEG legacy at /viewport/stream)",
                    flush=True,
                )
            else:
                runtime.capabilities.viewportStream = False
                print(
                    "[viewport] no offscreen GL — bridge runs headless, "
                    "dashboard shows FSM + console without video",
                    flush=True,
                )
            runtime.capabilities.recordingSeek = session.can_render
            runtime.driver_label = (
                "LineDriver (belt, press, flap folder, bagger + SimSession)"
                if kind == "line"
                else "PressBridgeDriver (PressCycle + SimSession)"
            )
            print(f"[bridge] {runtime.driver_label} active", flush=True)
            return

        if started:
            # cell.xml stub: renders, but has nothing to drive → mock FSM.
            if session.probe_render() and viewport_producer.start():
                runtime.capabilities.viewportStream = True
            runtime.capabilities.recordingSeek = False
            print(
                "[bridge] no line and no press_cell — MockDriver + viewport only",
                flush=True,
            )
        else:
            runtime.capabilities.viewportStream = False
            runtime.capabilities.recordingSeek = False
            print(
                "[bridge] MockDriver fallback — install MuJoCo via "
                "moon run install-mujoco / moon run sim:bridge",
                flush=True,
            )
        driver = MockDriver(runtime)
        driver.start()
        app.state.driver = driver

    @app.on_event("shutdown")
    def _shutdown() -> None:
        viewport_producer.stop()
        d = getattr(app.state, "driver", None)
        if d is not None:
            d.stop()
        session.stop()

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse()

    @app.get("/capabilities")
    def capabilities() -> dict:
        caps = runtime.capabilities.model_dump()
        # viewportStream = producer started (UI may long-poll even before first frame).
        caps["viewportStream"] = bool(runtime.capabilities.viewportStream)
        caps["viewportReady"] = bool(viewport_hub.available)
        caps["viewportSource"] = viewport_hub.source
        caps["viewportTransport"] = "long-poll"
        caps["recordingSeek"] = bool(runtime.capabilities.recordingSeek)
        active = getattr(app.state, "driver", None)
        caps["driver"] = (
            "line" if isinstance(active, LineDriver)
            else "press" if isinstance(active, PressBridgeDriver)
            else "mock"
        )
        caps["scene"] = session.kind
        return caps

    @app.get("/snapshot")
    def snapshot() -> dict:
        snap = runtime.snapshot()
        snap["capabilities"] = {
            **snap["capabilities"],
            "viewportStream": bool(runtime.capabilities.viewportStream),
            "viewportReady": bool(viewport_hub.available),
            "recordingSeek": bool(runtime.capabilities.recordingSeek),
        }
        return snap

    @app.get("/viewport/meta")
    def viewport_meta() -> dict:
        """Cheap status for the Control UI (no JPEG body)."""
        meta = viewport_hub.meta()
        meta["enabled"] = bool(runtime.capabilities.viewportStream)
        return meta

    @app.get("/viewport/frame")
    def viewport_frame(
        after_seq: int = Query(0, ge=0, alias="after_seq"),
        wait_ms: int = Query(0, ge=0, le=5000, alias="wait_ms"),
    ) -> Response:
        """Latest JPEG, optionally long-polling until ``seq > after_seq``.

        Dashboard primary path. Use ``wait_ms`` (e.g. 1500) to avoid busy loops.
        """
        if not runtime.capabilities.viewportStream:
            raise HTTPException(503, "viewport unavailable")

        if wait_ms > 0:
            got = viewport_hub.wait_newer(
                after_seq=after_seq, timeout=wait_ms / 1000.0
            )
        else:
            got = viewport_hub.latest()
            if got is not None and got[2] <= after_seq:
                # Immediate poll, no newer frame → 304 so client keeps last paint.
                return Response(
                    status_code=304,
                    headers={
                        "Cache-Control": "no-store",
                        "ETag": f'"{got[2]}"',
                        "X-Viewport-Seq": str(got[2]),
                        "X-Viewport-Source": viewport_hub.source,
                    },
                )

        if not got:
            raise HTTPException(503, "viewport not ready")

        payload, mime, seq = got
        age_ms = viewport_hub.meta().get("ageMs")
        return Response(
            content=payload,
            media_type=mime,
            headers={
                "Cache-Control": "no-store",
                "ETag": f'"{seq}"',
                "X-Viewport-Seq": str(seq),
                "X-Viewport-Source": viewport_hub.source,
                "X-Viewport-Age-Ms": str(age_ms if age_ms is not None else ""),
            },
        )

    @app.get("/viewport/stream")
    def viewport_stream() -> StreamingResponse:
        """Legacy multipart MJPEG (curl/VLC). Dashboard must not use this."""
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
                "X-Viewport-Deprecated": "use-long-poll-/viewport/frame",
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

    @app.get("/runs/{run_id}/timeline")
    def run_timeline(run_id: str) -> dict:
        """FSM markers from the journal for scrubber / replay UI."""
        detail = runtime.get_run(run_id)
        if not detail:
            # Still allow timeline from journal alone (hydrated / finished).
            events = [
                e.to_public_dict()
                for e in journal.since(0)
                if getattr(e, "runId", None) == run_id
            ]
            if not events:
                raise HTTPException(404, "run not found")
        else:
            events = [
                e.to_public_dict()
                for e in journal.since(0)
                if getattr(e, "runId", None) == run_id
            ]
        markers = []
        for ev in events:
            if ev.get("type") == "state_changed":
                markers.append(
                    {
                        "t": float(ev.get("t") or 0),
                        "state": ev.get("state"),
                        "seq": ev.get("seq"),
                    }
                )
            elif ev.get("type") == "run_finished":
                markers.append(
                    {
                        "t": float(ev.get("t") or 0),
                        "state": "BAG" if ev.get("lifecycle") == "succeeded" else None,
                        "seq": ev.get("seq"),
                        "finished": True,
                        "lifecycle": ev.get("lifecycle"),
                    }
                )
        t_max = max((m["t"] for m in markers), default=0.0)
        meta = load_trajectory_meta(run_id)
        if meta.hasTrajectory:
            t_max = max(t_max, meta.tMax)
        return {
            "runId": run_id,
            "tMax": t_max,
            "markers": markers,
            "hasTrajectory": meta.hasTrajectory,
        }

    @app.get("/runs/{run_id}/recording")
    def run_recording(run_id: str) -> dict:
        meta = load_trajectory_meta(run_id)
        if not meta.hasTrajectory and runtime.get_run(run_id) is None:
            # Unknown run with no file
            events = [
                e
                for e in journal.since(0)
                if getattr(e, "runId", None) == run_id
            ]
            if not events and runtime.get_run(run_id) is None:
                raise HTTPException(404, "run not found")
        return meta.to_dict()

    @app.get("/runs/{run_id}/recording/frame")
    def run_recording_frame(
        run_id: str,
        t: float = Query(0.0, ge=0.0),
    ) -> dict:
        """Seek nearest trajectory sample → JPEG (base64) + FSM state."""
        sample = nearest_sample(run_id, t)
        if sample is None:
            raise HTTPException(404, "no trajectory for run")
        t_s, state, qpos = sample
        if not session.ok:
            raise HTTPException(503, "sim session unavailable for seek render")
        got = session.seek_render(qpos)
        if not got:
            raise HTTPException(503, "seek render failed")
        payload, mime = got
        return {
            "runId": run_id,
            "t": t_s,
            "requestedT": t,
            "state": state,
            "mime": mime,
            "imageBase64": base64.b64encode(payload).decode("ascii"),
        }

    @app.get("/runs/{run_id}/photo")
    def run_photo(run_id: str) -> Response:
        """The QC camera's product shot for this run.

        A file, not a journal event — same rule as the viewport frames. Cached
        hard: a run's shot never changes once the flash has fired.
        """
        path = find_photo(run_id)
        if path is None:
            raise HTTPException(404, "no product shot for run")
        mime = "image/png" if path.suffix == ".png" else "image/jpeg"
        return Response(
            content=path.read_bytes(),
            media_type=mime,
            headers={"Cache-Control": "public, max-age=31536000, immutable"},
        )

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
