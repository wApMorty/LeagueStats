# SPEC-33 — Éclaireur des joueurs en partie

**Statut** : 🟢 Validée par @pj35 le 2026-10-13 ; tâches 151 à 154, 156 et 158 implémentées le même jour (reste le banc réel 155, puis 157, 159 à 161). Spike retiré le même jour (relevés de SPEC-25 et SPEC-27 suffisants, §1). Indicateur, win chance, affichage, déclencheur, concurrence,
fenêtre, files, suite en partie, seuils de couleur et seuil d'adoption validés par @pj35 (§2).

**Origine** : @pj35, 2026-10-13 : « ajouter une analyse des joueurs dans l'analyse in-game. Si on arrive
à crawl assez rapidement les stats de chaque joueur dans ses 20 dernières games pendant l'écran de
chargement, on peut d'office mettre à jour la win chance de la game de manière plus précise. […] me faire
un avis rapidement sur le niveau d'un joueur, peut-être en calculant son impact moyen dans les 5, 10 ou 20
dernières games. Il y a un enjeu majeur sur les performances […] la question du multi-threading se pose. »

**Effort** : ~4,5 jours, 11 tâches (151 à 160), 34 pts (§5), dont une tâche conditionnelle.

---

## 1. Constat

Mesuré le 2026-10-13 (lecture du code, `data/crawl.db` ouverte en lecture seule, banc jetable).

- **Ce que coûte un joueur.** `LCUClient.get_player_games(puuid)` (`src/lcu_match_history.py:75`) lit ses
  20 dernières parties en **une requête**, 1,4 à 1,7 s (SPEC-23 §1). Chaque entrée porte un seul
  participant, **lui**, avec ses 118 stats (`win`, `kills`, `deaths`, `assists`, `totalMinionsKilled`,
  `neutralMinionsKilled`…) et `gameDuration` : forme brute sans autre requête. L'impact ΔP de SPEC-20
  exige en plus le **détail** et la **timeline** de chaque partie (`get_game_detail`, `get_game_timeline`,
  `src/lcu_match_history.py:147-154`) : 2 requêtes par partie, ~400 pour 10 joueurs à 20 parties.
- **Latences** (SPEC-23 §1) : détail 60 à 280 ms, timeline 13 à 213 ms, mais **3 à 17 s** la timeline
  d'une partie jamais lue d'après le commentaire de `src/winprob/crawl.py:6-7`. En séquentiel, 400
  requêtes ne tiennent pas dans un écran de chargement : seule la concurrence le permet.
- **Concurrence aujourd'hui.** La collecte tourne dans **un** fil (`Crawler.start`, `crawl.py:136`), son
  propre `LCUClient`, une unité de travail par `CRAWL_REQUEST_INTERVAL_S` (1 s), en pause en draft et
  pendant l'acceptation (`Crawler._paused`, `crawl.py:147`). `LCUClient.last_status_code` est un attribut
  d'instance (`src/lcu_client.py`), faux dès que des threads partagent un client : c'est la tâche 62 de
  SPEC-23, non faite.
- **Calcul de l'impact** : `impacts(model, game, timeline, roles)` (`src/winprob/impact.py:135`) prend
  **9,1 ms** par partie (fixture `7998195590`, 377 lignes, 20 appels) : 200 parties ≈ 2 s de CPU, négligeable
  devant le réseau.
- **Le cache existe déjà** : `crawl.db` (1,07 Go) garde détail + timeline des parties lues (`pack`,
  `crawl.py:93`), joueurs au MMR de @pj35 par construction. Une partie déjà lue ne coûte aucune requête.
- **`crawl.db` ne suffit pas à entraîner un terme de forme** (§4.6). Mesuré le 2026-10-13 (script jetable,
  lecture seule, 24 min de décompression) : 67 578 parties lues, toutes au patch 16.20, 67 571 avec
  timeline, **167 836 joueurs distincts**, dont 75 416 vus une seule fois et 5 239 vus 20 fois ou plus. Pour
  qu'une partie ait ses dix joueurs avec au moins 5 parties **antérieures** dans la base : **579 parties
  (0,9 %)** ; en moyenne 3,8 joueurs sur 10 y ont ces 5 parties (1,9 pour 10 parties) ; 6 745 parties
  (10 %) en ont au moins 8 sur 10. La collecte lit 20 parties d'un joueur puis passe au suivant : elle
  couvre des parties, pas l'historique de chaque joueur.
- **La forme brute, elle, est déjà lue** : chaque visite de la collecte (`Crawler._visit`, `crawl.py:217`)
  reçoit l'historique de 20 parties avec les stats du joueur, puis n'en garde que les identifiants.
