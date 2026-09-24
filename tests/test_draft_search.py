"""Tests de src/draft/search.py (SPEC-12).

Le test qui porte toute la feature est
``TestCounterpickTrap::test_depth_two_avoids_what_depth_one_walks_into`` : à
profondeur 1 le moteur choisit le pick le plus fort dans l'instant, à
profondeur 2 il voit la réponse adverse et change d'avis. C'est exactement ce
que le classement par delta ne pouvait pas faire.
"""

import pytest

from src.analysis.game_eval import GameEvaluator
from src.draft.search import CandidatePool, DraftSearch, PickTurn

GAMES = 10_000


class FakeDB:
    """Tables de paires et popularité par lane, sans SQL."""

    def __init__(self, matchups, popularity_by_lane):
        self.matchups = matchups
        self.popularity_by_lane = popularity_by_lane

    def get_all_matchups_bulk(self, lane=None, with_games=False):
        return self.matchups

    def get_all_synergies_bulk(self, lane=None, with_games=False):
        return {}

    def get_meta(self, key):
        """SPEC-13 : lu par GameEvaluator pour le shrink mesuré. Vide ici, donc
        repli sur CONFIDENCE_K — la recherche est testée sur son classement,
        qu'un changement de shrink ne doit pas bouleverser."""
        return None

    def get_lane_popularity(self, lane):
        """Du plus joué au moins joué, comme MatchupsRepository."""
        return self.popularity_by_lane.get(lane, [])


# Greedy écrase le jungler ennemi déjà pické, mais Punisher (encore
# disponible en top) le détruit. Safe est tiède partout, et sans réponse.
TRAP_MATCHUPS = {
    ("greedy", "jungler"): (10.0, GAMES),
    ("safe", "jungler"): (2.0, GAMES),
    ("punisher", "greedy"): (40.0, GAMES),
    ("punisher", "safe"): (0.0, GAMES),
    ("filler", "greedy"): (0.0, GAMES),
    ("filler", "safe"): (0.0, GAMES),
}

TRAP_POPULARITY = {
    "top": ["Punisher", "Filler"],
    "jungle": [],
    "middle": [],
    "bottom": [],
    "support": [],
}


@pytest.fixture
def search():
    db = FakeDB(TRAP_MATCHUPS, TRAP_POPULARITY)
    return DraftSearch(GameEvaluator(db), CandidatePool(db, top_n=8))


OUR_TURN = PickTurn(is_ally=True, is_local_player=True)
THEIR_TURN = PickTurn(is_ally=False)
POOL = ["Greedy", "Safe"]
ENEMIES = [("Jungler", "jungle")]


class TestCounterpickTrap:
    def test_depth_one_takes_the_greedy_pick(self, search):
        """Sans lookahead, Greedy gagne : +10 contre le jungler ennemi."""
        results = search.rank(
            allies=[],
            enemies=ENEMIES,
            pool=POOL,
            remaining_turns=[OUR_TURN],
            player_lane="top",
        )
        assert [r.champion for r in results] == ["Greedy", "Safe"]

    def test_depth_two_avoids_what_depth_one_walks_into(self, search):
        """Avec la réponse adverse, Greedy devient le pire choix."""
        results = search.rank(
            allies=[],
            enemies=ENEMIES,
            pool=POOL,
            remaining_turns=[OUR_TURN, THEIR_TURN],
            player_lane="top",
        )

        assert results[0].champion == "Safe"
        assert results[0].win_probability > 0.5
        # Et le moteur nomme la punition qu'il a vue venir.
        greedy = next(r for r in results if r.champion == "Greedy")
        assert greedy.win_probability < 0.5
        assert greedy.principal_variation[0][0] == "Punisher"

    def test_principal_variation_reports_the_expected_answer(self, search):
        results = search.rank(
            allies=[],
            enemies=ENEMIES,
            pool=POOL,
            remaining_turns=[OUR_TURN, THEIR_TURN],
            player_lane="top",
        )
        best = results[0]
        assert best.depth == 2
        assert len(best.principal_variation) == 1
        # Contre Safe, Punisher n'apporte rien : l'adversaire prend le meilleur
        # champion de sa lane libre, pas le contre-pick devenu inutile.
        assert best.principal_variation[0][1] == "top"


