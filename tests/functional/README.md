# Tests Fonctionnels - LeagueStats Coach

## 📋 Vue d'Ensemble

Les tests fonctionnels valident que **toutes les fonctionnalités accessibles depuis l'UI fonctionnent correctement** et permettent de détecter les régressions.

## 🎯 Objectifs

- **Non-régression** : Détecter les bugs introduits lors des modifications
- **End-to-End** : Tester le parcours complet utilisateur
- **Validation UI** : S'assurer que toutes les options du menu fonctionnent
- **Intégrité des données** : Vérifier que les résultats sont cohérents

## 📂 Structure

```
tests/functional/
├── README.md                      # Ce fichier
├── conftest.py                    # Fixtures partagées
├── test_champion_analysis.py     # Tests analyse champions (5 tests)
├── test_optimal_team.py           # Tests optimal team builder (4 tests)
└── test_tier_list.py              # Tests tier lists (13 tests)
```

**Note**: Les fichiers suivants sont prévus pour de futures implémentations:
- `test_draft_coach.py` - Tests draft coach en temps réel
- `test_pool_management.py` - Tests gestion pools de champions
- `test_data_updates.py` - Tests parsing/updates de données

## 🧪 Types de Tests

### 1. Tests d'Analyse de Champions

**Fichier** : `test_champion_analysis.py` (5 tests - ✅ 100% pass)

Fonctionnalités testées :
- ✅ Tier list analysis via `tierlist_delta2()`
- ✅ Tri descendant par score
- ✅ Gestion listes vides
- ✅ Validation structure de sortie
- ✅ Non-régression: méthodes existantes et types

### 2. Tests Tier Lists

**Fichier** : `test_tier_list.py` (13 tests - ✅ 100% pass)

Fonctionnalités testées :
- ✅ Génération tier list blind pick (S/A/B/C)
- ✅ Génération tier list counter pick (S/A/B/C)
- ✅ Tri descendant par score
- ✅ Seuils classification tiers (75/50/25 d'après config)
- ✅ Normalisation globale correcte
- ✅ Gestion champions sans scores
- ✅ Gestion listes vides
- ✅ Validation `analysis_type` invalide
- ✅ Consistance entre appels
- ✅ Non-régression: méthodes existantes et signatures

### 3. Tests Optimal Team Builder

**Fichier** : `test_optimal_team.py` (4 tests - ✅ 100% pass)

Fonctionnalités testées :
- ✅ Recommandations de bans retourne liste
- ✅ Non-régression: méthode `get_ban_recommendations()` existe
- ✅ Non-régression: méthode `set_scoring_profile()` existe
- ✅ Non-régression: méthode `find_optimal_trios_holistic()` existe

---

**Tests Planifiés** (futurs):

### Tests Draft Coach (À IMPLÉMENTER)

**Fichier** : `test_draft_coach.py`

Fonctionnalités prévues :
- ⏳ Recommandations en draft réel (simulation)
- ⏳ Gestion bans (ajout/retrait)
- ⏳ Gestion picks allies/ennemis
- ⏳ Analyse finale de composition
- ⏳ Export/import drafts

### Tests Gestion Pools (À IMPLÉMENTER)

**Fichier** : `test_pool_management.py`

Fonctionnalités prévues :
- ⏳ Création pool
- ⏳ Édition pool (ajout/retrait champions)
- ⏳ Duplication pool
- ⏳ Suppression pool
- ⏳ Recherche pools
- ⏳ Statistiques pools

### Tests Mises à Jour Données (À IMPLÉMENTER)

**Fichier** : `test_data_updates.py`

Fonctionnalités prévues :
- ⏳ Recalcul scores globaux
- ⏳ Validation intégrité BD
- ⏳ Parsing champion pool (mock)

## 🔧 Exécution

### Tous les tests fonctionnels
```bash
pytest tests/functional/ -v
```

### Test spécifique
```bash
pytest tests/functional/test_tier_list.py -v
```

### Avec couverture
```bash
pytest tests/functional/ --cov=src --cov-report=html
```

### Mode verbose avec détails
```bash
pytest tests/functional/ -vv -s
```

## 📊 Fixtures Partagées

Définies dans `conftest.py` :

- **`temp_db`** : Base de données temporaire avec données de test
- **`assistant`** : Instance Assistant configurée
- **`sample_champions`** : Liste de champions pour tests
- **`sample_pool`** : Pool de champions pré-configuré
- **`pool_manager`** : Gestionnaire de pools

## ✅ Checklist Validation

Avant chaque release, s'assurer que :

- [ ] Tous les tests fonctionnels passent (100%)
- [ ] Aucune régression détectée
- [ ] Nouveaux tests ajoutés pour nouvelles features
- [ ] Documentation à jour

## 🐛 Détection de Régressions

Les tests fonctionnels détectent :
- ❌ Méthodes manquantes (AttributeError)
- ❌ Changements de signature d'API
- ❌ Résultats incohérents
- ❌ Erreurs de base de données
- ❌ Problèmes d'imports

## 📈 Métriques

| Métrique | Valeur Cible | Actuel |
|----------|--------------|--------|
| Tests fonctionnels | 50+ | **22** (5+4+13) |
| Couverture UI | 80%+ | TBD |
| Temps exécution | <30s | **1.77s** ⚡ |
| Taux succès | 100% | **100%** ✅ |

---

**Dernière mise à jour** : 2025-12-20
**Mainteneur** : Sprint 2 - Code Quality
