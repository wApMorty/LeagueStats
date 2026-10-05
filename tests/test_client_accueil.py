"""Accueil du coaching du client (SPEC-21 tâche 71) : axes, constats, colonne latérale, et les deux
écritures dans la base (fixer, clore un axe) derrière le jeton de session."""

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from jinja2 import Environment, FileSystemLoader, select_autoescape

from src.client.app import create_app
from src.client.assets import Assets
from src.client.draft_view import Champions
from src.client.home import axes_view, home_view
from src.config_client import client_config
from src.config_constants import coaching_config
from src.repositories.coaching import CoachingRepository
from tests.test_client_parties import capture
from tests.test_client_progression import NORM_N, store

LOCAL = "http://127.0.0.1"
NOW = datetime(2026, 10, 5, 18, 0, tzinfo=timezone.utc)
TEMPLATES = Path(__file__).parent.parent / "src" / "client" / "templates"


@pytest.fixture
def assets(tmp_path):
    return Assets(tmp_path / "cache", fetch=lambda url: None)


def client(temp_db, assets):
    return TestClient(
        create_app(temp_db, assets=assets), base_url=LOCAL, raise_server_exceptions=False
    )


def token(web):
    return {client_config.TOKEN_HEADER: web.app.state.session_token}


def goals_in(temp_db):
    with sqlite3.connect(temp_db) as connection:
        return connection.execute(
            "SELECT metric, role, origin, status FROM coaching_goals ORDER BY id"
        ).fetchall()


def weak_history(db, games=10):
    """Dix parties en Top où les morts avant 14 min sont un schéma négatif net."""
    store(db, "top", "deaths_before_14", [2.0] * games, z=-1.5)


# ---------- page ----------


def test_accueil_sur_base_vide(temp_db, assets):
    response = client(temp_db, assets).get("/")
    page = response.text
    assert response.status_code == 200
    assert "Aucune partie capturée" in page and "Aucune partie analysée : un axe se fixe" in page
    assert "Pas encore de constat" in page and "0 axe actif sur 2" in page
    assert page.count("Place libre") == 2


def test_accueil_sur_base_non_migree(tmp_path, assets):
    path = tmp_path / "vide.db"
    sqlite3.connect(path).close()
    response = client(path, assets).get("/")
    assert response.status_code == 200 and "Base non migrée" in response.text


def test_la_proposition_du_coach_est_affichee_sans_rien_ecrire(db, temp_db, assets):
    weak_history(db)
    page = client(temp_db, assets).get("/").text
    assert "Le coach propose « Morts avant 14 min »" in page
    assert "Fixer cet axe" in page and "Choisir une autre métrique" in page
    assert "rôle principal Top" in page
    assert goals_in(temp_db) == []  # proposer n'écrit pas : seul le clic le fait


def test_sans_schema_negatif_pas_de_proposition_et_le_choix_reste(db, temp_db, assets):
    store(db, "top", "cs_10", [70.0] * 3, z=0.0)
    page = client(temp_db, assets).get("/").text
    assert "Pas de proposition pour l'instant" in page and "Fixer cet axe" not in page
    assert "Choisir une autre métrique" in page


