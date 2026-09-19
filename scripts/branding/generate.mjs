import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import sharp from 'sharp';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const out = path.join(root, 'src/dashboard/public/brand');
await fs.mkdir(out, { recursive: true });
const ink = '#2a170f', cream = '#faf6ec', orange = '#d96b2a';

// Both sleeves share the same 18-unit shoulder diagonal and 12-unit cuff.
// Reflect the right sleeve inward about x=72. Outline the fold explicitly:
// its top/right edges meet the silhouette at y=18/x=74, without stroke-cap
// gaps or the protruding miter of an acute closed stroke.
function mark(color, fold = color) {
  const diagonal = 2 * Math.SQRT2;
  return `<g fill="none" stroke-width="4" stroke-linejoin="miter" stroke-linecap="square">
    <path stroke="${color}" d="M72 76H32V44L26 50 14 38 32 20H40L45 28H55L60 20H72V76Z"/>
    <path fill="${fold}" fill-rule="evenodd" d="M${74 - diagonal} 18H74V${44 + diagonal - 2}L66 ${50 + diagonal}L${54 - diagonal} 38Z M70 ${22 + diagonal}L${54 + diagonal} 38L66 ${50 - diagonal}L70 ${46 - diagonal}Z"/>
  </g>`;
}

// Wide, heavy uppercase lettering, 38 units high. F and O share their top
// rail while the open lower F stays legible. Original font-free outlines.
function lettering(color) {
  return `<g fill="${color}">
    <path d="M0 0H12L19 11 26 0H38L25 19 38 38H26L19 27 12 38H0L13 19Z"/>
    <path d="M44 0H89V8H54V16H73V24H54V38H44Z"/>
    <path fill-rule="evenodd" d="M87 0H109L117 8V30L109 38H87L79 30V8ZM91 8 89 10V28L91 30H105L107 28V10L105 8Z"/>
    <path d="M123 0H133V30H152V38H123Z"/>
    <path fill-rule="evenodd" d="M157 0H183L193 10V28L183 38H157ZM167 8V30H178L183 25V13L178 8Z"/>
  </g>`;
}
function svg(w, h, body, label = 'XFOLD') {
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
  const icon = svg(96, 96, mark(color, fold), 'XFOLD · camiseta con manga plegada');
  const logo = svg(320, 96, `${mark(color, fold)}<g transform="translate(112 29)">${lettering(color)}</g>`);
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

// ICO container with PNG-encoded entries (ICONDIR + ICONDIRENTRY per image).
// Written both to /brand and to app/favicon.ico, the Next.js file convention
// that otherwise ships the framework's stock icon.
const icoSizes = [16, 32, 48];
const icoPngs = await Promise.all(icoSizes.map((s) => sharp(Buffer.from(favicon)).resize(s, s).png().toBuffer()));
const icoHeader = Buffer.alloc(6 + 16 * icoSizes.length);
icoHeader.writeUInt16LE(0, 0);
icoHeader.writeUInt16LE(1, 2);
icoHeader.writeUInt16LE(icoSizes.length, 4);
let icoOffset = icoHeader.length;
icoSizes.forEach((s, i) => {
  const entry = 6 + 16 * i;
  icoHeader.writeUInt8(s, entry);
  icoHeader.writeUInt8(s, entry + 1);
  icoHeader.writeUInt8(0, entry + 2);
  icoHeader.writeUInt8(0, entry + 3);
  icoHeader.writeUInt16LE(1, entry + 4);
  icoHeader.writeUInt16LE(32, entry + 6);
  icoHeader.writeUInt32LE(icoPngs[i].length, entry + 8);
  icoHeader.writeUInt32LE(icoOffset, entry + 12);
  icoOffset += icoPngs[i].length;
});
const ico = Buffer.concat([icoHeader, ...icoPngs]);
await fs.writeFile(path.join(out, 'xfold-favicon.ico'), ico);
await fs.writeFile(path.join(root, 'src/dashboard/src/app/favicon.ico'), ico);

// Open Graph card: reverse wordmark on ink.
const og = svg(1200, 630, `
  <rect width="1200" height="630" fill="${ink}"/>
  <g transform="translate(240 207) scale(2.25)">${mark(cream, orange)}<g transform="translate(112 29)">${lettering(cream)}</g></g>
  <text x="600" y="500" text-anchor="middle" font-family="Helvetica,Arial,sans-serif" font-size="30" letter-spacing="6" fill="${cream}" opacity=".7">CENTRO DE CONTROL</text>`);
await sharp(Buffer.from(og)).png().toFile(path.join(out, 'xfold-og.png'));

const board = svg(1440, 1040, `
  <rect width="1440" height="1040" fill="#f4ecd8"/>
  <g font-family="Helvetica,Arial,sans-serif" fill="${ink}">
    <text x="72" y="68" font-size="17" letter-spacing="3">XFOLD / BRAND ASSETS</text>
    <text x="1368" y="68" text-anchor="end" font-size="15">HackSpain ’26</text>
    <path d="M72 96H1368" stroke="#d3c5ae"/>
    <g transform="translate(284 146) scale(2.7)">${mark(ink, orange)}<g transform="translate(112 29)">${lettering(ink)}</g></g>
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
