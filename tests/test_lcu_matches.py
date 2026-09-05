"""Tests for LCUClient.get_recent_matches / get_match_participants (SPEC-08).

Payload shapes are the ones verified against a real client on 2026-09-05
(docs/specs/SPEC-08-boucle-de-mesure.md §2.1) -- these tests are hermetic,
built on frozen fixtures reproducing that spike, never a live LCU.
"""

from unittest.mock import patch

from src.lcu_client import LCUClient


def _make_client() -> LCUClient:
    client = LCUClient()
    client.credentials = object()  # truthy: _make_request only short-circuits on None
    return client


def _game(
    game_id=7412339812,
    creation_ms=1788639943655,
    queue_id=420,
    win=True,
    champion_id=266,
    team_id=100,
):
    return {
        "gameId": game_id,
        "gameCreation": creation_ms,
        "gameCreationDate": "2026-09-05T20:25:43.655Z",
        "gameDuration": 1800,
        "queueId": queue_id,
        "gameMode": "CLASSIC",
        "endOfGameResult": "GameComplete",
        "teams": [
            {"teamId": 100, "win": "Win" if team_id == 100 else "Fail"},
            {"teamId": 200, "win": "Win" if team_id == 200 else "Fail"},
        ],
        "participants": [{"championId": champion_id, "teamId": team_id, "stats": {"win": win}}],
    }


class TestGetRecentMatches:
    def test_victory_is_normalized(self):
        client = _make_client()
        payload = {"games": {"games": [_game(win=True)]}}
        with patch.object(client, "_make_request", return_value=payload) as mock_request:
            matches = client.get_recent_matches(count=3)

        assert matches == [
            {
                "game_id": 7412339812,
                "game_creation_ms": 1788639943655,
                "queue_id": 420,
                "win": True,
                "player_champion_id": 266,
                "team_id": 100,
            }
        ]
        mock_request.assert_called_once_with(
            "/lol-match-history/v1/products/lol/current-summoner/matches?begIndex=0&endIndex=2"
        )

    def test_defeat_is_normalized(self):
        client = _make_client()
        payload = {"games": {"games": [_game(win=False)]}}
        with patch.object(client, "_make_request", return_value=payload):
            matches = client.get_recent_matches(count=1)

        assert matches[0]["win"] is False

    def test_end_index_is_count_minus_one_because_inclusive(self):
        """Spike finding (§2.1A): endIndex is INCLUSIVE, so `count` games
        requires endIndex = count - 1, not count."""
        client = _make_client()
        with patch.object(client, "_make_request", return_value=None) as mock_request:
            client.get_recent_matches(count=10)

        mock_request.assert_called_once_with(
            "/lol-match-history/v1/products/lol/current-summoner/matches?begIndex=0&endIndex=9"
        )

    def test_missing_nested_games_games_returns_empty_list(self):
        """The payload nests games twice (`games.games`, §2.1A). A response
        missing that nesting must not raise."""
        client = _make_client()
        with patch.object(client, "_make_request", return_value={"games": {}}):
            assert client.get_recent_matches() == []

        with patch.object(client, "_make_request", return_value={}):
            assert client.get_recent_matches() == []

    def test_empty_participants_skips_that_game(self):
        """A game whose `participants` list is empty is dropped, not raised."""
        client = _make_client()
        payload = {"games": {"games": [_game(win=True), {**_game(game_id=2), "participants": []}]}}
        with patch.object(client, "_make_request", return_value=payload):
            matches = client.get_recent_matches()

        assert len(matches) == 1
        assert matches[0]["game_id"] == 7412339812

    def test_none_response_returns_empty_list(self):
        client = _make_client()
        with patch.object(client, "_make_request", return_value=None):
            assert client.get_recent_matches() == []

    def test_no_credentials_returns_empty_list_without_raising(self):
        client = LCUClient()  # credentials never set
        assert client.get_recent_matches() == []


class TestGetMatchParticipants:
    def test_ten_participants_grouped_by_team(self):
        client = _make_client()
        payload = {
            "participants": [
                {"participantId": 1, "championId": 126, "teamId": 100},
                {"participantId": 2, "championId": 104, "teamId": 100},
                {"participantId": 3, "championId": 105, "teamId": 100},
                {"participantId": 4, "championId": 202, "teamId": 100},
                {"participantId": 5, "championId": 99, "teamId": 100},
                {"participantId": 6, "championId": 36, "teamId": 200},
                {"participantId": 7, "championId": 77, "teamId": 200},
                {"participantId": 8, "championId": 950, "teamId": 200},
                {"participantId": 9, "championId": 800, "teamId": 200},
                {"participantId": 10, "championId": 63, "teamId": 200},
            ]
        }
        with patch.object(client, "_make_request", return_value=payload) as mock_request:
            teams = client.get_match_participants(7412339812)

        assert teams == {
            100: [126, 104, 105, 202, 99],
            200: [36, 77, 950, 800, 63],
        }
        mock_request.assert_called_once_with("/lol-match-history/v1/games/7412339812")

    def test_404_response_returns_empty_dict(self):
        """The current-summoner/matches/{gameId} variant 404s (§2.1B); the
        endpoint actually used can too, e.g. a game too old to keep detail
        for -- _make_request already turns a 404 into None."""
        client = _make_client()
        with patch.object(client, "_make_request", return_value=None):
            assert client.get_match_participants(1) == {}

    def test_missing_participants_key_returns_empty_dict(self):
        client = _make_client()
        with patch.object(client, "_make_request", return_value={}):
            assert client.get_match_participants(1) == {}

    def test_no_credentials_returns_empty_dict_without_raising(self):
        client = LCUClient()
        assert client.get_match_participants(1) == {}
