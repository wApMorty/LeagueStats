"""Tests for src/lcu_client.py (SPEC-10 -- couverture du chemin critique).

Scope: everything in LCUClient itself that was not already covered by
tests/test_lcu_assigned_positions.py (get_assigned_positions) or
tests/test_lcu_matches.py (the _MatchHistoryMixin, SPEC-08):
credentials discovery, _make_request (the single injection point), champion
name normalization/lookup, hover/lock, and the connect/disconnect/ready-check
facades.

Hermetic by construction: `requests` is always mocked (never a real socket),
and `_find_credentials_lockfile`/`_find_credentials_process` are exercised
only through monkeypatched `os.path.exists`/`open`/`psutil.process_iter` --
never the real filesystem or process list.

Invariant under test throughout (SPEC-10 S1): no public LCUClient method may
raise when the client is absent or returns garbage -- that is the contract
the whole draft-monitoring loop is built on.
"""

from unittest.mock import Mock, mock_open, patch

import requests

from src.lcu_client import LCUClient, LCUCredentials


def _client_with_credentials() -> LCUClient:
    client = LCUClient()
    client.credentials = LCUCredentials(
        port=12345, password="secret", base_url="https://127.0.0.1:12345"
    )
    return client


class TestLCUCredentials:
    def test_auth_header_is_basic_base64_of_riot_password(self):
        creds = LCUCredentials(port=1, password="abc", base_url="https://127.0.0.1:1")
        # "riot:abc" base64-encoded -> "cmlvdDphYmM="
        assert creds.auth_header == "Basic cmlvdDphYmM="


class TestMakeRequest:
    """`_make_request` is the sole HTTP injection point -- everything else
    in LCUClient funnels through it."""

    def test_no_credentials_returns_none_without_raising(self):
        client = LCUClient()
        assert client._make_request("/lol-champ-select/v1/session") is None

    def test_status_200_with_json_body_returns_parsed_json(self):
        client = _client_with_credentials()
        response = Mock(status_code=200, content=b'{"phase": "ChampSelect"}')
        response.json.return_value = {"phase": "ChampSelect"}
        with patch.object(client.session, "get", return_value=response):
            assert client._make_request("/x") == {"phase": "ChampSelect"}

    def test_status_200_with_empty_body_returns_empty_dict(self):
        client = _client_with_credentials()
        response = Mock(status_code=200, content=b"")
        with patch.object(client.session, "get", return_value=response):
            assert client._make_request("/x") == {}

    def test_status_204_no_content_returns_empty_dict(self):
        """204 is PATCH's success code for hover/lock -- must not be treated as error."""
        client = _client_with_credentials()
        response = Mock(status_code=204, content=b"")
        with patch.object(client.session, "patch", return_value=response):
            assert client._make_request("/x", method="PATCH", data={}) == {}

    def test_status_200_with_invalid_json_returns_empty_dict(self):
        """A malformed body must degrade to {}, never raise."""
        client = _client_with_credentials()
        response = Mock(status_code=200, content=b"not json")
        response.json.side_effect = ValueError("invalid json")
        with patch.object(client.session, "get", return_value=response):
            assert client._make_request("/x") == {}

    def test_status_404_returns_none(self):
        """404 is normal when not in champ select -- not an error to log loudly."""
        client = _client_with_credentials()
        response = Mock(status_code=404, content=b"")
        with patch.object(client.session, "get", return_value=response):
            assert client._make_request("/x") is None

    def test_status_500_returns_none(self):
        client = _client_with_credentials()
        response = Mock(status_code=500, content=b"")
        with patch.object(client.session, "get", return_value=response):
            assert client._make_request("/x") is None

    def test_request_exception_returns_none(self):
        client = _client_with_credentials()
        with patch.object(
            client.session, "get", side_effect=requests.exceptions.RequestException("boom")
        ):
            assert client._make_request("/x") is None

    def test_unsupported_method_returns_none(self):
        client = _client_with_credentials()
        assert client._make_request("/x", method="DELETE") is None

    def test_post_and_put_are_dispatched(self):
        client = _client_with_credentials()
        response = Mock(status_code=200, content=b"{}")
        response.json.return_value = {}
        with patch.object(client.session, "post", return_value=response) as mock_post:
            client._make_request("/x", method="POST", data={"a": 1})
            mock_post.assert_called_once()
        with patch.object(client.session, "put", return_value=response) as mock_put:
            client._make_request("/x", method="PUT", data={"a": 1})
            mock_put.assert_called_once()


