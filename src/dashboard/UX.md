# XFOLD — experiencia y comportamiento del centro de control

Estado: dirección visual clara elegida por el equipo; especificación de producto para implementación. No describe capacidades ya implementadas.

## Intención

Una mesa de trabajo industrial cálida: crema, tinta espresso, retícula precisa y una vista oscura de la celda como foco. Inspiración: segunda exploración visual aprobada, con geometría de HackSpain y sobriedad de THEKER.

La pantalla debe responder en cinco segundos: qué está pasando, si necesita atención y qué puedo hacer. Cada elemento debe ayudar a operar, revisar o decidir.

Composición: espacio de trabajo dominante, contexto lateral opcional, detalle bajo demanda. Interacción: selección estable, apertura discreta del inspector y cambios de estado sin alterar el layout.

## Presupuesto de información

- Una tarea principal por vista; una sola acción primaria por contexto.
- Centro de control: visor + etapas + contexto de ejecución. Sin franja de KPIs globales, gráficos históricos ni tabla de logs permanente.
- Máximo tres cifras de resumen en el contexto de batch: finalizadas/total, fallidas y pendientes. La ejecución activa se identifica aparte.
- Cola resumida: activa y hasta tres siguientes, con «Ver cola (N)».
- Una incidencia accionable visible; el resto en «Ver incidencias». No repetir un error en banner, toast y panel a la vez.
- El inspector sustituye el contexto lateral; no apilar paneles ni abrir varios a la vez.
- Si una cifra aparece en dos lugares de la misma vista, conservarla en el lugar donde se toma la decisión.
- Los datos avanzados requieren selección o navegación explícita. No ocultar errores activos, estado de conexión ni alcance de comandos.

## Arquitectura de información

Navegación principal: **Control · Experimentos · Historial**. Comparar es una acción de selección dentro de Experimentos, no otro destino vacío del MVP.

| Vista | Pregunta | Contenido principal | Fuera de esta vista |
| --- | --- | --- | --- |
| Control | ¿Qué ocurre ahora? | Celda, fase, ejecución, conexión, controles y batch activo si existe | Análisis histórico, configuración completa y log completo |
| Experimentos | ¿Qué he lanzado y qué resultado tiene? | Lista de individuales/batches; detalle con progreso, resultados y ejecuciones | Telemetría de alta frecuencia |
| Historial | ¿Qué pasó en esta ejecución? | Tabla filtrable y detalle con etapas, resultado y configuración | Controles sobre ejecuciones terminadas |

Una ejecución tiene una URL estable. Abrirla desde cualquier lista conserva filtros y contexto al volver. Revisión y directo usan la misma estructura visual, con etiquetas explícitas que los distinguen.

## Centro de control

```text
XFOLD / navegación | Control                    Conexión · Nuevo experimento
                  | ┌──────────────────────────┬─────────────────────────┐
                  | │ RUN-014 · En directo      │ Batch B-008 (si existe) │
                  | │                          │ 12/20 finalizadas       │
                  | │ Vista real de la celda    │ Activa + 3 siguientes   │
                  | │                          │ Ver todas               │
                  | ├──────────────────────────┤                         │
                  | │ Etapas del proceso       │ Acciones con alcance    │
                  | └──────────────────────────┴─────────────────────────┘
                  | Ver detalle de ejecución · Ver eventos
```

El visor ocupa aproximadamente dos tercios del espacio útil en escritorio. Navegación de 192–216 px; contexto de 288–336 px; separación de 24 px. Estas medidas son guía, no requisitos que provoquen overflow.

- Individual: omitir progreso y cola de batch; mostrar estado y acciones de esa ejecución.
- Sin actividad: «Sin ejecución activa» y «Nuevo experimento»; no mostrar ceros ficticios ni una cámara marcada en directo.
- Sin imagen disponible: explicar que la vista no está disponible; conservar telemetría real. No fingir streaming con el mockup generado.
- Etapas (OpenArm / protocolo actual): Recogida → Orientación → Tensado → Prensado → Plegado ninja → Tolva → Embolsado (`PICK → ORIENT → SPREAD → PRESS → FOLD → CHUTE → BAG`). Reinicio se muestra cuando ocurra, separado del resultado productivo. La referencia visual antigua (UR5e / FlipFold) no define el ciclo.
- Seleccionar una etapa abre duración, mediciones disponibles y eventos de esa etapa. Los eventos completos viven en el detalle, no compiten con la celda.

## Lanzamiento, batches y comandos

