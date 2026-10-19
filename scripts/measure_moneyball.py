"""Mesure Moneyball du début de partie (SPEC-35 §4.4, tâche 174).

Lit `crawl.db` (parties de tiers, lues) et `db.db` (tes parties, `game_records`) en lecture seule,
puis : valorise les actions de début de partie par rôle (`value_actions`), recoupe avec les
impacts SPEC-20 (modèle en place, biais imprimé), et décide pour ton propre écart à l'adversaire
de lane (`player_gap`, `decide`). Ce n'est pas un test : les chiffres dépendent des bases et du
modèle. Aucune écriture.

USAGE:
    python scripts/measure_moneyball.py                  # mesure complète
    python scripts/measure_moneyball.py --limit 5000     # 5 000 parties lues les plus récentes
"""

import argparse
import json
import sqlite3
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean
from typing import Dict, List, Optional, Set, Tuple

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config import config
from src.config_constants import coaching_config
from src.config_winprob import winprob_config as cfg
from src.coaching.metrics import ROLES, participant_roles
from src.coaching.moneyball import (
    ACTIONS,
    decide,
    lane_rows,
    player_gap,
    player_gaps,
    value_actions,
)
from src.winprob.crawl import unpack
from src.winprob.impact import impacts
from src.winprob.model import WinModel
from src.winprob.state import blue_win
from src.winprob.train import crawl_path, load_model

PROGRESS_EVERY = 5000
# Types d'impacts SPEC-20 recoupés avec les actions (SPEC-35 §4.4).
IMPACT_TYPES = ("death", "death_solo", "lost_dragon", "lost_grubs")


@dataclass
class Sample:
    """Lignes par rôle, chronologiques : écarts bleu − rouge, issues bleues, impacts."""

    lines: Dict[str, List[Dict[str, float]]] = field(default_factory=lambda: defaultdict(list))
    wins: Dict[str, List[int]] = field(default_factory=lambda: defaultdict(list))
    impacts: Dict[str, List[Tuple[str, float]]] = field(default_factory=lambda: defaultdict(list))


def _parse_args() -> argparse.Namespace:
    """Arguments de la ligne de commande : bases et nombre de parties lues."""
    parser = argparse.ArgumentParser(description="SPEC-35 : mesure Moneyball du début de partie")
    parser.add_argument("--crawl-path", default=str(crawl_path()))
    parser.add_argument("--db-path", default=str(config.DATABASE_PATH))
    parser.add_argument(
        "--limit", type=int, default=None, help="parties de crawl.db les plus récentes, au plus"
    )
    return parser.parse_args()


def _open_ro(path: Path) -> sqlite3.Connection:
    """Connexion en lecture seule à `path` ; sort en erreur si la base est absente."""
    if not path.exists():
        print(f"[ERREUR] Base absente : {path}")
        raise SystemExit(1)
    return sqlite3.connect(
        f"file:{path.as_posix()}?mode=ro", uri=True, timeout=cfg.FORM_DB_TIMEOUT_S
    )


def _player_puuids(game_db: sqlite3.Connection) -> Set[str]:
    """Puuids de @pj35 : identité de `player_participant_id` dans chaque `raw_game`."""
    puuids: Set[str] = set()
    query = (
        "SELECT raw_game, player_participant_id FROM game_records "
        "WHERE player_participant_id IS NOT NULL"
    )
    for raw_game, participant_id in game_db.execute(query):
        for identity in json.loads(raw_game).get("participantIdentities") or []:
            puuid = (identity.get("player") or {}).get("puuid")
            if identity.get("participantId") == participant_id and puuid:
                puuids.add(puuid)
    return puuids


def _has_player(game: dict, puuids: Set[str]) -> bool:
    """Vrai si un des puuids de @pj35 figure dans les identités de la partie."""
    return any(
        (identity.get("player") or {}).get("puuid") in puuids
        for identity in game.get("participantIdentities") or []
    )


