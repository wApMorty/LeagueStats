# SPEC-44 — Un pool par poste

**Statut** : 🟢 Rédigée et validée le 2026-10-28 (tous les arbitrages de §2).

**Origine** : @pj35, 2026-10-28 — « J'aimerais pouvoir charger plusieurs champion pools car je joue
plusieurs rôles. L'appli choisirait le bon pool en fonction du rôle sur lequel je tombe. »

**Effort** : ~1,5 jour, 4 tâches (§5).

---

## 1. Constat

Lu sur le code et sur les fichiers de @pj35 le 2026-10-28.

- **Un seul pool par session.** Le Live Coach du client lit `pool_name` dans `user_prefs.json` au
  lancement (`src/client/launch.py:67-76`) et le garde pour toutes les drafts. Seule la commande
  `pool <nom>`, déposée par l'écran Pool, le change en cours de route (`src/draft/commands.py:88-107`).
- **Le rôle du pool passe avant le poste assigné.** `_resolve_player_lane` (`src/draft/automation.py:82-101`)
  et `_ban_lane` (`src/draft/ban_advice.py:50-62`) prennent `pool_lane` d'abord, et le poste assigné par
  le client seulement à défaut. Avec « Top playable » actif et un poste mid, le blind pick du hover initial
  et les bans sont donc calculés pour le top.
- **@pj35 a déjà un pool par rôle.** `champion_pools.json` contient 8 pools perso : `Top playable`
  (top, 13 champions), `Mid` (mid, 5), `ADC` (adc, 5), `Jungle` (jungle, 5), `Support` (support, 5),
  plus `GRIND`, `GWEN` et `ULTRA GRIND` au top. `user_prefs.json` désigne `Top playable`.
- **Le rôle d'un pool ne se règle pas dans le client.** `edit(..., "creer")` appelle
  `create_pool(arg, [])`, donc `role="custom"` (`src/client/pools.py:93`, `src/pool_manager.py:342-359`).
  Un pool créé dans le client n'a pas de lane déclarée.
- **Les bans précalculés dépendent de la lane déclarée du pool.** Ils sont calculés pour
  `pool_role_to_lane(pool.role)`, ou la lane dominante du pool si le rôle est `custom`
  (`src/analysis/ban_recommendations.py:172`). `BanAdvisor._recommendations` ne les sert que si
  `pool_lane` est posée (`src/draft/ban_advice.py:77`). Si `pool_lane` devient le poste assigné, un pool
  déclaré top servi au mid sortirait des bans calculés pour le top.
- **Le poste est connu dès le premier tick de la draft.** `DraftStateParser` remplit `ally_positions`
  depuis `assignedPosition` (`src/draft/state_parser.py:61`, `src/lcu_client.py:266-280`). Une file
  sans poste (normale blind, ARAM, partie perso) renvoie une chaîne vide, absente de
  `LCU_POSITION_TO_LANE` (`src/config_constants.py:16-26`).
- **Ordre du premier tick.** `_handle_champ_select` (`src/draft/lifecycle.py:178-196`) parse l'état,
  vide la file de commandes, puis `_handle_draft_change` lance le hover initial
  (`src/draft/lifecycle.py:407-410`). L'état de draft est remis à zéro par `reset_for_next_game`
  (`src/draft/lifecycle.py:330-345`), qui remet aussi `has_done_initial_hover` à `False`.
- **Changer de pool est rapide.** `Assistant.warm_cache` mesuré le 2026-10-28 sur `data/db.db` :
  `Top playable` 0,52 s à froid (13 champions), `Mid` 0,05 s, `All Top Champions` 0,24 s (91).

## 2. Objectif et arbitrages

Au premier tick de chaque draft, le Live Coach charge le pool que @pj35 a désigné pour le poste assigné,
et évalue tout (blind pick, recommandations, bans) sur ce poste.

