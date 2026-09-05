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

**Cette décision est révisée ici**, sur preuve empirique : une commande manuelle à 0 % de taux d'emploi ne produit aucune donnée, donc aucune calibration, donc aucune amélioration du modèle. L'objection de testabilité reste valable et est traitée en §2.1 (spike de terrain avant implémentation) et §5 (tests sur mocks, comme le reste de `lcu_client.py`).

---

## 2. Le travail

### 2.1 — Spike préalable, obligatoire (~1 h)

**Ne pas coder avant d'avoir observé le vrai client.** Avec League of Legends lancé et une partie terminée dans l'historique, relever la forme réelle des réponses :

```python
# Depuis le repo, client LoL lancé :
from src.lcu_client import LCUClient
c = LCUClient(verbose=True); c.connect()
print(c._make_request("/lol-match-history/v1/products/lol/current-summoner/matches?begIndex=0&endIndex=3"))
print(c._make_request("/lol-gameflow/v1/session"))          # noter la valeur de "phase"
print(c._make_request("/lol-end-of-game/v1/eog-stats-block"))  # pendant l'écran de fin uniquement
```

Consigner dans la PR : les clés réellement présentes, et si `endIndex` est inclusif. Si la forme diffère de §2.3, **adapter la spec plutôt que le client**.

### 2.2 — Choix d'architecture : historique de matchs, pas écran de fin

Trois sources possibles, une seule retenue :

| Source | Pour | Contre | Verdict |
|---|---|---|---|
| `/lol-end-of-game/v1/eog-stats-block` | Résultat immédiat, riche | Disponible **seulement** pendant l'écran de fin (quelques secondes si le joueur le passe) ; perdu si l'app est fermée | ❌ trop volatil seul |
| `/lol-gameflow/v1/session` phase `EndOfGame` | Signal de fin fiable | Ne contient **pas** le résultat | ✅ comme *déclencheur* |
| `/lol-match-history/v1/products/lol/current-summoner/matches` | Interrogeable **à tout moment**, contient `gameId`, `gameCreation`, `participants[].stats.win` | Latence de quelques secondes après la partie | ✅ comme **source de vérité** |

**Décision** : l'historique de matchs est la source de vérité ; le gameflow n'est qu'un déclencheur. Conséquence majeure : **un rattrapage au démarrage devient possible**, donc fermer l'application entre deux parties ne perd plus le résultat. C'est ce qui rend le dispositif robuste là où le hook `EndOfGame` seul ne l'aurait pas été.

### 2.3 — `LCUClient` : une méthode de lecture

Dans `src/lcu_client.py` (493 lignes — **ne pas dépasser 500**, une seule méthode courte ici, le reste va dans le nouveau module) :

```python
def get_recent_matches(self, count: int = 5) -> List[Dict[str, Any]]:
    """Les `count` dernières parties du joueur courant, les plus récentes d'abord.

    Chaque entrée normalisée : {"game_id": int, "game_creation_ms": int,
    "queue_id": int, "win": bool, "ally_champion_ids": List[int]}.
    Retourne [] si le client est absent ou la réponse inattendue (best-effort).
    """
```

Elle lit `games.games[]`, et pour chaque partie : `gameId`, `gameCreation`, `queueId`, le `participant` du joueur local (via `participantIdentities` ↔ `participants[].stats.win`), et les `championId` des 5 joueurs de son équipe (`participants[].teamId` égal à celui du joueur local).

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

**Règle d'appariement** — une partie `M` valide une prédiction `P` si et seulement si :

1. `M.game_creation_ms` est **postérieur** à `P.created_utc` (la partie a commencé après la fin de la draft) ;
2. l'écart est inférieur à `OUTCOME_MATCH_WINDOW_HOURS` (défaut 6 h) ;
3. au moins `OUTCOME_MIN_ALLY_OVERLAP` (défaut 4) des 5 `ally_champions` de `P` figurent dans `M.ally_champion_ids` — 4 et non 5, pour tolérer un dodge/remake partiel ou un pick de dernière seconde modifié après le log ;
4. `M.game_id` n'a pas déjà été rattaché à une autre prédiction.

En cas d'ambiguïté (plusieurs parties candidates), retenir **la plus proche dans le temps**. En cas d'ambiguïté inverse (une partie candidate pour deux prédictions), la prédiction la plus proche gagne, l'autre reste en attente : **une donnée fausse est pire qu'une donnée absente** — c'est l'invariant de toute cette spec.

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

# Champions alliés communs exigés entre une prédiction et une partie pour
# les apparier (sur 5). 4 tolère un pick modifié après le log de la draft.
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

Hermétiques, sans client LoL réel : mocker `LCUClient.get_recent_matches` et utiliser la fixture `temp_db`.

`tests/test_outcome_tracker.py` :
- appariement nominal (1 prédiction, 1 partie correspondante) → labellisée, `game_id` posé ;
- partie **antérieure** à la prédiction → rejetée ;
- partie hors fenêtre de 6 h → rejetée ;
- 3 champions alliés communs sur 5 → rejetée ; 4 sur 5 → acceptée ;
- deux parties candidates → la plus proche dans le temps gagne ;
- deux prédictions, une seule partie → une seule labellisée, l'autre reste `NULL` ;
- deuxième passage → 0 résolution supplémentaire (idempotence) ;
- LCU indisponible (`get_recent_matches` retourne `[]`) → retourne 0, ne lève pas.

`tests/test_lcu_matches.py` : normalisation de `get_recent_matches` à partir d'un payload figé issu du spike (défaite, victoire, payload tronqué, réponse `None`).

`tests/test_draft_monitor_lifecycle.py` (existant, à étendre) : la transition de phase déclenche `resolve_pending` **une seule fois** ; rester dans la même phase ne le rappelle pas.

Migration : ajouter à `tests/test_migration_*.py` un cas upgrade/downgrade, comme pour `3e87f22f2ec1`. Attention au piège déjà rencontré — la fixture doit créer `predictions` avant de stamper une révision antérieure (cf. `CHANGELOG.md`, fix du 2026-09-04).

---

## 6. Hors périmètre

- ❌ Modifier `K_MATCHUP`/`K_SYNERGY`/les poids de lane. Cette spec **produit la mesure**, elle ne l'exploite pas. Tout changement de valeur viendra plus tard, sur sortie de `calibrate_model.py`, et **exigera un bump de `MODEL_VERSION`** (sans quoi la calibration mélangerait deux modèles — cf. en-tête de `calibrate_model.py`).
- ❌ Distinguer les files (SoloQ / flex / normale). `queue_id` est stocké pour un filtrage ultérieur, pas exploité ici.
- ❌ Enregistrer autre chose que la victoire/défaite (durée, KDA, gold…).
- ❌ Toute recalibration automatique : appliquer un `k` reste une décision manuelle et documentée.
