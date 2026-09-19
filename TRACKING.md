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
| 2026-09-19 | Launch form: cloth type + condition (exact or random, with weights) and shirts-in-a-row mix (`same` / `random` / `list`). Random draws and skewed heading use `seed`. Catalogue on `GET /capabilities`; `LineDriver` rebuilds `SimSession` when the SKU changes. | dashboard + bridge |
| 2026-09-19 | Custom garment: catalogue key `custom`. Launch form: pick Personalizada → photo → auto cut-out preview; `POST /runs` `customDesign` bakes `_custom_garment.png` (both faces) and cuts `garment_custom.obj` to the detected outline. Not drawn in random mixes. Pixels off the journal. | dashboard + bridge |
| 2026-09-19 | **SimSession** compartida + **PressBridgeDriver** (PressCycle → `emit_state` con `t=data.time`). Trajectory NPZ + `GET …/recording/frame?t=` + UI Replay con scrubber FSM. MockDriver solo si MuJoCo/press_cell falla. | bridge |
| 2026-09-19 | Viewport **primary** = long-poll JPEG (`/viewport/frame?after_seq&wait_ms`) via Next `/api/bridge` proxy. MJPEG multipart = legacy only (Safari black-box). Dual plane: journal SSE ≠ pixels. | bridge |
| 2026-09-19 | Dashboard **sin sidebar ni pestañas**: `/` = lista de ejecuciones (Experimentos + Historial fusionados), `/historial/{runId}` = vista de control (live si activa, **replay integrado** con scrubber si terminada). Eliminados `ExperimentsView`, `RunDetailView`, `RunReplayView`; `/experimentos`, `/historial`, `…/replay` redirigen. Batches = columna enlazable, `/experimentos/{batchId}` se mantiene. | dashboard |
| 2026-09-19 | **Consola en vivo** en la columna derecha de la vista de run. Nuevo evento de journal `log` (`level/message/source/t`) + `runtime.emit_log()`; `PressBridgeDriver` lo usa en lugar de `print`. UI: `ConsolePanel` con filtro de avisos, autoscroll y **watchdog de atasco** (8 s sin eventos ⇒ alerta). `RunSummaryPanel` compacto. Sin cambios de transporte. | dashboard + bridge |
| 2026-09-19 | **Estación QC + try-on.** Tras la prensa la cinta para la prenda bajo `qc_cam`, las luces de la línea bajan a `QC_DIP` y disparan dos flashes; el `LineDriver` captura un cuadrado de 768 px en el pico y lo guarda en `data/photos/{run}.jpg` (`GET /runs/{id}/photo`, `hasPhoto` en el detalle). La bajada de luz no es decorativa: la iluminación general quema el blanco a 1 m y se lleva el estampado y la mancha. El dashboard lo muestra en `ProductShotPanel`; el botón llama a `/api/tryon` (Next, server-side) → OpenAI `images/edits` (`gpt-image-1`), con `OPENAI_API_KEY` en `.env.local`; devuelve base64, así que la ruta entrega un data URI y no se guarda nada. La imagen nunca pasa por el journal. | press + bridge + dashboard |
| 2026-09-19 | **`press` integrada** (cierra `docs/TODO_PRESS_INTEGRATION.md`, borrado). La `Line` vive en `bridge/line_driver.py`, no en el renderer: `SimSession` compila `line.xml` (fallbacks `press_cell` → `cell.xml`, expuestos como `scene` en `/capabilities`) y el `LineDriver` la avanza dentro de `session.lock`, respetando pausa/cancel. Logs de `Line` → `emit_log(source="line")`. Mapa de etapas (monótono; `BELT` solo cuenta la primera vez): LOAD→PICK · BELT→SPREAD · PRESS/STEAM/LIFT→PRESS · SETTLE/BAGGER/FOLD→FOLD · BAG/TILT/PEEL/RELEASE→CHUTE · INDEX/SEAL/DONE→BAG. Cámara: `FollowCam` en vivo, `overview` fija para el seek. | press + bridge |
| 2026-09-19 | Flat lay = hang → opposite corner → set down on the press → slide both hands to the T pose. | press track |
| 2026-09-19 | Retook `feat/shirt-flexcomp` cloth: 410-vert `shirt_t.obj`, bend FEM + edge equality, per-vertex contact spheres. Press cell still owns spawn/pinch. | press track |
| 2026-09-19 | Merged `new-shirt-from-press` (384-vert T: 0.65 m hem-to-collar, 0.91 m sleeve-to-sleeve, short hanging sleeves). Line resized for it: folder 0.305–0.98 with hem hinge at x=0.642 and side hinges at ±0.16, belt 2 starts at 0.985, bag hull 45 mm tall for the 33 mm pack. Belt 1 is 0.97 m wide (sleeves 0.91 m) and `xfold.line.build` moves the press columns out to y=±0.54: at ±0.46 they snagged the sleeves, which then slid under the folder flaps and flipped up through them. | press track |
| 2026-09-19 | Line extended past the folder: the fold plate is a **peel** that slides the pack through rails into an open bag; top film drops, seal bar + RFID stamp act together, belt 2 drops the bag into a carton. Bag is a dynamic body; shirt is fixed in its frame once the peel is out (bag films do not collide with cloth). | press track |
| 2026-09-19 | Simplified to a line with **no arms**: shirt arrives flat on a belt → belt stops it under the press, platen presses on the belt (press bed/table removed) → belt runs it onto a FlipFold-style flap folder (left, right, hem). `moon run sim:run` = `xfold.line`; viewport renders `line.xml`. Arm cell (`press_cell.xml`, `load_press.py`) no longer wired. | press track |
| 2026-09-19 | Shirt silhouette: iconic crew-neck T (circular U-neck, hanging short sleeves, stadium hem) instead of the boxy plus-sign panel. Same `shirt_t.obj` / ninja thirds. | cloth track |
| 2026-09-19 | **La simulación es la fuente de verdad:** `LINE_PHASES` + `Line.on_event` sustituyen el uso del mapa antiguo PICK→BAG. UI consume catálogo/labels emitidos; transportes, inserción y sellado tienen tiempos propios. Integrada la estación QC de main: `TO_QC` y `PHOTO` separadas de prensado, resultados de captura estructurados y avisos si no hay GL/falla la cámara. Logs con fase/operación/estación/paralelo y timestamp sim exacto; planitud σz y AABB medidas, bolsa desconocida=null. Config efectiva por ejecución (SKU/malla/textura/condición) y uso real de seed explícitos; integrados los sorteos ponderados y rumbo inicial sembrado de main. LOAD registra yaw/offset reales. Timeline sin fase terminal ficticia, replay qpos etiquetado parcial, aviso de silencio no afirma atasco. Física y REST/SSE sin rediseño. Persistencia tras reinicio, replay completo y validación de calidad siguen pendientes. | sim + bridge + dashboard |
| 2026-09-19 | **Infeed orient** before the press. Default (`good`) is square; **skewed** is a random heading. A **dual conveyor product turner** (two independent lanes) yaws the shirt collar-downstream; linear belt overlaps the turner by 2 cm. Phase `ORIENT` sits between LOAD and TO_PRESS. Overhead `orient_cam` (top-down, same convention as `qc_cam`) is the plant sensor; belts still turn from cloth-vertex heading, not OpenCV. | press track |
| | | |