| Sujet | Décision |
|---|---|
| Choix du pool d'un poste | **Validé (@pj35, 2026-10-28)** : un pool désigné par poste sur l'écran Pool, mémorisé dans `user_prefs.json` (`pools_by_role`). N'importe quel pool convient, même `custom` : c'est le poste assigné qui fixe la lane. |
| Poste sans pool désigné | **Validé (@pj35, 2026-10-28)** : le pool système du rôle (« All Support Champions »), avec un `[INFO]`. |
| Poste sans pool désigné, mais le pool par défaut a ce rôle | **Validé (@pj35, 2026-10-28)** : le pool par défaut sert (ex. `Top playable` au top tant qu'aucun pool top n'est désigné). Sans cette règle, la configuration actuelle de @pj35 passerait à « All Top Champions » au top jusqu'à ce qu'il désigne ses pools. |
| File sans poste assigné | **Validé (@pj35, 2026-10-28)** : le pool par défaut, c'est-à-dire le pool actif d'aujourd'hui (`pool_name`), relu à chaque draft. Comportement inchangé. |
| Choix manuel pendant une draft | **Validé (@pj35, 2026-10-28)** : « Pool par défaut » cliqué pendant une draft remplace le pool du poste jusqu'à la fin de cette draft ; la règle par poste reprend à la suivante. |
| Pool désigné supprimé | Traité comme non désigné : le nom reste dans `user_prefs.json` mais ne résout plus rien (même règle que `active_pool_name`). Pas de nettoyage. |
| Coach console (`lol_coach.py`) | Il partage `DraftMonitor` : la règle par poste s'applique dès que `user_prefs.json` désigne des pools. La sélection interactive au lancement ne change pas et devient le pool par défaut de la session. |

## 3. Approches considérées

1. **Un pool désigné par poste, dans `user_prefs.json`** (retenue). Cinq noms à côté de `pool_name`.
   Aucun changement de `champion_pools.json` ni de `ChampionPool`, et aucun éditeur de rôle à ajouter
   dans le client. Coût : la lane déclarée du pool et le poste peuvent différer, d'où la règle des bans
   précalculés (§4.2).
2. **Un pool « favori » par rôle, choisi selon `ChampionPool.role`.** Pas de nouvelle préférence, mais il
   faut un éditeur de rôle dans le client (tout pool qui y est créé est `custom`) et un drapeau de favori
   dans `champion_pools.json`. Écartée par @pj35.
3. **Fusion de tous les pools du rôle.** Aucun réglage, mais `GRIND`, `GWEN` et `Top playable` se
   mélangent, et le pool de la session perd son sens. Écartée par @pj35.

## 4. Détail

### 4.1 Préférences (`src/user_prefs.py`)

- `UserPrefs.pools_by_role: Dict[str, str] = field(default_factory=dict)`. Les clés sont les valeurs de
  `LCU_POSITION_TO_LANE` (`top`, `jungle`, `middle`, `bottom`, `support`) ; les valeurs sont des noms de pool.
- `load_user_prefs` lit `data.get("pools_by_role", {})`. Si la valeur n'est pas un objet, on prend `{}` ;
  on garde les entrées dont la clé est une lane connue et la valeur une chaîne. Une valeur invalide ne
  rend jamais `None` : les autres préférences restent valables.
- `save_role_pool(lane: str, name: Optional[str]) -> bool` : désigne `name` pour `lane`, ou retire la
  désignation si `name` est `None`. Même modèle que `save_pool_name` (`replace(load_user_prefs() or
  UserPrefs(), ...)`). Une lane inconnue renvoie `False` sans rien écrire.
- `save_user_prefs` n'a rien à faire de plus : `asdict` emporte le nouveau champ.

### 4.2 Live Coach (`src/draft/pool_selection.py`, `src/draft/lifecycle.py`, `src/draft/commands.py`, `src/draft/ban_advice.py`, `src/draft_monitor.py`)

- **Pool de lancement.** `DraftMonitor` garde dans `self.launch_pool_name` le nom résolu au démarrage
  (`pool_name` après `select_by_name`, la sélection interactive ou le repli « All Top Champions »).
  C'est le pool par défaut si `user_prefs.json` n'en désigne aucun qui existe.
- **Lane déclarée.** Partout où `pool_lane` est tiré du rôle du pool (`PoolSelector.select_by_name`,
  `select_interactive`, `DraftMonitor` repli auto, `handle_pool_command`), on pose aussi
  `self.m.pool_declared_lane = pool_role_to_lane(pool.role)`.
