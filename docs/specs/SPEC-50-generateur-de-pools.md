# SPEC-50 — Générateur de pools sur l'écran Suggestions

**Statut** : 🟡 Rédigée le 2026-11-06, arbitrages validés par @pj35 le même jour (§2). Dépend du seuil
`BLINDABILITY_MIN_GAMES` à 15 000 (modifié le 2026-11-06, à commiter avant la tâche 246).

**Origine** : @pj35, 2026-11-06 — « J'aimerais qu'on automatise cette méthode pour la génération de pools […]
Comme ça je pourrais réviser mes pools à chaque patch, et sur d'autres lanes que le Top. » La méthode est celle
qui a donné QUINTET TOP le même jour : ordre de pick tiré des matrices Blindabilité, blind exposé au counter,
counter en dernier pick, champions exclus parce que « trop durs à jouer », moyenne sur plusieurs scrapes.

**Effort** : ~2 jours, 6 tâches, 16 pts (§5).

---

## 1. Constat

### 1.1 Ce que fait l'écran Suggestions (SPEC-49)

`src/analysis/pool_swipe.py:41` note un pool par `pool_score = ½ · counter_value + ½ · max force`. La part blind
est la force du meilleur champion du pool (`_blind`, `pool_swipe.py:31`) : elle ignore les counters qu'il subit
quand il est pické à l'aveugle, et le tirage qui gonfle sa force. `swap_cards` (`pool_swipe.py:72`) ne propose que
des échanges un pour un sur le pool désigné au poste ; rien ne construit un pool de zéro.

`PoolEvaluator` (`src/analysis/pool_value.py:26`) donne `value(c, e) = force(c) + duel(c, e)` ; il sert aussi aux
bans (`ban_recommendations.py:50`), à la tier list (`tier_list.py:77`) et au trio (`trio_counterpick.py:48`).

### 1.2 Pourquoi ½ blind, ½ counter vaut pour chaque poste

Minimax du 2026-11-06 sur les matrices Blindabilité (`compute_blindability`, base du 1er nov.), séquence
B R R B B R R B B R sans bans, gain d'un pick = écart-type combiné des cases déjà connues : blue joue jungle, puis
mid et bot, puis top et support ; red joue jungle et mid, puis bot, support et top en dernier. Chaque poste est
pické à l'aveugle d'un côté et en counter de l'autre (top : blind chez blue, counter en R5 ; mid : l'inverse).
En solo queue, la place de pick est imposée par le lobby : blind et counter restent à peu près aussi probables.
D'où s = ½ partout.

### 1.3 La méthode, mesurée

Scripts du 2026-11-06 (jetés), vrai `PoolEvaluator`, tirages de `draw_shifts` au seuil de 15 000 parties :

- `value'(c, e) = force(c) − tirage(c) + duel(c, e)` ;
- `blind(c) = force(c) − tirage(c) + E[min des duels de c sur 7 adversaires tirés selon la popularité]` ;
- `J(P) = ½ · Σ_e popularité(e) · max_{c∈P} value'(c, e) + ½ · max_{c∈P} blind(c)` ;
- candidats : popularité ≥ 1 % (`POOL_SWIPE_MIN_POPULARITY`).

| Poste, scrape du 1er nov. | Candidats | Pool optimal de 5 | J |
|---|---|---|---|
| Top | 39 | Gangplank, Malphite, Riven, Shen, Urgot | +1,661 |
| Jungle | 36 | Elise, MasterYi, Nidalee, Nunu, Shaco | +2,185 |
| Mid | 35 | Ahri, Katarina, Lissandra, Vex, Zoe | +2,178 |
| Bot | 25 | KogMaw, Sivir, Twitch, Xayah, Yasuo | +2,787 |
| Support | 26 | Alistar, Blitzcrank, Braum, Rell, Thresh | +2,578 |

Une recherche gloutonne (ajout du meilleur champion cinq fois) suivie d'échanges un pour un tant que J monte
trouve le même optimum que l'énumération exhaustive (numpy) sur les cinq postes, en moins de 0,05 s par poste en
Python pur. numpy n'est ni dans `requirements.txt` ni importé par `src/` : il n'apporterait rien ici.

