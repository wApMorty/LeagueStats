"""Characterization tests for the FULL console output of
``DraftMonitor._calculate_final_scores`` (SPEC TODO E10 safety net, SPEC-12).

``tests/test_predictions_log.py`` already covers the prediction-logging side
effect of this method. This file complements it by pinning the rendered team
tables, the sorting, the strength markers and the draft verdict — i.e. what
the user actually sees at the end of a draft.

Le 5v5 ci-dessous est entièrement déterministe et les attendus sont calculés à
la main depuis la formule de SPEC-12, pas recopiés depuis une exécution :

    confidence(500 games)          = 500 / (500 + CONFIDENCE_K=500) = 0.5
    matchup_logit(delta2)          = delta2 * K_MATCHUP(1.0) * 0.04 * 1.0 * 0.5
                                   = delta2 * 0.02
    synergy_logit(delta2)          = delta2 * K_SYNERGY(0.5) * 0.04 * 0.5
                                   = delta2 * 0.01
    colonne affichée (points)      = (sigmoid(logit) - 0.5) * 100

Aucune lane n'est fournie : toutes les paires pèsent OTHER_LANE_WEIGHT = 1.0.
"""

from unittest.mock import Mock, patch

import pytest

from src.analysis.probability import sigmoid
from src.config_constants import analysis_config
from src.draft_monitor import DraftMonitor
from src.models import Matchup

ALLY_IDS = [1, 2, 3, 4, 5]
ENEMY_IDS = [6, 7, 8, 9, 10]

NAMES = {
    1: "Ally1",
    2: "Ally2",
    3: "Ally3",
    4: "Ally4",
    5: "Ally5",
    6: "Enemy6",
    7: "Enemy7",
    8: "Enemy8",
    9: "Enemy9",
    10: "Enemy10",
}

GAMES = 500  # -> confidence = 0.5

# Seul Enemy6 a des matchups renseignés, dans un seul sens : les autres paires
# valent 0. Somme des delta2 = +2, donc l'équipe alliée est légèrement devant.
ALLY_DELTA2_VS_ENEMY6 = {"Ally1": 10.0, "Ally2": 5.0, "Ally3": 0.0, "Ally4": -5.0, "Ally5": -8.0}
MATCHUPS = {
    (ally.lower(), "enemy6"): (delta2, GAMES) for ally, delta2 in ALLY_DELTA2_VS_ENEMY6.items()
}

# Toutes les paires d'une même équipe valent +2.0 : chaque champion a donc
# 4 coéquipiers * synergy_logit(2.0) = 4 * 0.02 = 0.08 de log-odds.
SYNERGY_PER_PAIR = 2.0
TEAM = [name.lower() for name in NAMES.values()]
SYNERGIES = {(a, b): (SYNERGY_PER_PAIR, GAMES) for a in TEAM for b in TEAM if a != b}


def points(logit: float) -> float:
    """Log-odds -> points de winrate affichés."""
    return (sigmoid(logit) - 0.5) * 100.0


# Log-odds attendus, par champion.
ALLY_MATCHUP_LOGIT = {name: delta2 * 0.02 for name, delta2 in ALLY_DELTA2_VS_ENEMY6.items()}
SYNERGY_LOGIT = 4 * SYNERGY_PER_PAIR * 0.01  # 0.08
# Enemy6 subit l'opposé de la somme alliée ; Enemy7-10 n'ont aucun matchup.
ENEMY_MATCHUP_LOGIT = {
    "Enemy6": -sum(ALLY_MATCHUP_LOGIT.values()),
    "Enemy7": 0.0,
    "Enemy8": 0.0,
    "Enemy9": 0.0,
    "Enemy10": 0.0,
}
# Le logit d'équipe ne retient que les paires allié x ennemi : les synergies
# des deux camps sont identiques ici, donc s'annulent.
TEAM_LOGIT = sum(ALLY_MATCHUP_LOGIT.values())


@pytest.fixture
def monitor():
    """DraftMonitor wired on a deterministic, fully mocked Assistant."""
    with patch("src.draft_monitor.Assistant", return_value=Mock()):
        with patch("src.draft_monitor.LCUClient", return_value=Mock()):
            monitor = DraftMonitor(verbose=False, auto_hover=False)

    monitor.champion_id_to_name = dict(NAMES)

    # Volume suffisant pour tout le monde : aucune ligne "données insuffisantes".
    monitor.assistant.get_matchups_for_draft.side_effect = lambda name, lane=None: [
        Matchup("Dummy", 50.0, 0.0, 0.0, 5.0, 1000)
    ]
    monitor.assistant.db.get_all_matchups_bulk.return_value = MATCHUPS
    monitor.assistant.db.get_all_synergies_bulk.return_value = SYNERGIES
    monitor.assistant.db.insert_prediction.return_value = 7
    return monitor


@pytest.fixture
def output(monitor, capsys):
    """Run the analysis once and return the captured stdout."""
    with patch("src.draft.final_analysis.clear_console"):
        monitor._calculate_final_scores(ALLY_IDS, ENEMY_IDS, ally_lanes=None)
    return capsys.readouterr().out


