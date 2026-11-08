# SPEC-53 — Rappel de place en draft : quelle place de pick demander

**Statut** : 🟡 Rédigée le 2026-11-08, arbitrages validés par @pj35 le même jour (§2).

**Origine** : @pj35, 2026-11-08 — « Maintenant qu'on a défini l'ordre de draft optimal, tu pourrais ajouter un
rappel pendant la draft pour me dire quelle place je dois demander ? » Suite de SPEC-51 (`pick_order`).

**Effort** : ~1,5 jour, 5 tâches, 12 pts (§5).

---

## 1. Constat

### 1.1 Ce que la draft sait déjà (SPEC-24)

- `DraftState.pick_order` (`src/draft/state_parser.py:136`) : rang de pick 1 à 10 de chaque cellule, dans l'ordre
  des actions `pick` de la session, connu dès le début de la sélection.
- `DraftState.swaps` (`state_parser.py:143`) : `pickOrderSwaps` et `positionSwaps`, `{cellId, id, state}`.
  Relevé de SPEC-24 §1 : chaque entrée désigne l'autre
  joueur, `state` ∈ `AVAILABLE`, `SENT`, `RECEIVED`, `INVALID` ; un échange d'ordre accepté échange les cellules.
- `DraftState.ally_positions` : poste assigné par le LCU (`utility` → `support` par `LCU_POSITION_TO_LANE`).
- Écran de draft : boutons « ⇄ ordre » / « ✕ ordre » par allié (`_swap_buttons`, `src/client/draft_view.py:154`),
  bandeau des demandes reçues (`swap_requests`, `draft_view.py:194`), route `POST /draft/swap/{kind}/{action}`.
  Le conseil existant (`SnapshotSwapAdvice`, `src/draft/swap_advice.py`) ne couvre que l'échange de rôle.

Fixture `tests/fixtures/lcu_forms/session_swaps.json` : je suis la cellule 4, top, côté bleu (la cellule 0 a le
rang 1) ; rangs 0→1, 1→4, 2→5, 3→8, 4→9 pour les alliés ; échange d'ordre `RECEIVED` de la cellule 1, les autres
`INVALID`. Les trois premiers picks y sont déjà verrouillés (cellules 0, 5 et 6, `completed`) : les échanges
d'ordre restent listés **après** le premier pick, contrairement à ce que SPEC-24 §1 laissait entendre (« jusqu'au
premier pick »).

### 1.2 L'ordre de pick conseillé et son coût

`pick_order` (`src/analysis/pick_order.py`, SPEC-51) rend la séquence B R R B B R R B B R sur les matrices de
`compute_blindability`. Sur la base du 1er nov. : B jungle, R jungle, R mid, B mid, B bot, R bot, R support,
B top, B support, R top. Mesure du 2026-11-08 : `compute_blindability` 1,97 s, `pick_order` 2 ms. La boucle de
draft ne peut pas payer 2 s.

`run_pipeline` (`src/pipeline.py`) recalcule après chaque scrape, et seul avec `--recompute-only` : scores, bans,
`last_recompute_utc`, K de shrink dans `db_meta` (`Database.set_meta`, `src/db.py:340`).

## 2. Objectif et arbitrages

Pendant la sélection, tant que les échanges d'ordre sont possibles et que je n'ai pas verrouillé, l'écran de draft dit quelle place de pick
viser pour mon poste et mon côté, met en avant l'échange qui m'en rapproche, et dit si une demande reçue me
rapproche ou m'éloigne de cette place.

| Sujet | Décision |
|---|---|
| Contenu | **Validé (@pj35, 2026-11-08)** : place visée et blind ou counter, ex. « Top côté bleu : blind, vise le n° 8 (tu es n° 9) » ; « Tu es à ta place conseillée » si c'est déjà le cas. |
| Repli | **Validé (@pj35, 2026-11-08)** : si l'échange vers la place exacte n'est pas disponible, l'échange disponible qui rapproche le plus de la place visée. |
| Mise en avant | **Validé (@pj35, 2026-11-08)** : bouton « ⇄ ordre » de l'allié concerné marqué « conseillé » ; bandeau des demandes reçues annoté (rapproche / éloigne) ; ligne `[INFO]` dans la console du Live Coach. |
| Durée | **Validé (@pj35, 2026-11-08)**, « tant qu'on peut encore échanger » : tant que la session liste au moins un échange d'ordre et que mon propre pick n'est pas verrouillé. La règle « jusqu'au premier pick » proposée à l'interview est contredite par le relevé (§1.1). |
| Calcul | **Validé (@pj35, 2026-11-08)** : la séquence est calculée à la mise à jour des données (étape de recalcul de `run_pipeline`, scrape ou `--recompute-only`) et stockée dans `db_meta` ; la draft la lit. Base sans séquence stockée : pas de rappel. |

