"""Tests de src/draft/search.py (SPEC-12, SPEC-48).

Le test qui porte toute la feature est
``TestCounterpickTrap::test_anticiper_evite_le_piege`` : sans anticipation le moteur
choisit le pick le plus fort dans l'instant, avec elle il voit la réponse du vis-à-vis
et change d'avis.
"""

import pytest

from src.analysis.game_eval import GameEvaluator
from src.analysis.mastery import to_win_points
from src.analysis.strategy import Strategy, WeightedEvaluator
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

    def get_lane_winrates(self, lane):
        """SPEC-43 : aucune force intrinsèque, le classement est testé sur les seuls matchups."""
        return {}

    def get_meta(self, key):
        """SPEC-13 : lu par GameEvaluator pour le shrink mesuré. Vide ici, donc
        repli sur CONFIDENCE_K — le classement testé ne doit pas dépendre d'un
        changement de shrink."""
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


def _rank(engine, turns=(OUR_TURN, THEIR_TURN), enemies=ENEMIES, pool=POOL, **kwargs):
    kwargs.setdefault("player_lane", "top")
    kwargs.setdefault("anticipate", True)
    return engine.rank(allies=[], enemies=enemies, pool=pool, remaining_turns=list(turns), **kwargs)


class TestCounterpickTrap:
    def test_sans_anticipation_greedy_gagne(self, search):
        """Calcul immédiat : Greedy gagne, +10 contre le jungler ennemi, et rien d'anticipé."""
        results = _rank(search, anticipate=False)
        assert [r.champion for r in results] == ["Greedy", "Safe"]
        assert all(r.reply is None for r in results)

    def test_sans_anticipation_la_valeur_est_la_position_immediate(self, search):
        evaluator = search.evaluator
        result = next(r for r in _rank(search, anticipate=False) if r.champion == "Greedy")
        expected = evaluator.win_probability([("Greedy", "top")], ENEMIES)
        assert result.win_probability == pytest.approx(expected)

    def test_anticiper_evite_le_piege(self, search):
        """Avec la réponse du vis-à-vis, Greedy devient le pire choix."""
        results = _rank(search)

        assert results[0].champion == "Safe"
        assert results[0].win_probability > 0.5
        greedy = next(r for r in results if r.champion == "Greedy")
        assert greedy.win_probability < 0.5
        assert greedy.reply == ("Punisher", "top")

    def test_la_valeur_compte_la_reponse(self, search):
        evaluator = search.evaluator
        greedy = next(r for r in _rank(search) if r.champion == "Greedy")
        expected = evaluator.win_probability([("Greedy", "top")], ENEMIES + [("Punisher", "top")])
        assert greedy.win_probability == pytest.approx(expected)

    def test_chaque_candidat_est_classe(self, search):
        results = _rank(search)
        assert len(results) == len(POOL)
        assert results == sorted(results, key=lambda r: -r.win_probability)

    def test_la_pire_reponse_gagne_meme_loin_dans_la_popularite(self):
        """Le vis-à-vis prend le pire pour moi, pas le plus joué."""
        popularity = {**TRAP_POPULARITY, "top": ["Filler", "Punisher"]}
        db = FakeDB(TRAP_MATCHUPS, popularity)
        engine = DraftSearch(GameEvaluator(db), CandidatePool(db, top_n=8))

        greedy = next(r for r in _rank(engine) if r.champion == "Greedy")

        assert greedy.reply == ("Punisher", "top")

    def test_le_terme_personnel_ne_porte_que_sur_mon_pick(self, search):
        term = 0.2
        greedy = next(r for r in _rank(search, personal=lambda _: term) if r.champion == "Greedy")
        logit = search.evaluator.team_logit([("Greedy", "top")], ENEMIES + [("Punisher", "top")])
        assert greedy.win_probability == pytest.approx(search.evaluator.probability(logit + term))
        assert greedy.reply == ("Punisher", "top")

    def test_win_lane_change_de_numero_un_en_anticipant(self):
        """SPEC-48 critère 5 : sous les poids réels de WIN LANE, le classement diffère de l'immédiat."""
        db = FakeDB(TRAP_MATCHUPS, TRAP_POPULARITY)
        win_lane = Strategy("WIN LANE", 1.0, 3.0, 0.25, 0.0, 0.0, search=True)
        engine = DraftSearch(
            WeightedEvaluator(GameEvaluator(db), win_lane), CandidatePool(db, top_n=8)
        )

        assert _rank(engine, anticipate=False)[0].champion == "Greedy"
        assert _rank(engine)[0].champion == "Safe"


