# SPEC-51 — Méta du poste : la page Blindabilité réarrangée autour d'un rôle

**Statut** : 🟡 Rédigée le 2026-11-06, arbitrages validés par @pj35 le même jour (§2).

**Origine** : @pj35, 2026-11-06 — « Je veux réarranger la page Blindabilité : on choisit un rôle tout en haut,
il affiche le graphe concerné en bas comme actuellement, met en surbrillance les cases qui me concernent dans les
matrices, et fais des suggestions de pool sur le côté. Les features de l'écran Suggestions seront portées ici. Il
faudra peut-être renommer la page également. » Fait suite au retrait de l'interface de SPEC-50 sur l'écran
Suggestions (commit `14f0006`).

**Effort** : ~2 jours, 6 tâches, 16 pts (§5).

---

## 1. Constat

### 1.1 La page Blindabilité aujourd'hui

`GET /blindabilite?poste=` (`src/client/app.py:357`) calcule `compute_blindability` (0,4 à 0,75 s sur la base du
1er nov., mesure du 2026-11-06) et rend `blindabilite.html` : deux matrices poste × poste (Adversaires, Alliés),
sans notion de « mon poste », puis l'histogramme des tirages du poste choisi par des puces placées dans le panneau
du graphe. Poste par défaut : `middle` (`src/client/blindabilite.py`, `_DEFAULT_LANE`). Menu : groupe Coaching
(`NAV`, `src/client/app.py:106`).

### 1.2 Le moteur de SPEC-50 sans interface

Restent en place après `14f0006` : `PoolScorer` et `swap_cards` nets du tirage (`src/analysis/pool_swipe.py`),
`generate_pool` (`src/analysis/pool_generator.py`), `load_pool_exclusions` / `save_pool_exclusion`
(`src/user_prefs.py`), `distinct_snapshots` (`src/db_backup.py`), les constantes `POOL_GEN_*`. L'interface retirée
(routes, cache, vue formatée, partiel) est dans les commits `d6e5956` (tâche 249) et `8596618` (tâche 250), à
reprendre. L'écran Suggestions de SPEC-49 (`/pool/suggestions`, cartes prendre / passer) est lié depuis l'écran Pool
(`partials/pool_body.html:18`) et l'écran Données (`partials/donnees_etat.html:8`).

### 1.3 Ordre de pick sur les matrices

Minimax du 2026-11-06 (script jeté) : séquence B R R B B R R B B R sans bans ; un pick rapporte
`√(Σ M[r][e]² sur les adversaires déjà pickés + Σ S[r][a]² sur les alliés déjà pickés)`, M et S les matrices de
`compute_blindability` en points ; gain compté pour le côté qui pique, retranché pour l'autre. Programmation
dynamique sur (postes pickés par blue, postes pickés par red) : 32 × 32 états.

| Scrape | Séquence optimale |
|---|---|
| 1er nov. (base actuelle, seuil 15 000) | B jungle · R jungle, mid · B mid, bot · R bot, support · B top, support · R top |
| 20 oct. | identique |
| 6 oct. | B bot · R support, bot · B support, jungle · R jungle, mid · B mid, top · R top |

Le détail bouge d'un scrape à l'autre ; « pické avant ou après le même poste adverse » reste identique pour
chaque poste sur les trois.

## 2. Objectif et arbitrages

Une page « Méta du poste » : un rôle choisi en haut, ses cases en surbrillance dans les deux matrices, la séquence
de pick conseillée, l'histogramme des tirages avec son pool en évidence, et sur le côté le générateur de pool et
les cartes d'échange.

| Sujet | Décision |
|---|---|
| Nom | **Validé (@pj35, 2026-11-06)** : « Méta du poste », URL `/meta`. `/blindabilite` redirige. |
| Menu | **Validé (@pj35, 2026-11-06)** : groupe Coaching, à la place de Blindabilité. |
| Écran Suggestions | **Validé (@pj35, 2026-11-06)** : supprimé ; ses cartes passent dans le panneau latéral ; `/pool/suggestions` redirige vers `/meta`, liens des écrans Pool et Données mis à jour. |
| Surbrillance | **Validé (@pj35, 2026-11-06)** : ligne et colonne du rôle dans les deux matrices ; champions du pool désigné au poste dans l'histogramme ; séquence de pick conseillée. |
| Ordre de pick | **Validé (@pj35, 2026-11-06)** : la séquence complète des 10 picks, le poste choisi en surbrillance, calculée sur le scrape actuel. |
| Rôle par défaut | **Validé (@pj35, 2026-11-06)** : le dernier choisi, mémorisé dans `user_prefs.json` ; Top au premier lancement. |
| Panneau latéral | **Validé (@pj35, 2026-11-06)** : générateur (taille, mode, exclusions, « Créer le pool ») puis cartes d'échange. |
| Générateur | Repris de SPEC-50 §2 sans changement (½ blind exposé + ½ counter, nets du tirage, taille 3 à 6, moyenne des scrapes ou scrape actuel, exclusions par poste, bouton « Générer » en cache, « Créer » = nouveau pool désigné au poste). |

