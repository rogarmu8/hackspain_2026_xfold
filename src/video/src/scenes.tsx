import { Fragment } from "react";
import { Video } from "@remotion/media";
import {
  AbsoluteFill,
  Easing,
  Img,
  interpolate,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { FoldLoader } from "./FoldLoader";
import {
  IconBox,
  IconCart,
  IconChevron,
  IconClock,
  IconCoin,
  IconFactory,
  IconFold,
  IconHotel,
  IconIron,
  IconPeople,
  IconPlace,
  IconShirt,
  IconTag,
} from "./icons";
import { colors, fonts } from "./theme";

const snap = Easing.bezier(0.34, 1.56, 0.64, 1);

const useEnter = (holdFrames = 10) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const enter = interpolate(frame, [0, holdFrames], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: snap,
  });
  const leave = interpolate(
    frame,
    [durationInFrames - 8, durationInFrames],
    [0, 1],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );
  return {
    opacity: enter * (1 - leave),
    rise: interpolate(enter, [0, 1], [28, 0]),
  };
};

const useStagger = (index: number, gap = 12, dur = 10) => {
  const frame = useCurrentFrame();
  return interpolate(frame, [index * gap, index * gap + dur], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: snap,
  });
};

const useFloat = (delay: number, amp = 7) => {
  const frame = useCurrentFrame();
  const t = Math.max(0, frame - delay);
  return Math.sin(t / 16) * amp;
};

const useCount = (to: number, start: number, dur: number) => {
  const frame = useCurrentFrame();
  return interpolate(frame, [start, start + dur], [0, to], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: Easing.out(Easing.cubic),
  });
};

const kickerStyle: React.CSSProperties = {
  fontFamily: fonts.mono,
  fontSize: 20,
  letterSpacing: "0.16em",
  textTransform: "uppercase",
  color: colors.orange,
};

const titleStyle: React.CSSProperties = {
  fontFamily: fonts.sans,
  fontWeight: 600,
  color: colors.ink,
};

export const HookScene: React.FC = () => {
  const { opacity, rise } = useEnter(8);
  const line = useStagger(1, 14, 10);
  return (
    <AbsoluteFill
      style={{
        backgroundColor: colors.ink,
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <div
        style={{
          opacity,
          transform: `translateY(${rise}px)`,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 36,
        }}
      >
        <Img
          src={staticFile("xfold-logo-reverse.svg")}
          style={{ width: 480, height: "auto" }}
        />
        <div
          style={{
            ...kickerStyle,
            color: colors.cream,
            fontSize: 42,
            letterSpacing: "0.04em",
            textTransform: "none",
            fontFamily: fonts.sans,
            fontWeight: 600,
            opacity: line,
            textAlign: "center",
          }}
        >
          Una camiseta más.
        </div>
      </div>
    </AbsoluteFill>
  );
};

type PhotoSceneProps = {
  src: string;
  kicker: string;
  title: string;
  objectPosition?: string;
};

export const PhotoScene: React.FC<PhotoSceneProps> = ({
  src,
  kicker,
  title,
  objectPosition = "50% 50%",
}) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const zoom = interpolate(frame, [0, durationInFrames], [1.06, 1.18], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const copy = interpolate(frame, [4, 14], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: snap,
  });

  return (
    <AbsoluteFill style={{ backgroundColor: colors.ink }}>
      <Img
        src={staticFile(src)}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          objectPosition,
          transform: `scale(${zoom})`,
        }}
      />
      <AbsoluteFill
        style={{
          background:
            "linear-gradient(180deg, rgba(42,23,15,0.08) 35%, rgba(42,23,15,0.86) 100%)",
        }}
      />
      <div
        style={{
          position: "absolute",
          left: 80,
          right: 80,
          bottom: 64,
          opacity: copy,
        }}
      >
        <div style={{ ...kickerStyle, marginBottom: 12 }}>{kicker}</div>
        <div
          style={{
            ...titleStyle,
            color: colors.cream,
            fontSize: 64,
            lineHeight: 1.06,
            maxWidth: 1200,
          }}
        >
          {title}
        </div>
      </div>
    </AbsoluteFill>
  );
};

type FootageSceneProps = {
  src: string;
  kicker: string;
  title: string;
  subtitle?: string;
  playbackRate?: number;
};

