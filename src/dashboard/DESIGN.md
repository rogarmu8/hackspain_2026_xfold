---
version: alpha
name: XFOLD Warm Workbench
description: Centro de control robótico de superficies crema, tinta espresso y geometría de plegado.
colors:
  primary: "#D96B2A"
  on-primary: "#2A170F"
  primary-hover: "#E47B3D"
  canvas: "#F4ECD8"
  surface: "#FAF6EC"
  ink: "#2A170F"
  muted: "#6B5A4D"
  divider: "#D3C5AE"
  active: "#35858A"
  active-ink: "#205C60"
  active-surface: "#DFEFEB"
  danger: "#A12D2A"
  viewport: "#171918"
typography:
  heading:
    fontFamily: IBM Plex Sans
    fontSize: 28px
    fontWeight: 600
    lineHeight: 1.2
    letterSpacing: -0.02em
  section:
    fontFamily: IBM Plex Sans
    fontSize: 18px
    fontWeight: 600
    lineHeight: 1.4
  body:
    fontFamily: IBM Plex Sans
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: IBM Plex Sans
    fontSize: 14px
    fontWeight: 600
    lineHeight: 1.4
  caption:
    fontFamily: IBM Plex Sans
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.4
  data:
    fontFamily: IBM Plex Mono
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.5
    fontFeature: '"tnum" 1'
rounded:
  none: 0px
  sm: 4px
  md: 6px
spacing:
  xs: 4px
  sm: 8px
  compact: 12px
  md: 16px
  lg: 24px
  xl: 32px
components:
  workspace:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    padding: "{spacing.lg}"
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.label}"
    rounded: "{rounded.sm}"
    height: 44px
    padding: "{spacing.md}"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
    textColor: "{colors.on-primary}"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    height: 44px
    rounded: "{rounded.sm}"
  button-danger:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.danger}"
    height: 44px
    rounded: "{rounded.sm}"
  button-disabled:
    backgroundColor: "{colors.divider}"
    textColor: "{colors.muted}"
  status-active:
    backgroundColor: "{colors.active-surface}"
    textColor: "{colors.active-ink}"
    typography: "{typography.caption}"
    rounded: "{rounded.sm}"
  progress-active:
    backgroundColor: "{colors.active}"
    height: 8px
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    typography: "{typography.body}"
    height: 44px
    rounded: "{rounded.sm}"
  inspector:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    padding: "{spacing.lg}"
  metadata:
    backgroundColor: "{colors.canvas}"
    textColor: "{colors.muted}"
    typography: "{typography.caption}"
  simulation-viewport:
    backgroundColor: "{colors.viewport}"
    textColor: "{colors.surface}"
    rounded: "{rounded.none}"
---

# XFOLD — identidad visual

## Overview

Una mesa de trabajo de laboratorio: papel crema, rótulos en tinta espresso, controles naranjas y una ventana oscura a la celda robótica. La precisión viene de la alineación, la lectura estable de los datos y el espacio entre grupos. El operador debe sentir que puede entender y controlar el proceso.

Usuarios: equipo de ingeniería que lanza y revisa simulaciones; durante la demo, el jurado debe identificar la fase activa sin explicación. Contenido en español y nombres técnicos solo donde aportan información.

Dirección clara elegida por el equipo. [Referencia aprobada](design/control-room-reference.png): conservar crema, visor dominante, contexto lateral y geometría rectangular. Simplificar los paneles inferiores, el gran titular y los bordes del mockup. La escena fotográfica, los números y los textos generados son ilustrativos; no constituyen datos ni una especificación del mecanismo.

Este archivo define identidad y componentes; [UX.md](UX.md) conserva flujos, presupuesto de información y alcance. Los tokens son valores de referencia para implementar; la prosa explica su uso. El tema aún no se ha aplicado al código.

## Colors

Crema y espresso ocupan casi toda la interfaz. El naranja concentra la acción principal; el teal señala actividad. La escasez de bloques saturados hace que los estados sean reconocibles.

- `primary`: acción con texto `on-primary`. El hover aclara el naranja; oscurecerlo reduciría el contraste con espresso.
- `canvas` mantiene continuidad; `surface` separa formularios e inspector sin tarjetas flotantes.
- `ink`: lectura; `muted`: metadatos legibles.
- `divider`: separación decorativa. Los límites necesarios de inputs usan `muted`; el foco usa `ink`. El separador claro no identifica controles por sí solo.
- `active`: barras y marcas sin texto encima. Etiquetas: `active-ink` sobre `active-surface`.
- `danger`: errores y acciones destructivas. Correcta, Fallida, Activa y Pendiente conservan etiquetas e iconos distintos; actividad y éxito no se distinguen solo por color.
- `viewport`: fondo oscuro; etiquetas sobre franja opaca, nunca sobre píxeles arbitrarios del render.

Contrastes sRGB de pares opacos: espresso/naranja **4,96:1**, muted/crema **5,58:1**, active-ink/active-surface **6,40:1**, danger/surface **6,65:1**. Blanco/naranja (**3,45:1**) y blanco/teal (**4,31:1**) no sirven para texto normal. Estos cálculos no sustituyen la revisión de transparencias, foco y DOM final.

## Typography

Usar **IBM Plex Sans** y **IBM Plex Mono** configuradas en `src/app/layout.tsx` (`--font-plex-sans`, `--font-plex-mono`). Elegidas frente a Geist por un tono más industrial / humano–máquina sin romper la mesa crema. No incorporar otra fuente para reproducir literalmente los titulares de HackSpain. Comparativa de candidatos: `/tipografia`.

