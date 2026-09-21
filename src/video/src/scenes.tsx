import { Fragment } from "react";
import { Video } from "@remotion/media";
import {
  AbsoluteFill,
  Easing,
  Freeze,
  Img,
  interpolate,
  Loop,
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
import {
  BeltRail,
  snap,
  useBeltIn,
  useFloat,
  useFoldIn,
  useHemIn,
} from "./motion";
import { colors, fonts, FPS } from "./theme";

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

type HookBeat = { text: string; enter: number; hold: number; travel: number };

const HOOK_BEATS: HookBeat[] = (() => {
  const first: HookBeat = {
    text: "Una camiseta más.",
    enter: 12,
    hold: 26,
    travel: 10,
  };
  const otras: HookBeat[] = Array.from({ length: 12 }, (_, i) => ({
    text: "y otra",
    enter: Math.max(2, Math.round(11 * Math.pow(0.66, i))),
    hold: Math.max(1, Math.round(20 * Math.pow(0.58, i))),
    travel: Math.max(2, Math.round(10 * Math.pow(0.66, i))),
  }));
  return [first, ...otras];
})();

const HOOK_STARTS = (() => {
  const starts = [20];
  for (let i = 0; i < HOOK_BEATS.length - 1; i++) {
    const beat = HOOK_BEATS[i];
    starts.push(starts[i] + beat.enter + beat.hold + beat.travel);
  }
  return starts;
})();

const lastBeat = HOOK_BEATS[HOOK_BEATS.length - 1];
/** Cut while the last "y otra" is still sliding out — no hold at the end. */
export const HOOK_FRAMES =
  HOOK_STARTS[HOOK_STARTS.length - 1] +
  lastBeat.enter +
  lastBeat.hold +
  Math.max(1, Math.round(lastBeat.travel / 2));

const hookLineStyle = (frame: number, beat: HookBeat, start: number) => {
  const inEnd = start + beat.enter;
  const holdEnd = inEnd + beat.hold;
  const outEnd = holdEnd + beat.travel;
  const hidden = frame < start || frame >= outEnd;
  const incoming = !hidden && frame < inEnd;
  const outgoing = frame >= holdEnd && frame < outEnd;
  const t = incoming
    ? interpolate(frame, [start, inEnd], [0, 1], {
        extrapolateLeft: "clamp",
        extrapolateRight: "clamp",
        easing: beat.enter <= 3 ? Easing.linear : snap,
      })
    : outgoing
      ? interpolate(frame, [holdEnd, outEnd], [0, 1], {
          extrapolateLeft: "clamp",
          extrapolateRight: "clamp",
          easing: Easing.in(Easing.cubic),
        })
      : 1;
  const x = hidden
    ? frame < start
      ? -220
      : 220
    : incoming
      ? interpolate(t, [0, 1], [-220, 0])
      : outgoing
        ? interpolate(t, [0, 1], [0, 240])
        : 0;
  const opacity = hidden
    ? 0
    : incoming
      ? interpolate(t, [0, 1], [0, 1])
      : outgoing
        ? interpolate(t, [0, 0.7], [1, 0], {
            extrapolateRight: "clamp",
            easing: Easing.out(Easing.quad),
          })
        : 1;
  return { transform: `translateX(${x}px)`, opacity };
};

export const HookScene: React.FC = () => {
  const logo = useFoldIn(0, 18);
  const frame = useCurrentFrame();
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
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 28,
          width: 720,
        }}
      >
        <div style={logo}>
          <Img
            src={staticFile("xfold-logo-reverse.svg")}
            style={{ width: 480, height: "auto" }}
          />
        </div>
        <div
          style={{
            position: "relative",
            width: "100%",
            height: 56,
            overflow: "hidden",
            WebkitMaskImage:
              "linear-gradient(90deg, transparent, #000 14%, #000 86%, transparent)",
            maskImage:
              "linear-gradient(90deg, transparent, #000 14%, #000 86%, transparent)",
          }}
        >
          {HOOK_BEATS.map((beat, i) => (
            <div
              key={`${beat.text}-${i}`}
              style={{
                position: "absolute",
                left: 0,
                right: 0,
                top: 0,
                ...kickerStyle,
                color: colors.cream,
                fontSize: 42,
                letterSpacing: "0.04em",
                textTransform: "none",
                fontFamily: fonts.sans,
                fontWeight: 600,
                textAlign: "center",
                ...hookLineStyle(frame, beat, HOOK_STARTS[i]),
              }}
            >
              {beat.text}
            </div>
          ))}
        </div>
        <BeltRail padTop={8} />
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
  /** Play this many frames, then hold the last one. Do not loop. */
  playFrames?: number;
};

