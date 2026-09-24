# SPEC-17 — Une recherche qui regarde les bons picks, et plus loin

**Statut** : 🟢 **Validée par @pj35 le 2026-09-24, approche A** (§3). Rien n'est implémenté.
Découpage : `TODO.md`, sprint 3 (tâches 21 à 26).

**Origine** : @pj35 — « Notre moteur Stockfish n'est pas assez performant : soit il regarde trop de
picks improbables, soit il a besoin de plus de puissance (peut-être ajouter du multi-threading pour
l'exploration ?) »

**Réponse courte** : les deux intuitions sont vraies, mais pas dans la même proportion. Le moteur
regarde surtout **les mauvais picks** : ses candidats adverses sont des champions que personne ne
joue. Le corriger, et donner aux alliés la lane que le client connaît déjà, fait gagner plus de
profondeur que 20 cœurs n'en apporteraient, sans ajouter de concurrence. Le multi-threading reste
une phase 2 conditionnelle (§5).

**Effort** : ~1 jour, phase 1, tests compris.

---

## 1. Constat, mesuré sur la base de production (2026-09-24)

Mesures faites sur une copie de `data/db.db` : pool de 20 mids parmi les plus joués, budget de 2 s
(`SEARCH_BUDGET_SECONDS`), ordre de draft SoloQ (B1 R1 R2 B2 B3 R3 R4 B4 B5 R5), notre lane
`middle`. Deux scénarios :

- **B1** : premier pick, 10 tours restants, board vide.
- **B2** : Jinx bot déjà pickée côté allié, Garen top et Lee Sin jungle côté ennemi, 7 tours
  restants.

### 1.1 Le générateur de coups propose des champions que personne ne joue

`CandidatePool._ranked()` (`src/draft/search.py:71`) classe les candidats de chaque lane par
`champion_scores.avg_delta2`, autrement dit par la tier list. Sur les données réelles, le haut de
cette tier list est occupé par des picks hors rôle à très faible échantillon :

| Lane | Top 8 actuel (par `avg_delta2`) | Part des games de la lane couverte par ces 8 | Part couverte par les 8 plus joués |
|---|---|---|---|
| top | Kassadin, Azir, Brand, Zoe, Kalista, Malzahar, Sylas, Rek'Sai | **1,7 %** | 27,3 % |
| jungle | Brand, Dr. Mundo, Rammus, Trundle, Amumu, Sion, Maokai, Malphite | **2,5 %** | 37,3 % |
| middle | Karthus, Smolder, Rumble, Heimerdinger, Malphite, Naafiri, Kennen, Morgana | **1,4 %** | 34,3 % |
| bottom | Cassiopeia, Brand, Swain, Ziggs, Seraphine, Yasuo, Veigar, Sivir | **7,0 %** | 56,5 % |
| support | Nidalee, Mel, Skarner, Poppy, Zyra, Zoe, Braum, Nautilus | **11,7 %** | 41,7 % |

(Popularité = somme de `matchups.games` par `(champion, lane)`. Kassadin top : 78ᵉ champion le plus
joué sur 82.)

Conséquence : la « meilleure réponse adverse » que le minimax anticipe est choisie parmi des
champions qui représentent 1 à 12 % des parties réelles. Les vrais contre-picks (ceux qu'un
adversaire joue effectivement) **ne sont jamais examinés**. Les variantes principales affichées le
montrent : `Kassadin top`, `Nidalee support`, `Brand jungle`, `Azir top`.

Ce n'est pas un défaut de l'évaluation : SPEC-13 écrase déjà ces paires à faible échantillon dans
`game_eval`. Le défaut est dans le **générateur** : il mélange deux questions. « Que pourrait
jouer l'adversaire ? » relève de la popularité. « Quel est son meilleur coup ? » relève du
minimax. En triant par force, le générateur répond à la seconde avec des données bruitées et
n'examine plus la première.

### 1.2 Les alliés sont modélisés comme s'ils pouvaient jouer n'importe quelle lane

`DraftSearch._moves()` (`src/draft/search.py:113`) : pour tout tour qui n'est pas celui du joueur,
les coups sont `SEARCH_TOP_N` candidats **par lane libre**, soit jusqu'à 5 × 8 = 40 coups. C'est
juste pour l'ennemi, dont l'`assignedPosition` est masquée. C'est faux pour nos alliés : le client
donne leur lane (`state.ally_positions`, rempli par `get_assigned_positions`,
`src/draft/state_parser.py:57`). Un allié a donc 8 coups possibles, pas 40, et la recherche
explore aujourd'hui des branches où notre support part jouer top.

### 1.3 Le temps passe dans le calcul des paires, pas dans la recherche

Profil cProfile, 3 s de recherche sur B2 :

| Fonction | Temps cumulé | Appels |
|---|---|---|
| `GameEvaluator.matchup_logit` | 1,39 s | 449 k |
| `GameEvaluator.synergy_logit` | 0,93 s | 347 k |
| `str.lower` | 0,30 s | 3,4 M |

Environ 80 % du temps est consommé à recalculer des paires déjà rencontrées : deux `.lower()`, deux
lookups de table, `confidence()` puis `winrate_points_to_logit()`, pour une valeur qui ne change
jamais au cours d'une session (les tables et le K de shrink sont chargés une fois pour toutes par
`GameEvaluator`).

