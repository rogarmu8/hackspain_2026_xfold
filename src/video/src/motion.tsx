import type { CSSProperties, ReactNode } from "react";
import { Easing, interpolate, useCurrentFrame } from "remotion";
import { colors } from "./theme";

export const snap = Easing.bezier(0.34, 1.56, 0.64, 1);

export const useStagger = (index: number, gap = 12, dur = 10) => {
  const frame = useCurrentFrame();
  return interpolate(frame, [index * gap, index * gap + dur], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: snap,
  });
};

/** Shirt fold: panel opens from the left hinge. */
export const useFoldIn = (start = 0, dur = 16) => {
  const frame = useCurrentFrame();
  const t = interpolate(frame, [start, start + dur], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: snap,
  });
  return {
    opacity: t,
    transform: `perspective(1100px) rotateY(${interpolate(t, [0, 1], [82, 0])}deg)`,
    transformOrigin: "left center",
  } satisfies CSSProperties;
};

/** Hem fold: panel lifts from the bottom. */
export const useHemIn = (start = 0, dur = 16) => {
  const frame = useCurrentFrame();
  const t = interpolate(frame, [start, start + dur], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: snap,
  });
  return {
    opacity: t,
    transform: `perspective(1100px) rotateX(${interpolate(t, [0, 1], [68, 0])}deg)`,
    transformOrigin: "center bottom",
  } satisfies CSSProperties;
};

/** Conveyor / train car: arrives from the left, coupled by index. */
export const useBeltIn = (index: number, gap = 16, dur = 14, from = -88) => {
  const t = useStagger(index, gap, dur);
  return {
    opacity: t,
    transform: `translateX(${interpolate(t, [0, 1], [from, 0])}px)`,
  } satisfies CSSProperties;
};

export const useFloat = (delay: number, amp = 7) => {
  const frame = useCurrentFrame();
  const t = Math.max(0, frame - delay);
  return Math.sin(t / 16) * amp;
};

type BeltRailProps = {
  color?: string;
  padTop?: number;
};

/** Rolling conveyor under a row of cars. */
export const BeltRail: React.FC<BeltRailProps> = ({
  color = colors.orange,
  padTop = 32,
}) => {
  const frame = useCurrentFrame();
  const shift = (frame * 6) % 32;
  const roller: CSSProperties = {
    width: 16,
    height: 16,
    borderRadius: "50%",
    border: `3px solid ${color}`,
    flexShrink: 0,
  };

  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        width: "100%",
        gap: 12,
        marginTop: padTop,
      }}
    >
      <div style={roller} />
      <div
        style={{
          flex: 1,
          height: 14,
          overflow: "hidden",
          position: "relative",
        }}
      >
        <div
          style={{
            position: "absolute",
            left: -shift,
            right: -32,
            top: 5,
            borderTop: `3px dashed ${color}`,
          }}
        />
      </div>
      <div style={roller} />
    </div>
  );
};

export const FoldIn: React.FC<{
  delay?: number;
  children: ReactNode;
  style?: CSSProperties;
}> = ({ delay = 0, children, style }) => {
  const fold = useFoldIn(delay, 16);
  return <div style={{ ...fold, ...style }}>{children}</div>;
};
