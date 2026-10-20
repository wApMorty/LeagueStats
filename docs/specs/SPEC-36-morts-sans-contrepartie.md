# SPEC-36 — Morts sans contrepartie : axe de travail et revue de partie

**Statut** : 🟡 Rédigée le 2026-10-20. Cible, place, fixation, morts listées, coût affiché et grille validés par @pj35
le 2026-10-20 (§2). Reste à valider la spec dans son ensemble avant `/implement`.

**Origine** : @pj35, 2026-10-20, après la mesure de SPEC-35 : « Comment traduire ces stats en stratégie pour gagner ? »,
puis : « Rédige une spec avec les deux : axe morts sans contrepartie avant 14 min (je lève le seuil, à ma décision) et
liste des morts sans contrepartie dans la revue de partie. »

**Effort** : ~1,5 jour, 4 tâches (177 à 180), 9 pts (§5).

---

## 1. Constat

Mesuré le 2026-10-20 sur `data/db.db` (lecture seule) et dans SPEC-35 §8.

**Le levier.** Une mort sans contrepartie (aucun kill ni objectif de son équipe à ± 20 s) avant 14 min coûte, en
moyenne sur 78 347 parties, −6,6 pts de win chance au top contre −3,3 pour une mort quelconque, et −7,7 à −9,0 pts
dans les autres rôles (SPEC-35 §8).

**Toi, au top** (136 parties classées avec timeline, `moneyball.player_actions`) : 2,2 morts avant 14 min, dont 1,0
sans contrepartie ; ton adversaire en a 2,6 et 1,1. Taux de victoire selon tes morts sans contrepartie avant 14 min :

| Morts sans contrepartie | Parties | Victoires |
|---|---|---|
| 0 | 58 | 63,8 % |
| 1 | 37 | 54,1 % |
| 2 ou plus | 41 | 26,8 % |

L'étude n'a rien adopté : son seuil comparait ton écart à tes adversaires, et tu ne fais pas pire qu'eux. **@pj35 lève
ce seuil, à sa décision** (2026-10-20). Les chiffres restent corrélationnels (une lane perdue produit aussi des morts
sans échange).

**Ce qui existe.**

- La règle « sans contrepartie » vit dans `src/coaching/moneyball.py` (`_contributions`, `_traded`), utilisée par
  `player_actions` pour l'étude seulement. Aucune métrique de `METRICS` (`src/coaching/metrics.py:40`) ne la porte.
- Un axe a une cible tirée de la norme (moyenne des pairs, `goals._target`) ou de l'objectif OneTricks
  (`reference = "objective"`) ; jamais une cible fixe (`src/coaching/goals.py:61`).
- L'accueil ne propose « Choisir une autre métrique » que sur une place libre, parmi les métriques de `GRID[role]`
  (`partials/accueil_axes.html`), et la route `/accueil/axe` refuse une métrique hors de `GRID[role]`
  (`src/client/app.py:286`).
- Tes deux places d'axe sont prises : « Morts / 10 min » (id 6, cible objectif) et « Écart d'or @15 » (id 8)
  (`coaching_goals`, `MAX_ACTIVE_GOALS` = 2).
- La revue de partie (`src/client/review.py:299`, `templates/partie.html`) montre l'impact par événement de
  `game_impact` (ΔP SPEC-20, dont `death` et `death_solo` du joueur), mais ne dit jamais si une mort a été échangée.
- `GRID_VERSION` = 1 (`src/config_coaching.py:56`) : l'incrémenter recalcule toutes les analyses au démarrage.

## 2. Objectif et arbitrages

Faire de « au plus une mort sans contrepartie avant 14 min » un axe de travail que @pj35 fixe d'un clic, et montrer
dans chaque revue de partie ses morts avant 14 min, échangées ou non, avec leur coût.

