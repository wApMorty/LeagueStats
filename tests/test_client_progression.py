"""Écran Progression du client (SPEC-21 tâche 52) : grille, verdicts, seuils d'échantillon, route."""

import pytest
from fastapi.testclient import TestClient

from src.client.app import create_app
from src.client.data import default_role, progression_view, rolling
from src.coaching.grid import GRID
from src.config_constants import coaching_config
from src.repositories.coaching import CoachingRepository

LOCAL = "http://127.0.0.1"
NORM_N = coaching_config.MIN_NORM_SAMPLE


def rows(metric, values, z=0.0, norm_mean=1.0, norm_n=NORM_N, objective=None, z_objective=None):
    """Historique du joueur pour une métrique, de la plus récente à la plus ancienne."""
    return [
        {
            "game_id": i,
            "created": "2026-10-01 00:00:00",
            "role": "top",
            "champion_id": 2,
            "metric": metric,
            "value": value,
            "norm_mean": norm_mean,
            "norm_n": norm_n,
            "z_norm": z,
            "objective_value": objective,
            "z_objective": z_objective,
        }
        for i, value in enumerate(values)
    ]


def row_of(view, metric):
    return next(r for r in view["rows"] if r["metric"] == metric)


def client(temp_db):
    return TestClient(create_app(temp_db), base_url=LOCAL, raise_server_exceptions=False)


def store(db, role, metric, values, z=-0.5, objective=None, z_objective=None, first_game=1):
    """Parties analysées du joueur (la dernière valeur est la plus récente), comme le moteur de constats."""
    repo = CoachingRepository(db)
    metric_rows = []
    for index, value in enumerate(values, first_game):
        db.insert_game_record(
            game_id=index,
            queue_id=420,
            game_creation_utc=f"2026-09-01 00:{index // 60:02d}:{index % 60:02d}",
            duration_s=1800,
            player_participant_id=1,
            raw_game="{}",
            raw_timeline=None,
            raw_eog=None,
        )
        metric_rows.append(
            (index, 1, metric, 1, role, 2, value, 1.0, 0.5, NORM_N, z)
            + (objective, None, None, z_objective, coaching_config.GRID_VERSION)
        )
    repo.insert_metrics(metric_rows)


# ---------- données ----------


def test_poste_par_defaut():
    assert default_role({"jungle": 4, "top": 31}) == "top"
    assert default_role({"jungle": 4, "support": 9}) == "support"
    assert default_role({"jungle": 3, "top": 3}) == "top"  # égalité : l'ordre des postes
    assert default_role({}) == "top"
    assert default_role({"ancien_poste": 99}) == "top"


def test_poste_inconnu_ou_absent_retombe_sur_le_plus_joue():
    for asked in (None, "", "<script>", "toplane"):
        assert progression_view({"jungle": 9}, [], asked)["role"] == "jungle"
    assert progression_view({"jungle": 9, "top": 2}, [], "top")["role"] == "top"


def test_puces_de_poste_avec_leur_nombre_de_parties():
    chips = progression_view({"top": 31, "jungle": 4}, [], "top")["chips"]
    assert [(c["key"], c["n"], c["on"]) for c in chips] == [
        ("top", 31, True),
        ("jungle", 4, False),
        ("middle", 0, False),
        ("bottom", 0, False),
        ("support", 0, False),
    ]


def test_sans_partie_pas_de_grille():
    view = progression_view({}, [], None)
    assert view["empty"] and view["rows"] == []
    assert view["patterns"][0]["tone"] == "muted"


def test_la_grille_suit_les_metriques_du_poste_et_leur_poids():
    history = rows("deaths_per_10", [2.0] * 3) + rows("cs_10", [70.0] * 3)
    view = progression_view({"top": 3}, history, "top")
    assert [r["metric"] for r in view["rows"]] == list(GRID["top"])
    assert row_of(view, "deaths_per_10")["weight"] == "●●"
    assert row_of(view, "cs_10")["weight"] == "●"


def test_valeurs_toi_norme_et_objectif_formatees():
    history = (
        rows("cs_10", [70, 72, 74], norm_mean=71.0, objective=78.0)
        + rows("gold_diff_15", [100, 0], norm_mean=0.0)
        + rows("solo_deaths", [1, 2], norm_n=NORM_N - 1)
    )
    view = progression_view({"top": 3}, history, "top")
    cs = row_of(view, "cs_10")
    assert (cs["you"], cs["norm"], cs["objective"]) == ("72", "71", "78")
    gold = row_of(view, "gold_diff_15")
    assert gold["norm"] == "0"  # un écart face à l'adversaire de lane a 0 pour norme
    assert gold["objective"] == "—"
    deaths = row_of(view, "solo_deaths")
    assert deaths["norm"] == "—"  # norme en construction : pas affichée
    assert row_of(view, "damage_per_min")["you"] == "—"  # métrique jamais calculée


def test_verdict_de_progres_et_de_recul_selon_le_sens_de_la_metrique():
    # Du plus récent au plus ancien : 12 parties, les 6 récentes meilleures sur les morts (sens −1)
    better = rows("deaths_per_10", [1.0, 1.2, 0.8, 1.0, 1.1, 0.9] + [3.0, 3.2, 2.8, 3.0, 3.1, 2.9])
    worse = rows("cs_10", [50, 52, 48, 50, 51, 49] + [70, 72, 68, 70, 71, 69])
    view = progression_view({"top": 12}, better + worse, "top")
    assert row_of(view, "deaths_per_10")["verdict"] == {"kind": "up", "text": "en progrès"}
    assert row_of(view, "cs_10")["verdict"] == {"kind": "down", "text": "en recul"}


