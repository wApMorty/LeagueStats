# SPEC-56 — Compétences, core et bottes du duel

**Statut** : ✅ Livrée le 2026-11-10 (tâches 278 à 281), recette @pj35 en partie réelle à faire. Arbitrages tranchés par @pj35 le 2026-11-10.

**Origine** : @pj35, 2026-11-10 — partie Malphite top contre Nasus (`game_id` 8041820924) : « le Client m'a suggéré le
mauvais Skill Order, et les items après le core build ne correspondaient pas au core build (qui était un peu particulier
dans cette game). […] selon OneTricks, les bottes font partie du Core Build, et certains matchups nécessitent de les faire
en first item, ce qui ne se voit pas dans l'import de build actuel ».

**Effort** : ~1,5 jour, 5 tâches (§5).

---

## 1. Constat

Mesuré le 2026-11-10 sur les pages OneTricks Malphite top (500 parties) et Malphite top contre Nasus (40 parties),
enregistrées réduites par `_trim` dans `tests/fixtures/onetricks_malphite_top.json` et
`tests/fixtures/onetricks_malphite_top_vs_nasus.json`. La timeline LCU de la partie (`game_records.raw_timeline`) ne
contient ni achats ni montées de compétences : la build affichée se reconstitue en rejouant `pick_build` et
`adapt_to_matchup` sur ces pages.

**1.1 L'ordre des compétences ignore le duel.** `LoadoutImporter._describe` appelle `_skills(page)`
(`src/draft/loadout_import.py:244`) avec la page **générale**, jamais celle du duel. Malphite : Q > E > W (55 % des
parties) affiché ; contre Nasus, le duel publie W > E > Q à 32 % de 40 parties (≈ 13 parties), absent des deux ordres
publiés en général (Q > E > W 55,5 %, Q > W > E 30,7 %, reste 13,8 %). Test binomial du duel, comme les objets :
P(X ≥ 13 | n = 40, p = 0,138) = 0,002, très sous `LOADOUT_MATCHUP_ALPHA` = 0,05. De plus, la montée (`levels`) est lue
dans `skillPaths[0]` (`loadout_import.py:66`), indépendamment de l'ordre de maximisation retenu ; chaque entrée de
`maxSkillOrders` publie pourtant ses propres `skillPaths`.

**1.2 Un core du duel sur 4 parties vide la suite du core.** Contre Nasus, `_significant` remplace le core général
Sunfire + Thornmail (18 %) par Eclipse + Jak'Sho : 9,7 % du duel, soit **4 parties**, p = 0,046 contre un plafond de
3,4 % (option non publiée en général). Sunfire + Thornmail reste le core le plus joué du duel (12,5 %, plus 8,1 % dans
l'ordre inverse, que `popCore` compte à part). Le chemin après Eclipse + Jak'Sho se lit sur la page du duel : 1 à 2
parties par objet, toutes sous `LOADOUT_PATH_MIN_GAMES` = 3 (`src/draft/loadout.py:168`), donc **« Situationnels » est
vide**. Les blocs « Composants » (Bami's Cinder, Chain Vest, Ruby Crystal, Bramble Vest) et « Autres cores » (Sunfire,
Thornmail, Frozen Heart, Kaenic Rookern) restent ceux de la build tank générale (`_item_blocks` lit `general_stats`,
`loadout.py:198`). D'où des objets d'après-core sans rapport avec le core proposé.

**1.3 Les bottes ne sont jamais dans le core.** `_item_blocks` place les bottes dans un bloc à part, après le core
(`loadout.py:238`) ; l'écran « En partie » vise le core puis la première paire de bottes (`src/client/en_partie.py:369`).
OneTricks publie pourtant, pour chaque paire de bottes, l'ordre d'achat jusqu'à elle (`bootsTimingSequences`, déjà
gardé par `_trim`) :

