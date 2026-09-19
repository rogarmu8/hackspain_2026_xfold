# TRACKING — checklist vivo

Actualizar al cerrar un bloque. Fecha del hackathon: _TBD_.

## Bloques ([SOLUTION.md §9](SOLUTION.md))

| # | Bloque | Owner | Status | Notas / PR |
|---|--------|-------|--------|------------|
| 0 | Empty cell (rigid) | A | ✅ | press_cell + stub cell.xml |
| 1 | Shirt lives (flex estable 10s) | B | 🟡 | ninja-fold `shirt_t.obj` in press + playground |
| 2 | FlipFold folds pre-laid shirt | C | ⬜ | **primer clip demo** |
| 3 | Press flattens wrinkled shirt | C | ⬜ | |
| 4 | Drop transfer → folder | C | ⬜ | |
| 5 | Arm + peel + suction | D | ⬜ | |
| 6 | Full FSM bin→box | E | ⬜ | |
| 7 | Randomization + metrics CSV | E | ⬜ | |
| 8 | T-shirt mesh / 2ª talla | B | ⬜ | solo si 6 OK |
| 9 | Slide + backup video | E (+todos) | ⬜ | |

Leyenda: ⬜ todo · 🟡 en curso · ✅ hecho · ⛔ bloqueado

## Métricas (cuando existan)

| Métrica | Último valor | Seed / N | Commit |
|---------|--------------|----------|--------|
| success rate | | | |
| flatness pre → post | | | |
| cycle_time_s | | | |
| grasp_fail count | | | |

## Obstáculos → cambios de diseño (Eje A)

| Día | Qué falló | Qué hicimos | Resultado |
|-----|-----------|-------------|-----------|
| | | | |

## Decisiones rápidas

| Cuándo | Decisión | Quién |
|--------|----------|-------|
| 2026-09-19 | Bus sim↔UI = **journal + REST/SSE** (no WS/gRPC al browser). Contrato vinculante: `docs/INTEGRATION_CONTRACT.md`. Detalle: `docs/BRIDGE.md`. | equipo |
| 2026-09-19 | Viewport MJPEG prefers `press_cell` (flex T + UR5e via `scene.build`); `cell.xml` keeps `overview` + cloth as fallback. No `shirt_free` proxy. | press track |
| 2026-09-19 | **SimSession** compartida + **PressBridgeDriver** (PressCycle → `emit_state` con `t=data.time`). Trajectory NPZ + `GET …/recording/frame?t=` + UI Replay con scrubber FSM. MockDriver solo si MuJoCo/press_cell falla. | bridge |
| 2026-09-19 | Viewport **primary** = long-poll JPEG (`/viewport/frame?after_seq&wait_ms`) via Next `/api/bridge` proxy. MJPEG multipart = legacy only (Safari black-box). Dual plane: journal SSE ≠ pixels. | bridge |
| 2026-09-19 | Dashboard **sin sidebar ni pestañas**: `/` = lista de ejecuciones (Experimentos + Historial fusionados), `/historial/{runId}` = vista de control (live si activa, **replay integrado** con scrubber si terminada). Eliminados `ExperimentsView`, `RunDetailView`, `RunReplayView`; `/experimentos`, `/historial`, `…/replay` redirigen. Batches = columna enlazable, `/experimentos/{batchId}` se mantiene. | dashboard |
| 2026-09-19 | **Consola en vivo** en la columna derecha de la vista de run. Nuevo evento de journal `log` (`level/message/source/t`) + `runtime.emit_log()`; `PressBridgeDriver` lo usa en lugar de `print`. UI: `ConsolePanel` con filtro de avisos, autoscroll y **watchdog de atasco** (8 s sin eventos ⇒ alerta). `RunSummaryPanel` compacto. Sin cambios de transporte. | dashboard + bridge |
| 2026-09-19 | **Para la rama `press`:** checklist completo en [`docs/TODO_PRESS_INTEGRATION.md`](docs/TODO_PRESS_INTEGRATION.md) (⬜ pendiente). Resumen: al mergear `main`, (a) `Line(model, data, log=lambda m: runtime.emit_log(run_id, m, source="line"))` en vez de `print` para que salga en la consola; (b) `viewport_mujoco.py` choca en diseño: `main` renderiza una `SimSession` compartida que avanza `PressBridgeDriver`; `press` avanza la `Line` dentro del renderer. El contrato pide que la física viva en un Driver — decidir antes de mergear. | press + bridge |
| 2026-09-19 | **Prenda en el experimento:** `garmentKind` (`tshirt`/`polo`/`tank`) + muestra CC0 del dataset Grigorev. Foto proyectada en UV del flex T (`garments/projected.png` / skin). Física = `shirt_t.obj` (151 verts). | dashboard + cloth |
| | | |