def test_valeurs_stables_verdict_stable():
    flat = rows("cs_10", [70, 71, 69, 70, 72, 68] + [70, 69, 71, 70, 68, 72])
    verdict = row_of(progression_view({"top": 12}, flat, "top"), "cs_10")["verdict"]
    assert verdict == {"kind": "flat", "text": "stable"}


@pytest.mark.parametrize(
    "games, text",
    [(3, "3/5 parties, pas de verdict"), (6, "6/10 parties, pas de verdict")],
)
def test_sous_les_seuils_pas_de_verdict_et_l_echantillon_est_dit(games, text):
    history = rows("cs_10", [70, 71, 69, 70, 72, 68][:games])
    verdict = row_of(progression_view({"top": games}, history, "top"), "cs_10")["verdict"]
    assert verdict == {"kind": "none", "text": text}


def test_tendance_en_moyenne_glissante_avec_la_ligne_d_objectif_en_pointille():
    history = rows("cs_10", [70] * 8, z=0.5, objective=75.0, z_objective=-0.2)
    spark = str(row_of(progression_view({"top": 8}, history, "top"), "cs_10")["spark"])
    assert spark.count("<path") == 2 and "stroke-dasharray:4 4" in spark
    only_norm = rows("cs_10", [70] * 8, z=0.5)
    assert (
        str(row_of(progression_view({"top": 8}, only_norm, "top"), "cs_10")["spark"]).count("<path")
        == 1
    )


def test_norme_en_construction_pas_de_tendance_face_a_la_norme():
    history = rows("cs_10", [70] * 8, z=0.5, norm_n=NORM_N - 1)
    spark = str(row_of(progression_view({"top": 8}, history, "top"), "cs_10")["spark"])
    assert "<path" not in spark  # seule la ligne de base : un z sans norme fiable ne se trace pas


def test_moyenne_glissante():
    assert rolling([1, 2, 3, 4], 2) == [1, 1.5, 2.5, 3.5]
    assert rolling([], 3) == []


def test_schemas_de_patterns():
    weak = rows("deaths_before_14", [2] * 10, z=-1.5)
    view = progression_view({"top": 10}, weak, "top")
    assert view["patterns"] == [
        {
            "text": "Faiblesse : Morts avant 14 min, sous la norme dans 10 parties sur 10.",
            "tone": "bad",
        }
    ]
    strong = rows("cs_10", [80] * 10, z=1.5)
    text = progression_view({"top": 10}, strong, "top")["patterns"][0]
    assert text["tone"] == "good" and text["text"].startswith(
        "Force : CS @10, au-dessus de la norme"
    )


def test_sans_schema_le_message_dit_pourquoi():
    few = progression_view({"top": 3}, rows("cs_10", [70] * 3), "top")
    assert few["patterns"][0]["text"] == "Pas assez de parties en Top pour dégager un schéma."
    many = progression_view({"top": 10}, rows("cs_10", [70] * 10), "top")
    assert many["patterns"][0]["text"].startswith("Aucun schéma significatif")


def test_note_d_echantillon():
    assert (
        "verdict à partir de 10 parties" in progression_view({"top": 8}, [], "top")["sample_note"]
    )
    assert progression_view({"top": 3}, [], "top")["sample_note"].startswith("Sous 5 parties")


# ---------- route ----------


def test_route_sur_base_vide_repond_200(temp_db):
    response = client(temp_db).get("/progression")
    assert response.status_code == 200
    assert "Aucune partie analysée en Top" in response.text
    assert response.text.count('class="role-chip"') == 5


def test_route_affiche_la_grille_du_poste_demande(db, temp_db):
    store(db, "top", "cs_10", [70, 71, 72], first_game=1)
    store(db, "support", "vision_per_min", [1.5, 1.6, 1.7], first_game=10)
    page = client(temp_db).get("/progression?role=support").text
    assert "Vision / min" in page and "Dégâts / min" not in page
    assert page.count('aria-current="true"') == 1
    top = client(temp_db).get("/progression?role=top").text
    assert "Dégâts / min" in top and "Vision / min" not in top
    assert "3/5 parties, pas de verdict" in top


def test_route_poste_par_defaut_et_valeur_hostile(db, temp_db):
    store(db, "jungle", "cs_per_min", [6.0, 6.1], first_game=1)
    hostile = client(temp_db).get("/progression", params={"role": "<script>alert(1)</script>"})
    assert hostile.status_code == 200
    assert "<script>alert" not in hostile.text
    assert "Participation aux kills" in hostile.text  # le poste le plus joué (jungle)


def test_les_puces_ne_declenchent_pas_la_transition_de_page(temp_db):
    page = client(temp_db).get("/progression").text
    assert 'hx-target="#prog" hx-select="#prog"' in page and 'hx-push-url="true"' in page


def test_la_consultation_n_ecrit_pas_dans_la_base(db, temp_db):
    store(db, "top", "cs_10", [70, 71, 72])
    before = (temp_db.stat().st_mtime_ns, temp_db.read_bytes())
    assert client(temp_db).get("/progression?role=top").status_code == 200
    assert (temp_db.stat().st_mtime_ns, temp_db.read_bytes()) == before