- **Le modèle de win chance n'a aucun a priori** : variables d'état (différences bleu − rouge) et leurs
  produits avec le temps (`src/winprob/model.py:17-30`). Au chargement, il dit ~50 % quelles que soient
  les équipes ; la probabilité de la draft (`analysis_view`, `src/client/en_partie.py:121`) est un autre
  chiffre, d'un autre modèle.
- **Le chargement est déjà relevé, pas besoin d'un nouveau spike.** Chronologie de SPEC-25
  (`tests/fixtures/lcu_endgame/gameflow_events.json`) : `ChampSelect` → `GameStart` à 197,06 s →
  `InProgress` à 197,25 s : la phase `InProgress` couvre l'écran de chargement. Relevé de SPEC-27
  (2026-10-12) : la Live Client API sert les dix joueurs (`riotId`, `team`, `position`, `championName`) dès
  le premier relevé, pendant le chargement (`game_time` figé à 0,027 s).
- **Seul point non relevé : les `puuid` des dix joueurs en partie.** La Live Client API ne sert que des
  `riotId` (`src/winprob/live.py:39`). La session gameflow (`LCUClient.get_gameflow_session`,
  `lcu_client.py:266`, lue aujourd'hui pour sa seule `phase`) porte `gameData.teamOne` / `teamTwo` avec
  `puuid` et `championId` d'après les outils tiers du LCU ; jamais vérifié dans ce projet. Pas de spike
  dédié : le branchement (tâche 156) lit ces champs défensivement et journalise leur forme à la première
  partie réelle (§4.4) ; s'ils manquent, la recette le dit et un repli par `riotId` est spécifié à ce
  moment-là.
- **La durée du chargement** n'est relevée nulle part ; elle ne conditionne rien (l'éclaireur est
  progressif) et la ligne `[DATA]` de fin d'éclaireur la mesure (§4.3).
- **Écran « En partie »** : tient sur un écran à 1 920 × 986 avec **30 px** de marge (SPEC-31 tâche 145) ;
  le face-à-face est rendu par `analysis_view` (`en_partie.py:99`), une ligne par lane, allié et ennemi.

## 2. Objectif et arbitrages

**Objectif** : dès l'écran de chargement, une pastille de niveau à côté de chacun des dix champions du
face-à-face (impact ΔP moyen sur ses 10 dernières parties classées, d'abord sa forme brute en attendant),
le détail 5 / 10 / 20 en infobulle ; puis **mesurer** si cette forme améliore la win chance, et ne
l'intégrer au modèle que si elle le fait.

| Sujet | Décision |
|---|---|
| Écran | **Validé (@pj35, 2026-10-13)** : l'analyse **en partie** (écran « En partie »), pas la revue d'après-partie. |
| Indicateur | **Validé (@pj35, 2026-10-13)** : les deux, progressif. Forme brute de l'historique en quelques secondes (taux de victoire, KDA, CS/min, parties sur le champion joué), puis impact ΔP moyen qui se remplit au fil des timelines ; parties déjà dans `crawl.db` servies sans requête. |
| Win chance | **Validé (@pj35, 2026-10-13)** : mesurer d'abord. Un terme de forme n'entre dans le modèle que s'il bat le modèle en place sur le jeu de validation (§4.6). Les pastilles s'affichent dans tous les cas. |
| Affichage | **Validé (@pj35, 2026-10-13)** : pastille dans le face-à-face, détail 5 / 10 / 20 en infobulle ; l'écran tient toujours sur un écran. |
| Déclencheur | **Validé (@pj35, 2026-10-13)** : passage en partie (écran de chargement), les dix joueurs. Rien pendant la draft, que SPEC-28 a protégée. |
| Concurrence | **Validé (@pj35, 2026-10-13)** : pool dédié « éclaireur » (`ThreadPoolExecutor`, stdlib), son propre `LCUClient` et une session à pool dimensionné, statut HTTP par thread (tâche 62 de SPEC-23 absorbée). La collecte se tait pendant l'éclaireur. Les parties lues sont rangées dans `crawl.db`, depuis le fil coordinateur seul. Nombre de workers fixé par un banc par paliers (§4.5). **Amendé (@pj35, 2026-10-14)** après le premier banc (§7) : un seul historique en vol (`SCOUT_HISTORY_WORKERS`), le LCU les sert un par un ; délai de requête de l'éclaireur porté à `SCOUT_REQUEST_TIMEOUT_S`. |
| Fenêtre | **Validé (@pj35, 2026-10-13)** : la pastille porte 10 parties ; 5 et 20 dans l'infobulle. |
| Files | **Validé (@pj35, 2026-10-13)** : Solo/Duo et Flex seules (`coaching_config.QUEUE_IDS`), comme la collecte ; pas de seconde page d'historique. Moins de N parties classées sur les 20 : la pastille le dit (« 6 parties »). |
| Fin du chargement avant la fin de l'éclaireur | **Validé (@pj35, 2026-10-13)** : on continue en partie avec `SCOUT_IN_GAME_WORKERS` = 2 (l'ordre de grandeur du débit en partie accepté en SPEC-23 §2), jusqu'à la fin. Alternative : tout arrêter au premier `gameTime > 0`. |
| Seuils de couleur de la pastille | **Validé (@pj35, 2026-10-13)** : quartiles des moyennes à 10 parties des joueurs de `crawl.db`, mesurés au banc (tâche 155) et consignés en §7 ; pas de valeur choisie à la main. **Amendé (@pj35, 2026-10-14)** : calculés hors client sur `crawl.db` en lecture seule (`scripts/measure_scout_quartiles.py`, Live Coach ouvert), le banc n'éclairant que 13 joueurs. |
| Seuil d'adoption du terme de forme | **Validé (@pj35, 2026-10-13)**, figé avant la mesure : validation croisée poolée à 5 blocs (celle de SPEC-20 §4.3 bis), Brier sur les images ≤ 10 min amélioré d'au moins **0,002** (l'ordre de grandeur du coût de l'or, SPEC-20 §4.3 bis), et écart de calibration par décile ≤ 5 pts sur toutes les images. |

