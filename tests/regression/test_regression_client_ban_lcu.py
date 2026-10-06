"""Régression SPEC-24 tâche 97 : le ban visé n'arrivait pas dans le client LoL.

Symptôme (@pj35, 2026-10-06) : le champion à bannir n'apparaît jamais dans le client LoL, ni depuis
l'écran de draft du client LeagueStats, ni par le survol automatique de la console.

Causes, relevées sur une vraie draft classée (file 420, bans simultanés, `scripts/dump_lcu_draft_forms.py
--watch`, fixtures `tests/fixtures/lcu_forms/`) :
1. `bannable-champion-ids` ne vaut que `[-1]` pendant toute la phase où mon ban est en cours :
   `draft_actions.run` refusait chaque ban (« pas disponible ») ; une liste sans identifiant réel ne dit
   rien, c'est le client LoL qui tranche.
2. `LCUClient.get_current_player_action_id` ne cherchait que `pick` : le survol automatique d'un ban
   s'écrivait sur mon action de pick (non en cours), pas sur mon action de ban.
3. Bans et picks sont simultanés (`isInProgress` vrai pour plusieurs cellules) : `current_actor` désigne
   la première action non terminée, donc `is_player_ban_turn` / `is_player_turn` étaient faux pour tout
   joueur qui n'est pas premier de son lot, et le survol automatique ne partait même pas.

Correctif : une liste sans identifiant réel ne bloque plus ; l'action est choisie par type ;
le tour se lit sur `acting_cells` quand le LCU le donne.
"""

from unittest.mock import Mock, patch

from src.draft import phases
from src.draft.ban_advice import BanAdvisor
from src.draft.state import DraftState
from src.draft.state_parser import DraftStateParser
from src.lcu_client import LCUClient
from tests.test_client_draft_actions import FauxLCU, load
from src.client import draft_actions
from src.client.lcu_proxy import LcuProxy

BANNABLE = "/lol-champ-select/v1/bannable-champion-ids"


def test_un_ban_n_est_pas_refuse_quand_la_liste_ne_contient_que_moins_un():
    lcu = FauxLCU(load("session_ban.json"), bannable=load("bannable_ban_phase.json"))
    draft_actions.run(LcuProxy(lcu), "hover_ban", 122)
    assert lcu.writes == [
        (
            "PATCH",
            "/lol-champ-select/v1/session/actions/4",
            {"championId": 122, "completed": False, "type": "ban"},
        )
    ]


def test_le_survol_automatique_d_un_ban_vise_l_action_de_ban():
    session = load("session_ban.json")
    client = LCUClient.__new__(LCUClient)
    with patch.object(client, "get_champion_select_session", return_value=session):
        assert client.get_current_player_action_id("ban") == 4  # mon ban, pas mon pick (18)


def test_le_survol_ecrit_le_type_demande():
    client = LCUClient.__new__(LCUClient)
    client.verbose = False
    sent = {}
    with (
        patch.object(client, "is_in_champion_select", return_value=True),
        patch.object(client, "get_champion_id_by_name", return_value=122),
        patch.object(client, "get_current_player_action_id", return_value=4),
        patch.object(
            client,
            "_make_request",
            side_effect=lambda e, method="GET", data=None: sent.update(data=data) or {},
        ),
    ):
        assert client.hover_champion("Darius", action_type="ban") is True
    assert sent["data"] == {"championId": 122, "completed": False, "type": "ban"}


def parse(session):
    lcu = Mock()
    lcu.get_assigned_positions.return_value = {}
    return DraftStateParser(lcu, str).parse(session, {}, {})[0]


def test_bans_simultanes_c_est_mon_tour_meme_si_je_ne_suis_pas_le_premier():
    state = parse(load("session_ban_simultane.json"))  # cellule 4, la cellule 0 n'a pas fini
    assert state.local_player_cell_id == 4 and state.current_actor == 0
    assert phases.is_player_ban_turn(state) is True


def test_picks_simultanes_c_est_mon_tour_dans_le_lot_de_deux():
    session = load("session_swaps.json")  # les cellules 1 et 2 jouent ensemble
    session["localPlayerCellId"] = 2
    state = parse(session)
    assert state.acting_cells == {1, 2} and state.current_actor == 1
    assert phases.is_player_turn(state) is True


def _advisor(hover_result):
    monitor = Mock()
    monitor.verbose = False
    monitor.pool_name = None
    monitor.current_pool = ["Aatrox"]
    monitor.pool_lane = None
    monitor.last_ban_recommendation = None
    monitor.assistant.get_ban_recommendations.return_value = [("Garen", 12.0, -5.0, "Aatrox", 1)]
    monitor._is_player_ban_turn.return_value = True
    monitor._get_display_name.side_effect = str
    monitor._auto_hover_champion.return_value = hover_result
    return BanAdvisor(monitor), monitor


def test_le_survol_automatique_demande_une_action_de_ban_et_lit_le_retour(capsys):
    advisor, monitor = _advisor(True)
    advisor.handle_auto_ban_hover(DraftState(phase="BAN_PICK"))
    assert monitor._auto_hover_champion.call_args.kwargs["action_type"] == "ban"
    assert "[AUTO-BAN-HOVER] Survol de Garen" in capsys.readouterr().out
    assert monitor.last_ban_recommendation == "Garen"


def test_un_survol_refuse_est_annonce_comme_un_echec(capsys):
    advisor, monitor = _advisor(False)
    advisor.handle_auto_ban_hover(DraftState(phase="BAN_PICK"))
    assert "Échec du survol de Garen" in capsys.readouterr().out
    assert monitor.last_ban_recommendation is None


def test_le_facade_du_moniteur_renvoie_le_resultat_du_survol():
    from src.draft.automation import HoverAutomation

    monitor = Mock()
    monitor.lcu.hover_champion.return_value = True
    assert HoverAutomation(monitor).auto_hover_champion("Garen", "x", action_type="ban") is True
    monitor.lcu.hover_champion.assert_called_once_with("Garen", action_type="ban")
    monitor.lcu.hover_champion.return_value = False
    assert HoverAutomation(monitor).auto_hover_champion("Garen") is False


def test_la_cellule_0_peut_survoler_son_ban_l_action_a_l_identifiant_0():
    """L'action de ban de la cellule 0 a l'id 0 : « if not action_id » la prenait pour « aucune »."""
    session = load("session_ban_simultane.json")
    session["localPlayerCellId"] = 0
    client = LCUClient.__new__(LCUClient)
    client.verbose = False
    sent = {}
    with patch.object(client, "get_champion_select_session", return_value=session):
        assert client.get_current_player_action_id("ban") == 0
        with (
            patch.object(client, "is_in_champion_select", return_value=True),
            patch.object(client, "get_champion_id_by_name", return_value=122),
            patch.object(
                client,
                "_make_request",
                side_effect=lambda e, method="GET", data=None: sent.update(endpoint=e) or {},
            ),
        ):
            assert client.hover_champion("Darius", action_type="ban") is True
    assert sent["endpoint"] == "/lol-champ-select/v1/session/actions/0"
