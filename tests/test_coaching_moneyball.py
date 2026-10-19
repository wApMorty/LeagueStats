"""Étude Moneyball, actions et lignes par rôle (SPEC-35 tâche 171, `src/coaching/moneyball.py`).

Hermétique : parties construites sur la fixture spike 7998195590 (queue 420, 24 min 48 s, dix postes
connus) et sur des copies modifiées par `copy.deepcopy`. Aucune base, aucun réseau.
"""

import copy
import json
import math
import random
from pathlib import Path

import pytest

from src.coaching.moneyball import lane_rows, player_actions, player_gaps, value_actions

FIXTURES = Path(__file__).parent / "fixtures" / "spike_gameplay"
GAME = json.loads((FIXTURES / "7998195590_game.json").read_text(encoding="utf-8"))
TIMELINE = json.loads((FIXTURES / "7998195590_timeline.json").read_text(encoding="utf-8"))
ROLES = {"top", "jungle", "middle", "bottom", "support"}


def _kill(timestamp: int, killer: int, victim: int, assists=()) -> dict:
    return {
        "type": "CHAMPION_KILL",
        "timestamp": timestamp,
        "killerId": killer,
        "victimId": victim,
        "assistingParticipantIds": list(assists),
    }


def _with_events(events: list) -> dict:
    """Timeline de la fixture dont seuls `events` restent (posés à la première image)."""
    timeline = copy.deepcopy(TIMELINE)
    for frame in timeline["frames"]:
        frame["events"] = []
    timeline["frames"][0]["events"] = list(events)
    return timeline


def _find_kill(timeline: dict, timestamp: int) -> dict:
    return next(
        e
        for frame in timeline["frames"]
        for e in frame["events"]
        if e["type"] == "CHAMPION_KILL" and e["timestamp"] == timestamp
    )


# ---------- 1. player_actions ----------


def test_cs_at_14_min_is_minions_plus_jungle_of_the_14th_image():
    frame = TIMELINE["frames"][14]["participantFrames"]["1"]
    expected = frame["minionsKilled"] + frame["jungleMinionsKilled"]

    assert player_actions(GAME, TIMELINE, 14)[1]["cs"] == expected


def test_death_added_after_14_min_is_not_counted():
    base = player_actions(GAME, TIMELINE, 14)
    timeline = copy.deepcopy(TIMELINE)
    timeline["frames"][-1]["events"].append(_kill(15 * 60_000 + 1_000, 6, 1))

    after = player_actions(GAME, timeline, 14)

    assert after[1]["deaths"] == base[1]["deaths"]
    assert after[1]["solo_deaths"] == base[1]["solo_deaths"]


def test_death_with_assist_is_not_solo_and_without_assist_it_is():
    base = player_actions(GAME, TIMELINE, 14)

    with_assist = copy.deepcopy(TIMELINE)
    _find_kill(with_assist, 118_175)["assistingParticipantIds"] = [5]  # 6 tue 1, sans assistant
    assert player_actions(GAME, with_assist, 14)[6]["solo_deaths"] == base[6]["solo_deaths"] - 1

    without = copy.deepcopy(TIMELINE)
    _find_kill(without, 564_794)["assistingParticipantIds"] = []  # 1 tue 6, avec assistant ôté
    after = player_actions(GAME, without, 14)
    assert after[6]["solo_deaths"] == base[6]["solo_deaths"] + 1
    assert after[6]["deaths"] == base[6]["deaths"]


def test_presence_is_one_inside_the_radius_of_an_allied_dragon_and_zero_outside():
    timeline = copy.deepcopy(TIMELINE)
    dragon = next(
        e
        for frame in timeline["frames"]
        for e in frame["events"]
        if e["type"] == "ELITE_MONSTER_KILL" and e["timestamp"] == 664_279
    )
    for frame in timeline["frames"]:
        # Seul le dragon compte avant 14 min : les grubs et les autres objectifs sortent.
        frame["events"] = [
            e for e in frame["events"] if e["type"] != "ELITE_MONSTER_KILL" or e is dragon
        ]
        for pid, pf in frame["participantFrames"].items():
            far = {"x": -100_000, "y": -100_000}
            pf["position"] = dict(dragon["position"]) if pid == "3" else far

    actions = player_actions(GAME, timeline, 14)

    assert actions[3]["presence"] == 1.0  # dans le rayon, ni tueur ni assistant
    assert actions[2]["presence"] == 1.0  # tueur du dragon
    assert actions[1]["presence"] == 0.0  # hors rayon, ni tueur ni assistant
    assert actions[4]["presence"] == 0.0


# ---------- 2. mort sans contrepartie ----------