### 1.4 Ce que rapporte chaque levier (prototypes jetables, même base, 2 s)

| Variante | B2 : profondeur (tours restants : 7) | B1 : profondeur (tours restants : 10) | Nœuds/s |
|---|---|---|---|
| Actuel | 5 | 3 | ~40 k |
| + cache des paires (§4.3) | 6 | 4 | ~80-170 k |
| + candidats par popularité (§4.1) | 6 | 4 | ~80-135 k |
| + lane des alliés (§4.2) | **7 (draft entière)** | **5** | ~190-300 k |
| Actuel avec un budget de 10 s au lieu de 2 s | 6 | 5 | ~43 k |

La dernière ligne donne le **facteur de branchement effectif** : multiplier le temps par 5 rapporte
environ un pli. C'est le chiffre qui tranche la question du multi-threading (§5).

Variantes principales avec les trois leviers, B1 : `Nautilus support, Zed mid, Alistar support`
au lieu de `Nidalee support, Sivir bot`.

---

## 2. Objectif

À budget constant (2 s, mono-thread) :

1. Les coups adverses et alliés examinés sont des champions **réellement joués sur leur lane**.
2. Dès que nous pickons en B2 ou plus tard, la recherche atteint la **fin de la draft**. En premier
   pick, elle atteint une profondeur d'**au moins 5**.
3. L'évaluation est inchangée : pas de bump de `MODEL_VERSION`. Les prédictions journalisées
   passent par `final_analysis.py` → `evaluator.win_probability()`, que cette spec ne modifie pas.

---

## 3. Approches considérées — A retenue (@pj35, 2026-09-24)

| | Approche | Gain mesuré ou estimé | Coût |
|---|---|---|---|
| **A** ⭐ | **Élaguer ce qui ne se joue pas.** Candidats par popularité, lane des alliés, cache des paires (§4). Mono-thread. | Mesuré : B2 5 → 7 (fin de draft), B1 3 → 5 | ~1 j. Trois changements locaux et indépendants, aucune dépendance. |
| B | A **+ recherche parallèle à la racine** (`multiprocessing`, §5) | Estimé : environ +1 pli en B1 avec 8 processus. Rien en B2, déjà au bout. | +1-1,5 j. Pool de processus maintenu pendant la draft, chargement des tables par worker (0,85 s chacun), `freeze_support()` pour l'exe PyInstaller, mémoire × N. |
| C | A, avec une **moyenne pondérée par popularité** côté ennemi au lieu du pire cas (expectimax) | Plus « réaliste » sur le papier | Pas d'élagage alpha-bêta aux nœuds de hasard, donc **moins** profond. Et le pire cas parmi des picks plausibles est justement ce qu'un premier pick doit anticiper. |

**Recommandation : A seule**, puis la mesure du §6 décide si B s'ouvre. C est écartée : elle
change la question posée au moteur et coûte la profondeur qu'on cherche à gagner.

---

## 4. Phase 1 — détail (approche A)

Trois commits indépendants, chacun mesurable seul avec le script du §4.4.

### 4.1 Générateur de coups par popularité

