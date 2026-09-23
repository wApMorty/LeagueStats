"""SPEC-14 : la draft finale se lit en face-à-face, lane par lane.

Hermétique : évaluateur factice (duels donnés directement en points), aucun
accès à data/db.db. Un test par critère d'acceptation de SPEC-14 §5.
"""

import math
from unittest.mock import Mock, patch

import pytest

from src.config_constants import analysis_config
from src.draft.final_analysis import FinalDraftAnalyzer, duel_cell, face_offs
from src.models import Matchup

LANES_BY_ID = {
    # Picks volontairement dans le désordre : support, top, adc, jungle, mid.
    1: "support",
    2: "top",
    3: "bottom",
    4: "jungle",
    5: "middle",
    6: "support",
    7: "top",
    8: "bottom",
    9: "jungle",
    10: "middle",
}
NAMES = {
    1: "Rell",
    2: "Garen",
    3: "Jinx",
    4: "Vi",
    5: "Ahri",
    6: "Nautilus",
    7: "Darius",
    8: "Draven",
    9: "Lee Sin",
    10: "Syndra",
}
ALLY_IDS = [1, 2, 3, 4, 5]
ENEMY_IDS = [6, 7, 8, 9, 10]

# Duels directs, en points de winrate du point de vue allié. Rell/Nautilus
# n'a aucune donnée.
DUELS = {
    ("Garen", "Darius"): 3.4,
    ("Vi", "Lee Sin"): -1.3,
    ("Ahri", "Syndra"): 0.2,
    ("Jinx", "Draven"): -2.5,
}


def logit_for(points: float) -> float:
    """Inverse exact de ``_to_points`` : le tableau réaffiche ``points``."""
    p = 0.5 + points / 100.0
    return math.log(p / (1.0 - p))


class FakeEvaluator:
    def __init__(self, duels):
        self.duels = duels

    def has_matchup_data(self, champion, enemy):
        return (champion[0], enemy[0]) in self.duels or (enemy[0], champion[0]) in self.duels

    def matchup_logit(self, champion, enemy):
        if (champion[0], enemy[0]) in self.duels:
            return logit_for(self.duels[(champion[0], enemy[0])])
        if (enemy[0], champion[0]) in self.duels:
            return -logit_for(self.duels[(enemy[0], champion[0])])
        return 0.0

    def synergy_logit(self, champion, ally):
        return 0.0

    def win_probability(self, allies, enemies):
        return 0.55


def make_monitor(duels=DUELS, thin=()):
    monitor = Mock()
    monitor.verbose = False
    monitor.evaluator = FakeEvaluator(duels)
    monitor._get_display_name = lambda champ_id: NAMES[champ_id]
    games = lambda name: 0 if name in thin else 1000  # noqa: E731
    monitor.assistant.get_matchups_for_draft.side_effect = lambda name, lane=None: [
        Matchup("Dummy", 50.0, 0.0, 0.0, 5.0, games(name))
    ]
    monitor.assistant.db.insert_prediction.return_value = 42
    return monitor


def render(monitor, lanes=LANES_BY_ID, capsys=None):
    with patch("src.draft.final_analysis.clear_console"):
        FinalDraftAnalyzer(monitor).analyze(ALLY_IDS, ENEMY_IDS, ally_lanes=lanes)
    return capsys.readouterr().out


def table_lines(output):
    """Lignes de données du tableau, entre le séparateur et la légende."""
    block = output.split("FACE-À-FACE PAR LANE :")[1].split("  DUEL :")[0]
    lines = [line for line in block.splitlines() if line.strip()]
    return lines[2:]  # en-tête + séparateur


class TestOrder:
    def test_rows_follow_lane_order_whatever_the_pick_order(self, capsys):
        lines = table_lines(render(make_monitor(), capsys=capsys))
        pairs = [("Garen", "Darius"), ("Vi", "Lee Sin"), ("Ahri", "Syndra")]
        pairs += [("Jinx", "Draven"), ("Rell", "Nautilus")]
        assert len(lines) == 5
        for line, (ally, enemy) in zip(lines, pairs):
            assert f" {ally} " in line and f" {enemy} " in line


