"""Tests de l'affichage des recommandations du Live Coach.

SPEC-06 C3 (historique) : les scores affichés devaient être ceux qui avaient
servi au classement, jamais un recalcul — deux calculs séparés pouvaient
diverger. SPEC-12 rend la divergence structurellement impossible (la recherche
produit une valeur par candidat, l'affichage l'imprime), mais la propriété
reste testée ici : c'est elle qui garantit que le chiffre à l'écran est bien
celui qui a trié la liste.
"""

from unittest.mock import Mock, patch

import pytest

from src.analysis.mastery import Mastery, MasteryTerm, to_win_points, with_term
from src.analysis.strategy import Strategy, WeightedEvaluator, find_strategy
from src.draft.snapshot import Analysis
from src.draft.state import Cell
from src.draft.search import CandidatePool, DraftSearch, PickTurn, SearchResult
from src.draft_monitor import DraftMonitor, DraftState
from src.models import Matchup
from src.user_prefs import save_active_strategy, save_strategies

POOL = ["Aatrox", "Darius", "Garen", "Sett"]
CHAMPION_IDS = {266: "Aatrox", 122: "Darius", 86: "Garen", 875: "Sett", 64: "LeeSin"}
OUR_TURN = PickTurn(is_ally=True, is_local_player=True)


def _matchup(enemy="LeeSin", games=1000):
    return Matchup(
        enemy_name=enemy, winrate=52.0, delta1=100.0, delta2=150.0, pickrate=5.0, games=games
    )


@pytest.fixture
def monitor():
    """DraftMonitor avec LCU et Assistant simulés, pool de 4 champions."""
    assistant = Mock()
    assistant.db = Mock()
    assistant.get_matchups_for_draft.return_value = [_matchup()]
    # Tables réelles (vides) : l'évaluateur SPEC-12 les indexe, un Mock nu
    # ferait exploser les lookups de paires.
    assistant.db.get_all_matchups_bulk.return_value = {}
    assistant.db.get_all_synergies_bulk.return_value = {}
    assistant.db.get_lane_winrates.return_value = {}
    assistant.db.get_all_champion_scores.return_value = []

    with patch("src.draft_monitor.LCUClient", return_value=Mock()):
        with patch("src.draft_monitor.Assistant", return_value=assistant):
            monitor = DraftMonitor(verbose=False, auto_hover=False)

    monitor.current_pool = POOL
    monitor.champion_id_to_name = dict(CHAMPION_IDS)
    # SPEC-46 : les `SearchResult` simulés portent leurs valeurs, que Complet garde telles quelles.
    monitor.set_strategy(find_strategy("Complet", ()))
    return monitor


@pytest.fixture
def state():
    """Un ennemi pické, aucun allié, notre pick à venir : phase de counterpick."""
    return DraftState(
        phase="BAN_PICK",
        enemy_picks=[64],
        ally_picks=[],
        remaining_picks=[OUR_TURN],
    )


def test_pool_is_scored_once_per_champion(monitor, state, capsys):
    """Un seul passage en base par champion du pool, et une seule recherche.

    La recherche est appelée avec le pool entier : si elle était relancée par
    champion, le budget temps serait divisé par la taille du pool.
    """
    with patch.object(monitor.search, "rank", return_value=[]) as mock_rank:
        monitor._provide_recommendations(state)

    capsys.readouterr()
    assert monitor.assistant.get_matchups_for_draft.call_count == len(POOL)
    assert mock_rank.call_count == 1
    assert sorted(mock_rank.call_args.kwargs["pool"]) == sorted(POOL)


def test_displayed_probability_is_the_searched_one(monitor, state, capsys):
    """Le chiffre affiché est la valeur rendue par la recherche, pas un recalcul."""
    ranked = [
        SearchResult("Aatrox", "top", 0.5731, [("Fiora", "top")], depth=2),
        SearchResult("Darius", "top", 0.5210, [], depth=2),
        SearchResult("Garen", "top", 0.4890, [], depth=2),
        SearchResult("Sett", "top", 0.4102, [], depth=2),
    ]

    with patch.object(monitor.search, "rank", return_value=ranked):
        monitor._provide_recommendations(state)

    output = capsys.readouterr().out
    assert "[1st] Aatrox" in output
    assert "57.31%" in output
    assert "[2nd] Darius" in output
    assert "52.10%" in output
    # Sett est 4e : hors du top 3, donc jamais affiché
    assert "Sett" not in output


