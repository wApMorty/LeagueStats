"""Coque du client LeagueStats (SPEC-21 tâches 68 et 69) : pages, navigation, thème, états, fenêtre."""

import json
import re
import sqlite3
import sys
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.client import window
from src.client.app import NAV, create_app
from src.client.lcu_status import LcuProbe
from src.config_client import client_config
from src.user_prefs import UserPrefs, load_motion, load_user_prefs, save_motion, save_user_prefs

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CLIENT_DIR = PROJECT_ROOT / "src" / "client"

LOCAL = "http://127.0.0.1"


class FauxLCU:
    """`LCUClient` réduit à ce que sonde le client : identifiants et une requête."""

    def __init__(self, up: bool = True) -> None:
        self.up = up
        self.credentials = None
        self.requests = []

    def find_lcu_credentials(self):
        return object() if self.up else None

    def _make_request(self, endpoint, method="GET", data=None):
        self.requests.append(endpoint)
        return "None" if self.up else None


@pytest.fixture(autouse=True)
def _probe_sans_cache(monkeypatch):
    monkeypatch.setattr(client_config, "LCU_PROBE_TTL_S", 0.0)


@pytest.fixture(autouse=True)
def _prefs_isolees(monkeypatch, tmp_path):
    """Le réglage Motion vit dans `user_prefs.json` : jamais celui du dépôt."""
    monkeypatch.setattr("src.user_prefs.get_user_prefs_path", lambda: str(tmp_path / "prefs.json"))


def make_client(temp_db, lcu=None) -> TestClient:
    return TestClient(create_app(temp_db, lcu=lcu), base_url=LOCAL, raise_server_exceptions=False)


# ---------- pages ----------


def test_accueil_est_la_coque(temp_db):
    client = make_client(temp_db)
    response = client.get("/")
    html = response.text
    assert response.status_code == 200
    assert html.count('aria-current="page"') == 1 and 'href="/" style' in html
    assert html.count('class="resize-handle"') == 8  # 4 côtés, 4 coins
    assert all(f'id="{i}"' in html for i in ("tb-min", "tb-max", "tb-close", "titlebar-drag"))
    assert "pywebview-drag-region" in html


def test_page_porte_le_jeton_de_session(temp_db):
    client = make_client(temp_db)
    html = client.get("/").text
    token = client.app.state.session_token
    assert f'<meta name="session-token" content="{token}">' in html
    assert f'content="{client_config.TOKEN_HEADER}"' in html


def test_configuration_htmx_valide_et_echange_les_erreurs(temp_db):
    html = make_client(temp_db).get("/").text
    config = json.loads(re.search(r"name=\"htmx-config\" content='([^']+)'", html).group(1))
    assert config["allowEval"] is False and config["allowScriptTags"] is False
    handled = {rule["code"]: rule for rule in config["responseHandling"]}
    assert handled["[45].."]["swap"] is True  # sinon la page d'erreur n'apparaît jamais


@pytest.mark.parametrize(
    "path, kind", [("htmx.min.js", "javascript"), ("shell.js", "javascript"), ("style.css", "css")]
)
def test_statiques_servis(temp_db, path, kind):
    response = make_client(temp_db).get(f"/static/{path}")
    assert response.status_code == 200 and kind in response.headers["content-type"]


@pytest.mark.parametrize("font", sorted(p.name for p in (CLIENT_DIR / "static/fonts").glob("*")))
def test_polices_embarquees_servies(temp_db, font):
    response = make_client(temp_db).get(f"/static/fonts/{font}")
    assert response.status_code == 200 and len(response.content) > 1000


def test_statique_hors_dossier_refuse(temp_db):
    assert make_client(temp_db).get("/static/../app.py").status_code == 404


# ---------- navigation et thème « Alchimie » ----------


def test_navigation_trois_groupes_et_entrees_sans_ecran_grisees(temp_db):
    html = make_client(temp_db).get("/").text
    for group in NAV:
        assert f'<div class="nav-title">{group.label}</div>' in html
    items = [item for group in NAV for item in group.items]
    assert [i.label for i in items if i.href] == ["Accueil"]
    assert html.count('aria-disabled="true"') == len([i for i in items if not i.href])
    assert all(f"{i.label}</span>" in html for i in items)
    assert 'class="rune" aria-hidden="true"' in html  # les runes ne portent jamais le sens


