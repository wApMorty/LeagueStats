# SPEC-35 — Étude « Moneyball » du début de partie

**Statut** : 🟡 Rédigée le 2026-10-20. Valorisation, vision, référence, mort évitable, seuil, livrable, rôles et
fenêtre validés par @pj35 le 2026-10-20 (§2). Reste à valider la spec dans son ensemble avant `/implement`.

**Origine** : @pj35, 2026-10-20 : étude « Moneyball » pour savoir quelles actions des 10 à 15 premières minutes
(CS, vision, morts évitables, présence aux objectifs) font le plus monter la win chance, et sur lesquelles il est le
plus loin de la moyenne de son rang. Données : `crawl.db`, impact ΔP de SPEC-20, modèle de partie de SPEC-33. Seuil
d'adoption fixé avant la mesure.

**Effort** : ~3 jours, 6 tâches (171 à 176), 21 pts (§5), dont une tâche conditionnelle.

---

## 1. Constat

Mesuré le 2026-10-20 sur `data/crawl.db` (ouverte en `mode=ro`) et `data/db.db`.

**Données tierces.** `crawl.db` contient 90 085 parties lues (`read_utc` non nul), toutes au patch 16.20, créées du
2026-10-07 au 2026-10-19. 81 310 sont en solo/duo (`queue_id` 420), 8 775 en flex. En solo/duo, 5 086 sont de
profondeur 1 (joueurs croisés par @pj35) et 76 224 de profondeur 2. Le spike du 2026-10-20 (2v2, `TODO.md`) en
gardait 78 163 avec les dix postes connus. Chaque `raw` est `zlib(JSON)` de `{"game", "timeline"}` au format LCU
(`src/winprob/crawl.py:105`), comme les parties de @pj35 dans `db.db`.

**Ce que la timeline permet de mesurer avant 14 min.**

- **CS** : `participantFrames[*].minionsKilled + jungleMinionsKilled`, une image par minute (`metrics._cs`).
- **Morts** : événements `CHAMPION_KILL` avec tueur, assistants et instant à la milliseconde. La mort solo de
  SPEC-19 (`solo_deaths` : tueur seul, sans assistant) vaut sur toute la partie (`src/coaching/metrics.py:197`).
- **Objectifs** : `ELITE_MONSTER_KILL` (dragons, larves, Héraut) avec position. La présence de SPEC-20 compte le
  tueur, les assistants et les coéquipiers à moins de `WINPROB_PRESENCE_RADIUS` (2 500) à l'image la plus proche
  (`src/winprob/impact.py:52`, `_present`). La présence de SPEC-19 (`objective_presence`) ne compte que tueur et
  assistants, sur toute la partie.
- **Vision : rien.** Une partie relevée ne contient que `CHAMPION_KILL` (54), `BUILDING_KILL` (14) et
  `ELITE_MONSTER_KILL` (9). Aucun événement de ward, ce que SPEC-20 §1 relevait déjà (« Ni achats d'items, ni
  wards »). Seuls `visionScore`, `wardsPlaced`, `wardsKilled` et `visionWardsBoughtInGame` existent, en fin de
  partie, donc confondus avec la durée et l'issue.

**Le rang n'est pas connu.** `highestAchievedSeasonTier` est vide dans les parties lues et `crawl_histories` n'a
pas de rang. Le crawl part des parties de @pj35 et s'en éloigne en profondeur, mais rien ne dit à quel rang.

**Le modèle de SPEC-20 ne valorise ni les CS ni la vision.** Ses variables (`src/winprob/model.py:20`, `INPUTS`)
sont kills, tours, inhibiteurs, dragons, âme, Héraut, larves, Baron, Ancien, niveaux et morts. Les CS en sont
sortis (`creepScore` de la Live Client API arrondi, perte de 0,001 de Brier). L'impact de SPEC-20 donne donc un
ΔP aux morts (`death`, `death_solo`) et aux objectifs perdus en l'absence du joueur (`lost_<k>`), mais aucun aux
CS. Il ne peut pas valoriser seul les quatre actions demandées.

