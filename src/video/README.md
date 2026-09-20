# XFOLD intro — Remotion

VC pitch (~70 s, Spanish): measured problem, economic impact, why folding is still human, XFOLD + stack, market, team.

## Preview

```bash
cd src/video
npm install
npm run dev
```

Or from the repo root: `moon run video:dev`.

Studio opens at http://localhost:3333. Composition: `XFoldIntro`.

## Render

```bash
npx remotion render XFoldIntro
```

Output goes to `src/video/out/`.

## Assets

Put source media in `public/`:

| File | Source |
|---|---|
| `roommate.svg` / `logo.svg` | Desktop `logo.svg` (Room Mate Hotels, white) |
| `roommate-ink.svg` | Same mark, ink fill for cream scenes |
| `xfold-logo-*.svg` | Brand wordmark from `src/dashboard/public/brand` |
| `warehouse-chaos.jpeg` / `closet.jpeg` / `floor-pile.jpeg` / `parcels.jpeg` | `Downloads/remotion` stills |
| `model.jpg` | product still |
| `bags.mp4` | process clip |
| `warehouse.mp4` | long plant clip (~38 MB, gitignored via root `*.mp4`) |

Copy `warehouse.mp4` from `Downloads/remotion/098765432345678.mp4` if Studio says the file is missing.

The folding shirt is the dashboard loader (`xfold-motion.mjs`), driven by `useCurrentFrame()` — no CSS animation.
