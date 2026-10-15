// Compositions (SPEC-34 §4.6) : `Teaser` 30 s en 1 920 × 1 080, muet ; `Hero`, la boucle du README.
import React from "react";
import { AbsoluteFill, Composition, Sequence } from "remotion";
import { Accroche } from "./scenes/Accroche";
import { Cloture } from "./scenes/Cloture";
import { Draft } from "./scenes/Draft";
import { Verrouillage } from "./scenes/Verrouillage";
import { C, FPS, HEIGHT, WIDTH } from "./theme";
import { Calm, SceneFade } from "./ui";

type Scene = { dur: number; render: (dur: number) => React.ReactNode };

// Storyboard de la spec : les scènes s'enchaînent, durées en images à 30 fps.
const TEASER: Scene[] = [
  { dur: 90, render: (dur) => <Accroche dur={dur} /> },
  { dur: 180, render: (dur) => <Draft dur={dur} /> },
  { dur: 120, render: (dur) => <Verrouillage dur={dur} /> },
  { dur: 420, render: () => null }, // En partie, revue et mosaïque : tâche 169
  { dur: 90, render: (dur) => <Cloture dur={dur} /> },
];

// La boucle du README : draft (la courbe arrive avec la tâche 169).
const HERO: Scene[] = [
  { dur: 120, render: (dur) => <Draft dur={dur} /> },
];

const total = (scenes: Scene[]) => scenes.reduce((sum, s) => sum + s.dur, 0);

const Timeline: React.FC<{ scenes: Scene[] }> = ({ scenes }) => {
  let from = 0;
  return (
    <AbsoluteFill style={{ background: C.bgDeep }}>
      {scenes.map(({ dur, render }) => {
        const start = from;
        from += dur;
        return (
          <Sequence key={start} from={start} durationInFrames={dur}>
            <SceneFade dur={dur}>{render(dur)}</SceneFade>
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};

const Teaser: React.FC = () => <Timeline scenes={TEASER} />;

/** Le README reçoit la même mise en scène, réduite de moitié. */
const Hero: React.FC = () => (
  <AbsoluteFill style={{ transform: "scale(0.5)", transformOrigin: "top left", width: WIDTH, height: HEIGHT }}>
    <Calm.Provider value>
      <Timeline scenes={HERO} />
    </Calm.Provider>
  </AbsoluteFill>
);

export const RemotionRoot: React.FC = () => (
  <>
    <Composition id="Teaser" component={Teaser} durationInFrames={total(TEASER)} fps={FPS} width={WIDTH} height={HEIGHT} />
    <Composition id="Hero" component={Hero} durationInFrames={total(HERO)} fps={FPS} width={WIDTH / 2} height={HEIGHT / 2} />
  </>
);
