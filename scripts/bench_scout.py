"""Banc de l'éclaireur des joueurs en partie (SPEC-33 §4.5).

Pour chaque palier de workers (``SCOUT_WORKERS``), un éclaireur neuf lit l'historique et les parties
de dix joueurs pris dans la file ``crawl_frontier`` d'une COPIE TEMPORAIRE de ``crawl.db`` (jamais la
base de production, jamais d'écriture dedans), avec une vraie session LCU et sans Live Client API.
Relève les durées (formes, impacts à 5 / 10 / 20 parties), les erreurs, les 429 et la part du cache.

Arrêt au premier palier qui dépasse un critère (429, erreurs > 2 %, p95 d'un type > 2 × sa valeur au
palier à 4 workers). Conclusion : le plus petit palier propre à moins de 10 % du meilleur temps jusqu'à
10 impacts, et les quartiles des impacts à 10 parties des joueurs éclairés pendant le banc.

Banc réel : client League of Legends ouvert, hors partie et hors draft. Refus propre sinon. Les chiffres
dépendent du réseau, du client et de la base : ce n'est pas un test.

USAGE:
    python scripts/bench_scout.py --dry-run --yes
    python scripts/bench_scout.py
    python scripts/bench_scout.py --workers 1,4,8,12,16 --yes
"""

import argparse
import math
import shutil
import sqlite3
import statistics
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.config import config
from src.config_winprob import winprob_config
from src.lcu_client import LCUClient
from src.winprob.crawl import Crawler
from src.winprob.scout import Scout

PLAYERS = 10
DRY_RUN_WORKERS = 4
DRY_RUN_PLAYERS = 2
DEFAULT_WORKERS = "1,4,8,12,16"
BASELINE_WORKERS = 4
CONCLUSION_WINDOW = 10
REFUSED_PHASES = ("ChampSelect", "ReadyCheck", "InProgress", "GameStart", "Reconnect")
REQUEST_TYPES = ("history", "detail", "timeline")
ERROR_SHARE = 0.02  # erreurs / requêtes au-delà : palier non propre
P95_RATIO = 2.0  # p95 d'un type au-delà de ce multiple de sa valeur au palier de référence
BEST_MARGIN = 0.10  # un palier est retenu à moins de 10 % du meilleur temps jusqu'à 10 impacts
PALIER_TIMEOUT_S = 900.0  # garde-fou : un palier qui ne se termine pas est arrêté
HEADER = (
    f"{'workers':>7} {'formes':>7} {'imp5':>7} {'imp10':>7} {'imp20':>7} {'req':>5} {'err':>6} "
    f"{'429':>4} {'cache':>7} {'p95 hist':>8} {'p95 det':>8} {'p95 tl':>8}"
)


def _schedule(text: str) -> List[int]:
    """'1,4,8' -> [1, 4, 8] ; refuse tout ce qui n'est pas une liste d'entiers >= 1."""
    try:
        values = [int(part) for part in text.split(",")]
    except ValueError as error:
        raise argparse.ArgumentTypeError(f"paliers invalides : {text}") from error
    if not values or min(values) < 1:
        raise argparse.ArgumentTypeError(f"paliers invalides : {text}")
    return values


def _parse_args() -> argparse.Namespace:
    """Options du banc : paliers, mode --dry-run, confirmation sautée par --yes."""
    parser = argparse.ArgumentParser(description="SPEC-33 : banc de l'éclaireur (paliers)")
    parser.add_argument(
        "--workers",
        type=_schedule,
        default=_schedule(DEFAULT_WORKERS),
        help="paliers de workers, séparés par des virgules (défaut : 1,4,8,12,16)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=f"un seul palier à {DRY_RUN_WORKERS} workers, {DRY_RUN_PLAYERS} joueurs",
    )
    parser.add_argument(
        "--yes", action="store_true", help="saute la confirmation « Live Coach fermé ? »"
    )
    return parser.parse_args()


def _seconds(value: Optional[float]) -> str:
    return "—" if value is None else f"{value:.1f}"


def _p95(values: List[float]) -> Optional[float]:
    """Rang au plus proche du 95e centile ; None sans échantillon."""
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(0.95 * len(ordered)) - 1)]