## 3. Approches considérées

**3.1 Concurrence** (arbitrée ci-dessus)

| Approche | Compromis |
|---|---|
| **Pool dédié « éclaireur » (retenue)** | Rafale bornée dans le temps, pensée pour l'écran de chargement ; indépendante de SPEC-23 (non démarrée). SQLite reste mono-thread : les workers ne font que HTTP + `impacts()`. Coût : un second mécanisme de concurrence à côté de la collecte, que SPEC-23 pourra reprendre (même session, même statut par thread). |
| SPEC-23 d'abord, joueurs en tête de file | Un seul mécanisme, mais dépend d'une spec non démarrée, et son débit est pensé pour la croisière, pas pour une rafale de 400 requêtes en une minute. |
| asyncio + aiohttp | Nouvelle dépendance pour rien : le débit est borné par le LCU, pas par les threads Python (`requests` libère le GIL en I/O). |

**3.2 Ordre de lecture** (**amendé par @pj35 le 2026-10-14**, après le banc du §7) : les historiques des dix
joueurs un par un (le LCU les sert l'un après l'autre : 1,5 s chacun, ~15 s pour les dix, sans gain en
parallèle), et **dès qu'un historique revient**, les parties de ce joueur, sans attendre les autres. Entre
joueurs dont l'historique est connu, les parties vont **par rang** (la plus récente de chacun, puis la
deuxième…). Une partie commune à plusieurs joueurs connus est lue une fois ; un joueur dont la partie est en
vol pour un autre l'attend, puis la reçoit du cache. *Avant l'amendement* : les dix historiques en parallèle,
puis les parties par rang une fois les dix revenus ; le banc a montré que les historiques ne vont pas plus
vite en parallèle et qu'ils dépassent alors le délai de 5 s du client.

## 4. Détail

### 4.1 `src/lcu_client.py` — statut par thread, session de l'éclaireur (absorbe SPEC-23 tâche 62)

- `last_status_code` devient une propriété adossée à `threading.local()` ; API inchangée (même nom, même
  lecture). Les tests existants (`tests/test_winprob_crawl.py`) continuent de s'appliquer.
- `LCUClient.pooled_session(size: int) -> requests.Session` : même identifiants, `verify=False`,
  `HTTPAdapter(pool_maxsize=size)` monté sur `https://`. Le pool par défaut (10) jetterait des connexions
  en silence au-delà.

### 4.2 `src/winprob/form.py` (nouveau, fonctions pures)

```python
def ranked_games(history: list, queue_ids: tuple) -> list:
    """Entrées brutes de l'historique (forme de `/lol-match-history/v1/products/lol/{puuid}/matches`,
    payload["games"]["games"]) → [{game_id, creation_ms, queue_id, champion_id, win, kills, deaths,
    assists, cs, duration_s}], classées, plus récentes d'abord ; entrée mal formée ignorée."""

def form(games: list, impacts: dict, champion_id: int, window: int) -> dict:
    """Sur les `window` premières parties : {n, win_rate, kda, cs_min, on_champion (parties sur
    `champion_id`), impact (ΔP moyen en points, None si aucune partie n'a d'impact), impact_n}."""
```

