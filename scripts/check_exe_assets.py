"""Vérifie que l'exécutable contient le client LeagueStats (SPEC-21 tâche 56) sans le lancer.

Ouvre l'archive de l'exe (PyInstaller) et contrôle : les gabarits, les statiques et les polices du client
(fichiers lus à l'exécution par `config.get_resource_path`), et les modules du serveur et de la fenêtre
(importés par le code, sans `hiddenimports`). Aucune fenêtre n'est ouverte, aucun serveur démarré.

USAGE:
    python scripts/check_exe_assets.py                         # dist/LeagueStatsCoach.exe
    python scripts/check_exe_assets.py chemin/vers/l.exe
"""

import sys
from pathlib import Path
from typing import List

from PyInstaller.archive.readers import CArchiveReader

project_root = Path(__file__).parent.parent
CLIENT = project_root / "src" / "client"
MODULES = (
    "src.client.app",
    "src.client.launch",
    "src.client.ingame",
    "src.client.en_partie",
    "src.client.draft_swaps",
    "src.draft.phase_tracker",
    "src.coaching.post_game_watcher",
    "fastapi",
    "uvicorn",
    "jinja2",
    "sse_starlette",
    "websockets",
    "webview",
)


def expected_files() -> List[str]:
    """Chaque fichier de gabarit et de statique du dépôt, sous son chemin d'exécution."""
    return sorted(
        path.relative_to(project_root).as_posix()
        for folder in ("templates", "static")
        for path in (CLIENT / folder).rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )


def check(exe: Path) -> List[str]:
    """Les manques de l'exe, un message par élément absent (liste vide : tout y est)."""
    reader = CArchiveReader(str(exe))
    present = {name.replace("\\", "/") for name in reader.toc}
    modules = set(reader.open_embedded_archive("PYZ.pyz").toc)
    missing = [f"fichier absent : {name}" for name in expected_files() if name not in present]
    missing += [f"module absent : {name}" for name in MODULES if name not in modules]
    return missing


def main() -> int:
    exe = Path(sys.argv[1]) if len(sys.argv) > 1 else project_root / "dist" / "LeagueStatsCoach.exe"
    if not exe.exists():
        print(f"[ERREUR] Exécutable introuvable : {exe}")
        return 1
    missing = check(exe)
    for line in missing:
        print(f"[ERREUR] {line}")
    if missing:
        return 1
    print(
        f"[OK] {exe.name} : {len(expected_files())} fichiers du client et "
        f"{len(MODULES)} modules présents ({exe.stat().st_size / 1e6:.1f} Mo)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
