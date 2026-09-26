# SPEC-19 — Coach de gameplay : analyse de fin de partie et suivi de progression

**Statut** : 🟢 **Validée par @pj35 le 2026-09-26**, schéma de suivi compris (§7, §8). Phase 0
(spike) prête à lancer (`scripts/spike_gameplay_dump.py`) ; les phases 1 à 4 seront précisées
avec ses résultats.

**Origine** : @pj35, 2026-09-26 — « capitaliser sur notre capacité à repérer les fins de game et
exploiter les stats pour que le live coach étende ses capacités à de l'analyse de gameplay […]
des conseils pertinents à chaque fin de game, mais aussi une progression dans le temps. Des
erreurs (ou succès) récurrentes doivent être identifiées et analysées […] comme un vrai coach. »

**Effort** : ~6,5 jours sur quatre phases (§11), à redécouper après le spike.

---

## 1. Principe

Le produit sait déjà, pour chaque partie jouée depuis le Live Coach, ce qui était **attendu** :
la probabilité de victoire prédite en fin de draft (`predictions`, reliée au `game_id` par
SPEC-08) et le delta du duel de lane (base de matchups). Un site de stats juge une partie en
absolu. Ici, on la juge **par rapport à une référence choisie** : ta norme, un objectif, ou ce
que la draft laissait attendre.

Le moteur est **déterministe** (@pj35) : pour chaque métrique retenue pour le rôle, on compare la
valeur de la partie à la norme ou à l'objectif fixé en amont, et on fait ressortir **les plus
gros écarts**, en négatif comme en positif. Aucune prose générée : un narrateur LLM fera l'objet
d'un POC documenté (§10), pas d'une dépendance.

On juge des métriques que le joueur contrôle, jamais la victoire seule. Une défaite dans une
draft prédite à 38 % ne dit rien du jeu ; une lane perdue dans un duel favorable, si.

## 2. Arbitrages (@pj35, 2026-09-26)

| Sujet | Décision |
|---|---|
| Source des données | **A. LCU** (historique de matchs et timeline) d'abord. **C. Live Client Data API** (port 2999, pendant la partie) dans un second temps : elle ouvre d'autres features (coaching en jeu). **B. API Riot match-v5 écartée** : pas de clé API tant qu'on peut l'éviter. |
| Files | **SoloQ (420) et Flex (440)**. Les autres modes sont ignorés. |
| Métriques | **Par rôle**, avec une **grille de lecture** pour chacun, adossée à des données publiques (§5). |
| Moteur | Déterministe : écart à la norme ou à l'objectif, classé par ampleur (§6). |
| Restitution | **Console** pour l'instant. Les courbes de progression plaident pour **reprioriser la GUI légère** (TODO, feature candidate 5) dans les prochains sprints. |
| Narrateur LLM | Bonne idée, mais la consommation de tokens inquiète : **POC documenté** (§10), non planifié. |
| Suivi dans le temps | **Tout est stocké** après chaque partie : valeur brute, écarts `z_norm` et `z_objective`, références utilisées (§8). Le score Z est l'outil principal pour les forces, les faiblesses et les patterns (§7). |
| LP | **Suivis depuis le LCU**, par file : ils situent le niveau de la norme et alimenteront la courbe de LP de la future GUI. |

Conséquence de l'arbitrage A : le LCU ne sert que **les parties du joueur**, et son historique est
court. Chaque partie non capturée est perdue pour le suivi dans le temps. **La capture (phase 1)
doit donc démarrer avant que le cadre d'analyse soit arrêté**, en stockant le JSON brut : les
métriques retenues changeront pendant l'exploration, et le brut permet de tout recalculer.

## 3. Phase 0 — Spike

### 3.1 Déjà connu

- **LCU** (SPEC-08 §2.1, vérifié le 2026-09-05) : `…/current-summoner/matches` ne renvoie que le
  joueur courant ; `/lol-match-history/v1/games/{id}` renvoie les **10 participants**. Seuls
  `championId` et `teamId` en ont été relevés, pas les stats.
