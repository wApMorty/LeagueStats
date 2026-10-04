# SPEC-23 — Débit de la collecte : concurrence, spike et régime de croisière

**Statut** : 🟡 Rédigée le 2026-10-04. Architecture, critère d'arrêt du spike, régime en partie et
régime de croisière validés par @pj35 (§2) ; les valeurs numériques marquées « à valider » se fixent
après le spike (tâche 66).

**Origine** : @pj35, 2026-10-04 : « revoir le taux de requêtes max sur la récupération de données
pour le modèle. L'API Riot pose un rate limiting de 30k requêtes/10 min, on pourrait au moins match
ce taux (ou à défaut faire un spike/benchmark pour voir jusqu'à combien on peut monter). »

**Effort** : ~2 jours, 6 tâches, 16 pts (§5).

---

## 1. Constat

Mesuré le 2026-10-04 (client ouvert, `data/crawl.db` lue en lecture seule, sonde jetable non versionnée).

- **La limite de 30 000 req/10 min (50 req/s) ne s'applique pas à notre collecte.** `src/winprob/crawl.py`
  passe par le LCU (`LCUClient._make_request`, `src/lcu_client.py:196`), le client local, et non par
  l'API publique Riot (SPEC-20 §2 : « pas de clé API »). Le LCU relaie vers le backend de Riot avec la
  session du joueur ; aucune limite n'y est documentée, et la provenance du chiffre de 30 000 n'est pas
  vérifiée ici. 50 req/s reste un **plafond de référence**, pas une mesure : le seul moyen de connaître
  la limite réelle du LCU est de la mesurer (§3).
- **Débit actuel : ~2 req/s au pic, pas 1.** `CRAWL_REQUEST_INTERVAL_S = 1.0` sépare des **unités de
  travail**, pas des requêtes : lire une partie fait 2 requêtes (détail, timeline,
  `crawl.py:165-176`) puis une seule attente (`_throttled` du détail est écrasé par celui de la
  timeline). La boucle du Live Coach ne fait qu'un pas par tick (`POLL_INTERVAL = 1.0`,
  `src/config_constants.py:256`, appel en `lifecycle.py:88`). Pic mesuré : **3 364 parties lues en
  une heure** (2026-10-02, 00 h), soit 0,93 partie/s ≈ 2 req/s ; le débit moyen des heures suivantes
  est de 1 000 à 1 750 parties/h (les visites d'historique occupent aussi des pas).
- **Latences par type** (6 requêtes séquentielles chacune, statut 200) : historique d'un joueur
  1,4 à 1,7 s ; détail d'une partie 60 à 280 ms ; timeline 13 à 213 ms. En séquentiel, l'historique
  plafonne à ~0,7 req/s : seule la concurrence permet de dépasser quelques req/s.
- **Une relecture est servie du cache du client** : 24 détails déjà lus, relus à 8 en parallèle,
  répondent en 59 ms (70 req/s) contre 550 ms à 4 en parallèle sur la première lecture. Un benchmark
  doit donc lire des parties **jamais demandées**, sinon il mesure le cache local et non la limite
  (§4.4).
- **Jamais de 429 observé** à ce jour. Cela ne dit rien d'un débit 25 fois supérieur : le message
  d'alerte va à la console, aucun journal ne le conserve.
- **`LCUClient.last_status_code` est un attribut d'instance** (`lcu_client.py:43,196,209`) lu par le
  collecteur après chaque appel. Sûr tant que tout tourne dans le même thread ; faux dès que des threads
  partagent le client (le thread de la boucle l'écrase à chaque poll de draft).
- **État de la base** : 12 234 parties lues, 6 à lire, 22 204 joueurs en attente de visite, tout au
  patch 16.19. Le plafond `CRAWL_MAX_GAMES` (100 000, ~1,6 Go) se remplirait en ~1 h à 50 req/s ; au-delà,
  la collecte lirait pour purger les plus anciennes (SPEC-20 §3.1).

## 2. Objectif et arbitrages

**Objectif** : porter le débit de collecte de ~2 req/s à la valeur la plus haute que le LCU tient sans
réaction, plafonnée à 50 req/s, **sans ralentir la boucle de draft ni exposer le compte**, puis revenir à
un débit de croisière une fois le patch courant bien fourni.

| Sujet | Décision |
|---|---|
| Plafond | 50 req/s (30 000 req/10 min) en **plafond de référence**. Le débit retenu vient du spike (§3.2), pas du chiffre. |
| Architecture | **Validé (@pj35, 2026-10-04)** : pool de threads qui ne font que les requêtes HTTP ; `step()` (thread du Live Coach) en soumet un lot par tick et range les résultats. SQLite reste mono-thread. Écarte, sur ce seul point, l'approche A de SPEC-20 §2 (« un pas par tick, sans thread ») ; la pause en draft garde sa forme (`step()` n'est pas appelé, donc plus de soumission). |
| Critère d'arrêt du spike | **Validé (@pj35, 2026-10-04)** : paliers 2, 5, 10, 20, 35, 50 req/s de 30 s ; arrêt à la première des trois : latence p95 d'un type de requête > 2× sa valeur au palier 2, erreurs > 2 %, premier 429. Débit retenu = 50 % du dernier palier propre, plafond 50 req/s. Jamais de 429 volontaire. |
| En partie | **Validé (@pj35, 2026-10-04)** : plein débit en lobby et file, débit réduit en partie (`CRAWL_IN_GAME_RPS`, valeur actuelle ~2 req/s). Draft et ready check restent en pause. |
| Cible | **Validé (@pj35, 2026-10-04)** : une fois `CRAWL_TARGET_GAMES` parties lues sur le dernier patch, débit de croisière bas (`CRAWL_CRUISE_RPS`) ; un nouveau patch, dont le compte repart de zéro, retrouve le plein débit. |
| `CRAWL_TARGET_GAMES` | **À valider** : 30 000 proposé (la logistique de SPEC-20 est calibrée à 5 300 parties, §4.3 bis ; 100 000 reste le plafond de stockage). |
| `CRAWL_CRUISE_RPS` | **À valider** : 1 req/s proposé (suit une dizaine de parties par jour de jeu, largement). |
| Valeurs initiales avant le spike | `CRAWL_RATE_RPS = 5` (2,5× l'actuel), `CRAWL_IN_GAME_RPS = 2`, `CRAWL_WORKERS = 12`. Prudentes ; remplacées à la tâche 66. |

## 3. Approches considérées

**3.1 Architecture de la concurrence** (arbitrée ci-dessus)

| Approche | Compromis |
|---|---|
| **Pool de threads, écritures dans la boucle (retenue)** | Le débit n'est borné que par la limite du LCU. SQLite reste mono-thread (le défaut `check_same_thread=True` de `sqlite3` interdit toute écriture d'un worker : garde-fou gratuit). La pause en draft reste « ne plus soumettre ». Coût : un thread de travail à arrêter proprement, `last_status_code` à rendre thread-local. |
| Lot séquentiel par tick | Aucune concurrence, aucun risque de thread, mais plafond ~1/latence (3 à 5 req/s) et la boucle de draft est bloquée d'autant. Insuffisant pour le plafond visé. |
| Processus séparé (`scripts/crawl.py`) | Isole la draft, mais perd la pause automatique et le déclenchement en fin de partie, et double l'infrastructure (identifiants LCU, reprise). |

**3.2 Mesure de la limite** : le spike rejoue le **vrai `Crawler`** sur une copie temporaire de
`crawl.db` (même modèle que `scripts/bench_search.py`, SPEC-17 §4.4), à chaque palier de débit. Pas de
script de requêtes parallèle à part : la mesure exerce le code qui servira, et les parties lues sont
celles de la file (jamais demandées, donc hors cache local, §1).

## 4. Détail

### 4.1 `src/lcu_client.py` — statut par thread

`last_status_code` devient une propriété adossée à `threading.local()` : chaque thread voit le statut de
son dernier appel. L'API publique ne change pas (même nom, même lecture) ; les tests existants
(`tests/test_winprob_crawl.py:352-361`) continuent de s'appliquer.

Les workers du collecteur utilisent une **session `requests` à part** (`verify=False`, un
`HTTPAdapter(pool_maxsize=CRAWL_WORKERS)`) : le pool par défaut de 10 connexions jetterait des
connexions en silence au-delà, et la session du Live Coach ne doit pas être affamée par le collecteur.
Méthode `LCUClient.crawl_session()` (ou équivalent), mêmes identifiants.

### 4.2 `src/winprob/crawl.py` — pool et jetons

- **Constructeur** : `Crawler(monitor, path=None, clock=time.monotonic, executor=None)` ; le défaut crée
  un `ThreadPoolExecutor(max_workers=cfg.CRAWL_WORKERS, thread_name_prefix="crawl")`. Les tests
  injectent un exécuteur synchrone (`submit` exécute et renvoie un `Future` terminé).
- **`step(phase: str = "") -> None`** (remplace `step()`, `lifecycle.py:88` passe la phase de gameflow) :
  1. récolte les `Future` terminés et écrit leurs résultats (une transaction, un `commit` par tick) ;
  2. si pause 429 en cours, s'arrête ici ;
  3. recharge le panier : `jetons = min(jetons + débit × dt, débit × CRAWL_BURST_S)` ;
  4. choisit jusqu'à `jetons` requêtes de travail, **parties à lire d'abord** (2 jetons), complétées par
     des visites d'historique (1 jeton) ; la sélection SQL (`LIMIT ?`, paramétrée) exclut les identifiants
     déjà en vol (ensemble en mémoire) ; soumet.
- **Débit effectif** : `CRAWL_IN_GAME_RPS` si `phase` ∈ `CRAWL_IN_GAME_PHASES` (`GameStart`,
  `InProgress`, `Reconnect`) ; `CRAWL_CRUISE_RPS` si la cible est atteinte (§4.3) ; sinon
  `CRAWL_RATE_RPS`. Le minimum des deux cas s'applique.
- **Travail des workers** (fonctions pures de HTTP + CPU, **jamais de base**) : lire une partie =
  détail, puis timeline si le détail est valide, puis `pack()` (compression `zlib`, qui libère le GIL) ;
  visiter = historique. Chaque fonction renvoie `(résultat, statut, latence)` avec le statut lu **dans le
  thread** ; toute exception est capturée et devient un résultat « échec, à réessayer ».
- **429** : si un résultat porte 429, pause `CRAWL_BACKOFF_S` (comme aujourd'hui, `[ALERTE]` en console),
  plus aucune soumission ; les unités concernées restent `raw IS NULL` / `visited_utc IS NULL` et sont
  reprises ensuite. Les résultats déjà prêts d'autres workers sont tout de même rangés.
- **Client injoignable** (`statut None`) : l'unité n'est pas marquée, retentée plus tard (comportement actuel).
- **Arrêt** : `shutdown(wait=False, cancel_futures=True)` appelé à la fermeture du monitor ; les requêtes
  en vol ont un `timeout=5` (`lcu_client.py:207`), la sortie attend au plus quelques secondes.
- **Mesures** : `Crawler.samples` (`collections.deque`, `maxlen=cfg.CRAWL_SAMPLES`) reçoit
  `(type, latence_s, statut)` pour chaque requête (`history`, `detail`, `timeline`) et
  `Crawler.step_durations` la durée de chaque `step()`. Lus par le bench ; sans effet sur la collecte.
- **Invariants** : aucune écriture SQLite hors du thread de la boucle (`sqlite3.connect` sans
  `check_same_thread=False`) ; `step()` reste best-effort (`_safely`), aucune exception ne remonte à la
  boucle de draft (CLAUDE.md).

### 4.3 Cible et croisière

`Crawler._target_reached()` : nombre de parties lues (`length(raw) > 0`) du **dernier patch** (le plus
grand `_patch(game_version)` parmi les parties lues, calcul analogue à `_purge`, requête paramétrée) ≥
`CRAWL_TARGET_GAMES`. Compté au démarrage, à chaque `seed()` et tous les `CRAWL_PURGE_EVERY` lectures
(pas à chaque tick).

Un nouveau patch apparaît dans les historiques des joueurs de la file : ses premières parties lues font
redescendre le compte du « dernier patch » sous la cible, donc le plein débit revient sans intervention.
Les parties du patch précédent encore « à lire » à ce moment sont lues pour rien puis purgées ; à
mesurer sur le premier changement de patch (§7).

### 4.4 `scripts/bench_crawl_rate.py` — le spike

- Refuse de tourner si le client est fermé, ou si la phase de gameflow est `ChampSelect`, `ReadyCheck`,
  en partie ou une fin de partie ; demande de fermer le Live Coach (deux collecteurs concurrents faussent
  la mesure).
- Copie `data/crawl.db` dans un dossier temporaire ; la base de production n'est ni lue en écriture ni
  modifiée. Les parties lues pendant le bench ne sont pas conservées.
- Pour chaque palier (`--steps 2,5,10,20,35,50`, `--seconds 30`) : un `Crawler` frais sur la copie, au débit
  du palier, `step()` appelé à 1 Hz comme la boucle. Relevé : débit effectif, p50/p95 de latence par type,
  taux d'erreurs, nombre de 429, p95 de `step_durations`.
- Applique les critères d'arrêt du §2 et conclut par `[DATA] Débit retenu : N req/s` (50 % du dernier
  palier propre, plafond 50). Option `--dry-run` : un seul palier à 2 req/s, pour vérifier le montage.
- Imprime l'alerte `[ALERTE]` et s'arrête **avant** de monter si les paliers précédents ont montré un début
  de dégradation (p95 > 1,5× la base) : pas de saut dans le vide.

### 4.5 Constantes (`src/config_winprob.py`)

| Constante | Valeur | Origine |
|---|---|---|
| `CRAWL_RATE_RPS` | 5,0 puis mesure (tâche 66) | spike §4.4 ; remplace `CRAWL_REQUEST_INTERVAL_S` (supprimée, § 1 : mal nommée) |
| `CRAWL_IN_GAME_RPS` | 2,0 | débit actuel observé (§1) |
| `CRAWL_IN_GAME_PHASES` | `("GameStart", "InProgress", "Reconnect")` | phases gameflow du LCU |
| `CRAWL_CRUISE_RPS` | 1,0 | **à valider** |
| `CRAWL_TARGET_GAMES` | 30 000 | **à valider** |
| `CRAWL_WORKERS` | 12 | débit × latence : à 50 req/s, ~7 détails/timelines et ~2 historiques en vol (§1) ; marge |
| `CRAWL_BURST_S` | 2,0 | plus que le tick de 1 s, pour ne pas perdre de débit sur un tick tardif |
| `CRAWL_SAMPLES` | 5 000 | mesures du bench |

`CRAWL_BACKOFF_S`, `CRAWL_MAX_GAMES`, `CRAWL_PURGE_EVERY` inchangées.

### 4.6 Tests (hermétiques : `FakeLCU`, exécuteur synchrone, `crawl.db` temporaire)

Dans `tests/test_winprob_crawl_rate.py` (le `_drain` de `test_winprob_crawl.py` est adapté au nouveau
`step`) :

1. Un tick de 1 s à `R` req/s soumet au plus `R` requêtes ; à `dt` ≥ `CRAWL_BURST_S` le panier plafonne.
2. Une partie coûte 2 jetons, un historique 1 ; les parties passent avant les visites.
3. Un identifiant en vol n'est pas resélectionné au tick suivant.
4. `phase="InProgress"` applique `CRAWL_IN_GAME_RPS` ; `phase=""` le plein débit.
5. Cible atteinte → débit de croisière ; un patch plus récent avec peu de parties → plein débit.
6. Un 429 d'un worker suspend toute soumission pendant `CRAWL_BACKOFF_S`, laisse l'unité non marquée, et
   n'empêche pas de ranger les autres résultats du lot.
7. Une exception dans un worker ne sort pas de `step()` et l'unité est retentée.
8. `last_status_code` : deux threads ne voient pas le statut l'un de l'autre (test de `LCUClient` avec
   `requests` simulé).
9. Aucune écriture hors du thread de la boucle : un worker qui touche la base lève (test de garde).

## 5. Tâches

Numéros globaux : suite du `TODO.md` (dernière tâche : 61).

| # | Tâche | Pts | Dépend de |
|---|---|---|---|
| 62 | `LCUClient.last_status_code` thread-local, session `crawl_session()` à pool dimensionné, test 8 | 2 | — |
| 63 | `Crawler` : exécuteur, jetons, en vol, rangement dans la boucle, 429, mesures ; constantes ; tests 1-3, 6, 7, 9 ; `_drain` adapté | 5 | 62 |
| 64 | Débit en partie et croisière : `step(phase)`, `lifecycle.py`, `_target_reached()`, tests 4-5 | 3 | 63 |
| 65 | `scripts/bench_crawl_rate.py` (copie temporaire, paliers, critères d'arrêt, `--dry-run`) | 3 | 63 |
| 66 | **Spike réel (par @pj35, client ouvert, Live Coach fermé)** : lancer le bench, consigner le tableau en §7, fixer `CRAWL_RATE_RPS` | 2 | 64, 65 |
| 67 | Docs : SPEC-20 §2, §3.1, §9 (débit, thread), `CHANGELOG.md`, statut, README des specs | 1 | 66 |

## 6. Critères d'acceptation

1. `python -m pytest tests/ -v` vert, avec les tests du §4.6 ; `python -m pytest tests/test_winprob_crawl.py tests/test_winprob_crawl_rate.py -v` vert seul.
2. `grep -rn "CRAWL_REQUEST_INTERVAL_S" src tests scripts` ne renvoie rien ; les constantes du §4.5 sont dans `src/config_winprob.py`.
3. `grep -n "check_same_thread" src/winprob/crawl.py` ne renvoie rien (SQLite mono-thread).
4. `python scripts/bench_crawl_rate.py --dry-run` (client ouvert, hors partie) imprime un palier à 2 req/s et un statut par type de requête, sans modifier `data/crawl.db` (mtime et taille inchangés).
5. Le bench complet (tâche 66) s'arrête sur un des critères du §2 **sans 429**, imprime `[DATA] Débit retenu : N req/s` avec N ≤ 50, et le tableau est consigné en §7.
6. Au débit retenu, le débit effectif du bench est ≥ 80 % du débit demandé, et le p95 de `step_durations` ≤ 0,25 s (la boucle de draft n'est pas ralentie).
7. Aucune exception ni `[ALERTE]` 429 pendant 1 h de Live Coach (lobby, file, partie) au débit retenu ; la ligne `[DATA] Collecte` de fin de partie montre ≥ 80 % du débit en parties/h attendu (`2 req/partie`).
8. Pendant une draft, aucune requête de collecte n'est soumise (test existant de `lifecycle` inchangé) ; en partie, le débit est `CRAWL_IN_GAME_RPS`.
9. `CHANGELOG.md` (`[Unreleased]`), SPEC-20 §2/§3.1/§9, statut de cette spec et `docs/specs/README.md` à jour.

**Vérification de bout en bout** : Live Coach ouvert en lobby 10 min au débit retenu ; `progress()` montre
la progression attendue (parties lues/h), aucun 429, puis une draft lancée : aucun retard visible des
recommandations.

## 7. Résultats du spike

*À remplir à la tâche 66 : tableau palier / débit effectif / p95 par type / erreurs / 429 / p95 de step ;
critère d'arrêt déclenché ; débit retenu.*

## 8. Risques

- **Le compte** : le LCU n'est pas une API supportée par Riot ; un débit anormal sur des historiques tiers
  peut déclencher une réaction (429, ou pire côté compte). Atténuation : spike par paliers avec arrêt avant
  tout 429 volontaire, retenue à 50 % du dernier palier propre, pause de 15 min au premier 429 au quotidien.
  Le risque résiduel est celui de SPEC-20 §9, avec un débit plus haut : à accepter par @pj35 avant la
  tâche 66.
- **Draft et partie** : un lot en vol à l'ouverture de la draft occupe le LCU quelques centaines de ms
  (`timeout=5`, ~12 requêtes). Mesuré au critère 6 ; session séparée pour ne pas affamer celle du Live Coach.
- **Patch** : parties « à lire » de l'ancien patch lues pour rien au plein débit après un changement de
  patch (§4.3).
- **Débit réel < débit demandé** : la boucle ne tick qu'à ~1 Hz ; au plafond, la résolution est de ~50
  requêtes par tick. Mesuré au critère 6, pas corrigé d'avance.

## 9. Hors périmètre

- ❌ Clé API Riot et API publique (arbitrage SPEC-19/20 maintenu) : la limite de 30 000 req/10 min ne
  concerne pas le LCU.
- ❌ Régulation adaptative en cours de route (baisse du débit sur latence ou erreurs) : le spike fixe le
  débit, le 429 déclenche la pause. À rouvrir si le débit retenu se révèle instable à l'usage.
- ❌ Collecte hors Live Coach (processus séparé, tâche planifiée) : écarté au §3.1 ; les mises à jour restent
  manuelles (CLAUDE.md).
- ❌ Scrape LoLalytics (`parallel_parser*`, ~45 min) : autre source, autre limite (Cloudflare, Selenium).
