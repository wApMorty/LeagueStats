"""Snapshot de draft (SPEC-21 tâche 72) : données structurées, sortie console identique, bus best-effort."""

import json
from dataclasses import asdict
from unittest.mock import Mock, patch

import pytest

from src.client.bus import EventBus
from src.draft.search import PickTurn, SearchResult
from src.draft.snapshot import TOPIC
from src.draft.state_parser import DraftStateParser
from src.draft_monitor import DraftMonitor, DraftState
from src.models import Matchup

POOL = ["Aatrox", "Darius", "Garen", "Sett", "Malphite"]
IDS = {
    266: "Aatrox",
    122: "Darius",
    86: "Garen",
    875: "Sett",
    64: "LeeSin",
    54: "Malphite",
    23: "Tryndamere",
    12: "Alistar",
}


def _matchup(games):
    return Matchup(
        enemy_name="LeeSin", winrate=52.0, delta1=1.0, delta2=1.5, pickrate=5.0, games=games
    )


@pytest.fixture
def monitor():
    assistant = Mock()
    assistant.db = Mock()
    assistant.db.get_all_matchups_bulk.return_value = {}
    assistant.db.get_all_synergies_bulk.return_value = {}
    assistant.db.get_all_champion_scores.return_value = []
    assistant.get_matchups_for_draft.side_effect = lambda name, lane=None: (
        [] if name == "Malphite" else [_matchup(12500 if name == "Aatrox" else 840)]
    )
    with patch("src.draft_monitor.LCUClient", return_value=Mock()):
        with patch("src.draft_monitor.Assistant", return_value=assistant):
            monitor = DraftMonitor(verbose=False, auto_hover=False)
    monitor.current_pool = POOL
    monitor.champion_id_to_name = dict(IDS)
    return monitor


RANKED = [
    SearchResult("Aatrox", "top", 0.5731, [("Fiora", "top"), ("Thresh", "support")], 2),
    SearchResult("Darius", "top", 0.5210, [], 2),
    SearchResult("Garen", "top", 0.4890, [("Nasus", "top")], 2),
    SearchResult("Sett", "top", 0.41, [], 2),
]


def pick_state():
    return DraftState(
        phase="BAN_PICK",
        enemy_picks=[64, 23],
        ally_picks=[12],
        local_player_cell_id=1,
        current_actor=1,
        ally_positions={1: "top"},
        inferred_roles={64: "jungle", 23: "top"},
        remaining_picks=[PickTurn(True, True, "top"), PickTurn(False)],
    )


# ---------- sortie console identique ----------

# Relevées sur le code d'avant la tâche 72, avec ces mêmes entrées.
CONSOLE_AVEC_CLASSEMENT = (
    "\n[PICKS] RECOMMANDATIONS DE COUNTERPICK :\n" + "-" * 50 + "\n"
    "  [1st] Aatrox (top vs Tryndamere) 57.31% de victoire · 12 500 games"
    " → suite attendue : Fiora (top), Thresh (support)\n"
    "  [2nd] Darius (top vs Tryndamere) 52.10% de victoire · 840 games\n"
    "  [3rd] Garen (top vs Tryndamere) 48.90% de victoire · 840 games"
    " → suite attendue : Nasus (top)\n"
    "  [SEARCH] Profondeur atteinte : 2 pick(s) anticipé(s)\n"
    "  [DATA] Sans données exploitables en top : Malphite (0 games)\n"
    "\n[ADVICE] [PICK] C'est le moment de sécuriser votre champion !\n"
)
CONSOLE_SANS_TOUR = (
    "\n[PICKS] RECOMMANDATIONS DE COUNTERPICK :\n" + "-" * 50 + "\n"
    "  [DATA] Plus aucun pick à jouer de votre côté\n"
    "  [DATA] Sans données exploitables : Malphite (0 games)\n"
    "\n[ADVICE] [PLAN] Réfléchissez à la composition d'équipe et aux priorités de ban\n"
)


def test_sortie_console_identique_avec_classement(monitor, capsys):
    with patch.object(monitor.search, "rank", return_value=RANKED):
        monitor._provide_recommendations(pick_state())
    assert capsys.readouterr().out == CONSOLE_AVEC_CLASSEMENT


def test_sortie_console_identique_sans_tour(monitor, capsys):
    state = DraftState(phase="PLANNING", enemy_picks=[64], remaining_picks=[])
    with patch.object(monitor.search, "rank", return_value=[]):
        monitor._provide_recommendations(state)
    assert capsys.readouterr().out == CONSOLE_SANS_TOUR


def test_sortie_console_identique_avec_un_bus_et_un_bus_en_panne(monitor, capsys):
    monitor.bus = Mock(publish=Mock(side_effect=RuntimeError("bus cassé")))
    with patch.object(monitor.search, "rank", return_value=RANKED):
        monitor._provide_recommendations(pick_state())  # ne lève pas
    assert capsys.readouterr().out == CONSOLE_AVEC_CLASSEMENT


# ---------- contenu du snapshot ----------


def snapshot_of(monitor, state, ranked):
    bus = EventBus()
    monitor.bus = bus
    with bus.subscribe([TOPIC]) as subscription:
        with patch.object(monitor.search, "rank", return_value=ranked):
            monitor._provide_recommendations(state)
        event = subscription.get(1)
    return event


def test_snapshot_publie_sur_le_bus_et_serialisable(monitor):
    topic, payload = snapshot_of(monitor, pick_state(), RANKED)
    assert topic == TOPIC
    json.dumps(payload)  # le SSE le sérialise tel quel
    assert payload == asdict(monitor.last_snapshot)


