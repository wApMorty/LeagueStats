"""Characterization tests for the champion-pool selection of ``DraftMonitor``
(SPEC TODO E10 safety net).

Scope:
- ``_select_champion_pool_by_name`` (SPEC-06 D2 remembered pool)
- ``_select_champion_pool_interactive``

These tests pin the CURRENT behavior, including the exact console messages and
the ``self.pool_name`` bookkeeping that drives the pre-calculated ban lookups.
"""

from unittest.mock import Mock, patch

import pytest

from src.constants import CHAMPIONS_BY_ROLE
from src.draft_monitor import DraftMonitor
from src.pool_manager import ChampionPool


@pytest.fixture
def monitor():
    """DraftMonitor with Assistant and LCUClient fully mocked out."""
    with patch("src.draft_monitor.Assistant", return_value=Mock()):
        with patch("src.draft_monitor.LCUClient", return_value=Mock()):
            return DraftMonitor(verbose=False, auto_hover=False)


ALPHA = ChampionPool(
    name="Alpha Pool",
    champions=["Aatrox", "Darius", "Garen"],
    description="Custom top pool",
    role="top",
    created_by="user",
)
BETA = ChampionPool(
    name="Beta Pool",
    champions=["Ahri", "Zed"],
    description="System mid pool",
    role="mid",
    created_by="system",
)


@pytest.fixture
def pool_manager():
    """Mock PoolManager patched at its definition site (imported lazily)."""
    manager = Mock()
    manager.get_all_pools.return_value = {"Beta Pool": BETA, "Alpha Pool": ALPHA}
    manager.get_pool.return_value = None
    with patch("src.pool_manager.PoolManager", return_value=manager):
        yield manager


class TestSelectChampionPoolByName:
    """``_select_champion_pool_by_name(pool_name)``."""

    def test_known_pool_is_used_without_prompting(self, monitor, pool_manager, capsys):
        # Arrange
        pool_manager.get_pool.return_value = ALPHA

        # Act
        champions = monitor._select_champion_pool_by_name("Alpha Pool")

        # Assert
        assert champions == ["Aatrox", "Darius", "Garen"]
        assert monitor.pool_name == "Alpha Pool"
        out = capsys.readouterr().out
        assert "[OK] Pool mémorisée utilisée : Alpha Pool (Aatrox, Darius, Garen)" in out
        pool_manager.get_pool.assert_called_once_with("Alpha Pool")

    def test_unknown_pool_falls_back_to_interactive(self, monitor, pool_manager, capsys):
        """A pool deleted/renamed since the last session re-opens the prompt."""
        # Arrange
        pool_manager.get_pool.return_value = None

        with patch.object(
            monitor, "_select_champion_pool_interactive", return_value=["Fallback"]
        ) as interactive:
            # Act
            champions = monitor._select_champion_pool_by_name("Ghost Pool")

        # Assert
        assert champions == ["Fallback"]
        interactive.assert_called_once_with()
        assert (
            "[INFO] Pool 'Ghost Pool' introuvable, sélection manuelle." in capsys.readouterr().out
        )

    def test_unknown_pool_does_not_set_pool_name(self, monitor, pool_manager):
        """``pool_name`` is left to the interactive path, not pre-set here."""
        pool_manager.get_pool.return_value = None

        with patch.object(monitor, "_select_champion_pool_interactive", return_value=[]):
            monitor._select_champion_pool_by_name("Ghost Pool")

        assert monitor.pool_name is None

    def test_pool_manager_failure_falls_back_to_interactive(self, monitor, capsys):
        """Any exception (corrupted pools file, ...) degrades to the prompt."""
        with patch("src.pool_manager.PoolManager", side_effect=Exception("pools.json corrupted")):
            with patch.object(
                monitor, "_select_champion_pool_interactive", return_value=["Fallback"]
            ) as interactive:
                # Act
                champions = monitor._select_champion_pool_by_name("Alpha Pool")

        # Assert
        assert champions == ["Fallback"]
        interactive.assert_called_once_with()
        out = capsys.readouterr().out
        assert "[WARNING] Erreur lors du chargement de la pool mémorisée" in out


