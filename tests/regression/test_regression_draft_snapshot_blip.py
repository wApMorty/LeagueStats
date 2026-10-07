"""Régression : l'écran de draft restait vide après un faux « hors champ select » du LCU.

Symptôme : la pastille « Champ select en cours » est allumée et le Live Coach continue de lire la
draft, mais l'écran de draft affiche « Pas de champ select en cours » jusqu'au prochain pick ou ban
(en FINALIZATION, jusqu'à la fin de la draft).

Cause racine : ``MonitorLifecycle.monitor_loop`` appelle ``recommender.clear()`` dès qu'un seul sondage
de ``is_in_champion_select`` répond faux, et ``LCUClient`` répond faux aussi quand l'appel échoue
(délai dépassé, 5xx). ``clear`` publie ``None`` et oublie le dernier calcul ; la draft n'ayant pas
changé au sondage suivant, ni ``handle_draft_change`` ni ``refresh`` ne republient.

Correctif : le client n'est déclaré hors champ select qu'après ``CHAMP_SELECT_EXIT_TICKS`` sondages
faux de suite.

Prévention : ce test rejoue un sondage faux isolé au milieu d'une draft inchangée.
"""

from unittest.mock import Mock, patch

from src.client.bus import EventBus
from src.config_constants import draft_config
from src.draft.snapshot import TOPIC
from tests.test_draft_snapshot import RANKED, monitor, pick_state  # noqa: F401  (fixture)


def _tick(monitor, in_champ_select):
    # Un sondage qui échoue répond None (SPEC-25 : la phase se lit en une seule requête).
    monitor.lcu.get_gameflow_session.return_value = (
        {"phase": "ChampSelect"} if in_champ_select else None
    )
    monitor.lcu.get_champion_select_session.return_value = {"timer": {}}
    with patch.object(monitor, "_parse_draft_state", return_value=pick_state()):
        monitor.lifecycle.monitor_loop()


def test_un_sondage_faux_isole_ne_vide_pas_l_ecran_de_draft(monitor):
    monitor.bus = EventBus()
    monitor.crawler, monitor.loadout = Mock(), Mock()
    with patch.object(monitor.search, "rank", return_value=RANKED):
        _tick(monitor, True)
        assert monitor.bus.latest(TOPIC) is not None
        _tick(monitor, False)  # un seul sondage échoue
        _tick(monitor, True)  # la draft n'a pas bougé
    assert monitor.bus.latest(TOPIC) is not None


def test_une_vraie_sortie_vide_l_ecran_apres_quelques_sondages(monitor):
    monitor.bus = EventBus()
    monitor.crawler, monitor.loadout = Mock(), Mock()
    with patch.object(monitor.search, "rank", return_value=RANKED):
        _tick(monitor, True)
        for _ in range(draft_config.CHAMP_SELECT_EXIT_TICKS):
            assert monitor.bus.latest(TOPIC) is not None
            _tick(monitor, False)
    assert monitor.bus.latest(TOPIC) is None