export const FootageScene: React.FC<FootageSceneProps> = ({
  src,
  kicker,
  title,
  subtitle,
  playbackRate = 1,
}) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const zoom = interpolate(frame, [0, durationInFrames], [1.02, 1.12], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const kickerIn = interpolate(frame, [10, 24], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: snap,
  });
  const titleIn = interpolate(frame, [28, 48], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: snap,
  });
  const subIn = interpolate(frame, [62, 88], [0, 1], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
    easing: snap,
  });

  return (
    <AbsoluteFill style={{ backgroundColor: colors.ink }}>
      <Video
        src={staticFile(src)}
        muted
        loop
        playbackRate={playbackRate}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          transform: `scale(${zoom})`,
        }}
      />
      <AbsoluteFill
        style={{
          background:
            "linear-gradient(180deg, rgba(42,23,15,0.05) 40%, rgba(42,23,15,0.88) 100%)",
        }}
      />
      <div
        style={{
          position: "absolute",
          left: 80,
          right: 80,
          bottom: 72,
        }}
      >
        <div
          style={{
            ...kickerStyle,
            marginBottom: 16,
            opacity: kickerIn,
            transform: `translateY(${interpolate(kickerIn, [0, 1], [16, 0])}px)`,
          }}
        >
          {kicker}
        </div>
        <div
          style={{
            ...titleStyle,
            color: colors.cream,
            fontSize: 52,
            lineHeight: 1.1,
            maxWidth: 1400,
            opacity: titleIn,
            transform: `translateY(${interpolate(titleIn, [0, 1], [20, 0])}px)`,
          }}
        >
          {title}
        </div>
        {subtitle ? (
          <div
            style={{
              display: "flex",
              alignItems: "center",
              gap: 22,
              marginTop: 18,
              opacity: subIn,
              transform: `translateY(${interpolate(subIn, [0, 1], [20, 0])}px)`,
            }}
          >
            <IconPeople size={56} color={colors.orange} />
            <div
              style={{
                ...titleStyle,
                color: colors.cream,
                fontSize: 40,
                lineHeight: 1.15,
                maxWidth: 1320,
              }}
            >
              {subtitle}
            </div>
          </div>
        ) : null}
      </div>
    </AbsoluteFill>
  );
};

const STATS = [
  { to: 15, suffix: "", label: "personas", Icon: IconPeople },
  { to: 1.5, suffix: " h", label: "juntas", Icon: IconClock, decimals: 1 },
  { to: 250, suffix: "", label: "camisetas", Icon: IconShirt },
];

export const StatScene: React.FC<{ kicker: string }> = ({ kicker }) => {
  const { opacity } = useEnter(12);
  return (
    <AbsoluteFill
      style={{
        backgroundColor: colors.cream,
        padding: "90px 100px",
        justifyContent: "center",
      }}
    >
      <div style={{ opacity, width: "100%" }}>
        <div style={{ ...kickerStyle, marginBottom: 56 }}>{kicker}</div>
        <div
          style={{
            display: "flex",
            flexDirection: "row",
            width: "100%",
            gap: 40,
          }}
        >
          {STATS.map((stat, i) => {
            const start = 12 + i * 20;
            const beat = useStagger(i, 20, 14);
            const raw = useCount(stat.to, start, 42);
            const shown = stat.decimals
              ? raw.toFixed(1).replace(".", ",")
              : String(Math.round(raw));
            const float = useFloat(start + 20);
            return (
              <div
                key={stat.label}
                style={{
                  flex: "1 1 0",
                  minWidth: 0,
                  textAlign: "center",
                  opacity: beat,
                  transform: `translateY(${interpolate(beat, [0, 1], [40, 0])}px) scale(${interpolate(beat, [0, 1], [0.8, 1])})`,
                }}
              >
                <div style={{ transform: `translateY(${float}px)` }}>
                  <stat.Icon size={88} />
                </div>
                <div
                  style={{
                    ...titleStyle,
                    fontSize: 88,
                    lineHeight: 1,
                    marginTop: 22,
                    marginBottom: 12,
                  }}
                >
                  {shown}
                  {stat.suffix}
                </div>
                <div style={{ ...kickerStyle, color: colors.ink }}>{stat.label}</div>
              </div>
            );
          })}
        </div>
      </div>
    </AbsoluteFill>
  );
};

