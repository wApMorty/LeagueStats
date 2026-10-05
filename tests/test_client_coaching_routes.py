"""Section Coaching du client, critères 2 et 8 de SPEC-21 : toutes ses routes répondent 200 sur une base
vide ou non migrée (message d'état vide, jamais une 500), sans client LoL, et la consultation n'écrit pas.
"""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from src.client.app import create_app
from src.client.assets import Assets
from tests.test_client_parties import capture, impact
from tests.test_client_postgame import modele  # noqa: F401 - fixture
from tests.test_client_progression import store

LOCAL = "http://127.0.0.1"
ROUTES = [
    "/",
    "/rang",
    "/progression",
    "/progression?role=support",
    "/parties",
    "/calibration",
    "/postgame",
    "/accueil/axes",
]


def client(path, tmp_path):
    assets = Assets(tmp_path / "cache", fetch=lambda url: None)
    return TestClient(
        create_app(path, assets=assets), base_url=LOCAL, raise_server_exceptions=False
    )


@pytest.mark.parametrize("route", ROUTES)
def test_base_vide_200_sans_client_lol(route, temp_db, tmp_path):
    response = client(temp_db, tmp_path).get(route)  # aucun LCU : `lcu=None`
    assert response.status_code == 200
    assert (
        "Traceback" not in response.text
        and "Erreur" not in response.text.split("<main", 1)[-1][:400]
    )


@pytest.mark.parametrize("route", ROUTES)
def test_base_non_migree_200(route, tmp_path):
    path = tmp_path / "vide.db"
    sqlite3.connect(path).close()
    assert client(path, tmp_path).get(route).status_code == 200


@pytest.mark.parametrize("route", ROUTES)
def test_base_remplie_200_et_lecture_seule(route, db, temp_db, tmp_path, modele):  # noqa: F811
    store(db, "top", "cs_10", [70.0] * 12, z=-1.5)
    capture(db, game_id=100, pid=1)
    impact(db, game_id=100)
    before = (temp_db.stat().st_mtime_ns, temp_db.read_bytes())
    assert client(temp_db, tmp_path).get(route).status_code == 200
    assert (temp_db.stat().st_mtime_ns, temp_db.read_bytes()) == before
