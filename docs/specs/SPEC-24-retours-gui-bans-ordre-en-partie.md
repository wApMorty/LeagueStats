# SPEC-24 — Retours sur le client : bans, ordre de pick et swaps, écran « En partie »

**Statut** : 🟡 Rédigée le 2026-10-06 ; arbitrages de §2 validés par @pj35 le 2026-10-06, sauf le cadre des swaps (à valider après le relevé de la tâche 96).

**Origine** : @pj35, 2026-10-06 — « fix la sélection de ban qui ne fonctionne pas » ; « afficher le pick
order et proposer des swap order ou swap role » ; « une section in-game : infos de build, analyse de game
avec tous les matchups comme dans le live coach actuel, évolution du win chance au cours de la game ».
Symptôme du ban précisé le même jour : **le ban visé n'arrive pas dans le client LoL**. Contenu du build
choisi le même jour : plan d'objets, suivi des achats, ordre des compétences.

**Effort** : ~8 jours, 16 tâches (96 à 111, 61 pts), trois lots utilisables seuls (§5).

---

## 1. Constat

Mesuré le 2026-10-06, sur le code et sur le client LoL ouvert de @pj35 (lectures `GET /help` seulement,
hors champ select : aucune session de draft n'a pu être lue).

**Bans.**

- Le chemin d'écriture des bans n'a **jamais vu une vraie phase de bans** : `tests/fixtures/lcu_forms/session_ban.json`
  et `session_pick.json` sont « construites d'après les formes connues » (TODO, tâche 86 : « reste à relever en
  champ select »). Les tests de la tâche 74 passent contre un faux LCU qui répond ce que le code attend.
- Chemin du client : `draft.js:309-317` (`aimBan` → `POST /draft/action/hover_ban`), `draft.js:339-344`
  (`confirmBan` → `POST /draft/action/ban`), `draft_actions.py:47-72` (`run` : action du joueur local en cours,
  liste `bannable-champion-ids`, `PATCH …/session/actions/{id}` avec `type: "ban"`).
- **Causes possibles, non reproduites** (lecture de code et du schéma LCU, à départager par le relevé) :
  1. Le schéma de session du client de @pj35 porte `disallowBanningTeammateHoveredChampions` (type
     `ChampSelectSession`, `/help`) ; sa valeur en file classée n'est pas lue. Si elle est vraie, le client LoL
     refuse un ban que `draft_actions.py` accepte, ou que `bannable-champion-ids` ne filtre pas.
  2. `current_action` (`draft_actions.py:33-44`) exige `isInProgress` ; la valeur réelle sur mon action de ban
     (planification, bans simultanés ou alternés) n'est pas relevée.
  3. `draft.js:186-187` présélectionne `state.bans[0]` **sans envoyer de survol**, et `aimBan` (`:311`) sort quand
     `ctx.banSel === id` : cliquer la première carte n'écrit rien dans le client LoL. Ne suffit pas à expliquer
     un ban final qui n'arrive pas (`confirmBan` envoie le ban), mais explique « pas de survol ».
  4. **Chemin console, même symptôme** (`user_prefs.json` : `auto_ban_hover: true`) : `LCUClient.get_current_player_action_id`
     (`lcu_client.py:364-389`) ne cherche que `type in ["pick", "hover"]` ; en phase de bans, le survol
     automatique écrit donc le champion à bannir **sur mon action de pick** (`type: "pick"`). De plus
     `HoverAutomation.auto_hover_champion` ne renvoie rien, si bien que `handle_auto_ban_hover`
     (`ban_advice.py:171`) imprime « Échec du survol » à chaque fois. Lu dans le code, non observé en partie.
- Sortie de ce constat : on ne corrige pas sur hypothèse ; le relevé réel est la première tâche (96).

**Acteur courant (bug trouvé en lisant, vérifié par un test jetable).** `DraftStateParser` fixe
`current_actor` puis sort avec `if state.current_actor:` (`state_parser.py:~162-170`) : la cellule **0 est
fausse**, la boucle continue et écrase l'acteur par celui d'une action ultérieure. Session minimale, cellule 0
seule en cours : `current_actor == 5`, et `phases.is_player_turn` renvoie `False` pour la cellule 0
(`phases.py:24-26`, `not state.local_player_cell_id`). Conséquence visible : sur le premier pick d'une draft, le
Live Coach ne voit pas mon tour, et un « tour en cours » affiché d'après `acting_cell` désignerait un autre
joueur. Les phases de bans simultanés ont le même défaut (`current_actor` = première action non terminée).

**Ordre de pick et swaps.**