def test_les_axes_actifs_et_leurs_verdicts(db, temp_db, assets):
    weak_history(db)
    repo = CoachingRepository(db)
    repo.insert_goal("deaths_before_14", "top", 1.0, "proposed")
    repo.insert_goal("cs_10", "top", 70.0, "player")
    for game_id, held in zip(range(4, 11), (1, 0, 1, 1, 0, 1, 1)):
        repo.insert_verdict(1, game_id, 1.0, bool(held))
    view = axes_view(repo)
    first, second = view["cards"]
    assert (
        first["tag"] == "Axe 1 · proposé par le coach" and second["tag"] == "Axe 2 · fixé par toi"
    )
    assert first["label"] == "Morts avant 14 min" and first["target"] == "≤ 1"
    assert second["target"] == "≥ 70"
    # cinq derniers verdicts (ceux des parties 6 à 10), du plus ancien au plus récent
    assert first["marks"] == [True, True, False, True, True]
    assert first["hold"] == "Tenu 4 fois sur les 5 dernières · acquis à 4 sur 5"
    assert first["since"] == "Actif depuis 7 parties"
    assert second["marks"] == [None] * 5 and second["since"] == "Fixé, pas encore jugé"
    assert view["note"] == "2 axes actifs sur 2 · clos-en un pour en fixer un autre"
    assert view["options"] == [
        {"metric": m, "label": label}
        for m, label in [
            ("gold_diff_15", "Écart d'or @15"),
            ("xp_diff_15", "Écart d'XP @15"),
            ("solo_deaths", "Morts en solo"),
            ("deaths_per_10", "Morts / 10 min"),
            ("damage_per_min", "Dégâts / min"),
            ("structure_damage_per_min", "Dégâts aux structures / min"),
        ]
    ]


def test_une_place_libre_apres_un_axe_et_ses_pastilles(db, temp_db, assets):
    weak_history(db)
    CoachingRepository(db).insert_goal("cs_10", "top", 70.0, "player")
    page = client(temp_db, assets).get("/").text
    assert page.count("goal-card goal-free") == 1 and "1 axe actif sur 2" in page
    assert page.count('class="goal-mark todo"') == 5 and "pas encore jugé" in page


def test_derniers_constats_avec_barre_divergente(db, temp_db, assets):
    capture(db, game_id=1, pid=1)
    repo = CoachingRepository(db)
    repo.insert_metrics(
        [
            (1, 1, "cs_10", 1, "top", 2, 74.0, 71.0, 6.0, NORM_N, 0.5)
            + (78.0, 5.0, "OneTricks", 0.3, coaching_config.GRID_VERSION),
            (1, 1, "solo_deaths", 1, "top", 2, 3.0, 1.6, 0.8, NORM_N, -1.75)
            + (None, None, None, None, coaching_config.GRID_VERSION),
        ]
    )
    repo.insert_findings(
        [(1, "cs_10", "positive", 1.8, "norm", 1), (1, "solo_deaths", "negative", -1.2, "norm", 1)]
    )
    view = home_view(repo, Champions(assets), NOW)
    rows = view["findings"]["rows"]
    # négatifs d'abord, puis positifs
    assert [r["label"] for r in rows] == ["Morts en solo", "CS @10"]
    solo, cs = rows
    assert (cs["value"], cs["reference"], cs["z"]) == ("74", "71 · obj. 78", "+1,8 σ")
    assert (cs["left"], cs["width"], cs["good"]) == (50.0, round(1.8 / 2.27 * 50, 1), True)
    assert (solo["value"], solo["reference"], solo["z"]) == ("3", "2", "−1,2 σ")
    assert solo["good"] is False and solo["left"] == round(50 - 1.2 / 2.27 * 50, 1)
    assert view["findings"]["win"] is True and view["findings"]["href"] == "/parties/1"


def test_un_brut_illisible_ne_fait_pas_tomber_l_accueil(db, temp_db, assets):
    capture(db, game_id=1, pid=1, raw="{}")
    repo = CoachingRepository(db)
    repo.insert_metrics(
        [
            (1, 1, "cs_10", 1, "top", 2, 74.0, 71.0, 6.0, NORM_N, 0.5)
            + (None, None, None, None, coaching_config.GRID_VERSION)
        ]
    )
    repo.insert_findings([(1, "cs_10", "positive", 1.8, "norm", 1)])
    response = client(temp_db, assets).get("/")
    assert response.status_code == 200 and "Pas encore de constat" in response.text


def test_une_norme_en_construction_n_est_pas_affichee(db, assets):
    capture(db, game_id=1, pid=1)
    repo = CoachingRepository(db)
    repo.insert_metrics(
        [
            (1, 1, "cs_10", 1, "top", 2, 74.0, 71.0, 6.0, NORM_N - 1, 0.5)
            + (None, None, None, None, coaching_config.GRID_VERSION)
        ]
    )
    repo.insert_findings([(1, "cs_10", "positive", 1.8, "objective", 1)])
    row = home_view(repo, Champions(assets), NOW)["findings"]["rows"][0]
    assert row["reference"] == "—"


