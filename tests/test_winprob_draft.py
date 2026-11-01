"""A priori de draft de la win chance (`src/winprob/draft.py`, SPEC-33 §7).

Aucune vraie base : l'évaluateur est un faux qui note la composition reçue.
"""

import sqlite3

import pytest

from src.db import Database
from src.winprob import draft
from src.winprob.draft import _live_teams, game_draft, live_draft, recorded_draft
from src.winprob.impact import impacts
from src.winprob.model import INPUTS, MODEL_INPUTS, WinModel, expand
from src.winprob.overlay import Tracker
from src.winprob.report import curve_points
from src.winprob.state import BLUE, RED
from src.winprob.train import draft_reader
from tests.test_winprob_impact import GAME, TIMELINE

LANES = ("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY")


class _Evaluator:
    """Note les compositions reçues, rend toujours 0,5."""

    def __init__(self):
        self.calls = []

    def team_logit(self, allies, enemies):
        self.calls.append((allies, enemies))
        return 0.5


def _model():
    """Le logit vaut `draft`, sans effet du temps ni des autres variables."""
    d = 2 * len(MODEL_INPUTS)
    weights = [0.0] * (d + 1)
    weights[MODEL_INPUTS.index("draft")] = 1.0
    return WinModel(MODEL_INPUTS, [0.0] * d, [1.0] * d, weights)


def _game(queue=420):
    """Dix joueurs ; `participant_roles` est remplacé par les tests qui en dépendent."""
    return {
        "queueId": queue,
        "participants": [
            {"participantId": i, "teamId": BLUE if i <= 5 else RED, "championId": i}
            for i in range(1, 11)
        ],
    }


def _live(positions=LANES):
    players = [
        {
            "team": team,
            "rawChampionName": f"game_character_displayname_C{team}{i}",
            "position": position,
        }
        for team in ("ORDER", "CHAOS")
        for i, position in enumerate(positions)
    ]
    return {"allPlayers": players}


def test_sans_draft_le_modele_reste_neutre():
    state = dict.fromkeys(INPUTS, 0.0) | {"time_min": 10.0}

    assert expand(state, MODEL_INPUTS) == expand({**state, "draft": 0.0}, MODEL_INPUTS)
    assert _model().logit(state) == 0.0


def test_le_modele_lit_la_draft_quand_elle_est_la():
    state = dict.fromkeys(INPUTS, 0.0) | {"time_min": 10.0, "draft": 0.7}

    assert _model().logit(state) == 0.7


def test_game_draft_range_les_equipes_du_point_de_vue_bleu(monkeypatch):
    monkeypatch.setattr(
        "src.winprob.draft.participant_roles",
        lambda game: {i: _ROLES[(i - 1) % 5] for i in range(1, 11)},
    )
    evaluator = _Evaluator()
    names = {i: f"C{i}" for i in range(1, 11)}

    assert game_draft(_game(), (evaluator, names)) == 0.5

    allies, enemies = evaluator.calls[0]
    assert allies[0] == ("C1", "top") and len(allies) == 5
    assert enemies[0] == ("C6", "top") and len(enemies) == 5


def test_game_draft_nul_hors_file_classee_ou_a_poste_inconnu(monkeypatch):
    monkeypatch.setattr(
        "src.winprob.draft.participant_roles",
        lambda game: {p["participantId"]: "top" for p in game["participants"]},
    )
    assert game_draft(_game(queue=450), (_Evaluator(), {})) == 0.0

    monkeypatch.setattr("src.winprob.draft.participant_roles", lambda game: {1: None})
    assert game_draft(_game(), (_Evaluator(), {})) == 0.0


def test_recorded_draft_base_illisible_rend_zero(tmp_path):
    assert recorded_draft(_game(), tmp_path / "absente.db") == 0.0


def test_live_teams_retire_le_prefixe_et_traduit_les_postes():
    teams = _live_teams(_live())

    assert teams[BLUE][0] == ("CORDER0", "top")
    assert teams[RED][4] == ("CCHAOS4", "support")


def test_live_draft_attend_les_dix_postes(tmp_path):
    assert live_draft(_live(("TOP", "JUNGLE", "MIDDLE", "BOTTOM", "")), tmp_path / "x.db") is None


def test_live_draft_base_illisible_ne_coupe_pas_la_win_chance(tmp_path):
    assert live_draft(_live(), tmp_path / "absente.db") == 0.0


