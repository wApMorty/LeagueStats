# SPEC-08 — Fermer la boucle de mesure : résultat de partie automatique

**Chantier** : A (priorité 1) · **Effort** : ~1 jour · **Prérequis** : aucun · **Bloque** : toute calibration du modèle

**Constat** (vérifié en base le 2026-09-05) : `predictions` contient **12 lignes, 0 outcome renseigné**.

---

## 1. Le problème

Toutes les constantes qui pilotent la décision du coach sont **devinées, jamais mesurées** :

| Constante | Valeur | Où | Commentaire du code |
|---|---|---|---|
| `K_MATCHUP` | 1.0 | `config_constants.py:140` | — |
| `K_SYNERGY` | 0.5 | `config_constants.py:141` | — |
| `SAME_LANE_WEIGHT` | 2.0 | `config_constants.py:226` | *« Provisional values, to be calibrated with SPEC-05 »* |
| `OTHER_LANE_WEIGHT` | 1.0 | `config_constants.py:227` | idem |
| `DEFAULT_SYNERGY_WEIGHT` | 0.5 | `config_constants.py:203` | — |
| `MIN_CHAMPION_GAMES` | 200 | `config_constants.py:197` | scalé « à ~40 % » à l'estime |
| `MIN_GAMES_THRESHOLD` | 800 | `config_constants.py:115` | idem |

L'infrastructure de mesure existe pourtant intégralement :

- `PredictionsRepository.insert_prediction()` (`src/repositories/predictions.py:17`), appelée en fin de draft par `FinalDraftAnalyzer` (`src/draft/final_analysis.py:296`).
- `scripts/calibrate_model.py` : courbe de calibration par décile, score de Brier, suggestion de `k_m`/`k_s` par recalibration de Platt. Il refuse de conclure sous `MIN_ROWS_FOR_CALIBRATION = 30` lignes labellisées.

**Le maillon manquant est unique** : le résultat réel de la partie n'entre jamais en base. Le seul chemin prévu est manuel — revenir dans le terminal après la partie et taper `outcome win` (`src/draft/commands.py:106`). Sur 12 parties draftées entre le 01/09 et le 05/09, il a été emprunté **zéro fois**.

### Révision explicite d'une décision de SPEC-05

`handle_outcome_command()` porte cette justification :

> *« Manual command by design (not a gameflow/EndOfGame hook, per SPEC-05: untestable against a real LCU client without speculating on its behavior). »*

**Cette décision est révisée ici**, sur preuve empirique : une commande manuelle à 0 % de taux d'emploi ne produit aucune donnée, donc aucune calibration, donc aucune amélioration du modèle.

L'objection de testabilité était fondée et elle est **levée** : le spike du 2026-09-05 (§2.1) a relevé la forme réelle des réponses sur le client de @pj35, il n'y a donc plus rien à supposer du comportement du LCU. Les tests se font sur mocks à partir de ces payloads vérifiés (§5), comme pour le reste de `lcu_client.py`.

---

## 2. Le travail

### 2.1 — Spike : ✅ FAIT le 2026-09-05, résultats ci-dessous

Réalisé sur le client réel (compte `Morty`, EUW1, LCU port 41133). **Ne pas le refaire : les formes ci-dessous sont vérifiées, les utiliser telles quelles.**

**A. `/lol-match-history/v1/products/lol/current-summoner/matches?begIndex=0&endIndex=2`**

Structure : `{"accountId", "platformId", "games": {"gameCount", "gameIndexBegin", "gameIndexEnd", "games": [...]}}` — noter le **double** `games.games`. `endIndex=2` a renvoyé **3** parties : il est **inclusif**.

Chaque partie porte : `gameId`, `gameCreation` (epoch **ms**, ex. `1788639943655`), `gameCreationDate` (ISO, ex. `"2026-09-05T20:25:43.655Z"`), `gameDuration`, `queueId` (`420` = SoloQ), `gameMode`, `endOfGameResult` (`"GameComplete"`), `teams` (`[{"teamId": 100, "win": "Win"}, {"teamId": 200, "win": "Fail"}]`).

