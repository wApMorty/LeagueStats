"""Blindabilité : matrice des postes, tirages (`src/analysis/blindability.py`) et leur écran.

Comme dans `test_shrink.py`, les données sont fabriquées avec un signal connu : sur la base réelle, la
vraie valeur est justement ce qu'on cherche.
"""

import random
import sqlite3

import pytest

from src.analysis.blindability import compute_blindability
from src.analysis.shrink import noise_variance
from src.client.blindabilite import blindabilite_view
from src.config_client import client_config
from src.config_constants import analysis_config

GAMES = analysis_config.BLINDABILITY_MIN_GAMES


class _NoAssets:
    def champions(self):
        return []


def _champions():
    from src.client.draft_view import Champions

    return Champions(_NoAssets())


def _base(rows, synergies=()):
    """Base en mémoire : `rows` = (champion, ennemi, delta2, games, lane), noms entiers ou texte."""
    connection = sqlite3.connect(":memory:")
    connection.executescript("""
        CREATE TABLE champions (id INTEGER PRIMARY KEY, name TEXT);
        CREATE TABLE matchups (champion INT, enemy INT, winrate REAL, delta2 REAL, games INT, lane TEXT);
        CREATE TABLE synergies (champion INT, ally INT, winrate REAL, delta2 REAL, games INT, lane TEXT);
        """)
    ids = sorted({row[0] for row in rows} | {row[1] for row in rows})
    connection.executemany("INSERT INTO champions VALUES (?, ?)", [(i, f"C{i}") for i in ids])
    connection.executemany(
        "INSERT INTO matchups VALUES (?, ?, 50.0, ?, ?, ?)", [tuple(row) for row in rows]
    )
    connection.executemany(
        "INSERT INTO synergies VALUES (?, ?, 50.0, ?, ?, ?)", [tuple(row) for row in synergies]
    )
    return connection


def _noisy(rng, signal, games):
    return rng.gauss(0, signal) + rng.gauss(0, noise_variance(50.0, games) ** 0.5)


def test_matrice_retrouve_un_signal_connu_et_ignore_le_bruit():
    """Top contre top : 2 pp de signal. Top contre support : rien, malgré le même bruit."""
    rng = random.Random(0)
    tops, supports = range(1, 41), range(101, 141)
    games = 3000
    rows = []
    for top in tops:
        rows += [(top, other, _noisy(rng, 2.0, games), games, "top") for other in tops]
        rows += [(top, other, _noisy(rng, 0.0, games), games, "top") for other in supports]
    # Les supports ne sont jamais sur la lane top : poste principal sans ambiguïté.
    rows += [(support, 1, 0.0, GAMES, "support") for support in supports]

    matrix = compute_blindability(_base(rows))["matchups"]["top"]

    assert matrix["top"] == pytest.approx(2.0, abs=0.3)
    assert matrix["support"] < 0.4


def test_champion_partage_entre_deux_postes_et_champion_peu_joue_sont_ecartes():
    rows = [
        (1, 3, 1.0, GAMES, "top"),
        (1, 2, 5.0, 100, "top"),  # 2 joue trois postes : sans poste principal, ligne ignorée
        (3, 1, 5.0, GAMES - 1000, "top"),  # 3 reste un adversaire, mais sans ligne à lui
        (2, 1, 0.0, GAMES, "top"),
        (2, 1, 0.0, GAMES, "middle"),
        (2, 1, 0.0, GAMES, "jungle"),
    ]

    draws = compute_blindability(_base(rows))["draws"]["top"]

    assert draws["C1"] == 0.0  # un seul adversaire compté : tirage égal à la méta
    assert "C3" not in draws


def test_synergies_sans_diagonale():
    rows = [(1, 2, 0.0, GAMES, "top"), (2, 1, 0.0, GAMES, "support")]
    synergies = [(1, 3, 1.0, 500, "top"), (1, 2, 1.0, 500, "top")]
    rows.append((3, 1, 0.0, GAMES, "top"))

    matrix = compute_blindability(_base(rows, synergies))["synergies"]["top"]

    assert list(matrix) == ["support"]


def test_tirage_positif_pour_un_contre_pick_negatif_pour_un_contre_pique():
    """Deux adversaires à parts égales dans la méta. 1 rencontre surtout celui qu'il bat, 2 l'inverse."""
    rows = [
        (3, 1, 0.0, GAMES, "top"),
        (4, 1, 0.0, GAMES, "top"),
        (1, 3, 4.0, 3000, "top"),  # 1 bat 3 et le rencontre 3 fois sur 4
        (1, 4, -4.0, 1000, "top"),
        (2, 3, 4.0, 1000, "top"),  # 2 bat 3 mais rencontre surtout 4, qui le bat
        (2, 4, -4.0, 3000, "top"),
    ]
    rows = [(c, e, d, GAMES if c in (1, 2) and g == 3000 else g, lane) for c, e, d, g, lane in rows]

    draws = compute_blindability(_base(rows))["draws"]["top"]

    assert draws["C1"] > 0 > draws["C2"]


def test_base_sans_paires():
    assert compute_blindability(_base([])) == {"matchups": {}, "synergies": {}, "draws": {}}


def test_vue_lignes_centrees_sur_zero_et_cases_absentes():
    data = {"matchups": {"top": {"top": 3.0, "jungle": 1.0}}, "synergies": {}, "draws": {}}

    view = blindabilite_view(data, _champions(), None)

    first = view["matchups"]["rows"][0]["cells"]
    assert [cell and cell["text"] for cell in first] == ["+50 %", "−50 %", None, None, None]
    assert first[0]["tone"] == "up" and first[1]["tone"] == "down"
    assert view["synergies"] is None
    assert not view["empty"]


def test_vue_ligne_sans_signal_ne_divise_pas_par_zero():
    data = {"matchups": {"top": {"top": 0.0, "jungle": 0.0}}}

    cells = blindabilite_view(data, _champions(), None)["matchups"]["rows"][0]["cells"]

    assert cells[0]["text"] == "—"


def test_vue_histogramme_range_chaque_champion_dans_sa_colonne():
    step = client_config.BLINDABILITE_BIN_PP
    data = {"matchups": {"top": {"top": 1.0}}, "draws": {"middle": {"Yasuo": -2 * step, "Ahri": 0}}}

    columns = blindabilite_view(data, _champions(), "inconnu")["histogram"]

    assert len(columns) == 5  # symétrique : −2 à +2 colonnes
    assert [c["name"] for c in columns[0]["champions"]] == ["Yasuo"]
    assert [c["name"] for c in columns[2]["champions"]] == ["Ahri"]
    assert columns[0]["tone"] == "down" and columns[4]["tone"] == "up"


def test_vue_vide_sans_donnees():
    view = blindabilite_view({}, _champions(), "top")

    assert view["empty"]
    assert next(lane for lane in view["lanes"] if lane["on"])["key"] == "top"
