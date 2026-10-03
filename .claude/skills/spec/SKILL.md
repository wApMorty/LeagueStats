---
name: spec
description: Rédiger une spec d'implémentation (interview, gabarit, découpage en tâches) et mettre à jour TODO.md.
disable-model-invocation: true
effort: high
argument-hint: <sujet de la spec>
---

Sujet : $ARGUMENTS

Specs existantes : !`ls docs/specs`
Dernière tâche du TODO : !`grep -ohE "tâches? [0-9]+b?( (à|et) [0-9]+b?)*" TODO.md docs/specs/*.md | grep -oE '[0-9]+' | sort -n | tail -1`

1. **Lire avant d'écrire** : `TODO.md`, `docs/specs/README.md`, `docs/ROADMAP_2026.md` (décisions tranchées), puis le code que le sujet touche. Un constat se vérifie sur le code ou la base (`sqlite3`, bench), il ne se déduit pas.
2. **Interview** avec `AskUserQuestion` : les points difficiles, les cas limites, les compromis. Pas de questions dont la réponse est dans le code ou le TODO. Continuer jusqu'à ce que chaque arbitrage soit tranché ou marqué « à valider ».
3. **Rédiger** `docs/specs/SPEC-NN-<slug>.md` (NN = numéro suivant) selon `.claude/skills/spec/template.md`. Les critères d'acceptation sont numérotés et vérifiables par commande. Les tâches continuent la numérotation globale du TODO.
4. **Mettre à jour** `TODO.md` (section du lot, tableau de tâches avec points Fibonacci, dépendances) et la table de `docs/specs/README.md`.
5. Commit `📝 Docs: SPEC-NN <titre>`. Résumer en 3 à 6 lignes (objectif, découpage, arbitrages « à valider ») et attendre la validation de @pj35 avant `/implement`. N'implémenter aucun code.
