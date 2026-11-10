# SPEC-47 — La draft dans la win chance en partie

**Statut** : ✅ Livrée le 2026-11-01 (branche `claude/clever-jang-6d19f8`, fusionnée dans `master`). Recette validée par @pj35 le 2026-11-10 (`docs/RECETTE_2026_11.md`).

**Origine** : @pj35, 2026-10-19 : la courbe de win chance part toujours de ~50 % sans tenir compte de la draft.
Terme écarté ce jour-là au seuil de 0,002, rejugé le 2026-11-01 sans seuil
([ADR-004](../adr/ADR-004-evaluation-a-deux-etages.md), [SPEC-33](SPEC-33-eclaireur-des-joueurs-en-partie.md) §7),
adoption validée par @pj35 le 2026-11-01.

**Effort** : ~2 jours, 6 tâches (§5).

---

## 1. Constat

- **Mesure du 2026-11-01** (`scripts/rejudge_winchance_terms.py`, 15 383 parties 16.21, validation croisée à 5
  blocs, K ajustés sur 16.20 donc hors échantillon) : Brier ≤ 10 min 0,23293 → 0,23057, gain **+0,00236**, IC 90 %
  +0,00170 à +0,00299, placebo nul. Écart max par décile ≤ 10 min 2,4 → 2,5 pts, toutes images 0,49 → 0,66 pt.
  La win chance bouge de 4,0 pts en moyenne sur les images ≤ 10 min (RMS 5,0, p90 8,3, max 21,6).
- **Le poids de la draft reste positif sur toute la partie** (ajustement sur les 15 383 parties, 2026-11-01) :
  1,23 logit par logit de draft à 0 min, 1,08 à 10 min, 0,79 à 30 min, 0,36 à 60 min. La forme linéaire en temps
  ne change pas de signe sur les durées observées.
- **Le modèle en place date du patch 16.19** : `data/winprob_model.json`, 7 782 parties, 2026-10-03, sans `draft`
  dans ses entrées. Le réentraînement est manuel en pratique (`src/winprob/retrain.py`, journal
  `data/winprob_model.log`, dernier passage le 2026-10-03).
- **Tous les états de partie naissent de `_Replay.state`** (`src/winprob/state.py:126`) : timeline
  (`frame_states`, `transitions`, `segments`) et Live Client (`live.state_from_live`, `src/winprob/live.py:84`).
- **Trois chemins prédisent** : `overlay.Tracker.update` (`src/winprob/overlay.py:38`, partagé avec l'écran
  « En partie » par `client/ingame.py:194`), `report.curve_points` (`src/winprob/report.py:44`, courbe de la
  revue) et `impact.impacts` (`src/winprob/impact.py:135`, ΔP, éclaireur, maîtrise).
- **Le poste de chaque joueur est connu en direct** : `allPlayers[*].position` est servi pour les dix joueurs dès
  le premier relevé (SPEC-27 §4.1), et `draft.reality_check.resolve_champions` et `real_lanes` traduisent déjà
  noms et postes de la Live Client API.
- **Le client ne lit pas `db.db` comme le moteur** : `client/db.py:24` rend une `DbHandle` en `mode=ro`, sans les
  `get_all_matchups_bulk` qu'exige `GameEvaluator` (`src/analysis/game_eval.py:67`), qui attend une `Database`.

## 2. Objectif et arbitrages

La win chance part de la draft, en partie et dans la revue, sans changer ce que vaut un kill.

