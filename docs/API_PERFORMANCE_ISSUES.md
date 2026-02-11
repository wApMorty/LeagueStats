# API Performance Issues - Neon + Render Free Tier

**Date**: 2026-02-11
**Severity**: High (endpoints inutilisables)
**Status**: Documenté, à corriger

---

## 🔴 Problème

Les endpoints `/api/champions/{id}/matchups` et `/api/champions/{id}/synergies` timeout systématiquement (60+ secondes) sur le serveur Render en production.

### Tests Effectués

```bash
# Test avec serveur chaud (après déploiement)
GET /api/champions/266/matchups
-> TIMEOUT après 60.04s ❌

GET /api/champions/266/synergies
-> Response: 2.76s ✅ (mais count: 0, données vides)

GET /api/champions/103/matchups
-> TIMEOUT après 60.04s ❌

GET /api/champions
-> Response: 1.72s ✅
```

---

## 📊 Données Impactées

**Base de données Neon (PostgreSQL)** :
- Champions : 172 ✅
- Matchups : 39,931 ✅ (synchronisés mais inaccessibles)
- Synergies : 30,108 ✅ (synchronisés mais inaccessibles)

**Synchronisation** : Fonctionne correctement (`scripts/sync_local_to_neon.py`)

---

## 🔍 Analyse Technique

### 1. Requête SQL Lente

**Fichier** : `server/src/db.py:435-500`

```python
def get_champion_matchups_by_name(self, name: str, as_dataclass: bool = False):
    # ...
    result = await session.execute(
        select(
            Champion.name,
            Matchup.winrate,
            Matchup.games,
            Matchup.delta2,
            Matchup.pickrate,
        )
        .join(Matchup, Matchup.enemy_id == Champion.id)  # ← JOIN sans index
        .where(Matchup.champion_id == champ_id)
        .where(Matchup.pickrate > 0.5)  # ← Filtre restrictif
    )
```

**Problèmes identifiés** :
- ❌ **Pas d'index** sur `matchups.champion_id` et `matchups.enemy_id`
- ❌ **JOIN** sur 39,931 lignes sans index = full table scan
- ❌ **Pas de pagination** (toutes les données en une requête)
- ⚠️ **Filtre pickrate > 0.5** élimine beaucoup de données (synergies count: 0)

### 2. Infrastructure Limitée

**Render Free Tier** :
- CPU : Limité (shared)
- RAM : 512 MB
- Connexions DB : Limitées
- Cold start : 50+ secondes après 15 min d'inactivité

**Neon Free Tier** :
- CPU : 0.25 vCPU (shared)
- Storage : 0.5 GB
- Compute : Suspendu après 5 min d'inactivité

**Résultat** : Les requêtes complexes (JOINs sur 40k lignes) sont trop lentes.

### 3. Code Synchrone Wrappé

```python
def get_champion_matchups_by_name(self, ...):
    async def _get():
        # Requête async
        ...
    return self._run_async(_get())  # ← Overhead asyncio.run()
```

L'overhead de `asyncio.run()` dans `_run_async()` ajoute de la latence.

---

## ✅ Ce Qui Fonctionne

1. **Health Check** (`/health`) : ✅ 1-2s
2. **Champions List** (`/api/champions`) : ✅ 1.72s
3. **Single Champion** (`/api/champions/{id}`) : ✅ < 2s
4. **ADMIN_API_KEY** (`/admin/refresh-db`) : ✅ Fonctionne
5. **Sync Local → Neon** : ✅ Fonctionne (172 champions, 39k matchups, 30k synergies)

---

## 🛠️ Solutions Recommandées

### Solution 1 : Indexes PostgreSQL (Priorité HAUTE)

**Fichier à créer** : `server/alembic/versions/XXXX_add_performance_indexes.py`

```sql
-- Matchups indexes
CREATE INDEX idx_matchups_champion_id ON matchups(champion_id);
CREATE INDEX idx_matchups_enemy_id ON matchups(enemy_id);
CREATE INDEX idx_matchups_pickrate ON matchups(pickrate);

-- Synergies indexes
CREATE INDEX idx_synergies_champion_id ON synergies(champion_id);
CREATE INDEX idx_synergies_ally_id ON synergies(ally_id);
CREATE INDEX idx_synergies_pickrate ON synergies(pickrate);

-- Composite indexes pour les JOINs
CREATE INDEX idx_matchups_champion_pickrate ON matchups(champion_id, pickrate);
CREATE INDEX idx_synergies_champion_pickrate ON synergies(champion_id, pickrate);
```

**Impact estimé** : Requêtes 10-100x plus rapides

---

### Solution 2 : Pagination (Priorité HAUTE)

**Fichier** : `server/src/api/routes/matchups.py`

```python
@router.get("/champions/{champion_id}/matchups")
def get_champion_matchups(
    champion_id: int,
    limit: int = 50,  # ← Ajouter pagination
    offset: int = 0,
    db: Database = Depends(get_db)
):
    # Ajouter .limit(limit).offset(offset) à la requête
    ...
```