def _death_at_5_min(*extra_events) -> dict:
    """Mort de 1 à 5 min 00 (tuée par 6, sans assistant), plus les événements donnés."""
    return _with_events([_kill(300_000, 6, 1), *extra_events])


def test_kill_by_the_other_team_15_s_after_the_death_trades_it():
    timeline = _death_at_5_min(_kill(315_000, 1, 6))

    assert player_actions(GAME, timeline, 14)[1]["untraded_deaths"] == 0.0


def test_kill_by_the_other_team_25_s_after_the_death_does_not_trade_it():
    timeline = _death_at_5_min(_kill(325_000, 1, 6))

    assert player_actions(GAME, timeline, 14)[1]["untraded_deaths"] == 1.0


def test_allied_dragon_10_s_after_the_death_trades_it():
    dragon = {
        "type": "ELITE_MONSTER_KILL",
        "timestamp": 310_000,
        "killerId": 2,
        "monsterType": "DRAGON",
        "monsterSubType": "WATER_DRAGON",
        "assistingParticipantIds": [],
        "position": {"x": 10049, "y": 4591},
    }
    timeline = _death_at_5_min(dragon)

    actions = player_actions(GAME, timeline, 14)
    assert actions[1]["deaths"] == 1.0
    assert actions[1]["untraded_deaths"] == 0.0


# ---------- 3. lane_rows et player_gaps ----------


def test_lane_rows_gives_blue_minus_red_for_the_five_roles():
    rows = lane_rows(GAME, TIMELINE, 14)

    assert set(rows) == ROLES
    frame = TIMELINE["frames"][14]["participantFrames"]
    blue_cs = frame["1"]["minionsKilled"] + frame["1"]["jungleMinionsKilled"]  # top bleu : pid 1
    red_cs = frame["6"]["minionsKilled"] + frame["6"]["jungleMinionsKilled"]  # top rouge : pid 6
    assert rows["top"]["cs"] == blue_cs - red_cs


def test_lane_rows_is_empty_when_a_role_is_ambiguous():
    game = copy.deepcopy(GAME)
    # Pid 9 (bas rouge) revendiqué comme top par l'objet de quête : deux tops, aucun ne se résout.
    game["participants"][8]["stats"]["roleBoundItem"] = 1220

    assert lane_rows(game, TIMELINE, 14) == {}


def test_lane_rows_is_empty_for_a_remake():
    game = copy.deepcopy(GAME)
    game["participants"][0]["stats"]["gameEndedInEarlySurrender"] = True

    assert lane_rows(game, TIMELINE, 14) == {}


def test_lane_rows_is_empty_below_15_min():
    game = copy.deepcopy(GAME)
    game["gameDuration"] = 899

    assert lane_rows(game, TIMELINE, 14) == {}


def test_player_gap_of_a_red_player_is_the_opposite_of_the_blue_minus_red_gap():
    rows = lane_rows(GAME, TIMELINE, 14)

    role, gaps = player_gaps(GAME, TIMELINE, None, 6, 14)

    assert role == "top"
    assert gaps["cs"] == pytest.approx(-rows["top"]["cs"])
    assert player_gaps(GAME, TIMELINE, None, 1, 14)[1]["cs"] == pytest.approx(rows["top"]["cs"])


# ---------- 4. value_actions (données synthétiques) ----------


def _synthetic_lines(n: int = 3000) -> tuple:
    """Lignes à la manière de `lane_rows` et issues bleues : seul le CS influence la victoire (logit 0,08 × cs)."""
    rng = random.Random(0)
    rows, wins = [], []
    for _ in range(n):
        cs = rng.gauss(0, 10)
        deaths = rng.randint(0, 3)
        rows.append(
            {
                "cs": cs,
                "deaths": float(deaths),
                "solo_deaths": float(rng.randint(0, deaths)),
                "untraded_deaths": float(rng.randint(0, deaths)),
                "presence": rng.random(),
                "vision": rng.uniform(0, 3),
            }
        )
        wins.append(1 if rng.random() < 1 / (1 + math.exp(-0.08 * cs)) else 0)
    return rows, wins


def test_value_actions_finds_the_cs_effect_and_no_effect_for_presence():
    rows, wins = _synthetic_lines()

    result = value_actions(rows, wins, folds=5)

    cs = result["effects"]["cs"]
    assert cs.pts_per_unit > 0
    assert cs.ci_low > 0
    assert cs.same_sign_folds == 5
    presence = result["effects"]["presence"]
    assert presence.ci_low < 0 < presence.ci_high
    assert result["brier"]["model"] < result["brier"]["constant"]
