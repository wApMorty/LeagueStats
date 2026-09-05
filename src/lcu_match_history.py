"""Match-history reading mixin for LCUClient (SPEC-08 — boucle de mesure).

Extracted so src/lcu_client.py stays under the project's 500-line ceiling
(cf. src/parser_cookie_banner.py for the same pattern applied to Parser).
These two methods only fetch and normalize the LCU's raw JSON shapes into a
small, stable dict per game -- the matching logic that consumes them
(temporal filter + team-composition confirmation) lives in
src/draft/outcome_tracker.py, not here.

Both response shapes were verified against a real client on 2026-09-05 (see
docs/specs/SPEC-08-boucle-de-mesure.md §2.1) -- do not re-derive them from
speculation, and do not re-run the spike.
"""

from typing import Any, Dict, List


class _MatchHistoryMixin:
    """get_recent_matches() / get_match_participants() for LCUClient."""

    def get_recent_matches(self, count: int = 5) -> List[Dict[str, Any]]:
        """The `count` most recent games of the current summoner, newest first.

        Each entry: {"game_id": int, "game_creation_ms": int, "queue_id": int,
        "win": bool, "player_champion_id": int, "team_id": int}.

        The endpoint's `endIndex` is INCLUSIVE (verified 2026-09-05), so
        `count` games requires `endIndex = count - 1`. The payload nests
        games twice (`payload["games"]["games"]`) and each entry's
        `participants` list holds a single element -- the current player,
        nobody else -- so team composition is not available here (see
        get_match_participants for that).

        Best-effort: any unexpected shape (missing key, None, empty list)
        yields [] rather than raising, since a stale/incompatible LCU
        response must never interrupt the draft monitor loop.
        """
        end_index = max(count - 1, 0)
        response = self._make_request(
            "/lol-match-history/v1/products/lol/current-summoner/matches"
            f"?begIndex=0&endIndex={end_index}"
        )
        if not response:
            return []

        games = (response.get("games") or {}).get("games")
        if not isinstance(games, list):
            return []

        matches: List[Dict[str, Any]] = []
        for game in games:
            try:
                participants = game.get("participants") or []
                if not participants:
                    continue
                player = participants[0]
                matches.append(
                    {
                        "game_id": game["gameId"],
                        "game_creation_ms": game["gameCreation"],
                        "queue_id": game.get("queueId"),
                        "win": bool(player["stats"]["win"]),
                        "player_champion_id": player.get("championId"),
                        "team_id": player.get("teamId"),
                    }
                )
            except (KeyError, TypeError, AttributeError):
                continue
        return matches

    def get_match_participants(self, game_id: int) -> Dict[int, List[int]]:
        """All 10 champion picks of one game, grouped by team: {100: [...],
        200: [...]}.

        Uses `/lol-match-history/v1/games/{game_id}` -- the sibling
        `.../current-summoner/matches/{game_id}` returns 404 (verified
        2026-09-05), do not use it.

        Best-effort: returns {} if the detail is unavailable (game too old,
        client disconnected) or the response shape is unexpected.
        """
        response = self._make_request(f"/lol-match-history/v1/games/{game_id}")
        if not response:
            return {}

        participants = response.get("participants")
        if not isinstance(participants, list):
            return {}

        teams: Dict[int, List[int]] = {}
        try:
            for participant in participants:
                team_id = participant["teamId"]
                champion_id = participant["championId"]
                teams.setdefault(team_id, []).append(champion_id)
        except (KeyError, TypeError):
            return {}
        return teams
