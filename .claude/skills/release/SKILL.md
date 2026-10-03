---
name: release
description: Publier une version de LeagueStats Coach (numéro SemVer, CHANGELOG, tag, build de l'exe).
disable-model-invocation: true
---

Entrées de `[Unreleased]` : !`awk '/^## \[Unreleased\]/{f=1;next} /^## \[/{f=0} f' CHANGELOG.md`

Quand proposer une release : fin d'une spec ou d'un sprint du `TODO.md` (mineure), `[Unreleased]` à 8 entrées, ou correctifs seuls en attente depuis une semaine (patch).

Numéro SemVer : majeure = fonctionnalité retirée ou action requise de l'utilisateur (migration Alembic, scrape complet) ; mineure = nouvelle fonctionnalité compatible ; patch = corrections seulement.

Étapes :
1. Mettre le numéro dans `src/__init__.py` et `README.md`.
2. `CHANGELOG.md` : renommer `[Unreleased]` en `[X.Y.Z] - AAAA-MM-JJ`, résumé de 2-3 lignes en tête (actions requises comprises), puis rouvrir un `[Unreleased]` vide.
3. Commit `🚀 Deploy: version X.Y.Z`, puis tag annoté `vX.Y.Z`.
4. `python build_app.py`, puis `echo 7 | ./LeagueStatsCoach.exe` dans `LeagueStatsCoach_Release/` pour vérifier qu'il démarre.
5. Résumer à @pj35 et attendre sa validation, puis `git push origin master` et `git push origin vX.Y.Z`.
