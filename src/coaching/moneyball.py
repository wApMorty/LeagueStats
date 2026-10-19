"""Étude Moneyball du début de partie (SPEC-35 §4.1, tâche 171).

Ce que chaque joueur fait avant 14 min : CS, morts, morts solo, morts sans contrepartie, présence aux
objectifs, et vision (en fin de partie, hors classement). Fonctions pures, sans base ni réseau : elles
lisent le format LCU commun à `crawl.db` et `game_records`.

`lane_rows` donne, par rôle, les écarts bleu − rouge entre adversaires de lane ; `player_gaps` donne les
écarts d'un joueur à son adversaire de lane. La valorisation (tâche 172) et la décision (tâche 173)
partent de ces lignes.
"""

import math
import random
from typing import Dict, List, NamedTuple, Optional, Sequence, Tuple

from ..analysis.calibration import brier_score
from ..config_constants import coaching_config
from ..winprob import impact
from ..winprob.model import WinModel, _solve, expand, fit
from ..winprob.state import BLUE, _other
from . import metrics

ACTIONS = ("cs", "deaths", "solo_deaths", "untraded_deaths", "presence")
# Valeurs suivies par `lane_rows` et `player_gaps` : les actions, plus la vision (hors classement).
_VALUES = ACTIONS + ("vision",)


def _team_of(game: dict) -> Dict[int, int]:
    """participantId -> teamId."""
    return {p["participantId"]: p["teamId"] for p in game["participants"]}


def _usable(game: dict, timeline: Optional[dict], minute: int) -> bool:
    """Partie exploitable à `minute` : pas de remake, durée suffisante, image de `minute` présente."""
    frames = (timeline or {}).get("frames") or []
    return (
        not metrics.is_remake(game)
        and (game.get("gameDuration") or 0) >= coaching_config.MONEYBALL_MIN_DURATION_MIN * 60
        and len(frames) > minute
    )


def _contributions(timeline: dict, team_of: Dict[int, int]) -> List[Tuple[int, int]]:
    """(instant, équipe) de chaque événement qui rapporte à une équipe, dans toute la timeline.

    Un kill rapporte à l'équipe de la victime adverse (comme le compteur de `winprob.state`). Un monstre
    épique ou un bâtiment rapporte à l'équipe qui le marque.
    """
    out = []
    for e in metrics._events(timeline, "CHAMPION_KILL"):
        if e.get("victimId") in team_of:
            out.append((e["timestamp"], _other(team_of[e["victimId"]])))
    for kind in ("ELITE_MONSTER_KILL", "BUILDING_KILL"):
        for e in metrics._events(timeline, kind):
            team = impact.scoring_team(e, team_of)
            if team is not None:
                out.append((e["timestamp"], team))
    return out


def _traded(t: int, team: int, contributions: List[Tuple[int, int]], window: int) -> bool:
    """Vrai si `team` rapporte un événement à ± `window` ms de l'instant `t` (la mort s'échange)."""
    return any(c_team == team and abs(ts - t) <= window for ts, c_team in contributions)


def player_actions(game: dict, timeline: dict, minute: int) -> Dict[int, Dict[str, float]]:
    """participantId -> actions à `minute` : CS, morts, morts solo, morts sans contrepartie, présence
    aux objectifs (part des monstres épiques de son équipe avant `minute` où il est présent). Plus
    `vision` (visionScore / min de partie entière, hors classement).

    Rend `{}` si l'image `minute` manque (pas de CS à lire).
    """
    frame = metrics._frame(timeline, minute)
    if frame is None:
        return {}
    team_of = _team_of(game)
    cutoff = minute * 60_000
    window = int(coaching_config.MONEYBALL_TRADE_WINDOW_S * 1000)
    kills = metrics._events(timeline, "CHAMPION_KILL")
    contributions = _contributions(timeline, team_of)
    monsters = [
        e
        for e in metrics._events(timeline, "ELITE_MONSTER_KILL")
        if e.get("monsterType") in metrics.ELITE_MONSTERS
        and e.get("killerId") in team_of
        and e["timestamp"] < cutoff
    ]
    actions: Dict[int, Dict[str, float]] = {}
    for p in game["participants"]:
        pid, team = p["participantId"], p["teamId"]
        deaths = [e for e in kills if e.get("victimId") == pid and e["timestamp"] < cutoff]
        solo = [
            e
            for e in deaths
            if e.get("killerId") in team_of and not e.get("assistingParticipantIds")
        ]
        untraded = [e for e in deaths if not _traded(e["timestamp"], team, contributions, window)]
        team_monsters = [e for e in monsters if team_of[e["killerId"]] == team]
        present = [
            e
            for e in team_monsters
            if pid == e["killerId"]
            or pid in (e.get("assistingParticipantIds") or [])
            or impact.present(timeline, e, [pid])
        ]
        actions[pid] = {
            "cs": float(metrics._cs(frame, pid)),
            "deaths": float(len(deaths)),
            "solo_deaths": float(len(solo)),
            "untraded_deaths": float(len(untraded)),
            "presence": len(present) / max(len(team_monsters), 1),
            "vision": p["stats"]["visionScore"] / (game["gameDuration"] / 60),
        }
    return actions