«Nuevo experimento» abre un Dialog (shadcn) modal: nombre opcional, semilla, **camisas en fila**, tipo de prenda (elegir / aleatoria / seleccionar en batch) y condición (limpia, rasgada, manchada, torcida, o aleatoria). 1 camisa = `POST /runs`; más de una = batch secuencial. Opciones avanzadas plegadas; validar antes de lanzar y resumir qué se ejecutará. El catálogo sale de `/capabilities`.

Batch significa grupo de ejecuciones, no paralelismo garantizado. MVP: cola secuencial. Distinguir pausa de la ejecución y pausa de la cola: «Pausar ejecución» y «Pausar cola» solo si el backend soporta cada acción.

- Comandos pendientes: «Pausa solicitada…» hasta confirmación del simulador; impedir envío duplicado.
- Cancelación: explicitar ejecución o batch y consecuencias sobre activa/pendientes antes de enviarla. No cancelar silenciosamente todo desde un control individual.
- Mostrar capacidades reales; no presentar botones funcionales para comandos aún no soportados.
- Desconexión: mantener los últimos datos, rotular «Sin conexión · último dato…», deshabilitar comandos y no reenviarlos automáticamente al reconectar.
- Reconexión: recuperar estado autoritativo. La ausencia de respuesta no equivale a éxito ni a fallo físico.

## Revisión y análisis

Detalle de ejecución: resumen de resultado/duración/motivo de fallo; etapas navegables; pestañas **Eventos · Métricas · Configuración**. Grabación solo si existe. «Repetir configuración» crea otra ejecución, no modifica la anterior ni promete resultado idéntico.

Detalle de batch: finalizadas/total, correctas/fallidas y tabla de ejecuciones. Tasa de éxito = correctas / (correctas + fallidas); mostrar denominador, excluir pendientes y canceladas, y explicar estados excluidos. Sin resultados elegibles, mostrar «—».

Comparaciones: mismas semillas/configuración cuando corresponda, tamaño de muestra visible, unidades y ámbito de cada gráfico. Tiempo simulado y tiempo real son magnitudes separadas. La planitud por sí sola no demuestra que la prenda esté extendida.

## Referencia visual

La identidad, los tokens y los componentes se definen en [DESIGN.md](DESIGN.md). Este documento conserva los flujos, presupuestos de información y criterios operativos.

## Comportamiento tranquilo y accesible

- No animar números continuamente ni desplazar listas mientras se leen. Actualizar telemetría visual a un ritmo legible, independiente del paso de física y del registro persistente.
- Mostrar «N eventos nuevos» cuando el usuario está revisando eventos antiguos; seguimiento automático solo si lo activa o permanece al final.
- Transiciones de 120–180 ms para inspector/selección; respetar reduced motion. Sin parpadeos permanentes.
- Foco visible, controles con nombre accesible, navegación por teclado. Al cerrar inspector/modal, devolver foco al origen. Anunciar cambios relevantes de estado, no cada muestra de telemetría.
- Bajo 1100 px: simplificar navegación y colocar contexto debajo o abrirlo bajo demanda. Bajo 768 px: una columna; no encoger tablas hasta hacerlas ilegibles. Conservar estado y controles; tablas con scroll horizontal localizado cuando sea necesario.

## Realidad del repositorio y alcance

Actualmente `page.tsx` muestra `SAMPLE_TELEMETRY`. El contrato en `packages/protocol` contiene `t`, `state`, `cycle`, `flatness` y `shirt_in_box`. Todavía no acredita runs persistentes, batches, comandos, streaming de imagen ni grabaciones.

La integración requerirá acordar IDs de ejecución/batch, configuración/semilla, estado de ciclo de vida, marcas de tiempo, eventos por etapa, resultados y confirmación de comandos. Este documento no modifica ese protocolo.

Primera implementación: composición de Control con fixtures identificados como **Datos de ejemplo**, estados vacío/desconectado/activo y detalle bajo demanda. Después lanzamiento y trazabilidad conectados al backend. Comparativas y grabaciones se añaden cuando existan datos y soporte.

## Revisión antes de considerar una pantalla terminada

- En cinco segundos se identifica ejecución, fase, conexión y siguiente acción.
- El primer viewport no exige interpretar gráficos ni leer logs para operar.
- Individual y batch tienen acciones de alcance inequívoco.
- Datos de ejemplo, ausentes y obsoletos se distinguen de datos reales actuales.
- Fallos y estados intermedios no quedan ocultos en un menú.
- No hay cifras duplicadas, porcentajes sin denominador ni valores sin unidades.
- El diseño funciona a 1440×900 y 1280×800, con zoom al 200% y teclado.
- La pantalla sigue siendo comprensible sin color y sin animaciones.

Referencias: https://hackspain.com · https://www.theker.ai · `../../SOLUTION.md`.