class TestDuelCell:
    @pytest.mark.parametrize(
        "points, expected",
        [
            (3.4, "<<<  +3.4"),
            (-1.3, ">    -1.3"),
            (0.2, "=    +0.2"),
            (-0.2, "=    -0.2"),
            (0.99, "=    +1.0"),
            (-0.99, "=    -1.0"),
            (1.0, "<    +1.0"),
            (-1.0, ">    -1.0"),
            (2.0, "<<   +2.0"),
            (-2.0, ">>   -2.0"),
            (3.0, "<<<  +3.0"),
            (-3.0, ">>>  -3.0"),
            (0.0, "=    +0.0"),
        ],
    )
    def test_arrow_points_to_the_winner_with_its_value(self, points, expected):
        assert duel_cell(points) == expected

    def test_the_table_shows_the_duel(self, capsys):
        lines = table_lines(render(make_monitor(), capsys=capsys))
        assert "<<<  +3.4" in lines[0]
        assert ">    -1.3" in lines[1]
        assert ">>   -2.5" in lines[3]


class TestNoData:
    def test_unmeasured_duel_is_a_question_mark_not_a_tie(self, capsys):
        rell_line = table_lines(render(make_monitor(), capsys=capsys))[4]
        assert "?" in rell_line
        assert "=" not in rell_line
        assert duel_cell(None) == "?"


class TestAmbiguousLanes:
    def test_shared_or_unknown_lane_goes_last_without_pairing(self):
        allies = [("A-top", "top"), ("A-mid1", "middle"), ("A-mid2", "middle")]
        enemies = [("E-top", "top"), ("E-mid", "middle"), ("E-none", None)]
        assert face_offs(allies, enemies) == [
            (0, 0, True),  # top : apparié
            (None, 1, False),  # mid ennemi seul : ses deux vis-à-vis sont ambigus
            (1, 2, False),  # restes, dans l'ordre des picks, jamais appariés
            (2, None, False),
        ]

    def test_ambiguous_rows_never_show_a_duel(self, capsys):
        lanes = {**LANES_BY_ID, 2: "middle", 7: None}  # Garen mid, Darius sans lane
        lines = table_lines(render(make_monitor(), lanes=lanes, capsys=capsys))
        garen = next(line for line in lines if " Garen " in line)
        darius = next(line for line in lines if " Darius " in line)
        ahri = next(line for line in lines if " Ahri " in line)
        assert "?" in garen and "?" in darius and "?" in ahri
        assert lines.index(garen) >= 3  # relégué après les lanes appariées


class TestInsufficientData:
    def test_thin_champion_keeps_its_row_and_duel(self, capsys):
        lines = table_lines(render(make_monitor(thin={"Garen"}), capsys=capsys))
        assert "peu de données" in lines[0]
        assert " Garen " in lines[0] and " Darius " in lines[0]
        assert "<<<  +3.4" in lines[0]


class TestWidthAndEncoding:
    def test_no_table_line_exceeds_80_columns(self, capsys):
        names = {**NAMES, 2: "Nunu & Willump", 7: "Aurelion Sol12"}
        duels = {("Nunu & Willump", "Aurelion Sol12"): -12.5}
        monitor = make_monitor(duels=duels, thin={"Jinx", "Draven"})
        monitor._get_display_name = lambda champ_id: names[champ_id]
        output = render(monitor, capsys=capsys)
        block = output.split("FACE-À-FACE PAR LANE :")[1].split("COMPARAISON")[0]
        assert all(len(line) <= 80 for line in block.splitlines())
        assert ">>> -12.5" in block

    def test_output_encodes_in_cp1252(self, capsys):
        render(make_monitor(), capsys=capsys).encode("cp1252")


class TestCalibrationUnchanged:
    def test_prediction_arguments_are_unchanged(self, capsys):
        monitor = make_monitor()
        render(monitor, capsys=capsys)
        monitor.assistant.db.insert_prediction.assert_called_once_with(
            ally_champions=ALLY_IDS,
            enemy_champions=ENEMY_IDS,
            ally_lanes=LANES_BY_ID,
            predicted_probability=0.55,
            model_version=analysis_config.MODEL_VERSION,
        )
        assert monitor._last_prediction_id == 42