export const FootageScene: React.FC<FootageSceneProps> = ({
  src,
  kicker,
  title,
  subtitle,
  playbackRate = 1,
  playFrames = 75,
}) => {
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const freezeAt = Math.max(0, playFrames - 1);
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

  const footage = (
    <Video
      src={staticFile(src)}
      muted
      playbackRate={playbackRate}
      style={{
        width: "100%",
        height: "100%",
        objectFit: "cover",
        transform: `scale(${zoom})`,
      }}
    />
  );

  return (
    <AbsoluteFill style={{ backgroundColor: colors.ink }}>
      {frame < playFrames ? footage : <Freeze frame={freezeAt}>{footage}</Freeze>}
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
            transform: `translateX(${interpolate(kickerIn, [0, 1], [-64, 0])}px)`,
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
            transform: `perspective(1100px) rotateY(${interpolate(titleIn, [0, 1], [70, 0])}deg)`,
            transformOrigin: "left center",
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
              transform: `translateX(${interpolate(subIn, [0, 1], [-80, 0])}px)`,
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
  const kickerFold = useFoldIn(0, 12);
  return (
    <AbsoluteFill
      style={{
        backgroundColor: colors.cream,
        padding: "90px 100px",
        justifyContent: "center",
      }}
    >
      <div style={{ width: "100%" }}>
        <div style={{ ...kickerStyle, marginBottom: 48, ...kickerFold }}>{kicker}</div>
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
            const car = useBeltIn(i, 20, 14);
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
                  ...car,
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
        <BeltRail />
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
          const hem = useHemIn(8 + i * 18, 16);
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
                  ...hem,
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
  const copy = useFoldIn(10, 18);
  const line = useBeltIn(2, 16, 14, -56);
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
      <div>
        <FoldLoader size={420} startMs={350} />
      </div>
      <div style={{ maxWidth: 860, ...copy }}>
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
        <div style={line}>
          <BeltRail padTop={4} />
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
  const kickerFold = useFoldIn(0, 12);
  return (
    <AbsoluteFill
      style={{
        backgroundColor: colors.cream,
        padding: "90px 100px",
        justifyContent: "center",
      }}
    >
      <div style={{ width: "100%" }}>
        <div style={{ ...kickerStyle, marginBottom: 48, ...kickerFold }}>
          Cómo lo hacemos
        </div>
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
            const car = useBeltIn(i, 22, 14);
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
                    ...car,
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
        <BeltRail />
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
  const kickerFold = useFoldIn(0, 12);
  return (
    <AbsoluteFill
      style={{
        backgroundColor: colors.ink,
        padding: "80px 90px",
        justifyContent: "center",
      }}
    >
      <div style={{ width: "100%" }}>
        <div style={{ ...kickerStyle, marginBottom: 48, ...kickerFold }}>
          Para quién
        </div>
        <div style={{ display: "flex", gap: 24, width: "100%" }}>
          {MARKETS.map((market, i) => {
            const car = useBeltIn(i, 20, 14);
            const float = useFloat(16 + i * 20, 7);
            return (
              <div
                key={market.title}
                style={{
                  flex: "1 1 0",
                  minWidth: 0,
                  textAlign: "center",
                  ...car,
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
        <BeltRail />
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
          const car = useBeltIn(i, 16, 14, -70);
          return (
            <div
              key={person.name}
              style={{
                flex: 1,
                backgroundColor: colors.cream,
                padding: "18px 22px",
                ...car,
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

export const TalkScene: React.FC<{
  src: string;
  kicker?: string;
  name?: string;
  trimBefore?: number;
  trimAfter?: number;
  playbackRate?: number;
  lowerThird?: boolean;
  broll?: string;
  brollFrom?: number;
  brollTo?: number;
  brollLoop?: boolean;
}> = ({
  src,
  kicker,
  name,
  trimBefore,
  trimAfter,
  playbackRate = 1,
  lowerThird = true,
  broll,
  brollFrom,
  brollTo,
  brollLoop,
}) => {
  const bar = useFoldIn(3, 10);
  const line = useBeltIn(1, 8, 10, -40);
  const frame = useCurrentFrame();
  const { durationInFrames } = useVideoConfig();
  const fadeLen = 14;
  const fade = interpolate(
    frame,
    [0, fadeLen, Math.max(fadeLen, durationInFrames - fadeLen), durationInFrames],
    [0, 1, 1, 0],
    { extrapolateLeft: "clamp", extrapolateRight: "clamp" },
  );
  const talkTrim = {
    trimBefore: trimBefore === undefined ? undefined : Math.round(trimBefore * FPS),
    trimAfter: trimAfter === undefined ? undefined : Math.round(trimAfter * FPS),
  };
  const talkVideo = (
    <Video
      src={staticFile(src)}
      {...talkTrim}
      playbackRate={playbackRate}
      objectFit="cover"
      style={{
        width: "100%",
        height: "100%",
      }}
    />
  );
  const brollStart = brollFrom === undefined ? undefined : Math.round(brollFrom * FPS);
  const brollEnd = brollTo === undefined ? undefined : Math.round(brollTo * FPS);
  const brollSpan =
    brollStart !== undefined && brollEnd !== undefined
      ? Math.max(1, brollEnd - brollStart)
      : undefined;
  const brollVideo = broll ? (
    <Video
      src={staticFile(broll)}
      muted
      loop={Boolean(brollLoop && brollSpan === undefined)}
      trimBefore={brollStart}
      trimAfter={brollEnd}
      objectFit="contain"
      style={{
        width: "100%",
        height: "100%",
      }}
    />
  ) : null;
  return (
    <AbsoluteFill style={{ backgroundColor: colors.ink, opacity: fade }}>
      {brollVideo ? (
        brollLoop && brollSpan !== undefined ? (
          <Loop durationInFrames={brollSpan}>{brollVideo}</Loop>
        ) : (
          brollVideo
        )
      ) : (
        talkVideo
      )}
      <AbsoluteFill
        style={{
          background: lowerThird
            ? "linear-gradient(180deg, rgba(42,23,15,0) 62%, rgba(42,23,15,0.82) 100%)"
            : undefined,
        }}
      />
      {broll ? (
        <div
          style={{
            position: "absolute",
            right: 56,
            bottom: 168,
            width: 380,
            height: 214,
            overflow: "hidden",
            border: `3px solid ${colors.cream}`,
          }}
        >
          {talkVideo}
        </div>
      ) : null}
      {lowerThird && name ? (
        <div
          style={{
            position: "absolute",
            left: 72,
            right: 72,
            bottom: 56,
            ...bar,
          }}
        >
          {kicker ? (
            <div style={{ ...kickerStyle, marginBottom: 12 }}>{kicker}</div>
          ) : null}
          <div
            style={{
              ...titleStyle,
              color: colors.cream,
              fontSize: 52,
              lineHeight: 1.05,
              ...line,
            }}
          >
            {name}
          </div>
          <BeltRail padTop={18} />
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

export const DemoScene: React.FC<{
  src: string;
  kicker?: string;
  title?: string;
  playbackRate?: number;
}> = ({ src, kicker, title, playbackRate = 1 }) => {
  const copy = useFoldIn(8, 14);
  return (
    <AbsoluteFill style={{ backgroundColor: colors.ink }}>
      <Video
        src={staticFile(src)}
        muted
        playbackRate={playbackRate}
        objectFit="contain"
        style={{
          width: "100%",
          height: "100%",
        }}
      />
      {kicker || title ? (
        <div
          style={{
            position: "absolute",
            left: 72,
            bottom: 40,
            ...copy,
          }}
        >
          {kicker ? <div style={{ ...kickerStyle, marginBottom: 8 }}>{kicker}</div> : null}
          {title ? (
            <div style={{ ...titleStyle, color: colors.cream, fontSize: 36 }}>{title}</div>
          ) : null}
        </div>
      ) : null}
    </AbsoluteFill>
  );
};

/** Reserved 90 s hole for the product demo clip. */
export const PRODUCT_SECONDS = 90;
export const PRODUCT_FRAMES = PRODUCT_SECONDS * FPS;

export const ProductSlot: React.FC = () => {
  const copy = useFoldIn(8, 16);
  const line = useBeltIn(2, 14, 14, -48);
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
        <FoldLoader size={420} startMs={350} />
        <div style={{ maxWidth: 860, ...copy }}>
          <div style={{ ...kickerStyle, marginBottom: 18 }}>La línea</div>
          <div
            style={{
              ...titleStyle,
              fontSize: 64,
              lineHeight: 1.08,
              marginBottom: 18,
            }}
          >
            Aquí entra el producto.
          </div>
          <div
            style={{
              fontFamily: fonts.sans,
              fontSize: 28,
              color: colors.ink,
              opacity: 0.7,
              ...line,
            }}
          >
            Hueco de 1:30 para el vídeo de la máquina.
          </div>
          <BeltRail padTop={22} />
        </div>
      </div>
    </AbsoluteFill>
  );
};

export const EndCard: React.FC = () => {
  const logo = useFoldIn(0, 18);
  const slogan = useBeltIn(1, 16, 14, -64);
  const credit = useBeltIn(2, 16, 14, -48);
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
          flexDirection: "column",
          alignItems: "center",
          gap: 24,
          width: 720,
        }}
      >
        <div style={logo}>
          <Img
            src={staticFile("xfold-logo-ink.svg")}
            style={{ width: 520, height: "auto" }}
          />
        </div>
        <div style={{ ...titleStyle, fontSize: 42, ...slogan }}>
          Sin nadie en la mesa.
        </div>
        <div style={{ ...kickerStyle, ...credit }}>
          THEKER × XFOLD · HackSpain '26
        </div>
        <BeltRail padTop={4} />
      </div>
    </AbsoluteFill>
  );
};
