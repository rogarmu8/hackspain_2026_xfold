# CLOTH — cómo simulamos la camiseta (teoría, MuJoCo 3.13, decisiones y recetas)

Owner: track **B · Cloth**. Código: `src/sim/src/xfold/shirt.py` · bench: `scripts/cloth_bench.py` · resultados: `data/cloth_bench/results.csv`.

Este documento existe para que nadie tenga que redescubrir a las 3 de la mañana por qué la tela explota, atraviesa la prensa o no se dobla. Léelo antes de tocar `flexcomp`.

---

## 0. TL;DR

| Decisión | Valor | Por qué |
|---|---|---|
| Motor de tela | `flexcomp` 2D nativo de MuJoCo (`dim="2"`, `type="direct"`) | Único camino soportado en 3.13; los plugins `elasticity.shell/membrane` **ya no existen**. |
| Inextensibilidad | `<edge equality="true">` (o `"vert"`) | Restricción dura de longitud de arista en el solver convexo. Es lo que hace que la tela no sea un chicle. |
| Rigidez a flexión | `<elasticity elastic2d="bend">` con `young` derivado de una rigidez a flexión objetivo `B` | Sin flexión la tela es una malla de cadena: se arruga infinito y no "plancha". Con flexión de más, rebota y se desdobla. |
| Integrador | `integrator="discrete"` + `solver="CG"` cuando hay `<elasticity>`; `implicitfast` si solo hay edge equality | En 3.13 cualquier `young>0` en flex **exige** `discrete` (error de carga si no). |
| Contacto | `internal="false"`, `selfcollide="auto"`, `radius=0.004`, `spacing≈0.035` | Autocolisión necesaria para que las capas dobladas no se atraviesen. `internal` es contraintuitivo y se desactivó por defecto en 3.3.1. |
| Superficies rígidas | **Gruesas (≥ 10 cm)** y **troceadas en tiles de ~15 cm, cada tile en su propio `<body>`** | Ver §4: la tela atraviesa cajas finas, y MuJoCo deja **50 contactos por par (body, flex)**: con una sola caja la tela se hunde y vibra para siempre; con 6×8 bodies se asienta a `vmax` 0.001 m/s. |
| Prensa | Actuador de posición con `forcerange`, no `mocap` | Un mocap aplasta capas dobles a través de la cama. La prensa real también es "compliant". |
| Forma | Rectángulo primero, luego contorno de camiseta en la misma rejilla | Misma física, mismos parámetros; solo cambia la máscara de celdas. |

Variantes en el código: `constraint` (solo edge equality), `hybrid` (edge equality + bend, **por defecto**), `hybrid_vert` (isometría locking-free, Chen–Kry–Vouga), `fem` (StVK stretch+bend, sin equality). El bench decide cuál se usa en la demo con criterios objetivos (§6).

---

## 1. Cómo se simula tela "en teoría"

Una prenda es una **superficie delgada casi inextensible con muy poca rigidez a flexión**. Todo el problema numérico viene de esa asimetría: la rigidez en el plano (estirar) es entre 10⁴ y 10⁶ veces mayor que la de flexión (doblar). Si se integra explícitamente, el paso de tiempo lo dicta la rigidez de estirado y la simulación se vuelve carísima o explota.

Familias de métodos, de más antiguo a más moderno:

