# SPEC-20 — Win chance en partie et impact de chaque joueur

**Statut** : 🟡 **Rédigée le 2026-10-01**, ordre des phases validé par @pj35 (§2). Arbitrages
marqués « à valider » en §2 avant la phase 1.

**Origine** : @pj35, 2026-10-01. Les constats de SPEC-19 confondent cause et effet : la grille a
été révisée sur le d de Cohen victoire/défaite, qui favorise les **conséquences** de la victoire
(dégâts aux structures, morts / 10 min sur toute la partie) plutôt que ce que le joueur contrôle.
Proposition : « calculer en live le win chance d'une game, et mesurer mes impacts
positifs/négatifs dans la game », comme Coachless ou DPM (overlay en jeu, autorisé par Riot).

**Effort** : ~8 jours sur cinq phases (§10), à redécouper après la phase 1.

---

## 1. Principe

Un modèle **P(victoire | état de la partie à l'instant t)** juge chaque événement selon l'état
où il survient. Une mort à 8 000 or de retard ne coûte presque rien ; la même 30 s avant un
Nashor coûte cher. L'**impact** d'un événement est la variation de win chance qu'il provoque
(ΔP), attribuée aux joueurs impliqués. On ne mesure plus une corrélation avec le résultat mais
une contribution marginale, conditionnée à l'état.

Trois usages, dans cet ordre :
1. **Après la partie** : courbe de win chance, tournants de la partie, impact cumulé du joueur
   et ses événements les plus coûteux ou rentables, dans le rapport de SPEC-19.
2. **Suivi dans le temps** : l'impact par partie et par type d'événement alimente les schémas et
   les axes de travail de SPEC-19 (§7 de celle-ci), à côté de la grille.
3. **En jeu** : overlay affichant la win chance courante (dernière phase, une fois le modèle
   calibré : un pourcentage faux affiché en jeu est pire que rien).

## 2. Arbitrages

| Sujet | Décision |
|---|---|
| Ordre | **Validé (@pj35, 2026-10-01)** : collecte → modèle → impact après la partie → overlay en jeu. |
| Source d'entraînement | **LCU**, parties de joueurs tiers, collectées de proche en proche à partir des parties du joueur (§3). Pas de clé API Riot (arbitrage SPEC-19 maintenu). |
| Source en jeu | **Live Client Data API** (port 2999), sans authentification. |
| Variables du modèle | **Uniquement celles présentes dans les deux sources** (timeline LCU et Live Client), pour que le même modèle tourne après la partie et en jeu (§4.1). |
| Modèle | **À valider** : régression logistique en Python pur (stdlib), comme le reste de `src/analysis/`. Pas de numpy ni scikit-learn tant que la logistique tient la calibration. |
| Stockage du brut | **À valider** : base SQLite séparée `data/crawl.db`, JSON compressé (`zlib`, stdlib). ~160 Ko de JSON par partie (détail + timeline), ~15 Ko compressé : 5 000 parties ≈ 75 Mo, hors de `db.db` (29 Mo). |
| Collecte | **Automatique et continue (@pj35, 2026-10-01)**, en tâche de fond du Live Coach, sans action du joueur (§3.1). Débit ~1 requête/s à valider. |
| Ordonnancement | **Validé (@pj35, 2026-10-02)** : approche A, un pas de collecte par tick de la boucle du monitor, sans thread (la pause en draft va de soi). |
| Stockage du brut | **Validé (@pj35, 2026-10-02)** : `data/crawl.db` séparé, hors Alembic, JSON `zlib`. |

## 3. Données : sondage du 2026-10-01

Sonde en lecture seule (script jetable, non versionné), client ouvert, à partir de la dernière
partie du joueur :

| Requête | Résultat |
|---|---|
| `/lol-match-history/v1/products/lol/{puuid}/matches?begIndex=0&endIndex=19` pour un **autre** joueur | HTTP 200, **20 parties**, ~1,4 s. Files 420 et 450 sur les 3 joueurs testés. |
| `/lol-match-history/v1/games/{id}`, partie **sans** le joueur | HTTP 200, 10 participants, instantané (vraisemblablement en cache après la lecture de l'historique). |
| `/lol-match-history/v1/game-timelines/{id}`, même partie | HTTP 200, **15 sur 15**, de 24 à 43 images, ~0,2 s. |

Trois historiques ont donné 57 parties distinctes. Chaque partie ouvre 9 historiques de 20
parties, **au MMR du joueur** par construction. Aucun bridage observé sur ces ~35 requêtes ;
le comportement sur la durée reste à mesurer (phase 1).

### 3.1 Collecte continue

La dérive de patch impose de toute façon de renouveler les données : la collecte tourne en
continu, pas en lots.

- **Déclencheur** : chaque fin de partie capturée (SPEC-19), dans la fenêtre d'après-partie
  déjà en place. Les 9 autres joueurs de la partie passent **en tête** de file : ce sont les
  plus frais, et au MMR du moment.
- **Hors de ces moments**, la file se vide au fil de l'eau tant que le Live Coach tourne (lobby,
  file d'attente, partie en cours), **en pause pendant la draft** pour laisser le LCU au Live
  Coach.
- **Profondeur** : joueurs de tes parties (profondeur 1), puis leurs adversaires (profondeur 2) ;
  au-delà, on s'éloigne de ton MMR. Limite en configuration.
- **Ordre de grandeur** : une partie ouvre 9 historiques de 20 parties, soit ~100 parties
  classées nouvelles après dédoublonnage ; ~2 min à 1 requête/s. À 5 parties par jour, ~500
  parties par jour, 5 000 en une dizaine de jours.
- **Purge** : les parties de plus de `WINPROB_PATCH_WINDOW` patchs sont supprimées (~15 Ko
  compressé par partie, ~7,5 Mo par jour).

La timeline (SPEC-19 §3.4) donne une image par minute (or, XP, niveau, CS, position des 10) et
les événements `CHAMPION_KILL`, `BUILDING_KILL`, `ELITE_MONSTER_KILL`, horodatés à la
milliseconde. Ni achats d'items, ni wards.

## 4. Modèle de win chance (phase 2)

### 4.1 Variables

Différences entre les deux équipes (bleu − rouge), toutes disponibles dans la timeline **et**
dans la Live Client API :

| Variable | Timeline LCU | Live Client API |
|---|---|---|
| Temps | horodatage | `gameData.gameTime` |
| Kills | `CHAMPION_KILL` | `scores.kills` |
| Tours, inhibiteurs | `BUILDING_KILL` | événements `TurretKilled`, `InhibKilled` |
| Drakes (nombre, soul), Héraut, larves, Nashor (buff actif) | `ELITE_MONSTER_KILL` | événements `DragonKill`, `HeraldKill`, `BaronKill` |
| Somme des niveaux | images | `level` |
| Somme des CS | images | `scores.creepScore` |
| Joueurs morts et durée restante | déduits des kills et du niveau | `isDead`, `respawnTimer` |

L'**or** est absent de la Live Client API pour les adversaires. Il est exclu du modèle :
kills, CS et niveaux l'approchent. À mesurer en phase 2 : la perte de qualité face à un modèle
avec l'or (timeline seule), pour savoir ce que coûte ce choix.

Les champs Live Client cités sont ceux de la documentation Riot, **à vérifier** au spike de la
phase 5.

### 4.2 Forme

Logistique sur ces différences, avec interactions avec le temps (un écart de kills ne pèse pas
le même poids à 10 et à 30 min) : par tranche de temps ou terme `écart × t`, tranché sur mesure.
Le modèle est filtré par patch (`gameVersion`), réentraîné quand le patch change.

### 4.3 Validation

- **Découpage par partie**, jamais par image : les images d'une même partie sont corrélées et
  partagent l'étiquette. Validation croisée par blocs de parties.
- **Calibration** avant tout : quand le modèle dit 70 %, l'équipe gagne-t-elle ~70 % du temps ?
  Réutiliser `src/analysis/calibration.py` (`brier_score`, `calibration_curve`, `auc`), par
  tranche de temps.
- **Seuil d'acceptation** fixé avant la mesure (§11) ; en dessous, pas de phase 3.

### 4.4 Réentraînement (@pj35, 2026-10-02)

Vérifié **après chaque partie**, les sessions pouvant être longues : dans la fenêtre
d'après-partie, une fois l'impact de la partie calculé avec le modèle en place. Jamais en draft
ni en partie.

- **Déclencheur** : au moins `WINPROB_RETRAIN_MIN_NEW_GAMES` nouvelles parties depuis le dernier
  entraînement. En dessous, un nouveau modèle ne différerait que par le bruit.
- **Champion contre challenger** : le nouveau modèle n'est adopté que s'il fait au moins aussi
  bien que le modèle en place (Brier, calibration) sur un **jeu de validation commun** : les
  parties les plus récentes, jamais utilisées pour l'entraînement. Sinon il est jeté, et la
  raison est journalisée.
- **Fenêtre d'entraînement** : les `WINPROB_PATCH_WINDOW` derniers patchs.
- **Traçabilité** : chaque modèle reçoit un `model_version`. Les impacts déjà calculés restent
  figés avec la version qui les a produits (même logique que les `z` de SPEC-19).

## 5. Impact (phase 3)

Pour chaque événement de la timeline : P juste avant, P juste après (état mis à jour par
l'événement), ΔP orienté du point de vue de chaque équipe.

**Attribution** (conventions documentées, à revoir sur données) :
- **Kill** : la victime porte −ΔP ; le tueur et les assistants se partagent +ΔP à parts égales.
- **Bâtiment, monstre épique** : l'équipe porte ΔP ; la part individuelle va aux joueurs
  **présents** (position à l'image la plus proche, dans un rayon en configuration). Approximatif
  à la minute près, affiché comme tel.
- **Entre deux événements** : la variation résiduelle de P (farm, niveaux) se répartit au prorata
  de l'écart de CS et d'XP gagné par chaque joueur face à son adversaire de lane sur la minute.
- **Non mesurable** : vision, placement, gestion de vague. Le rapport le dit.

**Sortie** : l'impact cumulé du joueur (en points de win chance), ses 3 événements les plus
coûteux et les 3 plus rentables (« −9 % : mort solo à 22:40, Nashor perdu derrière »), et la
courbe de la partie (sparkline console en attendant la GUI).

## 6. Overlay en jeu (phase 5)

- **Fenêtre séparée** au premier plan, transparente, traversée par les clics : `tkinter`
  (stdlib) et `ctypes` (`WS_EX_LAYERED | WS_EX_TRANSPARENT`). **Aucune injection** dans le
  processus du jeu.
- **Limite** : le jeu doit être en **mode fenêtré sans bordure**. En plein écran exclusif,
  l'overlay est masqué. Le dire au lancement.
- `tkinter` exige le fil principal : la boucle du Live Coach passe dans un thread, l'overlay lit
  une file (`queue.Queue`) via `after()`.
- Polling de `https://127.0.0.1:2999/liveclientdata/allgamedata` toutes les secondes,
  best-effort (aucune erreur n'interrompt le Live Coach).
- Position et taille en configuration.

## 7. Lien avec SPEC-19

- L'impact par partie est stocké, et sa série entre dans le bilan et les tendances.
- Les schémas de SPEC-19 gagnent une lecture par type d'événement (« tes morts solo coûtent en
  moyenne 6 % de win chance »).
- La grille de SPEC-19 reste, mais une fois l'impact en place, **le critère de révision de la
  grille change** : une métrique y figure parce qu'elle explique de l'impact, pas parce qu'elle
  accompagne la victoire. À rouvrir après la phase 3.

## 8. Stockage et modules

**`data/crawl.db`** (base séparée, schéma créé par le module, hors Alembic : c'est un cache
recalculable, pas une donnée produit — **à valider**) :

| Table | Contenu |
|---|---|
| `crawl_games` | `game_id` (PK), `queue_id`, `game_version`, `game_creation_utc`, `duration_s`, `blue_win`, `depth`, `raw` (détail + timeline, JSON compressé, identités retirées sauf `puuid`). `raw` NULL : découverte dans un historique, à lire ; `raw` vide : détail indisponible, ne pas relire. Réalisé en phase 1 (tâche 39) |
| `crawl_frontier` | `puuid` (PK), `depth` (1 : joueur de tes parties), `priority`, `discovered_utc`, `visited_utc` (NULL si à visiter) |

**`data/db.db`**, migration Alembic en phase 3 : `game_impact` (`game_id`, `participant_id`,
`event_time_ms`, `event_type`, `delta_p`, `model_version`), pour les parties du joueur seulement.

**Paquet `src/winprob/`** (limite de 500 lignes par fichier) :

| Module | Rôle |
|---|---|
| `crawl.py` | Collecte de proche en proche, débit limité, reprise sur `crawl_frontier` |
| `state.py` | Brut (timeline LCU ou Live Client) → vecteur d'état, fonctions pures |
| `model.py` | Logistique (ajustement, prédiction), coefficients versionnés |
| `impact.py` | ΔP par événement et attribution |
| `live.py` | Lecture de la Live Client API |
| `overlay.py` | Fenêtre `tkinter` |

Les lectures LCU vont dans `src/lcu_match_history.py` (mixin existant).

## 9. Risques

- **Bridage ou réaction de Riot** au crawl : débit bas, pause au premier 429.
- **Collecte pendant la partie** : charge réseau et CPU minime à 1 requête/s, mais à vérifier
  en phase 1 (FPS, ping). Si un effet se voit, pause aussi en jeu.
- **Biais d'échantillon** : de proche en proche depuis tes parties, la collecte reste à ton
  MMR, ce qui est voulu, mais surreprésente tes adversaires récurrents. Mesurer la diversité des
  `puuid`.
- **Dérive de patch** : réentraînement filtré par `gameVersion`.
- **Attribution conventionnelle** : les règles de §5 sont des choix, pas des mesures. Les
  afficher, ne pas les présenter comme des faits.

## 10. Découpage proposé

| # | Tâche | Phase | Pts | Dépend de |
|---|---|---|---|---|
| 39 | `crawl.py` + lectures LCU tierces, `data/crawl.db`, file priorisée, branchement sur l'après-partie et la boucle du Live Coach (pause en draft), purge par patch | 1 | 5 | — |
| 40 | Une semaine de collecte réelle : volume, débit, bridage, diversité des `puuid`, consignés ici | 1 | 1 | 39 |
| 41 | `state.py` : état depuis la timeline LCU, testé sur les fixtures de SPEC-19 | 2 | 3 | — |
| 42 | `model.py` : logistique, validation par blocs de parties, calibration par tranche de temps, comparaison avec et sans l'or | 2 | 5 | 40, 41 |
| 42b | Réentraînement après chaque partie, champion contre challenger (§4.4) | 2 | 2 | 42 |
| 43 | `impact.py` : ΔP et attribution, migration `game_impact` | 3 | 5 | 42 |
| 44 | Rapport de fin de partie : impact, tournants, courbe | 3 | 2 | 43 |
| 45 | Impact dans le bilan et les schémas de SPEC-19 | 4 | 3 | 43 |
| 46 | Spike Live Client API en partie réelle (champs, `state.py` depuis le live) | 5 | 1 | 41 |
| 47 | `live.py` + `overlay.py`, Live Coach en thread | 5 | 3 | 42, 46 |

## 11. Critères d'acceptation

1. La collecte démarre seule à chaque fin de partie, reprend là où elle s'est arrêtée,
   respecte le débit configuré, se met en pause pendant la draft et au premier 429 (reprise
   après un délai en configuration).
2. Le modèle est évalué sur des parties absentes de l'entraînement. **Brier ≤ 0,20 et écart de
   calibration ≤ 5 points par décile** sur les images après 10 min (seuils à confirmer avant la
   mesure, jamais après).
3. Un même état produit la même win chance qu'il vienne de la timeline ou de la Live Client API
   (test sur un état construit des deux façons).
4. La somme des impacts attribués d'une partie est égale à la variation totale de P (P final −
   P initial), au résidu non attribué près, affiché.
5. Aucune erreur du crawl, du modèle ou de l'overlay n'interrompt la boucle du Live Coach.
6. Tests hermétiques : fixtures, jamais de client réel.

## 12. Hors périmètre

- Clé API Riot (arbitrage SPEC-19 maintenu).
- Conseils en jeu (« va au drake ») : seul le pourcentage est affiché.
- Vision et placement, faute de données.
- GUI (feature candidate 5 du TODO) : la courbe passe en console d'abord.
