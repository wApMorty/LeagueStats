"""Métriques du coach de gameplay (SPEC-19 tâche 31, src/coaching/metrics.py).

Hermétiques : fixtures anonymisées du spike du 2026-09-28 (Olaf top, 24 min 48).
"""

import copy
import json
from pathlib import Path

import pytest

from src.coaching.metrics import compute_metrics, is_remake, participant_roles

FIXTURES = Path(__file__).parent / "fixtures" / "spike_gameplay"
GAME = json.loads((FIXTURES / "7998195590_game.json").read_text(encoding="utf-8"))
TIMELINE = json.loads((FIXTURES / "7998195590_timeline.json").read_text(encoding="utf-8"))
EOG = json.loads((FIXTURES / "eog_stats_block.json").read_text(encoding="utf-8"))
ROLES = ["top", "jungle", "middle", "bottom", "support"]


def _values(rows, pid):
    return {row.metric: row.value for row in rows if row.participant_id == pid}


def _event(kind, killer, victim=0, assists=(), timestamp=0, monster=""):
    return {
        "type": kind,
        "killerId": killer,
        "victimId": victim,
        "assistingParticipantIds": list(assists),
        "timestamp": timestamp,
        "monsterType": monster,
    }


class TestRoles:
    def test_end_of_game_screen_gives_every_position(self):
        roles = participant_roles(GAME, EOG)
        assert [roles[pid] for pid in range(1, 11)] == ROLES * 2

    def test_role_bound_item_gives_the_same_positions_without_it(self):
        roles = participant_roles(GAME)
        assert [roles[pid] for pid in range(1, 11)] == ROLES * 2

    def test_last_unknown_of_a_team_takes_the_last_free_position(self):
        game = copy.deepcopy(GAME)
        game["participants"][0]["stats"]["roleBoundItem"] = 0  # top inconnu
        assert participant_roles(game)[1] == "top"

    def test_two_unknowns_stay_unknown_rather_than_guessed(self):
        game = copy.deepcopy(GAME)
        for index in (0, 2):  # top et mid, sans Châtiment
            game["participants"][index]["stats"]["roleBoundItem"] = 0
        roles = participant_roles(game)
        assert roles[1] is None and roles[3] is None
        assert roles[2] == "jungle"


class TestMetrics:
    def test_per_minute_values_from_the_game_detail(self):
        mine = _values(compute_metrics(GAME, TIMELINE, EOG), 1)
        minutes = 1488 / 60
        assert mine["cs_per_min"] == pytest.approx((181 + 4) / minutes)
        assert mine["deaths_per_10"] == pytest.approx(5 / minutes * 10)
        assert mine["structure_damage_per_min"] == pytest.approx(13646 / minutes)
        team_kills = sum(p["stats"]["kills"] for p in GAME["participants"] if p["teamId"] == 100)
        assert mine["kill_participation"] == pytest.approx((11 + 4) / team_kills)

    def test_timeline_values_at_fixed_minutes_face_the_direct_opponent(self):
        mine = _values(compute_metrics(GAME, TIMELINE, EOG), 1)
        at_15 = TIMELINE["frames"][15]["participantFrames"]
        at_10 = TIMELINE["frames"][10]["participantFrames"]["1"]
        assert mine["gold_diff_15"] == at_15["1"]["totalGold"] - at_15["6"]["totalGold"]
        assert mine["xp_diff_15"] == at_15["1"]["xp"] - at_15["6"]["xp"]
        assert mine["cs_10"] == at_10["minionsKilled"] + at_10["jungleMinionsKilled"]

    def test_deaths_and_objectives_from_the_timeline_events(self):
        timeline = copy.deepcopy(TIMELINE)
        for frame in timeline["frames"]:
            frame["events"] = []
        timeline["frames"][5]["events"] = [
            _event("CHAMPION_KILL", killer=6, victim=1, timestamp=300_000),  # solo
            _event("CHAMPION_KILL", killer=0, victim=1, timestamp=400_000),  # tour
            _event("ELITE_MONSTER_KILL", killer=2, assists=[1], monster="DRAGON"),
            _event("ELITE_MONSTER_KILL", killer=2, monster="HORDE"),
            _event("ELITE_MONSTER_KILL", killer=7, monster="BARON_NASHOR"),
        ]
        timeline["frames"][20]["events"] = [
            _event("CHAMPION_KILL", killer=7, victim=1, assists=[6], timestamp=1_200_000)
        ]
        rows = compute_metrics(GAME, timeline, EOG)
        mine, theirs = _values(rows, 1), _values(rows, 6)
        assert mine["deaths_before_14"] == 2
        assert mine["solo_deaths"] == 1
        assert mine["objective_presence"] == pytest.approx(0.5)
        assert theirs["objective_presence"] == 0

    def test_no_timeline_omits_its_metrics_instead_of_zeroing_them(self):
        mine = _values(compute_metrics(GAME, None, EOG), 1)
        assert "cs_per_min" in mine
        assert not {"cs_10", "gold_diff_15", "deaths_before_14"} & set(mine)

    def test_every_participant_gets_rows(self):
        rows = compute_metrics(GAME, TIMELINE, EOG)
        assert {row.participant_id for row in rows} == set(range(1, 11))

    def test_remake_is_not_judged(self):
        game = copy.deepcopy(GAME)
        game["participants"][3]["stats"]["gameEndedInEarlySurrender"] = True
        assert is_remake(game)
        assert compute_metrics(game, TIMELINE) == []