def test_pied_de_navigation_theme_et_motion(temp_db):
    html = make_client(temp_db).get("/").text
    assert "<b>Alchimie</b>" in html
    for mode in client_config.MOTION_MODES:
        assert f'hx-post="/prefs/motion?mode={mode}"' in html


def test_jetons_du_handoff_presents_dans_le_css():
    """Les couleurs OKLCH du README du handoff sont la source de vérité du thème."""
    readme = (PROJECT_ROOT / "docs/design/client_alchimie/README.md").read_text(encoding="utf-8")
    tokens = re.findall(r"\| `(--[\w-]+)` \| `(oklch\([^`]+\))`", readme)
    assert len(tokens) >= 18  # fonds, texte et accents
    css = (CLIENT_DIR / "static/style.css").read_text(encoding="utf-8")
    missing = [f"{name}: {value}" for name, value in tokens if f"{name}: {value};" not in css]
    assert missing == []


def test_aucun_calque_du_prototype_ni_appel_externe():
    assert not list(CLIENT_DIR.rglob("*.dc.html")) and not list(CLIENT_DIR.rglob("support.js"))
    for path in [*CLIENT_DIR.rglob("*.html"), CLIENT_DIR / "static/style.css"]:
        assert not re.search(r"https?://(?!127\.0\.0\.1)", path.read_text(encoding="utf-8")), path


# ---------- réglage Motion ----------


def post_motion(client, mode, token=True):
    headers = {client_config.TOKEN_HEADER: client.app.state.session_token} if token else {}
    return client.post(f"/prefs/motion?mode={mode}", headers=headers)


def test_motion_complet_par_defaut(temp_db):
    html = make_client(temp_db).get("/").text
    assert '<html lang="fr" class="no-chrome" data-motion="complet">' in html


def test_motion_choisi_est_memorise_et_rendu(temp_db):
    client = make_client(temp_db)
    assert post_motion(client, "reduit").status_code == 204
    assert load_motion() == "reduit"
    html = client.get("/").text
    assert 'data-motion="reduit"' in html
    assert 'data-mode="reduit" aria-pressed="true"' in html


def test_motion_sans_jeton_403_et_rien_n_est_ecrit(temp_db):
    client = make_client(temp_db)
    assert post_motion(client, "reduit", token=False).status_code == 403
    assert load_motion() == client_config.MOTION_DEFAULT


def test_motion_valeur_inconnue_400(temp_db):
    client = make_client(temp_db)
    assert post_motion(client, "turbo").status_code == 400
    assert load_motion() == client_config.MOTION_DEFAULT


def test_motion_inconnu_dans_le_fichier_retombe_sur_le_defaut(tmp_path):
    (tmp_path / "prefs.json").write_text('{"motion": "turbo"}', encoding="utf-8")
    assert load_motion() == client_config.MOTION_DEFAULT


def test_motion_garde_les_prefs_du_draft_coach_et_inversement():
    save_user_prefs(UserPrefs(auto_hover=True, pool_name="GRIND"))
    assert save_motion("systeme") is True
    assert load_user_prefs() == UserPrefs(auto_hover=True, pool_name="GRIND")
    # le draft coach réécrit le fichier en fin de session : le réglage Motion survit
    save_user_prefs(UserPrefs(auto_hover=False, pool_name="GRIND"))
    assert load_motion() == "systeme"


def test_motion_seul_laisse_le_draft_coach_poser_ses_questions():
    assert save_motion("reduit") is True
    assert load_user_prefs() is None  # comme sans fichier : les questions habituelles


# ---------- état du client LoL ----------


@pytest.mark.parametrize("lcu, label", [(None, "fermé"), (FauxLCU(False), "fermé")])
def test_pastille_client_ferme(temp_db, lcu, label):
    html = make_client(temp_db, lcu).get("/etat/client").text
    assert f"Client LoL {label}" in html and "chip-closed" in html