def _connect() -> Optional[LCUClient]:
    """Client LCU connecté, hors partie et hors draft ; None après un [ERREUR] sinon."""
    client = LCUClient()
    credentials = client.find_lcu_credentials()
    if credentials is None:
        print("[ERREUR] Client League of Legends introuvable : ouvre-le (lobby) puis relance.")
        return None
    client.credentials = credentials
    session = client.get_gameflow_session()
    if session is None and client.last_status_code == 404:
        session = {"phase": "None"}  # accueil du client, hors lobby : pas de session gameflow
    if session is None:
        print("[ERREUR] Client sans réponse sur /lol-gameflow/v1/session.")
        return None
    phase = session.get("phase", "")
    if phase in REFUSED_PHASES:
        print(f"[ERREUR] Phase « {phase} » : le banc tourne hors partie et hors draft.")
        return None
    print(f"[INFO] Client connecté, phase « {phase} ».")
    return client


def _confirm(assume_yes: bool) -> bool:
    """Confirmation que le Live Coach est fermé ; faux sur entrée fermée (non interactif)."""
    if assume_yes:
        return True
    try:
        answer = input("Live Coach fermé ? Tape o pour lancer le banc : ")
    except EOFError:
        return False
    return answer.strip().lower() in ("o", "oui", "y", "yes")


def _pick(db: sqlite3.Connection, count: int, used: set) -> List[str]:
    """``count`` joueurs jamais visités de ``crawl_frontier``, hors ceux déjà éclairés par un palier."""
    rows = db.execute(
        "SELECT puuid FROM crawl_frontier WHERE visited_utc IS NULL "
        "ORDER BY depth, priority DESC LIMIT ?",
        (count + len(used),),
    ).fetchall()
    return [puuid for (puuid,) in rows if puuid not in used][:count]


def _reached(snapshot: Dict[str, Any], window: int) -> bool:
    """Chaque joueur est prêt et a min(fenêtre, ses parties) parties avec un impact."""
    return all(
        p["ready"] and p["windows"][window]["impact_n"] >= min(window, p["windows"][window]["n"])
        for p in snapshot.values()
    )


def _palier(workers: int, players: List[dict], copy: Path, client: LCUClient) -> Dict[str, Any]:
    """Un palier : éclaireur neuf à ``workers`` workers, lancé sur ``players``, mesuré jusqu'à la fin."""
    saved = winprob_config.SCOUT_WORKERS
    # Le pool et la session du Scout se dimensionnent à sa construction : patch avant.
    winprob_config.SCOUT_WORKERS = workers
    crawler = None
    scout = None
    try:
        monitor = SimpleNamespace(lcu=client, bus=None)
        crawler = Crawler(monitor, path=copy)
        scout = Scout(monitor, crawler, fetch=lambda: None)
        marks: Dict[int, Optional[float]] = {w: None for w in winprob_config.SCOUT_WINDOWS}
        began = time.monotonic()
        scout.start(players)
        while scout.active and time.monotonic() - began < PALIER_TIMEOUT_S:
            scout.step()
            elapsed = time.monotonic() - began
            snapshot = scout.snapshot()
            for window, at in marks.items():
                if at is None and _reached(snapshot, window):
                    marks[window] = elapsed
            time.sleep(winprob_config.SCOUT_TICK_S)
        stats = scout.stats()
        timings = stats.get("timings", {})
        final = scout.snapshot()
        return {
            "workers": workers,
            "timed_out": scout.active,
            "forms_s": stats.get("forms_s"),
            "marks": marks,
            "requests": stats.get("requests", 0),
            "errors": stats.get("errors", 0),
            "throttled": stats.get("throttled", 0),
            "games": stats.get("games", 0),
            "cache_hits": stats.get("cache_hits", 0),
            "p95": {kind: _p95(timings.get(kind, [])) for kind in REQUEST_TYPES},
            "impacts10": [p["windows"][CONCLUSION_WINDOW]["impact"] for p in final.values()],
        }
    finally:
        winprob_config.SCOUT_WORKERS = saved
        if scout is not None:
            scout.stop()
        if crawler is not None:
            crawler._db().close()  # connexion de la copie, à fermer avant la suppression du dossier


def _breach(
    result: Dict[str, Any], baseline: Optional[Dict[str, Optional[float]]]
) -> Optional[str]:
    """Le critère d'arrêt que ce palier dépasse, ou None."""
    if result["throttled"]:
        return "429 du LCU"
    if result["timed_out"]:
        return f"palier non terminé après {PALIER_TIMEOUT_S:.0f} s"
    if result["requests"] and result["errors"] / result["requests"] > ERROR_SHARE:
        return f"{result['errors']} erreurs sur {result['requests']} requêtes"
    if baseline is not None:
        for kind in REQUEST_TYPES:
            now, ref = result["p95"][kind], baseline[kind]
            if now is not None and ref is not None and now > P95_RATIO * ref:
                return f"p95 {kind} {now:.1f} s > {P95_RATIO:g} × {ref:.1f} s à {BASELINE_WORKERS} workers"
    return None


