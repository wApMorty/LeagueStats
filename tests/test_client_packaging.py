"""Empaquetage du client (SPEC-21 tâche 56) : le `.spec` embarque ce que le client lit à l'exécution, les
dépendances sont déclarées, la CI construit l'exe puis le vérifie. Le contrôle de l'exe lui-même est
`scripts/check_exe_assets.py` (ici testé sur une archive factice, sans construire d'exe)."""

import ast
import re
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import check_exe_assets

ROOT = Path(__file__).parent.parent
SPEC = ROOT / "LeagueStatsCoach.spec"
CLIENT = ROOT / "src" / "client"


def spec_datas():
    """Les couples (source, destination) de `Analysis(datas=[...])`, lus sans exécuter le `.spec`."""
    for node in ast.walk(ast.parse(SPEC.read_text(encoding="utf-8"))):
        if isinstance(node, ast.keyword) and node.arg == "datas":
            return ast.literal_eval(node.value)
    raise AssertionError("pas de datas dans le .spec")


def test_le_spec_embarque_gabarits_et_statiques_sous_leur_chemin_de_developpement():
    """`get_resource_path("src/client/...")` cherche sous `_MEIPASS` le même chemin que le dépôt."""
    datas = spec_datas()
    for folder in ("templates", "static"):
        assert (f"src/client/{folder}", f"src/client/{folder}") in datas


def test_chaque_source_du_spec_existe():
    for source, _ in spec_datas():
        if source != "data/db.db":  # la base personnelle est hors dépôt (gitignorée)
            assert (ROOT / source).exists(), source


def test_aucun_hiddenimport_pour_uvicorn_ni_pywebview():
    """Les hooks de PyInstaller suffisent tant que le code importe ces modules (SPEC-21 §8)."""
    assert not re.search(
        r"hiddenimports=\[[^\]]*(uvicorn|webview)", SPEC.read_text(encoding="utf-8")
    )


def test_les_modules_tiers_du_client_sont_declares_dans_requirements():
    requirements = {
        re.split(r"[<>=;\s]", line, maxsplit=1)[0].lower().replace("-", "_")
        for line in (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }
    provided_by = {  # nom du module -> paquet qui le fournit
        "webview": "pywebview",
        "sse_starlette": "sse_starlette",
        "markupsafe": "jinja2",  # dépendance de Jinja2
        "anyio": "fastapi",  # dépendance de Starlette, donc de FastAPI
        "starlette": "fastapi",
    }
    modules = set()
    for path in CLIENT.glob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                modules |= {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                modules.add(node.module.split(".")[0])
    third_party = {m for m in modules if m not in sys.stdlib_module_names and m != "src"}
    undeclared = sorted(m for m in third_party if provided_by.get(m, m) not in requirements)
    assert undeclared == []


def test_la_ci_construit_l_exe_apres_les_tests_puis_verifie_le_client():
    ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    build = ci.split("  build:", 1)[1].split("\n  # ====", 1)[0]
    assert "needs: [quality, tests]" in build
    assert "python build_app.py" in build
    assert (
        "scripts/check_exe_assets.py" in build
    )  # le client est dans l'exe, pas seulement l'exe construit


# ---------- scripts/check_exe_assets.py ----------


def fake_archive(files, modules):
    """Un `CArchiveReader` factice : fichiers de l'exe et modules de son PYZ."""

    class Reader:
        def __init__(self, path):
            self.toc = {name: None for name in files}

        def open_embedded_archive(self, name):
            assert name == "PYZ.pyz"
            return SimpleNamespace(toc={m: None for m in modules})

    return Reader


def test_les_fichiers_attendus_sont_ceux_du_depot():
    expected = check_exe_assets.expected_files()
    assert "src/client/templates/base.html" in expected
    assert "src/client/static/style.css" in expected
    assert any(name.startswith("src/client/static/fonts/") for name in expected)
    assert not any("__pycache__" in name for name in expected)


def test_un_exe_complet_n_a_rien_a_signaler(monkeypatch):
    monkeypatch.setattr(
        check_exe_assets,
        "CArchiveReader",
        fake_archive(check_exe_assets.expected_files(), check_exe_assets.MODULES),
    )
    assert check_exe_assets.check(Path("LeagueStatsCoach.exe")) == []


def test_un_exe_sans_gabarit_ni_module_le_dit(monkeypatch):
    files = [f for f in check_exe_assets.expected_files() if not f.endswith("base.html")]
    modules = [m for m in check_exe_assets.MODULES if m != "uvicorn"]
    monkeypatch.setattr(check_exe_assets, "CArchiveReader", fake_archive(files, modules))
    assert check_exe_assets.check(Path("x.exe")) == [
        "fichier absent : src/client/templates/base.html",
        "module absent : uvicorn",
    ]


def test_les_chemins_windows_de_l_archive_sont_reconnus(monkeypatch):
    files = [f.replace("/", "\\") for f in check_exe_assets.expected_files()]
    monkeypatch.setattr(
        check_exe_assets, "CArchiveReader", fake_archive(files, check_exe_assets.MODULES)
    )
    assert check_exe_assets.check(Path("x.exe")) == []


def test_exe_introuvable(capsys, monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "argv", ["check_exe_assets.py", str(tmp_path / "absent.exe")])
    assert check_exe_assets.main() == 1
    assert "[ERREUR] Exécutable introuvable" in capsys.readouterr().out