export const ImpactScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const zoom = interpolate(frame, [0, durationInFrames], [1.04, 1.12], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });
  const lines = [
    {
      value: "~1,80 €",
      label: "a mano",
      Icon: IconCoin,
      src: "floor-pile.jpeg",
      position: "50% 40%",
    },
    {
      value: "Miles €",
      label: "al día",
      Icon: IconBox,
      src: "parcels.jpeg",
      position: "60% 40%",
    },
  ];

  return (
    <AbsoluteFill style={{ backgroundColor: colors.ink }}>
      <div
        style={{
          display: "flex",
          flexDirection: "row",
          width: "100%",
          height: "100%",
        }}
      >
        {lines.map((line, i) => {
          const beat = useStagger(i, 22, 16);
          const float = useFloat(20 + i * 22, 5);
          const LineIcon = line.Icon;
          return (
            <div
              key={line.src}
              style={{
                width: "50%",
                height: "100%",
                overflow: "hidden",
                position: "relative",
              }}
            >
              <Img
                src={staticFile(line.src)}
                style={{
                  width: "100%",
                  height: "100%",
                  maxWidth: "none",
                  objectFit: "cover",
                  objectPosition: line.position,
                  transform: `scale(${zoom})`,
                }}
              />
              <div
                style={{
                  position: "absolute",
                  left: 0,
                  right: 0,
                  bottom: 0,
                  height: 280,
                  background:
                    "linear-gradient(180deg, rgba(42,23,15,0) 0%, rgba(42,23,15,0.88) 70%)",
                }}
              />
              <div
                style={{
                  position: "absolute",
                  left: 48,
                  right: 48,
                  bottom: 56,
                  opacity: beat,
                  transform: `translateY(${interpolate(beat, [0, 1], [24, 0])}px)`,
                }}
              >
                <div style={{ transform: `translateY(${float}px)` }}>
                  <LineIcon size={60} color={colors.orange} />
                </div>
                <div
                  style={{
                    ...titleStyle,
                    color: colors.cream,
                    fontSize: 56,
                    lineHeight: 1,
                    marginTop: 14,
                    marginBottom: 10,
                    whiteSpace: "nowrap",
                  }}
                >
                  {line.value}
                </div>
                <div
                  style={{
                    fontFamily: fonts.sans,
                    fontSize: 24,
                    color: colors.cream,
                    opacity: 0.8,
                  }}
                >
                  {line.label}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

export const FoldScene: React.FC = () => {
  const { opacity, rise } = useEnter(8);
  return (
    <AbsoluteFill
      style={{
        backgroundColor: colors.cream,
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <div
        style={{
          display: "flex",
          flexDirection: "row",
          alignItems: "center",
          width: "100%",
          padding: "0 90px",
          gap: 72,
        }}
      >
      <div style={{ opacity, transform: `translateY(${rise}px)` }}>
        <FoldLoader size={420} startMs={350} />
      </div>
      <div
        style={{
          opacity,
          transform: `translateY(${rise}px)`,
          maxWidth: 860,
        }}
      >
        <div style={{ ...kickerStyle, marginBottom: 18 }}>Dobla y empaqueta</div>
        <div
          style={{
            ...titleStyle,
            fontSize: 64,
            lineHeight: 1.08,
            marginBottom: 22,
          }}
        >
          Sin nadie en la mesa.
        </div>
      </div>
      </div>
    </AbsoluteFill>
  );
};

const LINE = [
  { title: "Colocar", Icon: IconPlace },
  { title: "Planchar", Icon: IconIron },
  { title: "Doblar", Icon: IconFold },
  { title: "Empaquetar", Icon: IconBox },
];

export const StackScene: React.FC = () => {
  const { opacity } = useEnter(10);
  return (
    <AbsoluteFill
      style={{
        backgroundColor: colors.cream,
        padding: "90px 100px",
        justifyContent: "center",
      }}
    >
      <div style={{ opacity, width: "100%" }}>
        <div style={{ ...kickerStyle, marginBottom: 56 }}>Cómo lo hacemos</div>
        <div
          style={{
            display: "flex",
            flexDirection: "row",
            alignItems: "flex-start",
            width: "100%",
            gap: 12,
          }}
        >
          {LINE.map((step, i) => {
            const beat = useStagger(i, 22, 14);
            const arrow = interpolate(
              useCurrentFrame(),
              [i * 22 + 14, i * 22 + 28],
              [0, 1],
              { extrapolateLeft: "clamp", extrapolateRight: "clamp", easing: snap },
            );
            const float = useFloat(18 + i * 22, 6);
            const StepIcon = step.Icon;
            return (
              <Fragment key={step.title}>
                <div
                  style={{
                    flex: "1 1 0",
                    minWidth: 0,
                    textAlign: "center",
                    opacity: beat,
                    transform: `translateY(${interpolate(beat, [0, 1], [36, 0])}px) scale(${interpolate(beat, [0, 1], [0.78, 1])})`,
                  }}
                >
                  <div style={{ transform: `translateY(${float}px)` }}>
                    <StepIcon size={96} />
                  </div>
                  <div
                    style={{
                      ...titleStyle,
                      fontSize: 30,
                      marginTop: 24,
                    }}
                  >
                    {step.title}
                  </div>
                </div>
                {i < LINE.length - 1 ? (
                  <div
                    style={{
                      opacity: arrow,
                      transform: `translateX(${interpolate(arrow, [0, 1], [-14, 0])}px)`,
                      flexShrink: 0,
                      marginTop: 26,
                    }}
                  >
                    <IconChevron size={48} />
                  </div>
                ) : null}
              </Fragment>
            );
          })}
        </div>
      </div>
    </AbsoluteFill>
  );
};

const MARKETS = [
  { title: "Hoteles", Icon: IconHotel },
  { title: "Tiendas online", Icon: IconCart },
  { title: "Grandes Marcas", Icon: IconTag },
  { title: "Fábricas", Icon: IconFactory },
];

export const MarketScene: React.FC = () => {
  const { opacity } = useEnter(10);
  return (
    <AbsoluteFill
      style={{
        backgroundColor: colors.ink,
        padding: "80px 90px",
        justifyContent: "center",
      }}
    >
      <div style={{ opacity, width: "100%" }}>
        <div style={{ ...kickerStyle, marginBottom: 56 }}>Para quién</div>
        <div style={{ display: "flex", gap: 24, width: "100%" }}>
          {MARKETS.map((market, i) => {
            const beat = useStagger(i, 20, 14);
            const float = useFloat(16 + i * 20, 7);
            return (
              <div
                key={market.title}
                style={{
                  flex: "1 1 0",
                  minWidth: 0,
                  textAlign: "center",
                  opacity: beat,
                  transform: `translateY(${interpolate(beat, [0, 1], [32, 0])}px) scale(${interpolate(beat, [0, 1], [0.8, 1])})`,
                }}
              >
                <div style={{ transform: `translateY(${float}px)` }}>
                  <market.Icon size={88} color={colors.orange} />
                </div>
                <div
                  style={{
                    ...titleStyle,
                    color: colors.cream,
                    fontSize: 28,
                    lineHeight: 1.15,
                    marginTop: 22,
                  }}
                >
                  {market.title}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </AbsoluteFill>
  );
};

const TEAM = [
  { name: "JD" },
  { name: "Alex Sánchez" },
  { name: "Rómulo García" },
  { name: "Miguel García" },
];

export const TeamScene: React.FC = () => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const zoom = interpolate(frame, [0, durationInFrames], [1.02, 1.08], {
    extrapolateLeft: "clamp",
    extrapolateRight: "clamp",
  });

  return (
    <AbsoluteFill style={{ backgroundColor: colors.ink }}>
      <Img
        src={staticFile("team.jpeg")}
        style={{
          width: "100%",
          height: "100%",
          objectFit: "cover",
          objectPosition: "50% 28%",
          transform: `scale(${zoom})`,
        }}
      />
      <AbsoluteFill
        style={{
          background:
            "linear-gradient(180deg, rgba(42,23,15,0.05) 45%, rgba(42,23,15,0.88) 100%)",
        }}
      />
      <div
        style={{
          position: "absolute",
          left: 64,
          right: 64,
          bottom: 56,
          display: "flex",
          gap: 20,
        }}
      >
        {TEAM.map((person, i) => {
          const beat = useStagger(i, 16, 14);
          return (
            <div
              key={person.name}
              style={{
                flex: 1,
                opacity: beat,
                transform: `translateY(${interpolate(beat, [0, 1], [18, 0])}px)`,
                backgroundColor: colors.cream,
                padding: "18px 22px",
              }}
            >
              <div
                style={{
                  ...titleStyle,
                  fontSize: 28,
                  marginBottom: 6,
                }}
              >
                {person.name}
              </div>
              <div style={{ ...kickerStyle, fontSize: 13, color: colors.ink }}>
                XFOLD · HackSpain '26
              </div>
            </div>
          );
        })}
      </div>
    </AbsoluteFill>
  );
};

export const EndCard: React.FC = () => {
  const { opacity, rise } = useEnter(10);
  return (
    <AbsoluteFill
      style={{
        backgroundColor: colors.cream,
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <div
        style={{
          opacity,
          transform: `translateY(${rise}px)`,
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 28,
        }}
      >
        <Img
          src={staticFile("xfold-logo-ink.svg")}
          style={{ width: 520, height: "auto" }}
        />
        <div style={{ ...titleStyle, fontSize: 42 }}>Sin nadie en la mesa.</div>
        <div style={kickerStyle}>THEKER × XFOLD · HackSpain '26</div>
      </div>
    </AbsoluteFill>
  );
};
