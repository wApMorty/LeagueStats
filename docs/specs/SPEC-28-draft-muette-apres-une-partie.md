# SPEC-28 — La draft suivante ne doit plus rester muette après une partie

**Statut** : ✅ Livrée le 2026-10-09 (tâches 129 à 132) ; approche B, seuils, journal et passage abandonné validés par @pj35 (§2) ; recette en conditions réelles (§6) à faire.

**Origine** : @pj35, 2026-10-09 : « J'ai toujours un problème lors de l'enchaînement des games, le jeu a l'air coincé
dans l'analyse de la game que je viens de finir et ne me fais pas de suggestion de draft ni n'affiche l'interface de
draft sur la GUI, alors qu'elle indique elle même que je suis en champ select. » Précisé le même jour : enchaînement
« Rejouer » puis file ; la console n'affiche rien de nouveau ; tantôt la draft finit par apparaître seule, en retard,
tantôt elle ne vient jamais.

**Effort** : ~2 jours, 4 tâches, 15 pts (§5).

---

## 1. Constat

Lecture de code et mesures du 2026-10-09 (copie de `data/db.db` pour les durées, `data/crawl.db` en lecture seule,
reproduction hermétique jetable). Ce qui n'est **pas** établi est dit comme tel.

**La pastille et la draft ne passent pas par le même chemin.** La pastille « Champion select » vient du
`PhaseTracker` (événement WebSocket, instantané). La draft (console, snapshot du client, sujet `game`) n'existe que
si la boucle monofil `MonitorLifecycle.monitor_loop` (`src/draft/lifecycle.py:35`) arrive à son tour en champ select.
Le client peut donc dire « Champion select » pendant que la boucle fait autre chose.

**Mécanisme 1 — la boucle est occupée ailleurs (établi par lecture, durée non mesurée).** Hors champ select, chaque
tour exécute dans le même fil, sans plafond de durée ni contrôle de phase entre deux étapes
(`lifecycle.py:93-97`, `148-163`) :

- `retry_post_game`, toutes les 5 s pendant 600 s après la fin de partie : résolution des résultats
  (`outcome_tracker.py:65-71` : historique + écran de fin), puis `GameCapture.on_post_game` (`capture.py:58-66` :
  historique, détail + timeline de chaque partie absente, analyse, impact), puis `crawler.seed()` ;
- `crawler.step()` (une à deux requêtes LCU et des lectures de `crawl.db`).

