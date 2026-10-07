"""Régression SPEC-20 : la boucle du Live Coach restait coincée dans la collecte et manquait les drafts.

Symptôme : seule la première draft d'une session était vue ; après une partie, la file trouvée n'était
plus acceptée ni le champ select ouvert (`py-spy` : la boucle sur la requête de travail du crawler, 30
relevés sur 30).

Cause racine : `crawl.db` (558 Mo, 35 000 parties à blobs) n'avait aucun index. Chaque `step()` balayait
la table pour trouver la prochaine partie à lire, et `seed()` (rappelé toutes les 5 s pendant les 10 min
d'après-partie) relançait une purge complète à chaque passage, même sans partie neuve. À froid, un
balayage prenait des dizaines de secondes de boucle.

Correctif : index partiels sur le travail à faire (`raw IS NULL`, `visited_utc IS NULL`), index sur
`read_utc` (qui remplace `length(raw) > 0` dans les comptes), et `seed()` ne purge que s'il a amorcé
une partie neuve.

Prévention : ce test exige que les requêtes de la boucle passent par un index et qu'un second `seed()`
sans partie neuve ne purge pas.
"""

from unittest.mock import patch

from tests.test_winprob_crawl import _capture_own_game, clock, crawler, lcu  # noqa: F401
from tests.conftest import db  # noqa: F401

LOOP_QUERIES = [
    "SELECT game_id, depth FROM crawl_games WHERE raw IS NULL "
    "ORDER BY depth, game_creation_utc DESC LIMIT 1",
    "SELECT puuid, depth FROM crawl_frontier WHERE visited_utc IS NULL "
    "ORDER BY depth, priority DESC LIMIT 1",
    "SELECT COUNT(*) FROM crawl_games WHERE read_utc IS NOT NULL",
    "SELECT COUNT(*) FROM crawl_games WHERE raw IS NULL",
]


def test_les_requetes_de_la_boucle_passent_par_un_index(crawler):  # noqa: F811
    conn = crawler._db()
    for query in LOOP_QUERIES:
        for row in conn.execute("EXPLAIN QUERY PLAN " + query):
            assert not row[3].startswith("SCAN") or "INDEX" in row[3], (query, row[3])


def test_seed_sans_partie_neuve_ne_purge_pas(crawler, db):  # noqa: F811
    _capture_own_game(db)
    with patch.object(crawler, "_purge", wraps=crawler._purge) as purge:
        crawler.seed()
        crawler.seed()
        crawler.seed()
    assert purge.call_count == 1