## 3. Approches considérées

1. **Retenue : séquence stockée à la mise à jour.** Lecture instantanée en draft, un seul calcul par scrape.
   Une base d'avant cette version n'a pas de rappel : `python scripts/update_all.py --recompute-only` la complète
   sans scrape.
2. **Fil séparé au lancement du Live Coach** : sans changement de la base, mais un fil de plus à arrêter
   proprement et 2 s de CPU à chaque lancement. Écartée par @pj35.
3. **Calcul au début de chaque draft** : la boucle se fige 2 s par draft. Écartée.

## 4. Détail

### 4.1 Stockage : `src/analysis/pick_order.py`, `src/pipeline.py`

```python
PICK_ORDER_META_KEY = "pick_order"

def to_meta(line: Sequence[Pick]) -> str: ...            # JSON [["blue", "jungle"], ["red", "jungle"], …]
def from_meta(value: Optional[str]) -> List[Pick]: ...   # [] si absente, illisible ou pas 10 picks valides
```

Dans `run_pipeline`, après l'écriture des K de shrink, dans les deux chemins : `compute_blindability` puis
`pick_order` sur la base, `db.set_meta(PICK_ORDER_META_KEY, to_meta(line))` si la ligne n'est pas vide.
Best-effort : une exception est journalisée en `WARNING` et n'échoue pas le pipeline. Tests :
`tests/test_pick_order.py` (aller-retour, valeurs invalides), `tests/test_pipeline*.py` (clé écrite en
`recompute_only` sur une base de test, exception ignorée).

### 4.2 Conseil : `src/draft/pick_advice.py` (nouveau, pur)

```python
@dataclass(frozen=True)
class PickAdvice:
    lane: str
    side: str            # "blue" | "red"
    mode: str            # "blind" | "counter" : mon pick avant ou après le même poste adverse dans la ligne
    target: int          # rang visé, 1 à 10
    current: int         # mon rang
    cell_id: Optional[int]   # allié avec qui demander l'échange d'ordre ; None s'il n'y en a pas
    target_cell: bool    # True si cet échange donne exactement la place visée

def pick_advice(line, lane, my_cell, ranks, swaps) -> Optional[PickAdvice]: ...
def request_effect(advice, ranks, cell_id) -> Optional[str]: ...   # "closer" | "farther" | None
```

- Côté : bleu si une cellule alliée a le rang 1, sinon rouge (`ranks` = `DraftState.pick_order` restreint aux
  alliés). `target` = slot du `Pick` de la ligne pour (côté, poste) ; `mode` = « blind » si ce slot précède celui
  du même poste pour l'autre côté.
- `cell_id` : parmi les échanges `pick_order` à l'état `AVAILABLE`, l'allié dont le rang est le plus proche de
  `target`, seulement s'il rapproche (|rang − target| < |current − target|) ; égalité : le rang du bon côté
  (plus tard pour un counter, plus tôt pour un blind). Déjà à la place visée : `cell_id` None.
- `request_effect` : pour une demande `RECEIVED`, « closer » si le rang de l'autre rapproche de `target`,
  « farther » s'il éloigne, None s'il ne change rien.
- `None` sans ligne, sans poste, sans rang pour moi.
- Tests (`tests/test_pick_advice.py`) : côté par le rang 1 ; blind / counter ; place exacte disponible ; repli
  au plus proche ; échange qui éloigne jamais conseillé ; déjà à sa place ; fixture `session_swaps.json` (top
  bleu, n° 9, vise n° 8 ; cellule 3 `INVALID` donc pas d'échange conseillé ; demande reçue de la cellule 1,
  n° 4 → « farther »).

### 4.3 Draft : `src/draft/recommendations.py`, `src/draft/snapshot.py`

- `SnapshotPickAdvice` (champs de `PickAdvice` + `request_effects: Dict[int, str]`) et
  `DraftSnapshot.pick_advice: Optional[SnapshotPickAdvice]`.
