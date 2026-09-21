"""Régression : l'avertissement SPEC-13 nommait une commande inexistante.

Remonté par @pj35 le 2026-09-21. Le message affiché quand les poids de shrink
ne sont pas mesurés disait de lancer ``python -m src.pipeline --recompute-only``.
Or ``src/pipeline.py`` est un module de bibliothèque sans bloc ``__main__`` :
cette commande importe le module et rend la main en silence, sans rien
recalculer. Lancé autrement (``python .\\pipeline.py`` depuis ``src/``), le
fichier lève ``ImportError: attempted relative import with no known parent
package`` — ce qui a été observé.

La vraie CLI est ``scripts/update_all.py``. Un message d'aide qui envoie dans
le mur est pire que pas de message : il coûte à l'utilisateur le temps de
découvrir que le conseil était faux.

Le test vérifie que la commande annoncée est réellement invocable, plutôt que
de comparer deux chaînes de caractères — c'est l'invocabilité qui était fausse,
pas l'orthographe.
"""

import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
ENTRY_POINT = PROJECT_ROOT / "scripts" / "update_all.py"


def _notice_text() -> str:
    """Le message tel que DraftMonitor l'affiche, lu à la source."""
    return (PROJECT_ROOT / "src" / "draft_monitor.py").read_text(encoding="utf-8")


def test_the_advertised_entry_point_exists():
    assert ENTRY_POINT.is_file(), f"{ENTRY_POINT} n'existe pas"


def test_the_advertised_entry_point_is_runnable_and_accepts_the_flag():
    """`--help` prouve que le script s'exécute ET qu'il expose l'option citée.

    C'est ce qu'un simple `assert "--recompute-only" in message` n'aurait pas
    attrapé : l'ancienne commande était bien orthographiée, elle ne menait
    simplement à aucun point d'entrée.
    """
    result = subprocess.run(
        [sys.executable, str(ENTRY_POINT), "--help"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, f"--help a échoué :\n{result.stderr}"
    assert "--recompute-only" in result.stdout


def test_the_notice_points_at_that_entry_point():
    """Et le message affiché nomme bien ce script, pas src.pipeline."""
    notice = _notice_text()

    assert "scripts/update_all.py --recompute-only" in notice
    assert "-m src.pipeline" not in notice