def test_colonne_laterale_rang_parties_et_bilan(db, temp_db, assets):
    store(db, "top", "cs_10", [70.0, 72.0, 71.0, 73.0, 74.0, 75.0], z=0.8)
    store(db, "top", "solo_deaths", [2.0] * 6, z=-0.9)
    capture(db, game_id=100, pid=1, created="2026-10-05 10:00:00")
    capture(db, game_id=101, pid=6, created="2026-10-05 12:00:00")
    for i, lp in enumerate((10, 40, 70)):
        db.connection.execute(
            "INSERT INTO rank_snapshots (captured_utc, queue, tier, division, lp, wins, losses) "
            "VALUES (?, 'RANKED_SOLO_5x5', 'EMERALD', 'II', ?, 5, 4)",
            (f"2026-10-0{i + 1} 12:00:00", lp),
        )
    db.connection.commit()
    view = home_view(CoachingRepository(db), Champions(assets), NOW)
    assert view["rank"]["tier"] == "Émeraude II" and view["rank"]["lp"] == 70
    assert view["rank"]["spark"] and "Voir le rang" in client(temp_db, assets).get("/").text
    games = view["last"]["games"]
    assert [g["win"] for g in games] == [False, True]  # la plus récente d'abord
    assert view["last"]["title"] == "2 dernières parties · 1 V · 1 D"
    assert view["review"]["label"] == "Top" and view["review"]["known"]
    assert [r["label"] for r in view["review"]["strong"]] == ["CS @10"]
    assert [r["label"] for r in view["review"]["weak"]] == ["Morts en solo"]
    assert view["review"]["strong"][0]["z"] == "+0,8 σ"


def test_etat_de_la_base_frais_ou_vide(db, assets):
    repo = CoachingRepository(db)
    assert home_view(repo, Champions(assets), NOW)["status"] == "Aucune partie capturée"
    capture(db, game_id=1, pid=1)
    status = home_view(repo, Champions(assets), datetime.now(timezone.utc))["status"]
    assert status == "1 partie capturée · dernière à l'instant"


def test_la_consultation_n_ecrit_pas_dans_la_base(db, temp_db, assets):
    weak_history(db)
    capture(db, game_id=1, pid=1)
    before = (temp_db.stat().st_mtime_ns, temp_db.read_bytes())
    web = client(temp_db, assets)
    assert web.get("/").status_code == 200 and web.get("/accueil/axes").status_code == 200
    assert (temp_db.stat().st_mtime_ns, temp_db.read_bytes()) == before


# ---------- écritures ----------


def test_fixer_un_axe_ecrit_en_base_et_renvoie_les_places(db, temp_db, assets):
    weak_history(db)
    web = client(temp_db, assets)
    response = web.post(
        "/accueil/axe?metric=deaths_before_14&role=top&origin=proposed", headers=token(web)
    )
    assert response.status_code == 200
    assert goals_in(temp_db) == [("deaths_before_14", "top", "proposed", "active")]
    assert 'id="axes"' in response.text and "Axe 1 · proposé par le coach" in response.text
    assert "Nouvel axe de travail" in response.text  # le message de l'écriture
    target = CoachingRepository(db).goals()[0]["target"]
    assert target == pytest.approx(1.0)  # la norme du moment (norm_mean des parties)


def test_fixer_sans_jeton_ou_avec_une_origine_etrangere_est_refuse(db, temp_db, assets):
    weak_history(db)
    web = client(temp_db, assets)
    path = "/accueil/axe?metric=deaths_before_14&role=top"
    assert web.post(path).status_code == 403
    assert web.post(path, headers={client_config.TOKEN_HEADER: "faux"}).status_code == 403
    assert (
        web.post(path, headers={**token(web), "Origin": "http://evil.example"}).status_code == 403
    )
    assert goals_in(temp_db) == []