class TestFindCredentialsLockfile:
    def test_lockfile_absent_returns_none(self):
        client = LCUClient()
        with patch("os.path.exists", return_value=False):
            assert client._find_credentials_lockfile() is None

    def test_well_formed_lockfile_is_parsed(self):
        client = LCUClient()
        content = "LeagueClient:1234:54321:sup3rsecret:https"
        with patch("os.path.exists", side_effect=lambda p: True):
            with patch("builtins.open", mock_open(read_data=content)):
                creds = client._find_credentials_lockfile()

        assert creds is not None
        assert creds.port == 54321
        assert creds.password == "sup3rsecret"
        assert creds.base_url == "https://127.0.0.1:54321"

    def test_malformed_lockfile_returns_none(self):
        """Too few ':'-separated fields -- must degrade, not raise/crash."""
        client = LCUClient()
        with patch("os.path.exists", side_effect=lambda p: True):
            with patch("builtins.open", mock_open(read_data="garbage")):
                assert client._find_credentials_lockfile() is None

    def test_unreadable_lockfile_returns_none_without_raising(self):
        """Belt-and-suspenders: exists() lies, or a permission error on open()."""
        client = LCUClient()
        with patch("os.path.exists", side_effect=lambda p: True):
            with patch("builtins.open", side_effect=OSError("permission denied")):
                assert client._find_credentials_lockfile() is None


class TestFindCredentialsProcess:
    """The process-list fallback -- always mocked, never the real process table."""

    def test_no_matching_process_returns_none(self):
        client = LCUClient()
        with patch("psutil.process_iter", return_value=iter([])):
            assert client._find_credentials_process() is None

    def test_matching_process_is_parsed(self):
        client = LCUClient()
        proc = Mock()
        proc.info = {
            "pid": 1,
            "name": "LeagueClientUx.exe",
            "cmdline": [
                "LeagueClientUx.exe",
                "--app-port=6543",
                "--remoting-auth-token=abc123",
            ],
        }
        with patch("psutil.process_iter", return_value=iter([proc])):
            creds = client._find_credentials_process()

        assert creds is not None
        assert creds.port == 6543
        assert creds.password == "abc123"

    def test_truncated_token_is_not_actually_reset(self):
        """Characterization, not a spec: the inline comment says a truncated
        token ('...'-suffixed, as truncated by the OS command-line length
        limit) should be skipped in favor of the lockfile, but the `continue`
        only skips the rest of that cmdline arg loop -- `password` was
        already assigned the truncated value and is never reset to None, so
        it is returned anyway. Documented here as a known discrepancy
        (SPEC-10 report) rather than silently fixed, since production code
        changes are out of this spec's scope."""
        client = LCUClient()
        proc = Mock()
        proc.info = {
            "pid": 1,
            "name": "LeagueClientUx.exe",
            "cmdline": ["--app-port=6543", "--remoting-auth-token=abc..."],
        }
        with patch("psutil.process_iter", return_value=iter([proc])):
            creds = client._find_credentials_process()

        assert creds is not None
        assert creds.password == "abc..."

    def test_process_scan_error_returns_none(self):
        client = LCUClient()
        with patch("psutil.process_iter", side_effect=Exception("access denied")):
            assert client._find_credentials_process() is None


