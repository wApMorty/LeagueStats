// 0–3 s : la promesse, mot à mot, sur les anneaux runiques du client.
import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { C, F } from "../theme";
import { Backdrop, Kinetic, ramp, RuneRings } from "../ui";

export const Accroche: React.FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame();
  const zoom = 1 + frame / (dur * 12);
  return (
    <AbsoluteFill>
      <Backdrop />
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", transform: `scale(${zoom})` }}>
        <RuneRings size={980} opacity={0.55} />
      </AbsoluteFill>
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", gap: 28, flexDirection: "column" }}>
        <Kinetic words={["Ta", "draft", "se", "joue"]} start={4} every={5} size={150} />
        <Kinetic words={["avant", "la", "partie."]} start={26} every={5} size={150} accent={0} />
        <div
          style={{
            marginTop: 40,
            fontFamily: F.ui,
            fontWeight: 700,
            fontSize: 28,
            letterSpacing: 12,
            textTransform: "uppercase",
            color: C.copper,
            opacity: ramp(frame, 46, 66),
          }}
        >
          LeagueStats Coach
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};