- **Nouveau** : `MatchupsRepository.get_lane_popularity(lane: str) -> List[str]`
  (`src/repositories/matchups.py`) et son délégué dans `src/db.py`. La méthode renvoie les noms des
  champions joués sur `lane`, triés par `SUM(games)` décroissant, avec une requête paramétrée :

  ```sql
  SELECT c.name FROM matchups m JOIN champions c ON c.id = m.champion
  WHERE m.lane = ? GROUP BY m.champion ORDER BY SUM(m.games) DESC
  ```

- `CandidatePool._ranked()` utilise cette méthode à la place de `get_all_champion_scores()`. Le
  cache par lane (`_by_lane`) et `best()` ne changent pas.
- Mettre à jour la docstring de `CandidatePool` et celle du module `search.py` (« la tier list
  du projet sert de générateur de coups » devient faux), ainsi que le commentaire de
  `SEARCH_TOP_N` dans `src/config_constants.py`.
- **`SEARCH_TOP_N`** : garder 8 dans ce commit. Une fois les trois commits faits, mesurer N = 8,
  10 et 12 avec le script du §4.4. Retenir **le plus grand N qui tient encore les critères du
  §2.2**. Consigner dans le commentaire de la constante la couverture de games obtenue (même
  calcul que le tableau du §1.1).

### 4.2 Les alliés jouent leur lane

- `PickTurn` (`src/draft/search.py:39`) gagne un champ `lane: Optional[str] = None`.
- `DraftStateParser` (`src/draft/state_parser.py:~100`) le renseigne pour les tours alliés :
  `lane=state.ally_positions.get(actor_cell_id)`. Il reste `None` côté ennemi.
- `DraftSearch._moves()` : pour un tour allié hors joueur local dont `turn.lane` est connue **et
  encore libre** dans l'équipe, renvoyer `candidates.best(turn.lane, taken)` sur cette seule lane.
  Sinon (normal blind, lane inconnue, ou déjà occupée après un échange de rôles), garder le
  comportement actuel sur toutes les lanes libres.
- Le tour du joueur local ne change pas : il utilise déjà `player_lane`.

### 4.3 Cache des paires dans `GameEvaluator`

- `matchup_logit()` et `synergy_logit()` mémorisent leur résultat dans un `dict` d'instance, avec
  pour clé le couple de `Placed` tel quel. Un `dict` suffit ; `functools.lru_cache` sur une
  méthode retiendrait `self` et n'apporte rien ici.
- **Invariant à documenter dans la docstring** : le cache vit aussi longtemps que l'évaluateur,
  comme les tables et les K de shrink qu'il met déjà en cache. Une mise à jour des données en
  cours de session n'est donc pas vue, ni avant ni après ce changement.
- Borne mémoire : au pire (173 × 5)² ≈ 750 k entrées. En pratique, une draft n'en touche que
  quelques dizaines de milliers. Aucune éviction nécessaire.

### 4.4 Script de mesure

