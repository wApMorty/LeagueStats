---
name: ship
description: Checklist avant de pousser sur master (Black, pytest complet, CHANGELOG) puis résumé et attente de validation.
disable-model-invocation: true
---

État du dépôt : !`git status --short`

Avant tout push sur master :

1. `python -m black src/ tests/ scripts/` puis `python -m black --check src/ tests/ scripts/`.
2. `python -m pytest tests/ -v` (suite complète, sortie lue en entier). Si seule la dernière ligne est « 1 error », voir `.claude/rules/tests.md` avant de conclure.
3. `CHANGELOG.md` à jour sous `[Unreleased]` ; README.md et docs/ si le comportement change.
4. Compter les entrées de `[Unreleased]` : à 8 ou plus, proposer `/release`.
5. Résumé de 3 à 6 lignes : ce qui change, résultat des tests, questions ouvertes.
6. S'arrêter et attendre la validation explicite de @pj35. Ne pas pousser avant.
