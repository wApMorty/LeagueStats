"""Rejugement d'ADR-004 : grappes du bootstrap, placebo et forme lue avant la partie."""

from statistics import mean

import pytest

from scripts import rejudge_winchance_terms as rwt
from scripts.measure_form_term import Game


def test_grouped_range_les_parties_consecutives_dans_un_meme_bloc() -> None:
    deltas = [(0, 1.0), (0, 2.0), (1, 3.0), (2, 4.0), (3, 5.0)]
    assert rwt.grouped(deltas, 2, 4) == [(6.0, 3), (9.0, 2)]
    assert rwt.grouped(deltas, 4, 4) == [(3.0, 2), (3.0, 1), (4.0, 1), (5.0, 1)]


def test_cluster_interval_exclut_zero_si_tout_gagne_et_le_contient_sinon() -> None:
    positive = [(0.01 + 0.001 * (i % 5), 1) for i in range(200)]
    _, low, high = rwt.cluster_interval(positive, 200, 1)
    assert 0 < low < 0.012 < high

    centred = [(0.01 * (-1) ** i, 1) for i in range(200)]
    se, low, high = rwt.cluster_interval(centred, 200, 1)
    assert low < 0 < high
    assert se == pytest.approx(0.01 / 200**0.5, rel=0.3)


def test_decile_gap_ne_fabrique_pas_d_ecart_sur_des_ex_aequo() -> None:
    """Toutes les images à 50 %, issues équilibrées : un tri par (p, issue) donnerait 50 pts."""
    points = [(0.5, i % 2, 1.0) for i in range(1000)]
    assert rwt.decile_gap(points, 1) < 0.15


def test_power_vaut_cinq_pour_cent_sans_gain_et_monte_avec_lui() -> None:
    assert rwt.power(0.0, 0.001) == pytest.approx(0.05)
    assert rwt.power(0.003, 0.001) > 0.9


def test_add_placebo_garde_la_loi_du_terme_et_coupe_son_lien() -> None:
    games = [Game(states=[{"t": 2.0}, {"t": 2.0}], win=1, covered=True) for _ in range(400)]
    name = rwt.add_placebo(games, "t", 1)
    assert {abs(s[name]) for g in games for s in g.states} == {2.0}
    assert all(g.states[0][name] == g.states[1][name] for g in games)
    assert abs(mean(g.states[0][name] for g in games)) < 0.4


def test_add_form_ne_lit_que_les_parties_anterieures(monkeypatch) -> None:
    """Dix joueurs, trois parties : la 3e voit l'impact des deux premières, jamais le sien."""
    teams = {p: (100 if p <= 5 else 200) for p in range(1, 11)}
    puuid_of = {p: f"p{p}" for p in teams}
    metas = [
        rwt.Meta(i, 100 + i, f"2026-10-0{i + 1} 12:00:00", "16.21", puuid_of, teams, True)
        for i in range(3)
    ]
    games = [Game(states=[{}], win=1, covered=False) for _ in metas]
    rows = [(m.game_id, m.creation, 420, b"") for m in metas]
    # Le joueur 1 marque 0,1 à chaque partie, sauf 0,9 à la dernière, qui ne doit pas compter.
    deltas = iter([0.1, 0.1, 0.9])

    monkeypatch.setattr(rwt, "unpack", lambda _raw: {"game": {}, "timeline": {}})
    monkeypatch.setattr(rwt, "participant_roles", lambda _game: {})
    monkeypatch.setattr(
        rwt,
        "impacts",
        lambda *_a: {"rows": [{"participant_id": 1, "delta_p": next(deltas)}]},
    )
    monkeypatch.setattr(rwt.cfg, "SCOUT_MIN_IMPACT_GAMES", 2)
    rwt.add_form(games, metas, rows, None, "f")

    assert games[0].states[0]["f"] == 0.0
    assert games[1].states[0]["f"] == 0.0  # une seule partie antérieure, sous le minimum
    # Joueur 1 à +10, les neuf autres à 0 : centre 1, bleu (9 - 4) / 5, rouge -5 / 5.
    assert games[2].states[0]["f"] == pytest.approx(2.0)
