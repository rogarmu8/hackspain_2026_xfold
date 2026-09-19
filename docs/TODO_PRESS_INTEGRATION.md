# TODO — integrar la rama `press` con `main` (consola + bridge)

**Estado:** ⬜ pendiente · **Owner:** track press · **Bloquea:** ver logs de la `Line` en la consola del dashboard.

Este documento es para el agente/persona que mergee `press` en `main`. `main` ya tiene:

- Dashboard con vista única de run (`/historial/{runId}`) y **consola en vivo** (`ConsolePanel`).
- Evento de journal `log` + `runtime.emit_log(run_id, message, level, source, t)`.
- `PressBridgeDriver` + `SimSession` compartida (PR #6): la física la avanza el **Driver**, el viewport solo renderiza.

`press` tiene la línea completa (`xfold/line.py`: cinta, prensa, plegador de solapas) y un `viewport_mujoco.py` que **avanza la `Line` dentro del renderer**. Eso choca con `main`.

---

## Checklist

### 1. Merge mecánico

- [ ] `git merge main` en `press` (o rebase). Conflictos esperados: `TRACKING.md`, `src/sim/models/cell.xml`, `src/sim/src/xfold/bridge/viewport_mujoco.py` (+ menores).
- [ ] `TRACKING.md` / `cell.xml`: quedarse con ambos lados (son aditivos).
- [ ] `viewport_mujoco.py`: **quedarse con la versión de `main`** (render-only sobre `SimSession`). La lógica de `Line` que `press` metió ahí se mueve al Driver (paso 2).

### 2. La `Line` vive en un Driver, no en el renderer

Contrato: [`docs/INTEGRATION_CONTRACT.md`](INTEGRATION_CONTRACT.md) §1 y §4b. El renderer no posee `MjData` propio ni avanza física.

- [ ] Crear `src/sim/src/xfold/bridge/line_driver.py` copiando la estructura de [`press_driver.py`](../src/sim/src/xfold/bridge/press_driver.py) (`start/stop/_loop/_run_cycle/_emit/_log`).
- [ ] `SimSession._compile()` debe poder construir el modelo de la línea (`xfold.line.build()`) en lugar de `press_cell`. Mantener el fallback a `cell.xml`. Cámara: hoy `SimSession.camera` es un **nombre** (`render_jpeg()` → `renderer.update_scene(data, camera=self.camera)`, `sim_session.py:233`). Para usar `FollowCam` de `line.py` habría que aceptar también un `MjvCamera`; la opción barata es una cámara fija en `line.xml` con `name="overview"`.
- [ ] En `_run_cycle`, instanciar `Line(session.model, session.data, repeat=False, log=...)` y avanzar con `line.step()` **dentro de `session.lock`**, respetando `runtime.driver_active_run()` (pausa / cancel) igual que `BridgeLoop` en `press_driver.py`.
- [ ] Mapear `Line.stage` → `CellState` y llamar `runtime.emit_state(run_id, state, t=session.sim_time())` en cada cambio. Tabla orientativa (ajustar a los nombres reales de `Line._enter`):

  | `Line.stage` | `CellState` |
  |---|---|
  | load / belt in | `PICK` |
  | spread / steam | `SPREAD` |
  | press | `PRESS` |
  | flap folds | `FOLD` |
  | belt2 / peel | `CHUTE` |
  | bag / seal | `BAG` |

- [ ] Al terminar el ciclo: `runtime.finish_success(run_id, t)`; en excepción: `runtime.finish_failed(run_id, t, reason=str(exc))`.
- [ ] En [`app.py`](../src/sim/src/xfold/bridge/app.py) (~línea 87, donde se instancia `PressBridgeDriver(runtime, session)`), preferir `LineDriver` si `xfold.line.build()` compila; si no, `PressBridgeDriver`; si no hay MuJoCo, `MockDriver`.

### 3. Logs de la `Line` → consola del dashboard

- [ ] Sustituir el `log=print` de `Line` por el journal:

  ```python
  line = Line(
      session.model,
      session.data,
      repeat=False,
      log=lambda m: runtime.emit_log(run_id, m, source="line", t=session.sim_time()),
  )
  ```

- [ ] Niveles: `Line._enter` emite `info`. Añadir `level="warning"` cuando la cinta no alcanza la posición (`_belt_until` agota tiempo), `level="error"` en excepciones. Firma: `emit_log(run_id, message, level="info", source="sim", t=None)`.
- [ ] **No** loguear por paso de física. Granularidad: cambios de etapa, esperas largas (> 2 s) y anomalías. El watchdog de la UI marca **atasco a los 8 s sin eventos**; si una fase legítima dura más, emite un `log` intermedio (p. ej. `"prensa cerrada · vapor 4 s"`).

### 4. Verificación

- [ ] `pixi run bash scripts/check-bridge-contract.sh` en verde.
- [ ] Bridge arriba → `curl :8765/snapshot` muestra `activeRun.currentState` cambiando.
- [ ] Dashboard `/historial/RUN-00x`: viewport muestra la línea; la consola muestra líneas con `source = line` y `fsm`; sin badge «Atasco» durante un ciclo normal.
- [ ] Matar el driver a mitad de ciclo → «Atasco · N s» aparece en la consola a los 8 s.
- [ ] Anotar el merge y el mapeo `stage → CellState` definitivo en `TRACKING.md` (Decisiones rápidas) y marcar este fichero como ✅ o borrarlo.

---

## Referencias rápidas

- Runtime API: `emit_state`, `emit_log`, `finish_success`, `finish_failed`, `driver_active_run`, `bump_sim_time` — [`runtime.py`](../src/sim/src/xfold/bridge/runtime.py).
- Plantilla de driver con pausa/cancel y grabación de trayectoria: [`press_driver.py`](../src/sim/src/xfold/bridge/press_driver.py).
- Qué pinta la consola y cómo mapea eventos: [`src/dashboard/src/lib/console.ts`](../src/dashboard/src/lib/console.ts).
- Qué **no** hacer: `INTEGRATION_CONTRACT.md` §5 (no stdout scraping, no MjData duplicado, no bus paralelo).
