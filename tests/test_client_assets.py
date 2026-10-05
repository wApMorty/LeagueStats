"""Assets Data Dragon du client (SPEC-21 tâche 86) : cache disque, version, route `/assets/...`."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.client.app import create_app
from src.client.assets import PLACEHOLDER, Assets
from src.config_client import client_config

LOCAL = "http://127.0.0.1"
PNG = b"\x89PNG\r\n\x1a\n-portrait"

CHAMPIONS = {
    "data": {
        "Aatrox": {"key": "266", "id": "Aatrox", "name": "Aatrox", "tags": ["Fighter"]},
        "MonkeyKing": {"key": "62", "id": "MonkeyKing", "name": "Wukong", "tags": ["Fighter"]},
    }
}
SKINS = {
    "data": {"Aatrox": {"skins": [{"num": 0, "name": "default"}, {"num": 1, "name": "Justicier"}]}}
}
RUNES = [
    {
        "id": 8000,
        "key": "Precision",
        "slots": [{"runes": [{"id": 8005, "icon": "perk-images/a.png"}]}],
    }
]


class Reseau:
    """Faux Data Dragon : sert un dictionnaire d'URL, compte les appels."""

    def __init__(self, files=None):
        base = client_config.DDRAGON_BASE
        self.files = {
            f"{base}/api/versions.json": json.dumps(["16.2.1", "16.1.1"]).encode(),
            f"{base}/cdn/16.2.1/img/champion/Aatrox.png": PNG,
            f"{base}/cdn/16.2.1/data/fr_FR/champion.json": json.dumps(CHAMPIONS).encode(),
            f"{base}/cdn/16.2.1/data/fr_FR/champion/Aatrox.json": json.dumps(SKINS).encode(),
            f"{base}/cdn/16.2.1/data/fr_FR/runesReforged.json": json.dumps(RUNES).encode(),
            f"{base}/cdn/img/perk-images/Styles/Precision/Conqueror.png": PNG,
            f"{base}/cdn/img/champion/loading/Aatrox_1.jpg": b"jpg",
        }
        self.files.update(files or {})
        self.calls = []

    def __call__(self, url):
        self.calls.append(url)
        return self.files.get(url)


@pytest.fixture(autouse=True)
def _version_auto(monkeypatch):
    monkeypatch.setattr(client_config, "DDRAGON_VERSION", "")


@pytest.fixture
def reseau():
    return Reseau()


@pytest.fixture
def assets(tmp_path, reseau):
    return Assets(tmp_path / "cache", fetch=reseau)


def test_version_la_plus_recente_puis_cache(assets, reseau):
    assert assets.version() == "16.2.1"
    assert assets.version() == "16.2.1"
    assert sum(url.endswith("versions.json") for url in reseau.calls) == 1


def test_version_de_la_config_sans_reseau(assets, reseau, monkeypatch):
    monkeypatch.setattr(client_config, "DDRAGON_VERSION", "14.24.1")
    assert assets.version() == "14.24.1" and reseau.calls == []


def test_version_hors_ligne_lit_la_liste_perimee(tmp_path, monkeypatch):
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "versions.json").write_text('["15.9.1"]')
    monkeypatch.setattr(client_config, "ASSETS_VERSIONS_TTL_S", -1)  # périmée
    assert Assets(cache, fetch=lambda url: None).version() == "15.9.1"


def test_version_inconnue_sans_reseau_ni_cache(tmp_path):
    assets = Assets(tmp_path / "cache", fetch=lambda url: None)
    assert assets.version() is None and assets.image("champion", "Aatrox.png") is None


def test_image_telechargee_une_fois_puis_lue_sur_disque(assets, reseau, tmp_path):
    assert assets.image("champion", "Aatrox.png") == PNG
    assert assets.image("champion", "Aatrox.png") == PNG
    assert sum(u.endswith("Aatrox.png") for u in reseau.calls) == 1
    assert (tmp_path / "cache" / "champion" / "16.2.1" / "Aatrox.png").read_bytes() == PNG


