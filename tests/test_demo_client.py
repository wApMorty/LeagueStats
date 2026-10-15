"""Mode démo du client (SPEC-34 §4.3) : faux LCU, isolation de la base et des journaux."""

import hashlib
import sqlite3
from pathlib import Path

import psutil
import pytest

from scripts import demo_client as demo
from src.config import config
from src.draft import tick_timer
from src.lcu_client import LCUClient
from src.winprob import live


@pytest.fixture
def fake():
    return demo.FakeLcu(demo.load_scenario())


@pytest.fixture
def lcu_url(fake, monkeypatch):
    """Le faux LCU servi sur un port libre, tous les `LCUClient` pointés dessus."""
    httpd, url = demo.serve(fake)
    demo.point_to(url, monkeypatch.setattr)
    yield url
    httpd.shutdown()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_faux_lcu_sert_les_fixtures_et_rien_d_autre(fake):
    assert fake.read("/lol-summoner/v1/current-summoner")["gameName"] == "Démo"
    assert fake.read("/lol-gameflow/v1/gameflow-phase") == "None"
    assert fake.read("/lol-match-history/v1/games/123")["gameId"] == 123
    history = "/lol-match-history/v1/products/lol/current-summoner/matches?begIndex=0&endIndex=19"
    assert len(fake.read(history)["games"]["games"]) == 20
    assert fake.read("/lol-store/v1/catalog") is None
    assert fake.read("/lol-summoner/v1/current-summoner/extra") is None  # motif complet


def test_un_lcu_client_ne_parle_qu_au_faux_lcu(lcu_url, monkeypatch):
    def interdit(*_args, **_kwargs):
        raise AssertionError("le vrai client LoL a été cherché")

    monkeypatch.setattr(psutil, "process_iter", interdit)
    lcu = LCUClient()
    assert lcu.connect()
    assert lcu.credentials.base_url == lcu_url
    assert lcu._make_request("/lol-gameflow/v1/gameflow-phase") == "None"
    assert lcu._make_request("/lol-store/v1/catalog") is None
    assert lcu.last_status_code == 404
    assert lcu._make_request("/lol-perks/v1/pages", "POST", {"name": "LS"}) == {}
    assert live.URL == f"{lcu_url}{demo.LIVE_PATH}"
    assert live.fetch() is None  # aucune partie dans la scène d'accueil


def test_isolate_ne_touche_jamais_la_base_source(temp_db, tmp_path, monkeypatch):
    source = Path(temp_db)
    before = (_sha(source), source.stat().st_mtime_ns)
    workdir = tmp_path / "demo"
    patches = demo.isolate(source, workdir, monkeypatch.setattr)

    copy = Path(config.DATABASE_PATH)
    assert copy.parent == workdir and copy != source
    with sqlite3.connect(copy) as connection:
        connection.execute("CREATE TABLE demo_write (x INTEGER)")
    assert (_sha(source), source.stat().st_mtime_ns) == before
    assert workdir in Path(tick_timer._LOG_PATH).parents
    for _target, _name, value in patches:
        if isinstance(value, (str, Path)):
            assert workdir in Path(value).parents


def test_liste_des_scenes_du_client(fake):
    assert fake.names()[:3] == ["accueil", "profil", "historique"]
    fake.set_scene("profil")
    assert fake.phase() == "None"
    with pytest.raises(KeyError):
        fake.set_scene("inconnue")
