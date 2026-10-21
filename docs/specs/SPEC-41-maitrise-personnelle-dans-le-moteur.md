# SPEC-41 — Maîtrise personnelle dans le moteur de draft

**Statut** : 🟢 Validée par @pj35 le 2026-10-21 (tous les arbitrages de §2).

**Origine** : @pj35, 2026-10-21 : « J'aimerais qu'on ajoute un degré d'analyse au moteur, pour qu'il soit plus
corrélé à mes performances personnelles, et moins à des stats globales prises sur Internet. Par exemple, je suis
plutôt mauvais sur Gnar, donc le coach ne devrait pas me conseiller de le jouer, à moins que le pick fasse une vraie
différence. »

**Effort** : ~3 j, 8 tâches (§5), dont 4 conditionnelles à la mesure (phase B).

---

## 1. Constat

Mesures du 2026-10-21, lecture seule de `data/db.db` et `data/crawl.db` (script jetable, hors dépôt).

- **Le moteur ne connaît que LoLalytics.** `GameEvaluator` (`src/analysis/game_eval.py`) somme des paires
  matchup et synergie Master+. La recherche (`src/draft/search.py:319`), le grimoire
  (`src/draft/recommendations.py:189`), l'analyse finale (`src/draft/final_analysis.py:369`) et le blind pick
  (`src/draft/automation.py:150`, winrate de lane rétréci) n'ont aucune entrée sur le joueur. Le seul choix
  personnel est le pool (`current_pool`). Un champion du pool est donc classé comme s'il était joué par un
  Master+ moyen.
- **Les données personnelles existent déjà.** `game_records` compte 154 parties SoloQ (file 420) de @pj35, du
  2026-09-24 au 2026-10-20, et 151 ont leurs impacts ΔP (SPEC-20, `game_impact`, 53 181 lignes). Le champion du
  joueur est dans `game_metrics` (`is_player = 1`, 151 parties, 17 champions). L'historique LCU ne sert que
  20 parties (SPEC-19 §3.4, testé pour `endIndex` de 20 à 200 depuis `begIndex = 0`). La pagination par
  `begIndex` ≥ 20 n'a jamais été testée.
- **Le winrate ne voit pas Gnar, l'impact si.** Sur ses 5 parties, Gnar fait 3 victoires (prédit 2,6 par la draft,
  résidu +0,4), mais un impact moyen de **−10,5 pts de win chance par partie** contre +0,2 sur tous ses champions.
  Impact par partie, tous champions : écart-type 16,3 pts. La victoire, elle, a un écart-type de 50 pts dont neuf
  joueurs sur dix ne dépendent pas de lui : l'impact est le signal le moins bruité.

  | Champion | Parties | Écart à sa moyenne (brut) | Rétréci (K = 13,5) |
  |---|---|---|---|
  | Ambessa | 30 | −4,3 | −3,0 |
  | Olaf | 23 | +9,0 | +5,7 |
  | Yorick | 22 | +3,0 | +1,9 |
  | Sion | 15 | −6,6 | −3,5 |
  | Shen | 14 | −2,9 | −1,5 |
  | Malphite | 8 | +12,2 | +4,5 |
  | Gnar | 5 | −10,5 | −2,8 |
  | Dr. Mundo | 3 | −16,5 | −3,0 |

  Méthode des moments sur les 150 parties : écart-type **réel** entre ses champions de 4,4 pts (au-delà du bruit),
  donc K = σ² / τ² ≈ 13,5 parties. C'est le même ordre que la draft elle-même (p10-p90 de 45 à 55 %, TODO.md
  « A priori de la draft écarté ») : un terme personnel ne submerge pas la draft, il la départage.
- **Sur 141 parties, le gain ne se mesure pas.** Les prédictions labellisées et rattachées à une partie
  (`predictions.game_id`), avec le terme rétréci calculé sans la partie prédite : Brier 0,2496 (draft seule) contre
  0,2502 (draft + terme). L'échantillon est trop petit pour trancher dans un sens ou dans l'autre.
- **`crawl.db` permet de mesurer sur des tiers.** La collecte lit 20 parties complètes, timeline comprise, de
  chaque joueur visité (SPEC-33 §1 : 5 239 joueurs vus 20 fois ou plus). `crawl_histories` contient 39 364 joueurs,
  dont 32 601 avec 10 parties SoloQ ou plus, et **35 760 couples (joueur, champion) à 5 parties ou plus** (14 019
  à 10 ou plus). `impacts` coûte 11 ms par partie, décompression comprise (SPEC-35 §4.5,
  `MONEYBALL_IMPACT_SAMPLE`), soit ~15 min pour 80 000 parties.