| Sujet | Décision |
|---|---|
| Seuil d'adoption de SPEC-35 | **Levé par @pj35 (2026-10-20)**, à sa décision : l'axe existe malgré le verdict de SPEC-35 §8. |
| Cible de l'axe | **Validé (@pj35, 2026-10-20)** : fixe, ≤ 1. Nouvelle référence `fixed` dans `coaching_goals.reference` ; la cible vient d'une constante et ne suit plus la norme. |
| Place | **Validé (@pj35, 2026-10-20)** : le nouvel axe remplace « Morts / 10 min ». @pj35 clôt cet axe dans l'accueil, puis fixe le nouveau sur la place libérée. Aucun code de remplacement. |
| Fixation | **Validé (@pj35, 2026-10-20)** : un clic dans l'accueil (« Choisir une autre métrique »). Pas de proposition du coach dédiée. |
| Grille | **Validé (@pj35, 2026-10-20)** : la métrique entre dans la grille des cinq rôles, poids 2 (constats, choix d'axe, schémas). `GRID_VERSION` 1 → 2. |
| Morts listées dans la revue | **Validé (@pj35, 2026-10-20)** : toutes les morts du joueur avant 14 min, chacune avec son échange (« Échangée : Dragon 05:12 ») ou « Sans contrepartie » en rose. |
| Coût affiché | **Validé (@pj35, 2026-10-20)** : le ΔP SPEC-20 de cette mort (déjà en base) en chiffre principal, et en pied de panneau le taux de change mesuré pour le rôle (SPEC-35 §8 : mort, mort sans contrepartie). |

## 3. Approches considérées

**Où vit la règle « sans contrepartie ».**

| Approche | Pour | Contre |
|---|---|---|
| A. La laisser dans `moneyball.py` et l'importer depuis `metrics.py` | Aucun déplacement | Import circulaire : `moneyball` importe `metrics` |
| **B. La déplacer dans `metrics.py`** (`death_trades`), `moneyball` l'appelle (retenue) | Une seule règle pour l'étude, la métrique et la revue ; pas de cycle (`metrics` n'importe que `winprob.impact`, qui n'importe pas `coaching`) | Petit refactor de `moneyball.player_actions`, couvert par ses 22 tests |
| C. Recalculer la règle dans la revue | Rien à toucher ailleurs | Deux règles qui divergeront |

**Cible fixe.**

| Approche | Pour | Contre |
|---|---|---|
| A. Référence `norm` (existant) | Zéro code d'axe | Cible = moyenne adverse (~1,1), qui bouge |
| **B. Référence `fixed`, cible par métrique en constante (retenue)** | Cible stable et lisible ; `judge` la gère déjà (`_held`) ; aucune migration (`reference` est un `TEXT`) | Une branche de plus dans `set_goal` |

Pour B, la cible fixe est une propriété de la métrique : `set_goal` l'applique dès que la métrique a une cible fixe,
quelle que soit la référence demandée (sauf `objective`). Le bouton de l'accueil et la commande `axe <métrique>` du
Live Coach n'ont donc rien à transmettre de plus.

## 4. Détail

### 4.1 Règle et métrique : `src/coaching/metrics.py` (tâche 177)

```python
class DeathTrade(NamedTuple):
    death: dict             # l'événement CHAMPION_KILL de la mort
    trade: Optional[dict]   # l'événement de son équipe le plus proche dans la fenêtre, None si aucun

def death_trades(game: dict, timeline: dict, pid: int, minute: int) -> List[DeathTrade]:
    """Morts de `pid` avant `minute`, dans l'ordre, chacune avec l'événement qui l'échange."""
```

- Même règle que `moneyball._contributions` / `_traded` (SPEC-35 §4.1) : un `CHAMPION_KILL` dont la victime est de
  l'autre équipe, ou un `ELITE_MONSTER_KILL` / `BUILDING_KILL` dont `impact.scoring_team` est l'équipe du joueur, à
  `|t_événement − t_mort| ≤ MONEYBALL_TRADE_WINDOW_S`. `trade` = l'événement le plus proche en temps (à égalité, le
  plus ancien). Les deux fonctions privées de `moneyball.py` disparaissent ; `player_actions` compte
  `trade is None` via `death_trades`. Les tests de `tests/test_coaching_moneyball.py` restent verts sans changement.
- Nouvelle métrique :

  ```python
  "untraded_deaths_14": Metric("Morts sans contrepartie avant 14 min", -1, "{:.0f}"),
  ```

  calculée dans `compute_metrics` pour les 10 participants quand la timeline a l'image `LANE_MINUTE`
  (`len(frames) > LANE_MINUTE`), sinon omise (règle du module : incalculable = absente, jamais 0).
- `src/coaching/grid.py` : `"untraded_deaths_14": 2` dans les cinq rôles de `GRID`.
- `src/config_coaching.py` : `GRID_VERSION` 1 → 2 (commentaire : SPEC-36, nouvelle métrique).

Tests (`tests/test_coaching_metrics.py`, fixture `tests/fixtures/spike_gameplay/7998195590_*`) :