**@pj35.** 139 parties classées dans `game_records` (2026-09-24 au 2026-10-19), dont 135 analysées, toutes au
top. Dernier rang relevé : Diamant III 72 LP (`rank_snapshots`, 2026-10-19), avec passage par Émeraude I. La
norme de SPEC-19 (`src/coaching/grid.py:3`) est déjà « les autres joueurs du même poste dans tes parties » : au
top, c'est l'adversaire de lane, de même MMR par construction du matchmaking.

**Précédents.** Deux pistes ont été mesurées puis écartées avec un seuil figé d'avance : l'a priori de draft
(2026-10-19) et la draft au seul matchup 2v2 (2026-10-20, `TODO.md` « Hors périmètre »). Le terme de forme de
SPEC-33 attend sa couverture. La mémoire du projet note un piège : des parties d'un même joueur ne sont pas
indépendantes, ce qui gonfle une p-value.

## 2. Objectif et arbitrages

Classer les actions des 14 premières minutes par les points de win chance que @pj35 y laisse par partie (valeur
de l'action × son écart à ses adversaires de lane). Adopter la première comme axe de travail si elle passe un seuil
figé avant la mesure, sinon consigner l'étude comme écartée.

| Sujet | Décision |
|---|---|
| Valorisation | **Validé (@pj35, 2026-10-20)** : une logistique dédiée, par rôle. L'issue de la partie est expliquée par les actions à 14 min, en écart bleu − rouge entre adversaires de lane. Coefficient × une unité = points de win chance. Le ΔP de SPEC-20 sert de recoupement pour les morts et les objectifs, sans entrer dans la décision. |
| Vision | **Validé (@pj35, 2026-10-20)** : hors classement. Mesurée sur la partie entière (`visionScore` / min), imprimée à part avec l'avertissement du §1, jamais classée ni adoptée. |
| Référence de l'écart | **Validé (@pj35, 2026-10-20)** : ses adversaires de lane dans ses parties classées (`game_records`). L'écart de @pj35 est la moyenne de (lui − son adversaire) ; même MMR par construction, c'est la norme de SPEC-19. |
| Mort évitable | **Validé (@pj35, 2026-10-20)** : deux définitions, mesurées côte à côte. **Mort solo** : tueur seul, sans assistant (définition de SPEC-19), avant 14 min. **Mort sans contrepartie** : aucun kill de son équipe ni objectif marqué par elle (monstre épique ou bâtiment) à ± `MONEYBALL_TRADE_WINDOW_S` (20 s) de la mort. |
| Rôles valorisés | **Validé (@pj35, 2026-10-20)** : les cinq rôles, un modèle par rôle. L'écart de @pj35 et l'adoption ne portent que sur les rôles où il a au moins `MONEYBALL_MIN_PLAYER_GAMES` (30) parties : le top aujourd'hui. |
| Fenêtre | **Validé (@pj35, 2026-10-20)** : 14 min (`coaching_config.LANE_MINUTE`, déjà utilisée par `cs_14` et `deaths_before_14`). Objectifs couverts : larves et premiers dragons ; le Héraut en est exclu. |
| Seuil d'adoption | **Validé (@pj35, 2026-10-20)**, figé avant la mesure. Une action est adoptée si les trois conditions tiennent : (1) son effet a un IC95 qui exclut 0 et le même signe dans les 5 blocs de la validation croisée ; (2) l'écart de @pj35 à ses adversaires a un IC95 bootstrap qui exclut 0 ; (3) le gain attendu (écart × effet, orienté) vaut au moins **1 pt de win chance par partie** (`MONEYBALL_GAIN_MIN_PTS`). Préalable : le modèle du rôle bat la constante en Brier, en validation croisée. Si plusieurs actions passent, la première au gain attendu est adoptée. |
| Livrable | **Validé (@pj35, 2026-10-20)** : le script de mesure, puis le résultat consigné dans cette spec (§8) et le `TODO.md`. Une tâche conditionnelle (176) propose l'action adoptée comme axe dans l'accueil du coaching (SPEC-29), chiffrée en points de win chance. Si rien n'est adopté, l'étude rejoint « Hors périmètre (tranché) » du `TODO.md` et la tâche 176 est abandonnée. |

## 3. Approches considérées

| Approche | Pour | Contre |
|---|---|---|
| **A. ΔP de SPEC-20 seul** : somme des lignes d'impact par type avant 14 min | Aucun modèle de plus, cohérent avec le post-game | Pas de valeur pour les CS (hors modèle) ni pour la vision : deux des quatre actions demandées tombent |
| **B. Réentraîner le modèle d'état avec les CS** de la timeline, lire leur ΔP | Une seule échelle, celle de la courbe | Touche `src/winprob/` et le modèle en place ; l'API live arrondit les CS, donc ce modèle ne servirait qu'après la partie |
| **C. Logistique dédiée par rôle** sur les actions à 14 min (retenue) | Valorise les quatre actions sur la même échelle ; hors du modèle en place ; une ligne par partie et par rôle | Effet corrélationnel : un joueur qui farme mieux joue souvent mieux ailleurs. L'écart à l'adversaire de lane retire une partie du biais, pas tout |

**Retenue : C**, validée par @pj35. A sert de recoupement pour les morts et les objectifs. Les écarts d'or et d'XP
sont exclus des variables : ce sont des conséquences des actions (CS, kills), pas des actions. Les mettre dans le
modèle absorberait l'effet des CS.

**Une ligne par partie et par rôle.** Les deux tops d'une partie donnent des lignes miroirs (écart opposé, issue
opposée). On garde donc la ligne bleue : écart bleu − rouge, issue = victoire bleue, l'avantage du côté bleu va
dans le biais.