def test_pastille_client_ouvert_et_rafraichie(temp_db):
    lcu = FauxLCU(True)
    html = make_client(temp_db, lcu).get("/etat/client").text
    assert "Client LoL connecté" in html and "chip-ok" in html
    assert f'hx-trigger="every {client_config.LCU_STATE_POLL_S}s"' in html
    assert lcu.requests == [client_config.LCU_PROBE_ENDPOINT]


def test_pastille_dans_chaque_page(temp_db):
    assert "Client LoL fermé" in make_client(temp_db, FauxLCU(False)).get("/").text


def test_sonde_garde_sa_reponse(monkeypatch):
    monkeypatch.setattr(client_config, "LCU_PROBE_TTL_S", 60.0)
    lcu = FauxLCU(True)
    probe = LcuProbe(lcu)
    assert probe.is_open() and probe.is_open()
    assert len(lcu.requests) == 1


def test_sonde_oublie_des_identifiants_perimes():
    lcu = FauxLCU(True)
    probe = LcuProbe(lcu)
    assert probe.is_open()
    lcu.up = False  # le client a redémarré : même port, plus de réponse
    assert not probe.is_open()
    assert lcu.credentials is None  # le prochain essai relit le lockfile


def test_sonde_ne_leve_jamais():
    class Casse(FauxLCU):
        def find_lcu_credentials(self):
            raise OSError("lockfile illisible")

    assert LcuProbe(Casse()).is_open() is False


# ---------- erreurs lisibles ----------


def test_base_occupee_503_lisible(temp_db):
    client = make_client(temp_db)

    @client.app.get("/_verrou")
    def verrou():
        raise sqlite3.OperationalError("database is locked")

    response = client.get("/_verrou")
    assert response.status_code == 503
    assert "Base occupée" in response.text and "Réessayer" in response.text


def test_autre_erreur_sqlite_500(temp_db):
    client = make_client(temp_db)

    @client.app.get("/_absente")
    def absente():
        raise sqlite3.OperationalError("unable to open database file")

    response = client.get("/_absente")
    assert response.status_code == 500 and "unable to open database file" in response.text


def test_exception_de_route_page_500_echappee_sans_arreter_le_serveur(temp_db):
    client = make_client(temp_db)

    @client.app.get("/_boom")
    def boom():
        raise RuntimeError("<script>alert(1)</script>")

    response = client.get("/_boom")
    assert response.status_code == 500
    assert "&lt;script&gt;alert(1)" in response.text and "<script>alert(1)" not in response.text
    assert 'aria-current="page"' not in response.text  # pas de section active sur une erreur
    assert client.get("/sante").json() == {"ok": True}


# ---------- fenêtre ----------


class FauxWindow:
    def __init__(self) -> None:
        self.calls = []

    def __getattr__(self, name):
        return lambda *args: self.calls.append((name, *args))


def make_api(frameless: bool = True):
    api = window.WindowApi(frameless)
    api._window = FauxWindow()
    return api


def test_agrandir_remplit_la_zone_utile_puis_restaure(monkeypatch):
    # fenêtre 1280x800 en (120, 90) ; zone utile 1920x986 en (0, 46) ; échelle 100 %
    state = ((120, 90, 1280, 800), (0, 46, 1920, 986), 1.0)
    monkeypatch.setattr(window, "_screen_state", lambda title: state)
    api = make_api()
    api.toggle_maximize()
    assert api._window.calls == [("resize", 1920, 986), ("move", 0, 46)]
    api._window.calls.clear()
    api.toggle_maximize()
    assert api._window.calls == [("resize", 1280, 800), ("move", 120, 90)]
    assert api._saved is None


def test_agrandir_en_pixels_logiques_a_150_pourcent(monkeypatch):
    state = ((180, 135, 1920, 1200), (0, 69, 2880, 1479), 1.5)
    monkeypatch.setattr(window, "_screen_state", lambda title: state)
    api = make_api()
    api.toggle_maximize()
    assert api._window.calls == [("resize", 1920, 986), ("move", 0, 46)]
    api._window.calls.clear()
    api.toggle_maximize()
    assert api._window.calls == [("resize", 1280, 800), ("move", 120, 90)]


