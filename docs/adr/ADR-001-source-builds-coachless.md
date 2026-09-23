# ADR-001 — Coachless comme source des runes, items et sorts

**Date** : 2026-09-23
**Statut** : Accepté (@pj35)
**Spec liée** : [SPEC-15](../specs/SPEC-15-import-runes-items.md)

## Contexte

Le Live Coach doit pousser runes, items et sorts d'invocateur dans le client au lock-in, puis, à
terme, les optimiser lui-même (SPEC-15). Il lui faut une source de données de builds.

## Options étudiées

| Option | Pour | Contre |
|---|---|---|
| **Coachless** (coachless.gg) | Classement par **WPA** (impact sur la victoire), la meilleure qualité statistique ; « situational WPA » annoncé, ce qui peut servir de matière à une optimisation maison | SPA : aucune donnée dans le HTML, API JSON non documentée à rétro-ingénierer ; site d'un seul mainteneur, qui peut casser sans préavis |
| OneTricks.gg | Builds de joueurs experts ; la page est déjà ouverte en fin de draft (`src/draft/onetricks.py`) | HTTP 429 sur toute requête automatisée (constaté le 2026-09-23) : c'est la source la plus hostile |
| LoLalytics | Déjà scrapé (Selenium, runbook, tier Master+), builds par matchup disponibles | Classement par winrate brut, biaisé par la sélection (les builds de situation perdante semblent mauvaises) |

## Décision

**Coachless.** Le WPA est la seule des trois métriques qui corrige le biais de sélection du winrate
brut, et c'est la seule source qui pourrait nourrir l'optimisation maison voulue en phase 2.

## Conséquences

- **Dépendance non contractuelle** : l'API peut changer ou fermer. Le client Coachless est isolé
  dans un seul module, et toute panne se traduit par « pas d'import » avec un `[INFO]`, jamais par
  une exception dans la boucle de draft.
- **Service payant et authentifié** : l'outil utilise le compte personnel de @pj35. Le jeton
  reste hors du dépôt (variable d'environnement). Un accès scripté à un compte payant peut
  contrevenir aux CGU de Coachless et exposer le compte à une suspension : c'est un risque
  accepté en connaissance de cause, à vérifier dans les CGU pendant le spike.
- **Usage sobre** : une requête par lock-in, un seul utilisateur, avec un cache mémoire par
  (champion, lane, patch). C'est un volume comparable à une consultation manuelle du site.
- **Faisabilité non prouvée** : un spike (SPEC-15, phase 0) doit confirmer l'API avant toute
  implémentation. Si le spike échoue, on rouvre cet ADR avec LoLalytics comme repli, car
  l'infrastructure de scraping existe déjà.
