"""Tests pour la persistance des préférences du draft coach (SPEC-06 D2)."""

import json
from unittest.mock import patch

from src.analysis.strategy import Strategy
from src.user_prefs import (
    UserPrefs,
    load_pool_exclusions,
    load_strategies,
    load_swipe_passes,
    load_user_prefs,
    save_active_strategy,
    save_motion,
    save_pool_exclusion,
    save_role_pool,
    save_strategies,
    save_swipe_pass,
    save_user_prefs,
)

GRIND = Strategy("Grind", force=2.0, duel=0.5, other=1.0, synergy=0.0, mastery=1.5, search=True)


class TestSaveLoadRoundTrip:
    """Sauvegarde puis relecture des préférences."""

    def test_round_trip(self, tmp_path):
        prefs_file = tmp_path / "user_prefs.json"
        prefs = UserPrefs(
            auto_hover=True,
            auto_accept_queue=False,
            auto_ban_hover=True,
            pool_name="GRIND",
        )

        with patch("src.user_prefs.get_user_prefs_path", return_value=str(prefs_file)):
            assert save_user_prefs(prefs) is True
            loaded = load_user_prefs()

        assert loaded == prefs

    def test_round_trip_with_no_pool(self, tmp_path):
        prefs_file = tmp_path / "user_prefs.json"
        prefs = UserPrefs(pool_name=None)

        with patch("src.user_prefs.get_user_prefs_path", return_value=str(prefs_file)):
            save_user_prefs(prefs)
            loaded = load_user_prefs()

        assert loaded.pool_name is None


class TestLoadEdgeCases:
    """Cas limites de lecture : fichier absent, corrompu, valeurs hors bornes."""

    def test_absent_file_returns_none(self, tmp_path):
        prefs_file = tmp_path / "does_not_exist.json"

        with patch("src.user_prefs.get_user_prefs_path", return_value=str(prefs_file)):
            assert load_user_prefs() is None

    def test_corrupted_json_returns_none(self, tmp_path):
        prefs_file = tmp_path / "user_prefs.json"
        prefs_file.write_text("{not valid json", encoding="utf-8")

        with patch("src.user_prefs.get_user_prefs_path", return_value=str(prefs_file)):
            assert load_user_prefs() is None

    def test_missing_key_returns_none(self, tmp_path):
        prefs_file = tmp_path / "user_prefs.json"
        prefs_file.write_text(json.dumps({"auto_hover": True}), encoding="utf-8")

        with patch("src.user_prefs.get_user_prefs_path", return_value=str(prefs_file)):
            assert load_user_prefs() is None

    def test_a_file_written_before_the_synergy_cursor_removal_still_loads(self, tmp_path):
        """Le fichier de préférences des utilisateurs existants contient encore
        `synergy_weight`, supprimé avec le curseur synergie/matchup, et
        `open_onetricks`, supprimé avec la fenêtre OneTricks (4.0.0). Une clé
        inconnue doit être ignorée, pas faire échouer le chargement — sinon
        chaque utilisateur se voit reposer toutes les questions après la mise
        à jour."""
        prefs_file = tmp_path / "user_prefs.json"
        prefs_file.write_text(
            json.dumps(
                {
                    "auto_hover": True,
                    "auto_accept_queue": False,
                    "auto_ban_hover": False,
                    "open_onetricks": True,
                    "synergy_weight": 0.7,
                    "pool_name": "GRIND",
                }
            ),
            encoding="utf-8",
        )

        with patch("src.user_prefs.get_user_prefs_path", return_value=str(prefs_file)):
            loaded = load_user_prefs()

        assert loaded is not None
        assert loaded.auto_hover is True
        assert loaded.pool_name == "GRIND"
        assert not hasattr(loaded, "synergy_weight")
        assert not hasattr(loaded, "open_onetricks")


class TestSaveErrorHandling:
    """save_user_prefs ne doit jamais lever d'exception (best-effort)."""

    def test_save_returns_false_on_filesystem_error(self, tmp_path):
        prefs_file = tmp_path / "readonly_dir" / "user_prefs.json"

        with patch("src.user_prefs.get_user_prefs_path", return_value=str(prefs_file)):
            with patch("builtins.open", side_effect=PermissionError("denied")):
                assert save_user_prefs(UserPrefs()) is False


