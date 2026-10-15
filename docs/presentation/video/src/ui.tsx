// Briques visuelles du teaser : fond vivant, anneaux runiques, texte cinétique, cadrage dans une capture.
import React from "react";
import {
  AbsoluteFill,
  Easing,
  Img,
  interpolate,
  random,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";
import { C, F, HEIGHT, RUNES, WIDTH } from "./theme";

export const clamp = { extrapolateLeft: "clamp", extrapolateRight: "clamp" } as const;
export const ease = Easing.bezier(0.16, 1, 0.3, 1);

/** Progression 0 → 1 entre deux images, adoucie. */
export const ramp = (frame: number, from: number, to: number): number =>
  interpolate(frame, [from, to], [0, 1], { ...clamp, easing: ease });

/** Vrai pour la boucle GIF : fond figé, le GIF ne réencode alors que ce qui bouge vraiment. */
export const Calm = React.createContext(false);

/** Fond du client : vert très sombre, halos menthe et magenta qui respirent, poussière d'étoiles. */
export const Backdrop: React.FC<{ hue?: "mint" | "magenta" | "gold" }> = ({ hue = "mint" }) => {
  const live = useCurrentFrame();
  const frame = React.useContext(Calm) ? 0 : live;
  const glow = { mint: C.mint, magenta: C.magenta, gold: C.gold }[hue];
  const drift = Math.sin(frame / 40) * 60;
  return (
    <AbsoluteFill style={{ background: C.bgDeep, overflow: "hidden" }}>
      <AbsoluteFill
        style={{
          background: `radial-gradient(900px 700px at ${30 + drift / 20}% 35%, color-mix(in oklch, ${glow} 22%, transparent), transparent 70%),
            radial-gradient(800px 600px at ${75 - drift / 25}% 75%, color-mix(in oklch, ${C.violet} 16%, transparent), transparent 70%)`,
        }}
      />
      {Array.from({ length: 70 }, (_, i) => {
        const x = random(`x${i}`) * WIDTH;
        const y = (random(`y${i}`) * HEIGHT - frame * (0.3 + random(`v${i}`) * 0.9)) % HEIGHT;
        const size = 1 + random(`s${i}`) * 2.5;
        const twinkle = 0.25 + 0.75 * Math.abs(Math.sin(frame / 18 + i));
        return (
          <div
            key={i}
            style={{
              position: "absolute",
              left: x,
              top: y < 0 ? y + HEIGHT : y,
              width: size,
              height: size,
              borderRadius: "50%",
              background: i % 3 ? C.mint : C.gold,
              opacity: twinkle * 0.6,
              boxShadow: `0 0 ${size * 4}px ${i % 3 ? C.mint : C.gold}`,
            }}
          />
        );
      })}
    </AbsoluteFill>
  );
};

/** Anneaux runiques et pentagramme du client, tracés puis en rotation lente. */
export const RuneRings: React.FC<{ size: number; delay?: number; color?: string; opacity?: number }> = ({
  size,
  delay = 0,
  color = C.copper,
  opacity = 1,
}) => {
  const frame = useCurrentFrame() - delay;
  const draw = ramp(frame, 0, 40);
  const r = 340;
  const circumference = 2 * Math.PI * r;
  const star = [0, 2, 4, 1, 3]
    .map((k) => {
      const a = -Math.PI / 2 + (k * 2 * Math.PI) / 5;
      return `${Math.cos(a) * 290},${Math.sin(a) * 290}`;
    })
    .join(" ");
  return (
    <svg
      width={size}
      height={size}
      viewBox="-370 -370 740 740"
      style={{ opacity, transform: `rotate(${frame * 0.25}deg)`, overflow: "visible" }}
    >
      <defs>
        <path id="ring-path" d="M0,-318 A318,318 0 1,1 0,318 A318,318 0 1,1 0,-318" />
      </defs>
      <circle
        r={r}
        fill="none"
        stroke={color}
        strokeWidth={2}
        strokeDasharray={circumference}
        strokeDashoffset={circumference * (1 - draw)}
      />
      <circle r={300} fill="none" stroke={color} strokeOpacity={0.35} strokeWidth={1} />
      <text fill={color} fillOpacity={draw * 0.8} fontFamily={F.rune} fontSize={22} letterSpacing={6}>
        <textPath href="#ring-path">{RUNES.repeat(3)}</textPath>
      </text>
      <polygon
        points={star}
        fill="none"
        stroke={C.mint}
        strokeWidth={2}
        strokeDasharray={3000}
        strokeDashoffset={3000 * (1 - ramp(frame, 15, 60))}
        style={{ filter: `drop-shadow(0 0 12px ${C.mint})` }}
      />
    </svg>
  );
};

/** Mots qui entrent un à un : montée, flou qui se dissipe, ressort. */
export const Kinetic: React.FC<{
  words: string[];
  start?: number;
  every?: number;
  size?: number;
  color?: string;
  accent?: number;
  font?: string;
}> = ({ words, start = 0, every = 6, size = 120, color = C.ink, accent = -1, font = F.title }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  return (
    <div style={{ display: "flex", flexWrap: "wrap", gap: size * 0.28, justifyContent: "center" }}>
      {words.map((word, i) => {
        const t = spring({ frame: frame - start - i * every, fps, config: { damping: 14, mass: 0.6 } });
        return (
          <span
            key={i}
            style={{
              fontFamily: font,
              fontWeight: 600,
              fontSize: size,
              lineHeight: 1,
              color: i === accent ? C.mint : color,
              opacity: t,
              filter: `blur(${(1 - t) * 18}px)`,
              transform: `translateY(${(1 - t) * 60}px) scale(${0.85 + 0.15 * t})`,
              textShadow: i === accent ? `0 0 40px ${C.mint}` : "0 4px 30px rgba(0,0,0,0.6)",
            }}
          >
            {word}
          </span>
        );
      })}
    </div>
  );
};

/** Une capture (1 920 × 1 080), entière ou cadrée sur la zone `crop` = [x, y, largeur, hauteur]. */
export const Shot: React.FC<{
  file: string;
  crop?: [number, number, number, number];
  width: number;
  style?: React.CSSProperties;
}> = ({ file, crop = [0, 0, WIDTH, HEIGHT], width, style }) => {
  const [x, y, w, h] = crop;
  const scale = width / w;
  return (
    <div
      style={{
        width,
        height: h * scale,
        overflow: "hidden",
        position: "relative",
        borderRadius: 14,
        boxShadow: "0 40px 120px rgba(0,0,0,0.7), 0 0 0 1px rgba(255,255,255,0.06)",
        ...style,
      }}
    >
      <Img
        src={staticFile(file)}
        style={{
          position: "absolute",
          left: -x * scale,
          top: -y * scale,
          width: WIDTH * scale,
          height: HEIGHT * scale,
        }}
      />
    </div>
  );
};

/** Légende en bas à gauche : surtitre cuivre, titre en Cormorant, filet qui se trace. */
export const Caption: React.FC<{ kicker: string; title: string; start?: number }> = ({
  kicker,
  title,
  start = 0,
}) => {
  const frame = useCurrentFrame() - start;
  const t = ramp(frame, 0, 18);
  return (
    <>
    <div
      style={{
        position: "absolute",
        inset: "auto 0 0 0",
        height: 460,
        opacity: t,
        background: `linear-gradient(to top, ${C.bgDeep} 25%, color-mix(in oklch, ${C.bgDeep} 70%, transparent) 60%, transparent)`,
      }}
    />
    <div style={{ position: "absolute", left: 110, bottom: 90, opacity: t }}>
      <div
        style={{
          fontFamily: F.ui,
          fontWeight: 700,
          fontSize: 26,
          letterSpacing: 8,
          textTransform: "uppercase",
          color: C.copper,
          transform: `translateX(${(1 - t) * -40}px)`,
        }}
      >
        {kicker}
      </div>
      <div
        style={{
          height: 2,
          width: 520 * ramp(frame, 4, 26),
          background: `linear-gradient(90deg, ${C.copper}, transparent)`,
          margin: "14px 0 18px",
        }}
      />
      <div
        style={{
          fontFamily: F.title,
          fontWeight: 600,
          fontSize: 76,
          color: C.ink,
          maxWidth: 1100,
          lineHeight: 1.05,
          textShadow: "0 6px 40px rgba(0,0,0,0.8)",
          transform: `translateY(${(1 - t) * 30}px)`,
        }}
      >
        {title}
      </div>
    </div>
    </>
  );
};

/** Fondu d'entrée et de sortie d'une scène de `dur` images. */
export const SceneFade: React.FC<{ dur: number; children: React.ReactNode }> = ({ dur, children }) => {
  const frame = useCurrentFrame();
  const opacity = Math.min(ramp(frame, 0, 8), 1 - ramp(frame, dur - 8, dur));
  return <AbsoluteFill style={{ opacity }}>{children}</AbsoluteFill>;
};
