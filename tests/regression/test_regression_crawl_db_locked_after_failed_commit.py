"""Régression (2026-10-15) : `crawl.db` illisible jusqu'au redémarrage du Live Coach.

Symptôme : `scripts/measure_form_term.py` (lecture seule) répondait « database is locked » pendant plus
de dix minutes, `crawl.db-journal` figé, tant que le Live Coach restait ouvert.

Cause racine : une longue lecture extérieure faisait échouer un commit de la collecte ou de l'éclaireur.
L'exception était avalée (`Crawler._safely`, `Scout.step`) sans annuler la transaction : la connexion
gardait son verrou PENDING, et plus aucun lecteur, Live Coach compris, ne lisait la base.

Correctif : `Crawler.rollback()` annule la transaction du fil courant ; `_safely` et `Scout.step`
l'appellent sur toute exception.

Prévention : ces tests font échouer un vrai commit derrière un lecteur et vérifient que la base se relit.
"""

import sqlite3
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

from src.winprob.crawl import Crawler
from src.winprob.scout import Scout
from tests.test_winprob_scout import PUUIDS, Clock, FakeLCU, SyncExecutor, _history, _players

BUSY_MS = 50  # attente d'un verrou par la connexion du Live Coach : le test reste rapide


def _long_reader(path: Path):
    """Un lecteur au milieu d'un SELECT : il tient un verrou SHARED, comme un script de mesure."""
    reader = sqlite3.connect(path)
    reader.execute(
        "INSERT INTO crawl_frontier VALUES ('a', 1, 0, 'x', NULL), ('b', 1, 0, 'x', NULL)"
    )
    reader.commit()
    cursor = reader.execute("SELECT puuid FROM crawl_frontier")
    cursor.fetchone()
    return reader, cursor


def _readable(path: Path) -> bool:
    db = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True, timeout=BUSY_MS / 1000)
    try:
        db.execute("SELECT COUNT(*) FROM crawl_frontier").fetchone()
        return True
    except sqlite3.OperationalError:
        return False
    finally:
        db.close()


def test_failed_commit_of_the_crawler_releases_the_database(tmp_path: Path):
    path = tmp_path / "crawl.db"
    crawler = Crawler(Mock(verbose=False), path=path)
    conn = crawler._db()
    conn.execute(f"PRAGMA busy_timeout = {BUSY_MS}")
    reader, cursor = _long_reader(path)

    def write():
        conn.execute("UPDATE crawl_frontier SET visited_utc = 'now'")
        conn.commit()  # échoue : le lecteur tient la base

    crawler._safely(write)
    cursor.close()
    reader.close()

    assert _readable(path)


def test_failed_commit_of_the_scout_releases_the_database(tmp_path: Path):
    path = tmp_path / "crawl.db"
    clock = Clock()
    monitor = SimpleNamespace(lcu=SimpleNamespace(credentials=None), bus=None)
    crawler = Crawler(monitor, path=path, clock=clock)
    crawler._db().execute(f"PRAGMA busy_timeout = {BUSY_MS}")
    lcu = FakeLCU()
    lcu.histories = {PUUIDS[0]: _history(1, 2)}
    scout = Scout(monitor, crawler, executor=SyncExecutor(), clock=clock, fetch=lambda: None)
    scout.lcu = lcu
    monitor.scout = scout
    scout.start(_players(PUUIDS[:1]))
    scout.step()  # soumet l'historique
    reader, cursor = _long_reader(path)

    scout.step()  # range l'historique : le commit échoue
    cursor.close()
    reader.close()

    assert _readable(path)
