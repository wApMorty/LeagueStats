# SPEC-49 — Suggestions de pool à swiper

**Statut** : ✅ Livrée le 2026-11-03, recette @pj35 à faire. Les arbitrages de §2 ont été validés le 2026-11-03, au lancement de l'implémentation. Deux écarts : les comptes de cartes ne s'affichent que pour le poste ouvert (calculer les cinq postes prend 0,5 à 0,7 s), et `pool_swipe.js` est chargé par `base.html` comme les autres scripts d'écran. Le 2026-11-06, l'écran est remplacé par le panneau de la page Méta du poste ([SPEC-51](SPEC-51-meta-du-poste.md)) ; les cartes et leurs routes y passent sous `/meta/`.

**Origine** : @pj35, 2026-11-03 — « Je pense au contraire qu'il serait intéressant de proposer une mise à jour du
pool à chaque mise à jour des données », puis « retire la maîtrise de l'équation, et fais un écran un peu interactif
façon Tinder (swipe/pass) pour chaque suggestion, afin de mettre à jour le pool au fur et à mesure ».

**Effort** : ~1,5 jour, 5 tâches, 12 pts (§5).

---

## 1. Constat

### 1.1 Rien ne propose de changer de pool

Les pools ne changent que par l'écran Pool (`src/client/pools.py:121`, actions `ajouter` et `retirer`) ou la console.
Un pool est désigné par poste dans `user_prefs.json` (`pools_by_role`, SPEC-44) ; `resolve_pool_for_lane`
(`src/pool_manager.py:478`) donne le pool joué à un poste. Le top de @pj35 est TRIO TOP (Malphite, Shen, Olaf) depuis
le 2026-11-01.

`PoolEvaluator` (`src/analysis/pool_value.py:26`) note déjà un pool sur une lane, sans maîtrise :
`value(c, e) = force(c) + duel(c, e)`, `counter_value(pool)` (`pool_value.py:66`) et `strength` (force rétrécie).
Ses adversaires sont les champions joués sur la lane, pondérés par leur popularité (`enemies`, `popularity`).

### 1.2 Avec la maîtrise, l'avis serait muet

Rejeu du 2026-11-03 sur les scrapes du 6 oct., 20 oct. et 1er nov. : avec la maîtrise (`MasteryTerm`), le meilleur
échange d'un champion de TRIO TOP vaut +0,00 aux trois scrapes. Olaf (+5,6 pts de maîtrise) gagne chaque duel, et
Malphite (+3,1) le relaie. D'où la décision de @pj35 : pas de maîtrise dans les suggestions.

### 1.3 La pile sans maîtrise, aujourd'hui

Mesure du 2026-11-03, vrai `PoolEvaluator` sur la base du 1er nov. Objectif `J = ½ · counter_value + ½ · max force`
(§4.1), candidats joués dans au moins 1 % des parties de la lane, un échange à la fois :

| Poste, pool | Candidats | Échanges à gain > 0 | Dont ≥ 0,2 pt | Meilleurs | Calcul |
|---|---|---|---|---|---|
| Top, TRIO TOP | 36 | 20 | 1 | Gangplank pour Olaf +0,26, Darius pour Olaf +0,15, Ornn pour Olaf +0,15 | 278 ms |
| Mid, Mid (5) | 30 | 79 | 9 | Vex pour Viktor +0,95, Katarina pour Viktor +0,27 | 94 ms |

Un même entrant revient pour chaque sortant (Gangplank pour Olaf, Malphite ou Shen ; Vex pour les cinq) : la pile
doit regrouper par entrant (§2).

Hors rôle, l'échantillon est trop faible : sans filtre de popularité, Zoe (+2,4) et Kassadin (+3,1) dominaient le
rejeu du top. Le bruit entre deux scrapes vaut 0,2 à 0,4 pt sur la valeur d'un trio (mesure du 2026-11-01).

## 2. Objectif et arbitrages

