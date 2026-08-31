# SPEC-03 — Lecture lane-aware : unifier l'agrégation et filtrer par lane

**Items** : B1, B2, B8 · **Priorité** : 3 · **Effort estimé** : ~2 jours
**Constats d'audit** : M1, M2, F5 (`docs/AUDIT_2026_08.md` §4)
**Prérequis** : aucun · **Bloque** : SPEC-04 (inférence des rôles)

---

## 1. Contexte

La colonne `lane` existe sur `matchups` et `synergies` depuis la migration `b7e41c9a3f02` (juin 2026). Elle est renseignée sur **100 % des lignes** (0 ligne `lane IS NULL`), quatre index composites l'accompagnent, et le pipeline la tague correctement.

**Elle n'est lue nulle part.** Recherche exhaustive : `lane` n'apparaît dans aucun fichier de `src/analysis/`, ni dans `src/draft_monitor.py`, ni dans `src/assistant.py`, ni dans l'UI. Seuls le pipeline d'écriture, les index et `src/pool_manager.py` (pools système) l'utilisent.

### Ce que ça coûte, mesuré sur la base réelle

Écart de `delta2` entre lanes, pour un **même** matchup :

```
Ivern vs Aphelios          23,9 pts
Quinn vs Belveth           23,0
Heimerdinger vs Yasuo      22,9
Rammus vs MissFortune      18,6
```

Et par champion (moyenne pondérée par lane) :

| Champion | Lanes |
|---|---|
| Pantheon | top **+0,303** · jungle +0,050 · support **−0,081** |
| Yasuo | bottom +0,170 · middle +0,140 · top **−0,033** |
| Seraphine | bottom **+0,079** · support **−0,100** |

Quand le coach recommande Pantheon, il ne distingue pas le Pantheon top du Pantheon support.

### Deux chemins de lecture incohérents

| Fonction | Traitement du multi-lane | Utilisée par |
|---|---|---|
| `db.get_matchup_delta2()` (`src/db.py:799`) | moyenne pondérée par `games`, en Python | `ChampionScorer.score_against_team` |
| `db.get_all_matchups_bulk()` (`src/db.py:847`) | **écrasement** : `cache[(champ, enemy)] = delta2`, dernière ligne SQL gagnante | trio holistique, cache d'`Assistant`, `warm_cache` |
| `db.get_champion_matchups_by_name()` (`src/db.py:292`) | **aucun** : renvoie toutes les lignes, doublons de lane compris | tier lists, `calculate_global_scores`, scoring |

Mesure : 26 398 lignes en base → **15 699 entrées** dans le cache bulk. **10 699 valeurs jetées silencieusement**, la survivante dépendant de l'ordre de parcours SQL. Le même matchup peut donc être noté différemment selon le chemin de code emprunté.

Et pour `get_champion_matchups_by_name` : Swain renvoie **376 lignes pour 99 adversaires distincts** — le scoring voit quatre fois chaque adversaire, sur quatre lanes mélangées.

### Doublons en base

Sans contrainte d'unicité, on compte aujourd'hui **1 263** triplets `(champion, enemy, lane)` en double et **783** côté synergies, avec des valeurs contradictoires (`Annie vs Lux` en support : `delta2 = −9,25 / 67 parties` **et** `+4,61 / 72 parties`). Origine : superposition des runs de `scripts/repair_data.py` avec le run principal.

---

## 2. Objectif

1. **Une seule** politique d'agrégation multi-lane, appliquée partout.
2. Tous les accesseurs de lecture acceptent une lane optionnelle et filtrent dessus.
3. Le scoring propage la lane de bout en bout, avec repli propre quand elle est inconnue.
4. Les doublons ne peuvent plus se créer.

---

## 3. Travail à faire

### B1 — Unifier l'agrégation (à faire en premier)

Créer `src/analysis/aggregation.py` (nouveau module, < 120 lignes) exposant la politique unique :

