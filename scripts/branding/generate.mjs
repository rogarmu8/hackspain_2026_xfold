import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import sharp from 'sharp';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const out = path.join(root, 'src/dashboard/public/brand');
await fs.mkdir(out, { recursive: true });
const ink = '#2a170f', cream = '#faf6ec', orange = '#d96b2a';

// One extended sleeve and one reflected across the chest. No hidden geometry
// or background-coloured masks: the mark is genuinely transparent.
function mark(color, fold = color) {
  return `<g fill="none" stroke-width="4" stroke-linejoin="miter" stroke-linecap="square">
    <path stroke="${color}" d="M72 42V76H32V42L23 49 12 36 30 20H40L45 28H55L60 20H70"/>
    <path stroke="${fold}" d="M70 20 48 38 59 51 80 34 70 20Z"/>
  </g>`;
}

// Custom outlined lettering; SVG consumers do not need an installed font.
function lettering(color) {
  return `<g fill="${color}">
    <path d="M0 0H9L22 20 35 0H44L27 26 45 54H36L22 32 8 54H-1L17 26Z"/>
    <path d="M55 0H89V7H63V23H86V30H63V54H55Z"/>
    <path fill-rule="evenodd" d="M112 14C100 14 94 22 94 34S100 55 112 55 130 46 130 34 124 14 112 14ZM112 21C119 21 122 26 122 34S119 48 112 48 102 42 102 34 105 21 112 21Z"/>
    <path d="M139 0H147V43Q147 48 152 48H155V54H150Q139 54 139 43Z"/>
    <path fill-rule="evenodd" d="M184 0H192V54H185V49Q181 55 173 55C162 55 157 46 157 35S163 14 174 14Q180 14 184 19ZM175 21C168 21 165 27 165 35S168 48 175 48 185 43 185 35 182 21 175 21Z"/>
  </g>`;
}
function svg(w, h, body, label = 'XFold') {
  return `<svg xmlns="http://www.w3.org/2000/svg" width="${w}" height="${h}" viewBox="0 0 ${w} ${h}" role="img" aria-label="${label}">${body}</svg>\n`;
}
const variants = {
  ink: [ink, ink],
  cream: [cream, cream],
  orange: [orange, orange],
  primary: [ink, orange],
  reverse: [cream, orange],
};
for (const [name, [color, fold]] of Object.entries(variants)) {
  const icon = svg(96, 96, mark(color, fold), 'XFold · camiseta con manga plegada');
  const logo = svg(320, 96, `${mark(color, fold)}<g transform="translate(112 22)">${lettering(color)}</g>`);
  await fs.writeFile(path.join(out, `xfold-mark-${name}.svg`), icon);
  await fs.writeFile(path.join(out, `xfold-logo-${name}.svg`), logo);
  await sharp(Buffer.from(icon)).resize(512, 512).png().toFile(path.join(out, `xfold-mark-${name}-512.png`));
  await sharp(Buffer.from(logo)).resize(1600, 480).png().toFile(path.join(out, `xfold-logo-${name}-1600.png`));
}
await fs.writeFile(path.join(out, 'xfold-mark-current.svg'), svg(96, 96, mark('currentColor')));
const favicon = svg(96, 96, `<rect width="96" height="96" rx="18" fill="${ink}"/>${mark(cream, orange)}`);
await fs.writeFile(path.join(out, 'xfold-favicon.svg'), favicon);
for (const size of [32, 180, 192, 512]) {
  await sharp(Buffer.from(favicon)).resize(size, size).png().toFile(path.join(out, `xfold-app-icon-${size}.png`));
}

const board = svg(1440, 1040, `
  <rect width="1440" height="1040" fill="#f4ecd8"/>
  <g font-family="Helvetica,Arial,sans-serif" fill="${ink}">
    <text x="72" y="68" font-size="17" letter-spacing="3">XFOLD / BRAND ASSETS</text>
    <text x="1368" y="68" text-anchor="end" font-size="15">HackSpain ’26</text>
    <path d="M72 96H1368" stroke="#d3c5ae"/>
    <g transform="translate(284 146) scale(2.7)">${mark(ink, orange)}<g transform="translate(112 22)">${lettering(ink)}</g></g>
    <text x="720" y="454" text-anchor="middle" font-size="18" fill="#6b5a4d">Una manga plegada. Un gesto reconocible.</text>
    <rect x="72" y="510" width="414" height="298" rx="8" fill="${cream}"/>
    <g transform="translate(183 548) scale(2)">${mark(ink)}</g>
    <text x="96" y="779" font-size="14">01 / MONOCROMO</text>
    <rect x="510" y="510" width="414" height="298" rx="8" fill="${ink}"/>
    <g transform="translate(621 548) scale(2)">${mark(cream, orange)}</g>
    <text x="534" y="779" font-size="14" fill="${cream}">02 / FONDO OSCURO</text>
    <rect x="948" y="510" width="420" height="298" rx="8" fill="${orange}"/>
    <g transform="translate(1062 548) scale(2)">${mark(ink)}</g>
    <text x="972" y="779" font-size="14">03 / SUPERFICIE DE MARCA</text>
    <text x="72" y="870" font-size="14" letter-spacing="2">ESCALA REAL</text>
    <g transform="translate(72 890) scale(.25)">${mark(ink, orange)}</g>
    <g transform="translate(124 886) scale(.333333)">${mark(ink, orange)}</g>
    <g transform="translate(190 878) scale(.5)">${mark(ink, orange)}</g>
    <g transform="translate(276 870) scale(.666667)">${mark(ink, orange)}</g>
    <text x="720" y="876" font-size="14">TINTA #2A170F</text>
    <text x="950" y="876" font-size="14">NARANJA #D96B2A</text>
    <text x="1200" y="876" font-size="14">CREMA #FAF6EC</text>
    <path d="M72 964H1368" stroke="#d3c5ae"/>
    <text x="72" y="1003" font-size="14" fill="#6b5a4d">SVG vectorial · PNG transparente · lettering trazado · iconos de aplicación</text>
  </g>`);
await sharp(Buffer.from(board)).png().toFile(path.join(out, 'xfold-brand-preview.png'));
console.log(`Brand assets written to ${out}`);