## 4. Détail

### 4.1 Actions par partie : `src/coaching/moneyball.py` (nouveau)

Fonctions pures, sans base ni réseau, sur le format LCU commun à `crawl.db` et `game_records`.

```python
ACTIONS = ("cs", "deaths", "solo_deaths", "untraded_deaths", "presence")

def player_actions(game: dict, timeline: dict, minute: int) -> Dict[int, Dict[str, float]]:
    """participantId -> actions à `minute` : CS, morts, morts solo, morts sans contrepartie, présence
    aux objectifs (part des monstres épiques de son équipe avant `minute` où il est présent). Plus
    `vision` (visionScore / min de partie entière, hors classement)."""

def lane_rows(game: dict, timeline: dict, minute: int) -> Dict[str, Dict[str, float]]:
    """Rôle -> écarts bleu − rouge des actions entre adversaires de lane. Vide si un poste manque
    (`participant_roles`), si la partie est un remake ou dure moins de `MONEYBALL_MIN_DURATION_MIN`."""

def player_gaps(game: dict, timeline: dict, eog: Optional[dict], player_pid: int, minute: int
) -> Optional[Tuple[str, Dict[str, float]]]:
    """(rôle, écarts joueur − adversaire de lane) pour une partie de @pj35, None si incalculable."""
```

- Réutilise `metrics.participant_roles`, `metrics.is_remake`, `metrics._frame`, `metrics._events` et
  `metrics._cs`.
- La présence réutilise la règle de SPEC-20 : tueur, assistants ou rayon `WINPROB_PRESENCE_RADIUS`. `_present`
  (`src/winprob/impact.py:52`) devient public (`present`), sans autre changement, et `impact.py` l'appelle sous
  son nouveau nom.
- Présence sans monstre de son équipe avant 14 min : 0 (pas d'objectif, pas d'absence). Le dénominateur vaut
  au moins 1.
- Mort sans contrepartie : kill par un joueur de son équipe, ou `ELITE_MONSTER_KILL` / `BUILDING_KILL` marqué par
  son équipe (`impact.scoring_team`), dans `[t − W, t + W]` avec W = `MONEYBALL_TRADE_WINDOW_S`.

### 4.2 Valorisation : `moneyball.value_actions`

```python
class Effect(NamedTuple):
    action: str
    pts_per_unit: float  # points de win chance pour +1 unité d'écart (effet marginal moyen × 100)
    ci_low: float
    ci_high: float
    same_sign_folds: int  # blocs de la validation croisée où le coefficient a le signe global

def value_actions(rows: List[Dict[str, float]], wins: List[int], folds: int) -> dict:
    """Trois variantes de la logistique, un rôle : effets, Brier en validation croisée (modèle et constante)."""
```