@pytest.mark.parametrize(
    "query",
    [
        "metric=nimporte&role=top",
        "metric=vision_per_min&role=top",  # une métrique d'un autre poste
        "metric=cs_10&role=toplane",
        "metric=cs_10&role=top&origin=hacker",
        "metric=%27%3B+DROP+TABLE+coaching_goals%3B--&role=top",
    ],
)
def test_un_axe_invalide_est_refuse_sans_ecriture(db, temp_db, assets, query):
    web = client(temp_db, assets)
    assert web.post(f"/accueil/axe?{query}", headers=token(web)).status_code == 400
    assert goals_in(temp_db) == []


def test_fixer_deux_fois_le_meme_axe_ne_le_double_pas(db, temp_db, assets):
    weak_history(db)
    web = client(temp_db, assets)
    web.post("/accueil/axe?metric=deaths_before_14&role=top", headers=token(web))
    again = web.post("/accueil/axe?metric=deaths_before_14&role=top", headers=token(web))
    assert "est déjà un axe actif" in again.text
    assert len(goals_in(temp_db)) == 1


def test_un_troisieme_axe_deplace_le_plus_ancien(db, temp_db, assets):
    store(db, "top", "cs_10", [70.0] * 3)
    store(db, "top", "solo_deaths", [2.0] * 3)
    store(db, "top", "deaths_per_10", [3.0] * 3)
    web = client(temp_db, assets)
    for metric in ("cs_10", "solo_deaths", "deaths_per_10"):
        web.post(f"/accueil/axe?metric={metric}&role=top", headers=token(web))
    assert [(m, status) for m, _, _, status in goals_in(temp_db)] == [
        ("cs_10", "dropped"),
        ("solo_deaths", "active"),
        ("deaths_per_10", "active"),
    ]


def test_fixer_sans_partie_analysee_le_dit(db, temp_db, assets):
    web = client(temp_db, assets)
    response = web.post("/accueil/axe?metric=cs_10&role=top", headers=token(web))
    assert response.status_code == 200 and "Aucune partie analysée en top" in response.text
    assert goals_in(temp_db) == []


def test_clore_un_axe(db, temp_db, assets):
    CoachingRepository(db).insert_goal("cs_10", "top", 70.0, "player")
    web = client(temp_db, assets)
    response = web.post("/accueil/axe/1/clore", headers=token(web))
    assert response.status_code == 200 and "Axe clos" in response.text
    assert goals_in(temp_db) == [("cs_10", "top", "player", "dropped")]
    assert response.text.count("goal-card goal-free") == 2  # les deux places sont libres


def test_clore_sans_jeton_un_axe_inconnu_ou_deja_clos(db, temp_db, assets):
    CoachingRepository(db).insert_goal("cs_10", "top", 70.0, "player")
    web = client(temp_db, assets)
    assert web.post("/accueil/axe/1/clore").status_code == 403
    assert goals_in(temp_db)[0][3] == "active"
    assert web.post("/accueil/axe/99/clore", headers=token(web)).status_code == 404
    assert web.post("/accueil/axe/1/clore", headers=token(web)).status_code == 200
    assert web.post("/accueil/axe/1/clore", headers=token(web)).status_code == 404  # déjà clos


def test_une_ecriture_ne_cree_pas_de_base(tmp_path, assets):
    """`writable()` ouvre en `mode=rw` : une base absente n'est jamais créée par un clic."""
    missing = tmp_path / "absente.db"
    web = client(missing, assets)
    assert web.post("/accueil/axe/1/clore", headers=token(web)).status_code == 500
    assert not missing.exists()


def test_le_message_de_l_ecriture_est_echappe():
    environment = Environment(
        loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html"])
    )
    axes = {
        "cards": [],
        "options": [],
        "note": "",
        "notice": "<script>alert(1)</script>",
        "role": None,
        "role_label": None,
        "minimum": 5,
    }
    html = environment.get_template("partials/accueil_axes.html").render(a=axes)
    assert "<script>" not in html and "&lt;script&gt;" in html