```python
def aggregate_rows(rows: Iterable[tuple]) -> dict:
    """Agrège des lignes multi-lane en une valeur par paire de champions.

    rows: (peer_name, delta2, pickrate, games) — la sortie des requêtes de db.py
    Retour: {peer_name_lower: AggregatedMatchup(delta2, pickrate, games)}

    Politique (unique dans tout le projet) :
      - delta2 : moyenne pondérée par games   -> sum(d*g) / sum(g)
      - games  : somme
      - pickrate : somme (part totale de rencontres, toutes lanes du champion)
    """
```

Justification des trois règles, à conserver en docstring :
- `delta2` pondéré par `games` = la valeur la mieux estimée est celle qui repose sur le plus de parties (c'est déjà ce que fait `get_matchup_delta2`, on généralise) ;
- `games` sommés = volume total observé, utile pour la confiance (voir SPEC-05) ;
- `pickrate` sommé = fréquence totale de rencontre de cet adversaire, ce qui préserve le rôle de prédiction du pick adverse (cf. audit M3).

Puis **remplacer** les trois traitements divergents :

- `get_matchup_delta2` : appeler `aggregate_rows` au lieu de son agrégation locale (comportement inchangé, code mutualisé).
- `get_all_matchups_bulk` / `get_all_synergies_bulk` : **agréger** au lieu d'écraser. Le dictionnaire retourné garde exactement la même forme `{(champion_lower, enemy_lower): delta2}` — seule la valeur change (elle devient la moyenne pondérée au lieu d'une ligne arbitraire). Aucun appelant à modifier.
- `get_champion_matchups_by_name` et `get_champion_matchups_for_draft` : agréger par adversaire avant de construire les dataclasses `Matchup` / `MatchupDraft`.

> ⚠️ **Effet attendu sur les résultats** : les scores vont bouger (légèrement en moyenne — écart mesuré de 0,004 à 0,029 sur `avg_delta2` — mais franchement pour les champions multi-lane). C'est une **correction**, pas une régression. Les tests dont les valeurs attendues changent doivent être mis à jour avec un commentaire expliquant pourquoi, et non « ajustés » silencieusement.

### B2 — Filtrage par lane

Ajouter un paramètre `lane: Optional[str] = None` aux accesseurs de `src/db.py` :

| Méthode | Ligne | Comportement avec `lane` |
|---|---|---|
| `get_champion_matchups_by_name` | 292 | `AND m.lane = ?` |
| `get_champion_matchups_for_draft` | 556 | `AND m.lane = ?` |
| `get_reverse_matchups_for_draft` | 620 | `AND m.lane = ?` |
| `get_champion_synergies_by_name` | 937 | `AND s.lane = ?` |
| `get_matchup_delta2` | 799 | `AND m.lane = ?` |
| `get_synergy_delta2` | 1046 | `AND s.lane = ?` |
| `get_all_matchups_bulk` | 847 | clé étendue (voir ci-dessous) |
| `get_all_synergies_bulk` | 1085 | idem |

`lane=None` conserve **exactement** le comportement post-B1 (agrégation toutes lanes) : aucun appelant existant ne casse.

**Sémantique de la lane pour un matchup** : une ligne `matchups(champion=A, enemy=B, lane=top)` signifie « A joué en top, affrontant B ». La lane est celle de **A**. Pour un affrontement direct (A top vs B top) c'est aussi celle de B, mais pour un croisement (A top vs B jungle) la base ne modélise que le point de vue de A. Ne pas chercher à modéliser le couple de lanes : LoLalytics ne le fournit pas.

**Pour les bulk**, deux options — retenir la (b) :

- (a) ~~ajouter la lane à la clé~~ → change la forme du dict, casse tous les appelants ;
- (b) **paramètre `lane` optionnel qui filtre avant agrégation**, clé inchangée. Un cache par lane devient alors un dict par lane côté appelant, ce qui est le besoin réel de SPEC-04.

Propager ensuite dans `src/analysis/scoring.py` :

