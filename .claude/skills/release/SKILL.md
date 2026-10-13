---
name: release
description: Vérifier puis publier une version de LeagueStats Coach (pytest complet, numéro SemVer, CHANGELOG, tag, build de l'exe, push).
disable-model-invocation: true
---

Entrées de `[Unreleased]` : !`awk '/^## \[/{f=(++n==1)} f' CHANGELOG.md`

Quand proposer une release : fin d'une spec ou d'un sprint du `TODO.md` (mineure), `[Unreleased]` à 8 entrées, ou correctifs seuls en attente depuis une semaine (patch).

Numéro SemVer : majeure = fonctionnalité retirée ou action requise de l'utilisateur (migration Alembic, scrape complet) ; mineure = nouvelle fonctionnalité compatible ; patch = corrections seulement.

Étapes :
0. Suite complète via l'agent `test-runner` (il gère le piège « 1 error » du Live Coach, voir `.claude/rules/tests.md`) ; si elle est rouge, s'arrêter et rapporter. Vérifier que README.md et docs/ suivent les changements de comportement listés dans `[Unreleased]`.
1. Mettre le numéro dans `src/__init__.py` et `README.md`.
2. `CHANGELOG.md` : renommer `[Unreleased]` en `[X.Y.Z] - AAAA-MM-JJ`, résumé de 2-3 lignes en tête (actions requises comprises), puis rouvrir un `[Unreleased]` vide.
3. Commit `🚀 Deploy: version X.Y.Z`, puis tag annoté `vX.Y.Z`.
4. `python build_app.py`, puis `echo 8 | ./LeagueStatsCoach.exe` dans `LeagueStatsCoach_Release/` pour vérifier qu'il démarre (8 = Quitter ; 7 ouvre la fenêtre du client).
5. `git push origin master` puis `git push origin vX.Y.Z`, sans redemander : lancer `/release` vaut validation de @pj35. S'arrêter avant le push seulement si une étape a échoué (tests rouges, exe qui ne démarre pas).
6. Résumer en 3 à 6 lignes : version, résultat des tests, actions requises.
