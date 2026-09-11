"""Regression : dette signalée SPEC-10 (TODO.md) -- BanRecommender était
aveugle à l'état de la draft (bans/picks). La seule protection réelle vivait
dans BanAdvisor.handle_auto_ban_hover() (et seulement pour les bans, pas les
picks), pas dans la classe qui produit la recommandation.

Fix : BanRecommender.get_ban_recommendations() reçoit désormais un paramètre
optionnel `exclude_champions`, relayé par Assistant.get_ban_recommendations()
et alimenté par BanAdvisor (bans + picks, camp allié et ennemi) partout où un
DraftState est disponible. Les bans précalculés en base (qui ne peuvent pas
connaître l'état live) sont filtrés a posteriori côté BanAdvisor.
"""

from unittest.mock import Mock

from src.analysis.ban_recommendations import BanRecommender
from src.draft.ban_advice import BanAdvisor
from src.draft.state import DraftState


class TestBanRecommenderExcludesUnavailableChampions:
    """L'invariant vit maintenant dans la classe qui produit la recommandation."""

    def test_excluded_champion_never_returned_as_candidate(self, db, insert_matchup):
        insert_matchup("Aatrox", "Darius", 48.5, -150, -2.5, 8.5, 1500)
        insert_matchup("Aatrox", "Garen", 51.2, 120, 1.2, 6.5, 1200)

        recommender = BanRecommender(db, verbose=False)
        recs = recommender.get_ban_recommendations(
            ["Aatrox"], num_bans=5, exclude_champions=["Darius"]
        )

        assert all(name != "Darius" for name, *_ in recs)
        assert any(name == "Garen" for name, *_ in recs)

    def test_exclusion_is_case_insensitive(self, db, insert_matchup):
        insert_matchup("Aatrox", "Darius", 48.5, -150, -2.5, 8.5, 1500)

        recommender = BanRecommender(db, verbose=False)
        recs = recommender.get_ban_recommendations(
            ["Aatrox"], num_bans=5, exclude_champions=["darius"]
        )

        assert all(name != "Darius" for name, *_ in recs)

    def test_no_exclusion_preserves_prior_behaviour(self, db, insert_matchup):
        """None (défaut) = comportement inchangé, notamment pour le précalcul
        hors contexte de draft (precalculate_pool_bans)."""
        insert_matchup("Aatrox", "Darius", 48.5, -150, -2.5, 8.5, 1500)

        recommender = BanRecommender(db, verbose=False)
        recs = recommender.get_ban_recommendations(["Aatrox"], num_bans=5)

        assert any(name == "Darius" for name, *_ in recs)


class TestBanAdvisorWiresDraftStateIntoRealTimeCalculation:
    """BanAdvisor doit transmettre bans+picks (camp allié et ennemi) comme
    exclude_champions au calcul temps réel."""

    def _make_monitor(self):
        monitor = Mock()
        monitor.verbose = False
        monitor.pool_name = None  # force le chemin temps réel
        monitor.current_pool = ["Aatrox"]
        monitor.pool_lane = None
        monitor.last_ban_recommendation = None
        monitor.assistant.get_ban_recommendations.return_value = [
            ("Garen", 12.0, -5.0, "Aatrox", 1)
        ]
        monitor._is_player_ban_turn.return_value = True
        monitor._get_display_name.side_effect = lambda champ_id: {
            1: "Darius",
            2: "Ahri",
            3: "Ashe",
        }.get(champ_id, f"Champion{champ_id}")
        return monitor

    def test_handle_auto_ban_hover_excludes_bans_and_picks_both_sides(self):
        monitor = self._make_monitor()
        advisor = BanAdvisor(monitor)
        state = DraftState(
            phase="BAN_PICK", ally_bans=[1], enemy_bans=[], ally_picks=[2], enemy_picks=[3]
        )

        advisor.handle_auto_ban_hover(state)

        call_kwargs = monitor.assistant.get_ban_recommendations.call_args.kwargs
        assert set(call_kwargs["exclude_champions"]) == {"Darius", "Ahri", "Ashe"}

    def test_show_adaptive_ban_recommendations_excludes_bans_and_picks(self):
        monitor = self._make_monitor()
        monitor.assistant.get_ban_recommendations.return_value = [
            ("Garen", 12.0, -5.0, "Aatrox", 1)
        ]
        advisor = BanAdvisor(monitor)
        state = DraftState(
            phase="BAN_PICK", ally_bans=[1], enemy_bans=[], ally_picks=[2], enemy_picks=[3]
        )

        advisor.show_adaptive_ban_recommendations(state)

        call_kwargs = monitor.assistant.get_ban_recommendations.call_args.kwargs
        assert set(call_kwargs["exclude_champions"]) == {"Darius", "Ahri", "Ashe"}


class TestBanAdvisorFiltersStalePrecalculatedBans:
    """Les bans précalculés en base ignorent l'état de draft par construction
    (calculés hors contexte) -- BanAdvisor doit les filtrer a posteriori."""

    def _make_monitor_with_precalculated(self, precalculated):
        monitor = Mock()
        monitor.verbose = False
        monitor.pool_name = "TestPool"
        monitor.current_pool = ["Aatrox"]
        monitor.pool_lane = None
        monitor.last_ban_recommendation = None
        monitor.assistant.db.get_pool_ban_recommendations.return_value = precalculated
        monitor._is_player_ban_turn.return_value = True
        monitor._auto_hover_champion.return_value = True
        monitor._get_display_name.side_effect = lambda champ_id: {1: "Darius"}.get(
            champ_id, f"Champion{champ_id}"
        )
        return monitor

    def test_stale_top_precalculated_ban_is_skipped_for_next_candidate(self):
        """Darius (précalculé en tête) est déjà banni en direct -- Garen (2e
        candidat précalculé) doit être choisi, plutôt que de renoncer."""
        monitor = self._make_monitor_with_precalculated(
            [("Darius", 15.0, -3.0, "Aatrox", 2), ("Garen", 10.0, -1.0, "Aatrox", 2)]
        )
        advisor = BanAdvisor(monitor)
        state = DraftState(phase="BAN_PICK", ally_bans=[1], enemy_bans=[])

        advisor.handle_auto_ban_hover(state)

        monitor._auto_hover_champion.assert_called_once()
        assert monitor._auto_hover_champion.call_args.args[0] == "Garen"

    def test_all_precalculated_candidates_stale_falls_back_to_real_time(self):
        monitor = self._make_monitor_with_precalculated([("Darius", 15.0, -3.0, "Aatrox", 2)])
        monitor.assistant.get_ban_recommendations.return_value = [
            ("Garen", 10.0, -1.0, "Aatrox", 2)
        ]
        advisor = BanAdvisor(monitor)
        state = DraftState(phase="BAN_PICK", ally_bans=[1], enemy_bans=[])

        advisor.handle_auto_ban_hover(state)

        monitor.assistant.get_ban_recommendations.assert_called_once()
        monitor._auto_hover_champion.assert_called_once()
        assert monitor._auto_hover_champion.call_args.args[0] == "Garen"