1. **Masa–resorte** (Provot 1995). Vértices con masa unidos por resortes de estructura, cizalla y flexión. Simple, pero los resortes de estirado tienen que ser rigidísimos → paso de tiempo minúsculo o "super-elasticidad" (la tela se estira un 10–20 %). Provot ya proponía **clamp de aristas** a posteriori — el germen de las restricciones duras.
2. **Integración implícita** (Baraff & Witkin, *Large Steps in Cloth Simulation*, SIGGRAPH 1998). Backward Euler con el jacobiano de las fuerzas: se puede dar pasos grandes con estirado rígido. Es el paper fundacional de la tela en producción (Pixar, Maya nCloth). Idea clave: **la rigidez entra en la matriz que se resuelve, no como fuerza explícita**.
3. **Modelos de lámina (shell) por elementos finitos.** Energía de membrana (St. Venant–Kirchhoff u otro hiperelástico lineal en tensión–deformación, no lineal en deformación–desplazamiento) + energía de flexión discreta. Para la flexión, el estándar es el **operador cotangente / discrete shells** (Grinspun et al. 2003; Bergou et al. 2006 *A Quadratic Bending Model for Inextensible Surfaces*): si la superficie es casi isométrica, la energía de flexión es **cuadrática en las posiciones** y su Hessiano es **constante** → se precalcula una vez. Esto es exactamente lo que hace MuJoCo (ver §2).
4. **Restricciones en vez de fuerzas — PBD / XPBD** (Müller 2007; Macklin 2016). Estirado = restricción de distancia de arista resuelta por proyección Gauss–Seidel. Es lo que usan Unity/Unreal/Nvidia Flex. Incondicionalmente estable, poco preciso. MuJoCo hace algo parecido pero **dentro de un solver convexo global** (`edge equality`), así que no tiene los artefactos de orden de proyección de PBD.
5. **Isometría sin *locking*** (Chen, Kry & Vouga, *Locking-free Simulation of Isometric Thin Plates*, 2019). Problema clásico: si impones longitud exacta en cada arista de una malla triangular, la malla **no puede doblarse** sin violar alguna restricción (*membrane locking*) → tela artificialmente rígida, "de cartón", sobre todo en mallas gruesas. Solución: restringir el **tensor de deformación promediado por mínimos cuadrados móviles** alrededor de cada vértice, no cada arista. Es el paper que MuJoCo implementa como `equality="vert"` (3.5.0) para "cloth con mallas más gruesas".
6. **Contacto**: para tela, autocolisión y capas apiladas. Métodos: proximidad continua (Bridson 2002), y hoy **IPC — Incremental Potential Contact** (Li et al. 2020): barrera logarítmica + búsqueda de línea que garantiza no intersección. MuJoCo `main` ya tiene un flag `ipc` para el integrador `discrete`; **no está en 3.13**, así que no contamos con él.
7. **Aprendizaje / sim-to-real para manipulación robótica de prendas**: SoftGym (Lin 2020, sobre Nvidia Flex), GarmentLab (Isaac), y el más cercano a nosotros: **Almeida et al., *Clothing Simulation in MuJoCo with the Evaluation of the Sim-to-Real Gap using Robotic Manipulation*, ICARSC 2026** (INESC TEC, Best Paper WiE). Extienden una macro de generación de tela rectangular en MuJoCo a **contornos arbitrarios (camiseta)** y validan contra escaneos 3D reales de manipulación con robot. Conclusión de ellos que nos vale como argumento en la slide: MuJoCo reproduce el comportamiento global (pliegues, caída, forma tras manipular), no el detalle fino de arrugas.

### Parámetros físicos de tejido (para no inventarse números)

Valores típicos de punto de algodón (single jersey, el tejido de una camiseta), medidos con el sistema Kawabata (KES):

| Magnitud | Valor real aproximado | Nota |
|---|---|---|
| Densidad superficial | 150–200 g/m² | Camiseta M completa (dos capas + mangas): 0.14–0.20 kg |
| Grosor | 0.5–0.8 mm | |
| Rigidez a flexión `B` | 2·10⁻⁶ – 1·10⁻⁵ N·m (0.02–0.1 gf·cm²/cm) | Punto es mucho más blando que tejido plano |
| Rigidez a tracción `EA` (por unidad de ancho) | 10² – 10³ N/m (punto), 10³ – 10⁴ N/m (tejido plano) | Punto se estira mucho más a baja carga |
| Fricción tela–metal / tela–tela | µ ≈ 0.3–0.6 | Nosotros usamos 1.0 en la cama para que el doblez "agarre" |

