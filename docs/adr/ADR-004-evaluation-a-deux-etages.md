# ADR-004 — Évaluer les probabilités et le classement de pick séparément

**Date** : 2026-11-01
**Statut** : Accepté (@pj35). Complète la règle d'adoption de
[SPEC-43](../specs/SPEC-43-force-intrinseque-et-recalibrage.md) §2 pour les termes de classement.

## Contexte

Le gain de Brier servait de verrou à toutes les évolutions du modèle. Or il vaut à peu près le carré
de l'effet d'un terme sur chaque partie : 0,002 demande 4,5 pp d'effet moyen par partie, 0,0001 en
demande 1. Trois repères, mesurés :

- la draft entière vaut ~0,0026 sur 14 650 parties de `crawl.db` ;
- la maîtrise, adoptée avec −2 pts pour Gnar, vaut +0,00008 sur 81 969 parties ;
- le tirage de la blindabilité vaudrait ~0,000014 s'il était entièrement réel, soit de l'ordre de
  150 000 parties pour le voir, alors que `crawl.db` ne garde que le patch en cours.

Le seuil de 0,002 vient de SPEC-33 : c'est le coût de l'or sur la win chance en partie. Il ne dit rien
de la draft. Un test sans puissance ne réfute pas une idée, il ne la voit pas.

## Options étudiées

| Option | Pour | Contre |
|---|---|---|
| **Règle à deux étages** | Juge chaque sortie sur ce qu'elle promet ; débloque les petits termes de classement | Des termes de classement entrent sans preuve de gain |
| Retirer le seuil, garder la preuve de gain | Le plus simple | Les petits termes restent bloqués sur 15 000 parties |

## Décision

**Probabilités affichées** (win chance, jauge, analyse finale, `predictions`) : Brier et calibration,
sans seuil fixe. On adopte si l'intervalle du gain exclut 0, comme SPEC-43 §2.

**Classement de pick** (ordre des cartes, survol) : un terme est adopté si les trois conditions tiennent.

1. **Raison solide** : un mécanisme explicable, pas seulement une corrélation.
2. **Pas de dégradation** : les intervalles à 90 % excluent une perte sensible. Une perte de Brier de
   plus de 0,0005 en borne basse bloque le terme.
3. **Effet chiffré** : part des n° 1 changés et points de winrate en jeu, sur des drafts rejouées de
   @pj35. Le chiffre est consigné, il ne fixe pas de seuil de gain.

On écrit « indétectable » et non « sans gain » quand le gain attendu est hors de portée du test.

## Conséquences

- Un terme de classement ne touche jamais les probabilités calibrées (SPEC-46 sépare déjà les deux).
- Le risque est d'empiler des termes jamais prouvés : chacun garde sa ligne dans la spec ou le CHANGELOG,
  avec son effet chiffré, pour pouvoir le retirer.
- Le terme de forme (+0,0013) et l'a priori de draft (+0,0005) ont été refusés au seuil de 0,002 sur la
  win chance. Ils relèvent du premier étage et peuvent être rejugés sans ce seuil.

## Première application : le tirage (2026-11-01)

La force d'un champion contient les adversaires qu'il rencontre d'habitude.
`WeightedEvaluator.draw_correction` la corrige au seul classement : tout le tirage si le vis-à-vis est
vu, sa partie positive sinon.

1. **Raison** : avec un vis-à-vis vu, le duel recompte ce que la force contient. Non vu, un contre-pick
   perd un gain qu'il ne tirera pas. Ce second cas reste une hypothèse : Riot ne donne pas l'ordre de pick.
2. **Dégradation** : gain de Brier −0,00003, IC 90 % [−0,00007 ; +0,00002] sur 14 650 parties.
   Coefficient −0,6, IC 90 % [−2,1 ; +0,9], du signe attendu.
3. **Effet** : 211 parties de @pj35, pools par poste, calcul immédiat, 844 positions.

| Stratégie | n° 1 changés, vu | n° 1 changés, non vu | Gain moyen d'un changement |
|---|---:|---:|---:|
| Simple | 0 à 0,5 % | 0 % | 0,03 pt |
| Counter | 0,9 % | 0,5 % | 0,01 à 0,07 pt |
| WIN LANE | 0,5 à 4,3 % | 0 % | 0,07 à 0,18 pt |

L'effet est faible parce qu'Olaf domine le pool top et que le terme reste petit : de −0,64 à +0,77 pp au
pire, en top, et le plus souvent sous 0,2 pp.