def _read_crawl(
    crawl_db: sqlite3.Connection,
    limit: Optional[int],
    puuids: Set[str],
    model: Optional[WinModel],
    counts: Dict[str, int],
) -> Sample:
    """Parties lues de `crawl.db`, de la plus récente à la plus ancienne, en `Sample`.

    `counts` reçoit lues, illisibles, exclues (@pj35 y joue), hors filtre, retenues. Impacts :
    seulement pour les `MONEYBALL_IMPACT_SAMPLE` premières parties retenues, si `model` existe.
    """
    query = (
        "SELECT raw FROM crawl_games WHERE read_utc IS NOT NULL AND queue_id = ? "
        "ORDER BY game_creation_utc DESC, game_id DESC LIMIT ?"
    )
    rows = crawl_db.execute(query, (420, limit if limit else -1))
    cutoff = coaching_config.LANE_MINUTE * 60_000
    sample = Sample()
    began = time.monotonic()
    for (raw,) in rows:
        counts["lues"] += 1
        if counts["lues"] % PROGRESS_EVERY == 0:
            print(f"[INFO] {counts['lues']} parties en {time.monotonic() - began:.0f} s")
        try:
            packed = unpack(raw)
            game, timeline = packed["game"], packed["timeline"]
            if _has_player(game, puuids):
                counts["exclues"] += 1
                continue
            win = blue_win(game)
            if win is None or not (timeline or {}).get("frames"):
                counts["hors_filtre"] += 1
                continue
            lanes = lane_rows(game, timeline, coaching_config.LANE_MINUTE)
            if not lanes:
                counts["hors_filtre"] += 1
                continue
            impact_rows: List[Tuple[str, str, float]] = []
            if model is not None and counts["retenues"] < coaching_config.MONEYBALL_IMPACT_SAMPLE:
                roles = participant_roles(game)
                for row in impacts(model, game, timeline, roles)["rows"]:
                    role = roles.get(row["participant_id"])
                    if role and row["event_time_ms"] < cutoff and row["event_type"] in IMPACT_TYPES:
                        impact_rows.append((role, row["event_type"], row["delta_p"]))
        except Exception:  # pylint: disable=broad-exception-caught
            counts["illisibles"] += 1  # partie illisible : ignorée, comme measure_form_term
            continue
        counts["retenues"] += 1
        for role, values in lanes.items():
            sample.lines[role].append(values)
            sample.wins[role].append(int(win))
        for role, kind, delta in impact_rows:
            sample.impacts[role].append((kind, delta))
    for store in (sample.lines, sample.wins, sample.impacts):
        for values in store.values():
            values.reverse()  # ordre chronologique : blocs contigus pour la validation croisée
    print(
        f"[DATA] {counts['lues']} parties lues ({counts['illisibles']} illisibles, "
        f"{counts['exclues']} exclues (@pj35 y joue), {counts['hors_filtre']} hors filtre), "
        f"{counts['retenues']} retenues en {time.monotonic() - began:.0f} s"
    )
    return sample


def _read_player(game_db: sqlite3.Connection) -> Dict[str, List[Dict[str, float]]]:
    """Rôle -> écarts joueur − adversaire, une ligne par partie de @pj35 (`game_records`)."""
    player: Dict[str, List[Dict[str, float]]] = defaultdict(list)
    query = (
        "SELECT raw_game, raw_timeline, raw_eog, player_participant_id FROM game_records "
        "WHERE queue_id = ? AND raw_timeline IS NOT NULL ORDER BY game_creation_utc, game_id"
    )
    for raw_game, raw_timeline, raw_eog, participant_id in game_db.execute(query, (420,)):
        eog = json.loads(raw_eog) if raw_eog else None
        found = player_gaps(
            json.loads(raw_game),
            json.loads(raw_timeline),
            eog,
            participant_id,
            coaching_config.LANE_MINUTE,
        )
        if found:
            role, gaps = found
            player[role].append(gaps)
    return player


def _print_values(role: str, result: dict, folds: int) -> None:
    """Tableau des actions valorisées d'un rôle : points par unité, IC95, signes par bloc."""
    print(f"[DATA] Valorisation {role} : {result['n']} lignes, validation à {folds} blocs")
    print("  action | pts par unité | IC95 | signes sur les blocs")
    for action in ACTIONS:
        effect = result["effects"][action]
        print(
            f"  {action} | {effect.pts_per_unit:+.3f} | "
            f"[{effect.ci_low:+.3f} ; {effect.ci_high:+.3f}] | {effect.same_sign_folds}/{folds}"
        )
    brier = result["brier"]
    print(f"  Brier modèle {brier['model']:.4f}, constante {brier['constant']:.4f}")


def _print_recoupement(role: str, impact_rows: List[Tuple[str, float]]) -> None:
    """ΔP moyen × 100 et nombre de lignes par type d'impact SPEC-20, pour un rôle."""
    parts = []
    for kind in IMPACT_TYPES:
        deltas = [delta for k, delta in impact_rows if k == kind]
        value = f"{100 * mean(deltas):+.2f} pts" if deltas else "n/a"
        parts.append(f"{kind} {value} ({len(deltas)} lignes)")
    print(f"[DATA] Recoupement SPEC-20 {role} : " + ", ".join(parts))