Relación lámina: **`B = E·t³ / (12·(1−ν²))`**. Es la fórmula con la que `shirt.py` convierte una rigidez a flexión objetivo en un `young` para MuJoCo (con `poisson=0`, `thickness=1e-3`). Nuestros presets (`soft` 2·10⁻⁵, `medium` 1·10⁻⁴, `stiff` 5·10⁻⁴ N·m) son **deliberadamente 2–50× más rígidos que el jersey real**: una malla de 35 mm no puede representar arrugas de 5 mm, y algo de rigidez extra compra estabilidad y hace que la prensa "planche" de forma visible. Es una decisión de ingeniería, no un error; decirlo así en la slide.

> Cómo MuJoCo escala internamente `young·thickness³` para la flexión no está documentado con fórmula cerrada; la tabla de presets se calibra con el bench (§6), no con la fórmula. La fórmula solo fija el orden de magnitud y da un mando único (`B`) que tiene sentido físico.

---

## 2. Qué ofrece MuJoCo 3.13 y cómo mapea con la teoría

MuJoCo modela la tela como un **flex 2D**: cada vértice es un `body` puntual con 3 `slide` joints; los triángulos son elementos "con radio" que colisionan; las fuerzas de forma vienen de tres mecanismos combinables:

| Mecanismo MJCF | Teoría equivalente | Cuándo usarlo |
|---|---|---|
| `<edge equality="true">` | Restricción dura de longitud de arista (tipo PBD, pero en el solver convexo global de MuJoCo con `solref/solimp`) | Inextensibilidad barata y robusta. Funciona con `implicitfast`. Sin flexión propia. |
| `<edge equality="vert">` | Chen–Kry–Vouga 2019: isometría locking-free por promedio MLS del tensor de deformación | Mallas gruesas que deben doblarse limpiamente. **Exige configuración de reposo plana** (nuestro generador lo es; solo se puede rotar en yaw). |
| `<edge damping>` | Amortiguamiento viscoso por arista | Siempre >0. Mando principal del "vapor" en la variante `constraint`. |
| `<elasticity young poisson thickness elastic2d="bend">` | Discrete shells / operador cotangente: Hessiano constante precalculado en `mj_setConst` (coste por paso ≈ 0) | Rigidez a flexión física. **Compatible con edge equality.** |
| `<elasticity elastic2d="stretch"\|"both">` | St. Venant–Kirchhoff con FEM lineal (grandes rotaciones, pequeñas deformaciones) | Membrana FEM "de verdad". **Incompatible con edge equality** (error de carga). Más caro y más elástico. |
| `<elasticity damping>` | Amortiguamiento de Rayleigh (escala la matriz de rigidez) | Estabiliza modos de flexión. |
| `<contact selfcollide="auto">` | Sweep-and-prune sobre elementos del mismo flex | Necesario para doblar (capas). |
| `<contact internal="true">` | Anti-inversión de elementos con pares vértice–elemento predefinidos | **No** para tela; modifica el comportamiento elástico. Off por defecto desde 3.3.1. |
| `<contact passive="true">` | Penalización implícita en la métrica efectiva, sin fricción | Solo para drapeados sobre geometría estática. **Sin fricción → inútil para prensa/doblez.** |
| `integrator="discrete"` (3.13) | Velocity-stepping implícito en posición: métrica efectiva `M + hD + h²K` (Baraff–Witkin generalizado y unificado con el solver de contacto) | **Obligatorio** con `<elasticity>` en 3.13. Estable a cualquier `solref`. Ligeramente más amortiguado. Nuevo (sep-2026), "subject to change". |

Historia relevante (changelog) que explica por qué casi todo lo que hay en internet sobre tela en MuJoCo está desactualizado:

