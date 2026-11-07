# SPEC-52 — Suivi du rang par compte

**Statut** : 🟡 Rédigée le 2026-11-07, arbitrages validés par @pj35 le 2026-11-07 (§2), relecture attendue avant `/implement`.

**Origine** : @pj35, 2026-11-07 — « On a un problème de suivi de l'ELO en multi-comptes. J'ai joué sur un smurf
et le coach a l'air de croire que j'ai perdu 1000 LP dans la journée. »

**Effort** : ~1 jour, 4 tâches (§5).

---

## 1. Constat

Lu sur le code et sur `data/db.db` (lecture `mode=ro`) le 2026-11-07.

- **Les photos de rang ne portent pas le compte.** `rank_snapshots` n'a que `captured_utc, queue, tier,
  division, lp, wins, losses, lp_delta, game_id` (migration 5c19a7e2d4b1). Les deux écritures,
  `snapshot_current` (`src/coaching/ranked.py:21`, au démarrage du Live Coach) et `snapshot_after_game`
  (`src/coaching/ranked.py:45`, à l'écran de fin), n'enregistrent pas le joueur.
- **Toutes les lectures mêlent les comptes.** `CoachingRepository.rank_history` et `rank_snapshots`
  (`src/repositories/coaching.py:138` et `:157`) lisent toute la table. Elles alimentent l'écran Rang
  (`rank_view`, `src/client/data.py:206`, appelé par `src/client/app.py:361`), la carte de rang de l'Accueil
  (`_rank_card`, `src/client/home.py:213`, lu en `:267`) et le bilan console (`lp_changes`,
  `src/coaching/report.py:86`).
- **Le symptôme, en base.** Le 2026-11-07, la file solo enchaîne Diamant IV 87 LP (photo de démarrage du
  2026-11-03, 451 V / 462 D), puis Or I 35 LP (démarrage à 12:28, 17 V / 17 D), neuf parties classées en Or I, puis
  de nouveau Diamant IV 87 LP (démarrage à 19:27). Sur l'échelle continue (`lp_scale`, 400 par palier, 100 par
  division), Diamant IV 87 vaut 2 487 et Or I 35 vaut 1 535 : la courbe montre −952 LP puis +952, et la note
  « ± LP sur 30 jours » de la carte compare des photos de deux comptes différents.
- **Deux comptes, même nom.** Les deux comptes s'appellent « Morty » (Riot ID différent par le tag) ; seul le
  `puuid` les distingue. Dans `game_records`, le joueur (`player_participant_id` dans `raw_game`) a le puuid
  `d06f7c3b…` dans 234 parties et `67777b36…` (le smurf) dans 19. L'écran de fin (`raw_eog`, champ
  `localPlayer.puuid`) porte aussi le puuid.
- **L'historique est rattachable.** 427 photos : 208 liées à une partie (`game_id`), toutes présentes dans
  `game_records`, donc de compte connu (199 principal, 9 smurf) ; 219 photos de démarrage sans partie (110 solo,
  109 flexible). Simulation du rattachement de §4.1 le 2026-11-07 : **427 photos sur 427 attribuées**
  (principal : 305 solo, 111 flexible ; smurf : 10 solo, 1 flexible), dont la paire de 12:28:18 (Or I solo, Or IV
  flexible) au smurf.

## 2. Objectif et arbitrages

Chaque photo de rang porte le compte qui l'a prise ; les écrans Rang et Accueil et le bilan console ne
montrent que celles d'un seul compte.

| Sujet | Décision |
|---|---|
| Compte affiché | **Validé (@pj35, 2026-11-07)** : le compte connecté dans le client ; client fermé, le dernier compte vu (celui de la photo la plus récente). Pas de sélecteur. |
| Historique existant | **Validé (@pj35, 2026-11-07)** : rattaché par la migration (photo liée → compte de la partie ; photo de démarrage → empreinte victoires + défaites, puis paire solo/flexible prise à la même seconde). Une photo sans attribution garde un compte NULL et sort des courbes. |
| Parties du smurf dans le gameplay (métriques, bilan de gameplay, maîtrise SPEC-41) | **Validé (@pj35, 2026-11-07)** : hors périmètre, elles restent mêlées (§7). |
| Identifiant du compte | `puuid` : stable, présent dans `current-summoner`, l'écran de fin et `raw_game`. Pas de Riot ID stocké : sans sélecteur, aucun écran ne nomme le compte. |

## 3. Approches considérées

1. **Colonne `puuid` dans `rank_snapshots`, filtre à la lecture** (retenue). Une migration, un paramètre de
   plus à l'écriture, un `WHERE puuid = ?` à la lecture. Le reste de la chaîne (`rank_view`, `_rank_card`,
   `lp_changes`) ne change pas : il reçoit déjà une liste de photos.
2. **Pas de colonne, compte déduit à la lecture** (photos liées via `game_records`, photos de démarrage par
   empreinte). Aucune migration, mais l'heuristique tourne à chaque affichage et une photo liée dont la partie
   n'est pas encore capturée reste sans compte. Écartée.
3. **Table `accounts` (puuid, Riot ID, vu le) et clé étrangère.** Utile seulement avec un sélecteur, écarté en
   §2. Écartée.

## 4. Détail

### 4.1 Migration Alembic (tâche 258)

Nouvelle révision après `a3f6c1d8b7e2` (head du 2026-11-07), `alembic/versions/<rev>_rank_snapshots_puuid.py`,
autonome (n'importe rien de `src/`, comme les migrations existantes) :

- `ALTER TABLE rank_snapshots ADD COLUMN puuid TEXT` et index `idx_rank_snapshots_puuid` sur `(puuid, id)`.
- Rattachement, dans cet ordre, SQL paramétré :
  1. **Photo liée** (`game_id` non NULL et présent dans `game_records`) : puuid du participant
     `player_participant_id` dans `raw_game.participantIdentities[].player.puuid`.
  2. **Photo de démarrage** (`game_id` NULL, `wins` et `losses` non NULL) : parmi les photos liées de la même
     file, les comptes dont une photo a un total `wins + losses` à au plus `MAX_GAMES_GAP = 10` parties ; un seul
     compte → ce compte, plusieurs ou aucun → rien. (Les compteurs d'un compte ne font que croître ; 10 parties
     couvrent les parties jouées entre deux démarrages sans photo liée.)
  3. **Paire de démarrage** : une photo encore sans compte, sans partie, prise à au plus `PAIR_SECONDS = 2` s
     d'une photo sans partie déjà attribuée **d'une autre file**, prend son compte (`snapshot_current` écrit
     solo et flexible dans la même seconde).
  4. Le reste garde `puuid` NULL.
- Les deux constantes vivent dans la migration, figées avec elle (une migration ne lit pas
  `config_constants.py`, qui peut changer après coup).
- `downgrade` : suppression de l'index puis de la colonne (`batch_alter_table`).
- La migration affiche `[DATA] rank_snapshots : N photos rattachées, M sans compte`.
- `tests/conftest.py:190` : la table de test reçoit la colonne `puuid` et l'index.

Tests (`tests/test_migration_rank_snapshots_puuid.py`, sur base temporaire comme
`tests/test_migration_game_records.py`) : montée puis descente ; photo liée → puuid de la partie ; photo de
démarrage à 3 parties du total d'un compte → ce compte ; ambiguë (deux comptes à moins de 10) → NULL ; paire
flexible à 1 s → même compte ; flexible isolée → NULL.

### 4.2 Écriture (tâche 259)

- `GameRecordRepository.insert_rank_snapshot(..., puuid: Optional[str] = None)`
  (`src/repositories/game_records.py:71`) écrit la colonne. Façade `Database.insert_rank_snapshot` inchangée
  (`**fields`).
- `ranked.snapshot_current(lcu, db)` lit `/lol-summoner/v1/current-summoner` (`lcu._make_request`, comme
  `src/draft/loadout_lcu.py:69`) et passe son `puuid` ; sans réponse, aucune photo (une photo sans compte ne
  servirait à rien).
- `ranked.snapshot_after_game(note, db, puuid: Optional[str])` : `GameCapture.write_lp_snapshots`
  (`src/coaching/capture.py`) passe `localPlayer.puuid` de l'écran de fin mis de côté pour ce `gameId`
  (`self._eog_by_game`), à défaut le puuid de `current-summoner` via `self.m.lcu`, à défaut None (la photo est
  écrite quand même : elle reste lue par la revue de partie, `rank_after_game`, qui ne filtre pas par compte).
- Tout reste best-effort (`_safely`) : aucune exception ne remonte dans la boucle du Live Coach.

Tests (`tests/test_coaching_capture.py`, fixtures de `tests/conftest.py`, faux LCU) : photo de démarrage avec le
puuid de `current-summoner` ; `current-summoner` absent → aucune photo ; photo d'après-partie avec le puuid de
l'écran de fin ; sans écran de fin → puuid de `current-summoner`.

### 4.3 Lecture (tâche 260)

- `CoachingRepository.rank_account() -> Optional[str]` : puuid de la photo la plus récente (`MAX(id)`) dont le
  puuid n'est pas NULL.
- `CoachingRepository.rank_history(puuid: Optional[str])` et `rank_snapshots(puuid: Optional[str])` :
  `WHERE puuid = ?`, liste vide si `puuid` est None.
- Client : `current_puuid(proxy) -> Optional[str]` dans `src/client/data.py` (puuid de
  `/lol-summoner/v1/current-summoner`, déjà autorisé par `src/client/lcu_proxy.py:18` ; None si le client est
  fermé). L'écran Rang (`src/client/app.py:361`) et l'Accueil (`src/client/home.py:267`) lisent
  `rank_history(current_puuid(proxy) or repo.rank_account())`. Un compte connecté sans photo affiche l'état vide
  existant.
- Bilan console (`src/coaching/report.py:86`, sans appel LCU par construction) : `rank_snapshots(repo.rank_account())`.
- `rank_after_game` (revue de partie, SPEC-45) ne change pas : la photo est déjà celle de la partie.

Tests : `tests/test_client_rang.py`, `tests/test_client_accueil.py` (photos de deux comptes, seul le compte
connecté ressort ; client fermé → dernier compte vu) ; test du bilan.

Test de régression `tests/regression/test_regression_rank_mixes_accounts.py` : le scénario du 2026-11-07 (photos
Diamant IV du principal, puis Or I du smurf, puis Diamant IV du principal), la carte solo de `rank_view` du compte
principal ne porte aucun écart de LP négatif ; rouge avant la tâche 260, vert après.

## 5. Tâches

| # | Tâche | Pts | Dépend de |
|---|---|---|---|
| 258 | Migration `rank_snapshots.puuid` et rattachement de l'historique (§4.1), `tests/conftest.py`, tests de migration | 3 | — |
| 259 | Écriture du puuid : `insert_rank_snapshot`, `snapshot_current`, `snapshot_after_game`, `GameCapture`, tests (§4.2) | 2 | 258 |
| 260 | Lecture par compte : `rank_account`, `rank_history`, `rank_snapshots`, `current_puuid`, écrans Rang et Accueil, bilan console, test de régression, tests (§4.3) | 3 | 258 |
| 261 | Clôture : `CHANGELOG.md`, statut de cette spec, README des specs, `TODO.md` ; `alembic upgrade head` sur `data/db.db` et recette laissés à @pj35 | 1 | 259, 260 |

## 6. Critères d'acceptation

1. `python -m pytest tests/ -v` vert, avec les tests des tâches 258 à 260.
2. `python -m alembic upgrade head` puis `python -m alembic downgrade -1` puis `upgrade head` passent sur une
   copie de `data/db.db`.
3. Sur une copie de `data/db.db` migrée :
   `SELECT COUNT(*) FROM rank_snapshots WHERE puuid IS NULL` vaut 0, et
   `SELECT COUNT(*), MIN(tier), MAX(tier) FROM rank_snapshots WHERE puuid LIKE '67777b36%'` donne 11 photos, toutes
   en `GOLD`.
4. `grep -n "puuid" src/coaching/ranked.py src/repositories/game_records.py src/repositories/coaching.py` montre
   l'écriture et le filtre ; le filtre est paramétré (`?`), sans f-string.
5. `tests/regression/test_regression_rank_mixes_accounts.py` existe et passe ; il échoue sur le code d'avant la
   tâche 260 (vérifié par `git stash` pendant l'implémentation).
6. Un appel LCU qui échoue pendant la photo (démarrage ou après-partie) ne lève rien hors de `GameCapture`
   (test dédié).
7. `CHANGELOG.md` (`[Unreleased]`), statut de cette spec et `docs/specs/README.md` à jour.

**Vérification de bout en bout** : sur une copie migrée de `data/db.db`, l'écran Rang client fermé montre la
courbe du dernier compte vu (principal, Diamant IV 87 LP le 2026-11-07 à 19:27) sans le creux en Or ; puis, en
réel (@pj35), une partie classée sur le smurf ajoute un point à la courbe du smurf seulement, et l'écran Rang
bascule de courbe en changeant de compte dans le client.

## 7. Hors périmètre

- ❌ Parties du smurf dans le gameplay : `game_metrics`, constats, bilan de gameplay, maîtrise personnelle
  (SPEC-41), pool. Elles restent mêlées (validé le 2026-11-07). À remesurer si le smurf devient fréquent :
  contre des adversaires Or, l'impact (ΔP) d'une partie peut gonfler la maîtrise des champions joués sur le
  smurf.
- ❌ Sélecteur de compte et Riot ID stocké (validé le 2026-11-07, §2).
- ❌ Photo de démarrage à chaque changement de compte sans redémarrer le Live Coach : `on_startup` ne tourne
  qu'une fois (`src/draft_monitor.py:188`). Les photos d'après-partie du nouveau compte sont bien rattachées ; la
  photo de démarrage manque jusqu'au prochain lancement.
