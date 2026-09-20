"""FastAPI application: REST commands + SSE journal + MJPEG viewport + recording seek.

OpenAPI UI: http://127.0.0.1:8765/docs
Viewport = live MJPEG. Recording seek = replay channel. See docs/BRIDGE.md.
"""

from __future__ import annotations

import asyncio
import base64
import os
import queue
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response, StreamingResponse

from xfold.bridge.experiments import ExperimentStore, default_db_path
from xfold.bridge.journal import Journal
from xfold.bridge.line_driver import LineDriver
from xfold.bridge.photo import find_photo
from xfold.bridge.video import PLAYLIST, VideoManager, has_video, servable
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


# Render rate for both the video and the JPEG hub. The line runs at about
# realtime, so this is also the video's frame rate.
VIEWPORT_FPS = 12.0
# Sims side by side, so several experiments run at once (the rest queue).
# Each is a MuJoCo scene of its own and about one core while it runs.
DEFAULT_WORKERS = max(1, int(os.environ.get("XFOLD_BRIDGE_WORKERS", "3")))


def create_app(
    *,
    persist: bool = True,
    session: SimSession | None = None,
    start_driver: bool = True,
    workers: int = DEFAULT_WORKERS,
) -> FastAPI:
    """The bridge. ``session`` swaps the engine (default: MuJoCo SimSession).

    ``workers`` sims run side by side, so that many experiments simulate at
    once and the rest queue (``/capabilities.maxConcurrentRuns``). Each worker
    owns a session, a viewport and its run's video; an injected ``session``
    (Isaac, whose Kit is one stage on one thread) means exactly one.

    With ``start_driver=False`` the driver is created but not started: the
    caller runs ``app.state.driver.run_here()`` on a thread of its choosing.
    """
    journal = Journal(persist_dir=_repo_data_dir() if persist else None)
    store = ExperimentStore(default_db_path() if persist else ":memory:")
    runtime = Runtime(journal, store=store)
    sessions = [session] if session is not None else [SimSession() for _ in range(max(1, workers))]
    session = sessions[0]
    hubs = [ViewportHub() for _ in sessions]
    viewport_hub = hubs[0]

    def worker_run(worker: str):
        """The run that worker is simulating, if it is live."""
        for run in list(runtime.runs.values()):
            if run.worker == worker and run.lifecycle == "running":
                return run
        return None

    def live_run_for(worker: str):
        run = worker_run(worker)
        return run.id if run is not None else None

    # One render per frame feeds the run's H.264 video and the JPEG hub. The
    # producer has no notion of runs, so it asks the runtime which one is live.
    videos: list[VideoManager] = []
    producers: list[MujocoViewportProducer] = []
    for index, worker_session in enumerate(sessions):
        video_width, video_height = worker_session.video_size or (
            worker_session.width,
            worker_session.height,
        )
        worker_video = VideoManager(
            video_width,
            video_height,
            worker_session.video_fps or VIEWPORT_FPS,
            on_open=runtime.mark_video,
            clock=worker_session.video_clock,
        )
        name = f"w{index}"
        active = (lambda worker: lambda: live_run_for(worker))(name)
        videos.append(worker_video)
        producers.append(
            MujocoViewportProducer(
                worker_session, hubs[index], fps=VIEWPORT_FPS, video=worker_video, active_run=active
            )
        )
        worker_session.attach_video(worker_video, active)
    video = videos[0]
    viewport_producer = producers[0]

    def hub_for_run(run_id: str | None) -> ViewportHub | None:
        """The viewport of whichever worker holds this run."""
        if run_id is None:
            return None
        run = runtime.runs.get(run_id)
        if run is None or run.worker is None:
            return None
        index = int(run.worker[1:]) if run.worker[1:].isdigit() else 0
        return hubs[index] if index < len(hubs) else None

    def focused_hub() -> ViewportHub:
        """What `/viewport/frame` (no run id) shows: the focused run's worker."""
        run = runtime.driver_active_run()
        hub = hub_for_run(run.id) if run is not None else None
        return hub or viewport_hub

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
        # The extra sims only matter for the line; anything else runs one.
        extra = [s for s in sessions[1:] if kind == "line" and s.start()]
        live_sessions = [session, *extra]

        if kind in ("line", "press_cell"):
            driver = (
                LineDriver(runtime, session, sessions=live_sessions)
                if kind == "line"
                else PressBridgeDriver(runtime, session)
            )
            if start_driver:
                driver.start()
            app.state.driver = driver
            # Probe offscreen GL before the producer thread exists: on a box
            # without it, MuJoCo aborts the process rather than raising.
            if session.probe_render() and viewport_producer.start():
                runtime.capabilities.viewportStream = True
                for index, extra_session in enumerate(extra, start=1):
                    if extra_session.probe_render():
                        producers[index].start()
                print(
                    "[viewport] long-poll JPEG at /viewport/frame and "
                    "/runs/{id}/viewport/frame (MJPEG legacy at /viewport/stream)",
                    flush=True,
                )
            else:
                runtime.capabilities.viewportStream = False
                print(
                    "[viewport] no offscreen GL — bridge runs headless, "
                    "dashboard shows FSM + console without video",
                    flush=True,
                )
            runtime.capabilities.recordingSeek = session.can_render and session.seekable
            runtime.capabilities.viewportVideo = bool(
                session.can_render and video.available
            )
            runtime.capabilities.liveVideo = bool(session.live_video)
            runtime.capabilities.engine = session.engine
            runtime.capabilities.maxConcurrentRuns = len(live_sessions)
            if len(live_sessions) > 1:
                print(
                    f"[bridge] {len(live_sessions)} sims side by side; "
                    "further launches queue",
                    flush=True,
                )
            if runtime.capabilities.viewportVideo:
                print(
                    "[video] H.264 per run at /runs/{id}/video/index.m3u8 "
                    "(a couple of segments behind live)",
                    flush=True,
                )
            else:
                print(
                    "[video] no ffmpeg — dashboard stays on JPEG long-poll",
                    flush=True,
                )
            runtime.driver_label = (
                "LineDriver (belt, press, flap folder, bagger + SimSession)"
                if kind == "line"
                else "PressBridgeDriver (PressCycle + SimSession)"
            )
            if session.engine != "mujoco":
                runtime.driver_label += f" on {session.engine}"
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
        for producer in producers:
            producer.stop()
        for manager in videos:
            manager.close()
        d = getattr(app.state, "driver", None)
        if d is not None:
            d.stop()
        for worker_session in sessions:
            worker_session.stop()

    @app.get("/health", response_model=HealthResponse)
    def health() -> HealthResponse:
        return HealthResponse()

    @app.get("/capabilities")
    def capabilities() -> dict:
        caps = runtime.capabilities.model_dump()
        # viewportStream = producer started (UI may long-poll even before first frame).
        caps["viewportStream"] = bool(runtime.capabilities.viewportStream)
        caps["viewportReady"] = any(hub.available for hub in hubs)
        caps["viewportSource"] = focused_hub().source
        caps["viewportTransport"] = "long-poll"
        caps["recordingSeek"] = bool(runtime.capabilities.recordingSeek)
        active = getattr(app.state, "driver", None)
        caps["driver"] = (
            "line" if isinstance(active, LineDriver)
            else "press" if isinstance(active, PressBridgeDriver)
            else "mock"
        )
        caps["scene"] = session.kind
        caps["engine"] = session.engine
        return caps

    @app.get("/snapshot")
    def snapshot() -> dict:
        snap = runtime.snapshot()
        snap["capabilities"] = {
            **snap["capabilities"],
            "viewportStream": bool(runtime.capabilities.viewportStream),
            "viewportReady": any(hub.available for hub in hubs),
            "recordingSeek": bool(runtime.capabilities.recordingSeek),
        }
        return snap

    @app.get("/viewport/meta")
    def viewport_meta() -> dict:
        """Cheap status for the Control UI (no JPEG body)."""
        meta = focused_hub().meta()
        meta["enabled"] = bool(runtime.capabilities.viewportStream)
        return meta

    def _frame_response(hub: ViewportHub, after_seq: int, wait_ms: int) -> Response:
        if wait_ms > 0:
            got = hub.wait_newer(after_seq=after_seq, timeout=wait_ms / 1000.0)
        else:
            got = hub.latest()
            if got is not None and got[2] <= after_seq:
                # Immediate poll, no newer frame → 304 so client keeps last paint.
                return Response(
                    status_code=304,
                    headers={
                        "Cache-Control": "no-store",
                        "ETag": f'"{got[2]}"',
                        "X-Viewport-Seq": str(got[2]),
                        "X-Viewport-Source": hub.source,
                    },
                )

        if not got:
            raise HTTPException(503, "viewport not ready")

        payload, mime, seq = got
        age_ms = hub.meta().get("ageMs")
        return Response(
            content=payload,
            media_type=mime,
            headers={
                "Cache-Control": "no-store",
                "ETag": f'"{seq}"',
                "X-Viewport-Seq": str(seq),
                "X-Viewport-Source": hub.source,
                "X-Viewport-Age-Ms": str(age_ms if age_ms is not None else ""),
            },
        )

    @app.get("/viewport/frame")
    def viewport_frame(
        after_seq: int = Query(0, ge=0, alias="after_seq"),
        wait_ms: int = Query(0, ge=0, le=5000, alias="wait_ms"),
    ) -> Response:
        """Latest JPEG of the focused run, long-polling until ``seq > after_seq``.

        With several runs going, each has its own camera; ask for a run by id
        with ``/runs/{id}/viewport/frame``.
        """
        if not runtime.capabilities.viewportStream:
            raise HTTPException(503, "viewport unavailable")
        return _frame_response(focused_hub(), after_seq, wait_ms)

    @app.get("/runs/{run_id}/viewport/frame")
    def run_viewport_frame(
        run_id: str,
        after_seq: int = Query(0, ge=0, alias="after_seq"),
        wait_ms: int = Query(0, ge=0, le=5000, alias="wait_ms"),
    ) -> Response:
        """The camera of the sim running this run (503 once it is over)."""
        if not runtime.capabilities.viewportStream:
            raise HTTPException(503, "viewport unavailable")
        hub = hub_for_run(run_id)
        if hub is None:
            raise HTTPException(503, "run is not simulating")
        return _frame_response(hub, after_seq, wait_ms)

    @app.get("/viewport/stream")
    def viewport_stream() -> StreamingResponse:
        """Legacy multipart MJPEG (curl/VLC). Dashboard must not use this."""
        if not runtime.capabilities.viewportStream:
            raise HTTPException(
                503,
                "viewport stream unavailable (MuJoCo env / Renderer not started)",
            )
        return StreamingResponse(
            focused_hub().mjpeg_sync(fps=12.0),
            media_type="multipart/x-mixed-replace; boundary=frame",
            headers={
                "Cache-Control": "no-cache, private",
                "Pragma": "no-cache",
                "X-Accel-Buffering": "no",
                "X-Viewport-Source": focused_hub().source,
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
        events = runtime.events_for_run(run_id)
        if not detail and not events:
            raise HTTPException(404, "run not found")
        markers = []
        for ev in events:
            if ev.get("type") == "state_changed":
                markers.append(
                    {
                        "t": float(ev.get("t") or 0),
                        "state": ev.get("state"),
                        "label": ev.get("label"),
                        "station": ev.get("station"),
                        "seq": ev.get("seq"),
                    }
                )
            elif ev.get("type") == "run_finished":
                markers.append(
                    {
                        "t": float(ev.get("t") or 0),
                        "state": None,
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

    @app.get("/runs/{run_id}/video/{name}")
    def run_video(run_id: str, name: str) -> Response:
        """HLS playlist and segments for a run.

        The playlist grows while the run is live and gains #EXT-X-ENDLIST when
        it finishes, so the same URL is the live stream and then the replay.
        `name` is matched against a fixed pattern, so it cannot walk out of the
        run's directory.
        """
        got = servable(run_id, name)
        if got is None:
            raise HTTPException(404, "no video for run")
        path, mime = got
        live = name == PLAYLIST
        return Response(
            content=path.read_bytes(),
            media_type=mime,
            headers={
                # The playlist changes until the run ends; segments never do.
                "Cache-Control": "no-store"
                if live
                else "public, max-age=31536000, immutable",
                "Access-Control-Allow-Origin": "*",
            },
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

    @app.get("/experiments/{experiment_id}")
    def get_experiment(experiment_id: str) -> dict:
        """Durable experiment detail: a run's ``to_detail`` or a batch summary."""
        run = runtime.get_run(experiment_id)
        if run is not None:
            return {"kind": "run", **run}
        batch = runtime.get_batch(experiment_id)
        if batch is not None:
            return {"kind": "batch", **batch}
        raise HTTPException(404, "experiment not found")

    @app.post("/runs", status_code=201)
    def post_run(body: LaunchRunRequest) -> dict:
        try:
            return runtime.launch_run(
                name=body.name,
                seed=body.seed,
                scenario=body.scenario,
                cloth_type=body.clothType,
                cloth_condition=body.clothCondition,
                cloth_weights=body.clothTypeWeights,
                condition_weights=body.clothConditionWeights,
                custom_design=body.customDesign,
                speed=body.speed,
            )
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
                cloth_mix=body.clothMix,
                cloth_types=body.clothTypes,
                condition_mix=body.conditionMix,
                conditions=body.conditions,
                cloth_weights=body.clothTypeWeights,
                condition_weights=body.clothConditionWeights,
                custom_design=body.customDesign,
                speed=body.speed,
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