> ⚠️ **Piège majeur** : `participants` ne contient ici qu'**une seule entrée** — le joueur courant. Les 9 autres joueurs sont **absents**. On y lit `participants[0].championId`, `participants[0].teamId` et `participants[0].stats.win` (booléen Python), rien de plus.

**B. `/lol-match-history/v1/games/{gameId}`** — c'est cet endpoint qui donne l'équipe complète :

```
nb participants: 10
championIds (participantId, championId, teamId):
  (1, 126, 100) (2, 104, 100) (3, 105, 100) (4, 202, 100) (5, 99, 100)
  (6, 36, 200)  (7, 77, 200)  (8, 950, 200) (9, 800, 200) (10, 63, 200)
teams: [{"teamId": 100, "win": "Win"}, {"teamId": 200, "win": "Fail"}]
```

`participantId` 1-5 ⇒ `teamId` 100, 6-10 ⇒ `teamId` 200. La variante `/lol-match-history/v1/products/lol/current-summoner/matches/{gameId}` renvoie **404** — ne pas l'utiliser.

**C. `/lol-gameflow/v1/session`** → `phase` valait `"InProgress"` (partie en cours au moment du spike). Les phases de fin (`WaitingForStats`, `PreEndOfGame`, `EndOfGame`) n'ont pas pu être observées. **Ce n'est pas bloquant** : le déclencheur n'est qu'une optimisation de confort, le rattrapage au démarrage (§2.6b) couvre tous les cas. Traiter la liste de phases comme configurable (§3) et ne jamais faire dépendre la correction d'une valeur exacte.

**D. `/lol-end-of-game/v1/eog-stats-block`** → `None` hors écran de fin, comme attendu. Endpoint écarté (§2.2).

### 2.2 — Choix d'architecture : historique de matchs, pas écran de fin

Trois sources possibles, une seule retenue :

| Source | Pour | Contre | Verdict |
|---|---|---|---|
| `/lol-end-of-game/v1/eog-stats-block` | Résultat immédiat, riche | Disponible **seulement** pendant l'écran de fin (quelques secondes si le joueur le passe) ; perdu si l'app est fermée | ❌ trop volatil seul |
| `/lol-gameflow/v1/session` phase `EndOfGame` | Signal de fin fiable | Ne contient **pas** le résultat | ✅ comme *déclencheur* |
| `/lol-match-history/v1/products/lol/current-summoner/matches` | Interrogeable **à tout moment**, contient `gameId`, `gameCreation`, `queueId` et le résultat du joueur | Ne renvoie qu'**un** participant (§2.1A) : la composition des équipes est absente | ✅ comme **source de vérité** du résultat |
| `/lol-match-history/v1/games/{gameId}` | Les **10 participants** avec `championId` et `teamId` | Un appel HTTP par partie | ✅ comme **confirmation d'appariement** |

**Décision** : l'historique de matchs est la source de vérité ; le gameflow n'est qu'un déclencheur. Conséquence majeure : **un rattrapage au démarrage devient possible**, donc fermer l'application entre deux parties ne perd plus le résultat. C'est ce qui rend le dispositif robuste là où le hook `EndOfGame` seul ne l'aurait pas été.

### 2.3 — `LCUClient` : deux méthodes de lecture

`src/lcu_client.py` est à **493 lignes** et le plafond projet est 500 : n'y mettre que ces deux méthodes, courtes, et **placer toute la normalisation et l'appariement dans `outcome_tracker.py`** (§2.4). Si le fichier menace de dépasser 500, extraire un mixin `src/lcu_match_history.py` sur le modèle de `src/parser_cookie_banner.py`.