- **OneTricks** (`matchHistory` de la page déjà téléchargée par SPEC-15, vérifié le 2026-09-26 sur
  Jinx bot) : **100 parties** de one-tricks Master+, avec pour chacune K/D/A, `cs`, `lvl`,
  `gameDuration`, `teamKills`, `gameRoles.gd15` et `gameRoles.exp15` (écarts d'or et d'XP à
  15 min face à l'adversaire direct), `enemyLvl`, `win`, `timeline.orderedItems` (**sans
  horodatage**). Ni vision, ni dégâts. Aucune requête supplémentaire : la page est déjà lue à
  chaque draft.

### 3.2 Questions

1. Combien de parties l'historique LCU sert-il, et jusqu'à quelle date ?
2. Quelles stats `games/{id}` donne-t-il pour les 10 participants (CS, or, dégâts, vision,
   wards, objectifs) ? Le rôle de chacun y figure-t-il, et est-il fiable ?
3. `/lol-match-history/v1/game-timelines/{id}` répond-il ? Avec quel intervalle d'images, quels
   champs par joueur (or, XP, CS, **position**) et quels événements (kills avec position,
   achats, wards, bâtiments, monstres épiques) ?
4. La timeline d'une partie ancienne est-elle encore servie, ou purgée ?
5. Que contient `eog-stats-block` pendant l'écran de fin ? (écarté par SPEC-08 comme source du
   résultat, mais il pourrait porter des stats absentes ailleurs)
6. **LP** : le LCU expose-t-il la variation de LP d'une partie (le « +19 LP » de l'écran de fin),
   ou seulement le rang courant (`/lol-ranked/v1/current-ranked-stats`) ? Endpoints sondés :
   `current-ranked-stats`, `current-lp-change-notification`, `notifications`, et tout champ
   évoquant des LP dans `eog-stats-block`. La documentation communautaire est contradictoire
   sur ce point.

### 3.3 Mode opératoire

Sur le PC de jeu, juste après une partie de SoloQ ou de Flex, client ouvert :

```bash
python scripts/spike_gameplay_dump.py
```

Le script est en lecture seule. Il affiche un résumé et écrit les réponses brutes dans
`outputs/spike_gameplay/` (ignoré par git), **identités anonymisées** : ces fichiers pourront
devenir les fixtures des tests. Le lancer aussi **pendant l'écran de fin d'une partie classée,
puis une fois après**, pour les questions 5 et 6.

### 3.4 Résultats

*À compléter.*

## 4. Références : attendu, norme, objectif

Chaque métrique se lit contre trois références :