```python
def score_against_team(self, matchups, team, champion_name=None,
                       banned_champions=None, lane: Optional[str] = None) -> float:
```

- le `lane` sert aux **requêtes inverses internes** (`self.db.get_matchup_delta2(enemy, champion_name)`) — c'est là qu'il change les résultats ;
- `calculate_synergy_bonus(champion_name, ally_names, lane=None)` de même ;
- `filter_valid_matchups`, `avg_delta2`, `avg_delta1`, `avg_winrate` n'ont **pas** besoin du paramètre : elles reçoivent déjà une liste filtrée par l'appelant.

Et dans `src/draft_monitor.py` : `_calculate_score_against_team` et `_calculate_synergy_score` acceptent une lane optionnelle, transmise telle quelle. **Ne pas** y implémenter la détection de lane — c'est SPEC-04. Ici, la lane arrive de l'extérieur ou vaut `None`.

**Vérification manuelle attendue** : avec un pool contenant Pantheon, lancer le scoring avec `lane="top"` puis `lane="support"` et constater que les scores diffèrent dans le sens des données (+0,30 vs −0,08).

### B8 — Contrainte d'unicité

Migration Alembic (`python -m alembic revision -m "unique matchup and synergy per lane"`) :

1. **Dédoublonner** avant de créer la contrainte — garder, pour chaque triplet, la ligne au plus grand `games` :

```sql
DELETE FROM matchups WHERE id NOT IN (
    SELECT id FROM (
        SELECT id, ROW_NUMBER() OVER (
            PARTITION BY champion, enemy, lane ORDER BY games DESC, id DESC
        ) AS rn FROM matchups
    ) WHERE rn = 1
);
```

Idem pour `synergies` avec `(champion, ally, lane)`.

