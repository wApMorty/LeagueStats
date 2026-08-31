"""Regression test for SPEC-04 B4 — role uniqueness is the central invariant
of infer_team_roles(): a team must never end up with two champions on the
same lane. 50 randomized compositions, fixed seed for reproducibility.
"""

import random

from src.role_inference import LANES, infer_team_roles


def _random_distribution(rng: random.Random) -> dict:
    return {lane: rng.uniform(0.0, 100.0) for lane in LANES}


def _random_team(rng: random.Random, size: int) -> tuple:
    champion_ids = list(range(1, size + 1))
    distributions = {champion_id: _random_distribution(rng) for champion_id in champion_ids}
    return champion_ids, distributions


def test_no_assignment_duplicates_a_role_across_50_random_compositions():
    rng = random.Random(20260901)  # fixed seed: deterministic across runs

    for _ in range(50):
        size = rng.randint(1, 5)
        champion_ids, distributions = _random_team(rng, size)

        # Randomly fix 0..size-1 ally roles from "the LCU", like a real draft.
        known_count = rng.randint(0, max(0, size - 1))
        known_champions = rng.sample(champion_ids, known_count)
        known_lanes = rng.sample(LANES, known_count)
        known_positions = dict(zip(known_champions, known_lanes))

        result = infer_team_roles(champion_ids, distributions, known_positions=known_positions)

        assert len(result.roles) == size
        assert len(set(result.roles.values())) == size, (
            f"Duplicate role in assignment {result.roles} "
            f"(champions={champion_ids}, known_positions={known_positions})"
        )
