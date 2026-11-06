"""SPEC-51 tâche 254 : page Méta du poste (vue pure, route, redirection depuis /blindabilite)."""

from fastapi.testclient import TestClient

from src import user_prefs
from src.client import app as app_module
from src.analysis.pick_order import Pick
from src.client.app import create_app
from src.client.draft_view import Champions
from src.client.meta_poste import meta_view
from src.config_constants import scraping_config
from tests.support_lcu_nav import make_assets

LOCAL = "http://127.0.0.1"
LANES = scraping_config.LANES


class _NoAssets:
    def champions(self):
        return []


def _champions():
    return Champions(_NoAssets())


def _full():
    """Matrice 5 × 5 complète, toutes les cases à 1.0 (moyenne non nulle)."""
    return {row: {col: 1.0 for col in LANES} for row in LANES}


def _data():
    return {"matchups": _full(), "synergies": {}, "draws": {}}


def _mine(matrix):
    return sum(cell["mine"] for row in matrix["rows"] for cell in row["cells"] if cell)


def test_neuf_cases_mine_sur_matrice_complete():
    data = {"matchups": _full(), "synergies": {}, "draws": {}}

    matrix = meta_view(data, _champions(), "top", (), [])["matchups"]

    assert _mine(matrix) == 9  # ligne (5) + colonne (5) moins la diagonale commune


def test_huit_cases_mine_sans_la_diagonale_du_poste():
    data = _full()
    del data["top"]["top"]

    matrix = meta_view({"matchups": data}, _champions(), "top", (), [])["matchups"]

    assert _mine(matrix) == 8


def test_cases_mine_suivent_le_poste_choisi():
    data = {"matchups": _full(), "synergies": {}, "draws": {}}

    matrix = meta_view(data, _champions(), "support", (), [])["matchups"]

    assert _mine(matrix) == 9
    assert [r["label"] for r in matrix["rows"] if r["mine"]] == ["Support"]
    assert [c["label"] for c in matrix["columns"] if c["mine"]] == ["Support"]
    assert matrix["rows"][-1]["cells"][-1]["mine"] is True


def test_entetes_du_poste_seulement():
    data = {"matchups": _full(), "synergies": _full(), "draws": {}}

    view = meta_view(data, _champions(), "jungle", (), [])

    for matrix in (view["matchups"], view["synergies"]):
        assert [r["label"] for r in matrix["rows"] if r["mine"]] == ["Jungle"]
        assert [c["label"] for c in matrix["columns"] if c["mine"]] == ["Jungle"]


def test_pool_marque_les_champions_sans_casse():
    data = {"matchups": _full(), "draws": {"top": {"Ahri": 0.5, "Yasuo": -0.5}}}

    view = meta_view(data, _champions(), "top", ("ahri",), [])

    flags = {c["name"]: c["mine"] for column in view["histogram"] for c in column["champions"]}
    assert flags == {"Ahri": True, "Yasuo": False}


def test_picks_marques_sur_le_poste_choisi():
    picks = [Pick(slot=1, side="blue", lane="top"), Pick(slot=2, side="red", lane="middle")]
    data = {"matchups": _full(), "draws": {}}

    view = meta_view(data, _champions(), "top", (), picks)

    assert [(p["slot"], p["label"], p["mine"]) for p in view["picks"]] == [
        (1, "Top", True),
        (2, "Mid", False),
    ]


def test_poste_inconnu_revient_a_top():
    view = meta_view({"matchups": _full()}, _champions(), "inconnu", (), [])

    assert next(lane for lane in view["lanes"] if lane["on"])["key"] == "top"
    assert [r["label"] for r in view["matchups"]["rows"] if r["mine"]] == ["Top"]


def test_vue_vide_sans_donnees():
    view = meta_view({}, _champions(), "top", (), [])

    assert view["empty"] and view["picks"] == []


def _client(path, tmp_path):
    return TestClient(
        create_app(path, assets=make_assets(tmp_path)),
        base_url=LOCAL,
        raise_server_exceptions=False,
    )


def _prefs_lane():
    return user_prefs.load_meta_lane()


def test_poste_memorise_et_relu_sans_parametre(temp_db, tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "compute_blindability", lambda connection: _data())
    client = _client(temp_db, tmp_path)

    assert client.get("/meta?poste=jungle").status_code == 200
    assert _prefs_lane() == "jungle"

    response = client.get("/meta")
    assert response.status_code == 200
    assert 'href="/meta?poste=jungle" aria-current="true"' in response.text


def test_poste_invalide_ne_remplace_pas_le_memorise(temp_db, tmp_path):
    client = _client(temp_db, tmp_path)
    client.get("/meta?poste=support")

    assert client.get("/meta?poste=zzz").status_code == 200
    assert _prefs_lane() == "support"


def test_blindabilite_redirige_en_303_vers_meta(temp_db, tmp_path):
    client = _client(temp_db, tmp_path)

    valid = client.get("/blindabilite?poste=bottom", follow_redirects=False)
    assert valid.status_code == 303
    assert valid.headers["location"] == "/meta?poste=bottom"

    bare = client.get("/blindabilite", follow_redirects=False)
    assert bare.status_code == 303
    assert bare.headers["location"] == "/meta"

    invalid = client.get("/blindabilite?poste=zzz", follow_redirects=False)
    assert invalid.headers["location"] == "/meta"


def test_base_absente_page_vide_sans_500(tmp_path):
    response = _client(tmp_path / "absente.db", tmp_path).get("/meta")

    assert response.status_code == 200
    assert "Pas encore assez de matchups" in response.text
    assert not (tmp_path / "absente.db").exists()