## 3. Approches considérées

1. **Retenue : une page à deux colonnes**, contenu à gauche, panneau latéral à droite (une colonne sous 1 100 px).
   Le panneau est un partiel htmx rechargé seul par ses actions : prendre ou passer une carte ne recalcule pas les
   matrices.
2. **Onglets dans la page** (Analyse / Pool) : moins de place perdue, mais @pj35 veut le pool « sur le côté » de
   l'analyse. Écartée.
3. **Garder l'écran Suggestions et y lier la page** : deux endroits pour la même chose. Écartée par @pj35.

## 4. Détail

### 4.1 Ordre de pick : `src/analysis/pick_order.py` (nouveau)

```python
PICK_SEQUENCE = "BRRBBRRBBR"

@dataclass(frozen=True)
class Pick:
    slot: int        # 1 à 10
    side: str        # "blue" ou "red"
    lane: str

def pick_order(matchups: Mapping[str, Mapping[str, float]],
               synergies: Mapping[str, Mapping[str, float]]) -> List[Pick]: ...
```

- Programmation dynamique de §1.3 sur `scraping_config.LANES`, case absente = 0 ; égalité de valeur : le premier
  poste dans l'ordre de `LANES`.
- Matrice vide : `[]`.
- Tests (`tests/test_pick_order.py`) : matrice où un seul poste a une diagonale forte → il est pické en dernier des
  deux côtés ; matrices nulles → ordre de `LANES` ; dix picks, cinq postes par côté ; égalité déterministe.

### 4.2 Rôle mémorisé : `src/user_prefs.py`

Clé `meta_lane` ajoutée à `_KEPT_KEYS` ; `load_meta_lane() -> str` (`"top"` si absente ou hors `_KNOWN_LANES`),
`save_meta_lane(lane) -> bool` (`False` sans écrire hors `_KNOWN_LANES`). Tests dans `tests/test_user_prefs.py`.

### 4.3 Page : `src/client/meta_poste.py` (renomme `blindabilite.py`), route `GET /meta`

- `meta_view(data, champions, lane, pool_champions, picks) -> dict` : `_cell` reçoit un drapeau `mine` (ligne ou
  colonne du rôle) ; l'histogramme marque `mine` les champions de `pool_champions` (sans casse) ; `picks` formatés
  (`slot`, côté, libellé du poste, `mine`).