def _row(result: Dict[str, Any]) -> str:
    """Une ligne du tableau."""
    marks, p95, req = result["marks"], result["p95"], result["requests"]
    err = 100 * result["errors"] / req if req else 0.0
    cache = 100 * result["cache_hits"] / result["games"] if result["games"] else 0.0
    return (
        f"{result['workers']:>7} {_seconds(result['forms_s']):>7} "
        f"{_seconds(marks.get(5)):>7} {_seconds(marks.get(10)):>7} {_seconds(marks.get(20)):>7} "
        f"{req:>5} {err:>5.1f}% {result['throttled']:>4} {cache:>6.0f}% "
        f"{_seconds(p95['history']):>8} {_seconds(p95['detail']):>8} {_seconds(p95['timeline']):>8}"
    )


def _conclude(rows: List[Dict[str, Any]]) -> None:
    """Palier retenu et quartiles des impacts à 10 parties, sur les paliers exécutés."""
    clean = [
        r for r in rows if r["breach"] is None and r["marks"].get(CONCLUSION_WINDOW) is not None
    ]
    if not clean:
        print(
            f"[ALERTE] Aucun palier propre n'atteint {CONCLUSION_WINDOW} impacts : pas de conclusion."
        )
    else:
        best = min(r["marks"][CONCLUSION_WINDOW] for r in clean)
        retained = min(
            r["workers"] for r in clean if r["marks"][CONCLUSION_WINDOW] < best * (1 + BEST_MARGIN)
        )
        print(f"[DATA] Workers retenus : {retained}")
    values = [v for r in rows for v in r["impacts10"] if v is not None]
    if len(values) >= 2:
        q1, median, q3 = statistics.quantiles(values, n=4)
        print(
            f"[DATA] Impacts à {CONCLUSION_WINDOW} parties, {len(values)} joueurs éclairés : "
            f"Q1 {q1:.1f}, médiane {median:.1f}, Q3 {q3:.1f}"
        )
    else:
        print("[INFO] Moins de deux joueurs éclairés : pas de quartiles.")


def main() -> None:
    """Point d'entrée : refus propre si le client n'est pas prêt, sinon les paliers puis la conclusion."""
    args = _parse_args()
    schedule = [DRY_RUN_WORKERS] if args.dry_run else args.workers
    count = DRY_RUN_PLAYERS if args.dry_run else PLAYERS
    source = Path(config.DATABASE_PATH).with_name(winprob_config.CRAWL_DB_FILENAME)
    if not source.exists():
        print(f"[ERREUR] Pas de base de collecte : {source}")
        raise SystemExit(1)
    client = _connect()
    if client is None:
        raise SystemExit(1)
    if not _confirm(args.yes):
        print("[ERREUR] Banc annulé : confirme que le Live Coach est fermé (ou --yes).")
        raise SystemExit(1)

    print(HEADER)
    rows: List[Dict[str, Any]] = []
    baseline = None
    used: set = set()
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / winprob_config.CRAWL_DB_FILENAME
        shutil.copy2(source, copy)
        db = sqlite3.connect(copy)
        try:
            for workers in schedule:
                players = _pick(db, count, used)
                if len(players) < count:
                    print(
                        f"[ALERTE] Pas assez de joueurs jamais visités dans crawl.db "
                        f"({len(players)} sur {count}) : arrêt."
                    )
                    break
                used.update(players)
                roster = [
                    {"puuid": puuid, "champion_id": None, "team": 100 if i < 5 else 200}
                    for i, puuid in enumerate(players)
                ]
                print(f"[INFO] Palier {workers} workers, {count} joueurs")
                result = _palier(workers, roster, copy, client)
                result["breach"] = _breach(result, baseline)
                if workers == BASELINE_WORKERS:
                    baseline = result["p95"]
                rows.append(result)
                print(_row(result))
                if result["breach"]:
                    print(f"[ALERTE] Arrêt au palier {workers} : {result['breach']}")
                    break
        except sqlite3.OperationalError as error:
            print(f"[ERREUR] crawl.db illisible (collecte jamais lancée ?) : {error}")
            raise SystemExit(1) from error
        finally:
            db.close()
    _conclude(rows)


if __name__ == "__main__":
    main()
