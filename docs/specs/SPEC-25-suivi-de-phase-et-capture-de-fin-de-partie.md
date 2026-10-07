# SPEC-25 — Suivi de phase de jeu et capture de fin de partie

**Statut** : 🟡 Rédigée le 2026-10-07. Source de phase, déclencheur de la capture, périmètre dans le client
et spike validés par @pj35 (§2) ; la cause exacte de la perte des LP reste une hypothèse jusqu'au spike (tâche 112).

**Origine** : @pj35, 2026-10-07 : « le live coach --client ne détecte plus les gains/pertes de LP […] Il est
important qu'on sache à tout moment si on est en champ select, dans une fin de game, ou en game. Ça mérite
peut-être une feature et une spec à part entière. »

**Effort** : ~3 jours, 7 tâches, 24 pts (§5).

---

## 1. Constat

Mesuré le 2026-10-07 (`data/db.db` ouverte en lecture seule, `logs/draft_monitor_memory.log`, lecture de code).

- **Les LP ne sont plus capturés depuis le 2026-10-05 à 17:42 UTC.** Dernière ligne de `rank_snapshots` avec
  `game_id` : 2026-10-05 17:42:22 (partie 8004727582, +19 LP). Depuis, **11 parties** sont dans `game_records`,
  aucune avec `raw_eog` (dernier `raw_eog` : partie du 2026-10-05 17:09 UTC) ni avec photo de fin de partie.
- **Le reste de l'après-partie marche.** Ces 11 parties ont été capturées par l'historique 2 à 4 minutes après
  leur fin (`captured_utc` − fin de partie, ex. 8005122344 : fin 23:06:13, capture 23:10:14 UTC), et les 6
  8 d'entre elles ont leur prédiction (`predictions`, `game_id` renseigné) : le Live Coach voyait la draft et
  restait connecté jusqu'à la capture. Ne manquent que les deux lectures **transitoires** de `capture.py` :
  `get_end_of_game_block` (`remember_end_of_game`) et `get_lp_change_notification` (`snapshot_after_game`),
  qui ne répondent que sur l'écran de fin (SPEC-19 §spike, question 6 : `{}` ensuite).
- **La lecture transitoire dépend de la vitesse d'un tour du monitor.** `retry_post_game`
  (`src/draft/lifecycle.py:125-140`) ne passe qu'une fois par `POST_GAME_RETRY_INTERVAL` (5 s), dans la boucle
  du monitor. Cadence de cette boucle (`logs/draft_monitor_memory.log`, 300 tours par ligne) : 1,01 s/tour le
  2026-10-01, ~1,6 s dès le 2026-10-02 (collecte SPEC-20), **2 à 5 s/tour depuis le 2026-10-05 vers 21 h 30
  locales** (pics à 4,7 et 5,2 s). Une lecture toutes les 6 à 10 s rate un écran de fin quitté par « Rejouer »
  (`draft_monitor.py:132-137` le dit déjà : « 'Play Again' leaves the end-of-game phases within seconds »).
- **La cause du ralentissement n'est pas établie.** Vérifié : la purge de `crawl.db` (481 Mo, 31 068 parties)
  prend 0,3 s une fois chaude (1,7 s la première), `_step` 0,08 s : ce n'est pas elle.
- **La phase est lue en plusieurs endroits, par sondage, sans source commune.** Par tour du monitor : jusqu'à
  **3 lectures** de `/lol-gameflow/v1/session` (`lifecycle.py:37` `is_in_ready_check` si auto-accept, `:40`
  `is_in_champion_select`, `:61` `get_gameflow_session`) puis la collecte. Ailleurs : `LiveGame` sonde la phase
  toutes les 1 à 5 s via `LcuProbe` (`launch.py:99-102`, `ingame.py:146`), `found.py:14` et `lobby.py:16` la
  lisent à chaque requête de page. Le WebSocket LCU suit déjà `/lol-gameflow` (`config_client.py:197-205`,
  `lcu_events.py`) et publie sur le bus (sujet `lcu`), **mais personne n'en tire la phase**.
