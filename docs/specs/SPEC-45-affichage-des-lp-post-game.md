# SPEC-45 — Affichage des LP sur l'écran post-game

**Statut** : ✅ Livrée le 2026-10-28 (tâches 219 à 222), recette validée par @pj35 le 2026-11-10 (`docs/RECETTE_2026_11.md`). Arbitrages validés par @pj35 le 2026-10-28 (§2).

**Origine** : @pj35, 2026-10-28 — « Il faut réparer l'affichage des LP sur l'écran post-game. » Symptôme
précisé en interview : le « + » et le « LP » sont gros, le nombre entre les deux est petit et gris.

**Effort** : ~1 jour, 4 tâches (§5).

---

## 1. Constat

Lu sur le code et sur `data/db.db` (lecture `mode=ro`) le 2026-10-28.

- **Le nombre est stylé comme la ligne de rang.** L'encart LP de la revue est
  `<b>+<span data-count>19</span> LP</b><span>Diamant II · 34 LP</span>`
  (`src/client/templates/partie.html:30`). La règle `.lp-gain span { font-size: 15px; color: var(--ink-2); }`
  (`src/client/static/style.css:902`), écrite pour la ligne de rang, attrape aussi le compteur logé dans le
  `<b>` : le nombre sort en 15 px gris, sans le dégradé de `.lp-gain b` (58 px, `background-clip: text`,
  `style.css:899-901`). C'est le symptôme décrit par @pj35.
- **Les LP sont bien capturées.** 199 parties classées dans `game_records` : 35 sans photo de rang, la plus
  récente le 2026-10-08 (avant SPEC-25 et son `PostGameWatcher`, toutes depuis ont leur photo). Les deltas
  relus sont cohérents d'une partie à l'autre (ex. 2 LP − 22 → Diamant III 80 le 2026-10-28).
- **Les LP arrivent parfois après l'ouverture de la revue.** La revue s'ouvre à l'événement `game_captured`
  (`src/coaching/capture.py:58-66`, `src/client/static/coaching.js:59-67`) et lit `rank_after_game` une seule
  fois (`src/client/review.py:466-474`). Pour 6 parties classées sur 199, la photo de rang est écrite 21 s à
  4 min après la capture de la partie (dernière : 8028429367, 2026-10-28, +21 s) : la revue n'a alors pas
  d'encart LP, et rien ne le rajoute.
- **Un delta nul s'affiche « +0 » en vert.** Deux photos à 0 LP en base : 8024448317 (remake, 155 s,
  `gameEndedInEarlySurrender` vrai dans le brut) et 8024541287 (défaite de 45 min, LP non retirées).
  `page["lp"]["gain"]` vaut `(lp_delta or 0) >= 0` (`review.py:471`) : l'encart dit « +0 LP » avec le
  dégradé de gain. La liste des parties dit aussi « +0 LP » (`review.py:173-175`, `signed`).

## 2. Objectif et arbitrages

La revue affiche le gain ou la perte de LP en entier et au bon style, y compris quand la photo de rang arrive
après l'ouverture de la page ; un delta nul est neutre.

| Sujet | Décision |
|---|---|
| Symptôme à corriger | **Validé (@pj35, 2026-10-28)** : le nombre minuscule (règle CSS trop large). |
| LP arrivées après l'ouverture de la revue | **Validé (@pj35, 2026-10-28)** : l'encart LP est mis à jour en place à l'arrivée de la photo, sans recharger la page ni rejouer la mise en scène (sceau, courbe). Seul le compteur du nouvel encart s'anime. |
| Delta de 0 LP | **Validé (@pj35, 2026-10-28)** : « 0 LP » en couleur neutre, avec « remake » si la partie a fini en remake ; même texte « 0 LP » dans la liste des parties. |

## 3. Approches considérées

Pour les LP tardives (le correctif CSS et le delta nul n'ont qu'une forme raisonnable) :

1. **Sujet de bus `rank_captured` + fragment htmx (retenue).** Le coach publie `rank_captured` quand une photo
   d'après-partie est écrite ; `coaching.js` recharge l'encart de la page affichée si c'est la même partie,
   depuis une route qui rend le seul fragment. Même schéma que `en_partie.js` et `en_partie_stage.html`.
   Coût : un sujet de plus sur la connexion SSE unique (aucune connexion en plus, voir
   `tests/regression/test_regression_sse_connection_budget.py`), une route, un partiel.
