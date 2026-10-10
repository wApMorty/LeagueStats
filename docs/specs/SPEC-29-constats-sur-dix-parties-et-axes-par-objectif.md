# SPEC-29 — Constats sur dix parties et axes de travail choisis par le coach

**Statut** : 🟡 Rédigée le 2026-10-10, arbitrages « à valider » en §2.

**Origine** : @pj35, 2026-10-10 : « Le GUI m'affiche les métriques marquantes de ma dernière game uniquement,
dans la section Derniers constats de la page d'accueil. J'aimerais qu'il m'affiche les constats plus loin (sur les
10 dernières games peut-être), en restant une page qui tient sur un écran. J'aimerais aussi qu'on câble les axes de
travail pour qu'il sélectionne les axes sur lesquels je dois me concentrer. »

**Effort** : ~2,5 jours, 5 tâches, 17 pts (§5).

---

## 1. Constat

Mesuré le 2026-10-10 sur `data/db.db` (lecture seule) et sur le code.

**Derniers constats.**

- `home._findings` (`src/client/home.py:113`) lit `repo.latest_findings()` : les constats **d'une seule partie**, la
  dernière qui en a (3 négatifs et 2 positifs au plus, `TOP_NEGATIVE` / `TOP_POSITIVE`). Un constat isolé est du bruit :
  une partie ne dit rien d'un schéma.
- Les données de la fenêtre existent déjà : `game_metrics` porte `z_norm` et `z_objective` pour chacune des 8 métriques
  du top sur les 90 parties capturées (1 190 lignes avec `z_norm` fiable). Le bilan de la colonne latérale
  (`home._review`) agrège aussi, mais sur **tout** l'historique, pas sur les dernières parties.
- Hauteur : à ≥ 1 500 px de large l'accueil a deux colonnes (`style.css:694`) ; en dessous, la colonne latérale
  passe sous la principale et la page défile. Le tableau actuel fait 5 lignes de 52 px ; les cartes d'axe ont
  `min-height: 250px`.

**Axes de travail.**

- Les axes sont câblés pour attendre un **schéma négatif net** : `goals.next_proposal` (`src/coaching/goals.py:56`)
  ne retient que `patterns()` négatifs (binomial à α = 0,05 sur les 10 dernières parties, `z_norm ≤ −1`).
- Sur tes données, ce schéma **n'arrive jamais** : `patterns(history, 'top')` renvoie une liste vide sur les 90
  parties, et le z moyen face à la norme est positif sur les 8 métriques (de +0,17 pour `deaths_before_14` à +0,62
  pour `structure_damage_per_min`). La norme est la moyenne des autres joueurs de ton poste dans tes parties :
  tu es au-dessus de ta lobby partout.
- Conséquence en base : `coaching_goals` contient **un seul axe, jamais jugé** (`solo_deaths`, fixé à la main le
  2026-10-06, clos), `goal_verdicts` est vide, et l'accueil affiche deux « Place libre — pas de proposition ».
- L'objectif OneTricks est la seule référence qui puisse encore pointer un écart : il existe pour 5 métriques
  (`cs_per_min`, `deaths_per_10`, `kill_participation`, `gold_diff_15`, `xp_diff_15`), stocké sur les 90 parties
  (`z_objective`). Sur le top, 3 d'entre elles sont dans la grille : `gold_diff_15` (z moyen +0,12 sur 90 parties),
  `xp_diff_15` (+0,15), `deaths_per_10` (−0,11, la seule sous l'objectif). Sur les 10 dernières : +0,32, +0,41,
  +0,16.
- L'objectif **dépend du champion** (une page OneTricks par champion et par poste, `grid.py:onetricks_objective`) ;
  tu as joué 5 champions sur 90 parties (24 Ambessa, 19 Yorick, 18 Olaf, 13 Sion, 12 Shen). Un axe dont la cible est
  un nombre figé serait jugé contre l'objectif d'un autre champion une partie sur deux : `judge` compare
  aujourd'hui `value` à `coaching_goals.target` (`goals.py:81`).

## 2. Objectif et arbitrages

Objectif : l'accueil montre les écarts de tes **10 dernières parties** (pas d'une seule) sans défiler, et le coach
**choisit lui-même** les axes de travail, y compris quand tu es au-dessus de la norme partout.

