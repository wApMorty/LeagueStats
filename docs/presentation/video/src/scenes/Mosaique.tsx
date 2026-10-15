// 25–27 s : six écrans en grille qui se retournent de plus en plus vite.
import React from "react";
import { AbsoluteFill, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { capture } from "../theme";
import { Backdrop, ramp, Shot } from "../ui";

const TILES = ["trouvee", "draft-lock", "en-partie", "revue", "profil", "historique"];

export const Mosaique: React.FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const settle = ramp(frame, 0, dur * 0.7);
  return (
    <AbsoluteFill>
      <Backdrop />
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", perspective: 2200 }}>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(3, 560px)",
            gap: 34,
            transform: `rotateX(${(1 - settle) * 22}deg) rotateZ(${(1 - settle) * -7}deg) scale(${1.35 - settle * 0.38})`,
          }}
        >
          {TILES.map((name, i) => {
            // Départs de plus en plus serrés : la mosaïque accélère.
            const flip = spring({ frame: frame - Math.round(10 * Math.sqrt(i)), fps, config: { damping: 14 } });
            return (
              <div key={name} style={{ transform: `rotateY(${(1 - flip) * 100}deg)`, opacity: flip }}>
                <Shot file={capture(name)} width={560} style={{ borderRadius: 10 }} />
              </div>
            );
          })}
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