## 2. Objectif et arbitrages

Ajouter au moteur un terme de maîtrise personnelle par champion, tiré de l'impact ΔP de @pj35 et rétréci vers 0.
Il ne s'applique que s'il améliore, sur des joueurs tiers, la prédiction de la draft au-delà de LoLalytics.

| Sujet | Décision |
|---|---|
| Signal | **Validé (@pj35, 2026-10-21)** : impact ΔP de SPEC-20, somme par partie des lignes du joueur dans `game_impact`. Le résidu de victoire est écarté parce que trop bruité (§1). |
| Validation | **Validé (@pj35, 2026-10-21)** : étude sur `crawl.db` d'abord (phase A). Le terme n'entre dans le moteur que si l'étude l'adopte (phase B conditionnelle), comme le terme de forme de SPEC-33. |
| Seuil d'adoption | **Validé (@pj35, 2026-10-21)**, figé avant la mesure : validation croisée à 5 blocs **de joueurs** ; le coefficient du terme et le gain de Brier ont chacun un IC95 bootstrap (rééchantillonnage par joueur) qui exclut 0. Le coefficient mesuré devient la conversion ΔP → logit (`MASTERY_LOGIT_PER_POINT`). |
| Forme | **Validé (@pj35, 2026-10-21)** : terme additif dans le logit de **mon** pick. « Sauf si le pick fait une vraie différence » en découle : Gnar repasse en tête dès que son avantage de draft dépasse sa pénalité. Pas de marge de confort (réglage deviné de plus). |
| Référence | **Validé (@pj35, 2026-10-21)** : tranchée par l'étude. (a) écart à ma moyenne tous champions ; (b) le même écart, moins la norme ΔP du champion sur `crawl.db`, c'est-à-dire le biais d'attribution propre au champion. On garde la variante au meilleur Brier, et (a) si l'écart entre les deux n'est pas significatif. |
| Rétrécissement | Décision de la spec : `offset = (moyenne_c − référence) × n / (n + K)`, K mesuré par l'étude (méthode des moments sur la population, plus stable que sur 150 parties). Le K de @pj35 est imprimé pour comparaison. |
| Champion jamais joué | **Validé (@pj35, 2026-10-21)** : terme 0, la carte dit « aucune partie ». Pas de pénalité d'inexpérience (§7). |
| Récence | **Validé (@pj35, 2026-10-21)** : toutes les parties pèsent pareil, pas de fenêtre ni de décroissance. |
| Files | **Validé (@pj35, 2026-10-21)** : SoloQ (420) seule. |
| Périmètre | **Validé (@pj35, 2026-10-21)** : classement de draft (recherche, cartes, console, auto-hover), grimoire, analyse finale, blind pick initial. Le conseil d'échange de rôles (`swap_advice.py`) n'est pas concerné (§7). |
| Affichage | **Validé (@pj35, 2026-10-21)** : la victoire affichée inclut le terme, avec la part de la maîtrise en sous-ligne : « dont toi sur Gnar : −2,8 pts (5 parties) ». |
| Historique ancien | **Validé (@pj35, 2026-10-21)** : spike LCU de la pagination (`begIndex` ≥ 20), puis rattrapage si elle répond. **Validé (@pj35, 2026-10-21)** : les parties rattrapées vont dans `game_records`, la table de la capture. Le coaching (bilan, tendances) les voit donc aussi, comme des parties plus anciennes. L'alternative, une table à part qui ne servirait qu'à ce terme, est écartée. |
| Prédiction journalisée | **Validé (@pj35, 2026-10-21)** : la probabilité **affichée** de l'analyse finale inclut le terme. La prédiction **journalisée** (`predictions.predicted_probability`) reste la draft seule, sous `MODEL_VERSION` inchangé. Sinon l'écran Calibration (SPEC-39) absorberait la maîtrise dans le facteur d'échelle de `K_MATCHUP`, et le compteur de 100 issues repartirait de zéro. |

## 3. Approches considérées