`get_player_games` ne garde que trois champs : `form.py` lit donc l'historique brut. Ajouter à
`_MatchHistoryMixin` `get_player_history(puuid) -> Optional[dict]` (réponse brute, `None` si
indisponible) ; `get_player_games` s'appuie dessus (aucun changement de comportement).

KDA = (kills + assists) / max(deaths, 1) sur la somme des parties ; CS = `totalMinionsKilled` +
`neutralMinionsKilled`. Impact d'une partie = somme des `delta_p` des lignes du joueur dans
`impacts(model, game, timeline, roles)["rows"]` (`roles` = `participant_roles(game)`,
`src/coaching/metrics.py:75`), en points (× 100), comme le classement de SPEC-32.

### 4.3 `src/winprob/scout.py` (nouveau) — l'éclaireur

```python
class Scout:
    def __init__(self, monitor, crawler, executor=None, clock=time.monotonic): ...
    active: bool                      # lu par Crawler._paused()
    def start(self, players: list) -> None:
        """players : [{puuid, champion_id, team}] des dix ; sans effet si déjà lancé pour ces puuid."""
    def step(self) -> None:          # fil coordinateur : récolte, range, publie ; best-effort
    def stop(self) -> None:          # shutdown(wait=False, cancel_futures=True)
    def snapshot(self) -> dict:      # {puuid: {champion_id, team, windows: {5: form, 10: form, 20: form},
                                     #           pending: int, failed: bool}}
```

- **Fil** : un fil daemon `scout` (comme `Crawler.start`) fait tourner `step()` toutes les
  `SCOUT_TICK_S` ; un `ThreadPoolExecutor(max_workers=SCOUT_WORKERS, thread_name_prefix="scout")` ne fait
  que les requêtes (`get_player_history`, `get_game_detail`, `get_game_timeline`) et `impacts()` sur un
  `WinModel` chargé une fois (`client/ingame._load_model`, à remonter dans `winprob` si besoin). Chaque
  tâche rend `(résultat, statut)`, statut lu **dans le worker** ; toute exception devient « échec ».
- **Cache** : avant de soumettre une partie, le coordinateur la cherche dans `crawl.db`
  (`SELECT raw FROM crawl_games WHERE game_id = ? AND length(raw) > 0`, via la connexion du coordinateur,
  `Crawler._db()` ouvre une connexion par fil) ; trouvée, `unpack` puis `impacts()` dans un worker, aucune
  requête.