| Sujet | Décision |
|---|---|
| Règle de choix d'un axe | **Validé (@pj35, 2026-10-10)** : l'écart à l'objectif OneTricks. Le coach prend la métrique à objectif dont le z_objective moyen sur les 10 dernières parties est le plus bas. |
| Fixation | **Validé (@pj35, 2026-10-10)** : automatique quand le schéma est net, proposition à un clic sinon. |
| Forme des constats | **Validé (@pj35, 2026-10-10)** : une ligne par métrique sur 10 parties (3 plus faibles, 2 plus fortes, mêmes plafonds qu'aujourd'hui), z moyen, barre divergente et bande de 10 points, un par partie. |
| Ordre des deux règles | **À valider** : (1) un schéma négatif net face à la norme (comportement actuel, fixé tout seul) reste prioritaire, car c'est un défaut avéré ; (2) à défaut, l'écart à l'objectif OneTricks, proposé d'un clic. Les deux réponses de @pj35 se combinent ainsi ; si tu préfères l'objectif seul, la tâche 134 retire l'étage 1. |
| Proposer un axe même au-dessus de l'objectif | **À valider** : oui. Sur le top, les trois candidats sont tous au-dessus de l'objectif sur 10 parties ; le coach propose le moins haut et l'écrit (« +0,16 σ : au-dessus de l'objectif, c'est ta marge la plus faible »), plutôt que de ne rien proposer. L'étiquette dit que ce n'est pas un défaut avéré. |
| Jugement d'un axe d'objectif | **À valider** : contre l'objectif **de la partie** (`z_objective ≥ 0` du champion joué), pas contre un nombre figé. Demande une colonne `reference` sur `coaching_goals` (migration, tâche 133). |
| Écran de référence | **À valider** : le contenu doit tenir sans défiler dans 1 920 × 950 (zone de la scène de draft, `style.css:208`), soit ≥ 1 500 px de large, deux colonnes. En dessous de 1 500 px la page peut défiler. |
| Poste des 10 parties | **À valider** : le poste principal (comme `_review`), pas les 10 dernières parties tous postes confondus ; la bande de portraits de la colonne latérale reste, elle, tous postes. |

## 3. Approches considérées

**Constats.**

- **A. Une ligne par métrique, bande de 10 points** (retenue). Même hauteur qu'aujourd'hui (5 lignes), le schéma
  se lit d'un coup d'œil (« 3 points rose sur les 5 dernières »), un point renvoie à la partie.
- B. Tableau métriques × 10 parties : 8 à 12 lignes selon le poste, la page déborde sans compacter les axes.
- C. Garder la dernière partie et ajouter une pastille de tendance : reste centré sur une partie, ce que le
  besoin demande de quitter.

**Choix d'un axe.**

- **A. Cascade : schéma net face à la norme, sinon écart à l'objectif** (retenue) : garde le seul signal avéré
  (binomial) et comble le trou mesuré.
- B. Objectif seul : plus simple, mais jette un défaut avéré s'il apparaissait un jour.
- C. Le plus faible relatif face à la norme (z moyen) : écarté par @pj35. Sur 10 parties l'erreur type du z moyen est
  ≈ ±0,3 σ, du même ordre que les écarts mesurés (0,17 à 0,62) : ce serait classer du bruit.

**Jugement.**

- **A. Verdict contre l'objectif de la partie** (retenue) : l'axe reste vrai quel que soit le champion joué ;
  `analysis.objective_z` porte déjà ce que `analyze_game` calcule.
- B. Cible figée = objectif de la dernière partie : aucune migration, mais faux dès qu'on change de champion
  (5 champions sur 90 parties).

## 4. Détail

### 4.1 Constats sur la fenêtre (`src/coaching/progression.py`, `src/client/home.py`)

