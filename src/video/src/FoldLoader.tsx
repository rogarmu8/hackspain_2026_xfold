import { Img, useCurrentFrame, useVideoConfig } from "remotion";
import { colors } from "./theme";
import { renderXFoldFrame, XFOLD_CYCLE_MS } from "./xfold-motion.mjs";

type FoldLoaderProps = {
  size?: number;
  startMs?: number;
};

const paint = (ms: number) =>
  renderXFoldFrame(ms)
    .replace(/var\(--stage-paper\)/g, colors.cream)
    .replace(/var\(--stage-ink\)/g, colors.ink)
    .replace(/var\(--stage-fold\)/g, colors.orange)
    .replace(/var\(--stage-reverse\)/g, colors.reverse)
    .replace(/var\(--stage-sleeve\)/g, colors.sleeve);

export const FoldLoader: React.FC<FoldLoaderProps> = ({
  size = 520,
  startMs = 350,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const ms = (startMs + (frame / fps) * 1000) % XFOLD_CYCLE_MS;
  const height = (size * 148) / 120;
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${size}" height="${height}" viewBox="0 0 120 148">${paint(ms)}</svg>`;

  return (
    <Img
      src={`data:image/svg+xml;utf8,${encodeURIComponent(svg)}`}
      width={size}
      height={height}
    />
  );
};