class TestWhenToAnticipate:
    """SPEC-48 §2 : stratégie à anticipation, poste connu, vis-à-vis non vu, tour ennemi à venir."""

    def test_pas_de_reponse_sans_lane(self, search):
        """Mes cinq postes sont pris et aucun poste assigné : je n'ai pas de vis-à-vis à anticiper."""
        allies = [
            ("A", "top"),
            ("B", "jungle"),
            ("C", "middle"),
            ("D", "bottom"),
            ("E", "support"),
        ]
        results = search.rank(
            allies=allies,
            enemies=ENEMIES,
            pool=POOL,
            remaining_turns=[OUR_TURN, THEIR_TURN],
            anticipate=True,
        )
        assert [r.lane for r in results] == [None, None]
        assert all(r.reply is None for r in results)

    def test_pas_de_reponse_si_le_vis_a_vis_est_vu(self, search):
        results = _rank(search, enemies=ENEMIES + [("Filler", "top")])
        assert all(r.reply is None for r in results)

    def test_un_ennemi_sans_lane_ne_compte_pas_comme_vu(self, search):
        results = _rank(search, enemies=ENEMIES + [("Filler", None)])
        assert any(r.reply is not None for r in results)

    def test_pas_de_reponse_sans_tour_ennemi_restant(self, search):
        results = _rank(search, turns=[OUR_TURN, PickTurn(is_ally=True)])
        assert all(r.reply is None for r in results)

    def test_un_tour_ennemi_derriere_un_allie_compte(self, search):
        results = _rank(search, turns=[OUR_TURN, PickTurn(is_ally=True), THEIR_TURN])
        assert all(r.reply is not None for r in results)

    def test_pas_de_reponse_sans_candidat(self):
        db = FakeDB(TRAP_MATCHUPS, {})
        engine = DraftSearch(GameEvaluator(db), CandidatePool(db, top_n=8))
        results = _rank(engine)
        assert all(r.reply is None for r in results)
        assert [r.champion for r in results] == ["Greedy", "Safe"]

    def test_sans_poste_connu_la_premiere_lane_libre_sert(self, search):
        results = _rank(search, player_lane=None)
        assert {r.lane for r in results} == {"top"}
        assert all(r.reply is not None for r in results)


class TestCandidates:
    def test_banned_and_picked_champions_never_appear(self, search):
        results = _rank(search, banned=["Greedy"], anticipate=False)
        assert [r.champion for r in results] == ["Safe"]

    def test_un_champion_banni_ne_repond_pas(self, search):
        greedy = next(r for r in _rank(search, banned=["Punisher"]) if r.champion == "Greedy")
        assert greedy.reply == ("Filler", "top")

    def test_un_champion_pris_ne_repond_pas(self, search):
        enemies = ENEMIES + [("Punisher", "middle")]
        greedy = next(r for r in _rank(search, enemies=enemies) if r.champion == "Greedy")
        assert greedy.reply == ("Filler", "top")

    def test_enemy_cannot_repick_a_champion_we_took(self):
        """Le candidat sort des réponses possibles."""
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

        assert _rank(engine, pool=["Mirror"])[0].reply == ("Filler", "top")

    def test_empty_pool_returns_nothing(self, search):
        assert _rank(search, pool=[]) == []

    def test_no_remaining_turn_returns_nothing(self, search):
        assert search.rank(allies=[], enemies=ENEMIES, pool=POOL, remaining_turns=[]) == []


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
            anticipate=True,
        )
        assert results[0].reply == ("Common", "top")


class TestPersonalTerm:
    """SPEC-41 critère 5 : ma maîtrise ne fait reculer un pick que si elle dépasse son avance."""

    def _gap(self, search) -> float:
        """Avance de Greedy sur Safe, en logit, sur la draft seule."""
        greedy = search.evaluator.contribution(("Greedy", "top"), [], ENEMIES)
        safe = search.evaluator.contribution(("Safe", "top"), [], ENEMIES)
        return greedy - safe

    def _rank(self, search, personal=None):
        kwargs = {} if personal is None else {"personal": personal}
        return search.rank(
            allies=[],
            enemies=ENEMIES,
            pool=POOL,
            remaining_turns=[OUR_TURN],
            player_lane="top",
            **kwargs,
        )

    def test_sans_terme_le_classement_ne_change_pas(self, search):
        results = self._rank(search)
        assert [r.champion for r in results] == ["Greedy", "Safe"]
        assert all(r.personal_points == 0.0 for r in results)

    def test_un_terme_plus_grand_que_l_avance_fait_reculer_le_pick(self, search):
        gap = self._gap(search)
        assert gap > 0
        malus = -(gap + 0.01)
        results = self._rank(search, lambda name: malus if name == "Greedy" else 0.0)
        assert [r.champion for r in results] == ["Safe", "Greedy"]
        greedy = next(r for r in results if r.champion == "Greedy")
        assert greedy.personal_points == pytest.approx(to_win_points(malus))

    def test_un_terme_plus_petit_que_l_avance_garde_le_pick(self, search):
        malus = -(self._gap(search) - 0.01)
        results = self._rank(search, lambda name: malus if name == "Greedy" else 0.0)
        assert [r.champion for r in results] == ["Greedy", "Safe"]
