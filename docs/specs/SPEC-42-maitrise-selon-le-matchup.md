# SPEC-42 — Maîtrise selon le matchup

**Statut** : ✅ Close le 2026-10-22. Phase A : 204 et 205, **rien d'adopté** (§8), la variante a reste en place.
Phase B (206 et 207) abandonnée.

**Origine** : @pj35, 2026-10-22 : « L'algorithme me recommande de jouer Olaf à toutes les games depuis qu'on a
introduit les performances personnelles. » Puis : « j'ai déjà eu plusieurs fois à jouer contre des Gangplank en
tant qu'Olaf et c'est toujours un matchup extrêmement pénible […] Peut-être que l'avantage qu'apporte la maîtrise
d'un champion ne devrait pas s'additionner mais influencer le win chance différemment. Même avec une maîtrise
parfaite, un matchup Malphite vs Sylas reste quasiment impossible. »

**Effort** : ~2 j, 5 tâches (§5), dont 2 conditionnelles à la mesure (phase B).

---

## 1. Constat

Mesures du 2026-10-22, lecture seule de `data/db.db` (copie temporaire pour `GameEvaluator`) et de `crawl.db`.

- **Le terme de SPEC-41 ne dépend pas de l'adversaire.** `MasteryTerm.logit(name)` vaut
  `MASTERY_LOGIT_PER_POINT × points` du champion (`src/analysis/mastery.py`), quel que soit le vis-à-vis. Il
  s'ajoute au logit de mon pick à la racine de la recherche (`src/draft/search.py:334`), dans le grimoire
  (`src/draft/recommendations.py:195`) et dans l'analyse finale affichée (`src/draft/final_analysis.py:379`).
- **Olaf domine parce que sa maîtrise pèse plus que le matchup de lane.** Maîtrise actuelle : Olaf +5,4 pts
  (30 parties), Malphite +3,4 (8), Yorick +1,7 (22), Kennen +0,3 (9), Ambessa −3,3 (30). Le duel de lane, tel que
  le moteur le compte (`GameEvaluator.matchup_logit`, confiance et `K_MATCHUP` compris), reste dans ±1,2 pt pour
  la plupart des paires :

  | Duel au top | Moteur (pts de victoire) | LoLalytics `delta2` (parties) |
  |---|---|---|
  | Kennen contre Darius | +1,2 | +4,58 (334) |
  | Olaf contre Darius | 0,0 | +0,56 (441) |
  | Olaf contre Gangplank | +1,0 | +1,74 (535) |
  | Malphite contre Sylas | **−7,2** | −6,73 (1 626) |

  Contre Darius, Kennen ne devance Olaf que de 1,2 pt de duel, et Olaf a 5,1 pts de maîtrise de plus : Olaf
  passe devant, ce que @pj35 a refusé sur sa dernière partie.
- **Le biais de counter-pick ne se voit pas dans les données.** Sur ses 30 parties d'Olaf, la draft prédisait
  51,8 % (toutes parties : 51,5 %), le `delta2` de lane moyen vaut +0,14 (toutes parties : +0,83), et il gagne
  19 fois (63 %, contre 78/154 au total). Olaf n'a pas été joué dans des drafts plus favorables que les autres.
- **Olaf contre Gangplank est un mauvais matchup personnel, pas un mauvais matchup général.** 2 parties, 2
  défaites, ΔP de −14,0 et −11,0, alors que LoLalytics donne Olaf favori (+1,74). Contre Darius, une seule partie
  (défaite, ΔP +3,3) : rien à conclure.
- **Malphite contre Sylas est déjà presque traité.** Le terme est additif en log-odds, pas en points : à −7,2 pts
  de duel, les +3,4 pts de maîtrise de Malphite ne compensent pas l'écart. Ce qu'une interaction changerait,
  c'est la part de la maîtrise selon le matchup, pas l'échelle.
- **La maîtrise par matchup a très peu d'échantillon.** SPEC-41 §7 l'avait écartée (« du bruit pur »). Sur
  `crawl.db`, sur 88 093 parties SoloQ lues (script jetable, filtre plus large que l'étude : postes connus, un
  vis-à-vis unique), 25 346 joueurs focaux et 469 517 lignes focales : 76,9 % des lignes ont une autre partie du
  même joueur sur le même champion, mais **15,3 % seulement (72 050) une autre partie sur le même champion contre
  le même vis-à-vis**. Pour 85 % des lignes, D vaut donc 0 : f ne peut gagner que sur ces 15 %. Chez @pj35,
  159 parties SoloQ : Olaf a rencontré 22 adversaires de lane différents en 30 parties.

