"""RÉGRESSION : les lectures bulk et unitaires doivent donner la même valeur.

Bug (constat M2 de docs/archive/AUDIT_2026_08.md, corrigé par SPEC-03 / B1)
------------------------------------------------------------------
`get_matchup_delta2()` faisait la moyenne pondérée par `games` des lignes
multi-lane, tandis que `get_all_matchups_bulk()` écrasait silencieusement les
lignes précédentes (`cache[(champ, enemy)] = delta2`) : la survivante dépendait
de l'ordre de parcours SQL. Sur la base réelle, 26 398 lignes ne produisaient
que 15 699 entrées de cache — 10 699 valeurs jetées. Le même matchup pouvait
donc être noté différemment selon le chemin de code emprunté (trio holistique
et cache d'`Assistant` d'un côté, scoring unitaire de l'autre).

Même divergence côté synergies : `get_synergy_delta2()` utilisait `fetchone()`.

Ce test est le garde-fou central de B1 : pour **toute** paire d'une base à trois
lanes, la valeur unitaire et la valeur bulk doivent coïncider.

Créé : 2026-08-31 — SPEC-03 / B1
"""

import sqlite3

import pytest

from src.db import Database

# (champion, peer, lane, delta2, pickrate, games)
# Chaque paire existe sur plusieurs lanes, avec des delta2 franchement écartés
# pour que l'écrasement se voie immédiatement s'il revient.
_MATCHUP_ROWS = [
    ("Pantheon", "Yasuo", "top", 12.0, 3.0, 900),
    ("Pantheon", "Yasuo", "middle", -4.0, 2.0, 400),
    ("Pantheon", "Yasuo", "support", -8.0, 1.5, 250),
    ("Pantheon", "Darius", "top", 5.0, 4.0, 1500),
    ("Pantheon", "Darius", "support", -6.0, 1.0, 300),
    ("Yasuo", "Pantheon", "middle", -3.0, 2.5, 700),
    ("Yasuo", "Pantheon", "top", 1.0, 1.0, 500),
    ("Darius", "Pantheon", "top", 2.5, 5.0, 2000),
]

_SYNERGY_ROWS = [
    ("Pantheon", "Yasuo", "top", 20.0, 3.0, 800),
    ("Pantheon", "Yasuo", "middle", -5.0, 2.0, 400),
    ("Pantheon", "Yasuo", "support", 10.0, 1.0, 600),
    ("Pantheon", "Darius", "top", 7.0, 2.0, 1000),
    ("Yasuo", "Darius", "middle", -2.0, 1.0, 250),
]


@pytest.fixture
def db_three_lanes(tmp_path):
    """Base temporaire : 3 champions, matchups et synergies sur 3 lanes."""
    db_path = tmp_path / "bulk_vs_unitaire.db"
    conn = sqlite3.connect(str(db_path))
    cursor = conn.cursor()
    cursor.execute(
        "CREATE TABLE champions (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL)"
    )
    for table, peer in (("matchups", "enemy"), ("synergies", "ally")):
        cursor.execute(f"""
            CREATE TABLE {table} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                champion INTEGER NOT NULL,
                {peer} INTEGER NOT NULL,
                winrate REAL NOT NULL,
                delta1 REAL NOT NULL,
                delta2 REAL NOT NULL,
                pickrate REAL NOT NULL,
                games INTEGER NOT NULL,
                lane TEXT
            )
            """)

    names = ["Pantheon", "Yasuo", "Darius"]
    cursor.executemany("INSERT INTO champions (name) VALUES (?)", [(n,) for n in names])
    ids = {name: index + 1 for index, name in enumerate(names)}

    for table, peer, rows in (
        ("matchups", "enemy", _MATCHUP_ROWS),
        ("synergies", "ally", _SYNERGY_ROWS),
    ):
        cursor.executemany(
            f"INSERT INTO {table} (champion, {peer}, winrate, delta1, delta2, pickrate, games, lane)"
            " VALUES (?, ?, 50.0, 0.0, ?, ?, ?, ?)",
            [
                (ids[champ], ids[other], delta2, pickrate, games, lane)
                for champ, other, lane, delta2, pickrate, games in rows
            ],
        )
    conn.commit()
    conn.close()

    database = Database(str(db_path))
    database.connect()
    yield database
    database.close()


def _weighted(rows, champion, peer):
    """Moyenne pondérée attendue, calculée indépendamment du code de prod."""
    selected = [r for r in rows if r[0] == champion and r[1] == peer]
    total_games = sum(r[5] for r in selected)
    return sum(r[3] * r[5] for r in selected) / total_games


