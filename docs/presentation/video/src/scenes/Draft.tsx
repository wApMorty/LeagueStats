// 3–9 s : la draft se redresse, la caméra plonge sur le classement, le n° 1 sort de l'écran.
import React from "react";
import { AbsoluteFill, interpolate, spring, useCurrentFrame, useVideoConfig } from "remotion";
import { C, capture, F, fr, manifest, NUM } from "../theme";
import { Backdrop, Caption, clamp, ramp, Shot } from "../ui";

// Le n° 1 du classement dans la capture « draft-pick » (coordonnées en 1 920 × 1 080).
const TOP_CARD: [number, number, number, number] = [38, 806, 342, 200];

export const Draft: React.FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const at = (share: number) => share * dur; // repères proportionnels : la scène sert aussi au GIF
  const rise = ramp(frame, 0, at(0.24));
  const dive = ramp(frame, at(0.36), at(0.64));
  const pop = spring({ frame: frame - at(0.62), fps, config: { damping: 13, mass: 0.7 } });
  const top = manifest.draft.top;
  const shown = interpolate(frame, [at(0.64), at(0.86)], [0, top.win_probability * 100], clamp);

  return (
    <AbsoluteFill>
      <Backdrop />
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", perspective: 2200 }}>
        <div
          style={{
            transform: `rotateX(${(1 - rise) * 32}deg) rotateY(${(1 - rise) * -14}deg) scale(${0.78 + 0.22 * rise + dive * 0.75})`,
            transformOrigin: "30% 86%",
            opacity: rise * (1 - pop * 0.55),
            filter: `blur(${pop * 6}px)`,
          }}
        >
          <Shot file={capture("draft-pick")} width={1560} />
        </div>
      </AbsoluteFill>
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", flexDirection: "row", gap: 90 }}>
        <div
          style={{
            opacity: pop,
            transform: `translateX(${(1 - pop) * -200}px) scale(${0.6 + 0.4 * pop}) rotate(${(1 - pop) * -8}deg)`,
          }}
        >
          <Shot
            file={capture("draft-pick")}
            crop={TOP_CARD}
            width={720}
            style={{ boxShadow: `0 0 0 3px ${C.gold}, 0 0 90px color-mix(in oklch, ${C.gold} 60%, transparent)` }}
          />
        </div>
        <div style={{ opacity: pop, transform: `translateY(${(1 - pop) * 60}px)` }}>
          <div
            style={{
              fontFamily: F.title,
              fontWeight: 600,
              fontSize: 230,
              lineHeight: 0.9,
              color: C.mint,
              textShadow: `0 0 60px ${C.mint}`,
              marginBottom: 30,
              ...NUM,
            }}
          >
            {fr(shown, 2)}&nbsp;%
          </div>
          <div style={{ fontFamily: F.ui, fontSize: 40, color: C.ink, marginTop: 18 }}>
            de victoire prédite avec <b style={{ color: C.gold }}>{top.champion}</b>
          </div>
          <div style={{ fontFamily: F.ui, fontSize: 32, color: C.muted, marginTop: 8 }}>
            {top.lane} contre {top.versus} · {fr(top.games)} parties mesurées
          </div>
        </div>
      </AbsoluteFill>
      <Caption kicker="Draft en direct" title="Le meilleur pick, chiffré." start={at(0.08)} />
    </AbsoluteFill>
  );
};