```python
@dataclass(frozen=True)
class WindowGap:
    metric: str
    mean_z: float            # z_norm moyen sur la fenêtre (parties à norme fiable seulement)
    zs: List[Optional[float]]  # un z par partie, de la plus ancienne à la plus récente, None si norme en construction
    game_ids: List[int]      # alignés sur zs, pour que le point renvoie à la partie
    mean_value: float
    mean_norm: Optional[float]

def window_gaps(history: List[dict], role: str, games: int) -> List[WindowGap]:
    """Écart moyen de chaque métrique de la grille sur les `games` dernières parties du poste, du plus
    faible au plus fort (pondéré par le rang de la grille). [] sous MIN_TREND_SAMPLE parties fiables."""
```

- `history` vient de `repo.player_history(role, limit=client_config.HOME_FINDINGS_GAMES)` (la requête existante
  limite déjà en nombre de parties distinctes).
- Classement : `mean_z × GRID[role][metric]`, comme `Finding.weighted`. Le tableau prend les
  `HOME_FINDINGS_WEAK` plus bas puis les `HOME_FINDINGS_STRONG` plus hauts, sans doublon.
- `home._findings` est réécrite : plus de `latest_findings` ni de `game_record`, plus de JSON de partie à relire
  (le titre devient « Sur tes 10 dernières parties · {rôle} »). Une ligne : `label`, `value` (moyenne,
  `format_value`), `reference` (moyenne des normes, objectif de la dernière partie s'il existe), `z`
  (`signed(mean_z, 1)`), barre divergente (`diverging(mean_z, HOME_FINDING_Z_FULL)`), `dots`
  (`[{href, tone}]`, `tone` ∈ `bad` si `z ≤ −MIN_ABS_Z`, `good` si `z ≥ MIN_ABS_Z`, `mid`, `none`).
- `repo.latest_findings` reste (la page post-game lit `game_findings`, `review.py:417`) ; seul `home.py` cesse de
  l'utiliser. Si plus aucun appelant, la tâche 135 le supprime.
- Gabarit `accueil.html` : colonnes Métrique · Moy. · Norme · objectif · 10 parties (bande de points, un
  `<a class="dot {tone}" href="/parties/{id}" title="…">` par partie) · Écart · σ. Pas de JS.

Constantes (`src/config_client.py`, bloc « Accueil du coaching ») :

| Constante | Valeur | Origine |
|---|---|---|
| `HOME_FINDINGS_GAMES` | 10 | demande de @pj35 ; égale `coaching_config.RECURRENCE_WINDOW` |
| `HOME_FINDINGS_WEAK` | 3 | `TOP_NEGATIVE` actuel |
| `HOME_FINDINGS_STRONG` | 2 | `TOP_POSITIVE` actuel |
| `HOME_FINDING_Z_FULL` | 2,27 → **1,0** | un z moyen sur 10 parties dépasse rarement 1 σ (mesuré : +0,04 à +0,53) ; à 2,27 la barre ne remplirait que 20 % |

### 4.2 Choix d'un axe par l'objectif (`src/coaching/progression.py`, `src/coaching/goals.py`)

```python
def objective_gaps(history: List[dict], role: str) -> List[tuple]:
    """(métrique, z_objective moyen, parties) sur les RECURRENCE_WINDOW dernières parties, du plus bas
    au plus haut ; seules les métriques de la grille ayant un objectif, et au moins MIN_TREND_SAMPLE parties."""

class Proposal(NamedTuple):
    metric: str
    reference: str   # "norm" (schéma net) ou "objective" (écart à l'objectif)
    net: bool        # True : défaut avéré, `propose` le fixe seul
    gap: Optional[float]  # z_objective moyen, pour le texte de l'accueil
```

- `next_proposal(repo, role) -> Optional[Proposal]` : étage 1 = premier `patterns()` négatif non pris
  (`Proposal(metric, "norm", True, None)`) ; étage 2 = première `objective_gaps()` non prise
  (`Proposal(metric, "objective", False, mean)`). Rien tant qu'une place d'axe n'est pas libre (inchangé).
- `propose(repo, role)` (appelée par `capture.analyze` après chaque partie et par `report.review`) ne fixe que
  si `proposal.net`. L'étage 2 n'écrit jamais seul.
- `set_goal(repo, metric, role, origin="player", reference="norm")` : `reference == "objective"` prend pour cible
  la dernière `objective_value` non nulle de la métrique (affichage seulement) ; `_target` garde la norme sinon.
  Refuse (`[AXE] …`) si la métrique n'a aucun objectif en base.
- `GameAnalysis.objective_z: Dict[str, float]` : le `z_obj` que `analyze_game` calcule déjà à `findings.py:112`.
- `judge` : pour un axe `reference == "objective"`, `held = analysis.objective_z.get(metric, nan) >= 0` (pas de
  verdict si absent) ; `value` stockée reste la valeur brute. Les axes `norm` ne changent pas.
- `describe` et `_goal_card` : cible affichée « objectif OneTricks de ton champion » pour un axe d'objectif.

**Migration Alembic** (`alembic/versions/`, tête actuelle `c8f3a1d95e26`, cf. `docs/alembic_guide.md`) :
`ALTER TABLE coaching_goals ADD COLUMN reference TEXT NOT NULL DEFAULT 'norm'` ; `CoachingRepository.goals()` et
`insert_goal(..., reference)` suivent. L'axe existant (`solo_deaths`, clos) reste `norm`.

**Accueil et route** (`src/client/app.py:282`, `partials/accueil_axes.html`) : `POST /accueil/axe` accepte
`reference` (liste blanche `{"norm", "objective"}`, 400 sinon, comme `origin`) ; le bouton « Fixer cet axe » le
transmet. Le texte de la carte libre dit, pour l'étage 2 : « Le coach propose « {label} » : {gap} σ face à
l'objectif OneTricks sur tes 10 dernières parties{, au-dessus de l'objectif : ta marge la plus faible}. Pas un
défaut avéré. »

