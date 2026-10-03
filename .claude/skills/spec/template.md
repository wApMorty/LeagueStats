# SPEC-NN — Titre court

**Statut** : 🟡 Rédigée le AAAA-MM-JJ, arbitrages « à valider » en §2.

**Origine** : @pj35, AAAA-MM-JJ — citation ou reformulation du besoin.

**Effort** : ~N jours, N tâches (§5).

---

## 1. Constat

Ce qui est vrai aujourd'hui, **mesuré** (requête sur la base, bench, lecture de code avec chemin:ligne),
avec la date de la mesure. Aucune affirmation sans source.

## 2. Objectif et arbitrages

Une phrase d'objectif, puis :

| Sujet | Décision |
|---|---|
| ... | **Validé (@pj35, AAAA-MM-JJ)** : ... ou **À valider** : ... |

## 3. Approches considérées

2 à 3 approches avec compromis ; l'approche retenue et pourquoi.

## 4. Détail

Fichiers créés ou modifiés (chemins), interfaces (signatures), constantes à ajouter dans
`src/config_constants.py` (avec l'origine de chaque valeur), migrations Alembic, tests à écrire.
Assez précis pour qu'un agent sans contexte implémente sans deviner.

## 5. Tâches

Numéros globaux : à la suite de la dernière tâche du `TODO.md`. 1 pt ≈ 1 h, 3 ≈ demi-journée, 5 ≈ journée, 8+ à redécouper.

| # | Tâche | Pts | Dépend de |
|---|---|---|---|
| NN | ... | 3 | — |

## 6. Critères d'acceptation

Numérotés, chacun vérifiable par une commande ou une lecture.

1. `python -m pytest tests/ -v` vert, avec les tests des tâches ci-dessus.
2. ...
N. `CHANGELOG.md` (`[Unreleased]`), statut de cette spec et `docs/specs/README.md` à jour.

**Vérification de bout en bout** : la commande ou le scénario réel qui prouve que la fonctionnalité marche.

## 7. Hors périmètre

- ❌ Ce qui est écarté, et pourquoi.
