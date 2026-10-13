---
name: implement
description: Implémenter des tâches d'une spec (un commit par tâche, TODO et CHANGELOG à jour, vérification finale), sans jamais pousser.
disable-model-invocation: true
argument-hint: SPEC-NN [tâches a-b]
---

Demande : $ARGUMENTS

État du dépôt : !`git status --short`
Branche : !`git branch --show-current`

1. **Cadrer.** Lire la spec (détail, critères d'acceptation, hors périmètre) et les lignes du `TODO.md` des tâches demandées (sans précision : les tâches ⬜ dont les dépendances sont ✅, dans l'ordre). Si l'arbre de travail n'est pas propre (hors un éventuel `docs/specs/PLAN-SPEC-NN.md` d'une session précédente : le lire, demander s'il faut le reprendre ou le supprimer), ou si un arbitrage « à valider » touche ces tâches : s'arrêter et demander.
2. **Planifier, puis attendre la validation.** Avant toute délégation, lire le code que les tâches touchent et écrire le plan technique dans un **document** `docs/specs/PLAN-SPEC-NN.md` (jamais commité : les `git add` sont toujours explicites). Contenu :
   - par tâche : approche retenue, fichiers touchés (code et tests), constantes à ajouter, tests prévus ; bug : le test de régression à écrire d'abord ;
   - qui l'exécute : agent `task-implementer` ou le modèle principal (et pourquoi, voir les cas réservés plus bas) ;
   - ordre : vagues, parallèles ou séquentielles, avec le motif quand deux tâches qui pourraient l'être sont mises en séquence ;
   - risques, ambiguïtés de la spec, et si la tâche demande une décision d'architecture non triviale : 2 à 3 approches avec leurs compromis, comme l'exige `CLAUDE.md`.
   Puis **s'arrêter et demander la validation de @pj35** : lien vers le document et résumé de 3 à 6 lignes. Ne lancer aucun agent, ne toucher à aucun autre fichier avant son accord. S'il amende le plan, réécrire le document en entier et redemander.
   Une fois validé, le rendre **en lecture seule** (`attrib +R docs/specs/PLAN-SPEC-NN.md` : `Edit` et `Write` échouent alors dessus). Les agents le lisent, ne le modifient jamais. Seul le modèle principal peut le changer (`attrib -R`, édition, `attrib +R`), et seulement pour consigner une décision prise après un blocage (voir plus bas). Un plan validé ne se rouvre pas, sauf fait nouveau qui remet en cause l'approche : alors s'arrêter et le dire à @pj35.