2. Créer `CREATE UNIQUE INDEX idx_matchups_unique ON matchups(champion, enemy, lane)` et son équivalent synergies.
3. `downgrade()` : supprimer les index uniques (le dédoublonnage n'est pas réversible — le documenter dans la docstring de la migration).

Puis rendre les insertions idempotentes dans `src/db.py` :

```sql
INSERT INTO matchups (champion, enemy, winrate, delta1, delta2, pickrate, games, lane)
VALUES (?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT(champion, enemy, lane) DO UPDATE SET
    winrate=excluded.winrate, delta1=excluded.delta1, delta2=excluded.delta2,
    pickrate=excluded.pickrate, games=excluded.games
```

dans `add_matchups_batch` (l. 690) et `add_synergies_batch` (l. 990).

**Attention à `lane = NULL`** : en SQLite, `NULL` n'est jamais égal à `NULL`, donc un index unique ne contraint pas les lignes non taguées et `ON CONFLICT` ne s'y déclenche pas. La base actuelle n'a aucune ligne `NULL`, mais le repli « découverte de lane en échec » de `src/multilane.py:37-39` peut en produire. **Choisir et documenter** : soit interdire `NULL` en écrivant la chaîne `"default"`, soit accepter que les lignes non taguées échappent à la contrainte. La première option est plus sûre — si elle est retenue, prévoir la mise à jour de `group_champions_by_lane` et le remplacement de la valeur en base.

---

## 4. Critères d'acceptation

- [ ] `get_all_matchups_bulk()` renvoie une valeur agrégée : sur la base réelle, `db.get_all_matchups_bulk()[("annie","lux")]` égale la moyenne pondérée par `games` de toutes les lignes correspondantes, et non l'une d'elles.
- [ ] `get_matchup_delta2(a, b)` et `get_all_matchups_bulk()[(a, b)]` donnent **la même valeur** pour toute paire (c'est le test central de B1).
- [ ] `get_champion_matchups_by_name("Swain")` renvoie **99 entrées** (adversaires distincts) et non 376.
- [x] `get_champion_matchups_by_name("Swain", lane="middle")` renvoie les seules données middle.
- [x] Une lane inexistante (`lane="jungle"` pour un champion qui n'y est pas joué) renvoie une liste vide, sans exception.
- [x] `score_against_team(..., lane="top")` et `score_against_team(..., lane="support")` diffèrent pour Pantheon, dans le sens des données.
- [ ] Après migration : 0 triplet `(champion, enemy, lane)` en double ; un second run de scrape ne crée pas de doublon (il met à jour).
- [ ] `pytest tests/ -v` : 0 échec — y compris les tests de régression multi-lane existants (`tests/test_matchup_delta2_multilane.py`, `tests/regression/test_regression_get_synergy_delta2.py`, `tests/test_regression_synergies.py`).

---

## 5. Tests exigés

| Fichier | Contenu |
|---|---|
| `tests/test_aggregation.py` (nouveau) | `aggregate_rows` : moyenne pondérée correcte, `games` sommés, cas une seule ligne, cas `games=0`, liste vide |
| `tests/test_db_lane_filter.py` (nouveau) | Chaque accesseur avec/sans `lane` sur une base temporaire à 3 lanes ; lane inexistante → vide ; `lane=None` = agrégation |
| `tests/regression/test_regression_bulk_vs_unitaire.py` (nouveau) | **Le test central** : pour toutes les paires d'une base à 3 lanes, `get_matchup_delta2` == `get_all_matchups_bulk()[clé]`. C'est l'incohérence M2 qui ne doit jamais revenir |
| `tests/test_scoring.py` (étendu) | `score_against_team` avec `lane` : filtre bien, `lane=None` inchangé |
| `tests/test_db_dataclass_migration.py` (existant) | Vérifier que les dataclasses restent construites correctement après agrégation |
| `tests/test_migration_unique_lane.py` (nouveau) | Migration : base avec doublons → dédoublonnée, ligne au plus grand `games` conservée ; double insertion → update, pas de doublon |

---

## 6. Pièges connus

- **Ne pas casser la forme des retours.** `get_champion_matchups_by_name(as_dataclass=False)` renvoie des tuples à 6 colonnes, `get_champion_matchups_for_draft` des tuples à 4. Ces formats sont consommés par du code legacy et par les tests. L'agrégation change les *valeurs*, jamais la *forme*.
- **`COLLATE NOCASE`** est présent dans `get_matchup_delta2` et empêche l'usage des index (6,3 ms/appel mesurés). Sa suppression est traitée par C4 (SPEC-06) — ne pas la faire ici, mais ne pas l'étendre non plus aux nouvelles requêtes : normaliser les noms côté Python.
- **Le cache d'`Assistant`** (`warm_cache`, `get_cached_matchups`, `get_cached_matchup_delta2`, `src/assistant.py:91-245`) est bidirectionnel et alimenté par les bulk. Si un cache par lane devient nécessaire, la clé de cache doit inclure la lane — sinon un premier appel `lane="top"` empoisonnerait un appel ultérieur `lane=None`. **Vérifier explicitement ce point**, c'est le bug le plus probable de cette spec.
- **`analysis_config.MIN_GAMES_THRESHOLD = 2000`** est comparé à `sum(m.games)` dans `TierListGenerator` (`src/analysis/tier_list.py:47`, `:64`). Après agrégation, cette somme **baisse mécaniquement** pour les champions multi-lane (les doublons ne sont plus comptés plusieurs fois). Vérifier qu'aucun champion légitime ne tombe sous le seuil ; si c'est le cas, recalibrer la constante et le documenter.
- **`src/db.py` fait déjà 1 409 lignes** : ne pas l'alourdir. Toute logique d'agrégation va dans `src/analysis/aggregation.py`, `db.py` ne fait qu'appeler.

---

## 7. Hors périmètre

- Détecter automatiquement la lane du joueur ou des adversaires → **SPEC-04**.
- Afficher la lane dans les recommandations → **SPEC-04** (B5).
- Modifier la formule de score, la conversion `delta2 → %` ou la pondération par confiance → **SPEC-05**.
- Retirer `COLLATE NOCASE` → SPEC-06 (C4).