Au top, Gangplank et Fiora exclus, J moyen sur les scrapes du 1er nov., du 20 oct. et du 6 oct. (candidats
communs aux trois, 36) : Malphite, Pantheon, Riven, Shen, Urgot, +1,52 (+1,56 / +1,46 / +1,53). Les 8 premiers
pools tiennent en 0,01 pt : seul le noyau (Urgot, Shen, Malphite) est stable.

### 1.4 Les sauvegardes comme historique

`backup_database` (`src/db_backup.py:35`) copie la base avant chaque scrape ; `BACKUP_RETENTION` = 3
(`config_constants.py:645`). Le 2026-11-06, `data/` contient trois sauvegardes, mais celles du 30 oct. et du
1er nov. portent le même scrape (`db_meta.last_scrape_utc` = 2026-10-20T08:34:16) : un run interrompu. La base et
les sauvegardes donnent donc trois scrapes distincts (1er nov., 20 oct., 6 oct.). `db_meta.last_update_patch` vaut
« 14 » sur les quatre fichiers : il ne sait pas dater un patch.

### 1.5 Coût

Par scrape et par poste : `PoolEvaluator` et ses valeurs 0,68 à 0,78 s, `draw_shifts` 0,16 à 0,18 s (mesure du
2026-11-06). Une moyenne sur trois scrapes coûte ~2,7 s par poste.

## 2. Objectif et arbitrages

Sur l'écran Suggestions, un bouton « Générer » propose pour le poste ouvert le pool de N champions qui maximise J,
sur le scrape actuel ou en moyenne sur les scrapes distincts, hors champions exclus ; « Créer le pool » l'enregistre
et le désigne au poste. Les cartes d'échange passent au même score.