- 3.0 (2023): nace `flex`/`flexcomp`; flexión via plugin `mujoco.elasticity.shell`.
- 3.2.x: plugins `solid`/`membrane` absorbidos al motor.
- **3.3.1**: `internal` pasa a `false` por defecto.
- **3.3.3 (jun-2025): se elimina el plugin `shell`** → `elastic2d`. El snippet de `SOLUTION.md §4.3` y el de la issue #1433 **no cargan** en 3.13.
- 3.5.0 (feb-2026): `equality="vert"` (Chen–Kry–Vouga) e integración implícita de flex en `implicit/implicitfast`.
- 3.11 / 3.12: elasticidad de flex dentro del CG con métrica efectiva; `drape.xml`, `bag.xml`.
- **3.13.0 (sep-2026)**: llega `integrator="discrete"` y **se elimina** el camino implícito de flex bajo `implicitfast` → error de carga si hay `young>0` sin `discrete`.

Modelos de referencia del repo de MuJoCo (`model/flex/`) y qué parámetros usan:

| Modelo | Receta |
|---|---|
| `flag.xml` | 9×19, `edge equality="true" damping="0.001"`, CG, sin elasticidad. Bandera al viento. |
| `poncho.xml` | malla `direct` sobre maniquí; `edge equality="vert" damping="0.1"` + `elasticity young="3e5" poisson="0" thickness="8e-3" elastic2d="bend" damping="0.02"`; `discrete` + CG; `contact solref="0.003"`. (Muy rígido: es un poncho de fieltro.) |
| `drape.xml` | 13×13 `spacing=.055 radius=.004 mass=.25`; `elasticity young="2e4" poisson=".2" thickness="1e-3" elastic2d="both" damping="1e-2"`; contactos `passive`; `discrete`, CG, `iterations=400`. |
| `bag.xml` | tela con `elastic2d="stretch"` y `selfcollide="none"`; usa `ipc` (solo en `main`, no en 3.13). |
| OpenArm `cloth.py` (Manas-arumalla) | 9×9 autocolisionante con edge equality; agarre por `weld` a un body-vértice; doblez de esquina con un brazo (reducción de span 16–44 % según build: "deformable dynamics are chaotic"). |

---

## 3. Nuestra arquitectura

```
xfold/shirt.py
  ShirtParams(shape, size, spacing, radius, mass, model, bending, friction)
  build_flexcomp_xml(params)      -> <flexcomp type="direct" .../>   (rect | tshirt, misma rejilla)
  required_option(params)         -> integrator/solver que exige la variante
  landmarks(params)               -> ids de vértice: collar_*, hem_*, sleeve_*_tip
  vertices / flatness / span_ratio / aabb / top_layer_vertices(model, data, ...)
  set_steam(model, data, params, on)
scripts/cloth_bench.py            -> drop+crumple → 10 s estabilidad → prensa → doblez → CSV + PNG
src/sim/models/shirt.xml          -> generado (`python -P -m xfold.shirt --write ...`), incluido por cell.xml
```

Principios:

1. **Un único generador de geometría** (rejilla regular recortada por un contorno) para rectángulo y camiseta. Cambiar de forma o talla no cambia ningún parámetro físico; solo la máscara de celdas. Los ids de vértice de los *landmarks* (cuello, bajo, puntas de manga) salen del mismo generador, así el FSM/perception no busca esquinas por heurística.
2. **La física la fija `ShirtParams`, no XML suelto.** `cell.xml` incluye un `shirt.xml` generado; si alguien edita a mano el XML generado, se pierde en el siguiente `--write`.
3. **`required_option()` es ley**: la variante dicta el integrador de toda la escena. `check_model_option()` falla ruidosamente si `cell.xml` no coincide.
4. **Métricas desde el minuto uno**: el bench escribe `data/cloth_bench/results.csv`; las mismas funciones (`flatness`, `span_ratio`) se usan en `metrics.py` del ciclo real.

---

## 4. Lo que aprendimos rompiéndolo (hallazgos empíricos, MuJoCo 3.13, este Mac)

Todos verificados con scripts de sonda antes de escribir `shirt.py`. Si contradices alguno, aporta evidencia y actualiza esta tabla.