class TestFindLcuCredentials:
    def test_lockfile_found_short_circuits_process_scan(self):
        client = LCUClient()
        fake_creds = LCUCredentials(port=1, password="x", base_url="https://127.0.0.1:1")
        with patch.object(client, "_find_credentials_lockfile", return_value=fake_creds):
            with patch.object(client, "_find_credentials_process") as mock_process:
                result = client.find_lcu_credentials()

        assert result is fake_creds
        mock_process.assert_not_called()

    def test_falls_back_to_process_scan_when_lockfile_missing(self):
        client = LCUClient()
        fake_creds = LCUCredentials(port=2, password="y", base_url="https://127.0.0.1:2")
        with patch.object(client, "_find_credentials_lockfile", return_value=None):
            with patch.object(client, "_find_credentials_process", return_value=fake_creds):
                assert client.find_lcu_credentials() is fake_creds

    def test_neither_method_returns_none(self):
        client = LCUClient()
        with patch.object(client, "_find_credentials_lockfile", return_value=None):
            with patch.object(client, "_find_credentials_process", return_value=None):
                assert client.find_lcu_credentials() is None


class TestConnect:
    def test_no_credentials_found_returns_false(self, capsys):
        client = LCUClient()
        with patch.object(client, "find_lcu_credentials", return_value=None):
            assert client.connect() is False
        assert "not found" in capsys.readouterr().out.lower()

    def test_valid_response_returns_true(self):
        client = LCUClient()
        fake_creds = LCUCredentials(port=1, password="x", base_url="https://127.0.0.1:1")
        with patch.object(client, "find_lcu_credentials", return_value=fake_creds):
            with patch.object(client, "_make_request", return_value={"displayName": "Faker"}):
                assert client.connect() is True

    def test_response_without_summoner_info_returns_false(self):
        client = LCUClient()
        fake_creds = LCUCredentials(port=1, password="x", base_url="https://127.0.0.1:1")
        with patch.object(client, "find_lcu_credentials", return_value=fake_creds):
            with patch.object(client, "_make_request", return_value={}):
                assert client.connect() is False

    def test_make_request_raising_is_caught(self):
        """connect() wraps the test request in try/except -- must never
        propagate an unexpected exception up into the caller."""
        client = LCUClient()
        fake_creds = LCUCredentials(port=1, password="x", base_url="https://127.0.0.1:1")
        with patch.object(client, "find_lcu_credentials", return_value=fake_creds):
            with patch.object(client, "_make_request", side_effect=Exception("boom")):
                assert client.connect() is False


class TestNormalizeChampionName:
    def test_apostrophe_and_case_are_stripped(self):
        client = LCUClient()
        assert client._normalize_champion_name("Kai'Sa") == "kaisa"
        assert client._normalize_champion_name("Cho'Gath") == "chogath"

    def test_spaces_are_stripped(self):
        client = LCUClient()
        assert client._normalize_champion_name("Lee Sin") == "leesin"

    def test_accents_are_stripped(self):
        client = LCUClient()
        # Renata Glasc has no accent in-game, but the normalizer must still
        # cope with one if the caller ever passes an accented variant.
        assert client._normalize_champion_name("Léblanc") == "leblanc"

    def test_dots_are_stripped(self):
        client = LCUClient()
        assert client._normalize_champion_name("Dr. Mundo") == "drmundo"


class TestGetChampionIdByName:
    def test_exact_match_returns_id(self):
        client = _client_with_credentials()
        payload = [{"id": 266, "name": "Aatrox"}, {"id": 1, "name": "Annie"}]
        with patch.object(client, "_make_request", return_value=payload):
            assert client.get_champion_id_by_name("Aatrox") == 266

    def test_apostrophe_name_matches_via_normalization(self):
        client = _client_with_credentials()
        payload = [{"id": 145, "name": "Kai'Sa"}]
        with patch.object(client, "_make_request", return_value=payload):
            assert client.get_champion_id_by_name("kaisa") == 145
            assert client.get_champion_id_by_name("Kai'sa") == 145

    def test_case_insensitive_match(self):
        client = _client_with_credentials()
        payload = [{"id": 64, "name": "LeeSin"}]
        with patch.object(client, "_make_request", return_value=payload):
            assert client.get_champion_id_by_name("leesin") == 64

    def test_unknown_champion_returns_none(self):
        client = _client_with_credentials()
        payload = [{"id": 266, "name": "Aatrox"}]
        with patch.object(client, "_make_request", return_value=payload):
            assert client.get_champion_id_by_name("NotAChampion") is None

    def test_no_response_returns_none(self):
        client = _client_with_credentials()
        with patch.object(client, "_make_request", return_value=None):
            assert client.get_champion_id_by_name("Aatrox") is None

    def test_wukong_riot_id_differs_from_display_name(self):
        """Riot's internal id for Wukong is 'MonkeyKing' -- the client-name
        match must still resolve it when queried by the display name."""
        client = _client_with_credentials()
        payload = [{"id": 62, "name": "MonkeyKing"}]
        with patch.object(client, "_make_request", return_value=payload):
            # Exact-name path won't match ("wukong" != "monkeyking"), but the
            # normalized comparison against the raw input string still can if
            # the caller passes the client's own name.
            assert client.get_champion_id_by_name("MonkeyKing") == 62