def test_principal_variation_is_displayed(monitor, state, capsys):
    """La réponse adverse anticipée est montrée au joueur : c'est l'intérêt
    d'une recherche par rapport à un score plat."""
    ranked = [SearchResult("Aatrox", "top", 0.53, [("Fiora", "top")], depth=2)]

    with patch.object(monitor.search, "rank", return_value=ranked):
        monitor._provide_recommendations(state)

    output = capsys.readouterr().out
    assert "suite attendue" in output
    assert "Fiora (top)" in output
    assert "Profondeur atteinte : 2" in output


def test_champion_without_data_is_listed_as_skipped_not_dropped(monitor, capsys):
    """SPEC-09 E1 : un champion de la pool sans matchups pour la lane doit
    apparaître comme écarté, jamais disparaître silencieusement.

    Avec SPEC-12 le risque change de nature mais reste le même : la recherche
    noterait un champion sans données à 50 %, soit exactement le score d'un
    matchup réellement neutre. Il doit donc être retiré du classement en amont.
    """
    pool = ["Aatrox", "Darius", "Malphite"]
    monitor.current_pool = pool
    monitor.champion_id_to_name = {**CHAMPION_IDS, 54: "Malphite"}
    state = DraftState(
        phase="BAN_PICK",
        enemy_picks=[64],
        ally_picks=[],
        local_player_cell_id=1,
        ally_positions={1: "middle"},
        remaining_picks=[OUR_TURN],
    )

    def fake_matchups(champion_name, lane=None):
        if champion_name == "Malphite":
            return []  # aucune donnée pour cette lane
        return [_matchup()]

    monitor.assistant.get_matchups_for_draft.side_effect = fake_matchups

    monitor._provide_recommendations(state)

    output = capsys.readouterr().out
    assert "Malphite (0 games)" in output
    assert "Sans données exploitables en middle" in output
    # Malphite ne doit jamais apparaître dans le classement [1st]/[2nd]/[3rd]
    for rank_line in output.splitlines():
        if rank_line.strip().startswith(("[1st]", "[2nd]", "[3rd]")):
            assert "Malphite" not in rank_line
    # Et il ne doit pas non plus être soumis à la recherche.
    assert "Malphite" not in str(monitor.search.candidates._by_lane)


class TestTurnSelection:
    """`_turns_from_our_next_pick` : la racine de la recherche doit être NOTRE
    tour, sinon la valeur par candidat perd son sens."""

    def test_turns_before_ours_are_dropped(self, monitor):
        state = DraftState(
            remaining_picks=[
                PickTurn(is_ally=False),
                PickTurn(is_ally=True),  # un allié, pas nous
                OUR_TURN,
                PickTurn(is_ally=False),
            ]
        )

        turns = monitor.recommender._turns_from_our_next_pick(state)

        assert turns[0] is OUR_TURN
        assert len(turns) == 2

    def test_no_remaining_pick_of_ours_returns_nothing(self, monitor):
        state = DraftState(remaining_picks=[PickTurn(is_ally=False)])
        assert monitor.recommender._turns_from_our_next_pick(state) == []

    def test_message_when_we_have_already_picked(self, monitor, capsys):
        """Après notre pick, un classement de counterpick n'aurait plus d'objet."""
        state = DraftState(phase="BAN_PICK", enemy_picks=[64], ally_picks=[266])

        monitor._provide_recommendations(state)

        assert "Plus aucun pick à jouer de votre côté" in capsys.readouterr().out