Après chaque mise à jour des données, un écran présente une à une des cartes « prends X à la place de Y » pour le
pool de chaque poste ; un swipe à droite applique l'échange, un swipe à gauche passe la carte.

| Sujet | Décision |
|---|---|
| Maîtrise | **Validé (@pj35, 2026-11-03)** : retirée de l'équation, valeurs de `PoolEvaluator` seules. |
| Forme de l'écran | **Validé (@pj35, 2026-11-03)** : une carte à la fois, accepter (droite) ou passer (gauche), le pool est mis à jour au fil des cartes. |
| Candidats | **Validé (@pj35, 2026-11-03)** : tous les champions joués dans au moins 1 % des parties de la lane (`POOL_SWIPE_MIN_POPULARITY`), hors pool. Les passes écartent ceux que @pj35 refuse. |
| Durée d'un pass | **Validé (@pj35, 2026-11-03)** : jusqu'à la mise à jour des données suivante (date `FreshnessInfo.last_update`). |
| Seuil | **Validé (@pj35, 2026-11-03)** : toute carte à gain > 0, triée par gain, avec l'étiquette « sous le bruit » sous `POOL_SWIPE_NOISE_PT` (0,2 pt). |
| Une carte par entrant | **À valider** : chaque champion candidat ne donne qu'une carte, avec le sortant qui maximise le gain. Un pass écarte l'entrant pour ce poste. |
| Objectif | **À valider** : `J = ½ · counter_value + ½ · max force`, comme la mesure du 2026-11-02 (s = 0,5, sans donnée d'ordre de pick). Sans tirage ni disponibilité (bans). |
| Échange seulement | **À valider** : la taille du pool ne change pas (pas d'ajout ni de retrait seuls). Un pool vide n'a pas de pile. |
| Postes | **À valider** : les cinq postes, chacun sur le pool que donne `resolve_pool_for_lane`. Un pool système (« All Top Champions ») ne s'édite pas : l'écran le dit et propose de le dupliquer, sans carte. |
| Après un accept | **À valider** : la pile se recalcule sur le nouveau pool ; les passes restent. L'échange suit le chemin de l'écran Pool : `save_custom_pools(recalculate_bans=False)`, `forget_bans`, commande `pool <nom>` au Live Coach si c'est le pool par défaut. |
| Accès | **À valider** : un bouton « Suggestions (N) » sur l'écran Pool, et un lien sur l'écran Données après une mise à jour réussie. Pas de fenêtre qui s'ouvre seule. |

## 3. Approches considérées

1. **Avis à seuil sur l'écran Pool** : une ligne « meilleur échange », un avis au-dessus de 0,2 pt. Proposée le
   2026-11-03 ; avec la maîtrise, muette aux trois scrapes (§1.2). Remplacée par la demande de @pj35.
2. **Avis confirmé sur deux mises à jour** : moins sensible au bruit, mais demande une table d'historique et retarde
   d'un patch. Écartée : le seuil se lit sur la carte (« sous le bruit »), @pj35 décide.
3. **Retenue : pile de cartes à swiper.** Calcul à la demande (moins de 0,3 s par poste, §1.3), aucun stockage
   hormis les passes, dans `user_prefs.json`. Pas de migration.

## 4. Détail

### 4.1 Calcul : `src/analysis/pool_swipe.py` (nouveau)

```python
@dataclass(frozen=True)
class SwapCard:
    lane: str
    incoming: str
    outgoing: str
    gain: float          # J(pool après) − J(pool), en points de winrate
    counter_gain: float  # part contre-pick (½ · Δcounter_value)
    blind_gain: float    # part blind (½ · Δmax force)
    below_noise: bool    # gain < POOL_SWIPE_NOISE_PT
    wins: List[Tuple[str, float]]   # 3 adversaires où l'entrant fait le plus gagner le pool (Δ max value pondéré)
    losses: List[Tuple[str, float]] # 3 adversaires où le pool perd le plus

def pool_score(evaluator: PoolEvaluator, pool: Sequence[str]) -> float: ...
def swap_cards(evaluator: PoolEvaluator, pool: Sequence[str], passed: Collection[str]) -> List[SwapCard]: ...
```

- `pool_score` = `0.5 * evaluator.counter_value(pool) + 0.5 * max(evaluator.strength.get(c.lower(), 0.0) for c in pool)`.
- Candidats : `evaluator.enemies` dont la popularité ≥ `POOL_SWIPE_MIN_POPULARITY`, hors pool, hors `passed`
  (comparaison sans casse).
- Pour chaque candidat, le sortant qui maximise le gain ; égalité : le premier du pool. Ne garder que gain > 0,
  trier par gain décroissant puis par nom.
- Pool vide ou évaluateur sans adversaires : `[]`.

### 4.2 Passes : `src/user_prefs.py`

Clé brute `pool_swipe` ajoutée à `_KEPT_KEYS` : `{"version": "<last_update ISO>", "passed": {"top": ["Gangplank"]}}`.

```python
def load_swipe_passes(version: str) -> Dict[str, List[str]]: ...   # {} si la version diffère, absente ou illisible
def save_swipe_pass(lane: str, champion: str, version: str) -> bool: ...  # repart de {} si la version change
```

Lane hors `_KNOWN_LANES` : `False` sans écrire. La version vient de `get_freshness_info(db_path).last_update`
(`src/data_freshness.py:49`), `"inconnue"` si absente.

### 4.3 Client : `src/client/pool_swipe.py` (nouveau) et routes dans `src/client/app.py`

- `swipe_view(manager, db, lane, version) -> dict` : pool résolu (`resolve_pool_for_lane`, préférences lues comme
  `pools_view`), `editable`, la carte du dessus et le nombre de cartes restantes par poste.
- `GET /pool/suggestions?poste=<lane>` (défaut : top) : écran `pool_suggestions.html`.
- `POST /pool/suggestions/accepter?poste=&entrant=&sortant=` : refus (200, `notice`) si la carte n'est plus dans la
  pile recalculée ou si le pool est un pool système ; sinon l'échange, en gardant l'ordre du pool (l'entrant prend
  la place du sortant), puis le chemin de `pool_action` (`save_custom_pools(recalculate_bans=False)`,
  `forget_bans`, commande `pool` si pool par défaut).
- `POST /pool/suggestions/passer?poste=&entrant=` : `save_swipe_pass`.
- Les deux POST renvoient le corps partiel `partials/pool_suggestions_body.html` (htmx), calculé dans `in_thread`.
- Bouton « Suggestions (N) » sur `partials/pool_body.html` pour le poste du pool ouvert ; lien « Voir les
  suggestions de pool » dans `partials/donnees_etat.html` quand le dernier run a réussi.

### 4.4 Écran : `pool_suggestions.html`, `static/pool_swipe.js`, `style.css`

- Onglets des cinq postes (compte de cartes par poste), le pool courant en puces, une carte : entrant ← sortant
  (icônes `Champions`), gain total et ses deux parts, étiquette « sous le bruit », 3 duels gagnés et 3 perdus.
- Deux boutons (« Passer », « Prendre ») qui font les POST ; le glisser (pointer events) au-delà de
  `POOL_SWIPE_DRAG_PX` déclenche le bouton du côté ; flèches gauche et droite au clavier. Le JS ne fait que déclencher
  les boutons : sans lui, l'écran marche aux boutons.
- Animation de sortie de carte désactivée sous `prefers-reduced-motion` et sous Motion `reduit` (`motion.js`).
- Pile vide : « Aucun échange ne fait gagner ce pool sur les données du <date> ».

### 4.5 Constantes (`PoolStatisticsConfig`, `src/config_constants.py`)

| Constante | Valeur | Origine |
|---|---|---|
| `POOL_SWIPE_MIN_POPULARITY` | 0,01 | §1.3 : sous 1 %, des hors-rôle à petit échantillon dominent |
| `POOL_SWIPE_NOISE_PT` | 0,2 | bruit entre scrapes sur la valeur d'un trio, 0,2 à 0,4 pt (2026-11-01) |
| `POOL_SWIPE_DRAG_PX` | 80 | glisser minimal, à régler à la recette |

### 4.6 Tests

- `tests/test_pool_swipe.py` : évaluateur factice (valeurs connues) — gain et sortant optimal, une carte par
  entrant, filtre de popularité, passes, `below_noise`, pool vide, tri.
- `tests/test_user_prefs.py` : passes par version, version changée = remise à
  zéro, lane inconnue, clés voisines conservées.
- `tests/test_client_pool_swipe.py` : `TestClient` sur base et préférences de `tests/conftest.py` — accepter échange
  et écrit `champion_pools.json` sous `tmp_path`, carte périmée refusée, pool système refusé, passer écrit la pass,
  commande `pool` déposée pour le pool par défaut, rendu de l'écran sans JS (boutons présents).

## 5. Tâches

| # | Tâche | Pts | Dépend de |
|---|---|---|---|
| 241 | `src/analysis/pool_swipe.py` (`SwapCard`, `pool_score`, `swap_cards`), constantes, `tests/test_pool_swipe.py` | 3 | — |
| 242 | `user_prefs` : clé `pool_swipe`, `load_swipe_passes`, `save_swipe_pass`, tests | 2 | — |
| 243 | `src/client/pool_swipe.py`, routes `GET`/`POST` des suggestions, `tests/test_client_pool_swipe.py` | 3 | 241, 242 |
| 244 | `pool_suggestions.html`, partiel, `pool_swipe.js`, styles, bouton sur l'écran Pool, lien sur l'écran Données | 3 | 243 |
| 245 | Clôture : exe vérifié, `PROJECT_STRUCTURE.md`, `CHANGELOG.md`, statuts, README des specs, `TODO.md` | 1 | 244 |

## 6. Critères d'acceptation

1. `python -m pytest tests/ -v` vert, avec les tests des tâches 241 à 244.
2. `swap_cards` sur TRIO TOP et la base du 1er nov. donne 20 cartes au plus, une par entrant, Gangplank en tête
   (§1.3), sans champion sous 1 % de popularité.
3. `grep -i mastery src/analysis/pool_swipe.py src/client/pool_swipe.py` ne trouve rien.
4. Un pass sur Gangplank au top le retire de la pile du top jusqu'à ce que `last_update` change (test 242 et 243).
5. Accepter une carte change le pool dans `champion_pools.json`, garde sa taille et son ordre, efface ses bans
   précalculés et dépose `pool <nom>` si c'est le pool par défaut (test 243).
6. L'écran marche sans JS (boutons) ; au clavier, les flèches gauche et droite passent et prennent.
7. `CHANGELOG.md` (`[Unreleased]`), statut de cette spec et `docs/specs/README.md` à jour.

**Vérification de bout en bout** : dans le client lancé, écran Pool, « Suggestions », poste Top : la première carte
est Gangplank pour Olaf (+0,26) ; passer, puis prendre la suivante ; l'écran Pool montre le pool changé, et la
prochaine draft charge ce pool (`[INFO] Poste …`). Recette par @pj35 (pas de sonde de fenêtre réelle sans son
accord).

## 7. Hors périmètre

- ❌ Maîtrise dans le score : écartée par @pj35 le 2026-11-03 (§1.2).
- ❌ Disponibilité (bans, picks alliés) et tirage dans le score : pas de donnée d'ordre de pick, gain non mesuré.
- ❌ Ajout ou retrait seul d'un champion : la taille du pool reste celle choisie par @pj35.
- ❌ Historique des suggestions et confirmation sur deux mises à jour (approche 2).
- ❌ Ouverture automatique de l'écran après une mise à jour.
