// 20–25 s : la revue de partie entre en perspective, les axes de travail tombent en cascade.
import React from "react";
import { AbsoluteFill, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { C, capture } from "../theme";
import { Backdrop, Caption, Shot } from "../ui";

// Les deux cartes « Axe de travail » de la capture « accueil » (1 920 × 1 080).
const AXES: [number, number, number, number][] = [
  [268, 208, 551, 248],
  [841, 208, 526, 248],
];

export const RevueCoaching: React.FC<{ dur: number }> = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const enter = spring({ frame, fps, config: { damping: 16 } });
  return (
    <AbsoluteFill>
      <Backdrop hue="magenta" />
      <AbsoluteFill style={{ perspective: 2400 }}>
        <div
          style={{
            position: "absolute",
            left: 90,
            top: 110,
            transform: `translateX(${(1 - enter) * -1100}px) rotateY(${14 + (1 - enter) * 30}deg)`,
            transformOrigin: "left center",
          }}
        >
          <Shot file={capture("revue")} width={1180} />
        </div>
      </AbsoluteFill>
      {AXES.map((crop, i) => {
        const fall = spring({ frame: frame - 16 - i * 10, fps, config: { damping: 10, mass: 0.8 } });
        return (
          <div
            key={i}
            style={{
              position: "absolute",
              right: 90,
              top: 150 + i * 330,
              opacity: fall,
              transform: `translateY(${(1 - fall) * -700}px) rotate(${(1 - fall) * (i ? 12 : -12)}deg)`,
            }}
          >
            <Shot
              file={capture("accueil")}
              crop={crop}
              width={600}
              style={{ boxShadow: `0 0 0 2px ${i ? C.blue : C.violet}, 0 30px 90px rgba(0,0,0,0.7)` }}
            />
          </div>
        );
      })}
      <Caption kicker="Après la partie" title="Chaque partie revue, tes axes suivis." start={8} />
    </AbsoluteFill>
  );
};
