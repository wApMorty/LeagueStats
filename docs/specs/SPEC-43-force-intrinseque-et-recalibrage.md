# SPEC-43 — Force intrinsèque dans le moteur, recalibrage sur `crawl.db`

**Statut** : 🟡 Rédigée le 2026-10-25, arbitrages de §2 validés par @pj35 le 2026-10-25.

**Origine** : @pj35, 2026-10-25 — « Il y a définitivement un problème avec l'algorithme de recommandation de
champions. Je viens de me retrouver à pick Olaf dans une game catastrophique pour mon champion. […] trouve-moi une
solution. » Rouvre SPEC-18 phase B (§3 de SPEC-18), dont le critère de réouverture est rempli (§1.3).

**Effort** : ~2,5 jours, 6 tâches, 15 pts (§5).

---

## 1. Constat

### 1.1 La partie d'Olaf n'est pas une erreur du moteur (mesuré le 2026-10-25)

Prédiction 257 (`predictions`, partie 8024348841) : Olaf top, avec Locke, Taliyah, Jinx et Braum, contre Jayce,
Master Yi, Ahri, Kai'Sa et Nautilus. P prédite 0,551, défaite en 33 min. Bilans : Olaf 6/12, Braum 2/13, Jinx 3/11.

Classement de la pool « Top playable » rejoué sur cette draft avec `GameEvaluator.contribution` et `MasteryTerm` :
Olaf 1er (+5,5 pts), dont draft −0,4 pt (duel contre Jayce −0,1 pt) et maîtrise +5,9 pts (39 parties, 59 % de
victoires). Avec le modèle corrigé de §1.3, Olaf reste 1er (+6,3), à égalité avec Malphite (+6,2). SPEC-42 avait
déjà relevé que la maîtrise d'Olaf domine la draft. Le défaut est ailleurs, et il est systémique.

### 1.2 Les 243 parties labellisées ne peuvent pas trancher

`scripts/compare_intrinsic_strength.py` sur les 243 prédictions labellisées : AUC 0,558 → 0,585 avec la force
intrinsèque, gain +0,027, IC 90 % [−0,022 ; +0,075]. Il faudrait des milliers de parties.

### 1.3 Backtest sur `crawl.db` : 96 987 parties classées (2026-10-25)

Parties lues de `crawl.db` (files 420 et 440, patchs 16.20 et 16.21, plus de 15 min), composition des deux
équipes, `blue_win`. Postes inférés par `champion_lanes` (meilleure permutation), Châtiment = jungle. Termes
calculés avec `GameEvaluator` et `_lane_strength` de `scripts/compare_intrinsic_strength.py`, régression logistique
(`mastery.fit_logistic`) en validation croisée à 5 plis, bootstrap sur 200 tirages. Script jetable de la session,
réécrit proprement en tâche 210.

| Modèle | AUC (CV) | Brier (CV) |
|---|---:|---:|
| Logit actuel seul (recalé par la régression) | 0,530 | 0,2492 |
| Force intrinsèque seule | 0,541 | — |
| Logit actuel + force | **0,552** | **0,2477** |
| Duel de lane, matchups hors lane, synergies, force, libres | 0,553 | 0,2477 |

- **Force intrinsèque** : gain d'AUC +0,022, IC 90 % [+0,019 ; +0,025]. La borne basse dépasse 0 : critère de
  SPEC-18 §3 rempli. `GameEvaluator` ne somme toujours que des paires (`src/analysis/game_eval.py:209-231`) ; le
  terme `Σ (winrate_base − moyenne)` de SPEC-05 §3.3 n'a jamais été implémenté.
- **Surconfiance** : le logit actuel reçoit un coefficient de 0,66 (0,70 une fois la force ajoutée). Ses écarts
  de probabilité sont environ 1,5 fois trop grands.
- **Coefficients libres**, ramenés aux unités de `config_constants` (`K_MATCHUP` = 1,0, `K_SYNERGY` = 0,5,
  `SAME_LANE_WEIGHT` = 2,0) : duel de lane 1,35 (soit 2 × 0,68), matchups hors lane 0,69, synergies 2,97 × 0,5 ≈
  1,49, force 0,82 point de victoire par point de winrate de lane. Le rapport 2 entre la lane et le reste est
  confirmé ; `K_MATCHUP` ≈ 0,69, `K_SYNERGY` ≈ 1,49, `K_INTRINSIC` ≈ 0,82 (valeurs provisoires, fixées en 210).
- **Plafond** : la draft seule plafonne vers 0,55 d'AUC. C'est l'ordre de grandeur de la littérature : 54 % de
  précision sans données joueur (thèse CVUT, *Drafting in MOBA Games using Machine Learning*), 75 % avec
  l'expérience joueur-champion (Do et al., arXiv 2108.02799).

