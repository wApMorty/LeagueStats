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
├── test_champion_analysis.py     # Tests analyse champions
├── test_draft_coach.py            # Tests draft coach
├── test_optimal_team.py           # Tests optimal team builder
├── test_tier_list.py              # Tests tier lists
├── test_pool_management.py        # Tests gestion pools
└── test_data_updates.py           # Tests parsing/updates
```

## 🧪 Types de Tests

### 1. Tests d'Analyse de Champions

**Fichier** : `test_champion_analysis.py`

Fonctionnalités testées :
- ✅ Analyse blind pick pour un champion
- ✅ Analyse contre équipe adverse
- ✅ Recherche optimal duo pour un champion
- ✅ Validation cohérence des scores

### 2. Tests Draft Coach

**Fichier** : `test_draft_coach.py`

Fonctionnalités testées :
- ✅ Recommandations en draft réel (simulation)
- ✅ Gestion bans (ajout/retrait)
- ✅ Gestion picks allies/ennemis
- ✅ Analyse finale de composition
- ✅ Export/import drafts

### 3. Tests Optimal Team Builder

**Fichier** : `test_optimal_team.py`

Fonctionnalités testées :
- ✅ Recherche optimal trio
- ✅ Différents profils (balanced, aggressive, defensive)
- ✅ Recommandations de bans
- ✅ Validation coverage des rôles

### 4. Tests Tier Lists

**Fichier** : `test_tier_list.py`

Fonctionnalités testées :
- ✅ Génération tier list blind pick
- ✅ Génération tier list counter pick
- ✅ Classification S/A/B/C cohérente
- ✅ Normalisation globale correcte

### 5. Tests Gestion Pools

**Fichier** : `test_pool_management.py`

Fonctionnalités testées :
- ✅ Création pool
- ✅ Édition pool (ajout/retrait champions)
- ✅ Duplication pool
- ✅ Suppression pool
- ✅ Recherche pools
- ✅ Statistiques pools

### 6. Tests Mises à Jour Données

**Fichier** : `test_data_updates.py`

Fonctionnalités testées :
- ✅ Recalcul scores globaux
- ✅ Validation intégrité BD
- ✅ Parsing champion pool (mock)

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
| Tests fonctionnels | 50+ | TBD |
| Couverture UI | 80%+ | TBD |
| Temps exécution | <30s | TBD |
| Taux succès | 100% | TBD |

---

**Dernière mise à jour** : 2025-12-20
**Mainteneur** : Sprint 2 - Code Quality