def row(name: str, matchup_logit: float, synergy_logit: float) -> str:
    """Reconstruit la ligne attendue, marqueurs compris."""

    def marker(score: float) -> str:
        if score >= 2.0:
            return "[++]"
        if score >= 1.0:
            return "[+]"
        if score >= -1.0:
            return "[~]"
        if score >= -2.0:
            return "[-]"
        return "[--]"

    matchup, synergy = points(matchup_logit), points(synergy_logit)
    total = points(matchup_logit + synergy_logit)
    return (
        f"  {name:<15} | {marker(matchup)} {matchup:+5.1f} | "
        f"{marker(synergy)} {synergy:+5.1f} | {marker(total)} {total:+5.1f}"
    )


class TestFinalScoresHeader:
    def test_header_block(self, output):
        assert "ANALYSE FINALE DU DRAFT - Scores individuels des champions" in output
        assert "=" * 80 in output

    def test_final_composition(self, output):
        assert "[TEAMS] COMPOSITION FINALE :" in output
        assert "  Équipe alliée :  Ally1 | Ally2 | Ally3 | Ally4 | Ally5" in output
        assert "  Équipe ennemie : Enemy6 | Enemy7 | Enemy8 | Enemy9 | Enemy10" in output

    def test_performance_section_title(self, output):
        assert "ANALYSE DE PERFORMANCE D'ÉQUIPE :" in output


class TestFinalScoresAllyTable:
    """The ally table: header, rows, sorting and strength markers."""

    def test_table_header(self, output):
        assert "VOTRE ÉQUIPE :" in output
        assert "  Champion        | Matchup | Synergy | Total" in output
        assert "  ----------------+---------+---------+-------" in output

    @pytest.mark.parametrize("name", list(ALLY_DELTA2_VS_ENEMY6))
    def test_rows_are_rendered_with_markers(self, output, name):
        assert row(name, ALLY_MATCHUP_LOGIT[name], SYNERGY_LOGIT) in output

    def test_rows_are_sorted_by_total_descending(self, output):
        positions = [output.index(f"  Ally{i}           |") for i in range(1, 6)]
        assert positions == sorted(positions)


class TestFinalScoresEnemyTable:
    """The enemy table mirrors the ally one."""

    def test_table_header(self, output):
        assert "ÉQUIPE ENNEMIE :" in output

    @pytest.mark.parametrize("name", list(ENEMY_MATCHUP_LOGIT))
    def test_rows_are_rendered_with_markers(self, output, name):
        assert row(name, ENEMY_MATCHUP_LOGIT[name], SYNERGY_LOGIT) in output

    def test_the_punished_enemy_ranks_last(self, output):
        """Enemy6 est le seul à subir des matchups : il ferme la marche."""
        enemy_block = output.split("ÉQUIPE ENNEMIE :")[1]
        positions = [enemy_block.index(f"  Enemy{i}") for i in (7, 8, 9, 10, 6)]
        assert positions == sorted(positions)


class TestFinalScoresComparison:
    """Team comparison and verdict — SPEC-12 : plus de normalisation."""

    def test_win_probability_is_the_model_probability(self, output):
        expected = sigmoid(TEAM_LOGIT) * 100.0
        assert f"  Probabilité de victoire estimée : {expected:.2f}%" in output
        assert f"  Probabilité adverse : {100.0 - expected:.2f}%" in output

    def test_the_two_sides_sum_to_one_hundred(self, output):
        """L'antisymétrie du modèle, visible à l'écran : plus de rapport
        allié / (allié + ennemi) pour rattraper deux nombres incohérents."""
        ours = float(output.split("Probabilité de victoire estimée : ")[1].split("%")[0])
        theirs = float(output.split("  Probabilité adverse : ")[1].split("%")[0])
        assert ours + theirs == pytest.approx(100.0, abs=0.01)

    def test_verdict_bracket(self, output):
        """draft_diff = (2 * 0.51 - 1) * 100 = +2.00 -> bracket [-2.5, 2.5)."""
        diff = (2.0 * sigmoid(TEAM_LOGIT) - 1.0) * 100.0
        assert f"  Évaluation : Draft équilibré ({diff:+.2f}% de différence)" in output

    def test_prediction_is_logged_with_the_model_probability(self, monitor):
        with patch("src.draft.final_analysis.clear_console"):
            monitor._calculate_final_scores(ALLY_IDS, ENEMY_IDS, ally_lanes={1: "top"})

        kwargs = monitor.assistant.db.insert_prediction.call_args.kwargs
        assert kwargs["ally_champions"] == ALLY_IDS
        assert kwargs["enemy_champions"] == ENEMY_IDS
        assert kwargs["ally_lanes"] == {1: "top"}
        assert kwargs["predicted_probability"] == pytest.approx(sigmoid(TEAM_LOGIT))
        assert monitor._last_prediction_id == 7

    def test_prediction_uses_the_spec12_model_version(self, monitor):
        """Sans nouvelle version, calibrate_model.py mélangerait les
        prédictions du modèle par delta et celles de la recherche."""
        with patch("src.draft.final_analysis.clear_console"):
            monitor._calculate_final_scores(ALLY_IDS, ENEMY_IDS)

        kwargs = monitor.assistant.db.insert_prediction.call_args.kwargs
        assert kwargs["model_version"] == analysis_config.MODEL_VERSION
        assert kwargs["model_version"] != "b7-v1"
