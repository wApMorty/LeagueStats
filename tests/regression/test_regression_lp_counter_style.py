"""Régression SPEC-45 : sur l'écran post-game, le nombre de LP était petit et gris entre le « + » et « LP ».

Symptôme : l'encart LP de la revue affiche « + 19 LP » où le « + » et le « LP » sont en 58 px en dégradé,
mais le nombre `19` est en 15 px gris (`--ink-2`), comme la ligne de rang.

Cause racine : `partie.html` place le compteur `<span data-count>` à l'intérieur du `<b>` (le gros
texte en dégradé). La règle `.lp-gain span` (sélecteur de descendant) attrape ce compteur et lui applique
le style de la ligne de rang (15 px, gris).

Correctif : `.lp-gain > span` (enfant direct), qui ne vise plus que la ligne de rang.

Prévention : ce test interdit le sélecteur de descendant `.lp-gain span` et exige la règle en enfant
direct avec `font-size: 15px`.
"""

import re
from pathlib import Path

CSS = Path("src/client/static/style.css")


def test_pas_de_selecteur_descendant_sur_lp_gain():
    css = CSS.read_text(encoding="utf-8")
    assert re.search(r"\.lp-gain\s+span\b", css) is None


def test_la_ligne_de_rang_est_un_enfant_direct_en_15px():
    css = CSS.read_text(encoding="utf-8")
    match = re.search(r"\.lp-gain\s*>\s*span\s*\{([^}]*)\}", css)
    assert match is not None
    assert "font-size: 15px" in match.group(1)
