# SPEC-27 — Vérification des postes en partie et recalcul de l'écran « En partie »

**Statut** : 🟡 Rédigée le 2026-10-08. Approche validée par @pj35 (§3, A) ; le déclencheur exact dépend du spike de la
tâche 122 (§2, « À valider »).

**Origine** : @pj35, 2026-10-08 : « vérifier une fois la game lancée que les ennemis sont au rôle prédit, et ajuster
les données de l'écran "En partie", avec les données du matchup et les builds recommandés ».

**Effort** : ~2,5 jours, 7 tâches (§5, 23 pts), dont un relevé sur de vraies parties joué par @pj35.

---

## 1. Constat

Lecture du code et de `data/db.db` en lecture seule, 2026-10-08.

- **Les postes adverses sont toujours devinés pendant la draft.** Le LCU ne donne `assignedPosition` que pour mon
  équipe ; `state_parser.py:210-214` infère les cinq postes ennemis par `infer_team_roles`, qui maximise la
  vraisemblance des parts de lane de chaque champion (`src/role_inference.py`). En normal blind, mes alliés sont
  inférés aussi.
- **Tout l'écran « En partie » en dépend.** `build_final_analysis` (`src/draft/final_analysis.py:354-377`) place chaque
  champion sur son poste inféré, et `face_offs` apparie les deux camps lane par lane : un poste faux change le duel,
  les matchups et synergies pondérés par lane, et la probabilité de la draft. La build suit le même poste :
  `LoadoutImporter.direct_opponent` (`src/draft/loadout_import.py:124-132`) prend l'ennemi inféré sur ma lane, et la page
  OneTricks du duel (`get_page(champion, lane, adversaire)`) en dépend.
- **Rien ne vérifie ces postes une fois la partie lancée.** L'analyse est calculée une fois, à la fin de la draft
  (`lifecycle.py:235-237`), publiée sur le sujet `game` du bus, puis gardée telle quelle jusqu'à la draft suivante
  (SPEC-24 §4.8). SPEC-24 §2 (ligne 106) avait écarté d'en recalculer une depuis `allPlayers[].position`.
- **L'inférence se trompe.** Mesure rejouée après coup sur les 69 parties capturées dont on connaît le poste réel
  (écran de fin, `detectedTeamPosition`) : 321 champions adverses sur 345 au bon poste (93 %), mais **59 équipes
  adverses sur 69 entièrement justes (85 %)** ; les erreurs sont des permutations (milieu / bas, soutien / haut /
  milieu). Mes alliés, eux, sont justes 346 fois sur 346 (poste LCU, parties classées). Le recalcul utilise les parts de
  lane d'aujourd'hui, pas celles du jour de la partie : c'est un ordre de grandeur, pas la mesure exacte.
- **La Live Client API sert un poste pour les dix joueurs.** `allPlayers[*].position` vaut `TOP`, `JUNGLE`, `MIDDLE`,
  `BOTTOM` ou `UTILITY` (spike du 2026-10-07, une lecture à 17 min 21 s, SPEC-24 §4.9 ;
  `tests/fixtures/spike_live/allgamedata_items.json`). **Non établi** : depuis quelle minute le champ est rempli, s'il
  l'est pour les adversaires dès l'ouverture de la partie, s'il bouge, et s'il est égal à `detectedTeamPosition` de
  l'écran de fin. Tout le déclencheur en dépend (§2, tâche 122).
- **Le fil du client lit déjà cette API.** `LiveGame` (`src/client/ingame.py`) interroge `allgamedata` chaque seconde et
  publie `{state, game_time, p, delta, series, objectives, me}` sur le sujet `ingame` ; il n'y publie pas la liste des
  joueurs.
- **La boucle du Live Coach tourne pendant la partie.** `monitor_loop` revient tôt hors `ChampSelect`
  (`lifecycle.py:46-98`) mais continue de s'exécuter (phase de fin de partie, collecte de fond) ; `last_draft_state`
  garde les picks et `inferred_roles` jusqu'à `_reset_for_next_game`.

## 2. Objectif et arbitrages