| # | Síntoma | Causa | Regla |
|---|---|---|---|
| 1 | `XML Error: plugin mujoco.elasticity.shell not found` | Plugin eliminado en 3.3.3 | Usar `<elasticity elastic2d=...>` nativo. Snippet de `SOLUTION.md §4.3` obsoleto. |
| 2 | `flex constraints and elasticity (young) cannot both be present` | `elastic2d="stretch/both"` + `edge equality` | Elegir: FEM puro (`fem`) **o** equality + `bend` (`hybrid`). |
| 3 | Error de carga con `<elasticity>` bajo `implicitfast` | 3.13 exige `discrete` para flex elástico | `required_option()`. |
| 4 | `flex vertices are not in the same plane` con `equality="vert"` | La isometría MLS necesita reposo plano; `euler` fuera del plano lo rompe | Generar plana; rotar solo yaw; arrugar con velocidades iniciales o dejándola caer. |
| 5 | La camiseta **atraviesa la cama de la prensa** y acaba en el suelo, en todas las variantes | Caja de 3 cm de grosor: los vértices (1 g cada uno, contacto blando) penetran más de la mitad del grosor y el collider los expulsa por la cara opuesta | **Cualquier superficie que soporte tela: ≥ 10 cm de grosor** (`size z ≥ 0.05`). Vale también para el platen. |
| 6 | Con cama gruesa la tela se hunde ~1 cm, **vibra para siempre** (`vmax` 0.25–0.4 m/s en reposo) y `ncon == 50` siempre | `engine_collision_driver.c::filterFlexContacts` deja `mjMAXCONPAIR = 50` contactos por par **(body, flex)** — por *body*, no por geom. Con 192+ vértices sobre un body, cada paso se apoyan 50 vértices distintos → chatter. Trocear en geoms del **mismo** body no sirve (seguían siendo 50; primer A/B nos engañó). | **Cada tile en su propio `<body>`**, tiles de ~14–15 cm (≤ ~50 puntos de contacto por tile). Medido: 1 caja → 50 contactos, vmax 0.3, centro de vértice 3.5 mm *bajo* la superficie; 3×4 bodies → 494 contactos, vmax 0.15; **6×8 bodies → 1084 contactos, vmax 0.001, centro a +3.9 mm = radius**. Helper: `shirt.tiled_surface_xml()`. |
| 7 | Tras prensar, vértices bajo la cama (`min z < 0`) | Platen `mocap` (fuerza infinita) aplasta zonas de doble capa (16 mm) en un hueco de 10 mm y las empuja a través de la cama | Platen con actuador `<position kp=2000 forcerange=±60>`; consigna a **1.5 diámetros** (12 mm) sobre la cama: aplasta capas dobles con fuerza limitada. (Con 3 diámetros el platen no llegaba a tocar la tela y la prensa era un no-op.) |
| 8 | `fem` (`elastic2d="both"`, young 2e4) se ve "gomoso": span tras prensa 0.32 vs 0.385 reposo, y el doblez no se queda | Membrana StVK blanda + sin restricción de arista | Para prendas manipuladas preferir `hybrid`. `fem` queda como comparación. |
| 9 | Con flexión rígida (`young=3e5, t=8e-3`, receta poncho) el doblez **rebota** y el span vuelve a ~reposo | `B ≈ 1.3·10⁻² N·m`: eso es cartón, 1000× el jersey | Bajar `B`; presets `soft/medium`. |
| 10 | Sin flexión (`constraint`) plancha peor (std z 0.010 vs 0.004 con `bend`) pero dobla bien (44 % de vértices en 2ª capa) | Sin energía de flexión no hay "memoria" de plano; tampoco resistencia a quedarse doblada | Es el fallback si `discrete` da problemas con el brazo. |
| 11 | Coste: 12×16 vértices (nv=576) → 1.1–1.8× tiempo real en portátil; `hybrid_vert` ≈ 0.5× | CG + autocolisión + restricciones | Demo en vivo a 12×16 / spacing 35 mm; no bajar de 25 mm sin medir. |