- **Rangement** : une partie lue par l'éclaireur est écrite dans `crawl_games` par le coordinateur, sous la
  forme exacte de `Crawler._read_game` (même `pack`, `depth` = 1, `read_utc`) : extraire de `_read_game`
  une fonction `store_game(db, game, timeline, depth)` partagée plutôt que dupliquer. Les dix `puuid` sont
  marqués visités dans `crawl_frontier` (leurs historiques viennent d'être lus).
- **Ordre** : §3.2. Au plus `SCOUT_HISTORY_WORKERS` historiques en vol, le reste du pool pour les parties. Parties hors `QUEUE_IDS` ignorées. Au plus 20 par joueur. Une partie illisible n'est pas redemandée pour un autre joueur.
- **429** : plus aucune soumission pour cette partie, `[ALERTE]` une fois, les pastilles gardent ce
  qu'elles ont ; la collecte repart en pause `CRAWL_BACKOFF_S` comme aujourd'hui (même horloge).
- **En partie** (§2) : dès que la Live Client API répond (`live.fetch()` non vide, `gameTime` >
  0), plus de `SCOUT_IN_GAME_WORKERS` requêtes en vol.
- **Journal** : à la fin (ou à l'arrêt), une ligne `[DATA] Éclaireur : formes en X s, 10 impacts en Y s, chargement Z s, N requêtes, C % du cache` ; Z = de `InProgress` au premier `gameTime` > 0 de la Live Client API.
- **Publication** : sujet de bus `players` (`TOPIC = "players"`), `snapshot()` après chaque `step()` qui a
  changé quelque chose ; `None` à la remise à zéro.
- **Invariants** : aucune écriture SQLite hors du fil coordinateur ; aucune exception ne sort de `step()`
  (CLAUDE.md, boucle de draft) ; rien n'est soumis pendant une draft (`Scout` n'est lancé qu'en partie et
  arrêté par `reset_for_next_game`).

### 4.4 Branchement (`src/draft/lifecycle.py`, `src/winprob/crawl.py`, `src/client/`)

- `Crawler._paused()` : `… or self.m.scout.active`.
- `lifecycle._tick` : en `InProgress` (là où `reality.step` tourne, `lifecycle.py:107`), si l'éclaireur n'a
  pas été lancé pour cet épisode, lire `get_gameflow_session()` et en tirer les dix joueurs
  (`gameData.teamOne` / `teamTwo` : `puuid`, `championId`, `team` ; la première fois, une ligne `[INFO]` donne les clés reçues) ; lecture absente ou incomplète : réessai au
  tick suivant, sans erreur.
- `reset_for_next_game` (`lifecycle.py:286`) : `scout.stop()`, publication `players` à `None`.
- `src/client/en_partie.py` : `en_partie_view(..., players=None)` ; `analysis_view` ajoute à chaque côté du
  face-à-face une clé `form` : `{label, tone, n, detail: [{window, …}], pending}` retrouvée par
  `champion_id`. `label` : ΔP moyen à 10 parties signé (« +3,1 ») si `impact_n` ≥ `SCOUT_MIN_IMPACT_GAMES`,
  sinon le taux de victoire (« 60 % V »), sinon « … » en attente. `tone` : `high` / `mid` / `low` selon les
  quartiles mesurés (§2), `neutral` pour le taux de victoire.
- `src/client/app.py:480` passe `latest("players")` ; le sujet `players` rejoint la liste d'abonnement de
  l'écran (`app.py:694`).
- Gabarit `partials/en_partie_stage.html` : pastille après le score de chaque champion, `title` = détail 5 /
  10 / 20 sur une ligne chacun (`n` parties, V %, KDA, CS/min, sur ce champion, ΔP moyen). CSS dans
  `static/style.css`, sans changer la hauteur d'une ligne du face-à-face.

### 4.5 `scripts/bench_scout.py` — le banc

- Refuse de tourner si le client est fermé, en draft, en acceptation ou en partie ; demande de fermer le
  Live Coach. Copie `crawl.db` dans un dossier temporaire (même modèle que `scripts/bench_search.py`) : la
  base de production n'est ni modifiée ni lue en écriture.
- Pour chaque palier `--workers 1,4,8,12,16` : dix `puuid` **jamais visités** pris dans `crawl_frontier`
  (hors cache du client, SPEC-23 §1), un `Scout` frais, `step()` à `SCOUT_TICK_S`. Relevé : temps jusqu'aux
  dix formes brutes, jusqu'à 5 / 10 / 20 impacts pour les dix, p50 / p95 par type de requête, erreurs, 429,
  part servie par le cache.
- Arrêt au premier : 429, erreurs > 2 %, p95 d'un type > 2× sa valeur à 4 workers (critère de SPEC-23 §2).
  Conclusion `[DATA] Workers retenus : N` = le plus petit palier dont le temps jusqu'à 10 impacts est à
  moins de 10 % du meilleur palier propre.
- Imprime aussi les quartiles des moyennes à 10 parties (seuils de la pastille, §2).
- `--dry-run` : un palier à 4 workers, 2 joueurs.

### 4.6 Mesure du terme de forme (phase 2)

`scripts/measure_form_term.py` (tâche 159) : pour chaque partie lue de `crawl.db`, la forme de chacun des dix joueurs
**avant** la partie, tirée de ses parties antérieures dans `crawl_histories` (forme brute) et `crawl.db` (impact ΔP moyen), voir « Données » ci-dessous (taux de
victoire sur 10, à défaut sur ce qui existe, au moins `SCOUT_MIN_IMPACT_GAMES`) ; variable d'équipe =
différence des moyennes bleu − rouge ; joueur sans forme = 0. Ajustement de la logistique de `model.py`
avec cette variable et son produit avec le temps, validation croisée poolée à 5 blocs de parties, contre le
modèle en place sur les **mêmes** blocs. Sortie : Brier toutes images et ≤ 10 min, écart par décile, AUC,
nombre de parties couvertes. Seuil d'adoption du §2, figé avant de lancer.

**Données** : la couverture du §1 (0,9 % des parties à dix joueurs couverts) exclut de mesurer la forme
par l'impact sur `crawl.db` seul. La tâche 158 ajoute donc à la collecte une table
`crawl_histories(puuid, game_id, creation_utc, queue_id, champion_id, win, kills, deaths, assists, cs,
duration_s)`, clé (`puuid`, `game_id`), remplie à chaque visite d'historique par `form.ranked_games` (la
réponse est déjà lue, aucune requête de plus), et l'éclaireur y range aussi les historiques qu'il lit. La
mesure porte alors sur la **forme brute** (taux de victoire et KDA à 10 parties antérieures) ; la forme par
l'impact est mesurée en second, sur le sous-ensemble couvert (parties à ≥ 8 joueurs sur 10 avec ≥ 5 parties
d'impact), et signalée comme telle. La mesure attend que `crawl_histories` couvre au moins
`FORM_MIN_COVERED_GAMES` parties à dix joueurs connus (à quelques jours de collecte : chaque partie lue de
profondeur 1 fait visiter ses dix joueurs).

