"""Régression (2026-10-11) : la purge du plafond de `crawl.db` parcourait les 33 000 lignes (blobs de
100 Ko) en lecture aléatoire pour filtrer `raw IS NOT NULL`. À froid, elle bloquait la boucle du
Live Coach plus de deux minutes (au démarrage, à chaque fin de partie, toutes les 500 lectures), et la
draft restait invisible.

Le sous-select du plafond doit parcourir l'index partiel des parties stockées (`crawl_games_stored`,
rowid seul, aucune ligne lue), pas `crawl_games_created` qui lit chaque ligne pour filtrer `raw`.
"""

from pathlib import Path
from unittest.mock import Mock

from src.winprob.crawl import Crawler


def test_cap_purge_scans_the_stored_games_index(tmp_path: Path):
    crawler = Crawler(Mock(), path=tmp_path / "crawl.db")
    conn = crawler._db()
    statements = []
    conn.set_trace_callback(statements.append)

    crawler._purge()

    cap = next(s for s in statements if "OFFSET" in s)
    plan = " ".join(row[3] for row in conn.execute(f"EXPLAIN QUERY PLAN {cap}"))
    assert "USING INDEX crawl_games_stored" in plan, plan