Números preliminares (sonda `/tmp/xfold_cloth_probe2.py`, 12×16, cama gruesa tileada, semilla única; **los sustituye el bench**):

| Variante | RT | flatness pre→post prensa (std z, m) | doblez: frac. 2ª capa | span tras doblez (reposo 0.385) |
|---|---|---|---|---|
| `constraint` (implicitfast) | 1.5× | 0.0085 → 0.0099 | 0.44 | 0.31 |
| `hybrid` bend rígido (poncho) | 1.1× | 0.0035 → 0.0036 | 0.44 | **0.45 (rebota)** |
| `hybrid` bend blando | 0.7× | 0.0089 → 0.0091 | 0.25 | 0.30 |
| `fem` (both, 2e4) | 1.1× | 0.030 → 0.029 | 0.00 | 0.31 |
| `hybrid_vert` (caída plana, sin arruga) | 0.55× | 0.0005 → 0.0010 | 0.64 | 0.25 |

---

## 5. Receta de tuning (en este orden, un cambio a la vez)

**Si explota / diverge (`mjWARN_BADQACC`, NaN):**
1. ¿Hay `<elasticity>` sin `integrator="discrete"`? → `required_option()`.
2. `timestep` 0.002 → 0.001. Subir `iterations` (200 → 400) y `tolerance` 1e-6.
3. Subir `edge damping` (0.1 → 1) y `elasticity damping` (0.02 → 0.05).
4. Bajar `young` (un preset de `bending`).
5. Rejilla más gruesa (`spacing` 0.035 → 0.045). **Nunca** compensar añadiendo complejidad al brazo.

**Si vibra en reposo / se hunde en la cama:** casi seguro tope de 50 contactos por body (§4 regla 6). Mira `data.ncon`: si es ≈50 con cientos de vértices apoyados, la superficie no está troceada en bodies. Nunca "arreglarlo" subiendo damping.

**Si atraviesa cosas:** §4 reglas 5–7 (grosor, tiles-por-body, platen compliant). Después: `radius` 0.004 → 0.006 (y `spacing` ≥ 6·radius), `solref` de contacto 0.005 → 0.002 (con `discrete` es estable a cualquier valor).

**Si se ve como cadena / no plancha:** pasar a `hybrid`, subir un preset de `bending`.

**Si el doblez se desdobla:** bajar un preset de `bending`; subir fricción de la cama (1.0 → 1.5); dejar 0.3 s de "asentar" antes de soltar; soltar a ≤ 5 mm de la cama.

**Si es lento:** `spacing` mayor; `selfcollide="none"` solo en fases donde no hay capas (peligroso: no en FOLD); `hybrid` en vez de `hybrid_vert`.

**"Vapor" (PRESS):** `set_steam(on=True)` escala `model.flex_stiffness` / `flex_bending` (en 3.13 no existe `flex_young`; `young` se compila en esos arrays) y sube el damping; al levantar, restaura. **Estado: experimental** — todavía no hemos demostrado un efecto medible en fuerzas tras editar los arrays en caliente; puede que el Hessiano de flexión precalculado necesite `mj_setConst` o recompilar el modelo. Es un truco de relajación de arrugas, no termodinámica — decirlo así.

---

## 6. Bench y criterios de aceptación

`pixi run -e mujoco python -P scripts/cloth_bench.py --variants constraint hybrid:medium hybrid_vert:medium fem --shapes rect tshirt --seeds 0 1 2`

Protocolo por fila: caída plana desde 0.30 m con yaw aleatorio + velocidades iniciales aleatorias en xy (σ 0.6 m/s) para arrugar → 10 s de estabilidad → prensa compliant → doblez cinemático de esquina (mano mocap + weld a un vértice) → soltar → 1 s.

