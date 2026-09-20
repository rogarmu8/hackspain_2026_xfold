import "./index.css";
import { Composition } from "remotion";
import { INTRO_DURATION, XFoldIntro } from "./XFoldIntro";
import { FPS, HEIGHT, WIDTH } from "./theme";

export const RemotionRoot: React.FC = () => {
  return (
    <Composition
      id="XFoldIntro"
      component={XFoldIntro}
      durationInFrames={INTRO_DURATION}
      fps={FPS}
      width={WIDTH}
      height={HEIGHT}
    />
  );
};