Réserves : environ 3 000 parties sont perdues à cause d'une copie à chaud de `crawl.db` (pages abîmées). Les
winrates de lane sont ceux de la base actuelle, pas ceux du jour de la partie. La fuite de données est négligeable
(les parties du crawl pèsent peu dans les agrégats LoLalytics Master+).

### 1.4 Un `calibration.json` périmé écraserait le nouveau modèle

`apply_overrides` (`src/calibration_overrides.py:65-70`) pose `K_MATCHUP`, `K_SYNERGY` et `MODEL_VERSION` sans
comparer la version du fichier à celle du code. Un fichier `spec13-v1+cal1` resterait donc en vigueur après le
passage à `spec43-v1`. Aujourd'hui aucun fichier n'existe (vérifié le 2026-10-25), mais « Appliquer » (SPEC-39) en
crée un.

## 2. Objectif et arbitrages

Le logit de draft somme la force intrinsèque de chaque champion en plus des paires. Ses trois coefficients sont
ajustés sur `crawl.db` par un script de backtest, qui devient le critère de toute modification future du modèle.

| Sujet | Décision |
|---|---|
| Où vivent les coefficients | **Validé (@pj35, 2026-10-25)** : dans `src/config_constants.py`, avec leur origine en commentaire. Le script les affiche, on les recopie à la main. `MODEL_VERSION` passe à `spec43-v1`. |
| Calibration perso de SPEC-39 | **Validé (@pj35, 2026-10-25)** : conservée. Le facteur d'échelle s'applique aussi à `K_INTRINSIC`, nouvelle clé de `calibration.json` ; un fichier sans cette clé reste lisible. |
| Quand tourne le backtest | **Validé (@pj35, 2026-10-25)** : script manuel, `scripts/backtest_draft_model.py`. Il est obligatoire avant tout changement de `game_eval.py` ou des K, et à relancer après une mise à jour des données. Pas de lancement automatique (décision tranchée). |
| Synergies | **Validé (@pj35, 2026-10-25)** : les trois coefficients sont ajustés ensemble par une seule régression et adoptés tels quels. |
| Règle d'adoption | Ajout ou retrait d'un terme : adopté si la borne basse de l'IC 90 % du gain d'AUC dépasse 0 (règle de SPEC-18). Simple recalibrage : adopté si l'IC 90 % du gain de Brier exclut 0 (l'AUC est aveugle à l'échelle). |
| Champion sans lane connue | Force lue dans le winrate toutes lanes (`shrunk_lane_winrates(db, None)`), comme les paires qui se replient sur la table toutes lanes (`game_eval.py:83-95`). Un champion sans données vaut 0. |
| Maîtrise de SPEC-41 | Son coefficient a été ajusté contre l'ancien logit. L'étude est relancée en 213 ; `MASTERY_LOGIT_PER_POINT` ne change que s'il sort de son IC95 [0,060 ; 0,084]. |
| `calibration.json` périmé | Ignoré, avec un `[INFO]`, quand sa version sans le suffixe `+calN` diffère de `MODEL_VERSION` dans le code. |

## 3. Approches considérées

