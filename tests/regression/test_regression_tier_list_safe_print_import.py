"""Regression test: la génération de Counter Pick tier list plantait avec
`ImportError: cannot import name 'safe_print' from 'src.assistant'`.

Bug: `src/ui/tier_list_ui.py::_display_tier_list` importait `safe_print` depuis
`src.assistant`, un emplacement obsolète -- `safe_print` a été déplacé vers
`src/utils/display.py` lors d'un refactor précédent, sans mettre à jour cet
import résiduel.

Fix: import corrigé vers `from src.utils.display import safe_print`.
"""

from src.ui.tier_list_ui import _display_tier_list


def test_display_tier_list_does_not_raise_import_error():
    tier_list = [
        {
            "champion": "Ahri",
            "score": 90.0,
            "tier": "S",
            "metrics": {
                "peak_impact_raw": 1.5,
                "variance": 0.4,
                "target_ratio_raw": 0.6,
            },
        },
    ]

    # Ne doit pas lever ImportError (bug initial) ni aucune autre exception
    # liée à l'affichage pour un jeu de données valide.
    _display_tier_list(tier_list, "Test Pool", "COUNTER PICK", "counter_pick", "middle")