### 4.3 Tenir sur un écran (`src/client/static/style.css`)

Budget à 1 920 × 950, colonne principale (mesure arithmétique à confirmer par la tâche 136) : bandeau de page
~110 px + axes (titre 50 + cartes) + marge 30 + constats (titre 50 + en-tête 30 + 5 × 52 = 340). Avec des cartes à
250 px : ≈ 780 px de contenu + 60 de marge de page = 840 < 950, sans marge pour un message `notice`. Cible : cartes
d'axe `min-height` 250 → 200, lignes de constats 52 → 44, pour que la colonne principale et la colonne latérale
(rang, portraits, bilan) restent sous 950 px avec un `notice` affiché. Mesure par rendu **headless** (pas de
fenêtre réelle ni de curseur, voir `feedback-no-ui-tests-without-permission`) : à autoriser par @pj35 avant la
tâche 136 ; à défaut, recette visuelle de @pj35.

### 4.4 Tests

`tests/test_client_accueil.py` (adapter `test_derniers_constats_avec_barre_divergente`,
`test_sans_schema_negatif_pas_de_proposition_et_le_choix_reste`, `test_la_proposition_du_coach_est_affichee_sans_rien_ecrire`),
`tests/test_coaching_progression.py` (`window_gaps`, `objective_gaps`, `propose` n'écrit pas l'étage 2, `judge` d'un
axe d'objectif contre l'objectif de la partie), `tests/regression/` : le bug « aucun axe jamais proposé » (base
où `patterns()` est vide et `z_objective` positifs : l'étage 2 propose le plus bas), rouge avant le fix.

## 5. Tâches

Numéros globaux : à la suite de la tâche 132 du `TODO.md`.

| # | Tâche | Pts | Dépend de |
|---|---|---|---|
| 133 | Migration `coaching_goals.reference` ; `CoachingRepository.goals()` / `insert_goal(reference)` ; test de migration et du dépôt | 2 | — |
| 134 | Choix par l'objectif : `objective_gaps`, `Proposal`, `next_proposal` à deux étages, `propose` (net seulement), `set_goal(reference)`, `GameAnalysis.objective_z`, `judge` contre l'objectif de la partie ; régression « aucun axe jamais proposé » rouge avant, verte après | 5 | 133 |
| 135 | Constats sur 10 parties : `window_gaps`, `home._findings` réécrite, constantes, gabarit et bande de points, route `reference`, texte de la carte libre ; adaptation des tests de l'accueil | 5 | 134 |
| 136 | Tenir sur un écran : `min-height` des cartes et des lignes, mesure headless à 1 920 × 950 avec un `notice` affiché (autorisation de @pj35 requise) | 3 | 135 |
| 137 | Clôture : `CHANGELOG.md`, statuts, `docs/specs/README.md`, `TODO.md`, suppression de `latest_findings` s'il est orphelin, recette @pj35 | 2 | 136 |

## 6. Critères d'acceptation

1. `python -m pytest tests/ -v` vert, avec les tests des tâches 133 à 135 ; la régression de la tâche 134 a été
   vue rouge avant le correctif.
2. `python -m alembic upgrade head` ajoute `coaching_goals.reference` (défaut `'norm'`) ; `python -m alembic
   downgrade -1` puis `upgrade head` passent sur une copie de la base.
3. Sur une copie de `data/db.db` : `next_proposal(repo, 'top')` renvoie `Proposal('deaths_per_10'|…, 'objective',
   False, gap)` (au lieu de `None`), et `propose(repo, 'top')` n'écrit rien (`repo.goals()` inchangé).
4. Un axe `objective` est jugé contre `z_objective` de la partie : deux parties sur deux champions d'objectifs
   différents, même valeur brute, verdicts distincts (test unitaire de `judge`).
5. `GET /` sur une base de test à 10 parties du poste rend 5 lignes de constats, chacune avec 10 points ; la 11e
   partie la plus ancienne n'y est pas ; chaque point renvoie à `/parties/{id}`.
6. Une norme sous `MIN_NORM_SAMPLE` ne produit ni z ni point coloré (point `none`) ; sous `MIN_TREND_SAMPLE`
   parties fiables, le bloc dit « Pas encore assez de parties » au lieu d'un tableau.
7. `POST /accueil/axe?reference=inconnu` répond 400 sans écriture ; `reference=objective` sur une métrique sans
   objectif répond par le message `[AXE]` sans écriture.
8. La carte libre de l'étage 2 contient « Pas un défaut avéré » ; celle de l'étage 1 garde « ton schéma négatif le
   plus net ».
9. `GET /` ne modifie pas la base (test existant `test_la_consultation_n_ecrit_pas_dans_la_base`).
10. À 1 920 × 950, avec un `notice` affiché, `document.scrollingElement.scrollHeight <= innerHeight` sur `/` (rendu
    headless de la tâche 136, ou recette visuelle de @pj35).
11. `CHANGELOG.md` (`[Unreleased]`), statut de cette spec, `docs/specs/README.md` et `TODO.md` à jour.

**Vérification de bout en bout** : lancer le client sur la vraie base, ouvrir l'accueil : « Derniers constats »
montre 5 métriques sur les 10 dernières parties du top avec leur bande de points, et la première place d'axe
propose une métrique d'objectif ; un clic la fixe (`coaching_goals`, `reference = 'objective'`), la partie
suivante la juge (`goal_verdicts`).

## 7. Hors périmètre

- ❌ **Objectifs pour les métriques sans page OneTricks** (`cs_10`, `solo_deaths`, `damage_per_min`, `structure_damage_per_min`) :
  aucune valeur repère sourcée (SPEC-19 §5.2). Sur le top, seuls trois axes sont donc proposables ; en choisir un
  autre reste possible à la main (« Choisir une autre métrique », norme).
- ❌ **Fixation automatique de l'étage 2** : écartée (@pj35) ; l'écart à l'objectif est un classement, pas un défaut.
- ❌ **Test de significativité sur l'écart à l'objectif** : sur 10 parties il ne conclurait jamais ; l'étiquette
  « pas un défaut avéré » porte l'ignorance.
- ❌ **Fenêtre réglable dans l'interface** : `HOME_FINDINGS_GAMES` suffit.
- ❌ **Constats par partie** : restent sur la page de la partie (`/parties/{id}`), inchangés.
- ❌ **Postes autres que le principal** sur l'accueil : le bilan et les constats suivent `main_role`, comme aujourd'hui.
