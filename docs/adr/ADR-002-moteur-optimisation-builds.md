# ADR-002 — Moteur d'optimisation des builds : shrinkage mesuré, puis correction par les patchs

**Date** : 2026-09-23
**Statut** : Accepté (@pj35)
**Spec liée** : [SPEC-16](../specs/SPEC-16-moteur-optimisation-builds.md)

## Contexte

Trois sources de builds (ADR-001 et discussion du 2026-09-23), qui ne mesurent pas la même chose :

| Source | Mesure | Biais | Variance |
|---|---|---|---|
| OneTricks, popularité | Ce que les experts choisissent | Suivisme de méta | Faible |
| Winrate par matchup | Winrate conditionnel | **Fort** (sélection : on achète défensif *parce qu'on* perd) | Moyenne |
| Coachless, WPA | Effet estimé sur la victoire | Faible | **Forte** (petits échantillons) |

La variance baisse avec le nombre de games, **pas le biais**. Le poids relatif des sources est donc
un compromis biais/variance, qui ne peut s'apprendre sans vérité terrain. Contrainte posée par
@pj35 : **les parties personnelles ne servent ni au calcul ni à la validation** (volume
insuffisant).

## Options étudiées

- **A. Shrinkage hiérarchique** : les candidats viennent de la popularité OneTricks, notés au WPA
  Coachless puis ajustés par un différentiel de matchup. Chaque terme est rétréci vers le niveau
  supérieur, avec des `K` mesurés sur le bruit par la méthode de SPEC-13.
- **A+. A, avec correction temporelle** : les patchs servent d'expériences naturelles. Data Dragon
  indique quels items et champions ont changé. Les items inchangés font office de témoins, les
  items modifiés d'un test de signe (différence de différences), et la popularité à stats
  constantes isole le biais de sélection. Le biais relatif de chaque source devient mesurable.
- **B. Méta-modèle appris sur des parties brutes** (Riot match-v5) : c'est la seule mesure absolue du
  biais, mais elle demande des semaines de collecte (clé dev à 100 requêtes par 2 min, cf. SPEC-13
  §1) et une infrastructure d'ingestion.
- **C. Pondération fixe à la main** : ce sont des constantes devinées, exactement ce que SPEC-08 et
  SPEC-13 ont éliminé.

**Objection retenue (@pj35)** : la stabilité inter-patch *brute* n'est pas un critère de
validation, car les items changent eux-mêmes d'un patch à l'autre. D'où A+ : la stabilité ne vaut
que sur les items et champions **inchangés**, et le changement devient lui-même un signal.

## Décision

**A d'abord, puis A+ une fois l'historique suffisant.** B est écartée tant que A+ n'a pas montré ses
limites. C est rejetée.

## Conséquences

- **Collecter tout de suite, exploiter plus tard.** A+ exige un historique par patch que les
  sources n'exposent a priori pas (patch courant seulement, à confirmer au spike). La photographie
  de chaque patch commence **dès la phase 1 de SPEC-15**, même sans consommateur, car un patch non
  photographié est perdu définitivement. Il faut 8 à 12 transitions exploitables, soit **4 à 6
  mois** à raison d'un patch toutes les deux semaines.
- **Réutilisation** : `confidence()` (`src/analysis/probability.py`) et le MLE de
  `src/analysis/shrink.py`. Aucune dépendance nouvelle (pas de pandas, pas de scipy), dans la
  lignée de SPEC-13.
- **Limite assumée de A** : le biais résiduel du winrate est atténué par le différentiel, pas
  corrigé. A+ est ce qui le corrige.
- **Facteur de confusion connu de A+** : un item inchangé peut bouger parce que les champions qui
  l'achètent ont changé. Les paires (champion, item) dont le champion a été modifié sont donc
  exclues des témoins.
