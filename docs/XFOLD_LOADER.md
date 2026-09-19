# Loader XFOLD

Componente listo para importar en cualquier pantalla, panel o fallback de Suspense.
La geometría es la de la demo aprobada, sin
dependencias añadidas. El archivo canónico es `src/dashboard/src/lib/xfold-motion.mjs`.

```tsx
import { XFoldLoader } from "@/components/XFoldLoader";

// Indicador con nombre accesible (texto oculto por defecto).
<XFoldLoader />

// Estado de carga de un panel. Hacer coincidir surface con el fondo del panel.
<XFoldLoader size={80} label="Cargando simulación…" showLabel surface="var(--card)" />

// Fondo oscuro; decorative evita un anuncio redundante si ya hay otro estado.
<XFoldLoader size={40} tone="dark" surface="#2a170f" decorative />

// En un componente cliente: un solo ciclo, reiniciable con una key numérica.
<XFoldLoader loop={false} replayKey={replay} onComplete={handleComplete} />
```

| Prop | Predeterminado | Uso |
| --- | --- | --- |
| `size` | `64` | Ancho en px; alto proporcional 148/120 salvo `height`. |
| `height` | `size × 148/120` | Alto en px; combinar con `viewBox` para recortar el lienzo. |
| `viewBox` | `"0 0 120 148"` | viewBox del SVG; recorta el lienzo de animación. |
| `label` | `Cargando…` | Nombre del estado para lectores de pantalla. |
| `showLabel` | `false` | Hace visible el texto. |
| `decorative` | `false` | Oculta toda la animación a tecnologías de asistencia. |
| `playing` | `true` | `false` detiene y muestra la marca estática; al activar comienza de nuevo. |
| `loop` | `true` | Repetición; `false` ejecuta un ciclo y vuelve a la marca estática. |
| `speed` | `1` | Multiplicador, limitado a 0.1–4. |
| `replayKey` | `0` | Cambiar el número reinicia el ciclo. |
| `onComplete` | — | Callback al completar un ciclo sin repetición; usar desde componentes cliente. |
| `surface` | `var(--background, #f4ecd8)` | Color CSS del fondo real. Necesario para las caras opacas y su ocultación. |
| `tone` | `light` | Trazos claros sobre fondos oscuros con `dark`. |
| `className` | `""` | Espaciado o colocación del contenedor. |

## Integraciones incluidas

- `app/loading.tsx`: fallback de navegación de Next. No sustituye los estados
  de fetch locales; para estos, renderizar `XFoldLoader` mientras se carga.
- `XFoldBrandLink` en `AppShell`: un ciclo al entrar con ratón o foco de teclado.
  El enlace sigue llevando a ejecuciones. No captura clics ni añade gestos ocultos
  en pantallas táctiles. La posición del logo se conserva.

## Accesibilidad y ciclo de vida

- `prefers-reduced-motion`: muestra el símbolo estático y conserva el estado textual.
- Una sola región `status` con texto estable; no anuncia cada fase del plegado.
- Sin actualizaciones de estado de React por fotograma. Actualiza atributos SVG
  conservando los nodos existentes cuando su tipo no cambia.
- Detiene `requestAnimationFrame` fuera del viewport o en pestañas ocultas.
- Cancela animación y listeners al desmontar. No retrasa la llegada del contenido.
- Reservar el espacio del componente mediante `size` evita saltos de layout.