| Page | Bottes | Séquence | Rang des bottes |
|---|---|---|---|
| Malphite général | Plated Steelcaps (3047) | Boots (1001) → Sunfire → Steelcaps | 2e objet |
| Malphite vs Nasus | Plated Steelcaps (3047) | Steelcaps → Sunfire | **1er objet** |
| Malphite vs Nasus | Boots of Swiftness (3009) | Boots → Sunfire → Swiftness | 2e objet |
| Ambessa général | Ionian Boots (3158) | Eclipse → Boots → Death's Dance → Ionian | 3e objet |

Les pages Jinx enregistrées le 2026-09-25 ne publient pas `bootsTimingSequences`.

**1.4 Les bottes du duel.** Contre Nasus, Boots of Swiftness (16,7 % du duel contre 0,6 % en général) remplace
Steelcaps, qui reste à 60 % du duel : la règle de SPEC-15 §3.2.1 prend l'option la plus jouée parmi celles que le duel
sur-représente. Rien à changer (§2).

## 2. Objectif et arbitrages

Que la build du duel soit cohérente de bout en bout : l'ordre des compétences suit le duel quand il diffère
significativement, un core du duel n'est retenu que s'il a assez de parties pour qu'on lise sa suite, et les bottes
prennent leur rang dans le core, comme sur OneTricks.