class TestMasteryReload:
    """SPEC-41 critère 7 : la maîtrise se recharge à chaque nouvelle draft, sans jamais casser la boucle."""

    def _new_episode(self, monitor, episode=5):
        monitor.phase_tracker = Mock(draft_episode=episode)
        monitor.lifecycle._rearm_for_new_draft(Mock())

    def test_une_nouvelle_draft_recharge_le_terme(self, monitor):
        fresh = MasteryTerm()
        with patch("src.draft.lifecycle.MasteryTerm.read", return_value=fresh) as read:
            self._new_episode(monitor)

        read.assert_called_once_with(monitor.assistant.db)
        assert monitor.mastery is fresh

    def test_une_base_en_panne_garde_l_ancien_terme(self, monitor, capsys):
        """Vraie panne (base illisible), sans faux `read` : le bon terme reste en place, la draft
        est ré-armée, et le mode verbeux le dit."""
        previous = MasteryTerm({"Gnar": Mastery("Gnar", 5, -10.0, -1.1)})
        monitor.mastery = previous
        monitor.verbose = True
        monitor.assistant.db.get_all_champion_names.side_effect = RuntimeError("base verrouillée")

        self._new_episode(monitor)  # ne lève pas

        assert monitor.mastery is previous
        assert monitor._draft_episode == 5
        assert "[ALERTE] Maîtrise personnelle non rechargée" in capsys.readouterr().out

    def test_la_recherche_recoit_le_terme_du_monitor(self, monitor, state):
        """Le classement passe la maîtrise du monitor à la recherche (logit de mon pick)."""
        monitor.mastery = MasteryTerm()
        monitor.search = Mock()
        monitor.search.rank.return_value = []

        monitor._provide_recommendations(state)

        personal = monitor.search.rank.call_args.kwargs["personal"]
        assert personal("Darius") == monitor.mastery.logit("Darius")


class TestGrimoireMastery:
    """SPEC-41 critère 6 : la victoire immédiate du grimoire inclut ma maîtrise du champion."""

    def _candidates(self, monitor):
        state = DraftState(
            phase="BAN_PICK",
            enemy_picks=[64],
            local_player_cell_id=0,
            ally_positions={0: "top"},
            ally_cells=[Cell(cell_id=0)],
        )
        analysis = Analysis()
        with patch.object(monitor, "_is_ban_phase", return_value=False):
            monitor.recommender._fill_candidates(state, analysis)
        return analysis.candidates

    def test_le_grimoire_ajoute_le_terme_a_mon_champion(self, monitor):
        monitor.mastery = MasteryTerm()
        without = self._candidates(monitor)
        monitor.mastery = MasteryTerm({"Darius": Mastery("Darius", 10, -4.0, -2.0)})

        with_mastery = self._candidates(monitor)

        assert with_mastery[122] == pytest.approx(
            with_term(without[122], monitor.mastery.logit("Darius"))
        )
        assert with_mastery[122] < without[122]
        assert with_mastery[266] == without[266]  # Aatrox, jamais joué : inchangé


def test_la_console_cite_ma_maitrise_du_champion(monitor, capsys):
    """« · toi −2,0 pts (5 parties) » après la victoire, seulement quand le terme est non nul."""
    monitor.mastery = MasteryTerm({"Darius": Mastery("Darius", 5, -10.0, -1.1)})
    results = [
        SearchResult("Darius", "top", 0.52, personal_points=-2.0),
        SearchResult("Garen", "top", 0.51),
    ]

    monitor.recommender._print_results(results, {}, "top", None)

    out = capsys.readouterr().out
    assert "Darius (top) 52.00% de victoire · toi -2.0 pts (5 parties)" in out
    assert "Garen (top) 51.00% de victoire" in out
    assert "· toi" not in out.split("Garen")[1]


MY_TURN = PickTurn(is_ally=True, is_local_player=True, lane="top")
ENEMY_TURN = PickTurn(is_ally=False)


