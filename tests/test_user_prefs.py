"""Tests pour la persistance des préférences du draft coach (SPEC-06 D2)."""

import json
from unittest.mock import patch

from src.user_prefs import UserPrefs, load_user_prefs, save_user_prefs


class TestSaveLoadRoundTrip:
    """Sauvegarde puis relecture des préférences."""

    def test_round_trip(self, tmp_path):
        prefs_file = tmp_path / "user_prefs.json"
        prefs = UserPrefs(
            auto_hover=True,
            auto_accept_queue=False,
            auto_ban_hover=True,
            open_onetricks=True,
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
        `synergy_weight`, supprimé avec le curseur synergie/matchup. Une clé
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


class TestSaveErrorHandling:
    """save_user_prefs ne doit jamais lever d'exception (best-effort)."""

    def test_save_returns_false_on_filesystem_error(self, tmp_path):
        prefs_file = tmp_path / "readonly_dir" / "user_prefs.json"

        with patch("src.user_prefs.get_user_prefs_path", return_value=str(prefs_file)):
            with patch("builtins.open", side_effect=PermissionError("denied")):
                assert save_user_prefs(UserPrefs()) is False