def _live_state(data):
    return {
        **data,
        "gameData": {"gameTime": 0.0},
        "events": {"Events": []},
        "activePlayer": {},
    }


def test_tracker_lit_la_draft_une_fois_et_l_ajoute_a_la_prediction():
    calls = []

    def draft_of(data):
        calls.append(data)
        return 1.0

    players = [
        {
            "team": team,
            "level": 1,
            "scores": {"creepScore": 0},
            "isDead": False,
            "respawnTimer": 0.0,
            "summonerName": f"{team}{i}",
        }
        for team in ("ORDER", "CHAOS")
        for i in range(5)
    ]
    data = _live_state({"allPlayers": players})
    tracker = Tracker(_model(), draft_of)

    first = tracker.update(data)
    tracker.update(data)

    assert first["p"] > 0.7
    assert len(calls) == 1


def test_postes_manquants_la_draft_est_relue_au_tour_suivant():
    answers = [None, 1.0]
    players = [
        {
            "team": team,
            "level": 1,
            "scores": {"creepScore": 0},
            "isDead": False,
            "respawnTimer": 0.0,
            "summonerName": f"{team}{i}",
        }
        for team in ("ORDER", "CHAOS")
        for i in range(5)
    ]
    data = _live_state({"allPlayers": players})
    tracker = Tracker(_model(), lambda _: answers.pop(0))

    assert tracker.update(data)["p"] == 0.5
    assert tracker.update(data)["p"] > 0.7


def test_la_courbe_part_de_la_draft(monkeypatch):
    monkeypatch.setattr(
        "src.winprob.report.frame_states",
        lambda game, timeline: [dict.fromkeys(INPUTS, 0.0) | {"time_min": 0.0}],
    )

    ((_, neutre),) = curve_points(_model(), {}, {}, BLUE)
    ((_, favori),) = curve_points(_model(), {}, {}, BLUE, 1.0)
    ((_, adverse),) = curve_points(_model(), {}, {}, RED, 1.0)

    assert neutre == 0.5
    assert favori > 0.7
    assert adverse == 1 - favori


_ROLES = ("top", "jungle", "middle", "bottom", "support")


def test_postes_en_double_pas_de_draft():
    assert _live_teams(_live(("TOP", "TOP", "MIDDLE", "BOTTOM", "UTILITY"))) is None

    double = ("top", "top", "middle", "bottom", "support")
    roles = {i: double[(i - 1) % 5] for i in range(1, 11)}
    assert game_draft(_game(), (_Evaluator(), {}), roles) == 0.0


def test_game_draft_prend_les_postes_donnes(monkeypatch):
    monkeypatch.setattr(draft, "participant_roles", lambda _game: pytest.fail("postes donnés"))
    evaluator = _Evaluator()
    roles = {i: _ROLES[(i - 1) % 5] for i in range(1, 11)}

    assert game_draft(_game(), (evaluator, {1: "Gnar"}), roles) == 0.5
    assert evaluator.calls[0][0][0] == ("Gnar", "top")


def test_lire_la_base_n_ecrit_rien(tmp_path):
    """`Database.connect` crée ses index : la lecture de la draft ne doit pas passer par lui."""
    path = tmp_path / "db.db"
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE champions (id INTEGER PRIMARY KEY, key TEXT, name TEXT)")
    db.commit()
    db.close()
    before = path.read_bytes()

    readonly = Database(str(path))
    readonly.connect_read_only()
    with pytest.raises(sqlite3.OperationalError):
        readonly.connection.execute("CREATE INDEX x ON champions(name)")
    readonly.close()

    assert path.read_bytes() == before


def test_draft_reader_leve_si_la_base_ne_se_lit_pas(monkeypatch, tmp_path):
    monkeypatch.setattr(draft.config, "DATABASE_PATH", str(tmp_path / "absente.db"))
    with pytest.raises(OSError):
        draft_reader()


def test_impacts_neutres_quel_que_soit_le_poids_de_la_draft():
    def model(weight):
        d = 2 * len(MODEL_INPUTS)
        weights = [0.0] * (d + 1)
        weights[MODEL_INPUTS.index("kills")] = 0.5
        weights[MODEL_INPUTS.index("draft")] = weight
        return WinModel(MODEL_INPUTS, [0.0] * d, [1.0] * d, weights)

    assert (
        impacts(model(0.0), GAME, TIMELINE)["rows"] == impacts(model(2.0), GAME, TIMELINE)["rows"]
    )