class TestStrategies:
    """SPEC-46 : l'ordre suit la stratégie, les probabilités restent celles du modèle calibré."""

    @pytest.fixture
    def board(self, monitor):
        """Aatrox gagne le duel de lane contre LeeSin, Garen a la meilleure force de lane."""
        db = monitor.assistant.db
        table = {("aatrox", "leesin"): (1.0, 100_000), ("fiora", "aatrox"): (6.0, 100_000)}
        db.get_all_matchups_bulk.return_value = table
        db.get_lane_winrates.return_value = {
            "Aatrox": (50.0, 100_000),
            "Darius": (50.0, 100_000),
            "Garen": (56.0, 100_000),
            "Sett": (50.0, 100_000),
        }
        db.get_lane_popularity.return_value = ["Fiora"]
        monitor.search.candidates = CandidatePool(db, 8)
        monitor.mastery = MasteryTerm({"Darius": Mastery("Darius", 40, 6.0, 3.0)})
        return monitor

    @staticmethod
    def _state(*turns):
        return DraftState(
            phase="BAN_PICK",
            enemy_picks=[64],
            remaining_picks=list(turns),
            inferred_roles={64: "top"},
            ally_positions={0: "top"},
            local_player_cell_id=0,
        )

    def _analysis(self, monitor, *turns):
        analysis = Analysis()
        monitor.recommender._provide(self._state(*turns), analysis)
        return analysis

    def _unseen(self, monitor, *turns):
        """Le même board, LeeSin en jungle : mon vis-à-vis n'est pas vu."""
        state = self._state(*turns)
        state.inferred_roles = {64: "jungle"}
        analysis = Analysis()
        monitor.recommender._provide(state, analysis)
        return analysis

    @pytest.mark.parametrize(
        "name, anticipate", [("Simple", False), ("Counter", False), ("Complet", True)]
    )
    def test_seule_une_strategie_a_recherche_anticipe(self, monitor, state, name, anticipate):
        monitor.set_strategy(find_strategy(name, ()))
        monitor.search.rank = Mock(return_value=[])

        monitor._provide_recommendations(state)

        assert monitor.search.rank.call_args.kwargs["anticipate"] is anticipate

    def test_le_poids_de_maitrise_s_applique_a_mon_terme(self, board, state):
        board.set_strategy(find_strategy("Counter", ()))
        board.search.rank = Mock(return_value=[])

        board._provide_recommendations(state)

        personal = board.search.rank.call_args.kwargs["personal"]
        assert personal("Darius") == pytest.approx(0.25 * board.mastery.logit("Darius"))

    def test_l_ordre_suit_la_strategie_et_le_pourcentage_reste_calibre(self, board):
        """Sous une stratégie au seul duel, Aatrox passe devant Garen, mieux noté par le modèle."""
        board.set_strategy(
            Strategy("Duel", force=0.0, duel=3.0, other=0.0, synergy=0.0, mastery=0.0)
        )

        results = self._analysis(board, MY_TURN).results

        assert results[0].champion == "Aatrox"
        for result in results:
            expected = with_term(
                board.evaluator.win_probability([(result.champion, "top")], [("LeeSin", "top")]),
                board.mastery.logit(result.champion),
            )
            assert result.win_probability == pytest.approx(expected)
        garen = next(r for r in results if r.champion == "Garen")
        assert garen.win_probability > results[0].win_probability
        assert results[0].score > garen.score

    def test_le_tirage_change_l_ordre_sans_toucher_au_pourcentage(self, board):
        """ADR-004 : le premier perd sa place, sa victoire affichée ne bouge pas d'un bit."""
        board.set_strategy(find_strategy("Simple", ()))
        before = self._analysis(board, MY_TURN).results
        first = before[0]

        board.evaluator._draws = {"top": {first.champion.lower(): 100.0}}
        after = self._analysis(board, MY_TURN).results

        assert after[0].champion != first.champion
        assert {r.champion: r.win_probability for r in after} == {
            r.champion: r.win_probability for r in before
        }

    def test_counter_garde_la_victoire_calibree(self, board):
        """Critère 5 : sous Counter, ni ses poids ni sa maîtrise à 0,25 ne touchent le %."""
        board.set_strategy(find_strategy("Counter", ()))

        results = self._analysis(board, MY_TURN).results

        assert len(results) == len(POOL)
        for result in results:
            expected = with_term(
                board.evaluator.win_probability([(result.champion, "top")], [("LeeSin", "top")]),
                board.mastery.logit(result.champion),
            )
            assert result.win_probability == pytest.approx(expected)
        darius = next(r for r in results if r.champion == "Darius")
        assert darius.personal_points == pytest.approx(
            to_win_points(0.25 * board.mastery.logit("Darius"))
        )

    @pytest.mark.parametrize(
        "strategy",
        [
            Strategy("Long", duel=2.0, search=True),
            Strategy("WIN LANE", 1.0, 3.0, 0.25, 0.0, 0.0, search=True),
        ],
    )
    def test_la_reponse_entre_dans_la_victoire_calibree(self, board, strategy):
        board.set_strategy(strategy)

        results = self._unseen(board, MY_TURN, ENEMY_TURN).results

        aatrox = next(r for r in results if r.champion == "Aatrox")
        assert aatrox.reply == ("Fiora", "top")
        expected = board.evaluator.win_probability(
            [("Aatrox", "top")], [("LeeSin", "jungle"), ("Fiora", "top")]
        )
        assert aatrox.win_probability == pytest.approx(expected)

    def test_un_vis_a_vis_vu_ne_laisse_aucune_reponse(self, board):
        board.set_strategy(Strategy("Long", duel=2.0, search=True))

        results = self._analysis(board, MY_TURN, ENEMY_TURN).results

        assert all(r.reply is None for r in results)

    def test_a_score_egal_la_victoire_calibree_departage(self, board):
        """Tout le pool à égalité : le premier du pool ne gagne plus par défaut (SPEC-46 §1.3)."""
        board.assistant.db.get_all_matchups_bulk.return_value = {}
        board.set_strategy(
            Strategy("Duel", force=0.0, duel=1.0, other=0.0, synergy=0.0, mastery=0.0)
        )

        results = self._analysis(board, MY_TURN).results

        assert len({r.score for r in results}) == 1
        assert results[0].champion == "Darius"  # sa maîtrise le place devant Garen, pas son rang

    def test_complet_rend_le_classement_d_un_draft_search_direct(self, board):
        direct = DraftSearch(board.evaluator, board.search.candidates)
        expected = direct.rank(
            allies=[],
            enemies=[("LeeSin", "jungle")],
            pool=POOL,
            remaining_turns=[MY_TURN, ENEMY_TURN],
            player_lane="top",
            personal=board.mastery.logit,
            anticipate=True,
        )

        results = self._unseen(board, MY_TURN, ENEMY_TURN).results

        assert expected[0].reply is not None
        assert [(r.champion, r.lane, r.win_probability, r.reply) for r in results] == [
            (r.champion, r.lane, r.win_probability, r.reply) for r in expected
        ]

    def test_parts_ne_garde_que_les_termes_de_poids_non_nul(self, board):
        board.set_strategy(find_strategy("Simple", ()))

        parts = self._analysis(board, MY_TURN).parts["Aatrox"]

        assert set(parts) == {"force", "duel", "other"}
        logit = WeightedEvaluator(board.evaluator, board.strategy).parts(
            ("Aatrox", "top"), [], [("LeeSin", "top")]
        )
        assert parts["duel"] == pytest.approx(to_win_points(logit["duel"]))

    def test_la_console_ne_cite_la_profondeur_que_pour_une_recherche(self, board, capsys):
        board.set_strategy(find_strategy("Simple", ()))
        self._analysis(board, MY_TURN)
        output = capsys.readouterr().out
        assert "RECOMMANDATIONS DE COUNTERPICK (Simple) :" in output
        assert "Profondeur atteinte" not in output

    def test_bascule_a_mon_tour_survole_le_nouveau_numero_un(self, board):
        board.auto_hover = True
        board.last_recommendation = "Darius"
        board._is_player_turn = Mock(return_value=True)
        board._enemy_picks_changed = Mock(return_value=False)
        board.lcu = Mock()  # faux LCU : seul le survol doit le toucher
        board.lcu.hover_champion.return_value = True
        board.set_strategy(
            Strategy("Duel", force=0.0, duel=3.0, other=0.0, synergy=0.0, mastery=0.0)
        )

        self._analysis(board, MY_TURN)

        board.lcu.hover_champion.assert_called_once_with("Aatrox", action_type="pick")
        assert [call[0] for call in board.lcu.method_calls] == ["hover_champion"]

    def test_bascule_hors_de_mon_tour_ne_survole_rien(self, board):
        board.auto_hover = True
        board.last_recommendation = "Darius"
        board._is_player_turn = Mock(return_value=False)
        board._enemy_picks_changed = Mock(return_value=False)
        board._auto_hover_champion = Mock(return_value=True)
        board.set_strategy(
            Strategy("Duel", force=0.0, duel=3.0, other=0.0, synergy=0.0, mastery=0.0)
        )

        self._analysis(board, MY_TURN)

        board._auto_hover_champion.assert_not_called()

    def test_la_cle_de_publication_change_avec_la_strategie(self, board):
        state = self._state(MY_TURN)
        before = board.recommender._key(state)
        board.set_strategy(find_strategy("Counter", ()))
        assert board.recommender._key(state) != before


