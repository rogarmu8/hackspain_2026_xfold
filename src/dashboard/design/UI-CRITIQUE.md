# XFOLD — revisión Interface Craft

## Context

Centro de control para un equipo de ingeniería bajo presión de hackathon. El operador necesita reconocer actividad, incidencias y alcance de las acciones sin leer documentación técnica.

## First Impressions

La dirección crema/espresso es reconocible, pero el visor y el panel lateral parecen ensamblados por separado. El esquema ocupa mucho espacio oscuro con poca información; las etiquetas repetidas y los marcos alrededor de las seis etapas fragmentan la lectura.

## Visual Design

- **Jerarquía del visor:** el encabezado, título interior, franja inferior y pie repiten fase/contexto. Conservar un encabezado, un esquema y una franja breve de mediciones.
- **Bordes acumulados:** seis etapas con contornos completos producen seis pequeñas tarjetas. Usar una única tira de proceso; solo la selección y actividad reciben énfasis.
- **Iconos:** símbolos tipográficos y SVG propios no constituyen una familia consistente. Lucide para acciones y navegación; conservar el símbolo propio de XFOLD.
- **Progreso nativo:** su apariencia depende del navegador. Progress debe usar el teal semántico y dimensiones del sistema.

## Interface Design

- Recuperar espacio para el trabajo eliminando textos de implementación como «muta el adaptador» y manteniendo una identificación breve de demo.
- Abrir detalle de etapa en Sheet con título, foco y cierre por Escape; el detalle no empuja el resto de la pantalla hacia abajo.
- Confirmar cancelación con AlertDialog: alcance y consecuencias claros, retorno seguro del foco.
- Nuevo experimento usa Field, Input y ToggleGroup. Los errores deben señalar el campo y conservar los valores.

## Consistency & Conventions

Button, Badge, Progress, Tabs, Table, Alert y Empty comparten tokens y variantes. Links con aspecto de botón usan composición de shadcn. Navegación por teclado y foco forman parte del comportamiento del componente, no se recrean por pantalla.

## User Context

El operador tiene poco tiempo. Una respuesta clara a pausar o cancelar aporta más que una animación ornamental. Los datos obsoletos deben permanecer identificados; un fallo no debe borrar el contexto que permite entenderlo.

## Top Opportunities

1. Aplicar los tokens XFOLD al sistema semántico de shadcn, incluyendo estados y contrastes.
2. Reducir el centro de control a un foco, una tira de proceso y contexto operativo compacto.
3. Unificar formularios, confirmaciones y detalle progresivo con componentes accesibles.
4. Corregir el visor móvil: altura basada en contenido, sin métricas tapadas por una franja absoluta.
5. Añadir feedback de 120–180 ms y respetar reduced motion; ningún número debe saltar de posición.

Referencia metodológica: Interface Craft, Design Critique. La migración conserva el adaptador existente; no habilita integración física con MuJoCo.