## 2. Objectif et arbitrages

Mesurer, avec la règle d'adoption de SPEC-41, si la maîtrise doit dépendre du matchup de lane. Deux formes, plus
leur combinaison. Le moteur ne change que si l'une d'elles bat la variante a en place.

| Sujet | Décision |
|---|---|
| Variante e (approche A) | **Validé (@pj35, 2026-10-22)** : interaction maîtrise × matchup **de lane seul**. `victoire ~ draft + b · M + c · M · m`, où M est la maîtrise de la variante a et m = `matchup_logit((mon champion, poste), (vis-à-vis, poste))`. Pas de terme m seul : le duel est déjà dans `draft`, et le gain de e ne doit venir que de l'interaction. |
| Variante f (approche B) | **Validé (@pj35, 2026-10-22)** : maîtrise par matchup contre le **vis-à-vis de lane seul**. `victoire ~ draft + b · M + e · D`, où D est l'écart de la case (champion, vis-à-vis) à la moyenne du champion, rétréci vers 0 par un K₂ propre (§4.1). Deux coefficients plutôt qu'un offset fusionné : M et D ne sont pas rétrécis par le même K. |
| Variante g (A + B) | **Validé (@pj35, 2026-10-22)** : `victoire ~ draft + b · M + c · M · m + e · D`, choisie par la même règle que les autres. |
| Seuil d'adoption | **Validé (@pj35, 2026-10-22)**, celui de SPEC-41 §2, figé avant la mesure : IC95 bootstrap (par joueur) du gain de Brier entièrement positif, et IC95 de **chaque coefficient introduit par la variante** (c pour e ; e pour f ; c et e pour g) qui exclut 0. |
| Règle de choix | Celle de SPEC-41 §8 (`choose`) : une variante ne remplace a que si l'IC95 de son gain moins celui de a est entièrement positif ; entre plusieurs, le plus grand gain moyen. Les variantes b, c, d restent mesurées, inchangées. |
| Périmètre | **Validé (@pj35, 2026-10-22)** : mesure et intégration au moteur, en tâches conditionnelles comme SPEC-41. Si rien n'est adopté, 206 et 207 sont abandonnées et la spec est close. |
| Vis-à-vis inconnu | Décision de la spec : tant que l'adversaire de lane n'est pas choisi (blind pick, ou vis-à-vis pas encore verrouillé), m = 0 et D = 0. Le terme vaut alors `b · M`, comme aujourd'hui. Les nœuds internes de la recherche ne recalculent pas le terme (§7). |
| Exceptions manuelles | Écartées (approche C, §3) : pas de liste à entretenir tant que la mesure n'a pas tranché. |

## 3. Approches considérées

| Approche | Pour | Contre |
|---|---|---|
| **A + B mesurées ensemble, puis appliquées si adoptées (retenue)** | Même règle que SPEC-41, seuil figé avant la mesure. A s'estime sur toute la population (82 000 parties) ; B est la seule qui capte Olaf contre Gangplank. | ~35 min d'étude ; peut conclure « non adopté » pour les deux. B a très peu de cases répétées (§1). |
| C. Exceptions manuelles (Olaf contre Gangplank → maîtrise annulée) | Immédiat, utilise ce que @pj35 sait déjà | Aucune métrique ; liste à tenir à la main ; contraire à la règle « pas d'heuristique sans mesure » |
| D. Plafonner le terme (±3 pts) | Trivial | Seuil arbitraire ; brise l'étalonnage de `MASTERY_LOGIT_PER_POINT` avec `MASTERY_K` (SPEC-41 §8) |

## 4. Détail

### 4.1 Fonctions pures dans `src/analysis/mastery.py` (tâche 204)

