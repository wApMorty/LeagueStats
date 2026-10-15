// 13–20 s : la courbe de win chance de la partie simulée, redessinée en SVG, chiffre en tête de tracé.
import React from "react";
import { AbsoluteFill, useCurrentFrame } from "remotion";
import { C, capture, F, fr, manifest, NUM } from "../theme";
import { Backdrop, Calm, Caption, ramp, Shot } from "../ui";

const W = 1500;
const H = 560;
const PAD = { left: 90, right: 40, top: 40, bottom: 70 };

export const EnPartie: React.FC<{ dur: number }> = ({ dur }) => {
  const frame = useCurrentFrame();
  const calm = React.useContext(Calm);
  const series = manifest.win_chance;
  const end = series[series.length - 1][0];
  const x = (t: number) => PAD.left + (t / end) * (W - PAD.left - PAD.right);
  const y = (p: number) => PAD.top + (1 - p) * (H - PAD.top - PAD.bottom);

  // Tracé progressif : les points déjà passés, puis le point courant interpolé entre deux mesures.
  const now = ramp(frame, dur * 0.08, dur * 0.82) * end;
  const shown = series.filter(([t]) => t <= now);
  const next = series.find(([t]) => t > now);
  const last = shown[shown.length - 1] ?? series[0];
  const tip: [number, number] = next
    ? [now, last[1] + ((next[1] - last[1]) * (now - last[0])) / (next[0] - last[0])]
    : last;
  const points = [...shown, tip];
  const line = points.map(([t, p], i) => `${i ? "L" : "M"}${x(t).toFixed(1)},${y(p).toFixed(1)}`).join(" ");
  const area = `${line} L${x(tip[0]).toFixed(1)},${y(0)} L${x(0)},${y(0)} Z`;
  const panel = ramp(frame, 0, 18);

  return (
    <AbsoluteFill>
      <Backdrop hue="magenta" />
      <AbsoluteFill style={{ filter: "blur(10px) brightness(0.35)", transform: `scale(${calm ? 1.06 : 1.08 - frame / (dur * 30)})` }}>
        <Shot file={capture("en-partie")} width={1920} style={{ borderRadius: 0 }} />
      </AbsoluteFill>
      <AbsoluteFill style={{ alignItems: "center", justifyContent: "center", paddingBottom: 170 }}>
        <div
          style={{
            position: "relative",
            opacity: panel,
            transform: `translateY(${(1 - panel) * 40}px)`,
            background: `color-mix(in oklch, ${C.surface} 82%, transparent)`,
            border: `1px solid color-mix(in oklch, ${C.copper} 30%, transparent)`,
            borderRadius: 18,
            boxShadow: "0 40px 120px rgba(0,0,0,0.6)",
          }}
        >
          <div style={{ position: "absolute", left: PAD.left, top: -96, fontFamily: F.title, fontSize: 58, color: C.ink }}>
            Win chance en direct
          </div>
          <div
            style={{
              position: "absolute",
              right: PAD.right,
              top: -158,
              fontFamily: F.title,
              fontWeight: 600,
              fontSize: 130,
              color: tip[1] >= 0.5 ? C.mint : C.rose,
              textShadow: `0 0 40px ${tip[1] >= 0.5 ? C.mint : C.rose}`,
              ...NUM,
            }}
          >
            {fr(tip[1] * 100)}&nbsp;%
          </div>
          <svg width={W} height={H}>
            <defs>
              <linearGradient id="fill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor={C.mint} stopOpacity={0.35} />
                <stop offset="100%" stopColor={C.mint} stopOpacity={0} />
              </linearGradient>
              <linearGradient id="stroke" x1="0" y1="0" x2="1" y2="0">
                <stop offset="0%" stopColor={C.blue} />
                <stop offset="100%" stopColor={C.mint} />
              </linearGradient>
            </defs>
            {[0, 0.5, 1].map((p) => (
              <g key={p}>
                <line
                  x1={PAD.left}
                  x2={W - PAD.right}
                  y1={y(p)}
                  y2={y(p)}
                  stroke={p === 0.5 ? C.copper : C.muted}
                  strokeOpacity={p === 0.5 ? 0.6 : 0.2}
                  strokeDasharray={p === 0.5 ? "8 8" : undefined}
                />
                <text x={PAD.left - 18} y={y(p) + 8} textAnchor="end" fill={C.muted} fontFamily={F.ui} fontSize={24}>
                  {p * 100} %
                </text>
              </g>
            ))}
            {Array.from({ length: Math.floor(end / 300) + 1 }, (_, i) => i * 300).map((t) => (
              <text key={t} x={x(t)} y={H - 24} textAnchor="middle" fill={C.muted} fontFamily={F.ui} fontSize={24}>
                {t / 60} min
              </text>
            ))}
            <path d={area} fill="url(#fill)" />
            <path d={line} fill="none" stroke="url(#stroke)" strokeWidth={6} strokeLinejoin="round" strokeLinecap="round" />
            <circle cx={x(tip[0])} cy={y(tip[1])} r={16} fill={C.mint} style={{ filter: `drop-shadow(0 0 18px ${C.mint})` }} />
            <circle cx={x(tip[0])} cy={y(tip[1])} r={30 + (frame % 30)} fill="none" stroke={C.mint} strokeOpacity={1 - (frame % 30) / 30} />
          </svg>
        </div>
      </AbsoluteFill>
      <Caption kicker="En partie" title="Ta win chance, en direct." start={dur * 0.05} />
    </AbsoluteFill>
  );
};