**Objectif** : une fois la partie lancée et les postes lus en jeu, confronter chaque joueur à son poste prédit ; si au
moins un diffère, recalculer le face-à-face (matchups, duel, probabilité) et le plan de build avec les vrais postes,
et l'afficher avec ce qui a changé.

| Sujet | Décision |
|---|---|
| Où recalculer | **Validé (@pj35, 2026-10-08)** : dans le Live Coach, qui détient l'évaluateur, la base et `LoadoutImporter` (§3, A). |
| Source du poste réel | **À valider (spike, tâche 122)** : `allPlayers[*].position` de la Live Client API, retenue sous réserve que le spike la montre remplie pour les adversaires et conforme à `detectedTeamPosition` de l'écran de fin sur les parties relevées. Repli envisagé si elle est vide tôt : le sort Châtiment (`summonerSpells`) pour la seule jungle. |
| Quand corriger | **À valider (spike, tâche 122)** : **défaut proposé**, dès que les cinq postes d'une équipe sont renseignés, distincts, et inchangés depuis `REALITY_STABLE_S` = 10 s de temps de jeu. Si le spike montre un champ qui bouge en début de partie (échange de lanes), le seuil monte ou une fenêtre minimale de temps de jeu s'ajoute. |
| Qui est vérifié | **Défaut proposé** : les dix joueurs, équipe par équipe. Une équipe au relevé incomplet ou ambigu n'est pas touchée et l'écran le dit. |
| Le poste réel prime | **Défaut proposé** : sur le poste inféré **et** sur un poste corrigé à la main (`r <champion> <lane>`), pour les champions que le relevé couvre. Les autres gardent leur poste d'avant. |
| Corrections par partie | **Défaut proposé** : une par relevé distinct, au plus `REALITY_MAX_CORRECTIONS` = 3 par partie (borne contre un champ instable). |
| Runes et sorts | **Défaut proposé** : non recalculés. Ils ont été poussés dans le client au verrouillage et ne se changent plus en partie ; l'écran « En partie » ne montre que les objets et l'ordre des compétences (SPEC-24 §2, « Contenu build »). |
| Prédiction enregistrée (`predictions`) | **Défaut proposé** : intacte. La spec ne touche ni la calibration (SPEC-08) ni la table ; voir §7. |
| Écriture en partie | Aucune dans le jeu ni dans le client LoL (lecture seule, SPEC-24 §2). La seule écriture est la republication du sujet `game` sur le bus interne. |
| Draft non vue | **Défaut proposé** : si le Live Coach n'a pas analysé la draft de cette partie, rien n'est vérifié (l'écran garde son « analyse indisponible »). Recalculer depuis `allPlayers` seul reste écarté (SPEC-24 §2). |

## 3. Approches considérées

- **A. Dans le Live Coach — retenue.** `LiveGame` publie la liste des joueurs et leur poste dans le sujet `ingame` ;
  une étape `RealityCheck`, appelée par `monitor_loop` quand la phase est `InProgress`, relit `bus.latest("ingame")`,
  compare, recalcule avec l'évaluateur et `LoadoutImporter` déjà chargés, puis republie `game`. L'écran « En partie »
  ne change presque pas : il relit un sujet qu'il consomme déjà. Best-effort, hors de la boucle de draft ; le seul
  appel réseau (page OneTricks du duel) a le délai de `LOADOUT_TIMEOUT_SECONDS`.
- B. Dans le serveur du client : le fil `LiveGame` reconstruirait un évaluateur (matchups et synergies en mémoire) et
  appellerait OneTricks. Fonctionne sans Live Coach, mais duplique le chargement de données dans un second fil,
  alourdit le processus et ouvre un deuxième chemin vers `build_final_analysis`. Écartée.
- C. Constat seul, sans recalcul : marquer les lignes dont le poste diffère. Le plus léger, mais n'ajuste pas les données
  demandées. Écartée.

## 4. Détail

### 4.1 Spike (tâche 122)

`scripts/spike_live_positions.py` (nouveau, lecture seule) : pendant une partie, lit `allgamedata` toutes les 5 s et écrit
dans `outputs/spike_live/` (ignoré par git) la série `(temps de jeu, [(rawChampionName, team, position, sort de
Châtiment)])`, identités absentes. Option `--compare` : après la partie, lit **en lecture seule**
`game_records.raw_eog` de la partie la plus récente (`file:data/db.db?mode=ro`) et affiche, par tranche de temps de
jeu (0-30 s, 30-60 s, 1-3 min, 3-10 min, 10 min et plus), la part des joueurs dont `position` vaut
`detectedTeamPosition`, adversaires et alliés séparés. Relevé par @pj35 sur **au moins 3 parties** (une normale
blind au moins, pour les alliés inférés), consigné ici en §4.1 avec : minute d'apparition du champ, changements
observés, conformité à l'écran de fin. La tâche s'arrête là : les constantes du §4.5 sont fixées d'après le relevé.

### 4.2 Liste des joueurs dans le sujet `ingame` (tâche 123)

`src/client/ingame.py` : `roster_of(data: dict) -> List[Dict[str, str]]`, fonction pure à côté de `me_of` : une entrée
par `allPlayers`, `{"champion": championName, "raw": rawChampionName sans le préfixe "game_character_displayname_",
"team": "ORDER"|"CHAOS", "position": position or ""}`. Ajoutée au dictionnaire de `_read` (`roster`), donc aussi à
l'état `ended`. Aucune identité de joueur (`summonerName`, `riotId`) n'y entre.

### 4.3 Comparaison, fonctions pures (tâche 124)

`src/draft/reality_check.py` (nouveau) :

```python
EOG_LANES = {"TOP": "top", "JUNGLE": "jungle", "MIDDLE": "middle", "BOTTOM": "bottom", "UTILITY": "support"}

def resolve_champions(roster, names: Dict[int, str]) -> Dict[int, dict]:
    """championId -> entrée du relevé. `names` : championId -> nom d'affichage de la draft.
    Clé de comparaison : minuscules sans caractère non alphanumérique, essayée sur `raw` puis sur `champion`
    (Wukong / MonkeyKing, Nunu & Willump / Nunu, Renata Glasc / Renata). Introuvable ou ambigu : absent, jamais deviné."""

def real_lanes(resolved) -> Dict[int, str]:
    """championId -> lane réelle, pour les seules équipes dont les cinq postes sont renseignés et distincts."""

def compare(predicted: Dict[int, str], real: Dict[int, str]) -> Dict[str, Any]:
    """{"checked": n, "mismatches": [{"champion_id", "predicted", "real"}], "unverified": [champion_id, ...]}"""
```

Fonctions pures : ni base, ni LCU, ni bus. La lane interne est celle de `scraping_config.LANES`
(`top`, `jungle`, `middle`, `bottom`, `support`), comme `coaching/metrics.py:EOG_POSITIONS` dont la table est
réutilisée plutôt que dupliquée.

### 4.4 Étape dans le Live Coach (tâches 125 et 126)

**`LoadoutImporter.retarget(champion_id, lane, opponent) -> Optional[Dict]`** (`src/draft/loadout_import.py`, tâche 125) :
`_import` est scindé en un calcul (`get_page`, `pick_build`, `adapt_to_matchup`, substitutions du duel) et une
application (`apply_build` dans le client LoL). `retarget` fait le calcul seul, met à jour `_applied` et `_duel_info`, et
renvoie `state(with_duel=True)`, sans toucher au LCU. `_import` garde son comportement et ses messages (test
d'identité sur les cas de `tests/test_loadout_import.py`).

**`RealityCheck(monitor)`** (`src/draft/reality_check.py`, tâche 126) :

- `step()` est appelé par `monitor_loop` quand la phase vaut `InProgress`, avant le `return` de la branche
  « hors champ select » (`lifecycle.py:93`). Il ne lève jamais (`try/except` large, `[INFO]` une fois par message
  distinct, comme `GameCapture._warn`).
- Il ne fait rien sans `has_analyzed_final_draft`, sans `bus`, ou sans `latest("ingame")` à l'état `live` portant un
  `roster`.
- Stabilité : le relevé de postes doit être identique sur `REALITY_STABLE_S` secondes de temps de jeu (le `game_time` du
  sujet) avant d'être pris en compte.
- Comparaison : `compare(last_draft_state.inferred_roles, real_lanes(...))`. Tous conformes : publie `reality`
  `state = "ok"` et imprime `[OK] Postes vérifiés en partie : N/N conformes`. Écarts : recalcule
  `build_final_analysis(monitor, ally_picks, enemy_picks, {**inferred_roles, **real})`, puis la build avec
  `retarget(mon champion, mon vrai poste, adversaire direct réel)` (adversaire = l'ennemi dont le poste réel est le
  mien, seul sur ce poste), publie `game` avec `reality = {"state": "corrected", "mismatches": [...]}` et imprime
  `[ALERTE] Postes corrigés en partie : <champion> <prédit> -> <réel>, ...` puis `[INFO] Face-à-face et build recalculés`.
- Équipe au relevé incomplet ou ambigu : `state = "partial"` et une ligne `[INFO]` ; champion non résolu :
  `unverified`. Un relevé déjà traité (même correspondance championId → lane) n'est pas recalculé ; au plus
  `REALITY_MAX_CORRECTIONS` recalculs par partie.
- `reset()` (appelé par `_reset_for_next_game`) remet l'état à zéro. Une correction ne se republie jamais après
  la remise à zéro : la republication vérifie que la partie est toujours celle qui a été lue.
- `build_final_analysis` n'imprime ni ne publie rien ; `RealityCheck` porte lui-même la publication. `inferred_roles` de
  `last_draft_state` n'est **pas** modifié : la comparaison de la partie suivante repart des postes de sa propre draft.

### 4.5 Charge utile et constantes

`FinalAnalysis` (`src/draft/final_analysis.py`) gagne `reality: Optional[Dict[str, Any]] = None` (`state`, `checked`,
`mismatches` avec nom du champion, poste prédit et poste réel en français, `at` : temps de jeu du relevé). `None` : rien
n'a été vérifié (c'est le cas avant le relevé, et pour toute draft d'avant la spec).

`src/config_constants.py`, `DraftConfig` : `REALITY_STABLE_S: float = 10.0` (défaut proposé, fixé par la tâche 122) ;
`REALITY_MAX_CORRECTIONS: int = 3` (borne de sûreté, aucune mesure derrière).

### 4.6 Écran « En partie » (tâche 127)

`src/client/en_partie.py`, `templates/partials/en_partie_stage.html` : sous l'en-tête du face-à-face, une ligne d'état
selon `reality.state`, dite en français et sans jargon :

- `ok` : « Postes vérifiés en partie : 10 sur 10 conformes » ;
- `corrected` : « Postes corrigés en partie : Ahri (bas, prédit milieu)… Face-à-face et build recalculés » ;
- `partial` : « Postes adverses non lus en partie : analyse de la draft conservée » ;
- aucune charge `reality` : rien n'est ajouté (l'écran d'avant).

Les lignes du tableau dont un des deux champions est corrigé portent la marque « poste corrigé ». Le bloc build reprend
`loadout` tel que la nouvelle charge le porte ; les substitutions du duel citent le vrai adversaire.

### 4.7 Tests

Hermétiques (`tests/conftest.py`, faux LCU, fixtures) : aucun test n'ouvre le vrai client LoL, `data/db.db`, ni
`logs/`. Fichiers : `tests/test_reality_check.py` (résolution des noms, relevés complets, partiels, ambigus,
comparaison, `step()` avec faux moniteur et faux bus), `tests/test_client_ingame.py` (`roster_of` sur la fixture du
spike, sans identité), `tests/test_loadout_import.py` (`retarget` n'appelle pas `apply_build`, `_import` inchangé),
`tests/test_client_en_partie.py` (les quatre états de la ligne, le marquage des lignes). Fixtures dérivées des
relevés de la tâche 122, noms remplacés.

## 5. Tâches

Numéros globaux : à la suite de la tâche 121 de `TODO.md`.

| # | Tâche | Pts | Dépend de |
|---|---|---|---|
| 122 | Spike : `scripts/spike_live_positions.py`, relevé de 3 parties par @pj35, §4.1 et constantes | 3 | — |
| 123 | `roster_of` dans `LiveGame` et le sujet `ingame`, tests | 2 | — |
| 124 | `reality_check.py` : `resolve_champions`, `real_lanes`, `compare`, tests | 5 | — |
| 125 | `LoadoutImporter.retarget` (calcul sans écriture), `_import` inchangé, tests | 3 | — |
| 126 | `RealityCheck.step` : stabilité, recalcul de l'analyse et de la build, republication, console, remise à zéro, appel dans `monitor_loop` | 5 | 122, 123, 124, 125 |
| 127 | Écran « En partie » : ligne d'état, marquage des lignes corrigées, `FinalAnalysis.reality` | 3 | 126 |
| 128 | Clôture : `CHANGELOG.md`, statut, `docs/specs/README.md`, `docs/PROJECT_STRUCTURE.md`, recette @pj35 | 2 | 127 |

## 6. Critères d'acceptation

1. `python -m pytest tests/ -v` vert, avec les tests des tâches 123 à 127.
2. `python -m pytest tests/test_reality_check.py -v` vert : une équipe adverse permutée (milieu / bas) est détectée et
   recalculée ; une équipe au relevé incomplet ne l'est pas ; un relevé déjà traité n'est pas recalculé ; au plus
   `REALITY_MAX_CORRECTIONS` recalculs ; `step()` ne lève pas quand le bus, le roster ou l'évaluateur manquent.
3. Noms de champions : Wukong (`MonkeyKing`), Nunu & Willump, Renata Glasc, Lee Sin, Twisted Fate sont résolus par
   `resolve_champions` ; un nom inconnu est `unverified`, jamais rattaché à un autre champion.
4. `python -m pytest tests/test_client_ingame.py -v` : `roster_of` sur `allgamedata_items.json` renvoie dix entrées
   sans `summonerName` ni `riotId`.
5. `python -m pytest tests/test_loadout_import.py -v` : `retarget` ne fait aucun appel à `apply_build` ni au LCU, et les
   tests existants d'`_import` passent sans modification.
6. `python -m pytest tests/test_client_en_partie.py -v` : les états `ok`, `corrected`, `partial` et l'absence de `reality`
   s'affichent comme au §4.6 ; une ligne du face-à-face dont le champion est corrigé porte « poste corrigé ».
7. Aucune requête SQL nouvelle (la spec ne touche pas la base) ; `git grep -n "REALITY_" src/` ne trouve les seuils que
   dans `src/config_constants.py`.
8. Pas de migration : `python -m alembic upgrade head` n'a rien à appliquer pour cette spec.
9. `CHANGELOG.md` (`[Unreleased]`), statut de cette spec et `docs/specs/README.md` à jour.

**Vérification de bout en bout** (recette @pj35, partie réelle, Live Coach et client ouverts) : en champ select, forcer un
faux poste avec la commande du Live Coach (`r <champion> <lane>`, SPEC-04 B5) sur un champion adverse ; une fois la
partie lancée et le relevé stable, la console affiche `[ALERTE] Postes corrigés en partie : …`, l'écran « En partie »
montre la ligne « Postes corrigés » et le tableau recalculé, et la build cite le vrai vis-à-vis. Sans poste forcé, une
draft juste affiche `[OK] Postes vérifiés en partie : 10/10 conformes`.

## 7. Hors périmètre

- ❌ Corriger la ligne `predictions` de la partie avec les vrais postes, ou la retirer de la calibration : une
  prédiction à postes faux salit le jeu de calibration de SPEC-08. À proposer après usage, avec le chiffre de
  l'inférence adverse (§1) comme argument.
- ❌ Persister le constat (taux de réussite de l'inférence adverse par champion et dans le temps) ou le comparer à
  l'écran de fin après la partie. Même remarque.
- ❌ Améliorer `infer_team_roles` d'après ce qu'on aura vu : un chantier à part, mesuré sur ces données.
- ❌ Changer les runes, les sorts ou la page de runes du client LoL en partie : impossible, et hors lecture seule.
- ❌ Recalculer l'analyse depuis `allPlayers` quand le Live Coach n'a pas vu la draft (SPEC-24 §2).
- ❌ Overlay `tkinter` de SPEC-20 : inchangé.