class TestBulkMatchesUnitaire:
    """Le test central de B1 : bulk == unitaire, pour toutes les paires."""

    def test_every_matchup_pair_matches(self, db_three_lanes):
        bulk = db_three_lanes.get_all_matchups_bulk()
        pairs = {(champ, peer) for champ, peer, *_ in _MATCHUP_ROWS}

        assert len(bulk) == len(pairs), "une entrée de cache par paire, pas par lane"
        for champion, peer in pairs:
            unitaire = db_three_lanes.get_matchup_delta2(champion, peer)
            assert unitaire == pytest.approx(
                bulk[(champion.lower(), peer.lower())]
            ), f"divergence bulk/unitaire pour {champion} vs {peer}"

    def test_every_synergy_pair_matches(self, db_three_lanes):
        bulk = db_three_lanes.get_all_synergies_bulk()
        pairs = {(champ, peer) for champ, peer, *_ in _SYNERGY_ROWS}

        assert len(bulk) == len(pairs)
        for champion, peer in pairs:
            unitaire = db_three_lanes.get_synergy_delta2(champion, peer)
            assert unitaire == pytest.approx(
                bulk[(champion.lower(), peer.lower())]
            ), f"divergence bulk/unitaire pour {champion} + {peer}"


class TestAggregatedValueIsWeighted:
    """La valeur commune est bien la moyenne pondérée, pas une lane au hasard."""

    def test_matchup_value_is_games_weighted(self, db_three_lanes):
        expected = _weighted(_MATCHUP_ROWS, "Pantheon", "Yasuo")
        # (12*900 - 4*400 - 8*250) / 1550 ~= 4.39, valeur d'aucune ligne
        assert expected not in (12.0, -4.0, -8.0)

        assert db_three_lanes.get_matchup_delta2("Pantheon", "Yasuo") == pytest.approx(expected)
        assert db_three_lanes.get_all_matchups_bulk()[("pantheon", "yasuo")] == pytest.approx(
            expected
        )

    def test_synergy_value_is_games_weighted(self, db_three_lanes):
        expected = _weighted(_SYNERGY_ROWS, "Pantheon", "Yasuo")

        assert db_three_lanes.get_synergy_delta2("Pantheon", "Yasuo") == pytest.approx(expected)
        assert db_three_lanes.get_all_synergies_bulk()[("pantheon", "yasuo")] == pytest.approx(
            expected
        )

    def test_direction_is_not_collapsed(self, db_three_lanes):
        """(A vs B) et (B vs A) restent deux entrées distinctes."""
        bulk = db_three_lanes.get_all_matchups_bulk()

        assert bulk[("pantheon", "yasuo")] != pytest.approx(bulk[("yasuo", "pantheon")])


class TestAccessorsAggregateToo:
    """Les accesseurs par champion renvoient une entrée par adversaire distinct."""

    def test_matchups_by_name_has_one_entry_per_enemy(self, db_three_lanes):
        matchups = db_three_lanes.get_champion_matchups_by_name("Pantheon")

        assert len(matchups) == 2  # Yasuo et Darius, malgré 5 lignes en base
        by_enemy = {m.enemy_name: m for m in matchups}
        assert by_enemy["Yasuo"].games == 900 + 400 + 250  # games sommés
        assert by_enemy["Yasuo"].pickrate == pytest.approx(3.0 + 2.0 + 1.5)  # pickrate sommé
        assert by_enemy["Yasuo"].delta2 == pytest.approx(
            _weighted(_MATCHUP_ROWS, "Pantheon", "Yasuo")
        )

    def test_matchups_for_draft_has_one_entry_per_enemy(self, db_three_lanes):
        matchups = db_three_lanes.get_champion_matchups_for_draft("Pantheon")

        assert len(matchups) == 2
        assert {m.enemy_name for m in matchups} == {"Yasuo", "Darius"}

    def test_reverse_matchups_has_one_entry_per_picker(self, db_three_lanes):
        """Pantheon est attaqué par Yasuo (2 lanes) et Darius (1 lane)."""
        reverse = db_three_lanes.get_reverse_matchups_for_draft("Pantheon")

        assert len(reverse) == 2
        by_picker = {m.enemy_name: m for m in reverse}
        assert by_picker["Yasuo"].games == 700 + 500
        assert by_picker["Yasuo"].delta2 == pytest.approx(
            _weighted(_MATCHUP_ROWS, "Yasuo", "Pantheon")
        )

    def test_synergies_by_name_has_one_entry_per_ally(self, db_three_lanes):
        synergies = db_three_lanes.get_champion_synergies_by_name("Pantheon")

        assert len(synergies) == 2  # Yasuo et Darius, malgré 4 lignes en base
        by_ally = {s.ally_name: s for s in synergies}
        assert by_ally["Yasuo"].games == 800 + 400 + 600
        assert by_ally["Yasuo"].delta2 == pytest.approx(
            _weighted(_SYNERGY_ROWS, "Pantheon", "Yasuo")
        )

    def test_tuple_shape_is_preserved(self, db_three_lanes):
        """L'agrégation change les valeurs, jamais la forme des retours."""
        assert all(
            len(row) == 6
            for row in db_three_lanes.get_champion_matchups_by_name("Pantheon", as_dataclass=False)
        )
        assert all(
            len(row) == 4
            for row in db_three_lanes.get_champion_matchups_for_draft(
                "Pantheon", as_dataclass=False
            )
        )
