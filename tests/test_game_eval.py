"""Tests de src/analysis/game_eval.py (SPEC-12).

Les trois propriétés testées ici ne sont pas cosmétiques : src/draft/search.py
construit son logit incrémentalement, et se tromperait silencieusement si
l'évaluation dépendait de l'ordre des picks ou n'était pas antisymétrique.
"""

import itertools

import pytest

from src.analysis.game_eval import GameEvaluator
from src.analysis.probability import confidence, winrate_points_to_logit
from src.config_constants import analysis_config, role_inference_config


class FakeDB:
    """Sert les mêmes tables quelle que soit la lane demandée.

    Suffisant ici : ce qui dépend de la lane dans game_eval, c'est la
    PONDÉRATION (même lane ou non), pas la table consultée.
    """

    def __init__(self, matchups=None, synergies=None, meta=None):
        self.matchups = matchups or {}
        self.synergies = synergies or {}
        self.meta = meta or {}
        self.matchup_loads = 0

    def get_all_matchups_bulk(self, lane=None, with_games=False):
        self.matchup_loads += 1
        return self.matchups

    def get_all_synergies_bulk(self, lane=None, with_games=False):
        return self.synergies

    def get_meta(self, key):
        """SPEC-13 : GameEvaluator lit le shrink mesuré dans db_meta. Vide par
        défaut, donc repli sur CONFIDENCE_K — les attentes des tests d'avant
        SPEC-13 restent valables telles quelles."""
        return self.meta.get(key)


@pytest.fixture
def evaluator():
    return GameEvaluator(
        FakeDB(
            matchups={
                ("jax", "garen"): (6.0, 10_000),
                ("garen", "jax"): (-2.0, 10_000),
                ("jax", "amumu"): (3.0, 10_000),
                ("nautilus", "garen"): (-4.0, 10_000),
            },
            synergies={
                ("jax", "nautilus"): (4.0, 10_000),
                ("garen", "amumu"): (2.0, 10_000),
            },
        )
    )


class TestPairTerms:
    def test_antisymmetric_delta_is_the_half_difference(self, evaluator):
        # Jax voit +6 contre Garen, Garen voit -2 contre Jax -> (6 - (-2)) / 2 = 4
        value = evaluator.matchup_logit(("Jax", "top"), ("Garen", "top"))

        expected = (
            winrate_points_to_logit(4.0 * analysis_config.K_MATCHUP)
            * role_inference_config.SAME_LANE_WEIGHT
            * confidence(10_000)
        )
        assert value == pytest.approx(expected)

    def test_single_sided_data_is_not_halved(self, evaluator):
        # Seul Jax -> Amumu existe : l'absence de donnée inverse n'est pas un
        # avantage nul mesuré, on garde la seule mesure disponible.
        value = evaluator.matchup_logit(("Jax", "top"), ("Amumu", "jungle"))

        expected = (
            winrate_points_to_logit(3.0 * analysis_config.K_MATCHUP)
            * role_inference_config.OTHER_LANE_WEIGHT
            * confidence(10_000)
        )
        assert value == pytest.approx(expected)

    def test_reverse_only_data_flips_sign(self, evaluator):
        # Rien pour Garen -> Jax dans ce sens de lecture, mais Jax -> Garen
        # existe : le terme doit être l'opposé.
        forward = evaluator.matchup_logit(("Jax", "top"), ("Nautilus", "support"))
        reverse = evaluator.matchup_logit(("Nautilus", "support"), ("Jax", "top"))
        assert forward == pytest.approx(-reverse)

    def test_same_lane_weighs_more_than_other_lane(self, evaluator):
        same = evaluator.matchup_logit(("Jax", "top"), ("Garen", "top"))
        other = evaluator.matchup_logit(("Jax", "top"), ("Garen", "jungle"))
        assert abs(same) > abs(other)
        assert same == pytest.approx(
            other * role_inference_config.SAME_LANE_WEIGHT / role_inference_config.OTHER_LANE_WEIGHT
        )

    def test_low_sample_is_shrunk_toward_zero(self):
        loud = GameEvaluator(FakeDB(matchups={("jax", "garen"): (20.0, 100_000)}))
        quiet = GameEvaluator(FakeDB(matchups={("jax", "garen"): (20.0, 80)}))

        assert abs(quiet.matchup_logit(("Jax", "top"), ("Garen", "top"))) < abs(
            loud.matchup_logit(("Jax", "top"), ("Garen", "top"))
        )

    def test_measured_shrink_from_db_meta_is_honoured(self):
        """SPEC-13 : le K mesuré au dernier scrape doit réellement atteindre le
        logit, et un K plus grand doit peser moins. Sans ce test, une régression
        du câblage db_meta -> GameEvaluator passerait inaperçue : le modèle
        continuerait de tourner, simplement sur le mauvais shrink."""
        pair = {("jax", "garen"): (6.0, 1_000)}
        default = GameEvaluator(FakeDB(matchups=pair))
        measured = GameEvaluator(FakeDB(matchups=pair, meta={"shrink_k_matchup": "1900"}))

        assert abs(measured.matchup_logit(("Jax", "top"), ("Garen", "top"))) < abs(
            default.matchup_logit(("Jax", "top"), ("Garen", "top"))
        )

    def test_synergy_and_matchup_shrinks_are_independent(self):
        """Les deux types ont des K distincts (mesurés ~1900 et ~4000-20000) :
        régler l'un ne doit pas déplacer l'autre."""
        db = FakeDB(
            matchups={("jax", "garen"): (6.0, 1_000)},
            synergies={("jax", "lulu"): (6.0, 1_000)},
            meta={"shrink_k_synergy": "20000"},
        )
        evaluator = GameEvaluator(db)
        baseline = GameEvaluator(FakeDB(matchups={("jax", "garen"): (6.0, 1_000)}))

        assert evaluator.matchup_logit(("Jax", "top"), ("Garen", "top")) == pytest.approx(
            baseline.matchup_logit(("Jax", "top"), ("Garen", "top"))
        )
        assert abs(evaluator.synergy_logit(("Jax", "top"), ("Lulu", "support"))) < 0.01

    def test_unknown_pair_contributes_nothing(self, evaluator):
        assert evaluator.matchup_logit(("Inconnu", "top"), ("Autre", "top")) == 0.0
        assert evaluator.synergy_logit(("Inconnu", "top"), ("Autre", "top")) == 0.0

    def test_has_matchup_data_tells_measured_from_missing(self, evaluator):
        """SPEC-14 : 0.0 ne distingue pas « égalité mesurée » de « rien de mesuré »."""
        assert evaluator.has_matchup_data(("Jax", "top"), ("Garen", "top"))
        assert evaluator.has_matchup_data(("Garen", "top"), ("Nautilus", "support"))  # sens inverse
        assert not evaluator.has_matchup_data(("Inconnu", "top"), ("Autre", "top"))