- `_pick_advice(state)` : ligne lue par `from_meta(db.get_meta(PICK_ORDER_META_KEY))` une fois par session de
  sélection (cache sur l'identifiant de partie ou la première cellule vue), poste = `ally_positions[local]`
  converti par `LCU_POSITION_TO_LANE`. `None` si la session ne liste aucun échange `pick_order` ou si mon action
  `pick` est complétée (`DraftState` : mon pick verrouillé).
  Best-effort : toute exception rend `None` (boucle du Live Coach).
- Console : une ligne `[INFO] Place conseillée : …` quand le conseil change (clé : cible, rang, cellule).
- Tests (`tests/test_draft_pick_advice.py`) : snapshot porte le conseil sur la fixture (trois picks
  adverses et alliés déjà verrouillés) ; rien après mon propre pick ; rien sans échange d'ordre listé ; rien sans clé `pick_order` ; une base qui lève ne casse pas le snapshot ; ligne console unique.

### 4.4 Écran : `src/client/draft_view.py`, `partials/draft_stage.html`, `style.css`

- `pick_advice_view(snapshot) -> Optional[dict]` : texte « Top côté bleu : blind, vise le n° 8 (tu es n° 9) » ou
  « Top côté bleu : tu es à ta place conseillée (n° 8) ».
- `_swap_buttons` : le bouton « ⇄ ordre » de `cell_id` devient « ⇄ ordre · conseillé », titre « Te donne le n° X,
  place conseillée » (ou « te rapproche de ta place conseillée, n° X »), classe `d-swap-advised`.
- `swap_requests` : pour un échange d'ordre reçu, ajoute « · te rapproche de ta place conseillée » ou « · t'éloigne
  de ta place conseillée ».
- Gabarit : une ligne `d-pick-advice` (`role="status"`) au-dessus des équipes, absente sans conseil.
- Tests (`tests/test_client_draft*.py`) : texte, bouton marqué, bandeau annoté, rien sans conseil.

## 5. Tâches

| # | Tâche | Pts | Dépend de |
|---|---|---|---|
| 262 | `to_meta` / `from_meta`, étape best-effort de `run_pipeline`, tests | 2 | — |
| 263 | `src/draft/pick_advice.py` (`PickAdvice`, `pick_advice`, `request_effect`), tests | 3 | — |
| 264 | `SnapshotPickAdvice`, `_pick_advice` dans les recommandations, console, tests | 3 | 262, 263 |
| 265 | Écran de draft : ligne de rappel, bouton conseillé, bandeau annoté, tests | 3 | 264 |
| 266 | Clôture : exe vérifié, `PROJECT_STRUCTURE.md`, `CHANGELOG.md`, statut, README des specs, `TODO.md` | 1 | 265 |

## 6. Critères d'acceptation

1. `python -m pytest tests/ -v` vert, avec les tests des tâches 262 à 265.
2. Après `python scripts/update_all.py --recompute-only`, `db_meta.pick_order` décode en la séquence de SPEC-51
   §1.3 sur la base du 1er nov. (vérifié sur une copie de `data/db.db`, jamais sur l'original).
3. Sur `session_swaps.json` : conseil « top, bleu, blind, vise 8, n° 9 », aucun échange conseillé (cellule 3
   `INVALID`), demande de la cellule 1 annotée « t'éloigne » (tests 263 et 265).
4. Le conseil reste après les premiers picks des autres (fixture) et disparaît après mon propre pick ou sans
   échange d'ordre listé (test 264).
5. Une exception dans le conseil ne change rien d'autre au snapshot (test 264).
6. `CHANGELOG.md` (`[Unreleased]`), statut de cette spec et `docs/specs/README.md` à jour.

**Vérification de bout en bout** : `python scripts/update_all.py --recompute-only`, puis une partie classée : dès
la sélection, la ligne « … vise le n° X (tu es n° Y) » s'affiche, le bouton « ⇄ ordre · conseillé » est sur le
bon allié, et la console du Live Coach l'écrit. Recette par @pj35 (pas de sonde de fenêtre réelle sans son accord).

## 7. Hors périmètre

- ❌ Échange demandé automatiquement : la demande reste un clic de @pj35, comme les autres échanges (SPEC-24).
- ❌ Ordre tenant compte des bans, des flex picks ou des champions déjà survolés : la ligne est celle des
  matrices (SPEC-51 §7).
- ❌ Conseil d'échange de rôle chiffré par l'ordre de pick : `role_swaps` reste inchangé.
- ❌ Moyenne de la séquence sur plusieurs scrapes : celle du scrape stocké, comme la page Méta du poste.