- **Les erreurs de capture sont muettes.** `GameCapture._safely` n'affiche rien hors `-v`
  (`capture.py:217-222`) : une exception dans `remember_end_of_game` ou `snapshot_after_game` n'est pas
  distinguable d'un écran de fin manqué.
- **Les connexions SQLite ne sortent pas du fil du Live Coach** (`launch.py:68`) : une capture lancée depuis
  un autre fil ne peut pas écrire dans `data/db.db` avec la connexion du coach.

## 2. Objectif et arbitrages

**Objectif** : une source unique de la phase de jeu (champ select, fin de partie, en partie…), instantanée,
partagée par le Live Coach et le client, et une capture des LP et de l'écran de fin qui ne dépend plus de la
vitesse de la boucle du monitor.

| Sujet | Décision |
|---|---|
| Source de la phase | **Validé (@pj35, 2026-10-07)** : un `PhaseTracker` alimenté par les événements `/lol-gameflow` du WebSocket LCU (déjà reçus par `LcuEvents`, bus `lcu`), avec un sondage lent de rattrapage et en mode console (sans client, donc sans WebSocket). Remplace les trois lectures par tour du monitor et la sonde de `LiveGame`. |
| Déclencheur de la capture | **Validé (@pj35, 2026-10-07)** : la **transition de phase** vers la fin de partie lance la lecture des deux endpoints transitoires, relancée chaque seconde tant que la phase dure, **hors de la boucle du monitor**. Les lectures sont mises de côté en mémoire (comme `_eog_by_game`) ; l'écriture en base reste dans le fil du coach. |
| Événement `/lol-ranked` du WebSocket | **Validé (@pj35, 2026-10-07)** : écarté comme source principale ; la tâche 117, **conditionnelle** au spike, ne le lit que s'il porte la notification de LP. |
| Périmètre dans le client | **Validé (@pj35, 2026-10-07)** : sujet `phase` sur le bus **et** pastille permanente dans la barre de titre. SPEC-23 (collecte : `step(phase)`) et SPEC-24 (écran « En partie ») la consomment. |
| Spike | **Validé (@pj35, 2026-10-07)** : un relevé en lecture seule d'une fin de partie réelle (événements WebSocket, phases, durée de disponibilité des deux endpoints) avant d'implémenter. |
| Erreurs de capture muettes | **Validé (@pj35, 2026-10-07)** : afficher une fois chaque erreur distincte en `[ALERTE]` même hors `-v` (le Live Coach reste best-effort : rien n'est levé). |
| Cadence de rattrapage | **Validé (@pj35, 2026-10-07)** : `PHASE_POLL_S = 2,0` hors fin de partie, `PHASE_POST_POLL_S = 1,0` en fin de partie ; à confirmer sur le relevé de la tâche 112. |
| Ralentissement de la boucle (2 à 5 s/tour) | **Validé (@pj35, 2026-10-07)** : non traité ici (cause non établie, §1). Avec le tracker le tour perd 2 lectures sur 3, et la capture n'en dépend plus ; si la lenteur persiste, un constat chiffré par étape du tour fait l'objet d'une tâche à part. |

## 3. Approches considérées

- **A. Constante seule** : réduire `POST_GAME_RETRY_INTERVAL`. Un tour du monitor dure 2 à 5 s : la lecture reste
  tributaire de la boucle, et aucune source de phase n'existe. Écartée.
- **B. Sondeur unique partagé** : un fil lit `gameflow-phase` chaque seconde et alimente tout. Simple, sans
  dépendance au WebSocket, mais une requête par seconde en permanence et une latence d'une seconde au mieux.
  Gardée comme **repli** de A.
- **C. Événementiel + repli (retenue)** : le WebSocket donne la phase à l'instant du changement ; le sondage
  lent rattrape un événement manqué, une reconnexion, et couvre le mode console. La capture est dans un fil
  à elle, cadencée par la phase, donc insensible à la boucle du monitor. Compromis : le WebSocket n'a pas été
  observé sur une fin de partie complète (d'où la tâche 112 d'abord), et le tracker ajoute un fil.

## 4. Détail

### 4.0 Relevé du spike (tâche 112, partie classée perdue, 2026-10-07)

`scripts/dump_lcu_endgame.py`, 1 689 s de relevé (file, champ select, partie, fin de partie), fixtures dans
`tests/fixtures/lcu_endgame/` (`gameflow_events.json`, `lp_change_notification.json`, `eog_stats_block.json`).

- **La phase arrive par événement, sans délai.** `uri` `/lol-gameflow/v1/gameflow-phase`, `eventType` `Update`,
  `data` = la phase en chaîne (le même instant, à la milliseconde, que l'événement `/session`). Suite vue :
  `Matchmaking` → `ReadyCheck` → `Matchmaking` → `ReadyCheck` → `ChampSelect` → `GameStart` → `InProgress` →
  `Reconnect` → `WaitingForStats` → `PreEndOfGame` → `EndOfGame` → `"None"`. **Hors lobby la phase est la chaîne
  `"None"`**, pas l'objet `None` : `PHASE_KINDS` la range avec `idle`, et `closed` reste le client qui ne répond pas.
- **Fenêtre des deux endpoints : de `PreEndOfGame` à la sortie d'`EndOfGame`.** Vides pendant `WaitingForStats`
  (8,5 s), pleins dès `PreEndOfGame` (`eog-stats-block` 0,03 s avant l'événement de phase, la notification de LP
  0,3 s après) et jusqu'à la milliseconde où la phase passe à `"None"` : les événements `Delete` / `null` des deux
  endpoints partent au même instant (1689,155 s) que le changement de phase. Ici 25 s parce que la partie a été
  quittée sans cliquer ; la fenêtre dure exactement ce que dure l'écran de fin, d'où le risque avec « Rejouer ».
  Hors fenêtre, la réponse est `null` (JSON), pas `{}`.
- **Lecture instantanée** : 1 ms en moyenne (`eog-stats-block` 8 ms en fenêtre, 70 ko, 11 ms au pire). Une lecture
  par seconde (`PHASE_POST_POLL_S = 1,0`) ne coûte rien et tient la cadence validée ; `PHASE_POLL_S = 2,0` reste
  le rattrapage, l'événement porte la phase.
- **Tâche 117 confirmée : l'événement `/lol-ranked/v1/current-lp-change-notification` porte la notification
  complète** (`leaguePointsDelta` −20, `leaguePoints` 64, `tier`, `division`, `gameId`, `queueType`), identique à la réponse du GET. Elle arrive 4 fois (une `null`, puis 3 fois la charge). Même constat pour
  `/lol-end-of-game/v1/eog-stats-block` (`Create` puis 3 `Update`, dernière charge identique au GET) : à noter pour la
  tâche 117 (lire aussi l'écran de fin dans l'événement coûte une ligne de plus).
- **Tâche 117 livrée** : `GameCapture.on_lcu_event` (abonné d'événements du tracker, `PhaseTracker.subscribe_events`)
  met la notification de côté dès l'événement ; l'écran de fin n'est pas lu dans l'événement (hors de la tâche).
- **Bruit du préfixe `/lol-ranked`** : à l'entrée en fin de partie, ~25 événements `ranked-stats/<puuid>` et
  `cached-ranked-stats/<puuid>` (un par joueur de la partie) en 130 ms, 69 événements au total sur la partie. Le tracker
  et la tâche 117 filtrent sur l'URI exacte.
- **Non couvert par ce relevé** : « Rejouer » cliqué dans les 3 s (la fenêtre s'y réduit), reste la vérification de
  bout en bout du §6. La cause de la perte des LP reste donc l'hypothèse du §1 ; la fenêtre bornée par la phase est,
  elle, établie.

### 4.1 `src/draft/phase_tracker.py` (nouveau)

```python
class PhaseTracker:
    """La phase gameflow courante, de l'événement WebSocket ou du sondage de rattrapage."""
    def __init__(self, read: Callable[[], Optional[str]], bus=None, clock=time.monotonic) -> None: ...
    @property
    def phase(self) -> Optional[str]: ...        # chaîne brute du LCU ; None : client fermé ou inconnue
    @property
    def kind(self) -> str: ...                   # voir `PHASE_KINDS`
    def since(self) -> float: ...                # secondes dans la phase courante
    def subscribe(self, callback: Callable[[str, str, str], None]) -> None:  # (ancienne, nouvelle, kind)
    def start(self) -> None: ...                 # fil daemon ; sans bus : sondage seul
    def stop(self) -> None: ...
```

- Entrée 1, événement : abonnement au sujet `lcu` du bus ; seul l'URI `/lol-gameflow/v1/gameflow-phase`
  compte, `data` est la phase (relevé de la tâche 112). Entrée 2, sondage : `read()` toutes les `PHASE_POLL_S`
  (`PHASE_POST_POLL_S` en fin de partie). Une même phase lue deux fois ne notifie pas.
- `read` est un `LCUClient` **propre au tracker** (comme `launch.py:119-120`) : ni celui du coach ni celui du
  serveur.
- Un rappel qui lève n'arrête ni le tracker ni les autres rappels. Best-effort partout.
- Publie `bus.publish("phase", {"phase", "kind", "since"})` à chaque changement (`since` : epoch, pour la pastille).
- `kind` regroupe les phases du LCU (`PHASE_KINDS` dans `config_constants.py`) : `closed` (None), `idle`
  (`None`, `Lobby`), `queue` (`Matchmaking`, `ReadyCheck`), `draft` (`ChampSelect`), `game` (`GameStart`,
  `InProgress`, `Reconnect`), `post` (`WaitingForStats`, `PreEndOfGame`, `EndOfGame`), `error`
  (`FailedToLaunch`, `TerminatedInError`). Phase inconnue : `unknown`, journalisée une fois en `[INFO]`.
  `post` reprend `OUTCOME_TRIGGER_PHASES` (`config_constants.py:374`), qui devient sa seule source.

### 4.2 `DraftMonitor` et `MonitorLifecycle`

- `DraftMonitor` crée le tracker (avec `bus` s'il y en a un) et le démarre dans `start_monitoring`, après
  `connect()`, l'arrête dans `cleanup()`.
- `monitor_loop` lit `tracker.phase` à la place de `is_in_ready_check()` (`lifecycle.py:37`),
  `is_in_champion_select()` (`:40`) et `get_gameflow_session()` (`:61`) : **zéro lecture de phase par tour**
  quand le tracker a une valeur fraîche. Tracker muet ou périmé (`PHASE_STALE_S`) : lecture directe, comme
  aujourd'hui. `get_champion_select_session` (la draft) reste lue à son tour.
- La détection de la fenêtre d'après-partie (`lifecycle.py:73-84`) passe par `subscribe` : l'entrée dans `post`
  ouvre la fenêtre (`_post_game_until`) sans attendre un tour. Les tests de
  `tests/test_draft_monitor_lifecycle.py` et `test_draft_monitor_display.py` restent verts (les faux `lcu` y
  répondent encore à `get_gameflow_session`, c'est le repli).

### 4.3 Capture de fin de partie hors boucle

- `src/coaching/capture.py` : la lecture transitoire se sépare de l'écriture.
  - `GameCapture.read_transients()` (nouveau, **sans base**) : `get_end_of_game_block` → `_eog_by_game` (existant) ;
    `get_lp_change_notification` → `_lp_by_game[game_id]` (nouveau : la notification, une fois par partie).
  - `GameCapture.on_post_game()` garde son rôle dans la boucle du monitor, mais **écrit** : insertion de la
    photo de LP depuis `_lp_by_game` (`ranked.snapshot_after_game` lit désormais la notification mise de côté,
    plus le LCU), capture de l'historique, analyse. Une notification mise de côté mais non écrite (base
    verrouillée) est rejouée au passage suivant.
- Un fil `PostGameWatcher` (nouveau, dans `capture.py`) : à l'entrée dans `post` (rappel du tracker), il appelle
  `read_transients()` chaque `PHASE_POST_POLL_S` tant que `kind == "post"`, avec un `LCUClient` propre ; il
  s'arrête à la sortie de `post` après une dernière lecture. `_eog_by_game` et `_lp_by_game` sont protégés par un
  verrou (deux fils les touchent). Console et client : même chemin (le tracker a toujours le repli sondage).
- `_safely` : une erreur distincte s'affiche une fois en `[ALERTE] Capture de partie : …` hors `-v` (§2, à valider).

### 4.4 Pastille de phase

- Barre de titre (`src/client/templates/base.html`) : pastille permanente alimentée par le sujet `phase`
  (SSE existant), libellés français : « Hors partie » (`idle`), « En file » (`queue`), « Champion select »
  (`draft`), « En partie » (`game`), « Fin de partie » (`post`), « Client LoL fermé » (`closed`). Elle remplace
  la pastille « En partie » de SPEC-24 tâche 108 (même élément, plus d'états). Aucune bascule automatique de page (comme la pastille de la tâche 108).
- `LiveGame` (`ingame.py`) prend la phase du tracker (`bus.latest("phase")`) au lieu de `_gameflow_phase` ; la
  sonde `LcuProbe` reste pour les pages qui l'utilisent. `found.py` et `lobby.py` lisent à la demande : inchangés.

### 4.5 Constantes (`src/config_constants.py`, classe `draft_config`)

| Constante | Valeur | Origine |
|---|---|---|
| `PHASE_POLL_S` | 2,0 | rattrapage ; moins de la moitié des lectures actuelles, à confirmer par la tâche 112 |
| `PHASE_POST_POLL_S` | 1,0 | cadence d'une lecture transitoire pendant la fin de partie |
| `PHASE_STALE_S` | 10,0 | au-delà, le monitor relit la phase lui-même |
| `PHASE_KINDS` | table §4.1 | phases du LCU (`GameflowPhase`) |

`POST_GAME_RETRY_INTERVAL` (5,0) et `POST_GAME_RETRY_WINDOW` (600,0) restent : ils cadencent l'historique et la
fenêtre de rattrapage, plus la lecture transitoire.

### 4.6 Tests

- `tests/test_phase_tracker.py` : fausse horloge, faux bus ; événement → notification et publication ; sondage de
  rattrapage ; même phase deux fois sans notification ; `kind` de chaque phase du LCU ; phase inconnue ; rappel
  qui lève ; reconnexion (événements qui reprennent après un silence). Rejeu des fixtures de la tâche 112.
- `tests/regression/test_regression_post_game_transients_off_loop.py` : **rouge avant la tâche 115** : un faux LCU
  rend l'écran de fin et la notification pendant 3 s seulement, la boucle du monitor met 5 s par tour ; la photo de
  LP (`lp_delta`, `game_id`) et `raw_eog` sont enregistrés quand même.
- `tests/test_coaching_capture.py` étendu : notification mise de côté puis écrite au passage suivant ; base
  verrouillée puis rejouée ; deux fils sur les dictionnaires (verrou).
- `tests/test_draft_monitor_lifecycle.py` : un tour du monitor ne lit **aucune** phase quand le tracker est frais
  (compteur d'appels du faux `lcu`), en lit une quand il est périmé.
- Client : le fragment de la pastille pour chacun des six états ; sujet `phase` reçu par SSE.
- Hermétique : ni `data/db.db`, ni `logs/`, ni vrai client LoL (`tests/conftest.py`).

## 5. Tâches

Numéros globaux : à la suite de la tâche 111 du `TODO.md`.

| # | Tâche | Pts | Dépend de |
|---|---|---|---|
| 112 | Spike : `scripts/dump_lcu_endgame.py` (lecture seule, horodaté : événements WebSocket `/lol-gameflow`, `/lol-ranked`, `/lol-end-of-game`, durée de réponse de `eog-stats-block` et `current-lp-change-notification`), une fin de partie réelle jouée par @pj35, fixtures anonymisées, constats en §4 | 3 | — |
| 113 | `PhaseTracker` : événements, sondage de rattrapage, `kind`, sujet `phase`, constantes ; tests | 5 | 112 |
| 114 | `DraftMonitor` et `MonitorLifecycle` sur le tracker : zéro lecture de phase par tour, repli, fenêtre d'après-partie par rappel ; tests | 3 | 113 |
| 115 | Capture hors boucle : `read_transients`, `_lp_by_game`, `PostGameWatcher`, erreurs affichées une fois ; régression rouge avant, verte après | 5 | 112, 113 |
| 116 | Pastille de phase dans la barre de titre, `LiveGame` sur le tracker ; tests | 3 | 113 |
| 117 | **Conditionnelle** au spike : notification de LP lue dans l'événement WebSocket `/lol-ranked` | 3 | 112, 115 |
| 118 | Clôture : exe vérifié, `PROJECT_STRUCTURE.md`, README, `CHANGELOG.md`, entrées SPEC-23 (`step(phase)`) et SPEC-24, statuts | 2 | 114, 115, 116 |

Total : 24 pts. **Articulation avec SPEC-23** : sa tâche 64 (`step(phase)`) lit la phase du tracker ; SPEC-25
passe donc avant 64. Les tâches 62 et 63 (pool de threads de la collecte) ne touchent pas à la phase.

## 6. Critères d'acceptation

1. `python -m pytest tests/ -v` vert, avec les tests des tâches ci-dessus.
2. `tests/regression/test_regression_post_game_transients_off_loop.py` : rouge sur le code d'avant la tâche 115
   (`git stash` du fix), vert après ; commité avec le fix.
3. `python -m pytest tests/test_phase_tracker.py -v` : chaque phase du LCU a un `kind` ; un événement notifie
   sans attendre un sondage ; un sondage rattrape un événement manqué.
4. `python -m pytest tests/test_draft_monitor_lifecycle.py -v` : un tour du monitor fait 0 lecture de phase
   (tracker frais) ou 1 (périmé), contre 3 aujourd'hui.
5. Mode console (`python lol_coach.py`, sans `--client`, donc sans bus) : le tracker tourne en sondage seul et
   la capture de fin de partie fonctionne (test sans bus).
6. `grep -n "POST_GAME_RETRY_INTERVAL\|PHASE_POLL_S\|PHASE_POST_POLL_S\|PHASE_STALE_S" src/draft/*.py src/coaching/*.py`
   ne montre aucune valeur littérale : tout vient de `config_constants.py`.
7. Aucune connexion SQLite n'est ouverte par `PostGameWatcher` ni par le tracker (`grep -n "sqlite\|\.connection"`
   sur leurs modules : vide).
8. Pastille : les six états rendus (test du fragment), et SSE `phase` reçu.
9. Si le spike le confirme, tâche 117 : la notification lue dans l'événement donne la même photo que le sondage
   (test sur la fixture) ; sinon la tâche est close sans code et le dit en §4.
10. `CHANGELOG.md` (`[Unreleased]`), statut de cette spec et `docs/specs/README.md` à jour.

**Vérification de bout en bout** : lancer `python lol_coach.py --client -v`, jouer une partie classée et cliquer
« Rejouer » dans les 3 s après l'écran de fin. Puis
`SELECT lp_delta, game_id FROM rank_snapshots ORDER BY id DESC LIMIT 1` renvoie un `lp_delta` non nul, et
`SELECT raw_eog IS NOT NULL FROM game_records ORDER BY game_creation_utc DESC LIMIT 1` renvoie 1. La pastille
passe de « En partie » à « Fin de partie » puis « Hors partie » ou « En file ».

## 7. Hors périmètre

- ❌ Cause du ralentissement de la boucle (2 à 5 s/tour) : non établie, traitée à part si elle persiste (§2).
- ❌ Lectures de phase à la demande de `found.py` et `lobby.py` : une requête par page, pas une boucle.
- ❌ Bascule automatique de page selon la phase : la pastille informe, elle ne navigue pas (SPEC-24 tâche 108).
- ❌ Reconstituer une variation de LP pour une partie récupérée au rattrapage : une partie sans notification
  lue n'a pas de variation, comme SPEC-19 §8 (« aucune variation inventée »).
- ❌ Changer le pas de la collecte (SPEC-23) ou le transport LCU (`LCUClient.last_status_code`, SPEC-23 tâche 62).