```python
def matchup_shrink_k(cells: Sequence[Mapping[str, Sequence[float]]]) -> Optional[float]:
    """K₂ de la maîtrise par matchup : un mapping par (joueur, champion), adversaire de lane -> valeurs.

    C'est `pooled_shrink_k` appliqué à ces mappings : la variance entre adversaires À L'INTÉRIEUR de
    chaque (joueur, champion), regroupée. None si τ² ≤ 0 ou sans degré de liberté.
    """

def leave_one_out_matchup_deviation(
    games: Sequence[Tuple[str, Optional[str], float]], k2: float
) -> List[float]:
    """Pour chaque partie (champion, vis-à-vis, valeur) d'un joueur, D calculé sur ses AUTRES parties :
    (moyenne de la case (champion, vis-à-vis) − moyenne du champion) × n_case / (n_case + k2).

    0 si le vis-à-vis est None, ou si la case ou le champion n'ont pas d'autre partie. O(1) par partie,
    comme `leave_one_out_points`.
    """

def matchup_deviations(
    games: Sequence[Tuple[str, Optional[str], float]], k2: float
) -> Dict[Tuple[str, str], Tuple[int, float]]:
    """(champion, vis-à-vis) -> (parties, D) sur toutes les parties, pour le moteur et la table de @pj35."""
```

Tests (`tests/test_mastery.py`) : sur des cases synthétiques à τ connu, K₂ retrouvé à ±20 % (graine fixe) ;
τ² nul → `None` ; `leave_one_out_matchup_deviation` identique à `matchup_deviations` recalculé sans la partie
(cas tiré au hasard, 200 tirages) ; vis-à-vis `None` → 0 ; case à une seule partie → 0 pour cette partie.

### 4.2 Étude `scripts/measure_mastery_term.py` (tâche 205)

1. `Row` gagne `opponent: Optional[str]` (champion du vis-à-vis de même poste, `None` s'il n'y en a pas
   exactement un) et `lane: float` (= `evaluator.matchup_logit((champion, poste), (vis-à-vis, poste))`, 0 sans
   vis-à-vis), remplis par `_game_rows`.
2. `VARIANTS = ("a", "b", "c", "d", "e", "f", "g")`. Les colonnes d'une ligne focale dépendent de la variante :
   `[1, draft, M]` pour a à d (inchangé) ; e : `[1, draft, M, M · lane]` ; f : `[1, draft, M, D]` ; g :
   `[1, draft, M, M · lane, D]`, où M est l'offset de la variante a et D celui de §4.1, tous deux calculés sans la
   partie prédite. K est celui de la variante a ; K₂ est estimé sur les blocs d'entraînement par
   `matchup_shrink_k`. Si K₂ vaut `None`, f et g sont imprimées `tau2 <= 0, terme nul`, comme aujourd'hui.
3. `cross_validate` et `full_fit` construisent les colonnes par une seule fonction (`_columns(variant, row,
   offsets)`), sans dupliquer la boucle. `full_fit` rend l'IC95 de **chaque** coefficient au-delà de `draft`.
4. `decide(coef_cis, gain_ci)` : `coef_cis` devient une séquence d'IC95, tous doivent exclure 0. Pour a à d,
   la séquence a un élément : comportement inchangé (test de régression).
5. Sortie, en plus de l'existant : par variante, K₂ s'il y a lieu, chaque coefficient et son IC95 ; le nombre de
   lignes focales dont D ≠ 0 (cases répétées). Si e, f ou g est retenue : la ligne `[OK] Adopté (variante x)`
   imprime les constantes du §4.4, puis la table de @pj35 par matchup (cases à 2 parties ou plus, triées par
   |D|), Olaf contre Gangplank compris.

### 4.3 Le terme dans le moteur (phase B, tâches 206 et 207, si e, f ou g est adoptée)

- **`MasteryTerm`** charge en plus, pour f et g, les cases `matchup_deviations` de @pj35 : le vis-à-vis de
  chaque partie vient de `game_metrics` (même `role`, `is_player = 0`, autre équipe), en SQL paramétré dans
  `CoachingRepository`. Nouvelle signature, compatible :
  `logit(name, opponent: Optional[str] = None, lane: float = 0.0) -> float`
  = `MASTERY_LOGIT_PER_POINT · M + MASTERY_LANE_INTERACTION · M · lane + MASTERY_OPPONENT_LOGIT_PER_POINT · D`.
  Sans adversaire, `lane = 0` et `D = 0` : la valeur est celle de SPEC-41, au bit près. `points(...)` suit la
  même signature. Toute erreur de chargement des cases les laisse vides, sans toucher au terme par champion.
- **Recherche** (`recommendations.py:357`) : `personal` devient
  `lambda name: term.logit(name, versus, evaluator.matchup_logit((name, player_lane), (versus, player_lane)))`
  quand `direct_counter_name` (`versus`) est connu, et `term.logit` sinon. `search.py` ne change pas.
