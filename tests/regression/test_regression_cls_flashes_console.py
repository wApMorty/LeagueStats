"""Régression : en pleine draft, une micro-fenêtre s'ouvrait et volait le focus à chaque lock.

Symptôme : le client lancé par `pythonw.exe lol_coach.py --client` faisait clignoter une fenêtre
à chaque nouveau pick, et la fenêtre active perdait le focus (signalé par @pj35, 2026-10-22).
Cause racine : le Live Coach appelle `clear_console()` à chaque pick ; `os.system("cls")` lance
`cmd.exe`, qui, sans console à hériter (pythonw), en crée une le temps de s'exécuter.
Correctif : `clear_console()` ne fait rien sans console (`sys.stdout` à None).
Prévention : ce test vérifie qu'aucune commande n'est lancée dans ce cas.
"""

from unittest.mock import patch

from src.utils.console import clear_console, set_clear_enabled


@patch("src.utils.console.sys.stdout", None)
@patch("src.utils.console.os.system")
def test_pas_de_cls_sans_console(mock_system):
    set_clear_enabled(True)
    clear_console()
    mock_system.assert_not_called()
