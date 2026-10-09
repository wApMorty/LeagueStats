"""SPEC-28 tâche 129 : `TickTimer`, durée des étapes du monitor et journal des tours lents.

Fausse horloge, sink en liste : rien n'est écrit dans `logs/`.
"""

import pytest

from src.config_constants import draft_config
from src.draft.tick_timer import TickTimer


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def make():
    clock, lines = Clock(), []
    return TickTimer(clock=clock, sink=lines.append), clock, lines


def step(clock, seconds, result=None):
    def work():
        clock.now += seconds
        return result

    return work


def test_run_returns_the_result_of_the_work():
    timer, clock, _ = make()

    assert timer.run("a", step(clock, 0.1, result=42)) == 42


def test_run_times_then_propagates_an_exception():
    timer, clock, lines = make()

    def boom():
        clock.now += draft_config.TICK_SLOW_S + 1
        raise ValueError("x")

    with pytest.raises(ValueError):
        timer.run("capture_recent", boom)
    timer.end_tick("Matchmaking")

    assert "capture_recent" in lines[0]


def test_fast_tick_writes_nothing():
    timer, clock, lines = make()

    timer.run("phase", step(clock, draft_config.TICK_SLOW_S - 0.5))
    timer.end_tick("Lobby")

    assert lines == []


def test_slow_tick_lists_only_the_steps_of_half_a_second_or_more(capsys):
    timer, clock, lines = make()

    timer.run("phase", step(clock, 0.1))
    timer.run("resolve_outcomes", step(clock, 4.2))
    timer.run("crawler_step", step(clock, 0.2))
    timer.end_tick("Matchmaking")

    assert lines == ["tour 4.5 s phase=Matchmaking | resolve_outcomes 4.2"]
    assert "[ALERTE]" not in capsys.readouterr().out


def test_nested_steps_are_listed_and_the_alert_names_the_innermost(capsys):
    timer, clock, lines = make()

    def post_game():
        timer.run("capture_recent", step(clock, 18.1))
        clock.now += 0.2

    timer.run("post_game", post_game)
    timer.end_tick("Matchmaking")

    assert lines == ["tour 18.3 s phase=Matchmaking | capture_recent 18.1 | post_game 18.3"]
    assert "[ALERTE] Boucle du Live Coach : 18 s dans capture_recent" in capsys.readouterr().out


def test_alert_is_printed_once_per_step(capsys):
    timer, clock, _ = make()

    for _ in range(2):
        timer.run("crawler_step", step(clock, draft_config.TICK_ALERT_S + 1))
        timer.end_tick("Lobby")

    assert capsys.readouterr().out.count("[ALERTE]") == 1


def test_each_tick_starts_from_zero():
    timer, clock, lines = make()
    timer.run("a", step(clock, draft_config.TICK_SLOW_S + 1))
    timer.end_tick("Lobby")
    timer.run("b", step(clock, 0.1))
    timer.end_tick("Lobby")

    assert len(lines) == 1


def test_draft_seen_writes_one_line():
    timer, _, lines = make()

    timer.draft_seen(1.44)

    assert lines == ["draft vue 1.4 s après l'entrée en champ select"]


def test_without_a_sink_nothing_is_written_and_nothing_raises(capsys):
    timer = TickTimer(clock=Clock())

    timer.run("a", lambda: None)
    timer.end_tick("Lobby")
    timer.draft_seen(2.0)

    assert capsys.readouterr().out == ""


def test_a_failing_sink_never_reaches_the_loop():
    clock = Clock()

    def broken(_line):
        raise OSError("disque plein")

    timer = TickTimer(clock=clock, sink=broken)
    timer.run("a", step(clock, draft_config.TICK_SLOW_S + 1))
    timer.end_tick("Lobby")
    timer.draft_seen(1.0)