- `GET /meta?poste=` : poste valide → `save_meta_lane` ; absent ou invalide → `load_meta_lane()`. Calcule
  `compute_blindability`, `pick_order(matchups, synergies)`, le pool résolu du poste (`resolve_pool_for_lane`, comme
  l'écran Pool), et la vue du panneau (§4.4).
- `GET /blindabilite` → redirection 303 vers `/meta` (avec `poste` s'il est donné) ; `GET /pool/suggestions` idem.
- `NAV` : `NavItem("meta", "Méta du poste", "ᛒ", 120, "/meta")` à la place de Blindabilité.
- Tests : renommer et adapter les tests `/blindabilite` de `tests/test_client_coaching_routes.py`.

### 4.4 Panneau latéral : `src/client/pool_swipe.py`, partiel `partials/meta_aside.html`

- Reprendre de `d6e5956` : `_size`, `_mode`, cache `_GENERATED` (borne `POOL_GEN_CACHE_MAX` = 32 dans
  `PoolStatisticsConfig`), `generate`, `cached_generation`, `require_generated`, `_generated_view`,
  `create_generated`, `exclude`, `_stack` avec `excluded`. `swipe_view` devient `aside_view(manager, db_path, lane,
  champions, notice, size, mode)` sans les onglets de poste (le rôle vient de la page).
- Routes POST sous `/meta/` : `generer`, `creer`, `exclure`, `prendre`, `passer` ; champs lus dans le corps du
  formulaire puis la query (`form_fields` de `d6e5956`) ; réponse = `partials/meta_aside.html` seul (cible
  `#meta-aside`). `creer` : `save_custom_pools(recalculate_bans=False)` puis `save_role_pool` ; `prendre` garde le
  chemin de SPEC-49 (`forget_bans`, commande `pool <nom>` si pool par défaut).
- Supprimer : routes `/pool/suggestions/*`, `pool_suggestions.html`, `partials/pool_suggestions_body.html`.
  `pool_swipe.js` est gardé (sélecteurs `[data-swipe]` inchangés).
- Liens : « Suggestions » de `partials/pool_body.html` → `/meta?poste=<lane>` (libellé « Méta du poste ») ;
  « Voir les suggestions de pool » de `partials/donnees_etat.html` → `/meta`.
- Tests : reprendre ceux de `d6e5956` et de `tests/test_client_pool_swipe.py` sur les nouvelles routes ; le test
  de régression `test_regression_client_base_corrompue.py` vise `/meta`.

### 4.5 Gabarit : `meta_poste.html`, `style.css`

- En-tête : titre « Méta du poste », puces des cinq postes (le choisi `aria-current`), puis la séquence des 10
  picks en deux lignes (Blue, Red), les picks du poste choisi en surbrillance.
- Grille `.meta-grid` : colonne principale (matrices puis histogramme, comme aujourd'hui) et `<aside id="meta-aside">`
  (générateur puis cartes, contenu de 8596618 et de la carte de SPEC-49). Une colonne sous 1 100 px.
- Surbrillance : `td.is-mine` (contour de la couleur du poste, sans changer la teinte verte ou rouge de la case) ;
  `th` du rôle en gras ; champion du pool dans l'histogramme : `.is-mine` (anneau). Légende d'une ligne sous chaque
  bloc.
- Sans JS ajouté ; animation de carte inchangée (`pool_swipe.js`, `prefers-reduced-motion`).

### 4.6 Constantes

| Constante | Valeur | Origine |
|---|---|---|
| `POOL_GEN_CACHE_MAX` | 32 | repris de `d6e5956` |
| `META_ASIDE_BREAKPOINT_PX` (CSS, commentaire dans `style.css`) | 1 100 | largeur où les deux colonnes tiennent, à régler à la recette |

## 5. Tâches

| # | Tâche | Pts | Dépend de |
|---|---|---|---|
| 252 | `src/analysis/pick_order.py`, `tests/test_pick_order.py` | 3 | — |
| 253 | `user_prefs` : `meta_lane`, `load_meta_lane`, `save_meta_lane`, tests | 1 | — |
| 254 | `meta_poste.py` (renomme `blindabilite.py`), `GET /meta`, redirections, `NAV`, tests | 3 | 252, 253 |
| 255 | Panneau latéral : reprise de `d6e5956` en `aside_view`, routes `/meta/*`, suppression de l'écran Suggestions, liens, tests | 5 | 254 |
| 256 | `meta_poste.html`, `partials/meta_aside.html`, styles (grille, surbrillance, séquence) | 3 | 255 |
| 257 | Clôture : exe vérifié, `PROJECT_STRUCTURE.md`, `CHANGELOG.md`, statuts SPEC-49, SPEC-50 et SPEC-51, README des specs, `TODO.md` | 1 | 256 |

## 6. Critères d'acceptation

1. `python -m pytest tests/ -v` vert, avec les tests des tâches 252 à 256.
2. Sur `data/db.db` (scrape du 1er nov.), `pick_order` rend la séquence de §1.3 : B jungle, R jungle, R mid,
   B mid, B bot, R bot, R support, B top, B support, R top.
3. `GET /meta?poste=top` : 9 cases `is-mine` dans Adversaires (ligne et colonne top) et 8 dans Alliés (pas de
   case top-top), picks 8 et 10 en surbrillance, champions du pool désigné au top marqués dans l'histogramme
   (test 254).
4. `GET /meta` sans poste rouvre le dernier poste choisi ; Top au premier lancement (tests 253, 254).
5. `GET /blindabilite` et `GET /pool/suggestions` redirigent (303) vers `/meta` ; `grep -rn "pool/suggestions"
   src/client/templates` ne trouve rien.
6. Dans le panneau, au top, Gangplank et Fiora exclus, moyenne, taille 5 : Malphite, Pantheon, Riven, Shen, Urgot
   (critère 3 de SPEC-50, vérifié hors suite sur `data/` tant que les sauvegardes du 20 oct. et du 6 oct. existent).
7. Prendre ou passer une carte ne rend que `#meta-aside` (le corps de la réponse ne contient pas `role-matrix`).
8. `PoolEvaluator` et `src/analysis/pool_generator.py` inchangés : `git diff --stat` vide sur ces deux fichiers.
9. `CHANGELOG.md` (`[Unreleased]`), statuts de SPEC-49, SPEC-50 et SPEC-51, `docs/specs/README.md` à jour.

**Vérification de bout en bout** : dans le client relancé, menu Coaching → « Méta du poste » ; Top : cases du top
entourées dans les deux matrices, picks 8 et 10 en surbrillance, les champions de QUINTET TOP marqués dans
l'histogramme ; exclure Gangplank et Fiora, « Générer », « Créer le pool » ; prendre une carte ; rouvrir la page
depuis le menu : elle revient sur Top. Recette par @pj35 (pas de sonde de fenêtre réelle sans son accord).

## 7. Hors périmètre

- ❌ Ordre de pick avec bans, flex picks ou ordre imposé par le lobby : la séquence est celle des matrices, sans
  ces contraintes (§1.3).
- ❌ Moyenne de l'ordre de pick sur plusieurs scrapes : il est calculé sur le scrape actuel, comme les matrices.
- ❌ Changement du score des pools ou du générateur : repris tel quel de SPEC-50.
- ❌ Maîtrise : écartée des suggestions par @pj35 le 2026-11-03 (SPEC-49).