1. **Terme par champion dans `GameEvaluator.contribution`** (retenue). La force d'un champion est un terme à un
   seul champion. Elle s'ajoute à sa contribution, une seule fois, au moment où il est posé. Les trois propriétés
   dont dépend la recherche tiennent par construction : antisymétrie (signe appliqué par l'appelant), décomposition
   et indépendance de l'ordre. Recherche, grimoire, analyse finale et prédiction journalisée en héritent sans
   modification.
2. **Terme ajouté hors de l'évaluateur, à la racine de la recherche**, comme la maîtrise de SPEC-41. Rejetée : la
   maîtrise n'existe que pour mon pick, alors que la force vaut pour les dix champions, ennemis compris. Hors de
   l'évaluateur, le minimax ne verrait pas qu'un adversaire peut prendre un champion fort.
3. **Remplacer le logit par un modèle appris** (régression sur les paires, boosting). Rejetée pour ce lot : il
   faudrait des centaines de milliers de parties pour apprendre ~25 000 paires par lane, alors que LoLalytics les
   mesure déjà. Le gain au-delà de 0,553 n'est pas démontré (le modèle à 4 termes libres ne gagne que +0,0007).

## 4. Détail

### 4.1 `src/analysis/game_eval.py` (tâche 209)

- Nouvelle table paresseuse `self._strength: Dict[str, Dict[str, float]]`, par lane (clé `ALL_LANES_KEY` pour
  `None`) : `{nom en minuscules: winrate rétréci − moyenne pondérée de la lane}`, construite comme `_lane_strength`
  de `scripts/compare_intrinsic_strength.py` (lignes 50-62), à partir de `shrunk_lane_winrates`. Chargée par
  `_table`-like à la première demande et par `warm()`.
- `def intrinsic_logit(self, champion: Placed) -> float` : `winrate_points_to_logit(strength *
  analysis_config.K_INTRINSIC)`, 0.0 sans données.
- `contribution()` ajoute `self.intrinsic_logit(champion)` à son total. `team_logit()` reste inchangée : elle passe
  par `contribution()`.
- Docstring de module : formule complétée par `+ K_INTRINSIC · Σ_i (f(i) − f̄_lane) − K_INTRINSIC · Σ_j (…)`.
- Tests (`tests/test_game_eval.py`) : antisymétrie et indépendance de l'ordre avec un terme de force non nul ;
  `contribution` d'un champion seul = sa force ; repli toutes lanes quand la lane est `None` ; champion inconnu = 0.

### 4.2 `scripts/backtest_draft_model.py` (tâche 210, nouveau)

- Lecture seule de `crawl.db` (`_open_ro` de `scripts/measure_moneyball.py`, `crawl_path()`) et de `db.db`.
  Parties lues, `queue_id` dans `BACKTEST_QUEUE_IDS`, durée ≥ `BACKTEST_MIN_DURATION_S`, `blue_win` connu. Postes
  par `src.coaching.metrics.participant_roles` (rôle d'objet, Châtiment, élimination) ; une partie avec un poste
  `None` est écartée et comptée. Une erreur `sqlite3.DatabaseError` sur une ligne fait sauter la ligne, comptée elle
  aussi.
- Fonctions pures testables : `game_terms(evaluator, blue, red) -> Terms` (duel de lane, matchups hors lane,
  synergies, force, chacun en logit à K = 1, et logit en vigueur), `cross_validate(rows, columns, folds, seed)`
  (prédictions hors pli), `auc(scores, outcomes)` par les rangs (O(n log n) ; `calibration.auc` est O(n²)),
  `bootstrap_gain(...)` (IC 90 %).
- Sortie console : nombre de parties (lues, écartées, retenues) ; AUC et Brier en CV du modèle en vigueur (un seul
  coefficient, qui doit valoir 1 s'il est calibré) et du modèle à coefficients libres ; IC 90 % du gain d'AUC et du
  gain de Brier ; K ajustés dans les unités de `config_constants` (coefficient × K en vigueur) ; verdict selon la
  règle de §2.
- Options : `--limit N` (parties les plus récentes), `--crawl-path`, `--db-path`.
- Constantes (`analysis_config`) : `BACKTEST_QUEUE_IDS = (420, 440)`, `BACKTEST_MIN_DURATION_S = 900` (exclut les
  remakes et les abandons précoces, comme le script de §1.3), `BACKTEST_FOLDS = 5`, `BACKTEST_BOOTSTRAP = 200`,
  `BACKTEST_SEED = 43`.
- Tests (`tests/test_backtest_draft_model.py`) : sur données synthétiques à coefficients connus, la régression les
  retrouve ; `auc` identique à `calibration.auc` sur un petit jeu avec ex aequo ; ligne avec poste `None` écartée.
- Résultat de la mesure consigné en §8 de cette spec.

### 4.3 Constantes et version (tâche 211)

`src/config_constants.py`, `AnalysisConfig` : `K_MATCHUP`, `K_SYNERGY` et le nouveau `K_INTRINSIC` prennent les
valeurs de 210, avec leur origine en commentaire (nombre de parties, date). `MODEL_VERSION = "spec43-v1"`, avec une
ligne d'historique dans le commentaire existant. Conséquence connue : le compteur de calibration repart de 0 et la
pondération par lane restante (`lane_restante.py:50`) reste éteinte jusqu'à 30 parties labellisées (~1 semaine au
rythme actuel). Relancer 210 : le coefficient du modèle en vigueur doit contenir 1 dans son IC 90 %.

### 4.4 Calibration perso et `calibration.json` (tâche 212)

- `calibration_overrides.py` : `K_INTRINSIC` facultatif dans `_valid`, `load_overrides`, `save_overrides` (un
  fichier à deux K reste valide, `K_INTRINSIC` garde alors la valeur du code). `apply_overrides` ignore le fichier,
  avec un `[INFO]`, si `MODEL_VERSION` sans `+calN` diffère de la version du code.
- `calibration_notice.py` : `Proposal.k_intrinsic = K_INTRINSIC × scale`, `format_proposal` l'affiche,
  `apply_proposal` l'écrit et le pose.
- Client : `src/client/data.py:586-589` et `src/client/app.py:363-370` affichent `K_INTRINSIC` comme les deux
  autres.
- Tests : fichier à deux K lu ; fichier à trois K lu ; fichier `spec13-v1+cal1` ignoré sous `spec43-v1` ;
  proposition qui met les trois K à l'échelle.

### 4.5 Maîtrise (tâche 213)

`python scripts/measure_mastery_term.py` (~35 min) avec le nouveau logit. Si `b` reste dans [0,060 ; 0,084], rien
ne change ; sinon `MASTERY_LOGIT_PER_POINT` et son commentaire sont mis à jour, sans nouveau bump de version si
c'est fait avant la première prédiction `spec43-v1`. Le résultat est noté en §8.

### 4.6 Clôture (tâche 214)

- Suppression de `scripts/compare_intrinsic_strength.py`, remplacé par 210, et de `calibration.intrinsic_points`
  avec son test (`tests/test_analysis_calibration.py:111`), qui n'ont pas d'autre appelant.
- SPEC-18 : phase B marquée « reprise par SPEC-43 ». `docs/specs/README.md`, section « Conventions propres aux
  specs » : une ligne pour le critère permanent (`scripts/backtest_draft_model.py` avant tout changement du modèle
  de draft).
- `CHANGELOG.md`, `TODO.md`, statut de cette spec.

## 5. Tâches

| # | Tâche | Pts | Dépend de |
|---|---|---|---|
| 209 | `GameEvaluator` : terme de force intrinsèque dans `contribution`, `K_INTRINSIC` provisoire à 0,82 + tests | 3 | — |
| 210 | `scripts/backtest_draft_model.py` : backtest sur `crawl.db`, CV, IC 90 %, K ajustés + tests ; mesure en §8 | 5 | 209 |
| 211 | `config_constants` : K de 210, `MODEL_VERSION` `spec43-v1` ; 210 relancé, coefficient en vigueur ≈ 1 | 1 | 210 |
| 212 | `calibration.json` : `K_INTRINSIC`, garde de version périmée, SPEC-39 (console et client) + tests | 3 | 211 |
| 213 | Étude de maîtrise relancée sur le nouveau logit, `MASTERY_LOGIT_PER_POINT` revu si hors IC95 ; §8 | 2 | 211 |
| 214 | Clôture : suppression du script SPEC-18, SPEC-18, README des specs, `CHANGELOG.md`, `TODO.md` | 1 | 212, 213 |

## 6. Critères d'acceptation

1. `python -m pytest tests/ -v` vert, avec les tests de 209, 210 et 212.
2. `python -m pytest tests/test_game_eval.py -v` : antisymétrie et indépendance de l'ordre vérifiées avec un terme
   de force non nul.
3. `python scripts/backtest_draft_model.py` (config de 211) : AUC en CV du modèle en vigueur ≥ 0,545 (0,530 avant),
   et IC 90 % de son coefficient contenant 1,0.
4. Même commande : la sortie donne le nombre de parties lues, écartées (poste inconnu, ligne illisible) et
   retenues, les K ajustés et le verdict.
5. `grep -n "K_INTRINSIC\|spec43-v1" src/config_constants.py` : valeurs de §8 avec leur origine en commentaire.
6. Un `calibration.json` en `spec13-v1+cal1` placé à côté de l'exécutable est ignoré sous `spec43-v1` (test de
   212), et un fichier à deux K reste lisible.
7. `grep -rn "compare_intrinsic_strength\|intrinsic_points" src scripts tests` ne renvoie rien.
8. §8 rempli : mesure de 210 (avant et après 211) et résultat de 213.
9. `CHANGELOG.md` (`[Unreleased]`), statut de cette spec, SPEC-18, `docs/specs/README.md` et `TODO.md` à jour.

**Vérification de bout en bout** : rejouer la draft de la prédiction 257 (Olaf contre Jayce) avec la pool
« Top playable » sur la vraie base. La part « draft » de chaque champion inclut désormais sa force (Malphite
≈ +1,6 pt, Ambessa ≈ −1,8 pt, valeurs de §1.3 à confirmer avec les K de 211). Puis une draft réelle
au Live Coach : cartes et jauge cohérentes, prédiction journalisée sous `spec43-v1`.

## 7. Hors périmètre

- ❌ Afficher la force séparément sur les cartes de draft (« dont force du champion ») : non demandé. La sous-ligne
  « dont toi sur X » de SPEC-41 suffit pour l'instant.
- ❌ Modèle appris sur les paires (§3, approche 3) : le gain n'est pas démontré.
- ❌ Lancer le backtest automatiquement en fin de pipeline : écarté par @pj35 le 2026-10-25.
- ❌ Données de joueurs adverses ou alliés dans la prédiction de draft : déjà mesuré et refusé (terme de forme,
  SPEC-33, tâche 161).
- ❌ Tier list, blind pick, bans, Team Builder : ils utilisent déjà le winrate de lane rétréci (SPEC-18 phase A).

## 8. Résultats

*À remplir en 210, 211 et 213.*