- Trois variantes, pour que les morts emboîtées ne soient jamais ensemble dans le même modèle :
  - V1 : `cs`, `deaths`, `presence` (valorise `cs`, `deaths`, `presence`) ;
  - V2 : `cs`, `solo_deaths`, `deaths − solo_deaths`, `presence` (valorise `solo_deaths`) ;
  - V3 : `cs`, `untraded_deaths`, `deaths − untraded_deaths`, `presence` (valorise `untraded_deaths`).
- Ajustement par `src/winprob/model.fit` avec des états au `time_min` nul. Les produits avec le temps sont alors
  nuls : leur écart-type vaut 1 (`or 1.0`) et la pénalité `WINPROB_L2` laisse leurs poids à 0. Aucun nouveau
  solveur.
- Effet marginal moyen : `β / scale × moyenne de p(1 − p)` sur les lignes, × 100 pour des points.
- IC95 de Wald : covariance = inverse de la hessienne complète à l'optimum, calculée sur toutes les lignes (pas le
  sous-échantillon de `fit`), avec `model._solve` colonne par colonne. Contre la dépendance entre parties d'un même
  joueur, il faut en plus le même signe dans les `MONEYBALL_CV_FOLDS` blocs (§2, condition 1).
- Validation croisée à 5 blocs contigus, prédictions poolées, comme SPEC-33. Brier du modèle V1 contre la
  constante (taux de victoire bleue du bloc d'entraînement).
- Vision : V1 + `vision`, ajusté à part, imprimé sous le classement avec l'avertissement du §1.

### 4.3 Écart de @pj35 et décision : `moneyball.player_gap`, `moneyball.decide`

```python
def player_gap(gaps: List[Dict[str, float]], resamples: int, seed: int) -> Dict[str, Tuple[float, float, float]]:
    """Action -> (moyenne, IC95 bas, IC95 haut) de l'écart joueur − adversaire, bootstrap des parties."""

def decide(effects: Dict[str, Effect], gap: dict, brier: dict, gain_min: float) -> List[dict]:
    """Une ligne par action classée par gain attendu décroissant : effet, écart, gain attendu
    (écart × effet, en points), conditions 1 à 3 et adoption. Rien n'est adopté si le modèle
    ne bat pas la constante."""
```

- Gain attendu = −écart × `pts_per_unit` : positif quand @pj35 est du mauvais côté de ses adversaires (moins de
  CS, plus de morts), c'est-à-dire les points qu'il laisse par partie.
- Graine fixe (`MONEYBALL_SEED`) : deux exécutions donnent le même tableau.

### 4.4 Script : `scripts/measure_moneyball.py` (nouveau)

Même forme que `scripts/measure_form_term.py` : `crawl.db` et `db.db` ouvertes en `mode=ro`, Live Coach ouvert
toléré. Ce n'est pas un test : les chiffres dépendent des bases.

```
python scripts/measure_moneyball.py                  # mesure complète
python scripts/measure_moneyball.py --limit 5000     # sur les 5 000 parties les plus récentes (essai)
```

1. Parties lues de `crawl.db` en solo/duo (`queue_id` 420), dix postes connus, durée ≥ 15 min, hors remake ; les
   parties où @pj35 joue (puuid de `game_records`) sont exclues. Une ligne par rôle et par partie (`lane_rows`).
2. `value_actions` par rôle ; tableau par rôle : effet par unité, IC95, signes sur 5 blocs, Brier modèle et
   constante.
3. Parties de @pj35 (`game_records`, solo/duo, avec timeline) : `player_gaps`, puis `player_gap` sur chaque rôle
   où il a au moins `MONEYBALL_MIN_PLAYER_GAMES` parties.
4. `decide` et tableau Moneyball : action, écart de @pj35, effet, gain attendu, conditions, verdict. Vision en
   dessous, hors classement.
5. Recoupement SPEC-20 sur les `MONEYBALL_IMPACT_SAMPLE` parties les plus récentes : ΔP moyen d'une mort (`death`,
   `death_solo`) et d'un objectif perdu absent (`lost_dragon`, `lost_grubs`) avant 14 min, par rôle, avec le
   modèle en place (`train.load_model`). Biais imprimé : le modèle a été entraîné sur ces parties.
