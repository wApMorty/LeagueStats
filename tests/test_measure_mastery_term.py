"""Tests de la validation croisée de scripts/measure_mastery_term.py (SPEC-41 tâche 199)."""

import random

from scripts import measure_mastery_term as study
from src.config_constants import analysis_config


def _rows(players: int = 30, games: int = 12, seed: int = 0):
    """Lignes synthétiques : chaque joueur a 3 champions possibles, impact et victoire au hasard."""
    rng = random.Random(seed)
    rows = []
    for p in range(players):
        for g in range(games):
            rows.append(
                study.Row(
                    puuid=f"joueur-{p}",
                    game=p * games + g,
                    champion=rng.choice(["Gnar", "Olaf", "Shen"]),
                    win=rng.randint(0, 1),
                    points=rng.gauss(0.0, 15.0),
                    draft=rng.gauss(0.0, 0.2),
                )
            )
    return rows


def test_validation_croisee_sans_fuite_du_bloc_de_test(monkeypatch):
    """Ni K ni les normes d'un bloc ne voient un joueur de ce bloc ; chaque ligne est prédite une fois."""
    rows = _rows()
    focal = {r.puuid for r in rows}
    seen = []  # (fonction, puuids vus) dans l'ordre des appels, un bloc après l'autre
    real_norms, real_k = study.champion_norms, study.estimate_k

    def spy_norms(train_rows):
        seen.append(("norms", {r.puuid for r in train_rows}))
        return real_norms(train_rows)

    def spy_k(by_player, norms):
        seen.append(("k", set(by_player)))
        return real_k(by_player, norms)

    monkeypatch.setattr(study, "champion_norms", spy_norms)
    monkeypatch.setattr(study, "estimate_k", spy_k)

    pooled = study.cross_validate(rows, focal)

    assert pooled is not None
    calls_per_fold = 1 + len(study.VARIANTS)  # une fois les normes, puis K par variante
    assert len(seen) == analysis_config.MASTERY_STUDY_FOLDS * calls_per_fold
    for fold in range(analysis_config.MASTERY_STUDY_FOLDS):
        test_players = {p for p in focal if study._fold(p) == fold}
        for _, puuids in seen[fold * calls_per_fold : (fold + 1) * calls_per_fold]:
            assert puuids and not puuids & test_players
    assert sorted(pooled.players) == sorted(r.puuid for r in rows)
    for variant in study.VARIANTS:
        assert len(pooled.variants[variant]) == len(rows)