| Métrica | Definición | Umbral para ser "variante de demo" |
|---|---|---|
| `stable` | sin warnings, finito, `max|qvel| < 0.05` a t=10 s | obligatorio |
| `flatness_post / flatness_pre` | std z tras prensa / antes | < 0.6 |
| `fold_layer_frac` | frac. vértices con z > cama + 3·radius tras soltar | ≥ 0.30 |
| `fold_span_ratio` | span en el eje del doblez tras soltar / antes | ≤ 0.7 |
| `penetration_post` | min z − (cama + radius) | > −0.010 m |
| `rt_factor` | s simulados / s de pared | ≥ 0.8 a 12×16 |

La variante por defecto de `cell.xml` es la que pasa todos los umbrales en `rect` **y** `tshirt` con 3 semillas; si ninguna, `constraint` (es la que menos supuestos hace). Resultado y fecha → `TRACKING.md`.

---

## 7. Interfaz con los demás tracks

- **Agarre (track D/arm):** `weld` entre el TCP y `shirt_{i}` (OpenArm lo hace así; MuJoCo issue #1556 confirma que pinzar un flex con dedos rígidos no funciona bien). Alternativa honesta: `adhesion` actuator en la pala. Vértices candidatos: `landmarks()`; evitar borde exterior (dribbling).
- **Percepción (track E):** `vertices()`, `flatness()`, `span_ratio()`, `aabb()` son las mismas funciones del bench. No leer `data.xpos` a mano.
- **Prensa/cama (track C):** cama y platen gruesos y tileados **un body por tile** (regla §4 · `shirt.tiled_surface_xml()`). El platen con `<position forcerange>`; `press_down()` = setpoint. Cama con fricción alta al doblar; para el volteo (CHUTE) bajar `geom_friction` de los tiles en runtime. Si la cama gira (tilt bed), los tiles son hijos del body con la bisagra: siguen siendo bodies distintos y el tope de 50 sigue siendo por tile.
- **Viewport (bridge):** la tela vive en `cell.xml` vía `<include file="shirt.xml"/>`; no toca el journal ni SSE.

---

## 8. Referencias

- Provot, X. (1995). *Deformation constraints in a mass-spring model to describe rigid cloth behavior*. Graphics Interface.
- Baraff, D., Witkin, A. (1998). *Large Steps in Cloth Simulation*. SIGGRAPH.
- Grinspun, E., Hirani, A., Desbrun, M., Schröder, P. (2003). *Discrete Shells*. SCA.
- Bergou, M., Wardetzky, M., Harmon, D., Zorin, D., Grinspun, E. (2006). *A Quadratic Bending Model for Inextensible Surfaces*. SGP.
- Müller, M. et al. (2007). *Position Based Dynamics*; Macklin, M. et al. (2016). *XPBD*.
- Narain, R., Samii, A., O'Brien, J. (2012). *Adaptive Anisotropic Remeshing for Cloth Simulation* (ARCSim).
- Chen, H., Kry, P., Vouga, E. (2019). *Locking-free Simulation of Isometric Thin Plates*. arXiv:1911.05204. ← base de `equality="vert"`.
- Li, M. et al. (2020). *Incremental Potential Contact*. SIGGRAPH. ← futuro `ipc` de MuJoCo.
- Almeida, F., Leão, G., Costa, C., Rocha, C., Sousa, A., Silva, L., Rocha, L., Veiga, G. (2026). *Clothing Simulation in MuJoCo with the Evaluation of the Sim-to-Real Gap using Robotic Manipulation*. ICARSC 2026, pp. 47–54. doi:10.1109/icarsc70216.2026.11523290.
- MuJoCo docs: XML Reference → `flexcomp`, `flex/elasticity`, `flex/contact`; Computation → *Integrators* (`discrete`); Changelog 3.3.1 / 3.3.3 / 3.5.0 / 3.11 / 3.13.
- MuJoCo issues #1433 (shirt flexcomp diverging), #1368 (config de flexcomp), #1556 / #1480 (agarre de flex con Panda).
- Manas-arumalla/openarm-control `openarm_control/cloth.py` (9×9 self-colliding, weld grasp).