| Approche | Pour | Contre |
|---|---|---|
| **A. Terme additif par champion, mesuré sur `crawl.db` puis appliqué (retenue)** | Une seule échelle (logit) avec la draft. Le coefficient et K sont mesurés, pas devinés. Le seuil est figé avant la mesure. | Une étude de ~15 min de calcul avant tout effet visible ; peut conclure « non adopté » |
| B. Terme additif appliqué d'emblée, K mesuré sur les 150 parties de @pj35 | Effet immédiat | Conversion ΔP → logit supposée 1:1 ; la mesure du §1 ne voit aucun gain ; contraire à la règle « pas d'heuristique sans métrique » |
| C. Filtre du pool : retirer les champions à maîtrise négative sous un seuil | Trivial | Seuil arbitraire ; perd « sauf si le pick fait une vraie différence » ; Gnar disparaît même en contre parfait |

## 4. Détail

### 4.1 Module `src/analysis/mastery.py` (nouveau, tâche 196)

Fonctions pures, sans base, réutilisées par l'étude (tâche 199) et par le moteur (tâche 200).

```python
@dataclass(frozen=True)
class Mastery:
    champion: str        # nom tel que le pool et l'évaluateur l'écrivent
    games: int
    raw_points: float    # moyenne ΔP du champion − référence, en points de win chance
    points: float        # rétréci : raw_points × games / (games + k)

def shrink_k(groups: Mapping[str, Sequence[float]]) -> Optional[float]:
    """K = σ² / τ² par la méthode des moments (variance intra-groupe σ², inter-groupe τ²) ; None si τ² ≤ 0."""

def masteries(games: Sequence[Tuple[str, float]], k: float,
              norms: Optional[Mapping[str, float]] = None) -> Dict[str, Mastery]:
    """Une Mastery par champion depuis (champion, ΔP de la partie en points). Référence : moyenne de toutes les
    parties (variante a) ; avec `norms`, on retranche en plus la norme du champion (variante b)."""
```

Tests (`tests/test_mastery.py`) : groupes synthétiques à τ connu, où K retrouvé est à ±20 % sur 2 000 tirages à
graine fixe ; τ² nul → None ; un champion à 0 partie est absent du dict ; rétrécissement monotone en n ; la variante
b retranche bien la norme.

### 4.2 Spike et rattrapage de l'historique (tâches 197 et 198)

`scripts/spike_lcu_history_pages.py` (lecture seule, client LoL ouvert, hors partie) :
`/lol-match-history/v1/products/lol/current-summoner/matches?begIndex=B&endIndex=B+19` pour B = 0, 20, 40… jusqu'à
une page vide ou 500. Il imprime par page le nombre de parties, la plus ancienne date et les files, puis le détail
et la timeline de la plus ancienne partie servie. Résultat consigné en §8.