3. **Par vague de tâches**, selon le plan validé. Une vague = les tâches dont les dépendances sont ✅ ; on les lance **en parallèle** (un appel `Agent` par tâche, tous dans le même message) si et seulement si elles sont sans risque de conflit, sinon en séquence :
   - **Parallélisable** = aucune dépendance entre elles **et** jeux de fichiers disjoints, y compris les fichiers de tests (listés dans le plan). Deux tâches qui touchent le même fichier (souvent `src/config_constants.py`, `tests/conftest.py`, un module partagé) vont dans des vagues séparées. Au moindre doute sur le périmètre, séquentiel. Les tâches faites par soi-même (voir ci-dessous) ne tournent pas pendant une vague.
   - Chaque agent reçoit la liste de ses fichiers et l'interdiction de toucher les autres : un fichier hors liste dans le diff = écart.
   - Même arbre de travail pour toute la vague. Valider et commiter **tâche par tâche** une fois la vague terminée, avec `git add <fichiers de la tâche>` explicite (jamais `git add -A`) : un commit par tâche, jamais de commit par un agent.
   - **Déléguer** à l'agent `task-implementer` (Haiku 5.5) : chemin de la spec, chemin du plan, lettre de la tâche (c'est la section du plan qui fait foi pour l'approche et la liste des fichiers). Il implémente et teste en ciblé, sans commit ni doc. Faire soi-même, sans agent, la tâche qui tranche une décision d'architecture, qui touche la boucle de draft du Live Coach ou une migration Alembic, ou si l'agent a signalé une ambiguïté.
   - **Blocage** : si l'agent rapporte `BLOQUÉ` (le plan ne tient pas face au code, la spec est ambiguë, un fichier hors liste est nécessaire), il s'est arrêté et attend. Les autres agents de la vague continuent. Trancher soi-même si la spec et le plan le permettent, sinon demander à @pj35 ; consigner la décision dans le plan (section « Décisions en cours d'implémentation »), puis relancer l'agent via `SendMessage`. Ne jamais le laisser contourner le plan de lui-même.
   - **Valider sa sortie avant tout commit**, sur pièces et non sur son rapport :
     1. `git status --short` puis `git diff -- <fichiers de la tâche>` : lire tout le diff de la tâche (en vague parallèle, l'arbre contient les changements des autres tâches ; ne les mélanger ni dans la lecture ni dans le commit). Rejeter tout fichier hors périmètre de la tâche, tout test ou doc non demandé, tout changement de `TODO.md`/`CHANGELOG.md`/`docs/`.
     2. Confronter le diff au plan (approche, fichiers) puis à la spec (§4 et critères d'acceptation de la tâche), et vérifier que le plan est intact (toujours en lecture seule, contenu inchangé) : chaque critère est couvert, et chaque comportement nouveau a un test qui échouerait si le comportement était faux (pas seulement un test qui exécute la ligne).
     3. Règles du dépôt : constantes dans `src/config_constants.py`, SQL paramétré, pas d'emoji en console, docstrings et type hints, ajouts du Live Coach best-effort, tests hermétiques.
     4. Relancer soi-même les tests ciblés (`python -m pytest tests/test_x.py`) et lire la sortie. Bug : le test de régression doit avoir été vu rouge avant le fix ; le vérifier en rejouant le test contre le code d'origine (`git stash push -- <fichiers src de la tâche>`, pytest, `git stash pop`), seulement quand plus aucun agent ne tourne.
   - **Écart** : renvoyer à l'agent (`SendMessage`) avec la liste précise des corrections, 2 allers-retours au maximum ; au-delà, reprendre la tâche soi-même. Une tâche en écart ne bloque pas le commit des tâches conformes de la même vague (leurs fichiers sont disjoints).
   - **Conforme** : cocher ✅ la tâche dans `TODO.md` (avec le résultat chiffré si la spec en demande un) et commiter `✨ Feature: SPEC-NN tâche X, <objet>` (ou 🐛 Fix, ✅ Test, ♻️ Refactor), tâche et son test ensemble. Le commit est toujours fait par le modèle principal, jamais par l'agent.
4. **Fin du lot** : suite complète via l'agent `test-runner`, `python -m black --check src/ tests/ scripts/`, `python -m pylint src/ --fail-under=8.0`. Corriger puis relancer jusqu'au vert.
5. Entrée sous `[Unreleased]` de `CHANGELOG.md`, statut de la spec et table de `docs/specs/README.md` à jour, commit `📝 Docs:`.
6. **Vérification indépendante** : lancer l'agent `spec-verifier` avec le chemin de la spec et le commit de départ (`git rev-parse` pris avant la première tâche). Corriger seulement les écarts de correction ou de critère d'acceptation, pas les préférences de style. Une fois l'implémentation validée (suite verte, vérificateur sans écart restant), **supprimer le plan** (`attrib -R` puis `rm docs/specs/PLAN-SPEC-NN.md`) ; il ne figure dans aucun commit. S'il reste un écart ou un arrêt en cours, le garder pour la reprise et le dire dans le rapport.
7. Rapporter en 3 à 6 lignes : tâches faites, résultat des tests, écarts restants, recettes en conditions réelles à faire par @pj35 (elles restent ⬜ dans le TODO). **Ne pas pousser** ; proposer `/release` si la spec est terminée.

Autonomie : la validation du plan (étape 2) est la seule pause prévue, `/goal` ne la remplace pas. Pour enchaîner ensuite sans interruption, @pj35 lance `/goal` avec une condition vérifiable, par exemple :
« Tâches NN à MM de SPEC-XX cochées ✅ dans TODO.md, `pytest tests/` vert (sortie visible), `black --check` propre, un commit par tâche, rien de poussé ; ou stop après 30 tours. » puis `/implement SPEC-XX tâches NN-MM`, et répond « validé » au plan.