class TestPoolsByRole:
    """Désignation d'un pool par poste (SPEC-44 §4.1)."""

    def test_pools_by_role_round_trip(self, tmp_path):
        prefs_file = tmp_path / "user_prefs.json"
        prefs = UserPrefs(pools_by_role={"middle": "Mid Pool", "top": "Top Pool"})

        with patch("src.user_prefs.get_user_prefs_path", return_value=str(prefs_file)):
            save_user_prefs(prefs)
            loaded = load_user_prefs()

        assert loaded == prefs

    def test_file_without_key_gives_empty_dict(self, tmp_path):
        prefs_file = tmp_path / "user_prefs.json"
        prefs_file.write_text(
            json.dumps({"auto_hover": True, "auto_accept_queue": False, "auto_ban_hover": False}),
            encoding="utf-8",
        )

        with patch("src.user_prefs.get_user_prefs_path", return_value=str(prefs_file)):
            loaded = load_user_prefs()

        assert loaded is not None
        assert loaded.pools_by_role == {}

    def test_invalid_entries_are_filtered_without_losing_other_prefs(self, tmp_path):
        prefs_file = tmp_path / "user_prefs.json"
        prefs_file.write_text(
            json.dumps(
                {
                    "auto_hover": True,
                    "auto_accept_queue": False,
                    "auto_ban_hover": False,
                    "pool_name": "GRIND",
                    "pools_by_role": {
                        "middle": "GRIND",
                        "bogus": "X",
                        "top": 3,
                        "jungle": None,
                    },
                }
            ),
            encoding="utf-8",
        )

        with patch("src.user_prefs.get_user_prefs_path", return_value=str(prefs_file)):
            loaded = load_user_prefs()

        assert loaded is not None
        assert loaded.pools_by_role == {"middle": "GRIND"}
        assert loaded.pool_name == "GRIND"
        assert loaded.auto_hover is True

    def test_non_dict_pools_by_role_becomes_empty(self, tmp_path):
        prefs_file = tmp_path / "user_prefs.json"
        prefs_file.write_text(
            json.dumps(
                {
                    "auto_hover": False,
                    "auto_accept_queue": False,
                    "auto_ban_hover": False,
                    "pools_by_role": ["middle", "GRIND"],
                }
            ),
            encoding="utf-8",
        )

        with patch("src.user_prefs.get_user_prefs_path", return_value=str(prefs_file)):
            loaded = load_user_prefs()

        assert loaded is not None
        assert loaded.pools_by_role == {}


class TestSaveRolePool:
    """save_role_pool désigne, retire, refuse une lane inconnue et garde le reste du fichier."""

    def test_designates_and_keeps_other_designations(self, tmp_path):
        prefs_file = tmp_path / "user_prefs.json"

        with patch("src.user_prefs.get_user_prefs_path", return_value=str(prefs_file)):
            assert save_role_pool("middle", "GRIND") is True
            assert save_role_pool("top", "Top Pool") is True

        data = json.loads(prefs_file.read_text(encoding="utf-8"))
        assert data["pools_by_role"] == {"middle": "GRIND", "top": "Top Pool"}

    def test_none_removes_designation(self, tmp_path):
        prefs_file = tmp_path / "user_prefs.json"

        with patch("src.user_prefs.get_user_prefs_path", return_value=str(prefs_file)):
            save_role_pool("middle", "GRIND")
            save_role_pool("top", "Top Pool")
            assert save_role_pool("middle", None) is True

        data = json.loads(prefs_file.read_text(encoding="utf-8"))
        assert data["pools_by_role"] == {"top": "Top Pool"}

    def test_unknown_lane_is_refused_without_writing(self, tmp_path):
        prefs_file = tmp_path / "user_prefs.json"

        with patch("src.user_prefs.get_user_prefs_path", return_value=str(prefs_file)):
            assert save_role_pool("mid", "GRIND") is False

        assert not prefs_file.exists()

    def test_keeps_motion_setting(self, tmp_path):
        prefs_file = tmp_path / "user_prefs.json"

        with patch("src.user_prefs.get_user_prefs_path", return_value=str(prefs_file)):
            save_motion("reduit")
            save_role_pool("bottom", "ADC Pool")

        data = json.loads(prefs_file.read_text(encoding="utf-8"))
        assert data["motion"] == "reduit"
        assert data["pools_by_role"] == {"bottom": "ADC Pool"}