class TestStrategyLoading:
    """SPEC-46 §4.3 : préférences, commande `strategy <nom>`, rechargement à chaque draft."""

    def test_le_monitor_part_sur_la_strategie_memorisee(self, monitor):
        save_active_strategy("Counter")

        monitor.load_strategy()

        assert monitor.strategy.name == "Counter"
        assert isinstance(monitor.search.evaluator, WeightedEvaluator)
        assert monitor.strategy_names == ["Simple", "Counter", "Méta", "Complet"]

    def test_sans_preference_la_strategie_par_defaut(self, monitor):
        monitor.load_strategy()
        assert monitor.strategy.name == "Simple"

    def test_complet_garde_l_evaluateur_calibre(self, monitor):
        monitor.set_strategy(find_strategy("Complet", ()))
        assert monitor.search.evaluator is monitor.evaluator

    def test_la_commande_applique_la_strategie_et_force_le_recalcul(self, monitor, state):
        monitor._command_queue.put("strategy counter")

        assert monitor.commands.apply_pending(state) is True
        assert monitor.strategy.name == "Counter"

    def test_la_commande_voit_une_strategie_perso_et_ses_noms(self, monitor, state):
        save_strategies([Strategy("Vite", duel=2.0)])
        monitor._command_queue.put("strategy Vite")

        assert monitor.commands.apply_pending(state) is True
        assert monitor.strategy.duel == 2.0
        assert "Vite" in monitor.strategy_names

    def test_un_nom_inconnu_laisse_la_strategie_courante(self, monitor, state, capsys):
        monitor._command_queue.put("strategy Inconnue")

        assert monitor.commands.apply_pending(state) is False
        assert monitor.strategy.name == "Complet"
        assert "[ALERTE] Stratégie 'Inconnue' introuvable" in capsys.readouterr().out

    def test_une_erreur_de_la_commande_n_interrompt_rien(self, monitor, state, capsys):
        monitor.set_strategy = Mock(side_effect=RuntimeError("panne"))
        monitor._command_queue.put("strategy Counter")

        assert monitor.commands.apply_pending(state) is False
        assert "[ALERTE] Changement de stratégie impossible" in capsys.readouterr().out

    def test_la_nouvelle_draft_relit_la_strategie(self, monitor):
        save_active_strategy("Méta")

        monitor.lifecycle._reload_strategy()

        assert monitor.strategy.name == "Méta"

    def test_une_erreur_de_relecture_garde_la_strategie(self, monitor):
        monitor.load_strategy = Mock(side_effect=OSError("panne"))

        monitor.lifecycle._reload_strategy()

        assert monitor.strategy.name == "Complet"