- **Grimoire** (`_fill_candidates`) et **analyse finale** : même vis-à-vis (l'ennemi de ma lane parmi les picks
  ennemis), même appel. La prédiction journalisée reste la draft seule (SPEC-41 §2).
- **Blind pick** (`automation.py`) : inchangé, pas de vis-à-vis.
- **Cartes et console** (tâche 207) : quand D ≠ 0 ou que l'interaction déplace le terme, la sous-ligne dit
  « dont toi sur Olaf contre Gangplank : −1,2 pts (2 parties) » ; sinon le texte de SPEC-41 reste.
  `SnapshotRecommendation` gagne `personal_versus: Optional[str]` et `personal_versus_games: int`.

### 4.4 Constantes (`src/config_constants.py`, `AnalysisConfig`)

| Constante | Valeur | Origine |
|---|---|---|
| `MASTERY_LANE_INTERACTION` | mesuré (tâche 205), 0 si e et g non adoptées | Coefficient c |
| `MASTERY_OPPONENT_LOGIT_PER_POINT` | mesuré (tâche 205), 0 si f et g non adoptées | Coefficient e |
| `MASTERY_OPPONENT_K` | mesuré (tâche 205) | K₂ de la population |
| `MASTERY_LOGIT_PER_POINT` | remesuré si e, f ou g est adoptée | b de la variante retenue : il change quand on ajoute des colonnes |

Si rien n'est adopté, aucune constante n'est ajoutée.

## 5. Tâches

| # | Tâche | Pts | Dépend de |
|---|---|---|---|
| 204 | `src/analysis/mastery.py` : `matchup_shrink_k`, `leave_one_out_matchup_deviation`, `matchup_deviations` + tests §4.1 | 2 | — |
| 205 | `scripts/measure_mastery_term.py` : variantes e, f, g (§4.2), `decide` à plusieurs coefficients, mesure complète, résultat et décision en §8 | 5 | 204 |
| 206 | *Conditionnelle (205)* : `MasteryTerm` avec vis-à-vis et duel, cases de @pj35, recherche, grimoire, analyse finale, constantes mesurées + tests | 3 | 205 |
| 207 | *Conditionnelle (205)* : sous-ligne « dont toi sur X contre Y » (snapshot, cartes, console) + tests | 2 | 206 |
| 208 | Clôture : critères du §6, `CHANGELOG.md`, statut de la spec, `docs/specs/README.md`, `TODO.md` | 1 | 205 (et 207 si adoptée) |

## 6. Critères d'acceptation

1. `python -m pytest tests/ -v` vert, avec les tests des tâches ci-dessus.
2. `python -m pytest tests/test_mastery.py -v` : K₂ synthétique retrouvé à ±20 %, τ² nul → `None`,
   leave-one-out identique au recalcul sans la partie, vis-à-vis `None` → 0.
3. Un test montre que `decide` avec un seul IC95 rend la même décision qu'avant SPEC-42, et qu'avec deux IC95 il
   refuse dès que l'un contient 0.
4. `python scripts/measure_mastery_term.py` (Live Coach fermé) imprime les sept variantes, K₂, chaque coefficient
   avec son IC95, le nombre de lignes à D ≠ 0, puis une ligne `[OK] Adopté (variante x)` ou `[INFO] Non adopté`.
   §8 consigne la sortie, et le seuil du §2 n'a pas changé depuis la rédaction (`git log -p` de cette spec).
5. *Si adopté* : `MasteryTerm.logit(name)` sans adversaire rend exactement la valeur de SPEC-41 (test), et
   `logit("Olaf", "Gangplank", lane)` sur une base de test où Olaf perd ses parties contre Gangplank est
   inférieur à `logit("Olaf")` (variantes f ou g).
6. *Si adopté* : un test de `recommendations.py` vérifie que `personal` reçoit le vis-à-vis de ma lane quand il
   est verrouillé, et `term.logit` seul sinon ; une exception dans le calcul du terme ne sort pas de la boucle de
   draft.
7. *Si adopté* : `draft_view.recommendations` produit « dont toi sur Olaf contre Gangplank : … » sur un snapshot
   de test, et le texte de SPEC-41 sans vis-à-vis.
8. `CHANGELOG.md` (`[Unreleased]`), statut de cette spec, `docs/specs/README.md` et `TODO.md` à jour.