| Sujet | Décision |
|---|---|
| Objectif | **Validé (@pj35, 2026-11-06)** : J de §1.3, ½ blind exposé au counter + ½ counter, sans maîtrise (décision SPEC-49). |
| Tirage | **Validé (@pj35, 2026-11-06)** : retiré de la force dans les deux parts, pour le générateur et les cartes (règle d'ADR-004, `draw_correction`). |
| Scrapes | **Validé (@pj35, 2026-11-06)** : interrupteur « Moyenne des scrapes » (défaut) ou « Scrape actuel ». Moyenne = base + sauvegardes, dédoublonnées par `last_scrape_utc`, candidats communs à tous. |
| Taille | **Validé (@pj35, 2026-11-06)** : de 3 à 6, 5 par défaut. |
| Création | **Validé (@pj35, 2026-11-06)** : nouveau pool « <POSTE> GÉNÉRÉ <AAAA-MM-JJ> », désigné au poste ; l'ancien reste dans la liste. |
| Exclusions | **Validé (@pj35, 2026-11-06)** : liste par poste, permanente jusqu'au retrait, appliquée au générateur et aux cartes. |
| Cartes | **Validé (@pj35, 2026-11-06)** : toujours sur le scrape actuel (passes liées à la version des données). |
| Déclenchement | **Validé (@pj35, 2026-11-06)** : bouton « Générer », résultat gardé en mémoire tant que données, taille, mode et exclusions ne changent pas. |
| Recherche | **Validé (@pj35, 2026-11-06)** : gloutonne puis échanges, Python pur, sans numpy (§1.3). |

## 3. Approches considérées

1. **Retenue : générateur sur l'écran Suggestions.** Le poste, le pool et les cartes y sont déjà ; l'écran est
   proposé après chaque mise à jour (SPEC-49). Les cartes profitent du nouveau score.
2. **Script `scripts/pool_optimal.py`** : livré en une heure, mais sans interface ni création du pool. Écarté par
   @pj35 le 2026-11-06.
3. **Écran dédié** : plus de place (comparaisons, stabilité par scrape), mais il double l'écran Suggestions.
   Écarté.

## 4. Détail

### 4.1 Score : `src/analysis/pool_swipe.py`

`PoolEvaluator` ne change pas (bans, tier list et trio en dépendent). Une couche au-dessus porte le tirage :

```python
class PoolScorer:
    """Valeurs nettes du tirage et blind exposé au counter, sur un `PoolEvaluator`."""

    def __init__(self, evaluator: PoolEvaluator, draws: Mapping[str, float]) -> None: ...
    lane: Optional[str]; enemies: List[str]; popularity: List[float]   # repris de l'évaluateur
    def values(self, champion: str) -> List[float]: ...   # evaluator.values(c) − tirage(c)
    def blind(self, champion: str) -> float: ...          # force − tirage + E[min sur POOL_BLIND_DRAWS tirages]
    def counter_value(self, pool: Sequence[str]) -> float: ...  # Σ_e popularité · max values

def pool_score(scorer: PoolScorer, pool: Sequence[str]) -> float: ...   # ½ counter_value + ½ max blind
def swap_cards(scorer: PoolScorer, pool, passed=(), excluded=()) -> List[SwapCard]: ...
```

- `draws` : `{nom: points}` de `draw_shifts(connection)[lane]`, clés comparées sans casse ; champion absent : 0.
- `E[min]` : adversaires `enemies` hors le champion lui-même, poids = popularité renormalisée, tirage avec
  remise : `Σ_v v · (P(≥ v)^k − P(> v)^k)` sur les duels triés, `k = POOL_BLIND_DRAWS`. Duel = `values(c)` brut
  de l'évaluateur moins sa force.
- `SwapCard.blind_gain` = ½ · Δ max blind ; `counter_gain` = ½ · Δ counter_value ; `_duels` lit `scorer.values`.
- `swap_cards` écarte `excluded` comme `passed`.
- `blind` et `values` sont mis en cache par champion.

### 4.2 Générateur : `src/analysis/pool_generator.py` (nouveau)

```python
@dataclass(frozen=True)
class GeneratedPool:
    lane: str
    champions: Tuple[str, ...]          # ordre : meilleur blind d'abord
    score: float                        # J moyen
    per_scrape: Tuple[float, ...]       # J de chaque scrape, du plus récent au plus ancien
    blind: Tuple[Tuple[str, float], ...]          # blind de chaque champion (scrape le plus récent)
    counter_share: Tuple[Tuple[str, float], ...]  # part de popularité où il est le meilleur counter
    counters: Tuple[Tuple[str, float, str, float], ...]  # (adversaire, popularité, counter du pool, value')
    candidates: int

def generate_pool(scorers: Sequence[PoolScorer], size: int, excluded: Collection[str]) -> Optional[GeneratedPool]: ...
```

- Candidats : popularité ≥ `POOL_SWIPE_MIN_POPULARITY` dans **chaque** scorer, hors `excluded` (sans casse).
- J moyen = moyenne des `pool_score` des scorers.
- Glouton : `size` ajouts du candidat qui maximise J ; puis, tant qu'un échange (position × candidat hors pool)
  augmente J de plus de 1e-12, l'appliquer. Égalité : ordre alphabétique des candidats.
- Moins de `size` candidats : `None`.
- `counters` : adversaires de popularité ≥ `POOL_GEN_COUNTERS_MIN_POPULARITY` dans le scrape le plus récent, triés
  par popularité.

### 4.3 Scrapes distincts : `src/db_backup.py`

```python
def distinct_snapshots(database_path: str) -> List[Path]: ...
```

La base puis les `db.backup-*.db` voisines (motif `_BACKUP_NAME_RE`), de la plus récente à la plus ancienne ; une
seule par `db_meta.last_scrape_utc` (la première vue). Fichier illisible ou sans `db_meta` : écarté sans exception.
Lecture seule (`mode=ro`).

### 4.4 Exclusions : `src/user_prefs.py`

Clé `pool_exclusions` ajoutée à `_KEPT_KEYS` : `{"top": ["Gangplank", "Fiora"]}`.

```python
def load_pool_exclusions() -> Dict[str, List[str]]: ...          # {} si absente ou illisible
def save_pool_exclusion(lane: str, champion: str, excluded: bool) -> bool: ...
```

Lane hors `_KNOWN_LANES` : `False` sans écrire. Sans doublon (sans casse) ; retirer un absent : `True` sans changer.

### 4.5 Client : `src/client/pool_swipe.py` et routes de `src/client/app.py`

- `swipe_view` : cartes calculées par un `PoolScorer` du scrape actuel, exclusions du poste écartées ; la vue
  ajoute `exclusions` (noms et portraits), `sizes` (3 à 6), le mode et la taille courants, et `generated` si le
  résultat est en cache.
- `generate(db_path, lane, size, mode) -> GeneratedPool | None` : `distinct_snapshots` (mode `moyenne`) ou la base
  seule (mode `actuel`), un `PoolScorer` par fichier (`Database.connect_read_only`, `draw_shifts`), puis
  `generate_pool`. Cache `functools.lru_cache` sur `(lane, size, mode, exclusions triées, (chemin,
  last_scrape_utc) des scrapes)`.
- Routes, toutes en `in_thread`, corps `partials/pool_suggestions_body.html` :
  - `POST /pool/suggestions/generer?poste=&taille=&mode=` ;
  - `POST /pool/suggestions/creer?poste=&taille=&mode=` : recalcule (cache), refuse si rien n'est généré ; crée
    « <POSTE> GÉNÉRÉ <date> » (suffixe « (2) », « (3) »… si le nom est pris) au rôle du poste, `save_custom_pools(
    recalculate_bans=False)`, `save_role_pool(lane, nom)`, puis commande `pool <nom>` si c'est le pool actif ;
  - `POST /pool/suggestions/exclure?poste=&champion=&retirer=0|1` : `save_pool_exclusion`, champion validé contre
    `champion_names(db_path)`.
- Taille hors 3 à 6 : ramenée à `POOL_GEN_DEFAULT_SIZE` ; mode inconnu : `moyenne`.

### 4.6 Écran : `partials/pool_suggestions_body.html`, `style.css`

Section « Générer un pool » au-dessus de la carte : taille (select), mode (deux boutons radio), exclusions en
puces avec ✕ (formulaire « Exclure » avec `datalist` des champions), bouton « Générer » (`hx-indicator`). Résultat :
les champions avec leur blind et leur part de counter, J moyen et par scrape, l'écart avec le pool du poste
(`pool_score` moyen du pool actuel), le tableau des counters, puis « Créer le pool ». Marche sans JS (formulaires).

### 4.7 Constantes (`PoolStatisticsConfig`, `src/config_constants.py`)

| Constante | Valeur | Origine |
|---|---|---|
| `POOL_BLIND_DRAWS` | 7 | pire duel sur 7 tirages, mesure Blindabilité du 2026-11-01 |
| `POOL_GEN_DEFAULT_SIZE` | 5 | arbitrage §2 |
| `POOL_GEN_MIN_SIZE` | 3 | arbitrage §2 |
| `POOL_GEN_MAX_SIZE` | 6 | arbitrage §2 |
| `POOL_GEN_COUNTERS_MIN_POPULARITY` | 0,03 | tableau des counters du 2026-11-06 |

### 4.8 Tests

- `tests/test_pool_swipe.py` : `FakeEvaluator` + tirages donnés à la main — valeurs nettes du tirage, `E[min]` sur
  un cas calculé à la main (k = 1 : moyenne pondérée ; k grand : pire duel), cartes avec `excluded`, gains
  adaptés au nouveau blind.
- `tests/test_pool_generator.py` : glouton + échanges égal à l'énumération exhaustive (`itertools.combinations`)
  sur des évaluateurs factices aléatoires à graine fixe (≥ 20 cas, 12 candidats, taille 3 à 5) ; moyenne sur deux
  scorers ; candidat absent d'un scorer écarté ; exclusions ; trop peu de candidats → `None`.
- `tests/test_db_backup.py` : `distinct_snapshots` sur `tmp_path` — doublon de `last_scrape_utc` écarté, fichier
  illisible écarté, ordre.
- `tests/test_user_prefs.py` : exclusions par poste, sans doublon, retrait, lane inconnue, clés voisines gardées.
- `tests/test_client_pool_swipe.py` : générer rend la section, créer écrit le pool sous `tmp_path` et le désigne,
  nom pris suffixé, exclure retire le champion des cartes, taille et mode invalides ramenés au défaut.

## 5. Tâches

| # | Tâche | Pts | Dépend de |
|---|---|---|---|
| 246 | `PoolScorer` (tirage, blind exposé), `pool_score` et `swap_cards` dessus, `excluded`, `POOL_BLIND_DRAWS`, tests | 3 | — |
| 247 | `user_prefs` : clé `pool_exclusions`, `load_pool_exclusions`, `save_pool_exclusion`, tests | 2 | — |
| 248 | `distinct_snapshots`, `src/analysis/pool_generator.py`, constantes, tests (dont exhaustif) | 5 | 246 |
| 249 | Client : cartes sur `PoolScorer` et exclusions, `generate` en cache, routes `generer`, `creer`, `exclure`, tests | 3 | 247, 248 |
| 250 | Section « Générer un pool » du partiel, styles, sans JS | 2 | 249 |
| 251 | Clôture : exe vérifié, `PROJECT_STRUCTURE.md`, `CHANGELOG.md`, statuts, README des specs, `TODO.md` | 1 | 250 |

## 6. Critères d'acceptation

1. `python -m pytest tests/ -v` vert, avec les tests des tâches 246 à 250.
2. Sur `data/db.db` (scrape du 1er nov.), `generate_pool` en mode actuel, taille 5, sans exclusion, donne les cinq
   pools de §1.3 aux cinq postes, J à 0,001 près.
3. Au top, mode moyenne sur les scrapes du 1er nov., 20 oct. et 6 oct., Gangplank et Fiora exclus : Malphite,
   Pantheon, Riven, Shen, Urgot, J moyen +1,52 à 0,01 près.
4. `distinct_snapshots("data/db.db")` rend trois fichiers le 2026-11-06 (la sauvegarde du 30 oct. est un doublon).
5. `grep -rn "numpy\|mastery" src/analysis/pool_generator.py src/analysis/pool_swipe.py src/client/pool_swipe.py`
   ne trouve rien.
6. `PoolEvaluator` inchangé : `git diff --stat src/analysis/pool_value.py` vide.
7. Un champion exclu au top n'apparaît ni dans le pool généré ni dans les cartes du top, après une mise à jour
   des données comprise (test 249).
8. « Créer le pool » écrit « TOP GÉNÉRÉ <date> » dans `champion_pools.json`, le désigne au top dans
   `user_prefs.json`, et un second clic le même jour crée « TOP GÉNÉRÉ <date> (2) » (test 249).
9. Un second « Générer » sans changement ne recalcule pas (cache, test 249).
10. `CHANGELOG.md` (`[Unreleased]`), statut de cette spec et `docs/specs/README.md` à jour.

**Vérification de bout en bout** : dans le client lancé, écran Suggestions, poste Top, exclure Gangplank et
Fiora, mode « Moyenne des scrapes », taille 5, « Générer » : Malphite, Pantheon, Riven, Shen, Urgot ; « Créer le
pool » ; l'écran Pool montre « TOP GÉNÉRÉ <date> » désigné au top. Puis poste Mid, « Générer ». Recette par @pj35
(pas de sonde de fenêtre réelle sans son accord).

## 7. Hors périmètre

- ❌ Maîtrise : écartée des suggestions par @pj35 le 2026-11-03 (SPEC-49), le générateur suit.
- ❌ Synergie bot-support dans le pool : le duo est mesuré (1,1 pp, matrice Blindabilité) mais chaque pool reste
  par poste.
- ❌ Coupure automatique au changement de patch : `last_update_patch` ne date pas un patch (§1.4) ; l'interrupteur
  « Scrape actuel » sert en début de patch.
- ❌ Bouton « Exclure » sur les cartes d'échange : les exclusions se gèrent dans la section du générateur.
- ❌ Assurance contre les bans dans J : à 5 champions, retirer le meilleur coûte 0,03 à 0,10 pt (2026-11-06),
  sous le bruit d'un scrape.
- ❌ numpy : la recherche gloutonne trouve l'optimum exact en Python pur (§1.3).
