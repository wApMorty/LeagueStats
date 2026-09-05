"""Tests for src/ui/tier_list_ui.py's display helper.

SPEC-09 E5: the tier list screen showed a score per champion with no
indicator of how much data backed it, unlike the Live Coach
(recommendations.py, "· 91 696 games"). _display_tier_list() now accepts an
optional games_by_champion map and prints the same volume tag when given.
"""

from src.ui.tier_list_ui import _display_tier_list


def _entry(champion, score=90.0, tier="S"):
    return {
        "champion": champion,
        "score": score,
        "tier": tier,
        "metrics": {
            "avg_delta2_raw": 1.5,
            "variance": 0.4,
            "coverage_raw": 0.6,
            "stability": 0.7,
        },
    }


def test_games_volume_shown_when_provided(capsys):
    tier_list = [_entry("Ahri")]

    _display_tier_list(
        tier_list,
        "Test Pool",
        "BLIND PICK",
        "blind_pick",
        "middle",
        games_by_champion={"Ahri": 91696},
    )

    out = capsys.readouterr().out
    assert "91 696 games" in out


def test_no_games_volume_line_when_map_absent(capsys):
    """Backward compatible: no games_by_champion argument -> unchanged
    display, no crash (regression guard for existing callers/tests)."""
    tier_list = [_entry("Ahri")]

    _display_tier_list(tier_list, "Test Pool", "BLIND PICK", "blind_pick", "middle")

    out = capsys.readouterr().out
    assert "games" not in out


def test_missing_champion_in_map_is_silently_skipped(capsys):
    """A champion absent from games_by_champion (best-effort lookup failure)
    must not crash the display — no volume tag, nothing else."""
    tier_list = [_entry("Ahri")]

    _display_tier_list(
        tier_list, "Test Pool", "BLIND PICK", "blind_pick", "middle", games_by_champion={}
    )

    out = capsys.readouterr().out
    assert "games" not in out
    assert "Ahri" in out