| Sujet | Décision |
|---|---|
| Compétences du duel | **Validé (@pj35, 2026-11-10)** : même test binomial que les objets et les runes (`_best_option`, `LOADOUT_MATCHUP_ALPHA`) sur les ordres de maximisation ; substitution « Compétences » affichée avec sa raison ; la montée est celle de l'ordre retenu. |
| Core du duel | **Validé (@pj35, 2026-11-10)** : plancher de parties ; sous le plancher, le core général reste et celui du duel peut figurer dans « Autres cores » (via `_matchup_items`, inchangé). |
| Valeur du plancher | **Validé (@pj35, 2026-11-10)** : `LOADOUT_CORE_MIN_GAMES` = 9, soit 3 × `LOADOUT_PATH_MIN_GAMES` (assez pour qu'au moins une suite du core passe le filtre de 3 parties). Ne s'applique qu'au core : Swiftness (7 parties) reste substituée. |
| Bottes dans le core | **Validé (@pj35, 2026-11-10)** : les bottes retenues sont insérées dans le bloc Core à leur rang d'achat ; le bloc Bottes ne garde que les alternatives ; le « prochain objet » de l'écran En partie suit cet ordre. |
| Page de la séquence | **Validé (@pj35, 2026-11-10)** : la séquence des bottes retenues se lit sur la page du duel si elle la publie, sinon sur la page générale (« certains matchups » : c'est le duel qui dit « bottes en 1er »). Sans séquence publiée, les bottes vont après le core (comportement actuel du prochain objet). |
| Règle de substitution des bottes | **Validé (@pj35, 2026-11-10)** : inchangée. Contre Nasus, Swiftness en tête ; sa séquence la met en 2e objet. |

## 3. Approches considérées

**Compétences.** (A) test du duel, retenu : cohérent avec items et runes, et 40 parties de duel sont bruitées.
(B) toujours l'ordre du duel : bruit non contrôlé. (C) afficher les deux : laisse le choix au joueur en pleine partie.

**Core du duel.** (A) plancher de parties, retenu : supprime la cause (substitution sur 4 parties) au lieu de masquer
l'effet. (B) chemin non filtré en repli : remplit « Situationnels » avec des objets vus 1 ou 2 fois. (C) les deux : plus
de code pour un cas que (A) rend rare.

**Bottes.** (A) insérées dans le core, retenu : c'est la présentation OneTricks, et l'ordre du bloc Core devient l'ordre
d'achat. (B) bloc Bottes déplacé avant le core : deux règles d'ordre de blocs. (C) simple mention : le set d'items et le
prochain objet restent faux.

## 4. Détail

### 4.1 Compétences dans la build (`src/draft/loadout.py`, `src/draft/loadout_import.py`)

- `Build` gagne `skills: Optional[Tuple[Tuple[int, ...], float, Tuple[str, ...]]] = None` : (ordre de maximisation en
  indices 0-2 de `maxSkillOrders[i]["order"]`, part, montée en lettres). Défaut `None` : les `Build(...)` des tests
  existants restent valides.
- `_skill_options(stats) -> Dict[Tuple[int, ...], Tuple[float, Tuple[str, ...]]]` : chaque entrée de
  `maxSkillOrders` → (playrate, montée lue dans **son** `skillPaths[0][0]`, repli sur `stats["skillPaths"][0][0]` si
  vide). `{}` si la page ne publie rien.
- `pick_build` remplit `skills` avec l'ordre le plus joué de la page générale (premier de `maxSkillOrders`).
- `adapt_to_matchup` : nouvelle substitution de catégorie `"Compétences"` par `_best_option(category, chosen,
  general_shares, duel_shares, ceiling, duel_games)` ; `ceiling` calculé comme dans `_significant` :
  `max(min(min(parts), 1 − Σ parts), 1 / parties générales)`. Si elle passe, `build.skills` prend l'ordre, la part et la
  montée du duel.
- `option_name(page, "Compétences", option)` → `"W > E > Q"` (lettres `"QWER"[i]`).
- `loadout_import._skills` est supprimée ; `_describe` lit `build.skills` (même dict qu'aujourd'hui :
  `max_order`, `playrate`, `levels`), donc `en_partie.build_view` et le template ne changent pas. La ligne de
  substitution « Compétences » passe par `_describe` et `_report` comme les autres.

### 4.2 Plancher du core (`src/draft/loadout.py`, `src/config_constants.py`)

- `draft_config.LOADOUT_CORE_MIN_GAMES: int = 9` (commentaire : 3 × `LOADOUT_PATH_MIN_GAMES`, SPEC-56, à valider).
- Dans `adapt_to_matchup`, une substitution `"Core"` dont `round(duel_share × duel_games) < LOADOUT_CORE_MIN_GAMES`
  est écartée **avant** application (le core reste celui de la page générale, son chemin se lit sur 500 parties).

### 4.3 Bottes à leur rang dans le core (`src/draft/loadout.py`)

- `_boots_rank(sequence: List[int], boots: int, core_len: int) -> int` : nombre d'objets de la séquence avant `boots`,
  hors composant Boots (1001), plafonné à `core_len`. Constante `BOOTS_COMPONENT = 1001` en tête de module (id Riot,
  pas un réglage).
- `_item_blocks` reçoit `boots_rank: Optional[int]` : le bloc Core devient `core[:rang] + (bottes,) + core[rang:]`,
  titré `Core (18%, bottes 59%)` ; le bloc suivant devient `Autres bottes` (alternatives seules). `boots_rank=None`
  (aucune séquence) : bottes insérées après le core, mêmes titres.
- `pick_build` lit la séquence sur la page générale ; `adapt_to_matchup` sur la page du duel si
  `bootsTimingSequences` y contient les bottes retenues, sinon sur la générale.
- Aperçu de draft (`src/client/draft_loadout._items`, décision du plan d'implémentation) : il montre Départ et Core,
  bottes retenues comprises ; les alternatives (« Autres bottes ») restent dans le set d'items du client seulement.
- `Build` gagne `boots: Tuple[int, ...] = ()` : bottes retenues puis alternatives, exposées par
  `LoadoutImporter.state()` sous la clé `boots`.

### 4.4 Prochain objet en partie (`src/client/en_partie.py`)

- `build_view` vise les objets du bloc Core dans l'ordre ; une paire de bottes du core compte comme faite si le joueur
  possède **n'importe quelle** paire de `loadout["boots"]` (il a pris une alternative). Le bloc `Autres bottes` n'est
  jamais visé. `NEXT_BLOCKS`, inutilisée, est retirée.
- Un loadout d'avant SPEC-56 (sans clé `boots`, bloc « Bottes ») garde le comportement actuel : pas de migration de
  snapshot, le repli suffit.

### 4.5 Tests

- `tests/regression/test_regression_malphite_vs_nasus_build.py` (tâche 278, rouge avant le fix) : sur les deux
  fixtures Malphite, `adapt_to_matchup` donne `skills` W > E > Q (montée commençant par W), et une substitution
  « Compétences ».
- `tests/test_loadout.py` : ordre non publié en général (plafond), ordre publié non significatif (pas de substitution),
  page sans `maxSkillOrders` (`skills` None) ; plancher du core (Malphite vs Nasus : core Sunfire + Thornmail,
  « Situationnels » non vide) ; `_boots_rank` sur les quatre séquences de §1.3 ; blocs Core avec et sans séquence
  (Jinx) ; séquence lue sur le duel quand il la publie.
- `tests/test_client_en_partie_build.py` : bottes dans le core visées à leur rang ; alternative possédée = bottes faites ;
  loadout ancien format inchangé.
- Tests existants à adapter : titres « Bottes (…) » dans `test_loadout.py`, `test_loadout_lcu.py`,
  `test_client_draft.py`, `test_final_analysis_data.py`.

## 5. Tâches

| # | Tâche | Pts | Dépend de |
|---|---|---|---|
| 278 | Test de régression Malphite vs Nasus (rouge), compétences dans `Build` avec test du duel, `_skills` retirée, `option_name` « Compétences », tests §4.5 | 3 | — |
| 279 | Plancher `LOADOUT_CORE_MIN_GAMES` dans `adapt_to_matchup`, tests | 2 | — |
| 280 | Bottes à leur rang dans le bloc Core (`_boots_rank`, `_item_blocks`, `Build.boots`, séquence du duel), « Autres bottes », tests existants adaptés | 3 | 279 |
| 281 | Prochain objet en partie : bottes du core, alternative possédée, repli ancien format, tests | 2 | 280 |
| 282 | Clôture : CHANGELOG, statut SPEC-56, README des specs, recette @pj35 | 1 | 278-281 |

## 6. Critères d'acceptation

1. `python -m pytest tests/ -v` vert, avec les tests des tâches ci-dessus.
2. `python -m pytest tests/regression/test_regression_malphite_vs_nasus_build.py -v` vert, vérifié rouge avant le fix de la tâche 278.
3. Sur les fixtures Malphite, `adapt_to_matchup(general, duel)` renvoie : `skills[0] == (1, 2, 0)` ; bloc
   `Core (…)` = Sunfire (3068), Boots of Swiftness (3009), Thornmail (3075) dans cet ordre ; bloc « Situationnels » non
   vide ; aucune substitution « Core ».
4. `pick_build` sur la fixture Malphite générale : bloc Core = Sunfire, Plated Steelcaps, Thornmail ; sur
   `onetricks_jinx_bot.json` (sans séquence) : bottes après le core.
5. `grep -n "LOADOUT_CORE_MIN_GAMES" src/config_constants.py` renvoie la constante, commentée avec son origine.
6. `grep -n "def _skills(" src/draft/loadout_import.py` ne renvoie rien (remplacée par `_skills_detail`).
7. `CHANGELOG.md` (`[Unreleased]`), statut de cette spec et `docs/specs/README.md` à jour.

**Vérification de bout en bout** : recette @pj35 en partie réelle avec un duel publié (idéalement Malphite contre
Nasus) : la console affiche la substitution « Compétences », le set d'items du client montre les bottes dans le bloc Core
à leur rang, et l'écran « En partie » vise les objets dans cet ordre.

## 7. Hors périmètre

- ❌ Fusionner les cores de même contenu dans un ordre différent (Sunfire + Thornmail / Thornmail + Sunfire) : l'ordre
  porte une information (premier objet), et le plancher règle le cas observé. À rouvrir si un autre cas apparaît.
- ❌ Changer la règle de substitution de SPEC-15 §3.2.1 (option sur-représentée plutôt que la plus jouée) : tranché
  le 2026-11-10.
- ❌ Composants dérivés du core (Data Dragon `from`) : « Composants » reste `componentBuildPaths` de la page générale.
- ❌ Pousser l'ordre des compétences dans le client : le LCU n'a pas d'endpoint pour cela.
