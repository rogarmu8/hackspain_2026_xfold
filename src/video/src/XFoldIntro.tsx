import { linearTiming, TransitionSeries } from "@remotion/transitions";
import { fade } from "@remotion/transitions/fade";
import { wipe } from "@remotion/transitions/wipe";
import { AbsoluteFill } from "remotion";
import {
  EndCard,
  FoldScene,
  FootageScene,
  HookScene,
  ImpactScene,
  MarketScene,
  StackScene,
  StatScene,
  TeamScene,
} from "./scenes";
import { colors, fade as fadeFrames } from "./theme";

const beat = linearTiming({ durationInFrames: fadeFrames });

export const SCENE_FRAMES = {
  hook: 120,
  proof: 330,
  problem: 240,
  impact: 270,
  solution: 240,
  stack: 270,
  market: 240,
  team: 270,
  close: 184,
} as const;

const sceneCount = Object.keys(SCENE_FRAMES).length;
const sceneSum = Object.values(SCENE_FRAMES).reduce((a, b) => a + b, 0);

export const INTRO_DURATION = sceneSum - fadeFrames * (sceneCount - 1);

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
            title="En HackSpain nos dimos cuenta"
            subtitle="que se necesitaron 15 personas para doblar 250 camisetas."
          />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition
          presentation={wipe({ direction: "from-right" })}
          timing={beat}
        />
        <TransitionSeries.Sequence durationInFrames={SCENE_FRAMES.problem}>
          <StatScene kicker="A mano" />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition
          presentation={wipe({ direction: "from-left" })}
          timing={beat}
        />
        <TransitionSeries.Sequence durationInFrames={SCENE_FRAMES.impact}>
          <ImpactScene />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition presentation={fade()} timing={beat} />
        <TransitionSeries.Sequence durationInFrames={SCENE_FRAMES.solution}>
          <FoldScene />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition presentation={fade()} timing={beat} />
        <TransitionSeries.Sequence durationInFrames={SCENE_FRAMES.stack}>
          <StackScene />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition
          presentation={wipe({ direction: "from-right" })}
          timing={beat}
        />
        <TransitionSeries.Sequence durationInFrames={SCENE_FRAMES.market}>
          <MarketScene />
        </TransitionSeries.Sequence>
        <TransitionSeries.Transition presentation={fade()} timing={beat} />
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
