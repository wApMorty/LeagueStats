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

    def spy_k(by_player, norms, field="points"):
        seen.append(("k", set(by_player)))
        return real_k(by_player, norms, field)

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


def test_impact_relatif_aux_coequipiers_et_a_l_adversaire_de_lane():
    """+5 quand ses coéquipiers font +20 : −15 relatif à l'équipe ; écart de lane contre son vis-à-vis."""
    team_of = {1: 100, 2: 100, 3: 100, 4: 100, 5: 100, 6: 200, 7: 200, 8: 200, 9: 200, 10: 200}
    roles = dict(zip(range(1, 11), ["top", "jungle", "middle", "bottom", "support"] * 2))
    points = {1: 5.0, 2: 20.0, 3: 20.0, 4: 20.0, 5: 20.0, 6: -12.0, 7: 0.0, 8: 0.0, 9: 0.0, 10: 0.0}

    relative = study.relative_values(points, team_of, roles)

    assert relative[1] == (5.0 - 20.0, 5.0 - (-12.0))
    assert relative[6] == (-12.0 - 0.0, -12.0 - 5.0)


def test_sans_adversaire_de_meme_poste_l_ecart_de_lane_vaut_zero():
    team_of = {1: 100, 2: 200}
    relative = study.relative_values({1: 3.0, 2: -4.0}, team_of, {1: "top", 2: None})
    assert relative[1][1] == 0.0 and relative[1][0] == 0.0  # ni vis-à-vis ni coéquipier


def test_choix_de_la_variante():
    """a reste la référence ; une autre ne la remplace que si son gain la dépasse significativement."""
    players = [f"j{i}" for i in range(40)] * 5
    gains = {
        "a": [0.001] * 200,
        "c": [0.003 + (0.0001 if i % 2 else -0.0001) for i in range(200)],  # nettement meilleure
        "d": [0.001 + (0.002 if i % 2 else -0.002) for i in range(200)],  # pareille en moyenne
    }
    adopted = {v: (40.0, [0.0, 1.0, 0.07]) for v in ("a", "c", "d")}
    assert study.choose(adopted, gains, players, seed=1) == "c"
    assert study.choose({v: adopted[v] for v in ("a", "d")}, gains, players, seed=1) == "a"
    assert study.choose({"d": adopted["d"]}, gains, players, seed=1) == "d"
    assert study.choose({}, gains, players, seed=1) is None