**Vérification de bout en bout** : l'étude (critère 4) tranche. Si elle adopte, une draft réelle de @pj35 au top
avec Olaf et Kennen dans le pool contre un Gangplank verrouillé : la carte d'Olaf porte « contre Gangplank », et
son terme est plus bas que sans vis-à-vis.

## 7. Hors périmètre

- ❌ Exceptions manuelles et plafond du terme (§3).
- ❌ Interaction avec toute la draft plutôt qu'avec le duel (§2, validé lane seule).
- ❌ Maîtrise contre les ennemis hors lane (jungler, mid…) : le duel est le seul vis-à-vis validé.
- ❌ Recalcul du terme dans les nœuds internes de la recherche, quand le vis-à-vis serait choisi plus tard
  dans la variante : le terme reste celui de la racine, avec le vis-à-vis connu à ce moment.
- ❌ Distinction blind / counter de mes parties passées : l'ordre de pick n'est pas enregistré (`predictions`
  n'a que la draft finale).

## 8. Résultats

**Mesure (tâche 205, 2026-10-22)** : `python scripts/measure_mastery_term.py`, sans limite. 88 143 parties lues
(99 exclues parce que @pj35 y joue, 3 411 hors filtre), dont 84 633 retenues, en 2 131 s ; 167 735 joueurs, dont
25 330 focaux, soit 468 703 lignes de prédiction. Validation croisée à 5 blocs de joueurs, IC95 par bootstrap sur
les joueurs (1 000 tirages), seuil du §2 inchangé depuis la rédaction.

| Variante | K / K₂ | Coefficient introduit | Gain de Brier |
|---|---|---|---|
| a : en place | 42,3 | b = 0,0723 [0,0595 ; 0,0846] | +0,00008 [+0,00005 ; +0,00011] |
| e : M × duel de lane | 42,3 | c = −0,031 [−0,241 ; +0,172] | +0,00008 [+0,00005 ; +0,00011] |
| f : écart par vis-à-vis D | 42,3 / 50,2 | e = −0,023 [−0,078 ; +0,035] | +0,00008 [+0,00005 ; +0,00011] |
| g : e et f | 42,3 / 50,2 | c = −0,030 [−0,242 ; +0,171] ; e = −0,023 [−0,078 ; +0,035] | +0,00008 [+0,00005 ; +0,00011] |

Les variantes b, c, d de SPEC-41 redonnent leurs chiffres (gains b − a, c − a, d − a : [−0,00001 ; +0,00001],
[−0,00004 ; +0,00001], [−0,00003 ; −0,00001]). 69 242 lignes focales ont un écart D non nul (14,8 %).

**Décision : rien d'adopté, la variante a reste en place.** Le script imprime `[OK] Adopté (variante a)` : la
variante a, celle de SPEC-41 déjà en place, passe toujours le seuil, et aucune autre ne la bat. e, f et g ont un gain de Brier identique à celui de
a : tout leur gain vient de la maîtrise par champion. Leurs coefficients introduits ont un IC95 qui contient 0,
avec un signe négatif. Tâches 206 et 207 abandonnées. Les constantes du moteur ne changent pas : 0,0723 et 42,3
redonnent 0,0717 et 42,4 dans leur marge, comme au passage du 2026-10-22 de SPEC-41.

Lecture :
- **La maîtrise ne pèse pas différemment selon le duel.** Sur 25 330 joueurs, un bon joueur de son champion ne
  gagne ni plus dans un matchup favorable, ni moins dans un matchup défavorable, que ce que le duel et sa maîtrise
  prédisent séparément. Le terme additif en log-odds suffit : il atténue déjà l'effet de la maîtrise aux deux
  extrêmes (§1, Malphite contre Sylas).
- **La maîtrise par vis-à-vis est du bruit, même mesurée sur 69 242 lignes.** K₂ = 50,2 : il faut une
  cinquantaine de parties contre le même adversaire, avec le même champion, pour que l'écart compte à moitié. Chez
  @pj35, Olaf contre Gangplank (2 parties, ΔP −14 et −11) donnerait D = −0,8 pt de ΔP, contre +3,2 pour sa
  maîtrise d'Olaf : deux défaites contre Gangplank ne se distinguent pas du hasard.
- **Olaf reste en tête pour la même raison qu'au §1** : 31 parties, +7,6 pts de ΔP brut, +3,2 une fois rétréci,
  soit environ +5,7 pts de victoire, quand le duel de lane du moteur reste dans ±1,2 pt.
