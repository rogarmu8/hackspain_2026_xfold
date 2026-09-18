# PLAN — 3 días · 4–5 personas · todos en Cursor

Fuente de verdad técnica: [`SOLUTION.md`](SOLUTION.md).  
Este archivo solo organiza **quién hace qué** y **cuándo**.

## Roles (rellenar nombres)

| Track | Owner | Ownership en repo | Bloques |
|-------|-------|-------------------|---------|
| **A · Cell** | _TBD_ | `models/scene*.xml`, bin/box/lights | **0** (gate de todos) |
| **B · Cloth** | _TBD_ | `models/shirt*.xml`, `xfold/shirt.py` | **1**, stretch **8** |
| **C · Machines** | _TBD_ | press, FlipFold, retract floor, `control/machines.py` | **2, 3, 4** |
| **D · Arm** | _TBD_ | peel + adhesion, Menagerie UR5e, `control/ik.py` | **5** |
| **E · FSM + demo** | _TBD_ | `control/fsm.py`, `perceive.py`, `metrics.py`, `scripts/*` | **6, 7, 9** |

Con 4 personas: fusionar **A+C** o **A+E**. Con 5: A solo el primer bloque y luego ayuda donde haya bloqueo.

## Contratos entre tracks (para no pisaros)

| Interfaz | Dueño | Contrato mínimo |
|----------|-------|-----------------|
| Shirt flex name / body | B | `flexcomp` name=`shirt`; vertices accesibles vía `data.flexvert_*` |
| Press setpoints | C | API Python: `press_down()`, `press_up()`, `retract_floor()` |
| Folder setpoints | C | `fold_left()`, `fold_right()`, `fold_bottom()`, `unfold()` |
| Peel tip frame | D | frame MJCF + mink `FrameTask` tip; `suction(on: bool)` |
| Flatness / grasp | E | `perceive.grasp_point()`, `perceive.flatness()`, `perceive.in_box()` |
| FSM states | E | `PICK → PLACE → PRESS → DROP → FOLD → PACK → RESET` |
| **Sim↔UI bus** | E (+UI) | **Contrato:** [`docs/INTEGRATION_CONTRACT.md`](docs/INTEGRATION_CONTRACT.md) — journal + REST/SSE; driver solo `runtime.emit_*` |

Si cambia un nombre de joint/body/actuator: **PR + mención en TRACKING**, no silencio en Discord.

## Git (ligero)

- `main` = siempre ejecutable (o al menos “viewer abre”).
- Ramas: `feat/cell`, `feat/cloth`, `feat/machines`, `feat/arm`, `feat/fsm`.
- PRs pequeños (< ~200 líneas si se puede). Merge varias veces al día.
- No force-push a `main`.
- Al final del día: 1 persona actualiza `TRACKING.md` en `main`.

## Cursor (todos)

1. Abrir **este** repo como root (no la home).
2. Empezar en **Plan Mode** solo si tocas arquitectura; si no, Agent directo en tu track.
3. Pegar en el chat: `Lee AGENTS.md + SOLUTION.md §9 y trabaja solo en <tu track>`. Si tocas sim↔UI: `Lee docs/INTEGRATION_CONTRACT.md y no inventes otro bus`.
4. Compartir avances con **shared transcript** o link de Cloud Agent cuando alguien se atasque.
5. No inventar stack nuevo (Isaac, ROS, RL, WebSocket/gRPC al browser) sin acuerdo del equipo + `TRACKING.md`.

## Ritmo de 3 días

### Día 1 — Escena viva + primer clip

| Mañana | Tarde | Gate de noche |
|--------|-------|---------------|
| **A** bloque 0 (todos esperan ~1h) | **B** cloth estable; **C** FlipFold con camiseta pre-colocada | Viewer + cloth 10s + **clip del fold** (bloque 2) |
| **D** stub peel/mocap en escena vacía | **D** adhesion prueba en cloth si B listo | No armar FSM completa aún |
| **E** esqueleto `demo.py` + carpeta `data/` | Documentar 1 obstáculo real en TRACKING | |

### Día 2 — Ciclo mecánico + brazo

| Mañana | Tarde | Gate de noche |
|--------|-------|---------------|
| **C** prensa + flatness + drop | **D** UR5e + mink pick/place a prensa | Bin→press→fold **o** press→fold→box sin brazo (fallback nuclear) |
| **B** tunear cloth / size param | **E** FSM parcial + métricas CSV | `flatness` baja tras press; CSV con ≥1 ciclo |

### Día 3 — Autonomía + jurado

| Mañana | Tarde | Gate |
|--------|-------|------|
| **E** FSM full + `eval.py` seeds | Slide + vídeo backup + ensayos demo | 1 ciclo unattended reproducible |
| Stretch size / T-mesh **solo si 6 OK** | Ensayo en vivo + fix bugs | No features nuevas tras T−2h |

## Definición de “hecho” para el jurado

1. Ciclo **bin → box** sin teclado.
2. Tarea real argumentada (load station humana).
3. Al menos **una métrica** (flatness o success) con antes/después.
4. Slide de 1 página + vídeo de respaldo.

## Comunicación (sugerido)

- Canal `#xfold-status`: un mensaje por persona al cerrar bloque (`done: fold clip` / `blocked: suction on flex`).
- Checkpoint 15 min al final de cada día frente a `TRACKING.md`.