```python
def get_recent_matches(self, count: int = 5) -> List[Dict[str, Any]]:
    """Les `count` dernières parties du joueur courant, les plus récentes d'abord.

    Chaque entrée normalisée : {"game_id": int, "game_creation_ms": int,
    "queue_id": int, "win": bool, "player_champion_id": int, "team_id": int}.
    Retourne [] si le client est absent ou la réponse inattendue (best-effort).
    """

def get_match_participants(self, game_id: int) -> Dict[int, List[int]]:
    """Les championId de chaque équipe d'une partie : {100: [...], 200: [...]}.

    Retourne {} si indisponible (best-effort).
    """
```

- `get_recent_matches` lit `payload["games"]["games"]` (double niveau, cf. §2.1A), puis pour chaque partie `gameId`, `gameCreation`, `queueId`, et **`participants[0]`** — qui est le joueur courant et le seul présent : `championId`, `teamId`, `stats.win`. Rappel : `endIndex` est **inclusif**, donc `count - 1`.
- `get_match_participants` appelle `/lol-match-history/v1/games/{game_id}` et regroupe `participants[].championId` par `participants[].teamId`.

Ne jamais lever : toute forme inattendue (clé manquante, `None`, liste vide) donne `[]` / `{}`.

### 2.4 — Nouveau module `src/draft/outcome_tracker.py`

Toute la logique d'appariement y vit (ne pas grossir `lifecycle.py` ni `commands.py`) :

```python
class OutcomeTracker:
    """Rapproche les prédictions en attente des parties réellement jouées."""

    def resolve_pending(self, limit: int = None) -> int:
        """Labellise les prédictions sans outcome depuis l'historique LCU.
        Retourne le nombre de prédictions résolues. Best-effort : ne lève jamais.
        """
```

**Règle d'appariement**, en deux passes (le détail des 10 participants coûte un appel HTTP par partie : ne le demander que pour les candidates retenues par le temps).

*Passe 1 — filtre temporel*, sur `get_recent_matches` seul. Une partie `M` est candidate pour une prédiction `P` si :

1. `M.game_creation_ms` est **postérieur** à `P.created_utc` (la partie commence après la fin de la draft) ;
2. l'écart est inférieur à `OUTCOME_MATCH_WINDOW_HOURS` (défaut 6 h) ;
3. `M.game_id` n'est pas déjà rattaché à une autre prédiction.

`created_utc` est écrit par `datetime('now')` de SQLite, donc au format `'YYYY-MM-DD HH:MM:SS'` en **UTC** — le parser comme tel (`datetime.strptime(..., "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)`), et `game_creation_ms` via `datetime.fromtimestamp(ms / 1000, tz=timezone.utc)`. Ne jamais comparer un naïf à un aware.

*Passe 2 — confirmation par composition*, via `get_match_participants(M.game_id)` :