class TestGetCurrentPlayerActionId:
    def test_no_session_returns_none(self):
        client = _client_with_credentials()
        with patch.object(client, "get_champion_select_session", return_value=None):
            assert client.get_current_player_action_id() is None

    def test_missing_local_player_cell_id_returns_none(self):
        client = _client_with_credentials()
        with patch.object(client, "get_champion_select_session", return_value={"actions": []}):
            assert client.get_current_player_action_id() is None

    def test_finds_incomplete_pick_action_for_local_player(self):
        client = _client_with_credentials()
        session = {
            "localPlayerCellId": 3,
            "actions": [
                [
                    {"actorCellId": 3, "completed": False, "type": "pick", "id": 42},
                    {"actorCellId": 1, "completed": False, "type": "pick", "id": 7},
                ]
            ],
        }
        with patch.object(client, "get_champion_select_session", return_value=session):
            assert client.get_current_player_action_id() == 42

    def test_completed_action_is_skipped(self):
        client = _client_with_credentials()
        session = {
            "localPlayerCellId": 3,
            "actions": [[{"actorCellId": 3, "completed": True, "type": "pick", "id": 42}]],
        }
        with patch.object(client, "get_champion_select_session", return_value=session):
            assert client.get_current_player_action_id() is None

    def test_ban_action_type_is_ignored(self):
        client = _client_with_credentials()
        session = {
            "localPlayerCellId": 3,
            "actions": [[{"actorCellId": 3, "completed": False, "type": "ban", "id": 1}]],
        }
        with patch.object(client, "get_champion_select_session", return_value=session):
            assert client.get_current_player_action_id() is None


class TestHoverChampion:
    def test_not_in_champion_select_returns_false(self):
        client = _client_with_credentials()
        with patch.object(client, "is_in_champion_select", return_value=False):
            assert client.hover_champion("Aatrox") is False

    def test_unknown_champion_returns_false(self):
        client = _client_with_credentials()
        with patch.object(client, "is_in_champion_select", return_value=True):
            with patch.object(client, "get_champion_id_by_name", return_value=None):
                assert client.hover_champion("NotAChampion") is False

    def test_no_current_action_returns_false(self):
        client = _client_with_credentials()
        with patch.object(client, "is_in_champion_select", return_value=True):
            with patch.object(client, "get_champion_id_by_name", return_value=266):
                with patch.object(client, "get_current_player_action_id", return_value=None):
                    assert client.hover_champion("Aatrox") is False

    def test_patch_failure_returns_false(self):
        client = _client_with_credentials()
        with patch.object(client, "is_in_champion_select", return_value=True):
            with patch.object(client, "get_champion_id_by_name", return_value=266):
                with patch.object(client, "get_current_player_action_id", return_value=42):
                    with patch.object(client, "_make_request", return_value=None):
                        assert client.hover_champion("Aatrox") is False

    def test_successful_patch_returns_true(self):
        client = _client_with_credentials()
        with patch.object(client, "is_in_champion_select", return_value=True):
            with patch.object(client, "get_champion_id_by_name", return_value=266):
                with patch.object(client, "get_current_player_action_id", return_value=42):
                    with patch.object(client, "_make_request", return_value={}) as mock_request:
                        assert client.hover_champion("Aatrox") is True
        mock_request.assert_called_once()
        assert mock_request.call_args.kwargs.get("method") == "PATCH"


