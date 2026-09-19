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
| 2026-09-19 | Flat lay = hang → opposite corner → set down on the press → slide both hands to the T pose. | press track |
| 2026-09-19 | Retook `feat/shirt-flexcomp` cloth: 410-vert `shirt_t.obj`, bend FEM + edge equality, per-vertex contact spheres. Press cell still owns spawn/pinch. | press track |
| 2026-09-19 | Merged `new-shirt-from-press` (384-vert T: 0.65 m hem-to-collar, 0.91 m sleeve-to-sleeve, short hanging sleeves). Line resized for it: folder 0.305–0.98 with hem hinge at x=0.642 and side hinges at ±0.16, belt 2 starts at 0.985, bag hull 45 mm tall for the 33 mm pack. Belt 1 is 0.97 m wide (sleeves 0.91 m) and `xfold.line.build` moves the press columns out to y=±0.54: at ±0.46 they snagged the sleeves, which then slid under the folder flaps and flipped up through them. | press track |
| 2026-09-19 | Line extended past the folder: the fold plate is a **peel** that slides the pack through rails into an open bag; top film drops, seal bar + RFID stamp act together, belt 2 drops the bag into a carton. Bag is a dynamic body; shirt is fixed in its frame once the peel is out (bag films do not collide with cloth). | press track |
| 2026-09-19 | Simplified to a line with **no arms**: shirt arrives flat on a belt → belt stops it under the press, platen presses on the belt (press bed/table removed) → belt runs it onto a FlipFold-style flap folder (left, right, hem). `moon run sim:run` = `xfold.line`; viewport renders `line.xml`. Arm cell (`press_cell.xml`, `load_press.py`) no longer wired. | press track |
| 2026-09-19 | Shirt silhouette: iconic crew-neck T (circular U-neck, hanging short sleeves, stadium hem) instead of the boxy plus-sign panel. Same `shirt_t.obj` / ninja thirds. | cloth track |
| | | |
