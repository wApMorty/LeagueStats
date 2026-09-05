"""Tests for src/ui/pool_selection_ui.py (SPEC-10 -- couverture du chemin
critique).

This module was at 2.6% coverage despite being exactly the path of the
September 2026 lane bugs (see tests/test_trio_lane_aware.py): its
``_select_pool_for_analysis`` resolves ``ChampionPool.role`` to a
``matchups.lane`` value via ``pool_manager.pool_role_to_lane()``, and every
consumer (Team Builder, Tournament Coach, pre-calculated bans) depends on
that resolution being correct. These tests exercise the three interactive
selectors directly, mocking only ``PoolManager`` and ``input()`` -- never a
real pools.json or a real terminal.
"""

from unittest.mock import Mock, patch

import pytest

from src.pool_manager import ChampionPool
from src.ui.pool_selection_ui import (
    _select_pool_for_analysis,
    _select_pool_for_parsing,
    _select_pool_interactive,
)

TOP_POOL = ChampionPool(
    name="Top Mains",
    champions=["Aatrox", "Darius"],
    description="Top pool",
    role="top",
    created_by="user",
)
JUNGLE_POOL = ChampionPool(
    name="Jungle Mains",
    champions=["Lee Sin"],
    description="Jungle pool",
    role="jungle",
    created_by="system",
)
CUSTOM_POOL = ChampionPool(
    name="Flex Pool",
    champions=["Ahri", "Zed"],
    description="Multi-role pool",
    role="custom",
    created_by="user",
)


def _mock_pool_manager(pools: dict):
    manager = Mock()
    manager.get_all_pools.return_value = pools
    return manager


class TestSelectPoolForAnalysisRoleToLane:
    """The lane resolution is the whole point of this module: every pool
    role must map to its ``matchups.lane`` value (SPEC-04), never a guess."""

    @pytest.mark.parametrize(
        "role,expected_lane",
        [
            ("top", "top"),
            ("jungle", "jungle"),
            ("mid", "middle"),
            ("adc", "bottom"),
            ("support", "support"),
        ],
    )
    def test_known_role_resolves_to_its_lane(self, role, expected_lane):
        pool = ChampionPool(name="Solo Pool", champions=["Aatrox", "Darius", "Garen"], role=role)
        manager = _mock_pool_manager({"Solo Pool": pool})
        with patch("src.pool_manager.PoolManager", return_value=manager):
            with patch("builtins.input", return_value="1"):
                result = _select_pool_for_analysis()

        assert result == ("Solo Pool", ["Aatrox", "Darius", "Garen"], expected_lane)

    def test_custom_role_resolves_to_none_not_an_arbitrary_lane(self):
        """A multi-role/custom pool has no single lane -- must fall back to
        None (all-lanes), never guess one."""
        manager = _mock_pool_manager({"Flex Pool": CUSTOM_POOL})
        with patch("src.pool_manager.PoolManager", return_value=manager):
            with patch("builtins.input", return_value="1"):
                name, champions, lane = _select_pool_for_analysis()

        assert lane is None
        assert name == "Flex Pool"

    def test_unknown_role_string_resolves_to_none(self):
        """A role value pool_manager doesn't recognize must not crash the
        selector -- degrades to the all-lanes fallback like 'custom'."""
        weird_pool = ChampionPool(name="Weird", champions=["Zed"], role="mystery")
        manager = _mock_pool_manager({"Weird": weird_pool})
        with patch("src.pool_manager.PoolManager", return_value=manager):
            with patch("builtins.input", return_value="1"):
                _, _, lane = _select_pool_for_analysis()

        assert lane is None


class TestSelectPoolForAnalysisFlow:
    def test_no_pools_returns_none(self, capsys):
        manager = _mock_pool_manager({})
        with patch("src.pool_manager.PoolManager", return_value=manager):
            assert _select_pool_for_analysis() is None
        assert "Aucune pool trouvée" in capsys.readouterr().out

    def test_cancel_returns_none(self):
        manager = _mock_pool_manager({"Top Mains": TOP_POOL})
        with patch("src.pool_manager.PoolManager", return_value=manager):
            with patch("builtins.input", return_value="cancel"):
                assert _select_pool_for_analysis() is None

    def test_legacy_option_returns_none(self):
        """The trailing 'legacy Assistant selector' entry signals a repli,
        not a resolved pool."""
        manager = _mock_pool_manager({"Top Mains": TOP_POOL})
        with patch("src.pool_manager.PoolManager", return_value=manager):
            with patch("builtins.input", return_value="2"):  # 1=pool, 2=legacy
                assert _select_pool_for_analysis() is None

    def test_out_of_range_choice_returns_none(self, capsys):
        manager = _mock_pool_manager({"Top Mains": TOP_POOL})
        with patch("src.pool_manager.PoolManager", return_value=manager):
            with patch("builtins.input", return_value="99"):
                assert _select_pool_for_analysis() is None
        assert "Choix invalide" in capsys.readouterr().out

    def test_non_numeric_choice_returns_none(self, capsys):
        manager = _mock_pool_manager({"Top Mains": TOP_POOL})
        with patch("src.pool_manager.PoolManager", return_value=manager):
            with patch("builtins.input", return_value="abc"):
                assert _select_pool_for_analysis() is None
        assert "Entrée invalide" in capsys.readouterr().out

    def test_pool_manager_exception_returns_none(self, capsys):
        with patch("src.pool_manager.PoolManager", side_effect=Exception("pools.json corrupted")):
            assert _select_pool_for_analysis() is None
        assert "Erreur de sélection" in capsys.readouterr().out

    def test_pools_are_listed_sorted_by_name(self, capsys):
        manager = _mock_pool_manager({"Zulu Pool": JUNGLE_POOL, "Alpha Pool": TOP_POOL})
        with patch("src.pool_manager.PoolManager", return_value=manager):
            with patch("builtins.input", return_value="1"):
                name, _, _ = _select_pool_for_analysis()

        out = capsys.readouterr().out
        assert out.index("Alpha Pool") < out.index("Zulu Pool")
        assert name == "Alpha Pool"