**Avantages** :
- Réduit la charge mémoire
- Permet de charger progressivement (lazy loading)
- Compatible avec infinite scroll côté frontend

---

### Solution 3 : Relâcher Filtre Pickrate (Priorité MOYENNE)

**Problème actuel** : `pickrate > 0.5` élimine trop de données

**Options** :
1. Baisser le seuil : `pickrate > 0.1` (10%)
2. Rendre le filtre optionnel : `?min_pickrate=0.5`
3. Supprimer le filtre et laisser le frontend filtrer

**Fichier** : `server/src/db.py:469` et `server/src/db.py:533`

---

### Solution 4 : Caching (Priorité BASSE)

**Option A : Redis** (nécessite service externe)
```python
from fastapi_cache import FastAPICache
from fastapi_cache.backends.redis import RedisBackend

@cache(expire=3600)  # 1 heure
async def get_champion_matchups(...):
    ...
```

**Option B : In-Memory** (simple mais limité)
```python
from functools import lru_cache

@lru_cache(maxsize=200)
def get_champion_matchups_cached(champion_id: int):
    ...
```

**Avantages** :
- Réduit les requêtes DB
- Améliore les temps de réponse pour les champions populaires

**Inconvénients** :
- Complexité accrue
- Redis = coût supplémentaire sur Render

---

### Solution 5 : Upgrade Infrastructure (Priorité BASSE)

**Render** :
- Starter Plan : $7/mois (1 GB RAM, CPU dédié)
- Impact : Meilleure performance CPU/RAM

**Neon** :
- Scale Plan : $19/mois (1 vCPU, 4 GB storage, pas de suspension)
- Impact : DB toujours active, meilleure performance

**Total** : ~$26/mois

---

## 📝 Plan d'Action Recommandé

### Phase 1 : Quick Wins (1-2 heures)

1. ✅ **Créer migration Alembic** avec indexes
2. ✅ **Ajouter pagination** aux endpoints matchups/synergies
3. ✅ **Relâcher filtre pickrate** à 0.1 ou optionnel
4. ✅ **Tester** avec Postman/curl

**Résultat attendu** : Endpoints fonctionnels en < 5s

---

### Phase 2 : Optimisations (2-3 heures)

1. Ajouter caching in-memory avec `lru_cache`
2. Optimiser requêtes SQL avec `EXPLAIN ANALYZE`
3. Ajouter monitoring (temps de réponse par endpoint)
4. Documenter dans OpenAPI les limites de pagination

---

### Phase 3 : Infrastructure (optionnel)

1. Évaluer si upgrade Render/Neon nécessaire
2. Mettre en place Redis si traffic élevé
3. Ajouter CDN pour assets statiques

---

## 🧪 Tests de Validation

Après corrections, vérifier :

```bash
# Test 1 : Matchups avec pagination
curl "https://leaguestats-adf4.onrender.com/api/champions/266/matchups?limit=50"
# Attendu : < 3s, 50 résultats

# Test 2 : Synergies complètes
curl "https://leaguestats-adf4.onrender.com/api/champions/266/synergies"
# Attendu : < 3s, 150+ résultats

# Test 3 : Bulk matchups (cache warm-up)
curl "https://leaguestats-adf4.onrender.com/api/matchups/bulk"
# Attendu : < 30s pour 172 champions

# Test 4 : Performance après indexes
# Utiliser EXPLAIN ANALYZE dans Neon console
```

---

## 📚 Références

**Fichiers impactés** :
- `server/src/db.py` : Requêtes SQL (lignes 435-550)
- `server/src/api/routes/matchups.py` : Endpoints matchups
- `server/src/api/routes/synergies.py` : Endpoints synergies
- `server/alembic/versions/` : Migrations à créer

**Documentation** :
- PostgreSQL Indexes : https://www.postgresql.org/docs/current/indexes.html
- FastAPI Pagination : https://fastapi.tiangolo.com/tutorial/query-params/
- Neon Performance : https://neon.tech/docs/guides/performance-tuning

---

## 📊 Métriques Actuelles vs Cibles

| Endpoint | Actuel | Cible | Amélioration |
|----------|--------|-------|--------------|
| `/champions` | 1.72s | < 2s | ✅ OK |
| `/champions/{id}` | < 2s | < 2s | ✅ OK |
| `/champions/{id}/matchups` | 60s+ (timeout) | < 3s | 🔴 CRITIQUE |
| `/champions/{id}/synergies` | 2.76s (count:0) | < 3s (150+ results) | 🔴 CRITIQUE |
| `/matchups/bulk` | Non testé | < 30s | ⚠️ À tester |

---

## 👤 Mainteneur

**Dernière mise à jour** : 2026-02-11
**Auteur** : Claude Sonnet 4.5
**Tests effectués par** : @pj35

**Statut** : Documenté, prêt pour implémentation
**Priorité** : Haute (endpoints critiques non fonctionnels)
