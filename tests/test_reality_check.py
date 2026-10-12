"""Tests de src/draft/reality_check.py : résolution des champions, lanes réelles, comparaison (SPEC-27 §6.2-3)."""

from src.draft.reality_check import compare, real_lanes, resolve_champions


def _entry(champion: str, raw: str, team: str, position: str) -> dict:
    return {"champion": champion, "raw": raw, "team": team, "position": position}


def _team(team: str, positions: list) -> list:
    return [_entry(f"Champ{team}{i}", f"Raw{team}{i}", team, p) for i, p in enumerate(positions)]


ROSTER = [
    _entry("Wukong", "MonkeyKing", "ORDER", "JUNGLE"),
    _entry("Nunu & Willump", "Nunu", "ORDER", "JUNGLE"),
    _entry("Renata Glasc", "Renata", "CHAOS", "UTILITY"),
    _entry("Lee Sin", "LeeSin", "CHAOS", "JUNGLE"),
    _entry("Twisted Fate", "TwistedFate", "ORDER", "MIDDLE"),
]


class TestResolveChampions:
    def test_five_names_resolved_via_raw_or_champion(self):
        names = {
            1: "Wukong",
            2: "Nunu & Willump",
            3: "Renata Glasc",
            4: "Lee Sin",
            5: "Twisted Fate",
        }
        resolved = resolve_champions(ROSTER, names)
        assert resolved[1]["champion"] == "Wukong"
        assert resolved[2]["champion"] == "Nunu & Willump"
        assert resolved[3]["champion"] == "Renata Glasc"
        assert resolved[4]["champion"] == "Lee Sin"
        assert resolved[5]["champion"] == "Twisted Fate"

    def test_display_name_matches_raw_key(self):
        roster = [_entry("Wukong", "MonkeyKing", "ORDER", "JUNGLE")]
        assert resolve_champions(roster, {1: "Monkey King"})[1]["champion"] == "Wukong"

    def test_display_name_matches_champion_key(self):
        roster = [_entry("Nunu & Willump", "Nunu", "ORDER", "JUNGLE")]
        assert resolve_champions(roster, {2: "Nunu & Willump"})[2]["champion"] == "Nunu & Willump"

    def test_unknown_name_absent(self):
        assert resolve_champions(ROSTER, {9: "Aatrox"}) == {}

    def test_ambiguous_name_absent(self):
        roster = [
            _entry("Lee Sin", "LeeSin", "ORDER", "JUNGLE"),
            _entry("Lee Sin", "LeeSin", "CHAOS", "JUNGLE"),
        ]
        assert resolve_champions(roster, {4: "Lee Sin"}) == {}

    def test_raw_match_takes_precedence_over_champion_match(self):
        roster = [
            _entry("Wukong", "MonkeyKing", "ORDER", "JUNGLE"),
            _entry("MonkeyKing", "Other", "CHAOS", "TOP"),
        ]
        assert resolve_champions(roster, {1: "MonkeyKing"})[1]["team"] == "ORDER"


class TestRealLanes:
    def test_complete_valid_team_kept(self):
        roster = _team("ORDER", ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"])
        resolved = resolve_champions(roster, {i: r["champion"] for i, r in enumerate(roster)})
        lanes = real_lanes(resolved)
        assert sorted(lanes.values()) == ["bottom", "jungle", "middle", "support", "top"]
        assert len(lanes) == 5

    def test_team_with_four_positions_dropped(self):
        roster = _team("ORDER", ["TOP", "JUNGLE", "MIDDLE", "BOTTOM"]) + _team(
            "CHAOS", ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", "UTILITY"]
        )
        resolved = resolve_champions(roster, {i: r["champion"] for i, r in enumerate(roster)})
        lanes = real_lanes(resolved)
        assert len(lanes) == 5
        assert all(resolved[c]["team"] == "CHAOS" for c in lanes)

    def test_duplicate_position_drops_team(self):
        roster = _team("ORDER", ["TOP", "JUNGLE", "MIDDLE", "MIDDLE", "UTILITY"])
        resolved = resolve_champions(roster, {i: r["champion"] for i, r in enumerate(roster)})
        assert real_lanes(resolved) == {}

    def test_empty_position_drops_team(self):
        roster = _team("ORDER", ["TOP", "JUNGLE", "MIDDLE", "BOTTOM", ""])
        resolved = resolve_champions(roster, {i: r["champion"] for i, r in enumerate(roster)})
        assert real_lanes(resolved) == {}


class TestCompare:
    def test_all_match(self):
        result = compare({1: "top", 2: "jungle"}, {1: "top", 2: "jungle"})
        assert result == {"checked": 2, "mismatches": [], "unverified": []}

    def test_middle_bottom_swap_detected(self):
        result = compare({1: "middle", 2: "bottom"}, {1: "bottom", 2: "middle"})
        assert result["checked"] == 2
        assert {m["champion_id"] for m in result["mismatches"]} == {1, 2}
        assert {"champion_id": 1, "predicted": "middle", "real": "bottom"} in result["mismatches"]

    def test_unverified_and_extra_real_ignored(self):
        result = compare({1: "top", 2: "jungle"}, {1: "top", 3: "support"})
        assert result == {"checked": 1, "mismatches": [], "unverified": [2]}