| Sujet | Décision |
|---|---|
| Adoption | **Validé (@pj35, 2026-11-01)** : ADR-004 premier étage, IC 90 % du gain hors de 0. |
| Approche | **Validé (@pj35, 2026-11-01)** : `draft` devient une variable du modèle, avec son produit par le temps, et le modèle est réentraîné (§3, A). |
| Impacts ΔP | **Validé (@pj35, 2026-11-01)** : neutres, draft = 0. Pastilles de l'éclaireur, maîtrise et classement post-game restent comparables entre parties. La somme des ΔP peut s'écarter un peu de la courbe, surtout loin de 50 %. |
| Surfaces | **Validé (@pj35, 2026-11-01)** : écran « En partie », overlay et courbe post-game. |
| Draft inconnue | Terme à 0 : file non classée à l'entraînement, moins de dix postes valides, base illisible, erreur. Jamais d'exception vers le suivi en partie. |
| Moment du calcul en direct | Au premier relevé où les dix postes sont valides, une fois par partie. Avant, le terme vaut 0 : la courbe peut sauter au tout premier relevé. |
| Ancien modèle | Il reste lisible : un modèle sans `draft` dans `inputs` ignore le champ, et le terme n'est alors même pas calculé. Rien ne change avant le réentraînement. |
| Réentraînement réel | `python -m src.winprob.retrain --force` écrit `data/winprob_model.json` : lancé par @pj35 ou sur son accord (tâche 235). |

## 3. Approches considérées

| Approche | Pour | Contre |
|---|---|---|
| **A. Variable du modèle (retenue)** | Forme mesurée ; l'effet relatif de la draft recule tout seul quand l'avance grossit ; le modèle rattrape deux patchs | Réentraînement à brancher sur `db.db` |
| B. Correction a + b·t hors modèle | Aucun réentraînement, impacts intacts | Forme non mesurée, modèle 16.19 conservé, second jeu de coefficients à maintenir |
| C. Point de départ affiché, fondu fixe | Le plus simple | Décroissance choisie à la main, affichage incohérent avec le modèle |

## 4. Détail

### 4.1 État et modèle

- `src/winprob/state.py` : `_Replay.__init__(self, teams, draft: float = 0.0)`, `state()` pose
  `state["draft"] = self.draft`. `walk(game, timeline, draft=0.0)` et `frame_states(game, timeline, draft=0.0)`
  le transmettent. `transitions` et `segments` gardent 0 : c'est ce qui rend les ΔP neutres, sans toucher à
  `impact.py`. `FEATURES` ne change pas.
- `src/winprob/model.py` : `DRAFT_INPUTS = INPUTS + ("draft",)`. `INPUTS` et le défaut de `fit` ne changent pas :
  `measure_form_term`, `rejudge_winchance_terms` et les fixtures restent valables.
- `src/winprob/live.py` : `state_from_live(data, draft: float = 0.0)` passe `draft` à `_Replay`.

### 4.2 Le logit de draft : `src/winprob/draft_term.py` (nouveau)

```python
Teams = Tuple[List[Placed], List[Placed]]  # bleu, rouge

def game_teams(game: dict, names: Dict[int, str], roles: Optional[dict] = None) -> Optional[Teams]:
    """Compositions d'une partie finie, None sans dix postes distincts connus."""

def live_teams(players: Sequence[dict], names: Dict[int, str]) -> Optional[Teams]:
    """Compositions depuis `allPlayers`, None sans dix postes valides (`resolve_champions`, `real_lanes`)."""

def read_logit(db_path: Union[str, Path], teams: Optional[Teams]) -> float:
    """Logit bleu de `GameEvaluator.team_logit`, 0.0 sans compositions ou sur toute erreur. Ouvre et
    referme sa `Database` : utilisable depuis n'importe quel fil, jamais d'écriture."""
```

`game_teams` reprend la sélection de `scripts/backtest_draft_model.select`, qui l'importe ensuite. Noms de
champions : `Database.get_all_champion_names`, comme les scripts de mesure.

### 4.3 Entraînement

- `src/winprob/train.py` : `games()`, `load()` et `cross_validate()` prennent `draft_of: Callable[[dict, int],
  float]` (partie brute, file). Pour la file hors `analysis_config.BACKTEST_QUEUE_IDS` ou sans `game_teams`, 0.0.
  `train.report` et `retrain.retrain` ajustent sur `DRAFT_INPUTS`.
- Un seul évaluateur et une seule `Database` pour tout le réentraînement, sur `config.DATABASE_PATH` : 16 000
  parties ne peuvent pas passer par `read_logit` à chaque ligne.
- `games()` ajoute `queue_id` à son `SELECT` ; son filtre ne change pas.

### 4.4 En partie et overlay