`scripts/bench_search.py` rejoue les scénarios B1 et B2 du §1. Il affiche, pour chacun, la
profondeur atteinte, les nœuds par seconde, le top 3 et la variante principale. Il travaille sur
une **copie temporaire** de `data/db.db` (jamais la base de production, jamais d'écriture) et
accepte `--budget` et `--top-n`. Il sert aux critères du §6 et à la décision de phase 2. Ce n'est
pas un test : il dépend de la base réelle et du CPU.

### 4.5 Tests (`tests/test_draft_search.py`, `tests/test_game_eval.py`)

1. **Générateur** : un champion très fort mais peu joué ne figure pas dans `best()`, un champion
   populaire moyen y figure. `FakeDB` gagne `get_lane_popularity`.
2. **Lane alliée** : un tour allié avec `lane="support"` ne génère que des coups `(x, "support")`.
   Avec `lane=None`, ou une lane déjà occupée, il revient aux lanes libres.
3. **Parser** : `remaining_picks` porte la lane `assignedPosition` des tours alliés et `None` pour
   les tours ennemis (étendre `tests/test_draft_monitor_roles.py`, qui couvre déjà `remaining_picks`).
4. **Cache** : un second appel identique ne relit pas la table (compteur sur `FakeDB`), et le test
   d'indépendance de l'ordre de `test_game_eval.py` passe toujours.
5. Le test phare `TestCounterpickTrap::test_depth_two_avoids_what_depth_one_walks_into` reste vert.
   Adapter ses fixtures à la popularité si besoin, sans changer ce qu'il démontre.

---

## 5. Phase 2 — multi-threading : pourquoi pas maintenant, et à quelle condition

**Des threads ne servent à rien ici.** La recherche est du Python pur, limité par le CPU. Avec le
GIL (CPython 3.13 standard, pas la build free-threaded expérimentale), N threads calculent au
rythme d'un seul.

**Des processus fonctionneraient**, et la racine s'y prête bien. `_rank_at_depth()` n'élague pas à
la racine (`src/draft/search.py:339`), puisqu'on veut la valeur exacte de chaque candidat. Les
coups racine sont donc indépendants et se répartissent sans perte entre des workers
(`ProcessPoolExecutor`, un sous-ensemble du pool par worker, résultats fusionnés puis triés).

**Mais le gain est logarithmique.** Facteur de branchement effectif mesuré : environ 5 (§1.4, ×5
de temps ≈ +1 pli). Avec 8 processus utiles (surcoût de spawn Windows compris), on gagne environ
**un pli**. C'est le gain qu'apporte à lui seul le cache du §4.3, au prix d'un pool de processus à
maintenir en vie pendant la draft, du chargement des tables dans chaque worker, de
`multiprocessing.freeze_support()` dans l'exe PyInstaller et d'une mémoire multipliée par N.

**Condition d'ouverture** : après la phase 1, `scripts/bench_search.py` montre une profondeur
inférieure à 5 en B1 avec le `SEARCH_TOP_N` retenu. Ou bien @pj35 constate à l'usage que le
premier pick reste mal conseillé *et* que la variante principale s'arrête avant la réponse adverse
qui compte.

**À garder en tête** (SPEC-11 §3) : chercher plus profond compose l'erreur d'une évaluation encore
non calibrée (`TODO.md`, tâche 4, en attente de données). La phase 1 réduit ce risque au lieu de
l'aggraver : elle retire du bruit (candidats à 0,1 % des games) plus qu'elle n'ajoute de plis. La
phase 2 n'apporte que des plis.

---

## 6. Critères d'acceptation (phase 1)

1. `python scripts/bench_search.py --budget 2` : **B2 atteint 7/7**, **B1 atteint ≥ 5**, sur le
   poste de @pj35.
2. Aucune variante principale affichée par le bench ne contient un champion hors des
   `SEARCH_TOP_N` plus joués de sa lane.
3. `pytest tests/ -v` vert (les tests existants et ceux du §4.5), `black --check` propre, `pylint
   src/ --fail-under=8.0`.
4. Aucun fichier au-delà de 500 lignes (`search.py` fait 344 lignes, `game_eval.py` 219, `db.py`
   413).
5. `CHANGELOG.md` (`[Unreleased]`), ce document (statut) et `docs/specs/README.md` sont mis à
   jour.

---

## 7. Hors périmètre

- ❌ **Recherche en tâche de fond pendant le chrono de pick** (« pondering »). Le budget de 2 s
  existe parce que `rank()` est synchrone dans la boucle du monitor. Profiter des ~30 s du chrono
  demande de sortir la recherche de cette boucle et de rafraîchir l'affichage à chaque profondeur
  terminée. C'est un vrai gain (×15 de temps ≈ +1,5 pli) mais un chantier d'UI, à rouvrir après la
  phase 1 si le besoin persiste.
- ❌ **Table de transposition.** L'évaluation ne dépend pas de l'ordre, donc deux ordres de picks
  d'un même camp mènent à la même position. Mais les transpositions n'existent que lorsqu'un camp
  enchaîne deux picks (B2-B3, R3-R4…). Gain à mesurer après la phase 1, pas avant.
- ❌ **Élagage à la racine pour les candidats hors du top affiché.** Cela casserait l'affichage de
  la probabilité exacte de chaque candidat, un choix explicite de SPEC-12.
- ❌ **La tier list elle-même** (`champion_scores.avg_delta2`, utilisée par `tier_list.py`) place
  Kassadin premier en top et Karthus premier en mid sur des échantillons minuscules. C'est le même
  bruit que le §1.1, mais dans un autre produit : constat à traiter dans une spec séparée
  (shrink de `avg_delta2`), à ne pas mélanger avec celle-ci.
- ❌ **Modéliser les bans** dans la recherche (déjà écarté par SPEC-11 §5).