4. `M.teams[P_team]` (l'équipe du joueur, donnée par `team_id` de la passe 1) doit partager au moins `OUTCOME_MIN_ALLY_OVERLAP` (défaut 4) champions avec `P.ally_champions` ;
5. **et** l'équipe adverse doit partager au moins autant de champions avec `P.enemy_champions`.

Le seuil est à 4 sur 5 et non 5 sur 5 pour tolérer un pick modifié après le log de fin de draft. La double vérification (alliés **et** ennemis) rend l'appariement quasi certain — c'est ce que le spike a rendu possible en découvrant l'endpoint de détail.

En cas d'ambiguïté (plusieurs parties candidates pour une prédiction), retenir **la plus proche dans le temps**. En cas d'ambiguïté inverse (une partie candidate pour deux prédictions), la prédiction la plus proche gagne, l'autre reste en attente : **une donnée fausse est pire qu'une donnée absente** — c'est l'invariant de toute cette spec.

Le résultat lui-même vient de `M.win` (`participants[0].stats.win`, booléen), pas de `teams[].win` (chaîne `"Win"`/`"Fail"`, plus fragile).

### 2.5 — Migration Alembic : `predictions.game_id`

Sans identifiant de partie, l'idempotence est impossible (une relance labelliserait deux fois). Migration :

```sql
ALTER TABLE predictions ADD COLUMN game_id INTEGER;  -- NULL = résolu manuellement ou pas encore résolu
CREATE UNIQUE INDEX idx_predictions_game_id ON predictions(game_id) WHERE game_id IS NOT NULL;
```

L'index partiel garantit qu'une même partie ne labellise jamais deux prédictions. Voir `docs/alembic_guide.md`.

`PredictionsRepository` gagne :
- `get_pending_predictions(limit) -> List[...]` — lignes `outcome IS NULL`, plus récentes d'abord, avec `created_utc` et `ally_champions` décodés ;
- `update_prediction_outcome(prediction_id, outcome, game_id=None)` — paramètre optionnel ajouté, **signature existante préservée** (la commande manuelle continue d'appeler sans `game_id`).

### 2.6 — Deux points de déclenchement

**(a) En cours de session** — dans `MonitorLifecycle.monitor_loop()` (`src/draft/lifecycle.py:59`), la lecture du gameflow existe déjà. Quand `phase` entre dans `("WaitingForStats", "PreEndOfGame", "EndOfGame")` alors qu'elle n'y était pas au tick précédent, appeler `OutcomeTracker.resolve_pending()`. **Une seule fois par transition** (garder un drapeau, comme `has_analyzed_final_draft`), et jamais dans le chemin chaud du champion select.

**(b) Au démarrage du Draft Coach** — dans `src/ui/draft_coach_ui.py`, avant d'entrer dans la boucle : un `resolve_pending(limit=OUTCOME_BACKFILL_LIMIT)` rattrape ce qui a été joué app fermée. C'est ce point qui rend le dispositif fiable en usage réel.

Sortie console (convention ASCII, cf. §Règles communes) :

```
[OUTCOME] Partie 7412339812 -> victoire — prédiction #13 (prévue 54,1 %) labellisée
[OUTCOME] 3 prédiction(s) en attente rattrapée(s) · 18 labellisées au total (30 requises pour calibrer)
```

Le compteur « n / 30 » est important : il rend visible la progression vers la première calibration exploitable.

### 2.7 — La commande manuelle reste

`outcome win|loss` n'est **pas** supprimée : elle sert de repli quand le LCU est indisponible et de correction manuelle. Elle doit continuer à passer ses tests existants sans modification.

### 2.8 — Rattrapage des 12 prédictions historiques

Les 12 lignes du 01/09 au 05/09 sont hors de la fenêtre de 6 h. Ne **pas** les labelliser au jugé : les laisser à `NULL`. Elles restent le témoin du problème que cette spec corrige.

---

## 3. Configuration

Dans `src/config_constants.py`, section `DraftConfig` (aucune valeur en dur ailleurs) :

```python
# SPEC-08 : fenêtre max entre la fin d'une draft et le début de la partie
# correspondante dans l'historique LCU. 6 h couvre une partie lancée après
# une longue file ou une pause, sans risquer d'apparier la session du soir
# avec celle du lendemain matin.
OUTCOME_MATCH_WINDOW_HOURS: float = 6.0

# Nombre de prédictions en attente examinées au démarrage (rattrapage).
OUTCOME_BACKFILL_LIMIT: int = 20

# Parties lues dans l'historique LCU à chaque tentative de résolution.
# Attention : le paramètre `endIndex` de l'endpoint est INCLUSIF (vérifié
# 2026-09-05), donc la requête utilise endIndex = OUTCOME_HISTORY_DEPTH - 1.
OUTCOME_HISTORY_DEPTH: int = 10

# Champions communs exigés (sur 5) entre une prédiction et une partie, des
# deux côtés — alliés ET ennemis. 4 tolère un pick modifié après le log de
# fin de draft.
OUTCOME_MIN_ALLY_OVERLAP: int = 4

# Phases gameflow déclenchant une tentative de résolution.
OUTCOME_TRIGGER_PHASES: tuple = ("WaitingForStats", "PreEndOfGame", "EndOfGame")
```

---

## 4. Critères d'acceptation

1. Après une partie jouée avec le Draft Coach actif, la prédiction correspondante porte `outcome` **et** `game_id` sans aucune action de l'utilisateur.
2. Application fermée pendant la partie puis relancée : le rattrapage au démarrage labellise la prédiction.
3. Relancer le rattrapage deux fois de suite ne modifie rien la seconde fois (idempotence via `game_id`).
4. Client LoL éteint : `resolve_pending()` retourne `0`, n'affiche aucune erreur bloquante, et le Draft Coach démarre normalement.
5. Aucune prédiction n'est labellisée quand la règle d'appariement (§2.4) n'est pas satisfaite — la valeur par défaut est l'abstention.
6. `python scripts/calibrate_model.py` fonctionne sans modification sur les lignes ainsi produites.
7. `pytest tests/ -v` intégralement vert, `black --check`, `pylint src/ --fail-under=8.0`.

---

## 5. Tests exigés

Hermétiques, sans client LoL réel : mocker `LCUClient.get_recent_matches` / `get_match_participants` et utiliser la fixture `temp_db`.

`tests/test_outcome_tracker.py` :
- appariement nominal (1 prédiction, 1 partie correspondante) → labellisée, `game_id` posé ;
- partie **antérieure** à la prédiction → rejetée ;
- partie hors fenêtre de 6 h → rejetée ;
- 3 champions alliés communs sur 5 → rejetée ; 4 sur 5 → acceptée ;
- alliés concordants mais **ennemis** discordants → rejetée (la passe 2 vérifie les deux côtés) ;
- deux parties candidates → la plus proche dans le temps gagne ;
- deux prédictions, une seule partie → une seule labellisée, l'autre reste `NULL` ;
- deuxième passage → 0 résolution supplémentaire (idempotence) ;
- LCU indisponible (`get_recent_matches` retourne `[]`) → retourne 0, ne lève pas ;
- `get_match_participants` retourne `{}` (détail indisponible) → abstention, pas de labellisation au jugé ;
- **économie d'appels** : `get_match_participants` n'est appelée que pour les parties retenues par la passe temporelle (vérifier par compteur de mock).

`tests/test_lcu_matches.py` : normalisation à partir des payloads figés du spike (§2.1).
- `get_recent_matches` : victoire, défaite, structure `games.games` absente, `participants` vide, réponse `None`, `endIndex` correctement calculé à `count - 1` ;
- `get_match_participants` : les 10 participants regroupés en `{100: [...], 200: [...]}`, réponse 404/`None` → `{}`.

`tests/test_draft_monitor_lifecycle.py` (existant, à étendre) : la transition de phase déclenche `resolve_pending` **une seule fois** ; rester dans la même phase ne le rappelle pas.

Migration : ajouter à `tests/test_migration_*.py` un cas upgrade/downgrade, comme pour `3e87f22f2ec1`. Attention au piège déjà rencontré — la fixture doit créer `predictions` avant de stamper une révision antérieure (cf. `CHANGELOG.md`, fix du 2026-09-04).

---

## 6. Hors périmètre

- ❌ Modifier `K_MATCHUP`/`K_SYNERGY`/les poids de lane. Cette spec **produit la mesure**, elle ne l'exploite pas. Tout changement de valeur viendra plus tard, sur sortie de `calibrate_model.py`, et **exigera un bump de `MODEL_VERSION`** (sans quoi la calibration mélangerait deux modèles — cf. en-tête de `calibrate_model.py`).
- ❌ Distinguer les files (SoloQ / flex / normale). `queue_id` est stocké pour un filtrage ultérieur, pas exploité ici.
- ❌ Enregistrer autre chose que la victoire/défaite (durée, KDA, gold…).
- ❌ Toute recalibration automatique : appliquer un `k` reste une décision manuelle et documentée.
