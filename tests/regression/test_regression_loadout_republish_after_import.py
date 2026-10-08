"""Régression : l'écran de draft n'affichait la page de runes que plusieurs secondes après son import.

Symptôme : au lock-in, la page de runes est déjà écrite dans le client LoL mais l'écran Draft du client
ne la montre que bien plus tard (au prochain survol, tour ou changement de phase).

Cause racine : le snapshot est publié sur le bus avant `LoadoutImporter.on_tick`, et sa signature
(`DraftRecommender._signature`) ne contenait pas la build écrite : une fois l'import fini, plus rien
ne déclenchait la republication tant que la draft elle-même ne bougeait pas.

Correctif : la signature du snapshot inclut `loadout.state()`, `refresh` du tick suivant republie.

Prévention : ce test importe une build après la publication et exige un second snapshot qui la porte.
"""

from unittest.mock import Mock, patch

from src.client.bus import EventBus
from src.draft.loadout import Build
from src.draft.snapshot import TOPIC
from src.draft_monitor import DraftMonitor, DraftState


def _monitor():
    assistant = Mock()
    assistant.db = Mock()
    assistant.db.get_all_matchups_bulk.return_value = {}
    assistant.db.get_all_synergies_bulk.return_value = {}
    assistant.db.get_all_champion_scores.return_value = []
    with patch("src.draft_monitor.LCUClient", return_value=Mock()):
        with patch("src.draft_monitor.Assistant", return_value=assistant):
            monitor = DraftMonitor(verbose=False, auto_hover=False)
    monitor.champion_id_to_name = {266: "Aatrox"}
    return monitor


def test_le_snapshot_est_republie_quand_la_build_est_importee():
    monitor, state = _monitor(), DraftState(phase="FINALIZATION", local_player_cell_id=0)
    monitor.bus = EventBus()
    with monitor.bus.subscribe([TOPIC]) as subscription:
        monitor.recommender.provide(state)
        _, before = subscription.get(1)
        assert before["loadout"] is None

        build = Build(
            8010, 8200, (8010, 9111, 9104, 8299, 8226, 8210), (5008, 5008, 5001), (), (4, 12), 90
        )
        monitor.loadout._applied = (266, "Aatrox top", build)  # ce que `_import` écrit
        monitor.recommender.refresh(state)  # le tick suivant, draft inchangée

        _, after = subscription.get(1)
    assert after["loadout"]["champion_id"] == 266
