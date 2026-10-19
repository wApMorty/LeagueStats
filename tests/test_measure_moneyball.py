"""Script de mesure Moneyball (SPEC-35 §4.4, tâche 174) : sorties, lecture seule, exclusion @pj35.

Hermétique : `crawl.db` et `db.db` temporaires (`tmp_path`), parties de la fixture spike
7998195590, modèle jouet de `tests/test_winprob_impact.py`. Aucune base réelle, aucun client LCU.
"""

import copy
import json
import random
import sqlite3
from pathlib import Path

from scripts import measure_moneyball as mmb
from src.config_constants import coaching_config
from src.winprob.crawl import SCHEMA, _utc, pack
from tests.test_winprob_impact import _model

FIXTURES = Path(__file__).parent / "fixtures" / "spike_gameplay"
GAME = json.loads((FIXTURES / "7998195590_game.json").read_text(encoding="utf-8"))
TIMELINE = json.loads((FIXTURES / "7998195590_timeline.json").read_text(encoding="utf-8"))
PJ35_PUUID = "pj35-puuid"  # absent des parties du crawl, sauf celle qu'on exclut
PJ35_PID = 1
MINUTE_MS = 60_000


def _crawl_game(i: int, puuid_of_pid_one: str = "") -> dict:
    """Copie de la fixture : `gameId` distinct, issue alternée, puuid du joueur 1 optionnel."""
    game = copy.deepcopy(GAME)
    game["gameId"] = GAME["gameId"] + i
    for team in game["teams"]:
        team["win"] = "Win" if (team["teamId"] == 100) == (i % 2 == 0) else "Fail"
    for identity in game["participantIdentities"]:
        if puuid_of_pid_one and identity["participantId"] == PJ35_PID:
            identity["player"]["puuid"] = puuid_of_pid_one
    return game


def _crawl_db(path: Path, games: list) -> None:
    """`crawl.db` au schéma de SCHEMA : une partie lue par élément, queue 420, chronologique."""
    db = sqlite3.connect(path)
    db.executescript(SCHEMA)
    for i, game in enumerate(games):
        db.execute(
            "INSERT INTO crawl_games (game_id, queue_id, game_creation_utc, depth, read_utc, raw) "
            "VALUES (?, 420, ?, 1, '2026-10-01 00:00:00', ?)",
            (game["gameId"], _utc(GAME["gameCreation"] + i * MINUTE_MS), pack(game, TIMELINE)),
        )
    db.commit()
    db.close()


def _game_db(path: Path, game_ids: list) -> None:
    """`db.db` avec `game_records` (SPEC-35 §1) : tes parties, participant `PJ35_PID`."""
    db = sqlite3.connect(path)
    db.execute(
        "CREATE TABLE game_records (game_id INTEGER PRIMARY KEY, queue_id INTEGER NOT NULL, "
        "game_creation_utc TEXT NOT NULL, duration_s INTEGER, player_participant_id INTEGER, "
        "raw_game TEXT NOT NULL, raw_timeline TEXT, raw_eog TEXT, captured_utc TEXT NOT NULL)"
    )
    for game_id in game_ids:
        mine = _crawl_game(game_id - GAME["gameId"], PJ35_PUUID)
        db.execute(
            "INSERT INTO game_records VALUES (?, 420, ?, 1488, ?, ?, ?, NULL, "
            "'2026-10-01 00:00:00')",
            (game_id, _utc(GAME["gameCreation"]), PJ35_PID, json.dumps(mine), json.dumps(TIMELINE)),
        )
    db.commit()
    db.close()


def _jittered(lane_rows):
    """`lane_rows` réel plus un bruit par partie (graine = gameId). Vingt copies identiques de la
    fixture donneraient des variables constantes, donc une hessienne singulière. Le bruit garde les
    variables mobiles ; le calcul de `lane_rows` reste celui du module."""

    def rows(game: dict, timeline: dict, minute: int) -> dict:
        rng = random.Random(game["gameId"])
        found = lane_rows(game, timeline, minute)
        return {
            role: {k: v + rng.gauss(0, 1) for k, v in values.items()}
            for role, values in found.items()
        }

    return rows


def _run(monkeypatch, capsys, crawl: Path, game_db: Path) -> str:
    """Lance `main()` sur ces bases avec le modèle jouet, rend la sortie console."""
    monkeypatch.setattr(
        "sys.argv",
        ["measure_moneyball.py", "--crawl-path", str(crawl), "--db-path", str(game_db)],
    )
    monkeypatch.setattr(mmb, "load_model", lambda: _model())
    monkeypatch.setattr(mmb, "lane_rows", _jittered(mmb.lane_rows))
    mmb.main()
    return capsys.readouterr().out


def test_mesure_complete_sur_base_de_test_sans_toucher_aux_bases(
    tmp_path, monkeypatch, capsys
) -> None:
    crawl, game_db = tmp_path / "crawl.db", tmp_path / "db.db"
    _crawl_db(crawl, [_crawl_game(i) for i in range(20)])
    _game_db(game_db, [GAME["gameId"] + 100 + i for i in range(3)])
    monkeypatch.setattr(coaching_config, "MONEYBALL_MIN_PLAYER_GAMES", 1)
    before = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in (crawl, game_db)}

    out = _run(monkeypatch, capsys, crawl, game_db)

    assert "20 parties lues (0 illisibles, 0 exclues" in out
    assert "20 retenues" in out
    mine = mmb.participant_roles(GAME)[PJ35_PID]  # le seul rôle où @pj35 a des parties
    for role in mmb.ROLES:
        assert f"[DATA] Valorisation {role} : 20 lignes" in out
        assert f"[DATA] Recoupement SPEC-20 {role} : death" in out
        assert f"[DATA] Vision hors classement {role} : " in out
    assert f"[DATA] Moneyball {mine} : 3 parties de @pj35" in out
    assert f"[DATA] Décision {mine} : " in out
    assert "  action | pts par unité | IC95 | signes sur les blocs" in out
    assert "  action | écart (IC95) | effet pts/unité" in out
    assert "[INFO] Biais : le modèle en place est entraîné sur ces mêmes parties." in out
    assert "[INFO] Hors classement" in out
    out.encode("cp1252")  # sortie redirigée sous Windows (CLAUDE.md)
    assert {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in (crawl, game_db)} == before


def test_partie_de_pj35_dans_le_crawl_est_exclue(tmp_path, monkeypatch, capsys) -> None:
    crawl, game_db = tmp_path / "crawl.db", tmp_path / "db.db"
    games = [_crawl_game(i) for i in range(20)] + [_crawl_game(20, PJ35_PUUID)]
    _crawl_db(crawl, games)
    _game_db(game_db, [GAME["gameId"] + 100])

    out = _run(monkeypatch, capsys, crawl, game_db)

    assert "21 parties lues (0 illisibles, 1 exclues (@pj35 y joue), 0 hors filtre)" in out
    assert "20 retenues" in out