class TestSelectChampionPoolInteractive:
    """``_select_champion_pool_interactive()``.

    Pools are listed sorted by name, so with the fixture:
      1 = Alpha Pool, 2 = Beta Pool, 3 = legacy assistant selector.
    """

    def test_lists_pools_sorted_by_name_with_status_markers(self, monitor, pool_manager, capsys):
        with patch("builtins.input", return_value="1"):
            monitor._select_champion_pool_interactive()

        out = capsys.readouterr().out
        assert "SÉLECTION DE LA POOL DE CHAMPIONS" in out
        assert "1. [USR] Alpha Pool" in out
        assert "2. [SYS] Beta Pool" in out
        assert "3. Utiliser le sélecteur de pool étendu de l'assistant (legacy)" in out
        assert out.index("Alpha Pool") < out.index("Beta Pool")

    def test_valid_choice_returns_that_pool(self, monitor, pool_manager, capsys):
        with patch("builtins.input", return_value="2"):
            champions = monitor._select_champion_pool_interactive()

        assert champions == ["Ahri", "Zed"]
        assert monitor.pool_name == "Beta Pool"
        assert "[OK] Pool utilisée : Beta Pool (Ahri, Zed)" in capsys.readouterr().out

    def test_whitespace_around_the_choice_is_stripped(self, monitor, pool_manager):
        with patch("builtins.input", return_value="  1  "):
            champions = monitor._select_champion_pool_interactive()

        assert champions == ["Aatrox", "Darius", "Garen"]
        assert monitor.pool_name == "Alpha Pool"

    def test_legacy_option_delegates_to_the_assistant(self, monitor, pool_manager):
        """The legacy selector clears ``pool_name`` (no pre-calculated bans)."""
        monitor.pool_name = "Stale Pool"
        monitor.assistant.select_champion_pool.return_value = ["Legacy1", "Legacy2"]

        with patch("builtins.input", return_value="3"):
            champions = monitor._select_champion_pool_interactive()

        assert champions == ["Legacy1", "Legacy2"]
        assert monitor.pool_name is None
        monitor.assistant.select_champion_pool.assert_called_once_with()

    def test_out_of_range_choice_defaults_to_top_pool(self, monitor, pool_manager, capsys):
        with patch("builtins.input", return_value="99"):
            champions = monitor._select_champion_pool_interactive()

        assert champions == CHAMPIONS_BY_ROLE["top"]
        assert monitor.pool_name == "All Top Champions"
        assert "[WARNING] Choix invalide" in capsys.readouterr().out

    def test_zero_choice_defaults_to_top_pool(self, monitor, pool_manager, capsys):
        """0 is neither a listed pool nor the legacy option."""
        with patch("builtins.input", return_value="0"):
            champions = monitor._select_champion_pool_interactive()

        assert champions == CHAMPIONS_BY_ROLE["top"]
        assert monitor.pool_name == "All Top Champions"
        assert "[WARNING] Choix invalide" in capsys.readouterr().out

    def test_non_numeric_input_defaults_to_top_pool(self, monitor, pool_manager, capsys):
        """``int(...)`` raises ValueError -> "Saisie invalide" (not "Choix")."""
        with patch("builtins.input", return_value="abc"):
            champions = monitor._select_champion_pool_interactive()

        assert champions == CHAMPIONS_BY_ROLE["top"]
        assert monitor.pool_name == "All Top Champions"
        out = capsys.readouterr().out
        assert "[WARNING] Saisie invalide, utilisation de la pool TOP par défaut" in out

    def test_empty_input_defaults_to_top_pool(self, monitor, pool_manager, capsys):
        with patch("builtins.input", return_value=""):
            champions = monitor._select_champion_pool_interactive()

        assert champions == CHAMPIONS_BY_ROLE["top"]
        assert "[WARNING] Saisie invalide" in capsys.readouterr().out

    def test_no_pool_available_makes_one_the_legacy_option(self, monitor, capsys):
        """With zero pools, index 1 is directly the legacy selector."""
        manager = Mock()
        manager.get_all_pools.return_value = {}
        monitor.assistant.select_champion_pool.return_value = ["Legacy"]

        with patch("src.pool_manager.PoolManager", return_value=manager):
            with patch("builtins.input", return_value="1"):
                champions = monitor._select_champion_pool_interactive()

        assert champions == ["Legacy"]
        assert monitor.pool_name is None

    def test_pool_manager_failure_falls_back_to_legacy_selector(self, monitor, capsys):
        monitor.pool_name = "Stale Pool"
        monitor.assistant.select_champion_pool.return_value = ["Legacy"]

        with patch("src.pool_manager.PoolManager", side_effect=Exception("boom")):
            champions = monitor._select_champion_pool_interactive()

        assert champions == ["Legacy"]
        assert monitor.pool_name is None
        out = capsys.readouterr().out
        assert "[WARNING] Erreur de sélection de pool: boom" in out
        assert "Retour au sélecteur de pool legacy..." in out
