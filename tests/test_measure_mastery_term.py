"""Tests de la validation croisée de scripts/measure_mastery_term.py (SPEC-41 tâche 199, SPEC-42 tâche 205)."""

import random

import pytest

from scripts import measure_mastery_term as study
from src.config_constants import analysis_config


def _rows(players: int = 30, games: int = 12, seed: int = 0):
    """Lignes synthétiques : chaque joueur a 3 champions possibles, un vis-à-vis de lane parfois absent,
    impact, lane et victoire au hasard."""
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
                    opponent=rng.choice(["Gangplank", "Malphite", "Sylas", None]),
                    lane=rng.gauss(0.0, 0.05),
                )
            )
    return rows


def test_validation_croisee_sans_fuite_du_bloc_de_test(monkeypatch):
    """Ni K, K₂ ni les normes d'un bloc ne voient un joueur de ce bloc ; chaque ligne est prédite une fois."""
    rows = _rows()
    focal = {r.puuid for r in rows}
    seen = []  # (fonction, puuids vus) dans l'ordre des appels, un bloc après l'autre
    real_norms, real_k, real_k2 = study.champion_norms, study.estimate_k, study.estimate_k2

    def spy_norms(train_rows):
        seen.append(("norms", {r.puuid for r in train_rows}))
        return real_norms(train_rows)

    def spy_k(by_player, norms, field="points"):
        seen.append(("k", set(by_player)))
        return real_k(by_player, norms, field)

    def spy_k2(by_player):
        seen.append(("k2", set(by_player)))
        return real_k2(by_player)

    monkeypatch.setattr(study, "champion_norms", spy_norms)
    monkeypatch.setattr(study, "estimate_k", spy_k)
    monkeypatch.setattr(study, "estimate_k2", spy_k2)

    pooled = study.cross_validate(rows, focal)

    assert pooled is not None
    # une fois les normes, K de a à d, puis K₂ une fois
    calls_per_fold = 1 + 4 + 1
    assert len(seen) == analysis_config.MASTERY_STUDY_FOLDS * calls_per_fold
    for fold in range(analysis_config.MASTERY_STUDY_FOLDS):
        test_players = {p for p in focal if study._fold(p) == fold}
        for _, puuids in seen[fold * calls_per_fold : (fold + 1) * calls_per_fold]:
            assert puuids and not puuids & test_players
    assert sorted(pooled.players) == sorted(r.puuid for r in rows)
    for variant in study.VARIANTS:
        assert len(pooled.variants[variant]) == len(rows)


def test_colonnes_par_variante():
    """a à d : biais, draft, maîtrise ; e ajoute M × lane ; f ajoute D ; g ajoute les deux."""
    row = study.Row(
        puuid="p",
        game=0,
        champion="Olaf",
        win=1,
        points=0.0,
        draft=0.5,
        opponent="Gangplank",
        lane=0.2,
    )
    assert study._columns("a", row, 3.0, 9.0) == [1.0, 0.5, 3.0]
    assert study._columns("d", row, 3.0, 9.0) == [1.0, 0.5, 3.0]
    assert study._columns("e", row, 3.0, 9.0) == pytest.approx([1.0, 0.5, 3.0, 0.6])
    assert study._columns("f", row, 3.0, 9.0) == [1.0, 0.5, 3.0, 9.0]
    assert study._columns("g", row, 3.0, 9.0) == pytest.approx([1.0, 0.5, 3.0, 0.6, 9.0])


def test_vis_a_vis_de_lane_unique_ou_absent():
    """Un seul participant adverse par poste : c'est le vis-à-vis ; poste doublé ou inconnu : aucun."""
    team_of = {1: 100, 2: 100, 3: 100, 4: 100, 5: 100, 6: 200, 7: 200, 8: 200, 9: 200, 10: 200}
    roles = dict(zip(range(1, 11), ["top", "jungle", "middle", "bottom", "support"] * 2))
    roles[7] = "top"  # équipe 200 : deux « top » (6 et 7) face au seul « top » 1
    roles[10] = None  # poste inconnu : aucun vis-à-vis pour 5
    opponents = study.lane_opponents(team_of, roles)
    assert opponents[1] is None  # deux tops adverses : pas de vis-à-vis unique
    assert (
        opponents[6] == 1 and opponents[7] == 1
    )  # chacun des deux « top » adverses a 1 pour unique vis-à-vis
    assert opponents[2] is None  # jungle sans jungle adverse
    assert opponents[5] is None  # support sans poste connu côté adverse
    assert opponents[3] == 8 and opponents[8] == 3  # milieu contre milieu


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


def test_lignes_de_partie_portent_le_vis_a_vis_et_son_duel(monkeypatch):
    """`_game_rows` : chaque ligne porte le champion de son vis-à-vis de lane et le duel vu de son
    côté, (moi, poste) contre (lui, poste)."""
    posts = ["top", "jungle", "middle", "bottom", "support"]
    roles = {pid: posts[(pid - 1) % 5] for pid in range(1, 11)}
    game = {
        "participants": [
            {"participantId": pid, "teamId": study.BLUE if pid <= 5 else 200, "championId": pid}
            for pid in range(1, 11)
        ],
        "participantIdentities": [
            {"participantId": pid, "player": {"puuid": f"p{pid}"}} for pid in range(1, 11)
        ],
    }
    names = {1: "Olaf", 6: "Gangplank", **{i: f"C{i}" for i in (2, 3, 4, 5, 7, 8, 9, 10)}}
    monkeypatch.setattr(study, "blue_win", lambda _game: True)
    monkeypatch.setattr(study, "participant_roles", lambda _game: dict(roles))
    monkeypatch.setattr(study, "impacts", lambda *_args: {"rows": []})
    duels = []

    class Evaluator:
        def team_logit(self, _allies, _enemies):
            return 0.0

        def matchup_logit(self, champion, enemy):
            duels.append((champion, enemy))
            return 0.25 if champion == ("Olaf", "top") else -0.25

    rows = study._game_rows(0, game, {"frames": [{}]}, None, names, Evaluator())

    by_champion = {r.champion: r for r in rows}
    assert by_champion["Olaf"].opponent == "Gangplank"
    assert by_champion["Olaf"].lane == 0.25
    assert by_champion["Gangplank"].opponent == "Olaf"
    assert by_champion["Gangplank"].lane == -0.25
    assert (("Olaf", "top"), ("Gangplank", "top")) in duels
    assert by_champion["C3"].opponent == "C8"  # milieu contre milieu
