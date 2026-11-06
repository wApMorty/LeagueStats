"""Régression client : une base corrompue fait tomber les écrans Pool et Suggestions en erreur 500.

Symptôme (spec-verifier, SPEC-50, 2026-11-06) : avec un `db.db` présent mais illisible (« file is not
a database »), l'écran Suggestions renvoie une 500 au lieu du message « Base de données indisponible ».
SPEC-50 y appelle `champion_names` à chaque rendu (liste du champ « Exclure ») ; l'écran Pool l'appelait
déjà.

Cause racine : `champion_names` (`src/client/pools.py`) ne rattrapait que `sqlite3.OperationalError`.
Une base corrompue lève `sqlite3.DatabaseError`, sa classe mère, qui remontait jusqu'à la route.

Correctif : `champion_names` rattrape `sqlite3.Error` et rend une liste vide, comme pour une base absente.

Prévention : ces tests ouvrent les deux écrans sur un vrai fichier corrompu, sans jamais toucher
`data/db.db`.
"""

import pytest
from fastapi.testclient import TestClient

from src import pool_manager, user_prefs
from src.client.app import create_app
from src.client.pools import champion_names
from tests.support_lcu_nav import make_assets

LOCAL = "http://127.0.0.1"


@pytest.fixture
def corrupt_db(tmp_path):
    """Un fichier présent mais qui n'est pas une base SQLite."""
    path = tmp_path / "db.db"
    path.write_bytes(b"ceci n'est pas une base SQLite" * 100)
    return path


@pytest.fixture
def web(corrupt_db, tmp_path, monkeypatch):
    """Client de test sur la base corrompue ; pools et préférences sous tmp_path."""
    monkeypatch.setattr(pool_manager, "get_user_data_path", lambda f: str(tmp_path / f))
    monkeypatch.setattr(user_prefs, "get_user_data_path", lambda f: str(tmp_path / f))
    app = create_app(corrupt_db, assets=make_assets(tmp_path))
    return TestClient(app, base_url=LOCAL, raise_server_exceptions=False)


def test_champion_names_d_une_base_corrompue_est_vide(corrupt_db):
    assert champion_names(corrupt_db) == []


@pytest.mark.parametrize("path", ["/pool", "/pool/suggestions"])
def test_les_ecrans_de_pool_s_ouvrent_sur_une_base_corrompue(web, path):
    response = web.get(path)

    assert response.status_code == 200