**Si le terme est adopté** (tâche 161, conditionnelle) : `INPUTS` gagne `form`, `state_from_live` reçoit la
forme d'équipe de l'éclaireur (0 tant qu'inconnue), la timeline la reçoit de la même façon pour les impacts
d'après-partie (0 : pas de forme connue pour les parties passées), et l'écran affiche la win chance au
chargement. À détailler par un amendement de cette spec une fois la mesure faite. **Sinon**, la mesure est
consignée en §7 et le modèle ne change pas.

### 4.7 Constantes (`src/config_winprob.py`)

| Constante | Valeur | Origine |
|---|---|---|
| `SCOUT_WORKERS` | 8 puis banc (tâche 155) | ~10 historiques en vol au départ ; remplacée par la mesure |
| `SCOUT_IN_GAME_WORKERS` | 2 | @pj35, 2026-10-13 (§2) ; ordre de grandeur du débit en partie de SPEC-23 |
| `SCOUT_TICK_S` | 0,25 | le coordinateur range et publie 4 fois par seconde : pastilles fluides, coût négligeable |
| `SCOUT_HISTORY_WORKERS` | 1 | banc du 2026-10-13 (§7) : historiques servis un par un par le LCU |
| `SCOUT_REQUEST_TIMEOUT_S` | 15 | banc du 2026-10-13 : à 4 workers, les historiques en file dépassaient les 5 s du client (p95 5,1 s, 7 échecs sur 82 requêtes) |
| `SCOUT_LIVE_POLL_S` | 1,0 | ajoutée à l'implémentation (2026-10-13) : lecture de la Live Client API par l'éclaireur, jusqu'au premier `gameTime` > 0 seulement (mode console compris) |
| `SCOUT_WINDOWS` | `(5, 10, 20)` | @pj35, 2026-10-13 |
| `SCOUT_BADGE_WINDOW` | 10 | @pj35, 2026-10-13 |
| `SCOUT_MIN_IMPACT_GAMES` | 3 | en dessous, la moyenne est un tirage ; la pastille montre le taux de victoire |
| `SCOUT_IMPACT_QUARTILES` | `scripts/measure_scout_quartiles.py` (tâche 155) | quartiles mesurés sur `crawl.db` (§2, amendé le 2026-10-14) |
| `FORM_MIN_COVERED_GAMES` | 5 000 | `WINPROB_MIN_PATCH_GAMES` : la taille à laquelle la logistique de SPEC-20 est calibrée |

### 4.8 Tests (hermétiques : `FakeLCU`, exécuteur synchrone, `crawl.db` temporaire, fixtures)

`tests/test_winprob_form.py` et `tests/test_winprob_scout.py` :

1. `ranked_games` : files hors `QUEUE_IDS` écartées, entrée mal formée ignorée, ordre conservé.
2. `form` : KDA sans mort, CS/min, `on_champion`, fenêtre plus grande que l'historique (`n` réel), impact
   `None` sans partie d'impact.
3. Ordre §3.2 (amendé le 2026-10-14) : un historique en vol à la fois ; les parties d'un joueur partent dès son historique revenu ; entre joueurs connus, par rang.
4. Une partie présente dans `crawl.db` ne déclenche aucune requête et a son impact.
5. Une partie lue est rangée dans `crawl_games` sous la forme de `Crawler._read_game` (même `unpack`), et
   les dix `puuid` sont marqués visités.
6. Un 429 arrête les soumissions, garde les formes acquises ; une exception de worker ne sort pas de `step()`.
7. Aucune écriture SQLite hors du fil coordinateur (test de garde, comme SPEC-23 test 9).
8. `Crawler._paused()` vrai tant que l'éclaireur est actif.
9. `last_status_code` : deux threads ne voient pas le statut l'un de l'autre.
10. `analysis_view` avec `players` : pastille ΔP, repli sur le taux de victoire, « … » en attente, infobulle
    5 / 10 / 20, aucun changement sans `players`.
11. `lifecycle` : éclaireur lancé une fois par épisode en `InProgress`, jamais en draft, arrêté à
    `reset_for_next_game`.
12. `crawl_histories` : une visite de la collecte y range les parties classées de l'historique (hors files
    ignorées, sans doublon à la revisite), sans requête de plus.

