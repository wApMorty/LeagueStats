// 27–30 s : le nom, les chiffres de la base en compteur, le dépôt.
import React from "react";
import { AbsoluteFill, interpolate, useCurrentFrame } from "remotion";
import { C, F, fr, manifest, NUM } from "../theme";
import { Backdrop, clamp, Kinetic, ramp, RuneRings } from "../ui";

const Counter: React.FC<{ value: number; label: string; start: number }> = ({ value, label, start }) => {
  const frame = useCurrentFrame();
  const shown = Math.round(interpolate(frame, [start, start + 30], [0, value], clamp));
  return (
    <div style={{ textAlign: "center", opacity: ramp(frame, start, start + 8) }}>
      <div style={{ fontFamily: F.title, fontWeight: 600, fontSize: 96, color: C.gold, ...NUM }}>
        {fr(shown)}
      </div>
      <div style={{ fontFamily: F.ui, fontSize: 30, letterSpacing: 4, textTransform: "uppercase", color: C.muted }}>
        {label}
      </div>
    </div>
  );
};

export const Cloture: React.FC<{ dur: number }> = () => {
  const frame = useCurrentFrame();
  const { champions, matchups } = manifest.chiffres;
  return (
    <AbsoluteFill>
      <Backdrop hue="gold" />
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center" }}>
        <RuneRings size={1150} opacity={0.35} color={C.gold} />
      </AbsoluteFill>
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", flexDirection: "column", gap: 60 }}>
        <Kinetic words={["LeagueStats", "Coach"]} start={2} every={6} size={170} accent={1} />
        <div style={{ display: "flex", gap: 140 }}>
          <Counter value={champions} label="champions" start={18} />
          <Counter value={matchups} label="matchups" start={24} />
          <div style={{ textAlign: "center", opacity: ramp(frame, 30, 38) }}>
            <div style={{ fontFamily: F.title, fontWeight: 600, fontSize: 96, color: C.gold }}>Master+</div>
            <div style={{ fontFamily: F.ui, fontSize: 30, letterSpacing: 4, textTransform: "uppercase", color: C.muted }}>
              tier de référence
            </div>
          </div>
        </div>
        <div style={{ fontFamily: F.ui, fontSize: 34, color: C.ink, opacity: ramp(frame, 44, 58), letterSpacing: 2 }}>
          github.com/wApMorty/LeagueStats
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