class TestStrategies:
    """Stratégies de draft (SPEC-46 §4.2) : lecture, écriture, clés préservées."""

    def test_round_trip(self, tmp_path):
        prefs_file = tmp_path / "user_prefs.json"

        with patch("src.user_prefs.get_user_prefs_path", return_value=str(prefs_file)):
            assert save_strategies([GRIND]) is True
            assert save_active_strategy("Grind") is True
            active, strategies = load_strategies()

        assert active == "Grind"
        assert strategies == [GRIND]

    def test_absent_file_gives_no_active_and_no_strategies(self, tmp_path):
        prefs_file = tmp_path / "does_not_exist.json"

        with patch("src.user_prefs.get_user_prefs_path", return_value=str(prefs_file)):
            assert load_strategies() == (None, [])

    def test_corrupted_entry_is_dropped_without_losing_others(self, tmp_path):
        prefs_file = tmp_path / "user_prefs.json"
        prefs_file.write_text(
            json.dumps(
                {
                    "active_strategy": "Grind",
                    "strategies": [
                        {
                            "name": "Trop lourd",
                            "force": 9.0,
                            "duel": 1,
                            "other": 1,
                            "synergy": 1,
                            "mastery": 1,
                        },
                        {
                            "name": "Grind",
                            "force": 2.0,
                            "duel": 0.5,
                            "other": 1.0,
                            "synergy": 0.0,
                            "mastery": 1.5,
                            "search": True,
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )

        with patch("src.user_prefs.get_user_prefs_path", return_value=str(prefs_file)):
            active, strategies = load_strategies()

        assert active == "Grind"
        assert [s.name for s in strategies] == ["Grind"]

    def test_active_strategy_of_wrong_type_gives_none(self, tmp_path):
        prefs_file = tmp_path / "user_prefs.json"
        prefs_file.write_text(json.dumps({"active_strategy": 3}), encoding="utf-8")

        with patch("src.user_prefs.get_user_prefs_path", return_value=str(prefs_file)):
            assert load_strategies() == (None, [])

    def test_save_user_prefs_keeps_strategies_and_motion(self, tmp_path):
        prefs_file = tmp_path / "user_prefs.json"

        with patch("src.user_prefs.get_user_prefs_path", return_value=str(prefs_file)):
            save_motion("reduit")
            save_strategies([GRIND])
            save_active_strategy("Grind")
            save_user_prefs(UserPrefs(auto_hover=True))

        data = json.loads(prefs_file.read_text(encoding="utf-8"))
        assert data["motion"] == "reduit"
        assert data["active_strategy"] == "Grind"
        assert data["strategies"][0]["name"] == "Grind"
        assert data["auto_hover"] is True

    def test_save_role_pool_keeps_strategies_and_pools_by_role(self, tmp_path):
        prefs_file = tmp_path / "user_prefs.json"

        with patch("src.user_prefs.get_user_prefs_path", return_value=str(prefs_file)):
            save_active_strategy("Simple")
            save_strategies([GRIND])
            save_role_pool("middle", "GRIND")
            save_role_pool("top", "Top Pool")

        data = json.loads(prefs_file.read_text(encoding="utf-8"))
        assert data["pools_by_role"] == {"middle": "GRIND", "top": "Top Pool"}
        assert data["active_strategy"] == "Simple"
        assert [s["name"] for s in data["strategies"]] == ["Grind"]


class TestSwipePasses:
    """Passes de l'écran de suggestions de pool (SPEC-49 §4.2) : par version, sans doublon."""

    def test_pass_then_read_same_version(self, tmp_path):
        prefs_file = tmp_path / "user_prefs.json"

        with patch("src.user_prefs.get_user_prefs_path", return_value=str(prefs_file)):
            assert save_swipe_pass("top", "Gangplank", "2026-11-01") is True
            passes = load_swipe_passes("2026-11-01")

        assert passes == {"top": ["Gangplank"]}

    def test_other_version_gives_empty_and_new_pass_clears_old_ones(self, tmp_path):
        prefs_file = tmp_path / "user_prefs.json"

        with patch("src.user_prefs.get_user_prefs_path", return_value=str(prefs_file)):
            save_swipe_pass("top", "Gangplank", "2026-11-01")
            assert load_swipe_passes("2026-11-08") == {}
            save_swipe_pass("middle", "Zoe", "2026-11-08")
            old_version_passes = load_swipe_passes("2026-11-01")
            new_version_passes = load_swipe_passes("2026-11-08")

        assert old_version_passes == {}
        assert new_version_passes == {"middle": ["Zoe"]}

    def test_duplicate_ignored_case_insensitively(self, tmp_path):
        prefs_file = tmp_path / "user_prefs.json"

        with patch("src.user_prefs.get_user_prefs_path", return_value=str(prefs_file)):
            save_swipe_pass("top", "Gangplank", "v1")
            save_swipe_pass("top", "GANGPLANK", "v1")
            passes = load_swipe_passes("v1")

        assert passes == {"top": ["Gangplank"]}

    def test_unknown_lane_refused_without_writing(self, tmp_path):
        prefs_file = tmp_path / "user_prefs.json"

        with patch("src.user_prefs.get_user_prefs_path", return_value=str(prefs_file)):
            assert save_swipe_pass("mid", "Zoe", "v1") is False

        assert not prefs_file.exists()

    def test_empty_champion_refused_without_writing(self, tmp_path):
        prefs_file = tmp_path / "user_prefs.json"

        with patch("src.user_prefs.get_user_prefs_path", return_value=str(prefs_file)):
            assert save_swipe_pass("top", "", "v1") is False

        assert not prefs_file.exists()

    def test_neighbour_keys_survive_save_swipe_pass(self, tmp_path):
        prefs_file = tmp_path / "user_prefs.json"

        with patch("src.user_prefs.get_user_prefs_path", return_value=str(prefs_file)):
            save_motion("reduit")
            save_role_pool("middle", "GRIND")
            save_swipe_pass("top", "Gangplank", "v1")

        data = json.loads(prefs_file.read_text(encoding="utf-8"))
        assert data["motion"] == "reduit"
        assert data["pools_by_role"] == {"middle": "GRIND"}
        assert data["pool_swipe"] == {"version": "v1", "passed": {"top": ["Gangplank"]}}

    def test_pool_swipe_survives_save_user_prefs(self, tmp_path):
        prefs_file = tmp_path / "user_prefs.json"

        with patch("src.user_prefs.get_user_prefs_path", return_value=str(prefs_file)):
            save_swipe_pass("top", "Gangplank", "v1")
            save_user_prefs(UserPrefs(auto_hover=True))

        data = json.loads(prefs_file.read_text(encoding="utf-8"))
        assert data["pool_swipe"] == {"version": "v1", "passed": {"top": ["Gangplank"]}}
        assert data["auto_hover"] is True

    def test_corrupted_value_is_read_tolerantly(self, tmp_path):
        prefs_file = tmp_path / "user_prefs.json"

        with patch("src.user_prefs.get_user_prefs_path", return_value=str(prefs_file)):
            prefs_file.write_text(json.dumps({"pool_swipe": 3}), encoding="utf-8")
            assert load_swipe_passes("v1") == {}

            prefs_file.write_text(
                json.dumps(
                    {
                        "pool_swipe": {
                            "version": "v1",
                            "passed": {
                                "top": ["Gangplank", 7, None],
                                "middle": "Zoe",
                                "bogus": ["X"],
                                "bottom": ["Jinx"],
                            },
                        }
                    }
                ),
                encoding="utf-8",
            )
            passes = load_swipe_passes("v1")

        assert passes == {"top": ["Gangplank"], "bottom": ["Jinx"]}


class TestPoolExclusions:
    """Champions exclus par poste du générateur de pools (SPEC-50 §4.4)."""

    def test_add_then_load(self, tmp_path):
        prefs_file = tmp_path / "user_prefs.json"

        with patch("src.user_prefs.get_user_prefs_path", return_value=str(prefs_file)):
            assert save_pool_exclusion("top", "Gangplank", True) is True
            assert save_pool_exclusion("top", "Fiora", True) is True
            exclusions = load_pool_exclusions()

        assert exclusions == {"top": ["Gangplank", "Fiora"]}

    def test_duplicate_ignored_case_insensitively(self, tmp_path):
        prefs_file = tmp_path / "user_prefs.json"

        with patch("src.user_prefs.get_user_prefs_path", return_value=str(prefs_file)):
            save_pool_exclusion("top", "Gangplank", True)
            save_pool_exclusion("top", "GANGPLANK", True)
            exclusions = load_pool_exclusions()

        assert exclusions == {"top": ["Gangplank"]}

    def test_removal_is_case_insensitive(self, tmp_path):
        prefs_file = tmp_path / "user_prefs.json"

        with patch("src.user_prefs.get_user_prefs_path", return_value=str(prefs_file)):
            save_pool_exclusion("top", "Gangplank", True)
            save_pool_exclusion("top", "Fiora", True)
            assert save_pool_exclusion("top", "gangplank", False) is True
            exclusions = load_pool_exclusions()

        assert exclusions == {"top": ["Fiora"]}

    def test_removing_absent_champion_returns_true_without_change(self, tmp_path):
        prefs_file = tmp_path / "user_prefs.json"

        with patch("src.user_prefs.get_user_prefs_path", return_value=str(prefs_file)):
            save_pool_exclusion("top", "Fiora", True)
            before = json.loads(prefs_file.read_text(encoding="utf-8"))
            assert save_pool_exclusion("top", "Gangplank", False) is True
            after = json.loads(prefs_file.read_text(encoding="utf-8"))

        assert after == before
        assert load_pool_exclusions() == {"top": ["Fiora"]}

    def test_unknown_lane_refused_without_writing(self, tmp_path):
        prefs_file = tmp_path / "user_prefs.json"

        with patch("src.user_prefs.get_user_prefs_path", return_value=str(prefs_file)):
            assert save_pool_exclusion("mid", "Zoe", True) is False

        assert not prefs_file.exists()

    def test_empty_champion_refused_without_writing(self, tmp_path):
        prefs_file = tmp_path / "user_prefs.json"

        with patch("src.user_prefs.get_user_prefs_path", return_value=str(prefs_file)):
            assert save_pool_exclusion("top", "", True) is False

        assert not prefs_file.exists()

    def test_emptied_lane_disappears_from_dict(self, tmp_path):
        prefs_file = tmp_path / "user_prefs.json"

        with patch("src.user_prefs.get_user_prefs_path", return_value=str(prefs_file)):
            save_pool_exclusion("top", "Fiora", True)
            save_pool_exclusion("middle", "Zoe", True)
            save_pool_exclusion("top", "Fiora", False)
            data = json.loads(prefs_file.read_text(encoding="utf-8"))

        assert data["pool_exclusions"] == {"middle": ["Zoe"]}

    def test_neighbour_keys_survive(self, tmp_path):
        prefs_file = tmp_path / "user_prefs.json"

        with patch("src.user_prefs.get_user_prefs_path", return_value=str(prefs_file)):
            save_motion("reduit")
            save_role_pool("middle", "GRIND")
            save_pool_exclusion("top", "Gangplank", True)

        data = json.loads(prefs_file.read_text(encoding="utf-8"))
        assert data["motion"] == "reduit"
        assert data["pools_by_role"] == {"middle": "GRIND"}
        assert data["pool_exclusions"] == {"top": ["Gangplank"]}

    def test_pool_exclusions_survive_save_user_prefs(self, tmp_path):
        prefs_file = tmp_path / "user_prefs.json"

        with patch("src.user_prefs.get_user_prefs_path", return_value=str(prefs_file)):
            save_pool_exclusion("top", "Gangplank", True)
            save_user_prefs(UserPrefs(auto_hover=True))

        data = json.loads(prefs_file.read_text(encoding="utf-8"))
        assert data["pool_exclusions"] == {"top": ["Gangplank"]}
        assert data["auto_hover"] is True

    def test_corrupted_value_is_read_as_empty(self, tmp_path):
        prefs_file = tmp_path / "user_prefs.json"

        with patch("src.user_prefs.get_user_prefs_path", return_value=str(prefs_file)):
            prefs_file.write_text(json.dumps({"pool_exclusions": ["Gangplank"]}), encoding="utf-8")
            assert load_pool_exclusions() == {}

            prefs_file.write_text(
                json.dumps(
                    {
                        "pool_exclusions": {
                            "top": ["Gangplank", 7, None],
                            "middle": "Zoe",
                            "bogus": ["X"],
                        }
                    }
                ),
                encoding="utf-8",
            )
            exclusions = load_pool_exclusions()

        assert exclusions == {"top": ["Gangplank"]}