class TestMoveGeneration:
    def test_banned_and_picked_champions_never_appear(self, search):
        results = search.rank(
            allies=[],
            enemies=ENEMIES,
            pool=POOL,
            remaining_turns=[OUR_TURN],
            banned=["Greedy"],
            player_lane="top",
        )
        assert [r.champion for r in results] == ["Safe"]

    def test_our_pick_stays_in_our_pool(self, search):
        results = search.rank(
            allies=[],
            enemies=ENEMIES,
            pool=POOL,
            remaining_turns=[OUR_TURN, THEIR_TURN],
            player_lane="top",
        )
        assert {r.champion for r in results} == set(POOL)

    def test_enemy_cannot_repick_a_champion_we_took(self, search):
        """Le champion choisi à la racine sort du pool adverse dans la branche."""
        db = FakeDB(
            {("mirror", "jungler"): (5.0, GAMES)},
            {
                "top": ["Mirror", "Filler"],
                "jungle": [],
                "middle": [],
                "bottom": [],
                "support": [],
            },
        )
        engine = DraftSearch(GameEvaluator(db), CandidatePool(db, top_n=8))

        results = engine.rank(
            allies=[],
            enemies=ENEMIES,
            pool=["Mirror"],
            remaining_turns=[OUR_TURN, THEIR_TURN],
            player_lane="top",
        )
        assert results[0].principal_variation[0][0] == "Filler"

    def test_empty_pool_returns_nothing(self, search):
        assert (
            search.rank(
                allies=[],
                enemies=ENEMIES,
                pool=[],
                remaining_turns=[OUR_TURN],
                player_lane="top",
            )
            == []
        )

    def test_no_remaining_turn_returns_nothing(self, search):
        assert search.rank(allies=[], enemies=ENEMIES, pool=POOL, remaining_turns=[]) == []


class TestBudget:
    def test_exhausted_budget_still_answers(self, search):
        """Budget nul : l'approfondissement itératif rend la profondeur 1, pas
        une exception et pas une liste vide."""
        results = search.rank(
            allies=[],
            enemies=ENEMIES,
            pool=POOL,
            remaining_turns=[OUR_TURN, THEIR_TURN, OUR_TURN],
            player_lane="top",
            budget_seconds=0.0,
        )
        assert results
        assert results[0].depth == 1

    def test_budget_is_respected(self, search):
        """Un pool large ne doit pas faire exploser la latence."""
        import time

        wide_pool = [f"Champ{i}" for i in range(40)]
        started = time.monotonic()
        search.rank(
            allies=[],
            enemies=ENEMIES,
            pool=wide_pool,
            remaining_turns=[OUR_TURN, THEIR_TURN] * 5,
            player_lane="top",
            budget_seconds=0.5,
        )
        # Marge large : on vérifie qu'il y a bien une coupure, pas sa précision.
        assert time.monotonic() - started < 3.0

    def test_deeper_search_keeps_every_candidate_ranked(self, search):
        results = search.rank(
            allies=[],
            enemies=ENEMIES,
            pool=POOL,
            remaining_turns=[OUR_TURN, THEIR_TURN],
            player_lane="top",
        )
        assert len(results) == len(POOL)
        assert results == sorted(results, key=lambda r: -r.win_probability)


class TestCandidatePool:
    """SPEC-17 §4.1 : les candidats sont les champions joués, pas les plus forts."""

    def test_candidates_follow_popularity_order(self):
        db = FakeDB({}, {"top": ["Popular", "Common", "Rare"]})
        assert CandidatePool(db, top_n=2).best("top", set()) == ["Popular", "Common"]

    def test_taken_champions_let_the_next_most_played_in(self):
        db = FakeDB({}, {"top": ["Popular", "Common", "Rare"]})
        assert CandidatePool(db, top_n=2).best("top", {"popular"}) == ["Common", "Rare"]

    def test_strong_but_unplayed_champion_is_never_examined(self):
        """Le cas Kassadin top : écrasant sur le papier, mais hors du top-N joué,
        il ne doit pas devenir la « meilleure réponse adverse »."""
        db = FakeDB(
            {("kassadin", "safe"): (40.0, GAMES), ("common", "safe"): (1.0, GAMES)},
            {"top": ["Common", "Kassadin"]},
        )
        engine = DraftSearch(GameEvaluator(db), CandidatePool(db, top_n=1))

        results = engine.rank(
            allies=[],
            enemies=[],
            pool=["Safe"],
            remaining_turns=[OUR_TURN, THEIR_TURN],
            player_lane="top",
        )
        assert results[0].principal_variation[0][0] == "Common"
