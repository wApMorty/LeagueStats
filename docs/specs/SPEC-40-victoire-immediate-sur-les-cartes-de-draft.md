# SPEC-40 — Victoire immédiate sur les cartes de draft

**Statut** : 🟡 Rédigée le 2026-10-20, arbitrages validés par @pj35 le 2026-10-20 (§2).

**Origine** : @pj35, 2026-10-20 — « J'ai l'impression que l'assistant draft du GUI n'affiche pas le win chance
recalculé pour chaque pick. Cependant je les retrouve correctement lorsque j'ouvre la page de sélection étendue. »
Symptôme précisé en interview : pour un même champion, le pourcentage de la carte ne correspond pas à celui du
grimoire, et les cartes sont toutes proches avec un écart négatif.

**Effort** : ~½ jour, 2 tâches (§5).

---

## 1. Constat

Mesuré le 2026-10-20 sur le code et sur une copie de `data/db.db` (scénarios de `scripts/bench_search.py`, pool des
20 mid les plus joués, budget 2 s).

- **Les cartes et le grimoire ne montrent pas le même chiffre.** La carte prend `rec["win_probability"]`
  (`src/client/draft_view.py:397`), la valeur de la recherche minimax : la fin de draft attendue quand les deux camps
  jouent au mieux (`src/draft/snapshot.py:267`). La tuile du grimoire prend `champion["win_probability"]`
  (`src/client/draft_grimoire.py:122`), rempli par `_fill_candidates` (`src/draft/recommendations.py:175`) : la
  victoire de la position actuelle avec ce champion sur ma lane, sans rien dérouler.
- **La valeur de recherche est sous la position actuelle, pour toutes les cartes.** Elle suppose que l'adversaire
  contre au mieux ensuite, donc l'écart affiché (`delta`, recherche − position actuelle, `src/draft/snapshot.py:268`)
  est presque toujours négatif et les cartes se tassent :

  | Scénario | Position actuelle | Cartes (recherche) | Grimoire (immédiat), mêmes champions |
  |---|---|---|---|
  | B2 : Jinx bot contre Garen top + Lee Sin jungle | 49,47 % | Zoe 48,22 · Galio 48,16 · Yasuo 48,10 · Leblanc 47,97 | 49,48 · 50,27 · 49,95 · 50,18 |
  | B4 : 3 alliés, 4 ennemis, avant-dernier pick | 43,75 % | Zoe 48,12 · Locke 47,67 · Katarina 47,48 · Yasuo 47,48 | 47,21 · 45,20 · 46,74 · 46,90 |

  En B2, les quatre cartes affichent −1,2 à −1,5 pt alors que Galio ou Leblanc améliorent la position tout de suite.
- **La jauge dit « si X est verrouillé » sur la valeur de fin de draft.** `state.win` ne contient que les
  recommandations, avec leur valeur de recherche (`src/client/draft_view.py:490`) ; le libellé de la jauge
  (`src/client/static/draft.js:148`) annonce pourtant une victoire « si X est verrouillé ». Survoler un champion hors
  des cartes (client ou grimoire) la laisse sur « position actuelle », faute d'entrée dans `state.win`.
- **Le grimoire lui-même se contredit** : pour un champion recommandé, la tuile montre l'immédiat et la barre basse
  la valeur de recherche, toutes deux nommées « victoire prédite » (`src/client/draft_grimoire.py:79`).
- La valeur immédiate existe déjà dans le snapshot pour chaque champion libre (`snapshot["champions"]`) pendant la
  phase de picks, tant que je n'ai pas verrouillé : aucun calcul de plus n'est nécessaire.

## 2. Objectif et arbitrages

Les cartes, la jauge et le grimoire montrent la même victoire immédiate pour un même champion ; la fin de draft
attendue reste visible en second et continue de fixer l'ordre des cartes.

| Sujet | Décision |
|---|---|
| Chiffre principal de la carte | **Validé (@pj35, 2026-10-20)** : la victoire immédiate (celle du grimoire) en gros, la fin de draft attendue de la recherche en sous-ligne. |
| Ordre des cartes | **Validé (@pj35, 2026-10-20)** : l'ordre de la recherche, inchangé ; la sous-ligne « fin de draft attendue », décroissante, l'explique. |
| Écart en points | **Validé (@pj35, 2026-10-20)** : immédiat − position actuelle. |
| Jauge | **Validé (@pj35, 2026-10-20)** : la victoire immédiate de tout champion libre survolé ou sélectionné, cartes comprises. |
| Champion sans valeur immédiate (table vide après une exception) | Repli sur l'affichage d'aujourd'hui : valeur de recherche en gros, écart du snapshot, pas de sous-ligne de fin de draft. |
| Console du Live Coach | Inchangée (elle imprime la valeur de recherche, qui est son classement). |

## 3. Approches considérées

1. **Lecture dans la vue (retenue).** `draft_view.py` lit la valeur immédiate dans `snapshot["champions"]`, déjà
   publié. Pas de champ de plus dans `DraftSnapshot`, le Live Coach ne bouge pas, le diff reste dans deux fichiers
   de vue.
2. **Champ `immediate_probability` sur `SnapshotRecommendation`.** Plus explicite, mais duplique une donnée déjà
   dans le snapshot et touche la boucle de draft du Live Coach pour un sujet d'affichage.
