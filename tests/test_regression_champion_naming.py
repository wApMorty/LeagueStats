"""
Regression test for champion naming consistency between constants.py and database.

Bug: Champions with compound names (ChoGath, BelVeth, KhaZix, KaiSa, VelKoz) had
case mismatches between constants.py (CamelCase) and database (lowercase after first letter).
This caused the draft monitor to fail filtering banned champions because the ID lookup
failed for these champions.

Fixed in: PR #26 commit XXXXXX

Test ensures:
1. All champion names in pool constants match exactly with database names
2. No case sensitivity issues that would break ID lookups
3. Ban filtering works correctly for all champions
"""

import pytest
from src.db import Database
from src.constants import (
    TOP_CHAMPIONS,
    JUNGLE_CHAMPIONS,
    MID_CHAMPIONS,
    ADC_CHAMPIONS,
    SUPPORT_CHAMPIONS,
)


@pytest.fixture
def db():
    """Database fixture."""
    database = Database("data/db.db")
    database.connect()
    yield database
    database.close()


def test_all_pool_champions_exist_in_database(db):
    """
    Regression test: All pool champion names must exactly match database names.

    Bug: ChoGath, BelVeth, KhaZix, KaiSa, VelKoz in constants.py didn't match
    database (Chogath, Belveth, Khazix, Kaisa, Velkoz), causing ID lookup
    failures and breaking ban filtering.

    Expected: Every champion name in every pool must exist in the database
    with exact case-sensitive match.
    """
    # Get all champions from database
    champion_id_to_name = db.get_all_champion_names()
    db_champion_names = set(champion_id_to_name.values())

    # Collect all pool champions
    all_pool_champions = set()
    all_pool_champions.update(TOP_CHAMPIONS)
    all_pool_champions.update(JUNGLE_CHAMPIONS)
    all_pool_champions.update(MID_CHAMPIONS)
    all_pool_champions.update(ADC_CHAMPIONS)
    all_pool_champions.update(SUPPORT_CHAMPIONS)

    # Find mismatches
    missing_champions = []
    for champion_name in all_pool_champions:
        if champion_name not in db_champion_names:
            missing_champions.append(champion_name)

    # Assert no mismatches
    assert len(missing_champions) == 0, (
        f"Found {len(missing_champions)} champion name mismatches between "
        f"constants.py pools and database: {missing_champions}. "
        f"These champions will fail ID lookup in draft_monitor.py, breaking "
        f"ban filtering. Fix by matching constants.py names to database names."
    )


def test_specific_compound_name_champions(db):
    """
    Regression test: Specific champions with compound names that had bugs.

    Bug: These 5 champions had case mismatches:
    - ChoGath -> Chogath
    - BelVeth -> Belveth
    - KhaZix -> Khazix
    - KaiSa -> Kaisa
    - VelKoz -> Velkoz

    Expected: All these champions must exist in database with correct casing.
    """
    champion_id_to_name = db.get_all_champion_names()
    db_champion_names = set(champion_id_to_name.values())

    # These are the CORRECT names that should be in both constants.py and database
    compound_name_champions = ["Chogath", "Belveth", "Khazix", "Kaisa", "Velkoz"]

    # All must exist in database
    for champion_name in compound_name_champions:
        assert champion_name in db_champion_names, (
            f"Champion '{champion_name}' not found in database. "
            f"This is a regression of the compound name bug."
        )

    # OLD incorrect names must NOT be in constants.py pools
    all_pool_champions = set()
    all_pool_champions.update(TOP_CHAMPIONS)
    all_pool_champions.update(JUNGLE_CHAMPIONS)
    all_pool_champions.update(MID_CHAMPIONS)
    all_pool_champions.update(ADC_CHAMPIONS)
    all_pool_champions.update(SUPPORT_CHAMPIONS)

    incorrect_names = ["ChoGath", "BelVeth", "KhaZix", "KaiSa", "VelKoz"]
    for incorrect_name in incorrect_names:
        assert incorrect_name not in all_pool_champions, (
            f"Found incorrect name '{incorrect_name}' in constants.py pools. "
            f"Should be the database-matching version (lowercase after first letter). "
            f"This breaks ban filtering in draft monitor."
        )


def test_reverse_lookup_works_for_all_champions(db):
    """
    Regression test: Reverse lookup (name -> ID) must work for all pool champions.

    Bug: ID lookup in draft_monitor.py (line 632) failed for champions with
    case mismatches, causing those champions to be excluded from pool_champion_ids,
    which broke ban filtering.

    Expected: Reverse lookup dict must successfully find IDs for all pool champions.
    """
    champion_id_to_name = db.get_all_champion_names()

    # Build reverse lookup dict (same as draft_monitor.py line 632)
    name_to_id = {name: champ_id for champ_id, name in champion_id_to_name.items()}

    # Collect all pool champions
    all_pool_champions = set()
    all_pool_champions.update(TOP_CHAMPIONS)
    all_pool_champions.update(JUNGLE_CHAMPIONS)
    all_pool_champions.update(MID_CHAMPIONS)
    all_pool_champions.update(ADC_CHAMPIONS)
    all_pool_champions.update(SUPPORT_CHAMPIONS)

    # All pool champions must be found in reverse lookup
    lookup_failures = []
    for champion_name in all_pool_champions:
        if champion_name not in name_to_id:
            lookup_failures.append(champion_name)

    assert len(lookup_failures) == 0, (
        f"Reverse lookup (name -> ID) failed for {len(lookup_failures)} champions: "
        f"{lookup_failures}. This means these champions won't be in pool_champion_ids "
        f"in draft_monitor.py, breaking their ban filtering."
    )