- **`PoolSelector.select_for_position(lane: Optional[str]) -> None`** : appelée une fois par draft.
  1. Relit `load_user_prefs()` (une désignation faite dans le client sert dès la draft suivante, sans
     commande).
  2. `lane` connue : le pool de `pools_by_role[lane]` s'il existe. Sinon le pool par défaut quand sa lane
     déclarée vaut `lane` (§2). Sinon le pool système du rôle :
     le pool `created_by == "system"` dont `pool_role_to_lane(role) == lane`.
  3. `lane` absente : le pool par défaut (`prefs.pool_name` s'il existe, sinon `launch_pool_name`).
  4. Pose `current_pool`, `pool_name`, `pool_declared_lane`, et `pool_lane = lane or pool_declared_lane`.
     Appelle `assistant.warm_cache` seulement si le pool a changé.
  5. Une ligne console : `[INFO] Poste mid : pool « Mid » (5 champions)`. Avec le pool système :
     `[INFO] Poste support : aucun pool désigné, pool « All Support Champions »`.
  6. Best-effort : une exception est attrapée et journalisée en `[ALERTE]`, et le pool courant reste.
- **Déclenchement.** Dans `_handle_champ_select`, après `_apply_pending_commands` et avant
  `_handle_draft_change` : si `not self.m.has_resolved_pool`, appeler
  `select_for_position(current_state.ally_positions.get(current_state.local_player_cell_id))`, puis
  `has_resolved_pool = True`. Le drapeau est initialisé à `False` dans `DraftMonitor.__init__` et remis à
  `False` dans `reset_for_next_game`, comme `has_done_initial_hover`. Placé après les commandes, ce choix
  écrase une commande `pool` déposée entre deux drafts (le pool par défaut est déjà sauvegardé) ; les
  commandes des ticks suivants l'emportent jusqu'à la fin de la draft.
- **`handle_pool_command` pendant une draft.** Si `last_draft_state` porte un poste pour le joueur local,
  `pool_lane` garde ce poste au lieu de la lane déclarée du nouveau pool : on joue toujours le mid, quel
  que soit le pool.
- **Bans précalculés.** `BanAdvisor._recommendations` ne lit `pool_ban_recommendations` que si
  `pool_lane == pool_declared_lane` (au lieu de la seule présence de `pool_lane`). Sinon, calcul à la
  volée sur `pool_lane`. Le docstring est mis à jour.

### 4.3 Écran Pool (`src/client/pools.py`, `src/client/app.py`, `src/client/templates/partials/pool_body.html`)

- `pools_view` ajoute `roles` : pour chaque lane de `LCU_POSITION_TO_LANE` (ordre top, jungle, middle,
  bottom, support), `{"lane", "label", "pool"}`, où `pool` est le nom désigné s'il existe, sinon `None`.
  Libellés : Top, Jungle, Mid, ADC, Support. Le détail du pool ouvert porte `roles_on` (les lanes qu'il
  couvre) ; chaque entrée de la liste porte aussi ses libellés de poste.
- `edit(..., action="role", arg=<lane>)` : bascule la désignation. Si le pool est déjà celui de la lane,
  on la retire, sinon on le désigne. Lane inconnue : `Refusal("Poste inconnu")`. Notice :
  « Pool « Mid » pour le poste Mid (appliqué dès la prochaine draft) » ou « Poste Mid : plus de pool
  désigné ». Les pools système se désignent aussi.
- `app.py`, route des actions : `role` rejoint `actif` dans les actions qui n'écrivent pas
  `champion_pools.json` et n'effacent pas les bans. Aucune commande n'est déposée pour `role`.
- Gabarit :
  - la ligne d'en-tête devient « Par défaut : **X** · Top : **Top playable** · Jungle : pool système · … » ;
  - le bouton « Utiliser ce pool » devient « Pool par défaut », sans autre changement (même action
    `actif`, même commande `pool <nom>`) ;
  - le panneau du pool ouvert ajoute une rangée de 5 boutons de poste, `aria-pressed` selon `roles_on`
    (`hx-post="/pool/role?name=…&arg=<lane>"`) ;
  - le badge « Actif » de la liste devient « Défaut », et les libellés de poste désignés s'y ajoutent.

### 4.4 Constantes

Aucune. Les libellés de poste sont des textes d'interface du gabarit et de `pools.py`, pas des réglages.

### 4.5 Tests

- `tests/test_user_prefs.py` : aller-retour de `pools_by_role` ; valeur invalide (liste, clé inconnue,
  valeur non chaîne) filtrée sans perdre les autres préférences ; `save_role_pool` désigne, retire, refuse
  une lane inconnue et garde `motion`.
- `tests/test_draft_monitor_pool_selection.py` : `select_for_position` sur un poste désigné, un poste non
  désigné (pool système), un pool désigné supprimé, l'absence de poste (pool par défaut, puis
  `launch_pool_name` sans préférence), une exception (pool courant gardé), un poste non désigné couvert
  par le pool par défaut (`Top playable` au top).