2. **Republier `game_captured`.** Aucune ligne côté client, mais la navigation vers `/postgame` rejoue toute la
   mise en scène et ramène sur la revue un joueur parti sur un autre écran. Écarté par l'arbitrage.
3. **Attendre les LP avant d'annoncer la partie.** Retarde la revue de toutes les parties pour 3 % d'entre
   elles, et une partie sans notification (rattrapage) attendrait pour rien. Écarté.

## 4. Détail

### 4.1 Correctif CSS (tâche 219)

`src/client/static/style.css:902` : `.lp-gain span` devient `.lp-gain > span` (la ligne de rang est un enfant
direct de `.lp-gain`, le compteur est dans le `<b>`). Rien d'autre ne change dans la règle.

Régression `tests/regression/test_regression_lp_counter_style.py` : lit `style.css`, vérifie qu'aucune règle `.lp-gain span` (descendant, sans `>`) n'existe et que
la règle de la ligne de rang cible `.lp-gain > span`. Rouge avant le correctif, vert après. Docstring au format
des autres régressions (symptôme, cause racine, correctif, prévention).

### 4.2 Delta nul et remake (tâche 220)

`src/client/review.py` : une fonction `lp_view(rank: Optional[dict], remake: bool) -> Optional[dict]`, seule
source de l'encart, appelée par `game_page` (remplace le bloc de `review.py:466-474`) et par la route de 4.3.

- `rank` vaut `None` → `None`.
- Sinon `{"delta", "tone", "value", "rank", "note"}` :
  - `tone` : `"gain"` si `lp_delta > 0`, `"loss"` si `< 0`, `"flat"` si `0` ou `None` ;
  - `delta` : `signed(lp_delta, 0)` si non nul, `"0"` si nul, `None` si `lp_delta` est `None` ;
  - `value` : `abs(lp_delta or 0)` ;
  - `rank` : inchangé (`f"{tier_name(rank)} · {rank['lp']} LP"`) ;
  - `note` : `"remake"` si `remake` et delta nul, sinon `None`.
- `remake` : `bool(me["stats"].get("gameEndedInEarlySurrender"))` sur le brut de la partie.

La clé `gain` disparaît au profit de `tone` : mettre à jour `partie.html` et le test
`tests/test_client_postgame.py::test_points_de_lp_de_la_partie`.

