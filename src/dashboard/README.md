Next.js monitor for XFOLD. Run from the repo root:

```bash
moon run dashboard:dev
```

See the root [README](../../README.md).

Before changing the interface, read [DESIGN.md](DESIGN.md) for visual identity,
tokens and components, and [UX.md](UX.md) for flows and information limits.
The [approved visual reference](design/control-room-reference.png) is a generated
mockup with illustrative data, not a screenshot of the simulator.


### Componentes y tema XFOLD

La interfaz utiliza shadcn/ui (preset Nova, primitivas Radix) y Lucide. Los componentes viven en `src/components/ui`; el tema semántico de Tailwind v4 está centralizado en `src/app/globals.css`. Mantener los colores crema, espresso, naranja para acción principal y teal para estado activo. No sobrescribir colores por pantalla.

El centro de control utiliza Sheet para consultar etapas sin expandir el layout, AlertDialog para confirmar cancelaciones, Progress para el batch y ToggleGroup para los escenarios. El formulario utiliza Field/Input y ToggleGroup; las tablas comparten las primitivas de shadcn. La revisión de Interface Craft está en `design/UI-CRITIQUE.md`.

La vista sigue usando datos de demostración: el esquema de la celda no es una imagen de MuJoCo y los lanzamientos se realizan en el adaptador local.