6. Progression tous les `PROGRESS_EVERY` parties, sortie console sans emoji (`[INFO]`, `[DATA]`, `[OK]`).

### 4.5 Constantes : `src/config_coaching.py` (réexporté par `config_constants.py`)

| Constante | Valeur | Origine |
|---|---|---|
| `MONEYBALL_TRADE_WINDOW_S` | 20.0 | Mort sans contrepartie, validé par @pj35 le 2026-10-20 |
| `MONEYBALL_GAIN_MIN_PTS` | 1.0 | Seuil d'adoption, validé par @pj35 le 2026-10-20 |
| `MONEYBALL_MIN_PLAYER_GAMES` | 30 | Plus petit échantillon où un IC95 bootstrap de moyenne reste lisible ; @pj35 en a 135 au top |
| `MONEYBALL_MIN_DURATION_MIN` | 15 | Il faut l'image de 14 min et une partie jouée au-delà |
| `MONEYBALL_CV_FOLDS` | 5 | Validation croisée de SPEC-20 §4.3 bis et SPEC-33 |
| `MONEYBALL_BOOTSTRAP` | 10 000 | Rééchantillonnages de l'écart de @pj35 (135 parties, coût négligeable) |
| `MONEYBALL_SEED` | 35 | Reproductibilité du bootstrap |
| `MONEYBALL_IMPACT_SAMPLE` | 5 000 | Recoupement SPEC-20 : `impacts` coûte 11 ms par partie, décompression comprise (mesuré le 2026-10-20 sur 100 parties), ~1 min pour 5 000 |

La minute vient de `coaching_config.LANE_MINUTE` (14), sans nouvelle constante.

### 4.6 Tests : `tests/test_coaching_moneyball.py` (nouveau)

Hermétiques, sur parties construites à la main (format de `tests/test_winprob_impact.py`) :

1. `player_actions` : CS à 14 min, morts avant 14 seulement, mort solo, présence par rayon et par assistance.
2. Mort sans contrepartie : un kill allié à 15 s rend la mort échangée, à 25 s non ; un dragon allié aussi.
3. `lane_rows` : écarts bleu − rouge par rôle ; vide si un poste manque, si remake ou si moins de 15 min.
4. `value_actions` sur données synthétiques où l'issue dépend des CS seuls : effet `cs` positif, IC qui exclut 0,
   5 signes sur 5 ; effet `presence` dont l'IC contient 0 ; Brier du modèle sous la constante.
5. `player_gap` : moyenne exacte, IC qui contient la moyenne, même résultat à graine égale.
6. `decide` : adoption seulement si les trois conditions tiennent ; rien d'adopté si le modèle ne bat pas la
   constante ; classement par gain attendu.
7. `scripts/measure_moneyball.py` sur deux bases SQLite temporaires (fixtures de `tests/conftest.py`, jamais
   `data/`) : tableau imprimé, aucune écriture dans les bases (`mode=ro`).

### 4.7 Tâche conditionnelle 176 : l'axe Moneyball dans l'accueil du coaching

Seulement si la tâche 175 adopte une action. Détail à reprendre selon l'action adoptée :

- Métrique de l'action dans `METRICS` (`src/coaching/metrics.py`) si elle n'y est pas (par exemple
  `untraded_deaths_14`), calculée par `compute_metrics` via `moneyball.player_actions` ; `GRID_VERSION` + 1
  (recalcul au démarrage).
- Constantes du résultat dans `config_coaching.py` : `MONEYBALL_ACTION` (métrique), `MONEYBALL_PTS_PER_UNIT`
  (effet mesuré) et la date de mesure en commentaire.