- `overlay.Tracker.__init__(model, draft: float = 0.0)`, attribut public `draft`, passé à `state_from_live`.
- `client/ingame.LiveGame.__init__(..., draft_of: Callable[[dict], float] = lambda _data: 0.0)`. Dans `_read` : si
  `"draft" in model.inputs` et que le terme n'est pas encore connu pour cette partie, appel de `draft_of(data)`
  sous le `tick()` best-effort, valeur posée sur le tracker au premier retour non nul. Remis à zéro à la
  détection d'une autre partie (`src/client/ingame.py:188`).
- `client/launch.py` construit `draft_of` : `live_teams` puis `read_logit` sur `config.DATABASE_PATH`.
- `overlay.main` fait de même dans son fil `poll`, au même moment.

### 4.5 Courbe post-game

- `report.curve_points(model, game, timeline, team, draft: float = 0.0)`, passé à `frame_states`.
- `client/review.game_page(..., draft: float = 0.0)`, calculé dans `app.py` par une fonction
  `review.game_draft(db_path, record, roles, names)` mise en cache `functools.lru_cache` sur `game_id` : `game_teams`
  avec `repo.game_roles(game_id)`, puis `read_logit`. Seule la courbe en dépend, les lignes d'impact non.
- Le bench de la tâche 233 dit si l'ouverture d'une `Database` coûte trop à l'affichage ; le cache en est la parade.

### 4.6 Rattrapage des impacts

`WINPROB_IMPACT_CONVENTION` passe de 2 à 3 (`src/config_winprob.py`) : le réentraînement change les poids, et
`client/review._residual` n'affiche plus de résidu pour des lignes d'une autre version. Commentaire de la
constante complété : « 3 : modèle à draft, impacts à draft nulle ».

### 4.7 Tests à écrire

- `tests/test_winprob_draft_term.py` : `game_teams` et `live_teams` (dix postes, poste manquant, doublon, champion
  inconnu), `read_logit` sur base temporaire, 0.0 sur base absente, mtime de la base inchangé.
- `tests/test_winprob_state.py` (ou existant) : `frame_states` porte `draft`, `transitions` et `segments` à 0.
- **Neutralité** : pour un modèle à `DRAFT_INPUTS`, `impacts()` rend les mêmes lignes quelle que soit la draft de
  la partie.
- **Ancien modèle** : un `WinModel` sans `draft` prédit à l'identique avec et sans le champ.
- `LiveGame` : `draft_of` appelé une fois par partie, relancé après un changement de partie ; une exception de
  `draft_of` n'interrompt pas le relevé et laisse le terme à 0.
- `curve_points` : à draft positive, la courbe bleue démarre au-dessus de celle à draft nulle.

## 5. Tâches

| # | Tâche | Pts | Dépend de |
|---|---|---|---|
| 230 | `draft` dans l'état (`_Replay`, `walk`, `frame_states`, `state_from_live`), `DRAFT_INPUTS`, tests (§4.1, neutralité) | 2 | — |
| 231 | `src/winprob/draft_term.py` et `backtest_draft_model` branché dessus, tests (§4.2) | 3 | 230 |
| 232 | Entraînement et réentraînement avec la draft, tests (§4.3) | 3 | 231 |
| 233 | En partie, overlay et courbe post-game, bench d'ouverture, tests (§4.4, §4.5) | 3 | 231 |
| 234 | `WINPROB_IMPACT_CONVENTION` à 3, `docs/PROJECT_STRUCTURE.md`, `CHANGELOG.md`, statuts (§4.6) | 1 | 232, 233 |
| 235 | Réentraînement réel sur `crawl.db`, Brier et décile relevés en SPEC-47 §8, par @pj35 ou sur son accord | 2 | 234 |

## 6. Critères d'acceptation

1. `python -m pytest tests/ -v` vert, avec les tests du §4.7.
2. `python -m pytest tests/test_measure_form_term.py tests/test_rejudge_winchance_terms.py -q` vert sans y toucher :
   `INPUTS` n'a pas bougé.
3. Sans réentraînement, `data/winprob_model.json` en place : `impacts()` et la win chance rendent les mêmes valeurs
   qu'avant (test « ancien modèle »).