Gabarit (dans `partie.html` ; la tâche 221 le déplace dans le partiel de 4.3) : classe `lp-gain {{ tone }}` ;
signe `+` pour `gain`, `−` pour `loss`, rien pour `flat` ; « 0 LP » sans compteur pour `flat` ; la ligne de rang
suivie de « · remake » quand `note` est posée. La condition d'affichage devient `{% if g.lp and g.lp.delta %}`
→ `{% if g.lp and g.lp.delta is not none %}` (un « 0 » doit s'afficher).

`style.css` : `.lp-gain.flat b` en couleur neutre (même encre que le texte courant, `var(--ink)`, au lieu
d'un dégradé ; garder `background-clip: text` cohérent : `background-image: linear-gradient(var(--ink), var(--ink))`).

Liste des parties (`review.py:173-175`) : « 0 LP » pour un delta nul au lieu de « +0 LP ».

Tests (`tests/test_client_postgame.py`, `tests/test_client_parties.py`) : gain, perte, nul, nul avec remake,
`lp_delta` `None`, ligne de liste à 0.

### 4.3 LP arrivées après l'ouverture (tâche 221)

**Publication.** `src/coaching/capture.py`, `write_lp_snapshots` : quand `ranked.snapshot_after_game` renvoie
vrai et que le client est branché (`self._client_mode`), publier `rank_captured` avec `{"game_id": game_id}`
via le bus, sous `self._safely` (best-effort : un bus en panne n'interrompt pas le passage, comme
`_announce`). La publication au premier passage, avant la capture de la partie, est sans effet côté client
(aucune page de cette partie n'est affichée).

**Fragment.** Nouveau partiel `src/client/templates/partials/lp_gain.html` : l'encart de 4.2, enveloppé d'un
conteneur toujours présent `<div id="lp-slot" data-game="{{ game_id }}">…</div>` (vide si pas de LP).
`partie.html` l'inclut à la place des lignes 29-31.

**Route.** `src/client/app.py` : `GET /parties/{game_id}/lp` rend `partials/lp_gain.html` à partir de
`lp_view(repo.rank_after_game(game_id), remake)` (lecture en `mode=ro` comme `/parties/{game_id}` ; partie
inconnue → fragment vide, pas de 404, pour ne pas casser l'encart).

**Client.** `src/client/static/coaching.js` : `Sse.open("rank_captured", …)` ; si
`document.querySelector('#lp-slot[data-game="<id>"]')` existe, `htmx.ajax("GET", "/parties/<id>/lp",
{ target: slot, swap: "outerHTML" })`. Le `htmx:load` du fragment anime son compteur (`play`), sans toucher au
reste de la page. Aucun nouveau `fetch("/events")` (régression du budget SSE).

Tests :
- `tests/test_client_postgame.py` : une photo écrite par `write_lp_snapshots` en mode client publie
  `rank_captured` avec le `game_id` ; sans bus, rien n'est publié ; un bus en panne n'interrompt pas le passage ;
  une photo déjà écrite (`insert_rank_snapshot` renvoie faux) ne republie pas.
- Route : `/parties/{id}/lp` rend l'encart avec les LP, un `#lp-slot` vide sans photo, vide aussi pour une
  partie inconnue.
- `coaching.js` : le script reste valide (`test_coaching_js_est_valide`) et contient l'écouteur
  `Sse?.open("rank_captured"` ou `Sse.open("rank_captured"`.

Aucune constante nouvelle (`src/config_constants.py` inchangé), aucune migration.

## 5. Tâches

| # | Tâche | Pts | Dépend de |
|---|---|---|---|
| 219 | Correctif CSS `.lp-gain > span` + régression `test_regression_lp_counter_style.py` | 1 | — |
| 220 | `lp_view` : ton gain / perte / neutre, « 0 LP », mention remake, liste des parties + tests | 2 | 219 |
| 221 | LP tardives : `rank_captured`, partiel `lp_gain.html`, route `/parties/{id}/lp`, écouteur `coaching.js` + tests | 3 | 220 |
| 222 | Clôture : critères, `CHANGELOG.md`, statut, README des specs, `TODO.md` | 1 | 221 |

## 6. Critères d'acceptation

1. `python -m pytest tests/ -v` vert, avec les tests des tâches ci-dessus.
2. `tests/regression/test_regression_lp_counter_style.py` rouge sur le `style.css` d'avant (`git stash` du
   correctif), vert après ; commité avec le correctif.
3. `grep -n "\.lp-gain span" src/client/static/style.css` ne renvoie rien ; `grep -n "\.lp-gain > span"` renvoie
   la règle de la ligne de rang.
4. `lp_view` renvoie `tone` `"gain"`, `"loss"` et `"flat"` pour +18, −22 et 0 ; `note == "remake"` pour un
   delta nul sur une partie à `gameEndedInEarlySurrender` vrai (test).
5. La liste des parties affiche « 0 LP » pour un delta nul (test).
6. `write_lp_snapshots` publie `rank_captured` `{"game_id": …}` une fois par photo écrite, rien sans bus (test).
7. `GET /parties/{id}/lp` rend `#lp-slot[data-game=id]`, vide sans photo et pour une partie inconnue (test).
8. `test_regression_sse_connection_budget.py` reste vert (aucune nouvelle connexion SSE).
9. `CHANGELOG.md` (`[Unreleased]`), statut de cette spec et `docs/specs/README.md` à jour.

**Vérification de bout en bout** : recette de @pj35 sur une classée réelle (aucun test d'interface sans son
accord) : à l'ouverture de la revue, « +19 LP » en entier dans le dégradé, rang en petit dessous ; si les LP
arrivent après coup, l'encart apparaît sans que la page se recharge. Sans partie : `/parties/8024448317` sur
`db.db` montre « 0 LP » neutre et « · remake ».

## 7. Hors périmètre

- ❌ Accueil, Profil et Rang : leurs LP (`accueil.html:53` etc.) n'ont pas le défaut CSS et ne sont pas en cause.
- ❌ Rattraper les 35 parties classées sans photo de rang (avant le 2026-10-08) : la notification de LP n'est
  lisible que sur l'écran de fin, une variation ne s'invente pas (`src/coaching/ranked.py`, docstring).
- ❌ Recalculer un delta à partir de deux photos successives : la notification de Riot fait foi (elle compte les
  défaites pardonnées et les bonus que la différence ignorerait).