Aplicar los seis niveles del frontmatter: heading para página, section para grupos, body para formularios, label para controles, caption para metadatos y data para IDs/tiempos. Tablas: lectura a 14 px. Cifras tabulares; no truncar números ni cambiar su ancho durante actualizaciones.

Formato: `83,3 %`, `42 s`, `RUN-014`. Ausente: `—` con motivo accesible; nunca cero por desconocido. Unidades y distinción entre tiempo real y simulado visibles. Frases en sentence case, no mayúsculas extensas.

## Layout

Navegación de 208 px, espacio principal flexible e inspector de 312 px cuando haya contexto. Márgenes y separación de 24 px; header de unos 64 px. Medidas adaptables al contenido y al zoom. El visor es el foco, con etapas próximas y sin slogan ni franja de KPIs globales.

Un grupo tiene un título y una función. Cola resumida: activa más tres pendientes. El inspector sustituye el contexto lateral, no añade otra columna. Gráficos y logs completos pertenecen a revisión. Ver UX.md para límites y recorridos.

Bajo 1100 px mover contexto debajo o abrirlo bajo demanda. Bajo 768 px usar una columna, navegación compacta y etapas en lista. Conservar conexión y alcance de comandos. Scroll localizado en tablas, no horizontal de toda la página. A partir de 1440 px aprovechar el espacio para la celda, no ampliar indefinidamente texto.

## Elevation & Depth

Jerarquía mediante superficies y posición; paneles integrados sin sombras. Menús y diálogos son transitorios. El inspector de escritorio pertenece al layout. Fondo modal espresso al 24 %; no difuminar toda la aplicación.

Capas: contenido 0, cabecera fija 10 si hace falta, menú 20, fondo modal 30, diálogo 40, notificación 50. Ningún elemento decorativo por encima de controles.

## Shapes

Radios de 4 px en controles y 6 px en diálogos; visor rectangular. Divisores de 1 px. Foco de 2 px espresso con offset de 2 px; sobre el visor, usar surface. Iconos de trazo uniforme de 16–20 px; botones de solo icono con nombre accesible y área de interacción de 44 px.

Un pequeño motivo de pliegue puede acompañar XFOLD. No repetirlo como fondo, separador y gráfico. Atribución secundaria: «HackSpain ’26 · THEKER challenge».

## Components

| Componente | Tratamiento y comportamiento |
| --- | --- |
| Primario | Naranja, altura mínima 44 px, texto espresso. Uno por contexto; al abrir un diálogo, la acción principal pasa al diálogo. |
| Secundario | Superficie clara y borde muted. Cancelar usa danger y alcance explícito. |
| Navegación | Selección con fondo surface, marcador espresso y aria-current. Evitar grandes bloques naranjas en la barra. |
| Input | Etiqueta persistente, borde muted, ayuda debajo. Error con texto/icono; conservar valor. Placeholder no sustituye etiqueta. |
| Estado | Texto e icono, sin pulsación continua. Activo con tinta teal oscura sobre fondo claro, pendiente neutro, fallo danger. |
| Tabla | Filas mínimas de 44 px, separadores horizontales. Números a la derecha, IDs a la izquierda; acciones por teclado. |
| Etapas | Completada con check, activa con etiqueta, pendiente con número. Selección abre detalle sin ocultar estado real. |
| Inspector | Título, cerrar/volver y contenido seleccionado. Devolver foco al origen; no anidar inspectores. |
| Visor | Render auténtico con fuente y frescura. Sin render: placeholder honesto y telemetría disponible. Ampliar como acción secundaria. |

Estados comunes: hover sutil, pressed sin desplazar layout y focus-visible contrastado. Disabled con tokens explícitos y motivo próximo, no solo tooltip. Pending conserva ancho e indica «Pausa solicitada…» hasta confirmación, bloqueando duplicados.

Carga: skeleton estático del tamaño del contenido, sin números ficticios. Vacío: explicación corta y acción relevante. Desconectado: último dato con fecha, retirar directo y deshabilitar comandos. Reconciliación y estados operativos en UX.md.

Movimiento: feedback 120 ms, inspector 180 ms, ease-out; sin rebotes, contadores animados o reordenación automática. Reduced motion elimina transiciones. Anunciar cambios relevantes, no cada muestra de telemetría.

## Do's and Don'ts

- Mantener un foco, espacio libre y acciones de alcance inequívoco.
- Dejar métricas y eventos a una selección de distancia; conexión y fallos activos visibles.
- Usar la referencia como dirección artística y UX.md como contrato de comportamiento.
- Evitar mosaicos de tarjetas, sombras ornamentales, gradientes, slogans y cifras duplicadas.
- No añadir tema oscuro al MVP ni fuentes decorativas.
- No usar la imagen generada como streaming ni presentar fixtures como mediciones.
- No confundir comandos pendientes con estados confirmados.

## Maintenance

Cambiar primero tokens y justificación, después trasladarlos al tema CSS y componentes. El frontmatter no cambia la app automáticamente. No duplicar valores en otros documentos.

Antes de implementar, leer DESIGN.md y UX.md. Revisar contraste real, teclado, zoom al 200 %, estados vacío/desconectado/activo/fallido y pantallas de 1440×900 y 1280×800.

Formato inspirado en [design.md de Google Labs](https://github.com/google-labs-code/design.md/blob/main/docs/spec.md), versión alpha consultada el 18 de septiembre de 2026. Se adopta la estructura; no se ha instalado ni ejecutado su CLI. Referencias: [HackSpain](https://hackspain.com) y [THEKER](https://www.theker.ai).