## 5. Tâches

Numéros globaux : suite du `TODO.md` (dernière tâche : 150).

| # | Tâche | Pts | Dépend de |
|---|---|---|---|
| 151 | `LCUClient` : `last_status_code` thread-local, `pooled_session`, `get_player_history` ; test 9 ; SPEC-23 tâche 62 marquée absorbée | 2 | — |
| 152 | `src/winprob/form.py` et tests 1-2 | 2 | 151 |
| 153 | `src/winprob/scout.py` : pool, coordinateur, ordre par rang, cache et rangement dans `crawl.db` (`store_game` extrait de `_read_game`), 429, en partie, publication ; constantes ; tests 3-8 | 5 | 151, 152 |
| 154 | `scripts/bench_scout.py` (copie temporaire, paliers, critères d'arrêt, quartiles, `--dry-run`) | 3 | 153 |
| 155 | **Banc réel (par @pj35, client ouvert en lobby, Live Coach fermé)** : consigner le tableau en §7, fixer `SCOUT_WORKERS` ; `SCOUT_IMPACT_QUARTILES` par `scripts/measure_scout_quartiles.py` (amendé le 2026-10-14) | 1 | 154 |
| 156 | Branchement : `lifecycle` (lancement en `InProgress` depuis la session gameflow, arrêt), pause de la collecte, sujet `players` ; test 11 | 3 | 153 |
| 157 | Écran : `analysis_view` (`form`), `app.py`, gabarit, CSS ; test 10 ; `scripts/measure_en_partie.py` avec pastilles : marge ≥ 20 px à 1 920 × 986 | 5 | 155, 156 |
| 158 | `crawl_histories` : table, remplissage à chaque visite de la collecte et par l'éclaireur ; test 12 | 3 | 152, 153 |
| 159 | `scripts/measure_form_term.py` : seuil du §2 figé, attente de `FORM_MIN_COVERED_GAMES`, forme brute puis forme par l'impact sur le sous-ensemble couvert, résultat en §7 | 5 | 158 |
| 160 | Clôture : `CHANGELOG.md`, statut, README des specs, `PROJECT_STRUCTURE.md`, modules ajoutés à `check_exe_assets.py`, recette @pj35 | 2 | 157, 159 |
| 161 | *Conditionnelle* : terme de forme dans le modèle (§4.6), si la tâche 159 l'adopte ; amendement de la spec d'abord | 3 | 159 |

## 6. Critères d'acceptation

1. `python -m pytest tests/ -v` vert, avec les tests du §4.8 ; `python -m pytest tests/test_winprob_form.py tests/test_winprob_scout.py -v` vert seul.
2. `grep -n "check_same_thread" src/winprob/scout.py` ne renvoie rien (SQLite mono-thread).
3. Les constantes du §4.7 sont dans `src/config_winprob.py` ; aucune valeur de réglage en dur dans `scout.py` ni `form.py`.
4. `python scripts/bench_scout.py --dry-run` (client ouvert, hors partie) imprime un palier, un p95 par type de requête, et laisse `data/crawl.db` intacte (mtime et taille).
5. Le banc complet (tâche 155) s'arrête sans 429, imprime `[DATA] Workers retenus : N` et les quartiles ; le tableau est consigné en §7, avec le temps jusqu'aux dix formes brutes et jusqu'à 10 impacts pour les dix.
6. `python scripts/measure_en_partie.py` : marge ≥ 20 px à 1 920 × 986 avec les pastilles, `scrollWidth` = `clientWidth`.
7. `python scripts/measure_form_term.py` imprime Brier (toutes images, ≤ 10 min), écart par décile et décision au seuil du §2 ; résultat consigné en §7.
8. `CHANGELOG.md` (`[Unreleased]`), statut de cette spec, `docs/specs/README.md`, `TODO.md` et SPEC-23 (tâche 62) à jour.

**Vérification de bout en bout** : une partie classée, Live Coach lancé, écran « En partie » ouvert dès le
chargement. Les dix pastilles affichent un taux de victoire en quelques secondes, puis un ΔP moyen ;
l'infobulle donne 5 / 10 / 20 ; la ligne `[DATA]` du journal dit en combien de secondes les dix formes et
les dix impacts à 10 parties sont arrivés ; aucun 429, aucune exception dans la console, la draft suivante
n'est pas ralentie (`logs/draft_monitor_ticks.log`).

## 7. Résultats

**Premier banc (@pj35, 2026-10-13, client en lobby, Live Coach fermé, 10 joueurs jamais visités)** :

| Workers | Formes | 5 impacts | 10 impacts | 20 impacts | Requêtes | Erreurs | 429 | Cache | p95 historique | p95 détail | p95 timeline |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 15,5 s | 26,4 s | 40,2 s | 64,4 s | 204 | 0 % | 0 | 34 % | 1,8 s | 0,1 s | 0,3 s |
| 4 | 13,3 s | 16,9 s | 18,5 s | 22,7 s | 82 | 8,5 % | 0 | 33 % | 5,1 s | 1,0 s | 0,7 s |

Arrêt au palier 4 (7 erreurs sur 82 requêtes). Lecture : les historiques ne gagnent presque rien en
parallèle (le LCU les sert un par un) et dépassent le délai de 5 s du client ; les joueurs dont l'historique
échoue n'ont aucune partie lue, d'où 82 requêtes au lieu de 204. Les parties, elles, sont rapides (détail
0,1 s, timeline 0,3 s au p95 à 1 worker ; aucune timeline à 3-17 s). Quartiles sur 13 joueurs : Q1 −3,2,
médiane −1,7, Q3 +1,0, trop peu pour fixer les seuils. D'où l'amendement du 2026-10-14 (§2, §3.2, §4.7) ;
banc à relancer pour fixer `SCOUT_WORKERS`.

**Seuils de couleur (2026-10-14, `python scripts/measure_scout_quartiles.py`, `crawl.db` en lecture seule,
Live Coach ouvert)** : 76 420 parties lues en 29 min, 21 177 joueurs à 10 parties ou plus ; impact moyen à
10 parties : **Q1 −3,8, médiane +0,1, Q3 +4,0** points. `SCOUT_IMPACT_QUARTILES = (-3.8, 4.0)`.

**Second banc (2026-10-15, client sur l'accueil, Live Coach fermé, ordre amendé : un historique en vol, parties
dès le retour de chaque historique)** :

| Workers | Formes | 5 impacts | 10 impacts | 20 impacts | Requêtes | Erreurs | 429 | Cache | p95 historique | p95 détail | p95 timeline |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 3,6 s | 16,0 s | 33,6 s | 67,9 s | 314 | 0 % | 0 | 19 % | 0,1 s | 0,1 s | 0,2 s |
| 4 | 17,6 s | 19,2 s | 21,6 s | 26,8 s | 130 | 0 % | 0 | 38 % | 2,0 s | 1,5 s | 0,6 s |
| 8 | 22,8 s | 24,7 s | 25,8 s | 32,6 s | 216 | 0 % | 0 | 28 % | 2,7 s | 2,0 s | 1,2 s |
| 12 | 25,2 s | 27,9 s | 30,8 s | 41,9 s | 296 | 0 % | 0 | 19 % | 3,4 s | 2,6 s | 2,7 s |

Arrêt au palier 12 (p95 timeline > 2 × sa valeur à 4 workers) ; `[DATA] Workers retenus : 4`. Lecture : plus
aucune erreur ni 429 ; 4 workers donnent les 10 impacts au plus tôt (21,6 s). Mais les parties lues en parallèle
ralentissent les historiques (p95 0,1 s seuls, 2,0 s à 4 workers) : les formes brutes passent de 3,6 s à
17,6 s. Une mesure par palier, sur des joueurs différents (requêtes et cache varient) : ordre de grandeur.

*Forme de la session gameflow (recette) et mesure du terme de forme (tâche 159) : à remplir.*

## 8. Hors périmètre

- ❌ Revue d'après-partie : le classement des dix joueurs de cette partie existe (SPEC-32) ; la forme
  passée des joueurs n'y est pas ajoutée (@pj35 : « dans l'analyse in-game »).
- ❌ Lecture pendant la draft (alliés connus en champ select) : remettrait des requêtes dans la draft.
- ❌ Seconde page d'historique, parties normales ou ARAM.
- ❌ Rang et LP des joueurs (`/lol-ranked/v1/ranked-stats/{puuid}`) : non demandé ; une requête de plus
  par joueur, à ajouter si l'avis sur le niveau en manque.
- ❌ Ajustement de la win chance sans mesure (§2).
- ❌ Clé API Riot (arbitrage SPEC-19/20 maintenu).