def _lane_pairs(
    roles: Dict[int, Optional[str]], team_of: Dict[int, int]
) -> Optional[Dict[str, Tuple[int, int]]]:
    """Rôle -> (participantId bleu, participantId rouge), None si un rôle manque ou est dupliqué
    dans une équipe (il faut exactement `metrics.ROLES` des deux côtés)."""
    pairs: Dict[str, Tuple[int, int]] = {}
    for role in metrics.ROLES:
        blue = [pid for pid, lane in roles.items() if lane == role and team_of[pid] == BLUE]
        red = [pid for pid, lane in roles.items() if lane == role and team_of[pid] != BLUE]
        if len(blue) != 1 or len(red) != 1:
            return None
        pairs[role] = (blue[0], red[0])
    return pairs


def lane_rows(game: dict, timeline: dict, minute: int) -> Dict[str, Dict[str, float]]:
    """Rôle -> écarts bleu − rouge des actions entre adversaires de lane, à `minute`.

    Vide si un poste manque ou est ambigu (`participant_roles`), si la partie est un remake, si elle
    dure moins de `MONEYBALL_MIN_DURATION_MIN`, ou si l'image `minute` manque.
    """
    if not _usable(game, timeline, minute):
        return {}
    team_of = _team_of(game)
    pairs = _lane_pairs(metrics.participant_roles(game), team_of)
    if pairs is None:
        return {}
    values = player_actions(game, timeline, minute)
    return {
        role: {k: values[blue][k] - values[red][k] for k in _VALUES}
        for role, (blue, red) in pairs.items()
    }


def player_gaps(
    game: dict, timeline: dict, eog: Optional[dict], player_pid: int, minute: int
) -> Optional[Tuple[str, Dict[str, float]]]:
    """(rôle, écarts joueur − adversaire de lane) pour une partie de @pj35, None si incalculable.

    Mêmes exclusions que `lane_rows` (remake, durée, image). Rôle par `participant_roles(game, eog)`,
    adversaire par `metrics._opponent` ; None s'il n'y a pas d'adversaire.
    """
    if not _usable(game, timeline, minute):
        return None
    roles = metrics.participant_roles(game, eog)
    role = roles.get(player_pid)
    if not role:
        return None
    opponent = metrics._opponent(player_pid, roles, _team_of(game))
    if opponent is None:
        return None
    values = player_actions(game, timeline, minute)
    return role, {k: values[player_pid][k] - values[opponent][k] for k in _VALUES}


# Quantile de la loi normale à 97,5 % : constante mathématique, pas un réglage.
Z95 = 1.96
# Variantes du modèle (SPEC-35 §4.2) : variables du modèle, puis actions qu'il valorise. Les parts de
# morts (`other_deaths`, `traded_deaths`) sont calculées dans `value_actions`.
_VARIANTS = (
    (("cs", "deaths", "presence"), ("cs", "deaths", "presence")),
    (("cs", "solo_deaths", "other_deaths", "presence"), ("solo_deaths",)),
    (("cs", "untraded_deaths", "traded_deaths", "presence"), ("untraded_deaths",)),
    (("cs", "deaths", "presence", "vision"), ("vision",)),
)


class Effect(NamedTuple):
    """Effet d'une action sur la win chance : points par unité, IC95 de Wald, blocs de même signe."""

    action: str
    pts_per_unit: float
    ci_low: float
    ci_high: float
    same_sign_folds: int