Chaque requête LCU peut attendre 5 s (`lcu_client.py:207`, `timeout=5`). Tant qu'une prédiction reste sans résultat
(13 sur 165 aujourd'hui, `outcome` et `game_id` nuls), la résolution relit l'historique à chaque passage. Un passage
commencé en `Matchmaking` finit avant que la draft soit lue. Le calcul, lui, ne pèse rien : `analyze_pending` 0,18 s,
`compute_pending` 0,01 s, 20 lectures de `get_raw_game` 0,00 s (copie de `db.db`, 2026-10-09). Les durées des
requêtes LCU en fin de partie ne sont **pas** mesurées : rien ne les chronomètre.

**Précédent.** Le même symptôme (« seule la première draft d'une session était vue ») a eu une cause trouvée au
`py-spy` le 2026-10-08 : `crawl.db` sans index (`9adee2e`). Il est revenu. Relevé du 2026-10-09 : `crawl.db` pèse
710 Mo dont 66 % de pages libres (115 026 sur 173 466), et la requête de plafond de la purge
(`SELECT … ORDER BY game_creation_utc DESC LIMIT -1 OFFSET n`) a pris **66 s** une fois à froid, puis 0,04 s aux deux
relevés suivants. Un seul relevé, non reproduit : il montre qu'une requête de la boucle peut bloquer longtemps, pas
que c'est la cause. Cadence moyenne : 1,3 à 2,3 s/tour les 08 et 09/10 pour `POLL_INTERVAL = 1,0`
(`logs/draft_monitor_memory.log`, une ligne par 300 tours) ; une moyenne cache les pics.

**Mécanisme 2 — l'état de la partie précédente n'est jamais ré-armé (établi par reproduction).**
`has_analyzed_final_draft`, `last_draft_state`, `has_done_initial_hover` et le sujet `game` ne sont remis à zéro que
si la boucle **observe** `Lobby`, `Matchmaking`, `None` ou `""` pendant un tour, et seulement si
`has_analyzed_final_draft` est vrai (`lifecycle.py:69-79`, `reset_for_next_game` `:249-273`). En champ select, la
draft n'est traitée que si `not has_analyzed_final_draft` (`lifecycle.py:114-118`) : sinon ni console, ni
`recommender.provide`, ni snapshot. Reproduction (script jetable, faux LCU, aucune écriture) : `EndOfGame` puis
`ChampSelect` sans phase intermédiaire vue → `_handle_draft_change` **non appelé**, `has_analyzed_final_draft` reste
vrai. Après `CHAMP_SELECT_EXIT_TICKS` tours hors champ select, `recommender.clear()` a déjà vidé l'écran de draft, et
l'écran « En partie » garde l'analyse précédente (le sujet `game` n'est republié à `None` que par le reset). C'est
exactement ce que décrit @pj35. **Reste à établir** : que la boucle puisse manquer `Lobby` **et** `Matchmaking`
(plusieurs dizaines de secondes de file) ; le mécanisme 1 l'explique, le chronomètre (tâche 129) le dira.

**Même cause, autre symptôme (lecture seule, à confirmer par la tâche 130).** Une esquive pendant la draft
(`has_analyzed_final_draft` faux) n'est jamais ré-armée : `has_done_initial_hover`, `forced_roles` et
`last_draft_state` survivent, la draft suivante n'a pas de survol initial.

**Aucune trace.** `logs/draft_monitor_memory.log` n'écrit que tous les 300 tours (`memory_diagnostics.py:21`) :
aucune donnée ne dit ce qu'a fait la boucle ni combien de temps après l'entrée en champ select la draft a été vue.
SPEC-25 §2 avait renvoyé le « ralentissement de la boucle » à une tâche à part « si la lenteur persiste » : c'est
la tâche 129.

## 2. Objectif et arbitrages

**Objectif** : la draft est lue et dessinée dans les quelques secondes qui suivent l'entrée en champ select, quoi
que la boucle ait fait avant, et ce qui la retarde est chiffré.

| Sujet | Décision |
|---|---|
| Approche | **Validé (@pj35, 2026-10-09)** : B (§3) : épisode de draft numéroté par le tracker, travail d'arrière-plan qui cède la main, chronométrage. |
| Épisode de draft | **Défaut proposé** : le tracker incrémente un compteur à chaque entrée en famille `draft` depuis une phase **connue** d'une autre famille. Pas depuis `closed` : un trou du LCU de plus de `PHASE_STALE_S` en pleine draft ne doit pas refaire le survol initial. |
| Réarmement | **Défaut proposé** : à chaque changement d'épisode, `reset_for_next_game()` (idempotent) avant de traiter la draft. Le reset sur `Lobby` / `Matchmaking` existant reste (il vide « En partie » dès le lobby). |
| Céder la main | **Défaut proposé** : un seul point de contrôle, dans `LCUClient._make_request` (§4.3), actif seulement pendant le travail d'arrière-plan : une requête demandée alors que le tracker dit `draft` rend `None` tout de suite (même contrat que « client injoignable », que capture, résolution et collecte réessaient déjà). |
| Passage abandonné | **À valider** : ce qu'un passage coupé n'a pas fait reprend au passage suivant (5 s plus tard, hors champ select) ; la fenêtre d'après-partie (600 s) ne se prolonge pas. Une partie non capturée à temps l'est au passage d'une partie suivante ou au démarrage (historique de 20 parties). |
| Seuils | **À valider** : `TICK_SLOW_S` = 3,0 (tour écrit au journal), `TICK_ALERT_S` = 15,0 (`[ALERTE]` en console, une fois par étape et par session). |
| Journal | **À valider** : `logs/draft_monitor_ticks.log`, rotatif (1 Mo × 3), ouvert par `start_monitoring()` seulement (les tests n'écrivent jamais dans `logs/`). |
| Disque (`crawl.db`) | **Défaut proposé** : non interruptible par ce correctif ; le journal désigne l'étape fautive, et un `VACUUM` ou l'approche C se décident sur ces chiffres (§7). |

## 3. Approches considérées

- **A. Épisode de draft seul** (~0,5 j) : règle la draft muette. Une boucle bloquée 30 s démarre quand même la
  draft en retard, et on ne saurait pas pourquoi.
- **B. Épisode + cède la main + chronométrage (retenue, ~2 j)** : la draft ne reste plus jamais muette, le travail
  d'arrière-plan s'arrête à une requête près dès le champ select, et le journal chiffre le reste. Pas de fil de plus,
  pas de connexion SQLite de plus.
- **C. Travail d'après-partie dans un fil à part** (~4 j) : la boucle ne fait plus que la draft. Une connexion SQLite
  par fil (elles ne sortent pas du fil du coach, `launch.py:68`), capture, analyse, impact et collecte à déplacer,
  surface de tests double. Écartée pour l'instant : à rouvrir si le journal montre un blocage disque que B ne coupe pas.

## 4. Détail

### 4.1 Chronomètre (`src/draft/tick_timer.py`, nouveau)

```python
class TickTimer:
    """Durée de chaque étape d'un tour du monitor ; journal des tours lents et du délai de la draft."""
    def __init__(self, clock=time.monotonic, sink: Optional[Callable[[str], None]] = None) -> None: ...
    def run(self, name: str, work: Callable[[], T]) -> T: ...   # chronomètre work(), renvoie son résultat
    def end_tick(self, phase: Optional[str]) -> None: ...        # écrit si total > TICK_SLOW_S, alerte si > TICK_ALERT_S
    def draft_seen(self, waited_s: float) -> None: ...           # une ligne par épisode
```

- API par appel (`run`), **pas** de gestionnaire de contexte : les moniteurs factices des tests sont des `Mock`.
- `DraftMonitor.tick_timer` existe dès `__init__` avec `sink=None` (rien n'est écrit) ; `start_monitoring()` lui
  donne le sink du journal rotatif (même schéma que `memory_diagnostics.py`).
- Étapes chronométrées dans `monitor_loop` : `phase` (lecture de `gameflow()`), `ready_check`, `resolve_outcomes`,
  `post_game` (et, dedans, chaque `GameCapture._safely` sous son nom : `capture_recent`, `analyze`, `impact`,
  `write_lp`), `crawler_seed`, `crawler_step`, `crawler_report`, `champ_select` (session, analyse).
- Ligne d'un tour lent : `2026-10-09 23:41:07 tour 24.3 s phase=Matchmaking | capture_recent 18.1 | resolve_outcomes 4.2`
  (étapes ≥ 0,5 s seulement). Alerte console : `[ALERTE] Boucle du Live Coach : 24 s dans capture_recent`.
- Délai de la draft : au premier tour en champ select de chaque épisode, `draft_seen(tracker.since())`, ligne
  `draft vue 1.4 s après l'entrée en champ select`. Toujours écrite (pas seulement quand elle est lente) : c'est la
  mesure qui juge le correctif.

### 4.2 Épisode de draft

- `src/draft/phase_tracker.py` : `PhaseTracker.draft_episode` (entier, sous le verrou). Dans `observe`, quand la
  nouvelle phase est de famille `draft`, l'ancienne est une chaîne (pas `None`) et de famille ≠ `draft` : `+1`.
- `src/draft_monitor.py` : `self._draft_episode = 0` (l'épisode dont la boucle détient l'état).
- `lifecycle.monitor_loop`, branche champ select, juste après `self._exit_ticks = 0` :
  si `phase_tracker.draft_episode != _draft_episode` → `self.m._reset_for_next_game()` puis
  `_draft_episode = draft_episode`. Premier épisode (0 des deux côtés) : aucun reset.
- Le reset sur `Lobby` / `Matchmaking` ne change pas. Le mode console (sans bus) garde le tracker en sondage seul.

### 4.3 Céder la main (`src/lcu_client.py`, `src/draft/lifecycle.py`)

- `LCUClient.yield_if: Optional[Callable[[], bool]] = None`. Dans `_make_request`, avant la requête :
  `if self.yield_if is not None and self.yield_if(): self.last_status_code = None; return None`.
- `DraftMonitor.draft_pending()` → `self.phase_tracker.kind == "draft"` (aucune requête ; tracker muet → `closed`
  → faux, donc comportement d'aujourd'hui).
- `lifecycle.monitor_loop` : autour de `retry_post_game()` et des appels au crawler, affectation puis remise à
  `None` en `try/finally` (`self.m.lcu.yield_if = self.m.draft_pending`) : de simples affectations, sûres avec les
  `Mock` des tests. Les requêtes du champ select (`get_champion_select_session`, `PATCH` du survol, `accept`) ne
  passent jamais par là.
- Garantie : après l'entrée en champ select, le travail d'arrière-plan fait **au plus la requête en vol**
  (5 s de timeout) plus du calcul local borné (< 1 s mesuré), puis la boucle revient.
- Les clients LCU des autres fils (`PostGameWatcher`, tracker, serveur) n'ont pas de `yield_if` : inchangés.

### 4.4 Constantes (`src/config_constants.py`, classe `draft_config`)

| Constante | Valeur | Origine |
|---|---|---|
| `TICK_SLOW_S` | 3,0 | au-dessus de la cadence moyenne observée (1,3 à 2,3 s) ; **à valider** |
| `TICK_ALERT_S` | 15,0 | trois requêtes LCU au timeout ; **à valider** |
| `TICK_LOG_MAX_BYTES` / `TICK_LOG_BACKUPS` | 1 000 000 / 3 | journal borné |

### 4.5 Tests

- `tests/test_tick_timer.py` : fausse horloge ; `run` renvoie le résultat et propage une exception après l'avoir
  chronométrée ; tour sous le seuil : rien d'écrit ; tour lent : ligne avec les seules étapes ≥ 0,5 s ; alerte
  console une fois par étape ; `draft_seen` ; `sink=None` n'écrit rien.
- `tests/test_phase_tracker.py` étendu : `draft_episode` +1 pour `Matchmaking` → `ChampSelect`, pas pour
  `ChampSelect` → `ChampSelect`, pas depuis `None` (premier événement, ou client fermé), +1 après `Matchmaking`
  entre deux drafts (esquive).
- `tests/regression/test_regression_draft_silent_after_missed_reset.py` (4 points en docstring) : **rouge avant la
  tâche 130**. (1) `EndOfGame` puis `ChampSelect` sans phase intermédiaire vue, `has_analyzed_final_draft` vrai :
  `_handle_draft_change` appelé, snapshot publié, sujet `game` remis à `None`. (2) Esquive : `ChampSelect` partiel,
  `Matchmaking`, `ChampSelect` : la seconde draft a son survol initial et un état neuf.
- `tests/regression/test_regression_background_work_blocks_draft.py` : **rouge avant la tâche 131**. Faux LCU dont
  chaque requête avance une horloge de 5 s ; le tracker passe en `draft` pendant un passage de `retry_post_game` ;
  aucune requête n'est émise après le passage (compteur), le passage rend la main, et le tour suivant traite la draft.
- `tests/test_draft_monitor_lifecycle.py` : `yield_if` remis à `None` après un passage qui lève ; hors épisode,
  aucun changement (les tests existants restent verts).

## 5. Tâches

Numéros globaux : à la suite de la tâche 128 du `TODO.md`. La tâche 129 d'abord : elle donne la base de mesure.

| # | Tâche | Pts | Dépend de |
|---|---|---|---|
| 129 | `TickTimer`, étapes chronométrées de `monitor_loop` et de `GameCapture._safely`, journal rotatif ouvert par `start_monitoring()`, alerte console, délai de la draft ; tests | 3 | — |
| 130 | Épisode de draft : `PhaseTracker.draft_episode`, réarmement dans la branche champ select ; régression rouge avant, verte après | 5 | — |
| 131 | Céder la main : `LCUClient.yield_if`, `draft_pending()`, pose et remise dans `monitor_loop` ; régression rouge avant, verte après | 5 | 129 |
| 132 | Clôture : `CHANGELOG.md` (Fix), statut, `docs/specs/README.md`, `PROJECT_STRUCTURE.md`, SPEC-25 §2 renvoyé ici, recette @pj35 | 2 | 130, 131 |

Total : 15 pts. SPEC-27 (tâche 126, `RealityCheck.step` dans `monitor_loop`) passe par les mêmes points de contrôle.

## 6. Critères d'acceptation

1. `python -m pytest tests/ -v` vert, avec les tests des tâches ci-dessus.
2. `python -m pytest tests/regression/test_regression_draft_silent_after_missed_reset.py -v` : rouge sur le code
   d'avant la tâche 130 (`git stash` du fix), vert après ; commité avec le fix.
3. `python -m pytest tests/regression/test_regression_background_work_blocks_draft.py -v` : rouge sur le code d'avant
   la tâche 131, vert après ; zéro requête LCU de la boucle après l'entrée en champ select.
4. `python -m pytest tests/test_tick_timer.py tests/test_phase_tracker.py -v` : tour lent journalisé avec ses
   étapes, `draft_episode` conforme à §4.2.
5. `grep -n "TICK_SLOW_S\|TICK_ALERT_S\|TICK_LOG" src/draft/*.py` ne montre aucune valeur littérale : tout vient de
   `config_constants.py`.
6. `python -m pytest tests/ -v` ne modifie ni `data/db.db` ni `logs/*.log` (la fixture
   `_guard_production_untouched` reste muette) : le journal des tours ne s'ouvre qu'à `start_monitoring()`.
7. Le mode console (sans bus) passe les deux régressions (le tracker y tourne en sondage seul).
8. `CHANGELOG.md` (`[Unreleased]`, une entrée Fix), statut de cette spec et `docs/specs/README.md` à jour.

**Vérification de bout en bout** (recette @pj35) : lancer `python lol_coach.py --client`, enchaîner trois parties avec
« Rejouer » puis la file. Dans `logs/draft_monitor_ticks.log`, chaque draft porte une ligne
`draft vue X s après l'entrée en champ select` avec X ≤ 6 s, la console affiche la recommandation, l'écran Draft
s'ouvre et « En partie » a perdu l'analyse précédente. Les lignes `tour … s` nomment les étapes lentes. **Si un tour
dépasse 15 s hors requête LCU** (disque), cette spec n'a pas réglé la cause : on rouvre l'approche C ou un `VACUUM`
sur ces chiffres.

## 7. Hors périmètre

- ❌ **Approche C** (fil à part pour l'après-partie) : décidée sur le journal, pas avant.
- ❌ **`VACUUM` de `crawl.db`** (66 % de pages libres) : à proposer à part si le journal désigne la collecte.
- ❌ **Raccourcir la fenêtre d'après-partie ou espacer les passages** : le correctif borne leur coût en draft, il
  ne change pas leur cadence.
- ❌ **Reset en cas de trou du LCU en pleine draft** : voulu absent (§2, épisode depuis une phase connue seulement).
- ❌ **La pastille et la bascule du client** (SPEC-25, SPEC-26) : elles marchent ; seul le chemin de la draft change.