class TestComposition:
    def test_swapping_teams_flips_the_logit(self, evaluator):
        allies = [("Jax", "top"), ("Nautilus", "support")]
        enemies = [("Garen", "top"), ("Amumu", "jungle")]

        assert evaluator.team_logit(allies, enemies) == pytest.approx(
            -evaluator.team_logit(enemies, allies)
        )

    def test_swapping_teams_makes_probabilities_complementary(self, evaluator):
        allies = [("Jax", "top"), ("Nautilus", "support")]
        enemies = [("Garen", "top"), ("Amumu", "jungle")]

        ours = evaluator.win_probability(allies, enemies)
        theirs = evaluator.win_probability(enemies, allies)
        assert ours + theirs == pytest.approx(1.0)

    def test_empty_draft_is_a_coin_flip(self, evaluator):
        assert evaluator.win_probability([], []) == pytest.approx(0.5)

    def test_incremental_sum_is_order_independent(self, evaluator):
        """La propriété dont dépend la recherche : empiler les contributions
        dans n'importe quel ordre doit redonner team_logit()."""
        allies = [("Jax", "top"), ("Nautilus", "support")]
        enemies = [("Garen", "top"), ("Amumu", "jungle")]
        expected = evaluator.team_logit(allies, enemies)

        # Chaque entrelacement possible des picks alliés et ennemis.
        for ally_order in itertools.permutations(allies):
            for enemy_order in itertools.permutations(enemies):
                for mask in itertools.permutations([True, True, False, False]):
                    placed_allies, placed_enemies = [], []
                    ally_iter, enemy_iter = iter(ally_order), iter(enemy_order)
                    total = 0.0
                    for is_ally in mask:
                        if is_ally:
                            champion = next(ally_iter)
                            total += evaluator.contribution(champion, placed_allies, placed_enemies)
                            placed_allies.append(champion)
                        else:
                            champion = next(enemy_iter)
                            total -= evaluator.contribution(champion, placed_enemies, placed_allies)
                            placed_enemies.append(champion)
                    assert total == pytest.approx(expected)

    def test_synergy_helps_its_own_team_only(self, evaluator):
        """Le pick d'un allié fait bouger le score via la synergie des AUTRES
        alliés avec lui — la motivation même de SPEC-12."""
        alone = evaluator.team_logit([("Jax", "top")], [])
        paired = evaluator.team_logit([("Jax", "top"), ("Nautilus", "support")], [])
        assert paired > alone

        # La même paire, côté ennemi, doit jouer contre nous.
        mirrored = evaluator.team_logit([], [("Jax", "top"), ("Nautilus", "support")])
        assert mirrored == pytest.approx(-paired)


class TestTableLoading:
    def test_tables_are_loaded_once_per_lane(self, evaluator):
        evaluator.matchup_logit(("Jax", "top"), ("Garen", "top"))
        evaluator.matchup_logit(("Jax", "top"), ("Garen", "top"))
        evaluator.matchup_logit(("Jax", "top"), ("Amumu", "top"))

        # Une seule lane touchée ("top") -> un seul chargement.
        assert evaluator.db.matchup_loads == 1