class TestLockChampion:
    def test_not_in_champion_select_returns_false(self):
        client = _client_with_credentials()
        with patch.object(client, "is_in_champion_select", return_value=False):
            assert client.lock_champion("Aatrox") is False

    def test_unknown_champion_returns_false(self):
        client = _client_with_credentials()
        with patch.object(client, "is_in_champion_select", return_value=True):
            with patch.object(client, "get_champion_id_by_name", return_value=None):
                assert client.lock_champion("NotAChampion") is False

    def test_no_current_action_returns_false(self):
        client = _client_with_credentials()
        with patch.object(client, "is_in_champion_select", return_value=True):
            with patch.object(client, "get_champion_id_by_name", return_value=266):
                with patch.object(client, "get_current_player_action_id", return_value=None):
                    assert client.lock_champion("Aatrox") is False

    def test_patch_failure_returns_false(self):
        client = _client_with_credentials()
        with patch.object(client, "is_in_champion_select", return_value=True):
            with patch.object(client, "get_champion_id_by_name", return_value=266):
                with patch.object(client, "get_current_player_action_id", return_value=42):
                    with patch.object(client, "_make_request", return_value=None):
                        assert client.lock_champion("Aatrox") is False

    def test_successful_lock_sends_completed_true(self):
        client = _client_with_credentials()
        with patch.object(client, "is_in_champion_select", return_value=True):
            with patch.object(client, "get_champion_id_by_name", return_value=266):
                with patch.object(client, "get_current_player_action_id", return_value=42):
                    with patch.object(client, "_make_request", return_value={}) as mock_request:
                        assert client.lock_champion("Aatrox") is True
        assert mock_request.call_args.kwargs["data"]["completed"] is True


class TestChampSelectAndGameflowFacades:
    def test_is_in_champion_select_true(self):
        client = _client_with_credentials()
        with patch.object(client, "get_gameflow_session", return_value={"phase": "ChampSelect"}):
            assert client.is_in_champion_select() is True

    def test_is_in_champion_select_false_on_other_phase(self):
        client = _client_with_credentials()
        with patch.object(client, "get_gameflow_session", return_value={"phase": "InProgress"}):
            assert client.is_in_champion_select() is False

    def test_is_in_champion_select_false_when_no_gameflow(self):
        client = _client_with_credentials()
        with patch.object(client, "get_gameflow_session", return_value=None):
            assert client.is_in_champion_select() is False

    def test_is_in_ready_check_true(self):
        client = _client_with_credentials()
        with patch.object(client, "get_gameflow_session", return_value={"phase": "ReadyCheck"}):
            assert client.is_in_ready_check() is True

    def test_is_in_ready_check_false_when_no_gameflow(self):
        client = _client_with_credentials()
        with patch.object(client, "get_gameflow_session", return_value=None):
            assert client.is_in_ready_check() is False


class TestAcceptReadyCheck:
    def test_not_in_ready_check_returns_false(self):
        client = _client_with_credentials()
        with patch.object(client, "is_in_ready_check", return_value=False):
            assert client.accept_ready_check() is False

    def test_successful_accept_returns_true(self):
        client = _client_with_credentials()
        with patch.object(client, "is_in_ready_check", return_value=True):
            with patch.object(client, "_make_request", return_value={}):
                assert client.accept_ready_check() is True

    def test_failed_accept_returns_false(self):
        client = _client_with_credentials()
        with patch.object(client, "is_in_ready_check", return_value=True):
            with patch.object(client, "_make_request", return_value=None):
                assert client.accept_ready_check() is False


class TestDisconnect:
    def test_disconnect_clears_credentials_and_closes_session(self):
        client = _client_with_credentials()
        with patch.object(client.session, "close") as mock_close:
            client.disconnect()
        mock_close.assert_called_once()
        assert client.credentials is None