def test_image_non_versionnee(assets):
    assert assets.image("perk", "perk-images/Styles/Precision/Conqueror.png") == PNG
    assert assets.image("loading", "Aatrox_1.jpg") == b"jpg"


def test_hors_ligne_le_cache_seul_repond(assets, tmp_path):
    assets.image("champion", "Aatrox.png")
    hors_ligne = Assets(tmp_path / "cache", fetch=lambda url: None)
    assert hors_ligne.image("champion", "Aatrox.png") == PNG
    assert hors_ligne.image("champion", "Garen.png") is None


def test_un_echec_n_est_pas_retente_tout_de_suite(tmp_path, reseau):
    assets = Assets(tmp_path / "cache", fetch=reseau)
    assert assets.image("champion", "Garen.png") is None
    assert assets.image("champion", "Garen.png") is None
    assert sum(u.endswith("Garen.png") for u in reseau.calls) == 1


@pytest.mark.parametrize(
    "kind, name",
    [
        ("champion", "../x.png"),
        ("champion", "a/b.png"),
        ("champion", "Aatrox.exe"),
        ("spell", "Flash.png"),
        ("item", "abc.png"),
        ("perk", "../../etc/passwd.png"),
        ("perk", "perk-images/../x.png"),
        ("perk", "/absolu.png"),
        ("loading", "Aatrox.jpg"),
        ("inconnu", "Aatrox.png"),
    ],
)
def test_noms_refuses(assets, reseau, kind, name):
    assert not assets.accepts(kind, name)
    assert assets.image(kind, name) is None
    assert reseau.calls == []  # aucune URL n'est construite


def test_champions_skins_et_runes(assets):
    assert assets.champions() == [
        {"key": 266, "id": "Aatrox", "name": "Aatrox", "tags": ["Fighter"]},
        {"key": 62, "id": "MonkeyKing", "name": "Wukong", "tags": ["Fighter"]},
    ]
    assert [s["num"] for s in assets.skins("Aatrox")] == [0, 1]
    assert assets.skins("../x") == [] and assets.skins("Garen") == []
    assert assets.rune_styles()[0]["key"] == "Precision"


def test_donnees_illisibles_donnent_des_listes_vides(tmp_path):
    base = client_config.DDRAGON_BASE
    reseau = Reseau({f"{base}/cdn/16.2.1/data/fr_FR/champion.json": b"pas du json"})
    assets = Assets(tmp_path / "cache", fetch=reseau)
    assert assets.champions() == [] and assets.rune_styles() != []


# ---------- route ----------


@pytest.fixture
def client(temp_db, assets):
    return TestClient(create_app(temp_db, assets=assets), base_url=LOCAL)


def test_route_sert_l_image_avec_cache_navigateur(client):
    response = client.get("/assets/champion/Aatrox.png")
    assert response.status_code == 200 and response.content == PNG
    assert response.headers["content-type"] == "image/png"
    assert "max-age" in response.headers["cache-control"]


def test_route_perk_avec_chemin(client):
    response = client.get("/assets/perk/perk-images/Styles/Precision/Conqueror.png")
    assert response.status_code == 200 and response.content == PNG


def test_route_jpeg(client):
    assert client.get("/assets/loading/Aatrox_1.jpg").headers["content-type"] == "image/jpeg"


def test_route_image_absente_rend_un_emplacement_neutre(client):
    response = client.get("/assets/champion/Garen.png")
    assert response.status_code == 200 and response.content == PLACEHOLDER
    assert response.headers["cache-control"] == "no-store"


def test_route_nom_refuse_404(client):
    assert client.get("/assets/champion/x.exe").status_code == 404
    assert client.get("/assets/inconnu/Aatrox.png").status_code == 404
    assert client.get("/assets/perk/..%2F..%2Fx.png").status_code == 404


def test_cache_par_defaut_ne_touche_pas_le_disque_a_la_creation(temp_db, monkeypatch, tmp_path):
    monkeypatch.setattr("src.client.app.get_user_data_path", lambda name: str(tmp_path / name))
    create_app(temp_db)
    assert not (tmp_path / client_config.ASSETS_DIR).exists()
