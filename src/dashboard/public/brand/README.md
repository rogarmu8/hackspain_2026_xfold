# XFold · assets de marca

Camiseta de contorno angular con la manga derecha plegada sobre el pecho.
El naranja destaca el gesto de plegado; el símbolo también funciona en monocromo.
Paleta tomada de `src/dashboard/src/app/globals.css`.

## Archivos

| Uso | Archivo recomendado |
| --- | --- |
| Logo horizontal sobre fondos claros | `xfold-logo-primary.svg` |
| Símbolo sobre fondos claros | `xfold-mark-primary.svg` |
| Logo / símbolo sobre fondos oscuros | `xfold-{logo,mark}-reverse.svg` |
| Monocromo marrón, crema o naranja | `xfold-{logo,mark}-{ink,cream,orange}.svg` |
| SVG inline que hereda el color CSS | `xfold-mark-current.svg` |
| Favicon con fondo marrón | `xfold-favicon.svg` |
| Iconos PNG con fondo | `xfold-app-icon-{32,180,192,512}.png` |
| Símbolos PNG transparentes | `xfold-mark-*-512.png` |
| Logos PNG transparentes | `xfold-logo-*-1600.png` |
| Lámina de presentación | `xfold-brand-preview.png` |

Los SVG tienen fondo transparente, sin imágenes incrustadas ni fuentes externas.
El lettering «XFold» está dibujado con trazados propios. Las variantes de logo
horizontal usan un lienzo 320 × 96; los símbolos, 96 × 96.

## Consumo en el dashboard

Los archivos de esta carpeta se sirven desde `/brand/`:

```tsx
<img
  src="/brand/xfold-logo-primary.svg"
  alt="XFold"
  width={160}
  height={48}
/>
```

Para un símbolo junto a un nombre visible, usar `alt=""` y evitar que el lector
de pantalla anuncie la marca dos veces. `currentColor` solo hereda el color del
dashboard cuando el contenido del SVG se inserta inline; un `<img>` es aislado.

## Reglas de uso

- Nombre visible: **XFold**, respetando mayúsculas y minúsculas.
- Tinta: `#2A170F`; naranja: `#D96B2A`; crema: `#FAF6EC`.
- Tamaño recomendado del símbolo: 32 px; mínimo: 24 px. Para 16 px, preferir
  el favicon sobre fondo sólido y comprobar su lectura en el navegador final.
- Logo horizontal: ancho recomendado de 160 px o más.
- Conservar el espacio libre incluido en los lienzos; no recortar al contorno.
- No deformar, rotar, añadir sombras o cambiar el grosor de los trazos.
- Sobre naranja usar `ink`; sobre marrón usar `cream` o `reverse`.
- Naranja es un acento gráfico, no un color para texto pequeño sobre crema.

## Fuente editable y regeneración

La geometría compartida está en `scripts/branding/generate.mjs`.
Desde la raíz del repositorio:

```sh
node scripts/branding/generate.mjs
```

Usa `sharp` (dependencia de Next / árbol del monorepo). No instala
paquetes. Genera SVG y PNG a partir de la misma geometría.

**Consumo en el dashboard (ya cableado):**

- Favicon / PWA icons → `src/dashboard/src/app/layout.tsx` (`metadata.icons`)
- Wordmark del sidebar → `FoldLogo` en `AppShell`
- Marca móvil en header → `FoldMark` (`/brand/xfold-mark-primary.svg`)