4. Un modèle à `DRAFT_INPUTS` rend des ΔP identiques pour deux valeurs de draft (test de neutralité).
5. `grep -n "draft" src/winprob/impact.py` ne trouve aucun passage de la draft aux `impacts`.
6. Aucune exception de `read_logit` ou `draft_of` ne remonte hors de `LiveGame.tick` (test).
7. `python -m src.winprob.retrain --force` : challenger accepté par `adopt`, `draft` dans ses `inputs`, ligne au
   journal `data/winprob_model.log`.
8. Après réentraînement, sur la validation du réentraînement : écart max par décile ≤ `WINPROB_GAP_MAX` et Brier
   ≤ 10 min inférieur à celui du modèle 16.19, chiffres consignés en §8.
9. `CHANGELOG.md` (`[Unreleased]`), statut de cette spec et `docs/specs/README.md` à jour.

**Vérification de bout en bout** : réentraîner, ouvrir une partie capturée à la draft déséquilibrée
(|logit| ≥ 0,3) dans la revue et lancer une partie réelle : les deux courbes démarrent à l'écart de 50 % annoncé
par la draft, et l'impact d'un kill reste celui d'avant à poids égaux.

## 7. Hors périmètre

- ❌ `form_impact` : indétectable sur 65 parties couvertes, remesure en fin de patch (SPEC-33 §7, tâche 161).
- ❌ La draft dans les ΔP (arbitrage du §2).
- ❌ Classement de pick et `predictions` : inchangés, un terme de win chance n'y touche pas (ADR-004).
- ❌ Nouveau réglage des K de draft sur ces mêmes parties (`scripts/backtest_draft_model.py` reste le passage obligé).
- ❌ Correction du tri par (probabilité, issue) de `measure_form_term.metrics` (SPEC-33 §7) : outil de mesure, sans
  effet sur cette spec.

## 8. Mesures

**Réentraînement du 2026-11-01** (`data/winprob_model.log`) : `wp-d819a71d` sur 16 224 parties 16.21, entrée `draft`
présente. Sur les parties récentes, images après 10 min : Brier 0,1498 → 0,1488, écart max par décile 2,4 → 2,1 pts.
Poids de la draft 1,24 à la première minute, 0,78 à 30 min. L'ancien modèle est gardé en
`data/winprob_model.backup-20261101.json`. Le critère 8 reste ouvert : le Brier ≤ 10 min de ce modèle n'est pas
relevé, et `adopt` ne regarde que les images après 10 min.

**Écarts entre l'implémentation et le §4**, sans effet sur les critères :

| §4 | Livré | Conséquence |
|---|---|---|
| `src/winprob/draft_term.py` | `src/winprob/draft.py` (`game_draft`, `recorded_draft`, `live_draft`, `reader`) | Tables gardées en mémoire tant que `db.db` ne change pas, au lieu d'ouvrir une `Database` à chaque lecture : le cache par `game_id` du §4.5 et son bench deviennent inutiles |
| `DRAFT_INPUTS`, champ posé par `_Replay` | `MODEL_INPUTS`, et `expand` prend `draft` à 0 si absent | `state.py` et `live.py` ne changent pas, ΔP neutres de la même façon |
| Noms via `resolve_champions` | `rawChampionName` direct | Vérifié sur `db.db` le 2026-11-01 : les noms en base sont les clés Riot (`MonkeyKing`, `Kaisa`), recherche en minuscules, donc `FiddleSticks` est trouvé. Logit en direct égal au calcul direct |
| `game_teams` partagé avec `backtest_draft_model` | Sélection propre à `game_draft` | Deux lectures des postes à garder alignées |
| `read_logit` | `Database.connect_read_only` (nouveau) | `connect` crée des index, cette lecture n'écrit rien (test) |

`draft_reader` lève si `db.db` ne se lit pas : un réentraînement à draft nulle silencieuse donnerait un poids nul.
Pas lu dans une partie réelle : la vérification de bout en bout du §6 était la recette de @pj35, validée le 2026-11-10.