@pytest.mark.skipif(sys.platform != "win32", reason="Win32")
def test_ecran_inconnu_sans_fenetre_de_ce_titre():
    assert window._screen_state("LeagueStats-titre-inexistant-0f3a") is None
    # une fenêtre d'un autre processus portant ce titre exact n'est pas la nôtre
    assert window._screen_state("Program Manager") is None


def test_agrandir_sans_ecran_connu_retombe_sur_le_natif(monkeypatch):
    monkeypatch.setattr(window, "_screen_state", lambda title: None)
    api = make_api()
    api.toggle_maximize()
    assert api._window.calls == [("maximize",)]


@pytest.mark.parametrize(
    "fix_east, fix_south, east, south",
    [(False, False, False, False), (True, False, True, False), (False, True, False, True)]
    + [(True, True, True, True)],
)
def test_redimensionner_tient_le_bord_oppose(fix_east, fix_south, east, south):
    pytest.importorskip("webview")
    from webview.window import FixPoint

    api = make_api()
    api.resize(1100.7, 700, fix_east, fix_south)
    ((name, width, height, fix_point),) = api._window.calls
    assert (name, width, height) == ("resize", 1100, 700)
    assert bool(fix_point & FixPoint.EAST) is east and bool(fix_point & FixPoint.SOUTH) is south


def test_redimensionner_respecte_la_taille_minimale():
    pytest.importorskip("webview")
    api = make_api()
    api.resize(10, 10, False, False)
    assert api._window.calls[0][1:3] == client_config.WINDOW_MIN_SIZE


def test_boutons_de_la_fenetre():
    api = make_api(frameless=False)
    api.minimize()
    api.close()
    assert [c[0] for c in api._window.calls] == ["minimize", "destroy"]
    assert api.frameless() is False


@pytest.fixture
def faux_webview(monkeypatch):
    """Module `webview` factice : l'essai de rang `fail_until` échoue, les suivants passent."""
    module = types.ModuleType("webview")
    module.created, module.windows, module.fail_until = [], ["reste"], 0

    def create_window(title, url, **kwargs):
        module.created.append((title, url, kwargs))
        return FauxWindow()

    def start():
        if len(module.created) <= module.fail_until:
            raise RuntimeError("WebView2 absent")

    module.create_window, module.start = create_window, start
    monkeypatch.setitem(sys.modules, "webview", module)
    return module


@pytest.fixture
def navigateur(monkeypatch):
    opened = []
    monkeypatch.setattr(window.webbrowser, "open", opened.append)
    return opened


def test_run_ouvre_la_fenetre_sans_bordure(faux_webview, navigateur):
    assert window.run("http://127.0.0.1:1") is True
    ((title, url, kwargs),) = faux_webview.created
    assert (title, url) == (client_config.WINDOW_TITLE, "http://127.0.0.1:1")
    assert kwargs["frameless"] is True and kwargs["easy_drag"] is False
    assert kwargs["min_size"] == client_config.WINDOW_MIN_SIZE
    assert navigateur == []


def test_run_replie_sur_la_fenetre_standard(faux_webview, navigateur, capsys):
    faux_webview.fail_until = 1
    assert window.run("http://127.0.0.1:1") is True
    assert [c[2]["frameless"] for c in faux_webview.created] == [True, False]
    assert faux_webview.windows == []  # la fenêtre de l'essai raté n'est pas rouverte
    assert "[ALERTE]" in capsys.readouterr().out and navigateur == []


def test_run_replie_sur_le_navigateur(faux_webview, navigateur, capsys):
    faux_webview.fail_until = 99
    assert window.run("http://127.0.0.1:1") is False
    assert navigateur == ["http://127.0.0.1:1"]
    assert capsys.readouterr().out.count("[ALERTE]") == 3


def test_run_sans_pywebview_ouvre_le_navigateur(monkeypatch, navigateur):
    monkeypatch.setitem(sys.modules, "webview", None)  # `import webview` lève ImportError
    assert window.run("http://127.0.0.1:1") is False
    assert navigateur == ["http://127.0.0.1:1"]