- `goals.next_proposal` : troisième étage, entre le schéma négatif net et l'écart à l'objectif. Il propose
  `MONEYBALL_ACTION` (`reference="norm"`, `net=False`, donc proposé d'un clic, jamais fixé seul), avec le gain
  attendu en texte : « ≈ N pts de win chance par partie ».
- Tests : la proposition apparaît quand la place est libre et qu'aucun schéma net ne la précède ; elle ne
  s'active pas seule.

## 5. Tâches

| # | Tâche | Pts | Dépend de |
|---|---|---|---|
| 171 | `src/coaching/moneyball.py` : `player_actions`, `lane_rows`, `player_gaps` ; `impact._present` rendu public ; tests 1 à 3 | 3 | — |
| 172 | `value_actions` : trois variantes, effet marginal, IC95 de Wald, signes sur 5 blocs, Brier en validation croisée contre la constante ; constantes §4.5 ; test 4 | 5 | 171 |
| 173 | `player_gap` et `decide` (bootstrap à graine fixe, gain attendu, seuil) ; tests 5 et 6 | 3 | 172 |
| 174 | `scripts/measure_moneyball.py` (§4.4) avec recoupement SPEC-20 et vision hors classement ; test 7 ; essai `--limit 5000` | 3 | 173 |
| 175 | Mesure réelle, résultat consigné en §8, `TODO.md` (lot, ou « Hors périmètre » si rien n'est adopté), `CHANGELOG.md`, statut, README des specs | 2 | 174 |
| 176 | *Conditionnelle* : axe Moneyball proposé dans l'accueil du coaching (§4.7) | 5 | 175 |

## 6. Critères d'acceptation

1. `python -m pytest tests/test_coaching_moneyball.py -v` vert (7 tests du §4.6), puis `python -m pytest tests/ -v`
   vert.
2. `python -m pytest tests/test_winprob_impact.py -v` vert après le passage de `_present` à `present`
   (comportement inchangé).
3. `grep -n "MONEYBALL_" src/config_coaching.py` montre les huit constantes du §4.5 ; aucune valeur de réglage en
   dur dans `src/coaching/moneyball.py` ni dans le script.
4. `python scripts/measure_moneyball.py --limit 5000` se termine et imprime, par rôle, l'effet par unité, l'IC95,
   les signes sur 5 blocs et le Brier (modèle et constante) ; puis le tableau Moneyball de @pj35 avec ses
   conditions et son verdict ; puis la vision sous le classement.
5. Deux exécutions identiques impriment le même tableau (graine fixe).
6. Après une exécution, `crawl.db` et `db.db` ont la même date de modification (lecture seule).
7. Le seuil du §2 n'a pas changé entre la rédaction et la mesure : `git log -p docs/specs/SPEC-35-*.md` ne montre
   aucune modification du §2 postérieure au commit de la tâche 174.
8. §8 rempli (chiffres de la mesure complète, verdict) ; `TODO.md`, `CHANGELOG.md` (`[Unreleased]`), statut de
   cette spec et `docs/specs/README.md` à jour.
9. *Si la tâche 176 est ouverte* : `python -m pytest tests/test_coaching_progression.py tests/test_client_accueil.py -v`
   vert avec les tests du §4.7, et l'accueil propose l'axe avec son gain en points.

**Vérification de bout en bout** : `python scripts/measure_moneyball.py` sur les vraies bases, Live Coach ouvert
ou non, puis la lecture du tableau Moneyball avec @pj35. L'action adoptée (ou l'absence d'adoption) se décide sur
ce tableau seul.

## 7. Hors périmètre

- ❌ Vision avant 14 min : la timeline LCU n'a pas d'événement de ward (§1). La Live Client API n'a qu'un
  `wardScore` cumulé. Une capture en partie de ce score pour @pj35 seul resterait sans population de comparaison.
- ❌ Écarts d'or et d'XP comme actions : ce sont des résultats (§3).
- ❌ Rang des joueurs de `crawl.db` lu par le LCU : de nouvelles requêtes pour une référence que les adversaires de
  lane donnent déjà, à MMR égal (§2).
- ❌ Changer le modèle de win chance en place (approche B du §3) : l'étude ne touche pas `src/winprob/model.py`.
- ❌ Causalité : l'effet mesuré est corrélationnel. Le verdict dit « les parties où l'on fait X se gagnent plus »,
  pas « faire X fait gagner ». L'écart à l'adversaire de lane retire une partie du biais de niveau, pas tout.
- ❌ Ligne par partie dans le post-game (« pts laissés sur l'action adoptée ») : non demandée, à proposer après la
  tâche 176 si l'axe sert.

## 8. Résultat de la mesure

*À remplir par la tâche 175.*
