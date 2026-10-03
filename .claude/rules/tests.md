---
paths:
  - "tests/**"
---

# Tests

- Bug corrigé = test dans `tests/regression/` qui échoue avant le correctif et passe après ; commit du fix et du test ensemble.
- Nom `test_regression_<sujet>.py`, docstring en 4 points : symptôme, cause racine, correctif, prévention (modèle : `tests/regression/test_regression_live_coach_lane_filter.py`).
- La fixture de session `_guard_production_untouched` (`tests/conftest.py`) échoue si `data/db.db` ou `logs/*.log` bougent. Une « 1 error » sur le dernier test collecté signifie en général que le Live Coach tourne : comparer les mtimes avant de chercher un bug.
- Les tests n'écrivent jamais dans `data/` ni `logs/` : utiliser les fixtures d'isolation de `conftest.py`.
- Seuil de couverture : celui de `pyproject.toml` (une seule source de vérité).