def _print_moneyball(role: str, n: int, decisions: List[dict], brier: Dict[str, float]) -> None:
    """Tableau Moneyball d'un rôle : écart, effet, gain, trois conditions, verdict."""
    print(
        f"[DATA] Moneyball {role} : {n} parties de @pj35, Brier modèle < constante : "
        f"{'oui' if brier['model'] < brier['constant'] else 'non'}"
    )
    print(
        "  action | écart (IC95) | effet pts/unité | gain attendu | effet | écart | gain | verdict"
    )
    for row in decisions:
        verdict = "ADOPTÉ" if row["adopted"] else ("retenue" if row["passes"] else "rejetée")
        print(
            f"  {row['action']} | {row['gap']:+.3f} "
            f"[{row['gap_low']:+.3f} ; {row['gap_high']:+.3f}]"
            f" | {row['pts_per_unit']:+.3f} | {row['gain']:+.3f} | "
            f"{'oui' if row['effect_ok'] else 'non'} | {'oui' if row['gap_ok'] else 'non'} | "
            f"{'oui' if row['gain_ok'] else 'non'} | {verdict}"
        )
    adopted = next((row["action"] for row in decisions if row["adopted"]), None)
    if adopted:
        print(f"[DATA] Décision {role} : ADOPTÉ {adopted}")
    else:
        print(f"[DATA] Décision {role} : AUCUNE ACTION ADOPTÉE")


def main() -> None:
    """Valorisation par rôle, recoupement SPEC-20, décision sur les parties de @pj35 et vision."""
    args = _parse_args()
    crawl_db = _open_ro(Path(args.crawl_path))
    game_db = _open_ro(Path(args.db_path))
    try:
        began = time.monotonic()
        puuids = _player_puuids(game_db)
        model = load_model()
        if model is None:
            print("[ALERTE] Pas de modèle de win chance : recoupement SPEC-20 non fait.")
        counts = {"lues": 0, "illisibles": 0, "exclues": 0, "hors_filtre": 0, "retenues": 0}
        sample = _read_crawl(crawl_db, args.limit, puuids, model, counts)
        player = _read_player(game_db)
    finally:
        crawl_db.close()
        game_db.close()

    folds = coaching_config.MONEYBALL_CV_FOLDS
    valued: Dict[str, dict] = {}
    for role in ROLES:
        rows = sample.lines.get(role, [])
        if len(rows) < folds:
            print(f"[ALERTE] {role} : {len(rows)} lignes, moins de {folds} : pas de valorisation.")
            continue
        valued[role] = value_actions(rows, sample.wins[role], folds)
        _print_values(role, valued[role], folds)

    if model is not None:
        print("[INFO] Biais : le modèle en place est entraîné sur ces mêmes parties.")
        for role in ROLES:
            _print_recoupement(role, sample.impacts.get(role, []))

    min_games = coaching_config.MONEYBALL_MIN_PLAYER_GAMES
    player_gap_by_role: Dict[str, Dict[str, Tuple[float, float, float]]] = {}
    for role in ROLES:
        gaps = player.get(role, [])
        if len(gaps) < min_games or role not in valued:
            continue
        gap = player_gap(gaps, coaching_config.MONEYBALL_BOOTSTRAP, coaching_config.MONEYBALL_SEED)
        player_gap_by_role[role] = gap
        result = valued[role]
        decisions = decide(
            result["effects"],
            gap,
            result["brier"],
            coaching_config.MONEYBALL_GAIN_MIN_PTS,
            folds,
        )
        _print_moneyball(role, len(gaps), decisions, result["brier"])
    if not player_gap_by_role:
        print(f"[INFO] Aucun rôle à {min_games} parties de @pj35 valorisé : pas de décision.")

    print(
        "[INFO] Hors classement : score de fin de partie, confondu avec la durée et l'issue. "
        "Ne décide rien."
    )
    for role in ROLES:
        if role not in valued:
            continue
        vision = valued[role]["vision"]
        gap = player_gap_by_role.get(role, {}).get("vision")
        gap_text = f"{gap[0]:+.3f}" if gap else "n/a"
        print(
            f"[DATA] Vision hors classement {role} : {vision.pts_per_unit:+.3f} pts par unité, "
            f"IC [{vision.ci_low:+.3f} ; {vision.ci_high:+.3f}], écart de @pj35 {gap_text}"
        )
    print(f"[INFO] Mesure en {time.monotonic() - began:.0f} s")


if __name__ == "__main__":
    main()
