"""Regression: the counters carousel was capped at its first ~18 opponents per lane.

Bug (reported by @pj35 on 2026-09-24): the end-of-draft duel Sion (top) vs Jax
(top) showed "?" — the database had no top-lane row for that pair. LoLalytics
renders the carousel VIRTUALIZED (~19 cells at a time); the element that
scrolls is the PARENT of the row track (``overflow-x-scroll``). The scraper
scrolled the track itself, a no-op, so every row stopped at its first batch:
~90 matchups per (champion, lane) instead of ~240, and Jax (16th-19th most
common top opponent of Sion depending on the day) fell off the list.

Second defect found on the way: an opponent present in several rows (Yone as
enemy top AND mid) was stored once per (champion, enemy, lane), the LAST row
read overwriting the direct lane duel.
"""

from unittest.mock import MagicMock, patch

import pytest
from selenium.webdriver.common.by import By

from src.parser import Parser, _one_per_opponent


class FakeCell:
    """One carousel cell, answering the lookups _extract_carousel_rows makes."""

    def __init__(self, name: str, games: int = 300, pickrate: float = 2.0):
        self.name, self.games, self.pickrate = name, games, pickrate

    @staticmethod
    def _html(value):
        element = MagicMock()
        element.get_attribute.return_value = value
        return element

    def find_element(self, by, value):
        if by == By.TAG_NAME:
            link = MagicMock()
            link.get_dom_attribute.return_value = f"/lol/sion/vs/{self.name}/build/"
            return link
        if by == By.CLASS_NAME:  # games
            return self._html(f"{self.games:,}")
        return self._html("52.0%")  # winrate span

    def find_elements(self, by, value):
        values = ["0", "0", "0", "0", "1.5", "0.8", str(self.pickrate)]
        return [self._html(v) for v in values]


class VirtualizedCarousel:
    """Renders ``window`` cells at a time; only scrolling the PARENT moves it."""

    def __init__(self, names, window=3):
        self.names, self.window, self.offset = names, window, 0

    def find_element(self, by, value):
        return MagicMock()  # the row track (and WebDriverWait's presence check)

    def find_elements(self, by, value):
        visible = self.names[self.offset : self.offset + self.window]
        return [FakeCell(name) for name in visible]

    def execute_script(self, script, *args):
        if "parentElement.scrollLeft" in script:
            self.offset += self.window


@pytest.fixture
def parser():
    with patch("src.parser.webdriver.Firefox", return_value=MagicMock()):
        p = Parser(headless=True)
    return p


def test_the_whole_virtualized_row_is_read(parser):
    names = ["yone", "jayce", "fiora", "jax", "ksante", "garen", "chogath", "teemo", "kayle"]
    parser.webdriver = VirtualizedCarousel(names)

    with patch("src.parser.sleep"):
        rows = parser._extract_carousel_rows(
            "sion", [2], "Matchup", lambda href: href.split("vs/")[1].split("/build")[0]
        )

    assert [row[0] for row in rows] == names  # Jax and the tail beyond the first batch


class TestOnePerOpponent:
    def test_direct_lane_duel_wins_over_a_more_played_indirect_row(self):
        direct = [("yone", 50.0, 1.0, 1.0, 2.0, 200)]
        indirect = [("yone", 48.0, -1.0, -1.0, 5.0, 900)]
        assert _one_per_opponent(direct, indirect) == direct

    def test_indirect_duplicates_keep_the_most_played(self):
        mid = ("viktor", 51.0, 0.5, 0.5, 3.0, 700)
        bot = ("viktor", 47.0, -0.5, -0.5, 0.6, 90)
        assert _one_per_opponent([], [bot, mid]) == [mid]

    def test_distinct_opponents_are_all_kept(self):
        rows = [("jax", 52.9, 5.4, 1.7, 2.1, 261), ("teemo", 55.1, 8.4, 4.7, 1.9, 236)]
        assert sorted(_one_per_opponent(rows[:1], rows[1:])) == sorted(rows)