| Référence | Question | Source | Disponible |
|---|---|---|---|
| **Attendu** | La draft laissait-elle prévoir ça ? | `predictions.predicted_probability`, delta du duel de lane (base de matchups) | Dès la phase 3, pour les parties passées par le Live Coach |
| **Norme** | Est-ce normal **à ton niveau** ? | Les **9 autres joueurs de tes propres parties**, par rôle (dont l'adversaire direct pour ton rôle) | S'accumule avec la capture : ~50 parties donnent ~50 valeurs par rôle, à ton MMR, sans aucune source externe |
| **Objectif** | Où est le niveau visé ? | OneTricks `matchHistory` (100 parties Master+ de **ton champion**) pour les métriques qu'il publie ; sinon une valeur repère par rôle, sourcée (§5.2) ; ou un objectif fixé par le joueur | Dès la phase 3 |

La **norme** tirée des parties du joueur est l'idée centrale : c'est une donnée publique au sens
où chaque partie l'expose, elle est au bon niveau de jeu par construction, et elle évite à la
fois la clé API et un nouveau scraping. Son défaut : elle ne sera exploitable qu'après quelques
dizaines de parties, d'où le repli sur l'objectif.

### 4.1 Deux écarts standardisés

Norme et objectif fournissent chacun une moyenne **et un écart-type** : les 100 parties
OneTricks le permettent pour CS/min, morts, participation aux kills, `gd15` et `xpd15`. Chaque
métrique du joueur reçoit donc deux scores Z (@pj35, 2026-09-26) :

- **`z_norm`**, face à tes pairs. Outil principal des forces, faiblesses et patterns : une
  faiblesse est relative aux joueurs de ton niveau, et un écart qui persiste à mesure que tu
  montes est une vraie faiblesse. Il rend aussi une partie immédiatement lisible (« −2 sur les
  morts avant 14 min » plutôt que « 4 morts »).
- **`z_objective`**, face aux one-tricks Master+ de ton champion. Sa référence ne dépend pas de
  ton rang : c'est l'échelle stable du suivi dans le temps. Sans écart-type publié (valeur
  repère §5.2 ou objectif fixé par le joueur), l'écart est relatif et non standardisé.

### 4.2 Les LP situent la norme

La norme monte avec le rang : un `z_norm` stable pendant qu'on grimpe est un progrès. Les LP,
suivis depuis le LCU par file (§8), rendent cette lecture possible : `z_norm` stable et LP en
hausse, c'est un progrès ; `z_norm` en baisse à LP constants, c'est un recul. Les LP ne sont
qu'un indicateur approché du niveau de la norme, qui dépend du MMR caché : un dodge ou la perte
de LP par inactivité les font bouger sans partie jouée.

La norme est peut-être à séparer par file : la Flex mêle des niveaux plus variés que la SoloQ.
L'exploration (phase 2) tranchera.

## 5. Grille de lecture par rôle

### 5.1 Métriques

Normalisées à la minute ou prises à un instant fixe (10 et 14 min), pour neutraliser la durée
de partie. Les métriques « @10/@14 » dépendent de la timeline (question 3 du spike).

| Métrique | Top | Jungle | Mid | Bot | Support |
|---|:-:|:-:|:-:|:-:|:-:|
| CS @10 et @14, CS/min | ● | ● (camps) | ● | ●● | |
| Écart d'or et d'XP @14 face à l'adversaire direct | ●● | ● | ●● | ●● | ● |
| Morts avant 14 min, morts solo | ●● | ● | ● | ●● | ● |
| Morts / 10 min | ● | ● | ● | ● | ● |
| Participation aux kills | | ●● | ● | ● | ●● |
| Présence aux objectifs (dragons, Héraut, larves, Baron) | | ●● | ● | ● | ● |
| Dégâts / min, part des dégâts de l'équipe | ● | | ●● | ●● | |
| Dégâts aux structures | ●● | | | ● | |
| Vision / min, wards détruites, pinks achetées | | ● | | | ●● |
| Minute du premier item core | ● | ● | ● | ●● | |

●● métrique principale du rôle, ● secondaire. La pondération initiale est une hypothèse de
coaching à confronter à la phase 2 (exploration) : une métrique qui ne sépare pas les victoires
des défaites **pour ce joueur** perd son rang.

Le rôle de chaque participant vient du LCU s'il est fiable (spike, question 2), sinon de
`src/role_inference.py` (déjà utilisé en draft), avec Châtiment comme indice fort pour la jungle.

### 5.2 Valeurs repères publiques

Pour les métriques qu'OneTricks ne publie pas (vision, dégâts, objectifs), il faut une valeur
repère par rôle, avec sa source. Candidats à évaluer pendant le spike, **sans clé API** :
agrégats par rôle et par rang publiés par les sites de stats (League of Graphs, LoLalytics déjà
scrapé). Chaque valeur retenue va dans `config_constants.py`, avec sa source et sa date en
commentaire. Si aucune source n'est jugée fiable, la métrique n'a pas d'objectif et ne se lit
que contre la norme.

## 6. Moteur de constats (déterministe)

Pour chaque métrique `m` de la grille du rôle joué :

1. **Valeur** `v` de la partie, puis les deux références de §4.1, chacune avec sa moyenne `r`,
   son écart-type `s` et la taille de son échantillon `n`.
2. **Écarts orientés** `z = sens(m) × (v − r) / s` contre chaque référence, où `sens` vaut +1 si
   « plus » est mieux (CS), −1 sinon (morts). Un `z` positif est toujours une bonne nouvelle.
   Le classement utilise `z_norm` quand la norme compte au moins `COACHING_MIN_NORM_SAMPLE`
   valeurs, sinon `z_objective`. Les deux sont stockés dans tous les cas (§8).
3. **Pondération** par le rang de la métrique dans la grille du rôle.
4. **Sortie** : les `COACHING_TOP_NEGATIVE` plus gros écarts négatifs et les
   `COACHING_TOP_POSITIVE` plus gros écarts positifs, au-delà de `COACHING_MIN_ABS_Z`.

**Écart à l'attendu** (ligne de contexte, non classée au départ) : le duel de lane annoncé par
la draft, mis en regard de l'écart d'or à 14 min. La correspondance entre un delta de winrate
et un écart d'or n'est pas calibrée. Elle se lit qualitativement jusqu'à ce que la phase 2
fournisse des données pour la mesurer.

Toutes les constantes vont dans `config_constants.py` (`coaching_config`).

### 6.1 Sortie console (maquette)

```
[DATA] Fin de partie : Jinx bot vs Draven, défaite (31 min, SoloQ)
  Draft : 54 % prédit, duel défavorable (-2,1 pp)
[ALERTE] Morts avant 14 min : 4        (norme 1,6, objectif 1,2)   z -2,1
[ALERTE] CS @14 : 98                   (norme 118, objectif 131)   z -1,7
[OK]     Part des dégâts : 34 %        (norme 27 %)                z +1,4
[INFO] Axe de travail « Morts avant 14 min » : 3e partie sur 5 au-dessus de l'objectif
```

## 7. Suivi dans le temps (phase 4)

Tout se lit dans les tables de §8. Aucune donnée n'est recalculée depuis le LCU.

1. **Forces, faiblesses et patterns**, sur `z_norm`. Un constat négatif (ou positif) devient un
   **schéma** quand sa fréquence dans `game_findings`, sur les `COACHING_RECURRENCE_WINDOW`
   dernières parties, dépasse significativement son taux de base : même test binomial que
   SPEC-15 §3.2.1 (`math.comb`, stdlib), même seuil α en configuration. On lit aussi le profil
   moyen de `z_norm` par métrique, par rôle et par champion quand l'échantillon suffit : il
   révèle les points forts et faibles durables, au-delà d'une partie.
2. **Progression**, en croisant trois lectures :
   - **LP** (`rank_snapshots`), par file ;
   - **`z_objective`**, dont la référence ne bouge pas avec le rang ;
   - **`z_norm`**, interprété à la lumière des LP (§4.2).

   Chaque série est lue en moyenne glissante, avec un verdict « progrès », « recul » ou
   « stable » seulement quand l'écart dépasse le bruit. Un CUSUM est à évaluer. Aucun verdict
   sous `COACHING_MIN_TREND_SAMPLE` parties : l'ignorance reste visible (esprit SPEC-09). La
   valeur brute face à l'objectif complète la lecture (« CS à 14 min : 98 → 120 »).
3. **Axes de travail** : **un ou deux actifs** à la fois (`coaching_goals`). Soit le joueur les
   fixe, soit ils sont proposés à partir du schéma négatif le plus fort. Ensuite :
   - **rappel en draft**, une ligne à l'écran de fin de draft ;
   - **verdict en fin de partie** sur l'axe, historisé dans `goal_verdicts` ;
   - l'axe est **acquis** quand il tient `COACHING_GOAL_HOLD` parties sur les
     `COACHING_GOAL_WINDOW` dernières, et le suivant est proposé.
4. **Bilan périodique**, toutes les `COACHING_REVIEW_EVERY` parties et sur demande (commande du
   Live Coach, entrée de menu) :
   - variation de LP ;
   - les plus nets progrès et reculs ;
   - schémas actifs ;
   - état des axes de travail et prochain axe proposé.

   En console d'abord, en GUI quand elle existera : courbe de LP, séries de Z par métrique.

## 8. Stockage et modules

**Migration Alembic** (numéro de révision au moment de l'écrire). **Tout est stocké**, en fin de
partie (@pj35, 2026-09-26) :

| Table | Contenu |
|---|---|
| `game_records` | `game_id` (PK), `queue_id`, `game_creation_utc`, `duration_s`, `player_participant_id`, `raw_game` (JSON), `raw_timeline` (JSON, NULL si indisponible), `captured_utc`. Le brut est la **source de vérité**. |
| `game_metrics` | Format long : une ligne par (`game_id`, `participant_id`, `metric`), avec `role`, `champion_id`, `value`. **Sur les lignes du joueur seulement** : `norm_mean`, `norm_sd`, `norm_n`, `z_norm`, `objective_value`, `objective_sd`, `objective_source`, `z_objective`, `grid_version`. Les lignes des 9 autres participants construisent la norme. |
| `rank_snapshots` | `captured_utc`, `queue` (SoloQ ou Flex), `tier`, `division`, `lp`, `wins`, `losses`, `lp_delta` (si le client l'expose, spike question 6), `game_id` (NULL pour une photo sans partie, prise au démarrage de l'app). |
| `game_findings` | Les constats affichés en fin de partie : `game_id`, `metric`, `polarity`, `z`, `reference`, `rank`. |
| `coaching_goals` | Axes de travail : métrique, cible, dates de début et d'acquisition, statut. |
| `goal_verdicts` | Verdict de chaque axe actif, partie par partie. |

Pourquoi un format long plutôt qu'une colonne par métrique : les métriques vont changer pendant
l'exploration, et un format large demanderait une migration à chaque ajout.

Les écarts sont **figés au moment de la partie**, contre la norme d'alors : un rapport passé
reste reproductible, et le suivi porte sur ce qui a réellement été dit au joueur. Tout reste
**recalculable** depuis `game_records` : un changement de grille ou de métriques incrémente
`grid_version` (même logique que `MODEL_VERSION`), et un script recalcule `game_metrics` et
`game_findings` sans appel LCU.

**Variation de LP.** Si le client l'expose (spike, question 6), on la lit pendant l'écran de
fin. Sinon, elle se déduit de deux photos consécutives de la même file. Dans les deux cas, les
parties récupérées au rattrapage n'ont pas de LP : le LCU ne sert que le rang courant. Une
variation entre deux photos séparées par plusieurs parties reste cumulée, sans être répartie.
Le rang se convertit en une échelle continue (tier × 400 + division × 100 + LP, Master+ sans
division) pour les courbes.

**Paquet `src/coaching/`** (limite de 500 lignes par fichier) :

| Module | Rôle |
|---|---|
| `capture.py` | Capture en fin de partie (déclencheur gameflow de SPEC-08) et **rattrapage au démarrage** sur la profondeur de l'historique. Filtre SoloQ/Flex. Best-effort, comme `outcome_tracker.py`. |
| `metrics.py` | Brut → `game_metrics`, fonctions pures, testées sur les fixtures du spike |
| `grid.py` | Grille par rôle et références (norme, objectif, attendu) |
| `findings.py` | Moteur de constats (§6) |
| `report.py` | Sortie console |
| `ranked.py` | Photos de classement, variation de LP, échelle continue |
| `progression.py` | Récurrence, tendances, axes de travail, bilan (phase 4) |

`src/lcu_client.py` est à 500 lignes : les nouvelles lectures LCU vont dans
`src/lcu_match_history.py` (mixin existant).

## 9. Phase C, plus tard : Live Client Data API

`https://127.0.0.1:2999/liveclientdata/allgamedata`, pendant la partie : événements horodatés,
scores, items du joueur. Hors de cette spec. Elle ouvrira le coaching **en jeu** (rappel de
l'axe de travail à la mort, timers d'objectifs), et la capture d'événements que la timeline LCU
n'aurait pas. À cadrer dans sa propre spec une fois les phases 1 à 3 en place.

## 10. POC narrateur LLM (documenté, non planifié)

Le moteur déterministe produit des constats structurés (métrique, valeur, référence, écart). Le
narrateur n'en change aucun : il les **met en forme** comme le ferait un coach, avec le
contexte de la draft et de l'axe de travail.

- **Entrée** : le JSON des constats, de l'ordre de 1 à 2 k tokens. **Sortie** : ~300 tokens.
  **Un appel par partie**, et aucun pendant la draft.
- **À mesurer au POC** : le coût réel par partie et par mois (avec prompt caching sur la grille
  et les consignes, qui ne changent pas), la valeur ajoutée par rapport au rapport
  déterministe, et le comportement hors ligne (repli sur le rapport déterministe, toujours).
- **Garde-fou** : désactivé par défaut (`COACHING_LLM_NARRATOR = False`), clé dans `.env`.

## 11. Découpage proposé

| # | Tâche | Phase | Pts | Dépend de |
|---|---|---|---|---|
| 27 | Script du spike `scripts/spike_gameplay_dump.py` | 0 | 1 | — |
| 28 | Spike sur le PC de jeu, puis résultats consignés en §3.4 et fixtures anonymisées | 0 | 1 | 27 |
| 29 | Migration des tables de §8, repository et délégué `db.py` | 1 | 2 | 28 |
| 30 | `capture.py` : capture en fin de partie, rattrapage au démarrage, filtre de files | 1 | 3 | 29 |
| 30b | `ranked.py` : photos de classement (démarrage, fin de partie), variation de LP selon le résultat du spike | 1 | 2 | 29 |
| 31 | `metrics.py` : métriques de la grille pour les 10 participants, rôles inférés | 2 | 3 | 28 |
| 32 | Script d'exploration : distributions par rôle et lien avec la victoire, sur les parties capturées (~30) | 2 | 2 | 30, 31 |
| 33 | `grid.py` : grille par rôle, norme, objectif OneTricks, valeurs repères sourcées | 3 | 3 | 32 |
| 34 | `findings.py` : `z_norm` et `z_objective` figés dans `game_metrics`, classement, `game_findings` | 3 | 3 | 33 |
| 35 | `report.py` : rapport console en fin de partie, ligne d'attendu de la draft | 3 | 2 | 34 |
| 36 | `progression.py` : schémas sur `z_norm`, progression croisant LP et Z, script de recalcul par `grid_version` | 4 | 3 | 34, 30b |
| 37 | Axes de travail : `coaching_goals`, rappel en draft, verdict, acquisition | 4 | 5 | 36 |
| 38 | Bilan périodique (commande du Live Coach, menu, toutes les N parties) | 4 | 3 | 36 |

**Ordre** : 29, 30 et 30b dès le spike rendu, pour que la capture tourne pendant qu'on explore. La
tâche 32 n'a de sens qu'après ~30 parties capturées, soit environ deux semaines de jeu.

## 12. Critères d'acceptation (à préciser après le spike)

1. Une partie SoloQ ou Flex terminée est capturée une seule fois, même quand l'app est fermée
   pendant la partie (rattrapage au démarrage). Une ARAM ou une normale ne l'est pas.
2. Aucune erreur de capture, de LCU ou de calcul n'interrompt la boucle du Live Coach.
3. `game_metrics` et `game_findings` se recalculent intégralement depuis `game_records`, sans
   appel LCU. Un changement de `grid_version` déclenche ce recalcul.
4. Le rapport de fin de partie liste au plus `COACHING_TOP_NEGATIVE` + `COACHING_TOP_POSITIVE`
   constats, triés par écart pondéré. Il affiche sa référence (norme, objectif) et n'affirme rien
   sous le seuil d'échantillon.
5. Tests hermétiques sur les fixtures anonymisées du spike, sans client réel.
6. Les lignes du joueur portent la valeur brute, les deux références (moyenne, écart-type,
   taille) et les deux scores Z. Un Z calculé sous le seuil d'échantillon est stocké mais
   jamais affiché comme un verdict.
7. Une photo de classement est prise au démarrage et après chaque partie classée capturée en
   direct. Une partie récupérée au rattrapage n'invente aucune variation de LP.

## 13. Hors périmètre

- API Riot match-v5 et toute clé API Riot (arbitrage du 2026-09-26).
- Coaching pendant la partie (phase C, §9).
- Cartes de chaleur et analyse de positions, même si la timeline les permettait : à rouvrir
  après la phase 3.
- GUI : décision de repriorisation séparée (TODO, feature candidate 5).