3. **Passer toute l'interface sur la valeur de recherche** (grimoire compris). Cohérent, mais demande une recherche
   par champion libre (~170 × le coût d'une racine) et garde le chiffre que @pj35 trouve trompeur.

## 4. Détail

### 4.1 Cartes et jauge (`src/client/draft_view.py`)

- Nouvelle fonction privée `_immediate(snapshot: Dict[str, Any]) -> Dict[int, float]` : `{champion_id:
  win_probability}` des lignes de `snapshot.get("champions") or []` dont `win_probability` n'est pas `None`.
- `recommendations(snapshot, champions)` : pour chaque carte, `now = immediate.get(rec["champion_id"])`.
  - `now` connu : `win` = `fr(now * 100, 2) + " %"` ; écart = `(now − base) × 100` avec
    `base = snapshot.get("base_probability")` (pas d'écart si `base` est `None`) ; `line` =
    `f"Fin de draft attendue {fr(rec['win_probability'] * 100, 2)} % · suite : {variation}"` (`suite : —` sans
    variante).
  - `now` inconnu : affichage d'aujourd'hui, inchangé (`win` de recherche, `rec["delta"]`,
    `"Suite attendue : …"`).
  - `up` suit l'écart retenu.
- `stage_view` : `state["win"]` = les valeurs de recherche des recommandations (repli), écrasées par `_immediate`
  pour chaque champion connu ; `state["names"]` ajoute `champions.name(id)` pour chaque identifiant de
  `state["win"]` (les noms des cartes et des bans restent prioritaires). `draft.js` n'a pas à changer : il lit déjà
  `state.win[sel]` et `state.names[sel]`.

### 4.2 Barre du grimoire (`src/client/draft_grimoire.py`)

- `_info` en mode pick, champion recommandé : `"Victoire prédite {imm} % · fin de draft attendue {rech} % ·
  {games} games · suite attendue : …"` quand la valeur immédiate du champion est connue (`champion.get(
  "win_probability")`) ; texte d'aujourd'hui sinon.

### 4.3 Tests

- `tests/regression/test_regression_carte_et_grimoire_meme_victoire.py` : un snapshot de pick où une
  recommandation a une valeur de recherche (0,4822) et une valeur immédiate (0,5027) différentes ; le pourcentage de
  la carte (`/draft/stage`) est celui de la tuile du grimoire (`/draft/champions`),
  l'écart vaut immédiat − position actuelle, la sous-ligne porte « Fin de draft attendue 48,22 % ». Vérifié rouge
  avant le fix.
- `tests/test_client_draft.py` : `state["win"]` couvre un champion hors des cartes avec sa valeur immédiate et
  `state["names"]` son nom ; repli sans table de champions (les tests existants restent verts tels quels) ; barre du
  grimoire d'un champion recommandé avec les deux chiffres.

Aucune constante, aucune migration.

## 5. Tâches

| # | Tâche | Pts | Dépend de |
|---|---|---|---|
| 194 | `_immediate`, cartes (gros chiffre, écart, sous-ligne) et `state.win` / `state.names` dans `draft_view.py` ; test de régression rouge puis vert ; tests de la jauge et du repli | 3 | — |
| 195 | Barre du grimoire (`_info`) avec les deux chiffres et son test ; `CHANGELOG.md`, statuts, README des specs ; recette @pj35 | 1 | 194 |

## 6. Critères d'acceptation

1. `python -m pytest tests/ -v` vert, avec les tests de §4.3.
2. `python -m pytest tests/regression/test_regression_carte_et_grimoire_meme_victoire.py -v` : rouge sur le commit
   précédant la tâche 194, vert après.
3. Pour un champion recommandé qui a une valeur immédiate, le pourcentage de la carte égale celui de sa tuile du
   grimoire, et l'écart affiché vaut (immédiat − position actuelle) × 100 (test de 1).
4. La carte porte « Fin de draft attendue X % » avec X la valeur de recherche, et l'ordre des cartes reste celui de
   `snapshot["recommendations"]` (test de 1).
5. `state["win"]` contient la valeur immédiate de tout champion libre de `snapshot["champions"]`, et
   `state["names"]` son nom (test de 1).
6. Sans valeur immédiate, la carte s'affiche comme avant la spec (tests existants de `test_client_draft.py`
   inchangés et verts).
7. `git diff` de la spec ne touche ni `src/draft/` ni `src/client/static/draft.js`.
8. `CHANGELOG.md` (`[Unreleased]`), statut de cette spec et `docs/specs/README.md` à jour.

**Vérification de bout en bout** : une draft réelle (ou personnalisée) dans le client : après un pick adverse, pour
chacune des quatre cartes, le gros chiffre égale celui de la tuile du grimoire, la sous-ligne donne la fin de draft
attendue, et survoler un champion hors des cartes depuis le grimoire déplace la jauge sur « si X est verrouillé ».

## 7. Hors périmètre

- ❌ Cartes avant le premier pick adverse : le classement attend toujours un ennemi (`src/draft/recommendations.py:317`),
  choix existant non remis en cause par @pj35.
- ❌ Changer l'ordre du classement ou le modèle de recherche : seul l'affichage change.
- ❌ Sortie console du Live Coach : elle garde la valeur de recherche.
- ❌ `projected_probability` (jauge sans sélection) : avec la sélection par défaut sur la 1re carte, elle n'est
  presque jamais lue.