def test_snapshot_classement_avec_ecarts_profondeur_et_suite(monitor):
    _, payload = snapshot_of(monitor, pick_state(), RANKED)
    first = payload["recommendations"][0]
    assert first["champion"] == "Aatrox" and first["lane"] == "top"
    assert first["win_probability"] == pytest.approx(0.5731)
    assert first["games"] == 12500 and first["depth"] == 2
    assert first["variation"] == [
        {"champion": "Fiora", "lane": "top"},
        {"champion": "Thresh", "lane": "support"},
    ]
    base = payload["base_probability"]
    assert base is not None
    assert first["delta"] == pytest.approx((0.5731 - base) * 100)
    assert [r["champion"] for r in payload["recommendations"]] == [
        "Aatrox",
        "Darius",
        "Garen",
        "Sett",
    ]  # tout le classement, la console n'en montre que 3
    assert payload["skipped"] == [{"champion": "Malphite", "games": 0, "reason": "no_data"}]
    assert payload["depth"] == 2 and payload["pool"] == POOL


def test_snapshot_phase_tour_et_equipes(monitor):
    _, payload = snapshot_of(monitor, pick_state(), RANKED)
    assert payload["phase"] == "BAN_PICK" and payload["kind"] == "pick"
    assert payload["my_turn"] is True and payload["acting_cell"] == 1
    assert payload["local_role"] == "top"
    assert payload["advice"].startswith("[PICK]")
    # Sans cellules (état construit à la main), les picks tiennent lieu d'emplacements.
    assert [p["champion"] for p in payload["allies"]] == ["Alistar"]
    assert [(p["champion"], p["role"]) for p in payload["enemies"]] == [
        ("LeeSin", "jungle"),
        ("Tryndamere", "top"),
    ]


def test_snapshot_en_phase_de_bans_sans_aucun_pick(monitor):
    state = DraftState(phase="BAN_PICK", ally_bans=[266], enemy_bans=[122], current_actor=1)
    state.local_player_cell_id = 1
    _, payload = snapshot_of(monitor, state, [])
    assert payload["kind"] == "ban" and payload["my_turn"] is True
    assert payload["ally_bans"] == [{"champion_id": 266, "champion": "Aatrox", "team": "ally"}]
    assert payload["enemy_bans"][0]["champion"] == "Darius"
    assert payload["recommendations"] == [] and payload["advice"].startswith("[BAN]")


def test_snapshot_sans_bus_garde_le_dernier(monitor):
    assert monitor.bus is None
    with patch.object(monitor.search, "rank", return_value=RANKED):
        monitor._provide_recommendations(pick_state())
    assert monitor.last_snapshot.recommendations[0].champion == "Aatrox"


def test_snapshot_echec_de_construction_n_interrompt_rien(monitor, capsys):
    monitor.bus = Mock()
    monitor.loadout = None  # build_snapshot lève
    with patch.object(monitor.search, "rank", return_value=RANKED):
        monitor._provide_recommendations(pick_state())
    assert capsys.readouterr().out == CONSOLE_AVEC_CLASSEMENT
    monitor.bus.publish.assert_not_called()


def test_snapshot_etat_du_loadout(monitor):
    assert monitor.loadout.state() is None
    build = Mock(
        primary_style=8000,
        sub_style=8100,
        perks=(8005, 9111),
        shards=(5008,),
        item_blocks=(("Départ", (1055,)),),
        spells=(4, 14),
        games=120,
    )
    monitor.loadout._applied = (266, "Aatrox top", build)
    _, payload = snapshot_of(monitor, pick_state(), RANKED)
    assert payload["loadout"] == {
        "champion_id": 266,
        "label": "Aatrox top",
        "primary_style": 8000,
        "sub_style": 8100,
        "perks": [8005, 9111],
        "shards": [5008],
        "spells": [4, 14],
        "item_blocks": [{"title": "Départ", "items": [1055]}],
        "games": 120,
    }


# ---------- emplacements lus dans le LCU ----------


def test_le_parseur_remplit_les_emplacements_survols_et_temps_restant():
    lcu = Mock()
    lcu.get_assigned_positions.return_value = {0: "top", 1: "jungle"}
    data = {
        "timer": {"phase": "BAN_PICK", "adjustedTimeLeftInPhase": 27500},
        "localPlayerCellId": 0,
        "myTeam": [
            {"cellId": 0, "championId": 0, "assignedPosition": "top"},
            {"cellId": 1, "championId": 64, "championPickIntent": 0, "assignedPosition": "jungle"},
            {"cellId": 2, "championId": 0, "championPickIntent": 12},
        ],
        "theirTeam": [{"cellId": 5, "championId": 23}, {"cellId": 6, "championId": 0}],
        "actions": [
            [{"type": "pick", "actorCellId": 0, "championId": 266, "completed": False}],
            [{"type": "ban", "actorCellId": 5, "championId": 54, "completed": True}],
        ],
    }
    state, _ = DraftStateParser(lcu, lambda cid: str(cid)).parse(data, {}, {})
    assert state.time_left_ms == 27500
    mine = {cell.cell_id: cell for cell in state.ally_cells}
    assert (mine[0].champion_id, mine[0].hover_id, mine[0].position) == (0, 266, "top")
    assert (mine[1].champion_id, mine[1].position) == (64, "jungle")
    assert mine[2].hover_id == 12  # l'intention d'un allié
    assert [(c.cell_id, c.champion_id) for c in state.enemy_cells] == [(5, 23), (6, 0)]
    assert state.ally_picks == [64] and state.enemy_picks == [23]  # les listes d'avant, inchangées
