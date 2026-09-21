import { linearTiming, TransitionSeries } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { wipe } from "@remotion/transitions/wipe";
import { AbsoluteFill } from "remotion";
import {
  DemoScene,
  EndCard,
  FoldScene,
  FootageScene,
  HOOK_FRAMES,
  HookScene,
  StackScene,
  StatScene,
  TalkScene,
  TeamScene,
} from "./scenes";
import { colors, fade as fadeFrames, FPS } from "./theme";

const beat = linearTiming({ durationInFrames: fadeFrames });
const sec = (seconds: number) => Math.round(seconds * FPS);

export const DEMO_FULL_SECONDS = 51.817;
export const DEMO_RATE = 2;
export const TALK_RATE = 1.1;

/** JD explaining the solution, immediately before the full line clip. */
export const SOLUTION_TALK = {
  src: "talk-6.mp4",
  from: 2.55,
  seconds: 10.35,
  kicker: "La solución",
  name: "JD",
} as const;

/**
 * One take per person. `from` is a breath before the first word,
 * `seconds` is source duration through the last word plus a silent tail
 * so the fade is not mid-sentence. Played at TALK_RATE.
 */
export const TALK_CLIPS = [
  {
    src: "talk-1.mp4",
    from: 3.8,
    seconds: 36.95,
    kicker: "El problema",
    name: "Alex Sánchez",
    broll: "demo-reject.mp4",
    brollFrom: 8,
    brollTo: 15,
    brollLoop: true,
  },
  {
    src: "talk-2.mp4",
    from: 1.4,
    seconds: 44.3,
    kicker: "La idea",
    name: "JD",
    broll: "demo-launch.mp4",
    brollLoop: true,
  },
  {
    src: "talk-4.mp4",
    from: 0.8,
    seconds: 21.45,
    kicker: "HackSpain",
    name: "Rómulo García",
    broll: "demo-full.mp4",
    brollFrom: 34,
    brollTo: 50.5,
    brollLoop: true,
  },
  {
    src: "talk-5.mp4",
    from: 3.15,
    seconds: 27.6,
    kicker: "El equipo",
    name: "Miguel García",
    broll: "demo-graphs.mp4",
    brollLoop: true,
  },
] as const;

export const SCENE_FRAMES = {
  hook: HOOK_FRAMES,
  proof: 90,
  problem: 150,
  solutionTalk: sec(SOLUTION_TALK.seconds / TALK_RATE),
  demo: sec(DEMO_FULL_SECONDS / DEMO_RATE),
  talk: TALK_CLIPS.map((clip) => sec(clip.seconds / TALK_RATE)),
  stack: 150,
  solution: 90,
  team: 90,
  close: 90,
} as const;

const sceneSum =
  SCENE_FRAMES.hook +
  SCENE_FRAMES.proof +
  SCENE_FRAMES.problem +
  SCENE_FRAMES.solutionTalk +
  SCENE_FRAMES.demo +
  SCENE_FRAMES.talk.reduce((a, b) => a + b, 0) +
  SCENE_FRAMES.stack +
  SCENE_FRAMES.solution +
  SCENE_FRAMES.team +
  SCENE_FRAMES.close;

const TRANSITIONS = 9;

export const INTRO_DURATION = sceneSum - fadeFrames * TRANSITIONS;

const TalkTake: React.FC<{ i: number }> = ({ i }) => {
  const clip = TALK_CLIPS[i];
  return (
    <TalkScene
      src={clip.src}
      kicker={clip.kicker}
      name={clip.name}
      lowerThird
      trimBefore={clip.from}
      trimAfter={clip.from + clip.seconds}
      playbackRate={TALK_RATE}
      broll={clip.broll}
      brollFrom={"brollFrom" in clip ? clip.brollFrom : undefined}
      brollTo={"brollTo" in clip ? clip.brollTo : undefined}
      brollLoop={"brollLoop" in clip ? clip.brollLoop : undefined}
    />
  );
};

export const XFoldIntro: React.FC = () => {
  return (
    <AbsoluteFill style={{ backgroundColor: colors.ink }}>
      <TransitionSeries>
        <TransitionSeries.Sequence durationInFrames={SCENE_FRAMES.hook}>
          <HookScene />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition presentation={fade()} timing={beat} />
        <TransitionSeries.Sequence durationInFrames={SCENE_FRAMES.proof}>
          <FootageScene
            src="videoexpbolsas.mp4"
            kicker="HackSpain"
            title="Así se doblaba a mano."
          />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition
          presentation={wipe({ direction: "from-right" })}
          timing={beat}
        />
        <TransitionSeries.Sequence durationInFrames={SCENE_FRAMES.problem}>
          <StatScene kicker="A mano" />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition presentation={fade()} timing={beat} />
        <TransitionSeries.Sequence durationInFrames={SCENE_FRAMES.solutionTalk}>
          <TalkScene
            src={SOLUTION_TALK.src}
            kicker={SOLUTION_TALK.kicker}
            name={SOLUTION_TALK.name}
            lowerThird
            trimBefore={SOLUTION_TALK.from}
            trimAfter={SOLUTION_TALK.from + SOLUTION_TALK.seconds}
            playbackRate={TALK_RATE}
          />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition presentation={fade()} timing={beat} />
        <TransitionSeries.Sequence durationInFrames={SCENE_FRAMES.demo}>
          <DemoScene
            src="demo-full.mp4"
            kicker="La línea"
            title="Un ciclo completo."
            playbackRate={DEMO_RATE}
          />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition presentation={fade()} timing={beat} />
        <TransitionSeries.Sequence durationInFrames={SCENE_FRAMES.talk[0]}>
          <TalkTake i={0} />
        </TransitionSeries.Sequence>
        <TransitionSeries.Sequence durationInFrames={SCENE_FRAMES.talk[1]}>
          <TalkTake i={1} />
        </TransitionSeries.Sequence>
        <TransitionSeries.Sequence durationInFrames={SCENE_FRAMES.talk[2]}>
          <TalkTake i={2} />
        </TransitionSeries.Sequence>
        <TransitionSeries.Sequence durationInFrames={SCENE_FRAMES.talk[3]}>
          <TalkTake i={3} />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition presentation={fade()} timing={beat} />
        <TransitionSeries.Sequence durationInFrames={SCENE_FRAMES.stack}>
          <StackScene />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition presentation={fade()} timing={beat} />
        <TransitionSeries.Sequence durationInFrames={SCENE_FRAMES.solution}>
          <FoldScene />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition
          presentation={wipe({ direction: "from-right" })}
          timing={beat}
        />
        <TransitionSeries.Sequence durationInFrames={SCENE_FRAMES.team}>
          <TeamScene />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition presentation={fade()} timing={beat} />
        <TransitionSeries.Sequence durationInFrames={SCENE_FRAMES.close}>
          <EndCard />
        </TransitionSeries.Sequence>
      </TransitionSeries>
    </AbsoluteFill>
  );
};
