// Palette et polices du client LeagueStats (src/client/static/style.css), reprises telles quelles.
import manifestJson from "../../../images/captures/manifest.json";

export const C = {
  bg: "oklch(0.15 0.02 170)",
  bgDeep: "oklch(0.11 0.018 170)",
  surface: "oklch(0.195 0.02 170)",
  ink: "oklch(0.94 0.012 120)",
  muted: "oklch(0.70 0.02 160)",
  copper: "oklch(0.74 0.11 55)",
  gold: "oklch(0.86 0.13 85)",
  mint: "oklch(0.82 0.13 165)",
  rose: "oklch(0.72 0.21 345)",
  violet: "oklch(0.72 0.20 290)",
  blue: "oklch(0.74 0.15 230)",
  magenta: "oklch(0.70 0.27 345)",
};

export const F = {
  title: '"Cormorant Garamond", Georgia, serif',
  ui: '"Alegreya Sans", "Segoe UI", sans-serif',
  rune: '"Noto Sans Runic", serif',
};

/** Chiffres alignés et à chasse fixe (Cormorant dessine des chiffres elzéviriens par défaut). */
export const NUM = { fontVariantNumeric: "lining-nums tabular-nums" } as const;

/** Nombre à la française, espace insécable classique (toutes les polices l'ont, pas l'espace fine). */
export const fr = (n: number, digits = 0): string =>
  n
    .toLocaleString("fr-FR", { minimumFractionDigits: digits, maximumFractionDigits: digits })
    .replace(/[  ]/g, " ");

export const RUNES = "ᚠᚢᚦᚨᚱᚲᚷᚹᚺᚾᛁᛃᛇᛈᛉᛊᛏᛒᛖᛗᛚᛜᛞᛟ";

export const FPS = 30;
export const WIDTH = 1920;
export const HEIGHT = 1080;

type Manifest = {
  captures: { file: string; scene: string; route: string }[];
  win_chance: [number, number][];
  chiffres: { champions: number; matchups: number; matchups_par_role: Record<string, number> };
  draft: {
    top: { champion: string; lane: string; versus: string; win_probability: number; games: number };
    final_probability: number;
  };
};

export const manifest = manifestJson as unknown as Manifest;

/** Le fichier de capture d'une scène de la démo (ex. « draft-pick » → « 07-draft-pick.png »). */
export const capture = (name: string): string => {
  const found = manifest.captures.find((c) => c.file.endsWith(`-${name}.png`));
  if (!found) throw new Error(`capture absente du manifeste : ${name}`);
  return found.file;
};