**Si des pages au-delà de 20 répondent** (tâche 198) : `scripts/backfill_own_games.py` range les parties SoloQ
absentes de `game_records` par le chemin de la capture (`src/coaching/capture.py`, `_match_from_detail` et
l'écriture de `capture_recent`, factorisés si besoin, sans changer leur comportement). Les impacts suivent par
`games_without_impact` au prochain passage. Sinon la tâche 198 est abandonnée, et l'historique grossit d'environ
5 parties par jour.

### 4.3 Étude `scripts/measure_mastery_term.py` (tâche 199)

Lecture seule de `crawl.db` et `db.db`, modèle de partie de `load_model` (comme `measure_moneyball.py`), parties où
@pj35 joue exclues (`_has_player`).

1. Parties lues de file 420, dix postes connus (`participant_roles`). Pour chaque participant : ΔP de la partie
   (somme de ses lignes `impacts(...)["rows"]`), champion, victoire, `puuid`.
2. **Joueurs focaux** : `puuid` avec au moins `MASTERY_STUDY_MIN_GAMES` parties lues. Pour chacune de leurs
   parties : `offset` du champion joué, calculé par `masteries` sur **ses autres** parties (la partie prédite
   exclue), K estimé sur les blocs d'entraînement.
3. Logit de draft de la partie, vu de son équipe : `GameEvaluator(db).team_logit(alliés, ennemis)`, lanes
   données par `participant_roles`.
4. Logistique `victoire ~ a · logit_draft + b · offset` contre `victoire ~ a · logit_draft`, validation croisée
   à 5 blocs de joueurs (un joueur n'est jamais à la fois en entraînement et en test), puis Brier poolé. IC95 de
   `b` et du gain de Brier par bootstrap sur les joueurs (`MASTERY_STUDY_BOOTSTRAP` tirages).
5. Les deux références du §2 (a, puis b avec la norme par champion calculée sur les participants non focaux des
   blocs d'entraînement), sur les mêmes blocs.
6. Sortie : parties et joueurs retenus, K, `b` et son IC95, Brier des deux modèles, gain et son IC95, décision
   `[OK] Adopté (variante x)` ou `[INFO] Non adopté`, puis K de @pj35 et sa table du §1 recalculée. Résultat
   consigné en §8 par la tâche 199.

Fonctions de logistique, de validation croisée et de Brier : celles de `src/coaching/moneyball.py` (`_fit`,
`_cross_validate`, `_brier`), rendues publiques si besoin, plutôt qu'une copie.

### 4.4 Le terme dans le moteur (phase B, tâches 200 à 202, si la tâche 199 l'adopte)

- **Chargement** : `MasteryTerm` (dans `mastery.py`) lit les parties SoloQ du joueur (ΔP par partie,
  `game_impact` × `game_records.player_participant_id` ; champion, `game_metrics.is_player = 1`) avec SQL
  paramétré, et applique `masteries` avec `MASTERY_K` (et les normes si la variante b est retenue). Méthodes :
  `logit(name) -> float` (0 si inconnu), `points(name) -> float` = `100 × (sigmoid(logit) − 0,5)`, et
  `games(name) -> int`. Il est porté par le monitor (`self.m.mastery`) et rechargé à l'entrée du champ select.
  Toute erreur donne un terme vide, avec `[ALERTE]` en verbose : la draft n'est jamais interrompue.
- **Recherche** (`search.py`) : `DraftSearch.rank(..., personal: Callable[[str], float] = lambda _: 0.0)`. Dans
  `_rank_at_depth`, la contribution de chaque coup racine (mon pick) reçoit `+ personal(move[0])`. Les nœuds
  internes ne changent pas, puisque mon pick n'est joué qu'à la racine. `SearchResult` gagne
  `personal_points: float = 0.0`.
- **Grimoire** (`_fill_candidates`) : `sigmoid(team_logit(alliés + [moi], ennemis) + mastery.logit(name))`.
- **Analyse finale** : la probabilité affichée ajoute `mastery.logit` de mon champion verrouillé. La prédiction
  journalisée reste la draft seule (§2).
- **Blind pick** (`automation.py`) : score = winrate de lane rétréci + `mastery.points(name)`, les deux en points.
- **Console** : `_print_results` ajoute ` · toi −2,8 pts (5 parties)` quand le terme est non nul.
- **Client** : `SnapshotRecommendation` gagne `personal_points: Optional[float]` et `personal_games: int`, et
  `draft_view.recommendations` ajoute à la sous-ligne « dont toi sur Gnar : −2,8 pts (5 parties) ». Sans partie,
  « aucune partie sur Gnar ».

### 4.5 Constantes (`src/config_constants.py`, `AnalysisConfig`)

| Constante | Valeur | Origine |
|---|---|---|
| `MASTERY_STUDY_MIN_GAMES` | 10 | Assez de parties **lues** pour un offset sans la partie prédite ; 5 239 joueurs en ont 20 ou plus dans `crawl_games` (SPEC-33 §1), le compte à 10 est imprimé par l'étude |
| `MASTERY_STUDY_BOOTSTRAP` | 1 000 | Ordre de grandeur des IC95 bootstrap de SPEC-35 |
| `MASTERY_LOGIT_PER_POINT` | mesuré (tâche 199) | Coefficient `b` de l'étude |
| `MASTERY_K` | mesuré (tâche 199) | K de la population ; 13,5 pour @pj35 au 2026-10-21, pour comparaison |
| `MASTERY_QUEUE_IDS` | `(420,)` | §2, Files |

## 5. Tâches

| # | Tâche | Pts | Dépend de |
|---|---|---|---|
| 196 | `src/analysis/mastery.py` : `Mastery`, `shrink_k`, `masteries` (variantes a et b) + tests §4.1 | 3 | — |
| 197 | Spike `scripts/spike_lcu_history_pages.py` (pagination `begIndex` ≥ 20, détail et timeline de la plus ancienne), résultat en §8 | 1 | — |
| 198 | *Conditionnelle (197)* : `scripts/backfill_own_games.py` par le chemin de la capture, test sur faux LCU | 3 | 197 |
| 199 | `scripts/measure_mastery_term.py` (§4.3), seuil figé, constantes d'étude, résultat et décision en §8 | 5 | 196 |
| 200 | *Conditionnelle (199)* : `MasteryTerm`, chargement au champ select, terme à la racine de la recherche, `SearchResult.personal_points`, console, constantes mesurées + tests | 3 | 199 |
| 201 | *Conditionnelle (199)* : grimoire, analyse finale (affichée seulement), blind pick + tests | 3 | 200 |
| 202 | *Conditionnelle (199)* : snapshot et sous-ligne des cartes « dont toi sur X » + tests | 2 | 200 |
| 203 | Clôture : critères du §6, `CHANGELOG.md`, statut de la spec et de `docs/specs/README.md`, `TODO.md` | 1 | 199 (et 202 si adoptée) |

## 6. Critères d'acceptation

1. `python -m pytest tests/ -v` vert, avec les tests des tâches ci-dessus.
2. `python -m pytest tests/test_mastery.py -v` : K retrouvé à ±20 % sur données synthétiques, τ² nul → `None`,
   rétrécissement monotone, variante b qui retranche la norme.
3. `python scripts/spike_lcu_history_pages.py` imprime une ligne `[DATA]` par page, et §8 consigne la profondeur
   servie.
4. `python scripts/measure_mastery_term.py` (Live Coach fermé) imprime K, `b` et son IC95, le Brier des deux
   modèles, le gain et son IC95, puis une ligne de décision `[OK] Adopté` ou `[INFO] Non adopté`. §8 consigne la
   sortie, et le seuil du §2 n'a pas changé depuis la rédaction (`git log -p` de cette spec).
5. *Si adopté* : un test de `search.py` montre qu'un candidat à maîtrise négative, premier sans le terme, passe
   derrière un autre quand `−personal` dépasse l'écart de leurs logits, et reste premier sinon (« sauf si le pick
   fait une vraie différence »).
6. *Si adopté* : un test du grimoire et un test de l'analyse finale vérifient que la probabilité affichée est
   `sigmoid(logit_draft + terme)`, et que `insert_prediction` reçoit toujours la probabilité de la draft seule.
7. *Si adopté* : `MasteryTerm` sur une base sans `game_impact` donne un terme vide sans exception, et une
   exception levée dans le chargement ne sort pas de la boucle de draft (test de régression du monitor).
8. *Si adopté* : `draft_view.recommendations` produit « dont toi sur Gnar : −2,8 pts (5 parties) » sur un
   snapshot de test, et « aucune partie sur X » à 0 partie.
9. `CHANGELOG.md` (`[Unreleased]`), statut de cette spec, `docs/specs/README.md` et `TODO.md` à jour.

**Vérification de bout en bout** : l'étude (critère 4) tranche. Si elle adopte le terme, il reste une draft réelle
de @pj35 avec Gnar dans le pool : la carte de Gnar porte « dont toi sur Gnar », et Gnar ne passe devant un autre
champion du pool que si sa victoire immédiate le dépasse encore une fois le terme compté.

## 7. Hors périmètre

- ❌ Pénalité d'inexpérience pour un champion jamais joué (§2) : c'est une autre mesure, à ouvrir si le grimoire
  pousse trop de champions hors pool.
- ❌ Maîtrise par (champion, lane) : 154 parties presque toutes au top, le découpage n'aurait pas d'échantillon.
- ❌ Maîtrise par matchup (moi sur Gnar contre Darius) : quelques parties par case, du bruit pur.
- ❌ Conseil d'échange de rôles (`swap_advice.py`) : il compare des affectations d'alliés, ma maîtrise sur un
  autre poste n'est pas mesurée.
- ❌ Maîtrise des alliés et des ennemis (forme des joueurs en draft) : c'est SPEC-33, en partie et sans lecture
  pendant la draft.
- ❌ Parties Flex, normales ou ARAM (§2).
- ❌ Points de maîtrise du client (`/lol-champion-mastery`) : ils comptent le temps de jeu, pas le niveau.

## 8. Résultats

*Spike de la pagination (tâche 197) et mesure du terme (tâche 199) : à remplir.*