- `tests/regression/` ou `tests/test_draft_monitor_lifecycle.py` : premier tick d'une draft mid avec un
  pool par défaut top, puis le hover initial résout la lane `middle` ; une commande `pool` déposée avant
  la draft est écrasée, une commande au 2e tick l'emporte et garde `pool_lane = "middle"` ; après
  `reset_for_next_game`, une draft sans poste repasse au pool par défaut.
- `tests/test_draft_monitor_ban_advice_lane.py` : pool déclaré top servi au mid, donc pas de bans
  précalculés et calcul sur `middle` ; pool déclaré mid au mid, donc bans précalculés servis.
- `tests/test_client_pool.py` : `pools_view` expose `roles` et `roles_on` ; `edit("role")` désigne,
  retire, refuse un poste inconnu ; la route `/pool/role` n'écrit pas `champion_pools.json` et ne dépose
  aucune commande.

Tous hermétiques : `user_prefs.json` et `champion_pools.json` sous `tmp_path` (patch de
`get_user_prefs_path` / `get_user_pools_path`, comme les tests existants).

## 5. Tâches

| # | Tâche | Pts | Dépend de |
|---|---|---|---|
| 215 | `user_prefs` : `pools_by_role`, lecture tolérante, `save_role_pool` + tests | 2 | — |
| 216 | Live Coach : `select_for_position` au premier tick, `launch_pool_name`, `pool_declared_lane`, `handle_pool_command` garde le poste, bans précalculés seulement sur leur lane + tests | 5 | 215 |
| 217 | Écran Pool : désignation par poste, en-tête, badges, « Pool par défaut » + tests | 3 | 215 |
| 218 | Clôture : critères, `CHANGELOG.md`, statut, README des specs, `TODO.md` | 1 | 216, 217 |

## 6. Critères d'acceptation

1. `python -m pytest tests/ -v` vert, avec les tests de §4.5.
2. `python -m pytest tests/test_user_prefs.py -v` : un `user_prefs.json` sans `pools_by_role` (le fichier
   actuel de @pj35) se charge, avec `pools_by_role == {}`.
3. Au premier tick d'une draft avec poste `middle` et `pools_by_role == {"middle": "Mid"}`, `current_pool`
   vaut les champions de `Mid` et `pool_lane == "middle"` avant le hover initial (test de 216).
4. Poste désigné sur aucun pool existant, donc pool système du rôle et `[INFO]` en console ; mais pool
   par défaut si sa lane déclarée est ce poste (tests de 216).
5. Draft sans poste : pool par défaut, comme avant SPEC-44 (test de 216).
6. Une commande `pool <nom>` au 2e tick remplace le pool jusqu'à `reset_for_next_game`, et `pool_lane`
   garde le poste (test de 216).
7. `grep -n "pool_declared_lane" src/draft/ban_advice.py` : les bans précalculés ne sont servis que sur
   leur lane déclarée.
8. Aucune exception de `select_for_position` n'interrompt la draft (test de 216 : exception injectée,
   la draft continue avec le pool courant).
9. Écran Pool : désigner, retirer et voir la désignation dans l'en-tête et la liste (tests de 217).
10. `CHANGELOG.md` (`[Unreleased]`), statut de cette spec, `docs/specs/README.md` et `TODO.md` à jour.

**Vérification de bout en bout** : recette @pj35 sur le client. Désigner `Mid` pour le poste Mid et
`Support` pour le poste Support sur l'écran Pool, lancer une partie classée, puis vérifier en draft le
`[INFO] Poste … : pool « … »`, le blind pick et les bans du poste obtenu. Une normale blind doit ensuite
repartir sur le pool par défaut.

## 7. Hors périmètre

- ❌ Éditeur du rôle d'un pool dans le client : la désignation par poste le rend inutile.
- ❌ Lire les postes choisis dans le lobby (primaire / secondaire) pour préparer le pool avant la draft :
  le poste assigné arrive au premier tick, et changer de pool prend moins d'une seconde.
- ❌ Précalcul des bans pour chaque couple (pool, poste) : le calcul à la volée sert déjà quand les lanes
  diffèrent.
- ❌ Fusion de plusieurs pools pour un même poste : écartée par @pj35 (§3).