def _fit(rows: Sequence[Dict[str, float]], wins: Sequence[int], inputs: Sequence[str]) -> WinModel:
    """Ajuste la logistique sur des lignes à `time_min` 0 : les produits avec le temps sont nuls, leurs
    poids restent à 0 (pénalité L2) et leur `scale` vaut 1."""
    return fit([{"time_min": 0.0, **row} for row in rows], wins, inputs)


def _cross_validate(
    rows: Sequence[Dict[str, float]], wins: Sequence[int], inputs: Sequence[str], folds: int
) -> Tuple[WinModel, List[Tuple[int, int, WinModel]]]:
    """Modèle global et, pour chaque bloc contigu `[lo, hi[`, le modèle ajusté sur le reste."""
    n = len(rows)
    blocks = []
    for k in range(folds):
        lo, hi = k * n // folds, (k + 1) * n // folds
        sub = _fit(list(rows[:lo]) + list(rows[hi:]), list(wins[:lo]) + list(wins[hi:]), inputs)
        blocks.append((lo, hi, sub))
    return _fit(rows, wins, inputs), blocks


def _wald_var(
    model: WinModel, rows: Sequence[Dict[str, float]], probs: List[float], j: int
) -> float:
    """Variance de `w_j` : élément (j, j) de l'inverse de la hessienne des variables de base et du biais.

    Les colonnes produit sont exclues : elles valent 0 à `time_min` 0, donc n'apportent rien à la
    hessienne du modèle ajusté.
    """
    k = len(model.inputs)
    h = [[0.0] * (k + 1) for _ in range(k + 1)]
    for row, p in zip(rows, probs):
        x = expand({"time_min": 0.0, **row}, model.inputs)
        z = [(x[i] - model.mean[i]) / model.scale[i] for i in range(k)] + [1.0]
        weight = p * (1 - p)
        for a in range(k + 1):
            for b in range(k + 1):
                h[a][b] += weight * z[a] * z[b]
    e_j = [1.0 if i == j else 0.0 for i in range(k + 1)]
    return _solve(h, e_j)[j]


def _effect(
    model: WinModel,
    rows: Sequence[Dict[str, float]],
    probs: List[float],
    action: str,
    blocks: List[Tuple[int, int, WinModel]],
) -> Effect:
    """Effet marginal moyen de `action`, IC95 de Wald et nombre de blocs de même signe que le global."""
    j = model.inputs.index(action)
    w, scale = model.weights[j], model.scale[j]
    mean_var = sum(p * (1 - p) for p in probs) / len(probs)
    se = math.sqrt(_wald_var(model, rows, probs, j))
    same = sum(1 for _, _, sub in blocks if sub.weights[j] * w > 0)
    return Effect(
        action,
        100 * w / scale * mean_var,
        100 * (w - Z95 * se) / scale * mean_var,
        100 * (w + Z95 * se) / scale * mean_var,
        same,
    )


def _brier(
    rows: Sequence[Dict[str, float]], wins: Sequence[int], blocks: List[Tuple[int, int, WinModel]]
) -> Dict[str, float]:
    """Brier poolé des prédictions hors bloc du modèle, et de la constante (taux bleu du reste)."""
    model_pairs, constant_pairs = [], []
    for lo, hi, sub in blocks:
        rest = list(wins[:lo]) + list(wins[hi:])
        rate = sum(rest) / len(rest)
        for row, y in zip(rows[lo:hi], wins[lo:hi]):
            model_pairs.append((sub.predict({"time_min": 0.0, **row}), y))
            constant_pairs.append((rate, y))
    return {"model": brier_score(model_pairs), "constant": brier_score(constant_pairs)}


