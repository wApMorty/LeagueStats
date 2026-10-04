"""Socle du client LeagueStats (SPEC-21 tâche 49) : base en lecture seule, garde, serveur."""

import socket
import sqlite3

import httpx
import pytest
from fastapi.testclient import TestClient

from src.client import server
from src.client.app import create_app
from src.client.db import read_only
from src.config_client import client_config
from src.repositories.coaching import CoachingRepository

LOCAL = "http://127.0.0.1"


@pytest.fixture
def app(temp_db):
    app = create_app(temp_db, bus="bus", lcu="lcu")

    @app.post("/_ecrit")
    def ecrit() -> dict:
        return {"ecrit": True}

    @app.delete("/_efface")
    def efface() -> dict:
        return {}

    @app.get("/events")
    def events() -> dict:
        return {"flux": True}

    return app


@pytest.fixture
def web(app):
    return TestClient(app, base_url=LOCAL)


def token_header(app) -> dict:
    return {client_config.TOKEN_HEADER: app.state.session_token}


# ---------- base en lecture seule ----------


def test_read_only_lit_via_les_repositories(temp_db):
    with read_only(temp_db) as handle:
        assert CoachingRepository(handle).unanalyzed_games() == []


def test_read_only_refuse_toute_ecriture(temp_db):
    with read_only(temp_db) as handle:
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            handle.connection.execute("INSERT INTO champions (name) VALUES ('Ahri')")
    with sqlite3.connect(temp_db) as check:
        assert check.execute("SELECT COUNT(*) FROM champions").fetchone() == (0,)


def test_read_only_ne_cree_pas_une_base_absente(tmp_path):
    missing = tmp_path / "absente.db"
    with pytest.raises(sqlite3.OperationalError):
        with read_only(missing):
            pass
    assert not missing.exists()


def test_read_only_ne_touche_pas_au_fichier(temp_db, capsys):
    before = (temp_db.stat().st_mtime_ns, temp_db.read_bytes())
    with read_only(temp_db) as handle:
        handle.connection.execute("SELECT COUNT(*) FROM game_records").fetchone()
    assert (temp_db.stat().st_mtime_ns, temp_db.read_bytes()) == before
    assert capsys.readouterr().out == ""  # `Database.connect()` imprimerait


def test_read_only_accepte_un_chemin_avec_espaces(tmp_path, temp_db):
    spaced = tmp_path / "Code Workspace" / "base de test.db"
    spaced.parent.mkdir()
    spaced.write_bytes(temp_db.read_bytes())
    with read_only(spaced) as handle:
        assert handle.connection.execute("SELECT COUNT(*) FROM champions").fetchone() == (0,)


# ---------- garde : Host, Origin, jeton ----------


def test_lecture_locale_sans_jeton(web):
    assert web.get("/sante").json() == {"ok": True}


def test_fabrique_garde_base_bus_et_lcu(app, temp_db):
    assert (app.state.db_path, app.state.bus, app.state.lcu) == (temp_db, "bus", "lcu")


def test_jeton_different_a_chaque_application(temp_db):
    assert create_app(temp_db).state.session_token != create_app(temp_db).state.session_token


def test_documentation_openapi_non_exposee(web):
    assert [web.get(p).status_code for p in ("/docs", "/redoc", "/openapi.json")] == [404] * 3


@pytest.mark.parametrize("method, path", [("post", "/_ecrit"), ("delete", "/_efface")])
def test_ecriture_sans_jeton_refusee(web, method, path):
    assert getattr(web, method)(path).status_code == 403


def test_ecriture_avec_mauvais_jeton_refusee(web):
    response = web.post("/_ecrit", headers={client_config.TOKEN_HEADER: "faux"})
    assert response.status_code == 403


def test_ecriture_avec_jeton_valide_acceptee(web, app):
    assert web.post("/_ecrit", headers=token_header(app)).json() == {"ecrit": True}


def test_flux_sse_exige_le_jeton(web, app):
    assert web.get("/events").status_code == 403
    assert web.get("/events", headers=token_header(app)).status_code == 200


@pytest.mark.parametrize("origin", ["http://evil.example", "https://127.0.0.1", "null"])
def test_origine_etrangere_refusee_meme_avec_jeton(web, app, origin):
    headers = {**token_header(app), "Origin": origin}
    assert web.post("/_ecrit", headers=headers).status_code == 403
    assert web.get("/sante", headers={"Origin": origin}).status_code == 403


def test_origine_locale_acceptee(web, app):
    headers = {**token_header(app), "Origin": "http://127.0.0.1:51234"}
    assert web.post("/_ecrit", headers=headers).status_code == 200


def test_host_etranger_refuse(app):
    """Anti-DNS rebinding : un nom d'hôte qui résout vers 127.0.0.1 n'est pas le nôtre."""
    rebinding = TestClient(app, base_url="http://evil.example")
    assert rebinding.get("/sante").status_code == 403
    assert rebinding.post("/_ecrit", headers=token_header(app)).status_code == 403


def test_refus_sans_appel_lcu(temp_db):
    class FauxLCU:
        calls: list = []

        def __getattr__(self, name):
            self.calls.append(name)

    lcu = FauxLCU()
    app = create_app(temp_db, lcu=lcu)
    app.post("/_action")(lambda: app.state.lcu.accept())  # route qui appellerait le LCU
    TestClient(app, base_url=LOCAL).post("/_action")
    TestClient(app, base_url="http://evil.example").post("/_action")
    assert lcu.calls == []


# ---------- serveur en fil ----------


@pytest.fixture
def running(temp_db):
    url = server.start(temp_db)
    yield url
    server.stop()


def test_serveur_demarre_sur_la_boucle_locale(running):
    assert running.startswith("http://127.0.0.1:")
    assert httpx.get(f"{running}/sante").json() == {"ok": True}
    bound = server._server.servers[0].sockets[0].getsockname()
    assert bound[0] == "127.0.0.1"
    assert bound[1] == int(running.rsplit(":", 1)[1])


def test_serveur_idempotent(running, temp_db):
    assert server.start(temp_db) == running


def test_serveur_en_fil_daemon_et_arret(temp_db):
    url = server.start(temp_db)
    thread = server._thread
    assert thread.daemon
    server.stop()
    assert not thread.is_alive()
    assert server._url is None
    with pytest.raises(httpx.TransportError):
        httpx.get(f"{url}/sante")
    server.stop()  # sans effet quand rien ne tourne


def test_serveur_port_pris_alerte_sans_exception(temp_db, monkeypatch, capsys):
    with socket.socket() as occupant:
        occupant.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        occupant.bind((client_config.HOST, 0))
        occupant.listen()
        monkeypatch.setattr(client_config, "PORT", occupant.getsockname()[1])
        assert server.start(temp_db) is None
    assert "[ALERTE]" in capsys.readouterr().out
    assert server._url is None


def test_serveur_echec_de_fabrique_alerte_sans_exception(temp_db, monkeypatch, capsys):
    def boom(*args):
        raise RuntimeError("fabrique cassée")

    monkeypatch.setattr(server, "create_app", boom)
    assert server.start(temp_db) is None
    assert "[ALERTE]" in capsys.readouterr().out
    assert server._url is None
