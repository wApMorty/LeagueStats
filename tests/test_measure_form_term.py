"""Mesure du terme de forme (SPEC-33 §4.6, tâche 159) : forme avant la partie, couverture, décision.

Hermétique : `crawl.db` temporaire au schéma de `src.winprob.crawl.SCHEMA`, aucune partie décompressée.
"""

import sqlite3

import pytest

from scripts import measure_form_term as mft
from src.config_winprob import winprob_config as cfg
from src.winprob.crawl import SCHEMA


def _history(day: int, game_id: int, win: int, kills: int, deaths: int, assists: int) -> tuple:
    return (f"2026-09-{day:02d} 12:00:00", game_id, win, kills, deaths, assists)


def _crawl_db(path) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.executescript(SCHEMA)
    return db


def _add_game(db: sqlite3.Connection, game_id: int, creation: str, players: int) -> None:
    """Une partie lue, vue dans l'historique de `players` joueurs qui ont chacun 3 parties avant."""
    db.execute(
        "INSERT INTO crawl_games (game_id, game_creation_utc, depth, read_utc, raw) "
        "VALUES (?, ?, 1, '2026-10-01 00:00:00', x'00')",
        (game_id, creation),
    )
    for i in range(players):
        puuid = f"p{i}"
        rows = [
            (puuid, 100 + j, f"2026-09-0{j + 1} 12:00:00", 420, 1, 1, 0, 0, 0, 0, 1800)
            for j in range(3)
        ]
        rows.append((puuid, game_id, creation, 420, 1, 1, 0, 0, 0, 0, 1800))
        db.executemany("INSERT OR IGNORE INTO crawl_histories VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
    db.commit()


def test_prior_form_exclut_la_partie_et_les_posterieures() -> None:
    rows = [_history(d, 100 + d, 1 if d >= 3 else 0, 2, 1, 3) for d in range(1, 13)]
    rows.append(_history(20, 999, 0, 0, 9, 0))  # la partie elle-même : jamais dans sa forme
    rows.append(_history(25, 1000, 1, 9, 0, 9))  # postérieure : jamais dans sa forme
    form = mft.prior_form(rows, "2026-09-20 12:00:00", 999, cfg.SCOUT_BADGE_WINDOW, 3)
    # Fenêtre de 10 : les 10 parties du 3 au 12 septembre, toutes gagnées, KDA (2+3)/1.
    assert form == (1.0, 5.0)


def test_prior_form_sous_le_minimum_donne_none() -> None:
    rows = [_history(d, 100 + d, 1, 1, 1, 1) for d in range(1, 5)]
    assert mft.prior_form(rows, "2026-09-20 12:00:00", 999, 10, 5) is None
    assert mft.prior_form(rows, "2026-09-20 12:00:00", 999, 10, 3) is not None


def test_covered_games_compte_une_partie_a_dix_joueurs_pas_une_a_neuf(tmp_path) -> None:
    db = _crawl_db(tmp_path / "crawl.db")
    _add_game(db, 5001, "2026-10-01 12:00:00", players=10)
    _add_game(db, 5002, "2026-10-02 12:00:00", players=9)
    assert mft.covered_games(db, 10, cfg.SCOUT_MIN_IMPACT_GAMES) == 1
    assert mft.covered_games(db, 9, cfg.SCOUT_MIN_IMPACT_GAMES) == 2
    assert mft.covered_games(db, 10, 4) == 0  # trois parties antérieures seulement
    db.close()


def test_decide_seuils_de_gain_et_d_ecart() -> None:
    base = {"brier_early": 0.250, "max_gap": 0.03}
    assert (
        mft.decide(base, {"brier_early": 0.248, "max_gap": 0.05}) is True
    )  # gain 0,002, écart 5 pts
    assert mft.decide(base, {"brier_early": 0.2481, "max_gap": 0.03}) is False  # gain 0,0019
    assert mft.decide(base, {"brier_early": 0.240, "max_gap": 0.051}) is False  # écart 5,1 pts


def test_script_sans_force_sur_base_peu_couverte_attend(tmp_path, monkeypatch, capsys) -> None:
    path = tmp_path / "crawl.db"
    _crawl_db(path).close()
    monkeypatch.setattr("sys.argv", ["measure_form_term.py", "--db-path", str(path)])
    mft.main()  # sort avec 0 : pas de SystemExit
    out = capsys.readouterr().out
    assert "[INFO] Mesure en attente : couverture 0 / 5000" in out
    assert "[DATA] Couverture" in out


def test_script_sans_modele_sort_en_erreur(tmp_path, monkeypatch, capsys) -> None:
    path = tmp_path / "crawl.db"
    db = _crawl_db(path)
    _add_game(db, 5001, "2026-10-01 12:00:00", players=10)
    db.close()
    monkeypatch.setattr("sys.argv", ["measure_form_term.py", "--db-path", str(path)])
    monkeypatch.setattr(mft, "load_model", lambda: None)
    monkeypatch.setattr(cfg, "FORM_MIN_COVERED_GAMES", 1)  # une partie couverte suffit
    with pytest.raises(SystemExit) as exc:
        mft.main()
    assert exc.value.code == 1
    assert "[ERREUR] Pas de modèle de win chance" in capsys.readouterr().out
