// 9–13 s : flash au verrouillage, la page de runes et la build glissent dans le cadre.
import React from "react";
import { AbsoluteFill, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { C, capture, F, fr, manifest, NUM } from "../theme";
import { Caption, ramp, Shot } from "../ui";

// Zones de la capture « draft-lock » (1 920 × 1 080) : panneau runes et build, mon portrait verrouillé.
const LOADOUT: [number, number, number, number] = [1482, 84, 436, 950];
const ME: [number, number, number, number] = [260, 190, 300, 120];

export const Verrouillage: React.FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const flash = 1 - ramp(frame, 0, 12);
  const panel = spring({ frame: frame - 8, fps, config: { damping: 15 } });
  const badge = spring({ frame: frame - 18, fps, config: { damping: 11 } });
  const drift = 1.04 + (frame / dur) * 0.08;
  const final = manifest.draft.final_probability;

  return (
    <AbsoluteFill style={{ background: C.bgDeep }}>
      <AbsoluteFill style={{ transform: `scale(${drift})`, filter: "brightness(0.42) saturate(1.2) blur(5px)" }}>
        <Shot file={capture("draft-lock")} width={1920} style={{ borderRadius: 0 }} />
      </AbsoluteFill>
      <div
        style={{
          position: "absolute",
          right: 120,
          top: 70,
          transform: `translateX(${(1 - panel) * 900}px) rotate(${(1 - panel) * 6}deg)`,
        }}
      >
        <Shot
          file={capture("draft-lock")}
          crop={LOADOUT}
          width={500}
          style={{ boxShadow: `0 0 0 2px ${C.mint}, 0 0 80px color-mix(in oklch, ${C.mint} 45%, transparent)` }}
        />
      </div>
      <div
        style={{
          position: "absolute",
          left: 140,
          top: 200,
          transform: `scale(${badge}) rotate(${(1 - badge) * -20}deg)`,
          transformOrigin: "left center",
        }}
      >
        <Shot file={capture("draft-lock")} crop={ME} width={600} />
        <div style={{ fontFamily: F.ui, fontSize: 36, color: C.ink, marginTop: 26 }}>
          Fin de draft estimée :{" "}
          <b style={{ color: C.mint, fontSize: 64, fontFamily: F.title, ...NUM }}>
            {fr(final * 100, 1)}&nbsp;%
          </b>
        </div>
      </div>
      <AbsoluteFill style={{ background: C.mint, opacity: flash * 0.85, mixBlendMode: "screen" }} />
      <Caption kicker="Verrouillage" title="Runes, sorts et build importés." start={10} />
    </AbsoluteFill>
  );
};