- L'écran de draft ne montre **aucun ordre de pick** : `SnapshotPlayer` (`src/draft/snapshot.py`) n'a ni rang
  ni swap ; le pentacle range les alliés par rôle (`draft_view.py:160-204`). L'ordre existe pourtant dans la
  session : `DraftStateParser` lit déjà « l'ordre des `action_set` est celui de la draft » pour `remaining_picks`
  (SPEC-12), mais ne garde que les tours restants. L'action et le joueur du LCU portent aussi `pickTurn`
  (`/help`, types `TeamBuilderDirect-ChampSelectAction` et `…PlayerSelection`) : sa sémantique n'est pas relevée.
- Le LCU de @pj35 expose les swaps (`/help`, 2026-10-06) : `GET …/session/pick-order-swaps` et
  `…/position-swaps`, `POST …/{id}/request|accept|decline|cancel` pour chacun, `…/ongoing-*-swap/{id}/clear`,
  contrat `{id, cellId, state}` ; la session porte `pickOrderSwaps` et `positionSwaps`. Les chemins exacts (forme
  en tirets, sens de `id`), les valeurs de `state` et les files qui autorisent chaque swap ne sont **pas
  relevés**. Les swaps de champion (`champion-swaps`, `bench-swap`) existent aussi : hors périmètre (§7).
- Aucun swap n'est dans la liste blanche (`lcu_proxy.py`, `WRITES`).

**En partie.**

- SPEC-21 §7 écartait explicitement « Overlay et écran en partie ». L'overlay de SPEC-20
  (`src/winprob/overlay.py`, `tkinter`, processus à part) ne montre qu'une ligne de texte.