1. `death_trades` : une mort échangée par un dragon allié à +10 s rend ce dragon en `trade` ; deux candidats (kill à
   +15 s, tour à −5 s) : la tour, plus proche ; sans candidat : `None` ; une mort après 14 min est absente.
2. `compute_metrics` : `untraded_deaths_14` présent pour les 10 joueurs et égal à
   `moneyball.player_actions(...)[pid]["untraded_deaths"]` ; absent sans timeline.
3. `GRID` : la métrique est dans les cinq rôles avec le poids 2.

### 4.2 Axe à cible fixe : `src/coaching/goals.py` (tâche 178)

- `src/config_coaching.py` : `GOAL_FIXED_TARGETS: Dict[str, float] = {"untraded_deaths_14": 1.0}` (validé par @pj35
  le 2026-10-20 : 64 % de victoires à 0, 54 % à 1, 27 % à 2 ou plus, §1). `field(default_factory=...)` comme les
  autres dictionnaires de la classe.
- `set_goal` : si `metric in GOAL_FIXED_TARGETS` et `reference != "objective"`, alors `reference = "fixed"` et
  `target = GOAL_FIXED_TARGETS[metric]` (aucune partie analysée n'est nécessaire). Le reste est inchangé : refus d'un
  doublon, l'axe le plus ancien cède sa place au-delà du maximum.
- `judge` : inchangé (la branche `else` compare la valeur à `target` avec `_held`) ; vérifié par un test.
- `describe` et `home._goal_card` affichent déjà « cible ≤ 1 » pour une référence autre que `objective` ; vérifié par
  un test.

Tests (`tests/test_coaching_progression.py`, base temporaire comme les tests d'axes existants) :

4. `set_goal(repo, "untraded_deaths_14", "top")` : axe `reference = "fixed"`, `target = 1.0`, même sans partie
   analysée.
5. `judge` : valeur 1 → tenu ; valeur 2 → non tenu.
6. Accueil (`tests/test_client_accueil.py`) : la carte de l'axe affiche « cible ≤ 1 » ; « Choisir une autre
   métrique » propose « Morts sans contrepartie avant 14 min » sur une place libre ; le `POST
   /accueil/axe?metric=untraded_deaths_14&role=top&origin=player` fixe l'axe en `fixed`.

### 4.3 Revue de partie : panneau « Tes morts avant 14 min » (tâche 179)

`src/client/review.py`, dans `game_page`, quand la partie a une timeline :

```python
page["deaths"] = {
    "rows": [{"time": "05:02", "killer": "Darius", "solo": True,
              "traded": "Dragon 05:12" | None, "delta_text": "−2,4 pts" | "—", "untraded": bool}, ...],
    "untraded": 1,               # nombre de morts sans contrepartie
    "rates": "Au top, une mort vaut ≈ −3,3 pts, une mort sans contrepartie ≈ −6,6 pts (SPEC-35)",
}
```

- Lignes : `metrics.death_trades(game, timeline, pid, LANE_MINUTE)`. `killer` : nom du champion du tueur
  (`champions.name`), « Tourelle » ou « Sbires » si le tueur n'est pas un joueur (`killerId` hors participants : 0 →
  « Tourelle / sbires »). `solo` : tueur joueur sans assistant (règle de `solo_deaths`).
- `traded` : libellé court de l'événement d'échange et son heure : kill → « Kill sur <champion> », monstre → libellé
  de `winprob.report.LABELS` / `SHORT` déjà utilisés par la revue (Dragon, Larves, Héraut…), bâtiment → « Tour » ou
  « Inhib. ».
- `delta_text` : somme des lignes `game_impact` du joueur de type `death` ou `death_solo` à `event_time_ms` égal à
  l'instant de la mort, × 100, au format de la revue (`_pts`) ; « — » si l'impact n'est pas calculé.
- `rates` : `MONEYBALL_DEATH_PTS[rôle]` (constante, ci-dessous) ; absent si le rôle est inconnu.
- Aucune mort avant 14 min : `rows` vide, le panneau dit « Aucune mort avant 14 min. ». Sans timeline : pas de
  panneau (`page["deaths"] = None`).

`src/config_coaching.py` : `MONEYBALL_DEATH_PTS: Dict[str, Tuple[float, float]]` = (mort, mort sans contrepartie),
mesurés par SPEC-35 §8 le 2026-10-20 : top (−3,30 ; −6,64), jungle (−5,83 ; −8,59), middle (−5,03 ; −7,96),
bottom (−4,43 ; −7,65), support (−5,35 ; −8,99).

`templates/partie.html` : une `section class="panel deaths"` dans la colonne principale, après les cartes « Les plus
coûteux / rentables », titre « Tes morts avant 14 min » et à droite « N sans contrepartie ». Une ligne par mort :
heure, tueur (badge « solo »), échange en vert ou « Sans contrepartie » en rose (`var(--rose)`), ΔP. Pied :
`rates` en `muted-2`. `src/client/static/style.css` : styles du panneau, en réutilisant les classes des lignes
existantes (`top-row`, `tab`, `muted-2`) autant que possible.

Tests (`tests/test_client_parties.py`, fixture de partie capturée existante) :

7. La page d'une partie avec timeline contient le panneau, une ligne par mort du joueur avant 14 min, le bon nombre
   « sans contrepartie », le ΔP de la mort et le pied au taux du rôle.
8. Une mort échangée affiche son échange ; une mort sans échange affiche « Sans contrepartie ».
9. Sans timeline : pas de panneau ; sans impact : « — » à la place du ΔP.

### 4.4 Clôture (tâche 180)

`CHANGELOG.md` (`[Unreleased]`), statut de cette spec, `docs/specs/README.md`, `docs/PROJECT_STRUCTURE.md` si un
fichier change de rôle, `TODO.md`. Recette @pj35 : lancer le client (le recalcul `GRID_VERSION` 2 tourne au
démarrage), clore « Morts / 10 min » dans l'accueil, fixer « Morts sans contrepartie avant 14 min » sur la place
libérée, ouvrir la revue d'une partie récente.

## 5. Tâches

| # | Tâche | Pts | Dépend de |
|---|---|---|---|
| 177 | `metrics.death_trades` (règle déplacée de `moneyball.py`), métrique `untraded_deaths_14`, grille des cinq rôles, `GRID_VERSION` 2 ; tests 1 à 3 | 3 | — |
| 178 | Référence `fixed` : `GOAL_FIXED_TARGETS`, `set_goal` ; tests 4 à 6 | 2 | 177 |
| 179 | Revue : panneau « Tes morts avant 14 min », `MONEYBALL_DEATH_PTS` ; tests 7 à 9 | 3 | 177 |
| 180 | Clôture : `CHANGELOG.md`, statuts, README des specs, structure, recette @pj35 | 1 | 178, 179 |

## 6. Critères d'acceptation

1. `python -m pytest tests/test_coaching_metrics.py tests/test_coaching_moneyball.py tests/test_coaching_progression.py tests/test_client_accueil.py tests/test_client_parties.py -v`
   vert avec les tests 1 à 9 du §4, puis `python -m pytest tests/ -v` vert.
2. `grep -n "_contributions\|_traded" src/coaching/moneyball.py` ne renvoie rien : une seule règle, dans
   `metrics.death_trades`.
3. `grep -n "untraded_deaths_14" src/coaching/grid.py` renvoie cinq lignes ; `GRID_VERSION` vaut 2.
4. `grep -n "GOAL_FIXED_TARGETS\|MONEYBALL_DEATH_PTS" src/config_coaching.py` montre les deux constantes avec leur
   origine ; aucune valeur de cible ni de taux en dur dans `goals.py` ou `review.py`.
5. Aucune migration Alembic (`git diff --stat` ne touche pas `alembic/`).
6. `CHANGELOG.md` (`[Unreleased]`), statut de cette spec et `docs/specs/README.md` à jour.

**Vérification de bout en bout** : sur une copie de `data/db.db`, lancer le client
(`python lol_coach.py`, menu 7) ; l'accueil recalcule les analyses (`GRID_VERSION` 2), la ligne « Morts sans
contrepartie avant 14 min » apparaît dans les constats ou le choix d'axe ; clore « Morts / 10 min », fixer le nouvel
axe (cible ≤ 1) ; la revue d'une partie montre le panneau des morts avant 14 min. Recette réelle par @pj35 (tâche 180).

## 7. Hors périmètre

- ❌ Proposition chiffrée du coach (« ≈ 6,6 pts par mort sans échange ») : @pj35 fixe l'axe lui-même (§2).
- ❌ Troisième place d'axe : le nouvel axe remplace « Morts / 10 min » (§2).
- ❌ Alerte en partie (« ton jungler est loin, joue safe ») : rien ne dit en direct qu'une mort sera échangée.
- ❌ Nouvelle mesure de l'effet : les taux viennent de SPEC-35 §8, figés en constante ; les remesurer reste
  `python scripts/measure_moneyball.py`.