def value_actions(rows: List[Dict[str, float]], wins: List[int], folds: int) -> dict:
    """Valorise les actions par régression logistique (SPEC-35 §4.2, tâche 172).

    `rows` : une ligne par adversaire de lane (écarts bleu − rouge, comme `lane_rows`), `wins` : victoires
    bleues (0 ou 1), `folds` : blocs contigus de la validation croisée (au moins 2). Rend `n`, `effects`
    (cs, deaths, presence, solo_deaths, untraded_deaths), `vision` (hors classement) et `brier` (modèle et
    constante, variante V1, validation croisée poolée).
    """
    derived = [
        {
            **row,
            "other_deaths": row["deaths"] - row["solo_deaths"],
            "traded_deaths": row["deaths"] - row["untraded_deaths"],
        }
        for row in rows
    ]
    effects: Dict[str, Effect] = {}
    brier: Dict[str, float] = {}
    for index, (inputs, actions) in enumerate(_VARIANTS):
        model, blocks = _cross_validate(derived, wins, inputs, folds)
        probs = [model.predict({"time_min": 0.0, **row}) for row in derived]
        for action in actions:
            effects[action] = _effect(model, derived, probs, action, blocks)
        if index == 0:
            brier = _brier(derived, wins, blocks)
    vision = effects.pop("vision")
    return {"n": len(rows), "effects": effects, "vision": vision, "brier": brier}


# Quantiles du bootstrap à 2,5 % et 97,5 % : constantes statistiques, pas des réglages.
_Q_LOW = 0.025
_Q_HIGH = 0.975


def player_gap(
    gaps: List[Dict[str, float]], resamples: int, seed: int
) -> Dict[str, Tuple[float, float, float]]:
    """Écart moyen du joueur par action, avec IC95 percentile du bootstrap (SPEC-35 §4.3).

    `gaps` : une ligne par partie du joueur (écarts joueur − adversaire, comme `player_gaps`).
    Seules les actions présentes dans toutes les lignes sont gardées. À chaque rééchantillonnage,
    un même tirage d'indices (avec remise) sert à toutes les actions. Rend
    `{action: (moyenne, bas, haut)}`, `{}` si `gaps` est vide.
    """
    if not gaps:
        return {}
    n = len(gaps)
    actions = [a for a in gaps[0] if all(a in row for row in gaps)]
    rng = random.Random(seed)
    means: Dict[str, List[float]] = {a: [] for a in actions}
    for _ in range(resamples):
        draw = [rng.randrange(n) for _ in range(n)]
        for a in actions:
            means[a].append(sum(gaps[i][a] for i in draw) / n)
    low_rank, high_rank = int(_Q_LOW * resamples), int(_Q_HIGH * resamples) - 1
    out: Dict[str, Tuple[float, float, float]] = {}
    for a in actions:
        ranked = sorted(means[a])
        mean = sum(row[a] for row in gaps) / n
        out[a] = (mean, ranked[low_rank], ranked[high_rank])
    return out


def decide(
    effects: Dict[str, Effect],
    gap: Dict[str, Tuple[float, float, float]],
    brier: Dict[str, float],
    gain_min: float,
    folds: int,
) -> List[dict]:
    """Décision par action (SPEC-35 §4.3, tâche 173).

    Une ligne par action valorisée et présente dans `gap`, triée par gain décroissant
    (gain = −écart × points par unité). `effect_ok` : IC de l'effet hors de 0 et même signe sur les
    `folds` blocs ; `gap_ok` : IC de l'écart hors de 0 ; `gain_ok` : gain ≥ `gain_min` ; `passes` :
    les trois, et Brier du modèle < constante. `adopted` n'est vrai que pour la première ligne qui
    `passes`.
    """
    rows = []
    for action, effect in effects.items():
        if action not in gap:
            continue
        mean, low, high = gap[action]
        gain = -mean * effect.pts_per_unit
        effect_ok = (effect.ci_low > 0 or effect.ci_high < 0) and effect.same_sign_folds == folds
        gap_ok = low > 0 or high < 0
        gain_ok = gain >= gain_min
        passes = effect_ok and gap_ok and gain_ok and brier["model"] < brier["constant"]
        rows.append(
            {
                "action": action,
                "pts_per_unit": effect.pts_per_unit,
                "ci_low": effect.ci_low,
                "ci_high": effect.ci_high,
                "same_sign_folds": effect.same_sign_folds,
                "gap": mean,
                "gap_low": low,
                "gap_high": high,
                "gain": gain,
                "effect_ok": effect_ok,
                "gap_ok": gap_ok,
                "gain_ok": gain_ok,
                "passes": passes,
                "adopted": False,
            }
        )
    rows.sort(key=lambda row: row["gain"], reverse=True)
    first = next((row for row in rows if row["passes"]), None)
    if first is not None:
        first["adopted"] = True
    return rows