class TestSelectPoolForParsing:
    def test_no_pools_returns_none(self, capsys):
        manager = _mock_pool_manager({})
        with patch("src.pool_manager.PoolManager", return_value=manager):
            assert _select_pool_for_parsing() is None
        assert "Aucune pool trouvée" in capsys.readouterr().out

    def test_cancel_returns_none(self):
        manager = _mock_pool_manager({"Top Mains": TOP_POOL})
        with patch("src.pool_manager.PoolManager", return_value=manager):
            with patch("builtins.input", return_value="cancel"):
                assert _select_pool_for_parsing() is None

    def test_valid_choice_returns_name_and_champions_only(self):
        """Unlike _select_pool_for_analysis, this selector has no lane in
        its return value (used for scraping, not scoring)."""
        manager = _mock_pool_manager({"Top Mains": TOP_POOL})
        with patch("src.pool_manager.PoolManager", return_value=manager):
            with patch("builtins.input", return_value="1"):
                result = _select_pool_for_parsing()

        assert result == ("Top Mains", ["Aatrox", "Darius"])

    def test_all_champions_option(self):
        manager = _mock_pool_manager({"Top Mains": TOP_POOL})
        with patch("src.pool_manager.PoolManager", return_value=manager):
            with patch("builtins.input", return_value="2"):  # 1=pool, 2=ALL, 3=default
                name, champions = _select_pool_for_parsing()

        assert name == "ALL CHAMPIONS"
        assert len(champions) > 0

    def test_default_option_returns_none(self):
        manager = _mock_pool_manager({"Top Mains": TOP_POOL})
        with patch("src.pool_manager.PoolManager", return_value=manager):
            with patch("builtins.input", return_value="3"):  # 1=pool, 2=ALL, 3=default
                assert _select_pool_for_parsing() is None

    def test_out_of_range_returns_none(self, capsys):
        manager = _mock_pool_manager({"Top Mains": TOP_POOL})
        with patch("src.pool_manager.PoolManager", return_value=manager):
            with patch("builtins.input", return_value="99"):
                assert _select_pool_for_parsing() is None
        assert "Choix invalide" in capsys.readouterr().out

    def test_non_numeric_returns_none(self, capsys):
        manager = _mock_pool_manager({"Top Mains": TOP_POOL})
        with patch("src.pool_manager.PoolManager", return_value=manager):
            with patch("builtins.input", return_value="xyz"):
                assert _select_pool_for_parsing() is None
        assert "Entrée invalide" in capsys.readouterr().out

    def test_pool_manager_exception_returns_none(self, capsys):
        with patch("src.pool_manager.PoolManager", side_effect=Exception("boom")):
            assert _select_pool_for_parsing() is None
        assert "Erreur de sélection" in capsys.readouterr().out


class TestSelectPoolInteractive:
    def test_no_pools_returns_none(self, capsys):
        manager = _mock_pool_manager({})
        assert _select_pool_interactive(manager) is None
        assert "Aucune pool trouvée" in capsys.readouterr().out

    def test_cancel_returns_none(self):
        manager = _mock_pool_manager({"Top Mains": TOP_POOL})
        with patch("builtins.input", return_value="cancel"):
            assert _select_pool_interactive(manager) is None

    def test_valid_choice_returns_the_champion_pool_object(self):
        manager = _mock_pool_manager({"Top Mains": TOP_POOL})
        with patch("builtins.input", return_value="1"):
            result = _select_pool_interactive(manager)

        assert result is TOP_POOL

    def test_out_of_range_returns_none(self, capsys):
        manager = _mock_pool_manager({"Top Mains": TOP_POOL})
        with patch("builtins.input", return_value="99"):
            assert _select_pool_interactive(manager) is None
        assert "Choix invalide" in capsys.readouterr().out

    def test_non_numeric_returns_none(self, capsys):
        manager = _mock_pool_manager({"Top Mains": TOP_POOL})
        with patch("builtins.input", return_value="nope"):
            assert _select_pool_interactive(manager) is None
        assert "Entrée invalide" in capsys.readouterr().out

    def test_custom_action_name_is_shown_uppercased(self, capsys):
        manager = _mock_pool_manager({"Top Mains": TOP_POOL})
        with patch("builtins.input", return_value="1"):
            _select_pool_interactive(manager, action_name="choisir une pool de test")

        assert "CHOISIR UNE POOL DE TEST" in capsys.readouterr().out
