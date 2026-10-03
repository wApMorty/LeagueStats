---
name: implement
description: Implémenter des tâches d'une spec (un commit par tâche, TODO et CHANGELOG à jour, vérification finale), sans jamais pousser.
disable-model-invocation: true
argument-hint: SPEC-NN [tâches a-b]
---

Demande : $ARGUMENTS

État du dépôt : !`git status --short`
Branche : !`git branch --show-current`

1. **Cadrer.** Lire la spec (détail, critères d'acceptation, hors périmètre) et les lignes du `TODO.md` des tâches demandées (sans précision : les tâches ⬜ dont les dépendances sont ✅, dans l'ordre). Si l'arbre de travail n'est pas propre, ou si un arbitrage « à valider » touche ces tâches : s'arrêter et demander.
2. **Par tâche**, dans l'ordre des dépendances :
   - bug : écrire d'abord le test de régression et le voir échouer ;
   - implémenter ce que la spec décrit, rien de plus ; constantes dans `src/config_constants.py` ;
   - tests de la tâche, lancés en ciblé (`python -m pytest tests/test_x.py`) ;
   - cocher ✅ la tâche dans `TODO.md` (avec le résultat chiffré si la spec en demande un) ;
   - commit `✨ Feature: SPEC-NN tâche X, <objet>` (ou 🐛 Fix, ✅ Test, ♻️ Refactor), tâche et son test ensemble.
3. **Fin du lot** : suite complète via l'agent `test-runner`, `python -m black --check src/ tests/ scripts/`, `python -m pylint src/ --fail-under=8.0`. Corriger puis relancer jusqu'au vert.
4. Entrée sous `[Unreleased]` de `CHANGELOG.md`, statut de la spec et table de `docs/specs/README.md` à jour, commit `📝 Docs:`.
5. **Vérification indépendante** : lancer l'agent `spec-verifier` avec le chemin de la spec et le commit de départ (`git rev-parse` pris avant la première tâche). Corriger seulement les écarts de correction ou de critère d'acceptation, pas les préférences de style.
6. Rapporter en 3 à 6 lignes : tâches faites, résultat des tests, écarts restants, recettes en conditions réelles à faire par @pj35 (elles restent ⬜ dans le TODO). **Ne pas pousser** ; `/ship` ensuite.

Autonomie : pour enchaîner sans interruption, @pj35 lance `/goal` avec une condition vérifiable, par exemple :
« Tâches NN à MM de SPEC-XX cochées ✅ dans TODO.md, `pytest tests/` vert (sortie visible), `black --check` propre, un commit par tâche, rien de poussé ; ou stop après 30 tours. » puis `/implement SPEC-XX tâches NN-MM`.