- Déjà disponible : `winprob/live.py` (`fetch()`, `state_from_live()`, vérifié au spike du 2026-10-02 sur 27 min :
  `team`, `level`, `scores`, `isDead`, `respawnTimer`, `position` pour les 10 joueurs, événements d'objectifs, pas
  d'or adverse) ; `overlay.Tracker` (win chance du point de vue du joueur, variation sur une minute) ;
  `charts.line_chart` (tracé animable, repères) ; `winprob.report.curve_points` (courbe d'une partie finie).
- **L'analyse de fin de draft n'est pas une donnée** : `FinalDraftAnalyzer.analyze` (`final_analysis.py:206-290`)
  calcule et imprime en un geste, comme `DraftRecommender` avant SPEC-21 tâche 72. Le snapshot de draft est
  **vidé en quittant le champ select** (`lifecycle.py`, `recommender.clear()`) : l'écran de partie ne peut pas
  le relire sur le bus.
- Le plan de build est déjà calculé au lock-in (`LoadoutImporter.state()` : blocs d'objets `Départ`, `Autres
  départs`, `Core`, `Bottes`, `Composants`, `Situationnels`), mais `state()` n'expose pas les substitutions du
  duel (imprimées en console seulement), et `loadout._trim()` jette tout de la page OneTricks hors `firstItemStats`
  (aucun ordre de compétences conservé ; si la page le publie, **à vérifier**).
- Non vérifié : `allPlayers[].items` / `championName` / `position` et `activePlayer.currentGold` / `abilities`
  de la Live Client API (champs documentés par Riot, absents des fixtures `tests/fixtures/spike_live/`, qui sont
  réduites).

## 2. Objectif et arbitrages

**Objectif** : un ban qui arrive dans le client LoL ; l'ordre de pick lisible d'un coup d'œil, avec les swaps
d'ordre et de rôle demandables, acceptables et conseillés chiffres à l'appui ; un écran « En partie » qui garde
l'analyse de la draft, le plan de build et la courbe de win chance pendant la partie.

| Sujet | Décision |
|---|---|
| Découpage | **Défaut proposé** : une spec, trois lots utilisables seuls (bans, ordre et swaps, en partie). Le lot 1 se livre en premier : c'est un bug. |
| Cause du ban | **Validé (@pj35, 2026-10-06)** : le symptôme est « rien n'arrive dans le client LoL ». **Non établie** : relevé d'une vraie draft d'abord (tâche 96), correctif ensuite (tâche 97), jamais sur hypothèse. |
| Périmètre du correctif de ban | **Validé (@pj35, 2026-10-06)** : la tâche 97 corrige aussi `LCUClient.hover_champion` (chemin console, hypothèse 4) si le relevé la confirme. Sans cela le Live Coach continue d'écrire le ban sur l'action de pick quand `auto_ban_hover` est vrai. |
| `current_actor` de la cellule 0 | **Défaut proposé** : corrigé en tâche 98, test de régression (§1). Préalable de l'ordre de pick, qui s'appuie sur « qui joue maintenant ». |
| Affichage de l'ordre de pick | **Validé (@pj35, 2026-10-06)** : numéro 1 à 10 sur chaque sceau, présent dès la phase de bans, anneau du joueur en cours (§3, A). Frise des dix tours écartée. |
| Swaps | **Validé (@pj35, 2026-10-06)** : boutons (demander, accepter, refuser, annuler) **et** conseil chiffré par le modèle. Heuristique sans métrique écartée (précédent : items et matchups indirects, 2026-09-25). |
| Conseil de swap de rôle | **Défaut proposé** : gain = victoire prédite après l'échange moins avant, en points, par `GameEvaluator.win_probability` ; seulement si les deux joueurs ont un champion (le mien survolé ou verrouillé, l'autre verrouillé). Seuil `SWAP_MIN_GAIN_PTS` (§4.6). |
| Conseil de swap d'ordre | **Défaut proposé, livraison conditionnelle** : recherche minimax relancée à budget réduit avec les tours permutés, comparée à l'ordre actuel **au même budget**. Si le bench (tâche 103) ne dégage pas un signal au-dessus du bruit, la tâche est close sans conseil d'ordre (les boutons restent) et la spec le consigne. |
| Cadre des swaps | **À valider** : files concernées et sens de `id` connus après le relevé (tâche 96) ; le client n'offre un bouton que pour un swap que la session liste. |
| Écran « En partie » | **Validé par la demande (@pj35, 2026-10-06)** : section du client. **Rouvre SPEC-21 §7** (« Overlay et écran en partie »), à acter dans la tâche 111. L'overlay `tkinter` de SPEC-20 reste tel quel. |
| Source en jeu | **Défaut proposé** : Live Client API (port 2999), lue 1 fois par seconde par un fil du **serveur du client**, pas par la boucle du Live Coach (§3, C). Modèle de win chance de SPEC-20, identique à l'overlay. |
| Courbe de win chance | **Défaut proposé** : série en mémoire, un point toutes les `INGAME_SAMPLE_S`, depuis l'ouverture du client ; **pas de persistance** (la page de la partie, `/parties/{id}`, redessine la courbe complète depuis la timeline LCU après la partie). Redémarrer le client en pleine partie perd le début de la courbe, et l'écran le dit. |
| Analyse de la draft | **Validé (@pj35, 2026-10-06)** : on garde le résultat calculé à la fin de la draft (`FinalAnalysis`, tâche 106), publié sur son sujet du bus et conservé jusqu'à la draft suivante. Si le Live Coach n'a pas vu la draft, l'écran dit « analyse indisponible » (ignorance visible) ; alternative écartée pour l'instant : recalculer depuis `allPlayers[].championName/position`. |
| Contenu « build » | **Validé (@pj35, 2026-10-06)** : plan d'objets (avec les substitutions du duel et leur raison), suivi des achats (objets déjà pris cochés, prochain objet du plan, or disponible), ordre des compétences. Runes et sorts : non retenus (déjà dans la colonne loadout de la draft). L'ordre des compétences n'est livré que si OneTricks le publie (spike, tâche 105) ; sinon la ligne disparaît et le CHANGELOG le dit. |
| Ouverture de l'écran | **Validé (@pj35, 2026-10-06)** : entrée « En partie » dans la navigation et pastille dans la barre de titre pendant une partie, **sans bascule automatique** de page (@pj35 peut être sur un autre onglet du client). |
| Écriture en partie | **Défaut proposé** : aucune. L'écran « En partie » est en lecture seule ; les seules écritures nouvelles de la spec sont les swaps de draft et le correctif de ban. |
| Design | Les écrans sont extrapolés du système « Alchimie » (SPEC-21 §2, « Écrans sans maquette », validé le 2026-10-05) ; si une direction manque, Claude s'arrête et le signale. |

## 3. Approches considérées

**Affichage de l'ordre de pick**

- **A. Numéro sur chaque sceau — retenue.** Réutilise la macro `member` et les positions du pentacle, aucun
  changement de mise en page ; l'ordre est global (1 à 10), donc l'entrelacement des deux camps se lit sur les
  numéros ; l'anneau du joueur en cours montre où en est la draft.
- B. Frise horizontale des dix tours dans l'en-tête : montre mieux l'entrelacement, mais l'en-tête porte déjà
  bans, titre et chrono ; coût de mise en page pour une information que A donne.
- C. Numéro dans la légende seulement : trop discret pour un repère de coordination.

**Conseil de swap**

- **A. Gain du modèle — retenue.** Rôle : deux évaluations de `GameEvaluator.win_probability` (quelques ms).
  Ordre : la recherche du Live Coach avec les tours permutés, à budget réduit, mesurée.
- B. Règles écrites à la main (« picke tard si ton champion dépend du counter ») : aucune métrique, déjà rejeté.

**Où lire la Live Client API**

- **A. Fil du serveur du client — retenue.** Aucun changement de la boucle du Live Coach ; le fil ne tourne que
  pendant une partie (phase gameflow `InProgress`), best-effort.
- B. Dans la boucle du Live Coach : une lecture lente (timeout de 2 s) ralentirait la draft suivante ; la règle
  « aucune exception ne doit interrompre le monitoring » est plus facile à tenir hors de la boucle.
- C. Le processus d'overlay `tkinter` alimente le client : deux processus pour une donnée, écarté.

## 4. Détail

### 4.1 Relevé en champ select réel (tâche 96)

`scripts/dump_lcu_draft_forms.py` gagne `--watch` : toutes les 2 s, il écrit chaque **nouvelle forme** de
`/lol-champ-select/v1/session`, `bannable-champion-ids`, `pickable-champion-ids`, et les listes de swaps, avec
l'heure. Lectures `GET` seulement, aucun test d'interface. @pj35 lance le script pendant une draft classée
(bans, position swaps) puis une draft normale (pick-order swaps), **en faisant** : survoler un ban, le valider,
demander un swap, en recevoir un. À lire dans le relevé : valeurs de `disallowBanningTeammateHoveredChampions`,
`hasSimultaneousBans`, `isInProgress` de mon action de ban à chaque phase, forme de l'action de ban après survol
puis verrouillage, `pickTurn` (joueur et action), `pickOrderSwaps` / `positionSwaps` (entrées, `state`, sens de
`id`), files qui exposent chaque swap. Les fixtures `session_ban.json` et `session_pick.json` sont **remplacées**
par des extraits réels anonymisés (`gameName`, `tagLine`, `puuid`, `summonerId`, `obfuscated*` retirés), plus
`session_swaps.json`. Les endpoints de swap sont notés en SPEC-21 §10 une fois confirmés.

### 4.2 Ban (tâche 97)

1. Un test rejoue sur la fixture réelle la séquence `hover_ban` puis `ban` de `draft_actions.run` et vérifie
   l'endpoint, le corps et le type contre ce que le relevé montre que le client LoL fait / accepte
   (`tests/regression/test_regression_client_ban_lcu.py`, rouge avant le fix, docstring en 4 points).
2. Correctif au niveau de la cause relevée (une seule), pas un symptôme par appelant : avant de toucher
   `current_action`, `LCUClient.get_current_player_action_id` ou `hover_champion`, lister leurs appelants
   (`grep`). Si l'hypothèse 4 est confirmée : `hover_champion(name, action_type="pick")` choisit l'action du
   **type demandé** et en cours, `auto_hover_champion` renvoie un booléen, `handle_auto_ban_hover` passe `ban` et
   lit le retour ; sortie console inchangée hors le message d'échec devenu exact.
3. Hypothèse 3 : plus de présélection silencieuse. La première carte reste une suggestion visible ; le bouton
   « Bannir » est actif seulement quand une cible a été **envoyée** au client (survol de ban) ou cliquée.
4. Les cartes de ban et les tuiles du grimoire excluent les champions absents de `bannable-champion-ids`
   (si le relevé montre qu'il filtre les survols d'alliés, c'est ce qui évite la visée d'un ban refusé).
5. Un refus du client LoL (`result is None`) s'affiche avec la raison connue, pas « refusé » seul.

### 4.3 Acteur courant (tâche 98)

`DraftStateParser.parse` et `phases.py` : tests sur `is not None`, jamais sur la valeur (0 est une cellule).
`DraftState` gagne `acting_cells: Set[int]` lu sur `isInProgress` (plusieurs acteurs en bans simultanés) ;
`current_actor` garde sa sémantique (le premier non terminé) corrigée. Avant de modifier, `grep current_actor` et
`local_player_cell_id` : chaque appelant est relu (`phases.py`, `snapshot.py`, `automation.py`, `draft_view.py`).
Test de régression `tests/regression/test_regression_current_actor_cell_zero.py` : la session minimale du §1.

### 4.4 Snapshot : ordre et swaps (tâche 99)

- `DraftState.pick_order: Dict[int, int]` (`cellId` → rang 1 à 10) : rang de l'action `pick` de chaque cellule
  dans l'ordre des `action_set` (la convention de `remaining_picks`). `pickTurn` n'est **pas** utilisé sans preuve.
- `DraftState.swaps: List[Swap]` ; `Swap(kind: "pick_order" | "position", id: int, cell_id: int, state: str)`,
  lu dans `pickOrderSwaps` et `positionSwaps`.
- `SnapshotPlayer.pick_order: Optional[int]` ; `DraftSnapshot.swaps: List[SnapshotSwap]` et
  `swap_advice: List[SnapshotSwapAdvice]` (§4.7). `my_turn` et `is_acting` lisent les corrections de la tâche 98.
- Sortie console identique (test d'identité sur un jeu fixe, comme SPEC-21 tâche 72).

### 4.5 Ordre de pick à l'écran (tâche 100)

`draft_view._member` expose `order` ; la macro `member` (`draft_stage.html`) ajoute `<span class="d-order">`
(numéro dans un médaillon, couleur de camp) ; `style.css` : `.d-order`, anneau `.d-acting` sur le joueur en cours,
visibles dès la phase de bans. La légende dit « n° 4 » en infobulle. L'empreinte `sig` de `member` inclut `order`.
Un joueur sans rang (LCU sans actions : normal blind) n'affiche rien.

### 4.6 Swaps : actions et conseils (tâches 101 à 103)

`src/client/draft_swaps.py`, sur le modèle de `draft_actions.py` :

```python
KINDS = {"pick_order": "pick-order-swaps", "position": "position-swaps"}  # forme confirmée en 96
ACTIONS = ("request", "accept", "decline", "cancel")

def run(proxy: LcuProxy, kind: str, action: str, cell_id: int) -> Dict[str, Any]:
    """Écrit le swap ; lève Refusal (409) si la session ne le liste pas dans l'état attendu."""
```

L'`id` n'est **jamais** donné par le front : le serveur le lit dans la session pour la cellule nommée.
`request` exige une entrée disponible pour cette cellule, `accept` / `decline` une entrée reçue, `cancel` une
entrée envoyée (noms d'états relevés en 96). `WRITES` gagne un motif unique couvrant les huit chemins
`…/session/(pick-order-swaps|position-swaps)/\d+/(request|accept|decline|cancel)`. Route
`POST /draft/swap/{kind}/{action}?cell_id=` derrière le jeton et le contrôle `Origin`.

`src/draft/swap_advice.py` :

```python
def role_swaps(evaluator, allies: Sequence[Placed], enemies: Sequence[Placed], me: int, swaps: Sequence[Swap]) -> List[SwapAdvice]
def order_swaps(search, allies, enemies, pool, turns: Sequence[PickTurn], me: int, swaps: Sequence[Swap], ...) -> List[SwapAdvice]
# SwapAdvice(kind, cell_id, champion, gain_pts, reason)
```

Rôle : `win_probability(allies avec les deux lanes échangées, enemies) − win_probability(allies, enemies)`, en
points ; l'adversaire direct de chaque lane est celui de `inferred_roles`. Ordre : `search.rank(...,
remaining_turns=tours permutés, budget_seconds=SWAP_SEARCH_BUDGET_S)` comparé à `rank` de l'ordre actuel **au
même budget** (la profondeur atteinte dépend du budget). Calculé dans `DraftRecommender.provide`, **best-effort**
(`try/except`, rien n'interrompt la boucle), seulement quand la session liste un swap ouvert, et recalculé quand
les picks, les lanes ou les swaps changent (cache sur cette clé). Un conseil n'est publié qu'au-dessus de
`SWAP_MIN_GAIN_PTS`.

Constantes (`draft_config`, `src/config_constants.py`) :

| Constante | Valeur de départ | Origine |
|---|---|---|
| `SWAP_MIN_GAIN_PTS` | 1,0 | ordre de grandeur d'un palier de DUEL (SPEC-14) ; **calibrée au bench** (tâche 103) |
| `SWAP_SEARCH_BUDGET_S` | 0,5 | un quart du budget de pick (2 s), par candidat ; au plus 4 candidats |

`scripts/bench_swap_advice.py` (copie temporaire de la base, comme `bench_search.py`) : rejoue des drafts
fixes, imprime pour chaque candidat le gain d'ordre à budget réduit et sa stabilité d'un budget à l'autre
(0,5 s contre 2 s). Critère de livraison de l'ordre : le signe du gain est identique à 2 s sur au moins 80 % des
cas au-dessus du seuil.

### 4.7 Carte « Échanges » (tâche 104)

Sur la légende d'un coéquipier dont la session liste un swap : icône ⇄ (ordre) et ⇄ de rôle, avec le gain du
coach (« +1,2 pts ») ; un clic ouvre une popover « Demander l'échange » (appel `/draft/swap/...`). Une
demande **reçue** apparaît en bandeau dans `#d-overlays` (qui, quel swap, « Accepter » / « Refuser »), et une
demande **envoyée** affiche « Annuler ». Refus 409 en toast, comme les autres actions. Fragment
`partials/draft_swaps.html`, synchronisé par clé et empreinte comme le reste de l'écran.

### 4.8 Analyse de fin de draft, structurée (tâche 106)

`final_analysis.py` : `build_final_analysis(monitor, ally_picks, enemy_picks, ally_lanes) -> FinalAnalysis`
(données seules : lignes du face-à-face dans l'ordre de `face_offs`, matchup / synergie / total de chaque côté en
points, duel, probabilité de victoire, écart et évaluation) ; `analyze` imprime **à partir** de cette structure
(test d'identité de la sortie console sur un jeu fixe) et la publie sur le bus (sujet `game`). La charge utile
embarque aussi le loadout de `LoadoutImporter.state()` au moment de la fin de draft, **étendu** de ses
substitutions (catégorie, ancien, nouveau, parts, raison) et du nom des objets. Le bus la garde
(`latest("game")`) jusqu'à `reset_for_next_game`, qui publie `None`.

### 4.9 Écran « En partie » (tâches 105 à 110)

- **`src/client/ingame.py`** : `LiveGame(bus, get_phase, fetch=live.fetch, model=…)`, un fil daemon démarré avec
  le serveur. Hors partie (phase gameflow ≠ `InProgress`), il dort `INGAME_IDLE_POLL_S` et publie `{"state":
  "idle"}` une fois. En partie, il lit `live.fetch()` toutes les `INGAME_POLL_S`, calcule la win chance par
  `overlay.Tracker.update` (même fonction que l'overlay : même état, même résultat), ajoute un point à la série
  toutes les `INGAME_SAMPLE_S` (bornée à `INGAME_MAX_POINTS`), et publie `{"state": "live", game_time, p, delta,
  series, objectives, me}`. Fin de partie : `INGAME_GRACE_POLLS` lectures vides d'affilée → `{"state": "ended"}`,
  série gardée jusqu'à la partie suivante (un `gameTime` qui recule la remet à zéro). Aucune exception ne sort
  du fil (`try/except` large, journalisé en `[INFO]`). Sans modèle (`train.model_path()` absent) : `p` est
  `None` et l'écran dit comment l'entraîner (`python -m src.winprob.retrain --force`).
- **Routes** : `GET /en-partie`, `GET /en-partie/stage` (fragment, comme `/draft/stage`) ; aucune route `POST`.
  Entrée de navigation « En partie », pastille dans la barre de titre pendant `state == "live"`. SSE sur le sujet
  `ingame`, consommé par `ingame.js` (`sse.js` partagé).
- **Cadre et face-à-face (108)** : le tableau de SPEC-14 (une ligne par lane : allié, mat / syn / total, DUEL, ennemi)
  tel que `FinalAnalysis` le porte, la probabilité de la draft et son évaluation. Sans `FinalAnalysis`, l'état
  « analyse indisponible : le Live Coach n'a pas vu la draft de cette partie ».
- **Courbe (109)** : `charts.line_chart` sur la série, axe en minutes, bande des 50 %, repères d'objectifs
  (dragon, Héraut, Nashor, tour, inhibiteur) tirés des événements Live Client, dernier point lumineux ; moins de
  deux points : un message, pas de courbe. Affichée avec la variation sur la dernière minute (`delta`).
  Le point de départ de la draft (modèle de draft) **n'est pas** tracé sur la même courbe : ce n'est pas le même
  modèle, il reste dans l'en-tête de l'analyse.
- **Build (110)** : plan = blocs du loadout de `FinalAnalysis` avec leurs substitutions ; suivi des achats = objets de
  `allPlayers[moi].items` cochés dans le plan, prochain objet du plan non acheté, or de `activePlayer.currentGold`
  face à son coût (Data Dragon, `assets`) ; ordre des compétences si la page OneTricks le publie (la tâche 105
  tranche, `loadout._trim` en conserve alors la clé, rien de plus). Moi = joueur d'`activePlayer`, comme
  `overlay.Tracker`. Objets absents de l'API : le suivi dit « achats indisponibles ».
- **Constantes** (`client_config`, `src/config_client.py`) : `INGAME_POLL_S = 1.0`, `INGAME_IDLE_POLL_S = 5.0`,
  `INGAME_SAMPLE_S = 5.0` (le pas du spike de SPEC-20), `INGAME_MAX_POINTS = 720` (une heure), `INGAME_GRACE_POLLS = 10`
  (valeurs de `OVERLAY_POLL_S` et `OVERLAY_GRACE_POLLS` de SPEC-20).

### 4.10 Tests

Hermétiques (fixtures de `tests/conftest.py`, faux LCU, `tests/fixtures/`) : aucun test n'ouvre le vrai client
LoL, `data/db.db` ni `logs/`. Un fichier par groupe : `tests/test_client_draft_swaps.py`, `tests/test_swap_advice.py`,
`tests/test_client_en_partie.py`, `tests/test_final_analysis_data.py`, et les deux régressions des tâches 97 et 98.
Le fil `LiveGame` se teste avec un `fetch` factice, sans fil réel (une méthode `tick()` appelée à la main).

## 5. Tâches

Numéros globaux : à la suite de la tâche 95 du `TODO.md`. 1 pt ≈ 1 h.

| # | Tâche | Pts | Dépend de |
|---|---|---|---|
| **Lot 1 — Bans et acteur courant (8 pts)** | | | |
| 96 | `dump_lcu_draft_forms.py --watch`, relevé d'une draft classée et d'une normale par @pj35, fixtures réelles anonymisées (`session_ban`, `session_pick`, `session_swaps`), SPEC-21 §10 | 3 | — |
| 97 | Ban : cause racine confirmée sur le relevé, correctif, test de régression rouge puis vert, audit des appelants (`hover_champion`, console) | 3 | 96 |
| 98 | `current_actor` de la cellule 0 et `acting_cells` sur `isInProgress` : correctif et test de régression | 2 | — |
| **Lot 2 — Ordre de pick et swaps (24 pts)** | | | |
| 99 | `pick_order` et `swaps` dans `DraftState` et `DraftSnapshot`, console identique | 3 | 96, 98 |
| 100 | Ordre de pick à l'écran : numéro sur chaque sceau, anneau du joueur en cours | 3 | 99 |
| 101 | Actions de swap : liste blanche, `draft_swaps.run`, `POST /draft/swap/{kind}/{action}` | 5 | 96, 99 |
| 102 | Conseil de swap de rôle (`swap_advice.role_swaps`, constantes, best-effort) | 3 | 99 |
| 103 | Conseil de swap d'ordre : recherche à budget réduit, `scripts/bench_swap_advice.py`, calibrage du seuil ; **conditionnelle** | 5 | 102 |
| 104 | Carte « Échanges » : icônes, popover, bandeau de demande reçue, annuler | 5 | 100, 101, 102 |
| **Lot 3 — En partie (29 pts)** | | | |
| 105 | Spike Live Client en partie réelle (@pj35) : `items`, `championName`, `position`, `currentGold`, `abilities` ; page OneTricks : ordre des compétences ; fixtures | 3 | — |
| 106 | `FinalAnalysis` structuré, publié (sujet `game`), loadout étendu des substitutions, console identique | 5 | — |
| 107 | `LiveGame` : fil de lecture, série de win chance, état sur le bus, tests avec `fetch` factice | 5 | 105 |
| 108 | Écran « En partie » : cadre, navigation, pastille, état vide, face-à-face de la draft | 5 | 106, 107 |
| 109 | Courbe de win chance en direct (`line_chart`, repères d'objectifs, variation) | 3 | 107, 108 |
| 110 | Build : plan d'objets, substitutions, suivi des achats, ordre des compétences si publié | 5 | 105, 108 |
| 111 | Clôture : exe vérifié, README, `PROJECT_STRUCTURE.md`, `CHANGELOG.md`, SPEC-21 §7 mis à jour, statuts | 3 | 104, 109, 110 |

## 6. Critères d'acceptation

1. `python -m pytest tests/ -v` vert, avec les tests des tâches ci-dessus.
2. **Relevé** : `session_ban.json`, `session_pick.json` et `session_swaps.json` sont des extraits réels (clés
   `pickOrderSwaps`, `positionSwaps`, `hasSimultaneousBans`, `disallowBanningTeammateHoveredChampions` présentes,
   aucune identité : test qui cherche `puuid`, `gameName`, `tagLine`, `summonerId`).
3. **Ban** : `tests/regression/test_regression_client_ban_lcu.py` échoue sur le commit qui précède le correctif
   (`git stash` du fix ou checkout du parent) et passe après ; le PATCH émis par `run` pour `hover_ban` et `ban`
   est celui que le relevé documente (endpoint, type, `completed`).
4. **Ban** : aucune carte de ban ni tuile de grimoire n'offre un champion absent de `bannable-champion-ids`
   (test sur la fixture réelle) ; un clic sur la première carte envoie un survol (test du JS sous node, comme
   `rune_logic.js`) ; plus de présélection silencieuse.
5. **Console** : en phase de bans, `handle_auto_ban_hover` écrit sur l'action de type `ban` et lit le retour
   d'`auto_hover_champion` (test avec faux LCU) ; sinon, voir « À valider » du périmètre de la tâche 97.
6. **Acteur courant** : session minimale (cellule 0 en cours, cellule 5 plus loin) → `current_actor == 0` et
   `is_player_turn(...) is True` pour la cellule 0 (test de régression, rouge avant).
7. **Ordre de pick** : sur la fixture réelle, `pick_order` des dix joueurs est une permutation de 1 à 10 ; la page
   `/draft/stage` (`TestClient`) rend dix `.d-order`, un anneau `.d-acting` sur le joueur en cours (cellule 0
   comprise), et rien quand le LCU ne donne pas d'actions.
8. **Console identique** : la sortie console de `DraftRecommender` et de `FinalDraftAnalyzer.analyze` est
   identique avant et après les refontes (tests d'identité sur un jeu fixe, hors le message d'échec du critère 5).
9. **Swaps, écriture** : `WRITES` ne gagne que le motif des huit chemins de swap (test qui compare à la liste
   attendue) ; `POST /draft/swap/...` répond 403 sans jeton, 409 sans écriture quand la session ne liste pas le swap
   dans l'état attendu, et l'`id` écrit est celui de la session, jamais un paramètre du front (tests avec faux LCU).
10. **Conseil de rôle** : sur une fixture, le gain annoncé vaut `win_probability` après moins avant en points ;
    aucun conseil sans champion des deux côtés ni sous `SWAP_MIN_GAIN_PTS` ; une panne du conseil
    n'interrompt pas `DraftRecommender.provide` (test avec évaluateur qui lève).
11. **Conseil d'ordre** : `python scripts/bench_swap_advice.py` imprime le gain à 0,5 s et à 2 s par candidat ;
    résultat consigné en §4.6 ; tâche close sans conseil d'ordre si le critère de stabilité du §4.6 n'est pas tenu.
12. **Analyse structurée** : `FinalAnalysis` porte une ligne par lane dans l'ordre de `face_offs` ; publiée sur le
    bus et vidée au `reset_for_next_game` (tests) ; l'écran sans elle dit « analyse indisponible ».
13. **En partie, lecture** : `LiveGame.tick()` avec le `fetch` factice et `tests/fixtures/spike_live/snapshot.json`
    donne la même probabilité que `overlay.Tracker.update` ; hors `InProgress`, aucune lecture de l'API ; une
    exception du `fetch` ne sort pas du fil ; la série reste sous `INGAME_MAX_POINTS` ; un `gameTime` qui recule
    la réinitialise.
14. **En partie, écran** : `/en-partie` et `/en-partie/stage` répondent 200 dans les trois états (`idle`, `live`,
    `ended`), sans modèle (message d'entraînement) et avec moins de deux points (message, pas de courbe) ;
    aucune route `POST` sous `/en-partie` (test qui liste les routes).
15. **Build** : sur une fixture d'`allPlayers`, les objets possédés sont cochés dans le plan, le prochain objet
    non acheté est nommé, le manque d'or est calculé ; sans `items` dans l'API : « achats indisponibles » ; l'ordre
    des compétences n'apparaît que si la page le publie (test des deux cas).
16. **Exe** : `python build_app.py` puis `python scripts/check_exe_assets.py` : les nouveaux gabarits, scripts
    et modules y sont.
17. `CHANGELOG.md` (`[Unreleased]`), statut de cette spec, `docs/specs/README.md`, `TODO.md` et SPEC-21 §7
    (« Overlay et écran en partie » rouvert) à jour.

**Vérification de bout en bout** (par @pj35, client LoL réel, aucun test d'interface sans son accord) : en
draft classée, survoler puis valider un ban depuis le client LeagueStats et le voir apparaître dans le client
LoL ; lire les numéros 1 à 10 et l'anneau du joueur en cours, y compris à la cellule 0 ; demander, recevoir et
accepter un swap de rôle ; en partie, ouvrir « En partie » : analyse de la draft, plan de build qui se coche à
l'achat, courbe de win chance qui avance.

## 7. Hors périmètre

- ❌ **Overlay `tkinter` de SPEC-20** : inchangé, il reste un processus à part.
- ❌ **Swaps de champion** (`champion-swaps`, `bench-swap`, ARAM) : non demandés ; les endpoints existent.
- ❌ **Écriture en partie** : l'écran « En partie » ne commande rien dans le jeu.
- ❌ **Courbe de win chance persistée** : la page de la partie la redessine depuis la timeline LCU ; ne rien
  stocker pendant la partie évite une table et une migration.
- ❌ **Recalculer l'analyse de la draft depuis la Live Client API** quand le Live Coach ne l'a pas vue : à
  rouvrir si l'état « analyse indisponible » gêne à l'usage.
- ❌ **Runes et sorts en partie** : déjà dans la colonne loadout de la draft (non retenus par @pj35, 2026-10-06).
- ❌ **Objets des adversaires, cooldowns, suivi de leur or** : non demandés, et l'API ne sert pas l'or adverse.
- ❌ **Conseil d'ordre par règles écrites à la main** : sans métrique (§3).
- ❌ **Bascule automatique de page** vers « En partie » : à rouvrir après usage (§2, « à valider »).
