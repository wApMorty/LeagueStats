# SPEC-38 — Trois pages de runes OneTricks au choix pendant la draft

**Statut** : 🟡 Rédigée le 2026-10-20, arbitrages de §2 validés par @pj35 le jour même, spec à valider avant `/implement`.

**Origine** : @pj35, 2026-10-20 — « J'aimerais pouvoir choisir mes runes avec un peu plus de précision pendant la
préparation de la draft. Possible de me faire un écran avec les 3 pages de runes les plus recommandées selon notre
algo OneTrick ? »

**Effort** : ~1,5 jour, 4 tâches (§5, 11 pts).

---

## 1. Constat

Lecture du code et des fixtures OneTricks le 2026-10-20.

- **Une seule page est montrée.** La colonne « Runes & sorts » de la draft (`src/client/static/runes.js`) affiche la
  page de `/draft/loadout` (`src/client/draft_loadout.py:182`, `plan`) : `pick_build` prend `popKeystone[0]` puis la
  première page de `popRunes[keystone]` (`src/draft/loadout.py:265-287`), affinée au duel par `adapt_to_matchup`
  (`src/draft/loadout.py:449`). Les autres pages publiées par OneTricks ne sont jamais lues. Seul le grimoire
  (éditeur rune par rune, SPEC-21 tâche 92) permet d'en changer.
- **OneTricks publie 4 pages par keystone**, keystones absentes de `popKeystone` comprises. Leur part est une part
  **de toutes les parties** de la page, pas de la keystone : pour Ambessa top (`tests/fixtures/onetricks_ambessa_top.json`),
  les 4 pages de Poigne de l'immortel (8437) pèsent 23,0 % contre 49,4 % pour la keystone, et les 24 pages publiées
  couvrent 56,6 % des 500 parties. Une page complète est donc rare : la plus jouée d'Ambessa fait 8,2 % (41 parties).
- **Classements mesurés sur les fixtures** :

  | Fixture | Part globale (top 3) | Une page par keystone (top 3) |
  |---|---|---|
  | Ambessa top, 500 parties | 8437/8300 8,2 % · 8230/8100 7,6 % · 8437/8300 6,9 % | 8437 8,2 % · 8010 4,9 % · 8112 2,9 % |
  | Jinx bot, 500 parties | 8008/8300 29,9 % · 8008/8200 21,2 % · 8008/8300 13,4 % | 8008 29,9 % (keystone à 99 %, une seule page) |

- **Le duel publie aussi ses pages**, sur un échantillon mince : Jinx contre Draven, 40 parties
  (`tests/fixtures/onetricks_jinx_bot_vs_draven.json`). Les pages générales n° 1, 2 et 4 y figurent (22,5 %, 18,9 %,
  15,1 %), la n° 3 (13,4 %) n'y est pas publiée.
- **Les fragments ne sont publiés qu'en un seul jeu** (`popStat`) : les trois pages auront les mêmes.
- **Aucune requête de plus n'est nécessaire.** `get_page` met en cache chaque (champion, lane, adversaire) par
  processus (`src/draft/loadout.py:126`) ; le serveur du client a déjà lu la page générale et celle du duel pour
  `plan` avant le verrouillage. Après le verrouillage, `plan` lit la page écrite dans le client **sans réseau**, et un
  test le garde (`tests/test_client_draft.py:1035`) : les trois pages doivent donc passer par une route à part,
  appelée seulement à l'ouverture de l'écran.
- **L'écriture existe** : `POST /draft/loadout/send` (`src/client/app.py:641`) valide la page contre les arbres, écrit
  la page `LS` et les sorts, puis passe le Live Coach en `loadout manual` (l'import du lock-in ne l'écrase plus).
- **La place existe** : l'éditeur occupe déjà un écran superposé de 1 480 px à gauche de la colonne
  (`.ed-overlay`, `src/client/static/style.css:577`), dans `#d-overlays`.

## 2. Objectif et arbitrages

Pendant la draft, un écran superposé montre les trois pages de runes les plus recommandées par OneTricks pour le
champion survolé ou verrouillé, avec leur popularité (et leur part dans le duel une fois l'adversaire connu), et un
clic sur l'une l'écrit dans le client.

| Sujet | Décision |
|---|---|
| Affichage | **Validé (@pj35, 2026-10-20)** : écran superposé ouvert depuis la colonne « Runes & sorts », trois pages complètes côte à côte, runes qui diffèrent de la page 1 mises en évidence. |
| Classement | **Validé (@pj35, 2026-10-20)** : page 1 = la page de l'import du lock-in (`pick_build`, affinée au duel) ; pages 2 et 3 = les pages publiées les plus jouées ensuite, toutes keystones confondues, sans doublon de la page 1. |
| Duel | **Validé (@pj35, 2026-10-20)** : la page 1 suit l'affinage existant ; chaque page affiche en plus sa part contre l'adversaire de lane et le nombre de parties correspondant, ou « non publiée » ; affichage informatif seulement, il ne change pas le classement. |
| Effet de « Choisir » | **Validé (@pj35, 2026-10-20)** : écrit directement la page dans le client (page `LS`, avec les sorts de la colonne), sans passer par « Envoyer au client » ; la page devient « Modifiée à la main » et prime sur l'import du lock-in. |
| Fragments | Ceux de `popStat`, identiques pour les trois pages (OneTricks n'en publie qu'un jeu, §1). |
| Moins de 3 pages publiées | On montre celles qui existent (au moins la page 1). |
| Verrouillage pendant que l'écran est ouvert | L'écran reste ouvert : la finalisation est le moment où l'on choisit ses runes. Il se ferme quand le champion montré change. |

## 3. Approches considérées

1. **Ajouter les candidates au plan existant (`/draft/loadout`)** : une seule requête côté navigateur, mais après le
   verrouillage le plan lit le client sans réseau (§1) ; y ajouter les candidates ferait appel à OneTricks à chaque
   relecture du plan et casserait cet invariant. Écartée.
2. **Route dédiée `/draft/loadout/pages`, appelée à l'ouverture de l'écran** (retenue) : le plan ne change pas, la
   route relit les pages en cache (au pire 2 requêtes OneTricks, celles que `plan` aurait faites), et le calcul vit
   dans `src/draft/loadout.py` à côté de `pick_build`, testable sur les fixtures.
3. **Calcul côté navigateur** à partir de la page OneTricks brute : il faudrait exposer `popRunes` et dupliquer en JS
   la logique d'affinage. Écartée.

## 4. Détail

### 4.1 `src/draft/loadout.py` (tâche 187)

```python
@dataclass(frozen=True)
class RunePage:
    """Une page de runes candidate, sans fragments (communs, `popStat`)."""

    primary_style: int
    sub_style: int
    perks: Tuple[int, ...]  # triées par id, comme OneTricks
    share: Optional[float]  # part des parties de la page générale ; None si non publiée (page 1 adaptée au duel)
    duel_share: Optional[float]  # part des parties du duel ; None sans duel ou si non publiée


def rune_pages(
    general: dict, first: Build, duel: Optional[dict] = None, count: int = draft_config.LOADOUT_RUNE_PAGES
) -> List[RunePage]:
    """La page de `first` puis les pages publiées les plus jouées, sans doublon ; [] si la page est illisible."""
```

- Une page publiée s'identifie par la clé `(style principal, style secondaire, tuple(sorted(perks)))`, lue dans
  chaque entrée `[perks, part, [principal, secondaire, keystone]]` de `popRunes`, toutes keystones confondues.
- Ordre : `first` d'abord (sa `share` est celle de sa clé dans la page générale, `None` si elle n'y est pas), puis
  les pages générales par part décroissante (tri stable), en sautant la clé de `first`, jusqu'à `count`.
- `duel_share` : part de la même clé dans `popRunes` de `duel`, `None` si `duel` est `None` ou si la clé n'y est pas.
- Toute erreur de structure (`KeyError`, `IndexError`, `TypeError`, `ValueError`) donne `[]`, comme `pick_build`.
- Constante `LOADOUT_RUNE_PAGES: int = 3` dans `draft_config` (`src/config_constants.py`, à côté des `LOADOUT_*`),
  origine : la demande de @pj35.

Tests (`tests/test_loadout.py`, fixtures existantes) :

1. Ambessa, `first = pick_build(page)` : clés 8437/8300 (8,2 %), 8230/8100 (7,6 %), 8437/8300 (6,9 %), dans cet ordre.
2. Jinx contre Draven : `duel_share` de 0,225 et 0,189 pour les pages 1 et 2, `None` pour la page 3 (13,4 %).
3. `first` adaptée et absente de la page générale : en tête avec `share is None`, suivie des deux premières pages
   générales.
4. `first` égale à la 2e page générale : pas de doublon, la 4e remonte en 3e position.
5. Une seule page publiée : liste d'un élément ; `popRunes` absent : `[]`.

### 4.2 Route `/draft/loadout/pages` (tâche 188)

`src/client/draft_loadout.py` :

```python
def pages(snapshot: Dict[str, Any], champion_id: int, styles: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
    """Les pages OneTricks au choix pour `champion_id` ; `available` faux (avec la raison) sinon."""
```

- Champion lu dans `snapshot["champions"]` comme `plan`, lane `snapshot["local_role"]`, adversaire
  `snapshot["versus"]`. Page 1 : `_onetricks_build(...)` (le même calcul que `plan`, donc la même page tant que la
  colonne montre la page OneTricks). Pages générale et du duel : `onetricks.get_page(...)` (en cache).
  **Jamais** la page `loadout` du snapshot : les candidates viennent toujours d'OneTricks.
- Réponse :

  ```json
  {"available": true, "champion_id": 164, "games": 500, "opponent": "Darius", "duel_games": 40,
   "shards": [5008, 5008, 5011],
   "pages": [{"page": {"primary": 8400, "sub": 8300, "keystone": 8437, "rows": [], "subs": [], "shards": []},
              "share": 0.082, "games": 41, "duel_share": 0.225, "duel_games": 9}]}
  ```

  `page` est la forme de `normalize_page` (fragments = `popStat`) ; `games = round(share × games)`, `null` si
  `share` l'est ; `duel_games = round(duel_share × duel_games)`, `null` sinon ; `opponent` et `duel_games` (racine)
  `null` sans page de duel. Une page que `normalize_page` rejette (arbre inconnu du Data Dragon) est sautée.
- `available: false` avec `reason` : champion inconnu, page OneTricks indisponible, aucune page lisible.
- `src/client/app.py` : `GET /draft/loadout/pages?champion_id=` à côté de `/draft/loadout`, même garde sur le
  snapshot que `draft_loadout`.

Tests (`tests/test_client_draft.py`, fixture `onetricks` et `runes_assets` existantes) : trois pages Jinx dans
l'ordre de la page générale avec `games` cohérent ; parts du duel quand `versus` a une page (fixture du duel
injectée) et `opponent` nul sinon ; route appelée **après** le verrouillage avec un `loadout` dans le snapshot :
les pages viennent quand même d'OneTricks ; champion inconnu et page indisponible → `available: false` ;
le test `test_page_deja_ecrite_dans_le_client_sans_reseau` reste vert sans modification.

### 4.3 Écran « Pages OneTricks » (tâche 189)

`src/client/static/runes.js` :

- Bouton « 3 pages OneTricks › » dans la colonne, sous la ligne de titre, visible quand `lo.status === "ready"`
  (hors de la carte de page, qui ouvre déjà le grimoire au clic).
- `openPages()` : `GET /draft/loadout/pages?champion_id=` puis un écran superposé dans `#d-overlays`, sur le modèle
  de `openEditor` (classe `ed-overlay`, fermeture par Échap et « Annuler »). En-tête : champion et lane, nombre de
  parties OneTricks, et « contre {adversaire} · {n} parties » si `opponent`. `available: false` : l'écran affiche
  la raison.
- Trois colonnes, une par page : rang, part (« 8,2 % · 41 parties », ou « Adaptée au duel » si `share` est nul),
  ligne du duel (« 22,5 % contre Draven · 9 parties » ou « non publiée contre Draven », rien sans adversaire), la
  page en lecture seule, et un bouton « Choisir ». La carte reprend le rendu de `pageCard` (à paramétrer par la page
  plutôt que de lire `lo.page`) ; une rune des pages 2 et 3 absente de la page 1 porte la classe `is-diff`.
- « Choisir » : `applyPage(page)` (page de travail, « Modifiée à la main », mise en lumière existante), puis
  `push()` (écriture immédiate avec les sorts de la colonne), puis fermeture. Si l'envoi échoue, le toast de
  `Draft.post` s'affiche et la page reste la page de travail, à renvoyer par « Envoyer au client ».
- `Draft.onSync` : l'écran se ferme si le champion montré change (`lo` nul ou `lo.championId` différent) ; il reste
  ouvert au verrouillage.
- `src/client/static/style.css` : grille de trois colonnes dans l'écran, style `is-diff` (contour à la couleur de
  l'arbre), sans nouvelle couleur hors des jetons existants.

Tests : `test_runes_js_sans_erreur_de_syntaxe` reste vert ; un test vérifie que `runes.js` appelle
`/draft/loadout/pages`. Le rendu se juge à la recette (pas de sonde de fenêtre réelle sans accord de @pj35).

### 4.4 Clôture (tâche 190)

`CHANGELOG.md` (`[Unreleased]`, ✨ Feature), statut de cette spec, `docs/specs/README.md`, `TODO.md`.

## 5. Tâches

| # | Tâche | Pts | Dépend de |
|---|---|---|---|
| 187 | `RunePage`, `loadout.rune_pages()`, `LOADOUT_RUNE_PAGES` + 5 tests sur fixtures (§4.1) | 3 | — |
| 188 | `draft_loadout.pages()` et route `GET /draft/loadout/pages` + tests (§4.2) | 2 | 187 |
| 189 | Écran « Pages OneTricks » : bouton, écran superposé, `pageCard` paramétré, `is-diff`, « Choisir » qui écrit, CSS + test du script (§4.3) | 5 | 188 |
| 190 | Clôture : `CHANGELOG.md`, statuts, README des specs, recette @pj35 en draft réelle | 1 | 189 |

## 6. Critères d'acceptation

1. `python -m pytest tests/ -v` vert, avec les tests des tâches 187 à 189.
2. `python -m pytest tests/test_loadout.py -k rune_pages -v` : sur Ambessa top, les trois pages sont 8437/8300,
   8230/8100 puis 8437/8300 (seconde page), dans cet ordre ; sur Jinx contre Draven, la page 3 a `duel_share is None`.
3. La page 1 de `/draft/loadout/pages` est identique à la page de `/draft/loadout` pour le même snapshot avant
   verrouillage (test de la tâche 188).
4. `test_page_deja_ecrite_dans_le_client_sans_reseau` passe sans modification : le plan après verrouillage ne
   touche toujours pas OneTricks.
5. `grep -n "LOADOUT_RUNE_PAGES" src/config_constants.py src/draft/loadout.py` : la constante est définie une fois et
   utilisée par `rune_pages`, aucun `3` littéral pour le nombre de pages.
6. `node --check src/client/static/runes.js` sans erreur, et `runes.js` appelle `/draft/loadout/pages`.
7. `CHANGELOG.md` (`[Unreleased]`), statut de cette spec et `docs/specs/README.md` à jour.

**Vérification de bout en bout** : en draft réelle (recette @pj35), survoler un champion, ouvrir « 3 pages
OneTricks », vérifier trois pages distinctes avec leur part ; après le verrouillage de l'adversaire de lane, la
ligne du duel apparaît ; « Choisir » sur la page 2 l'écrit dans le client (page `LS` visible dans le client LoL),
la colonne affiche « Modifiée à la main », et le verrouillage ne la remplace pas.

## 7. Hors périmètre

- ❌ **Taux de victoire par page** : OneTricks ne publie que des popularités, et les 100 parties de `matchHistory`
  viennent de quelques joueurs, donc ne sont pas indépendantes (test du duel abandonné le 2026-10-08).
- ❌ **Fragments par page** : non publiés par OneTricks (§1).
- ❌ **Re-classement des pages par le duel** : l'échantillon (40 parties pour Jinx contre Draven) ne le porte pas ;
  la part du duel reste informative (§2).
- ❌ **Choix entre plusieurs builds d'items ou de sorts** : la demande porte sur les runes.
- ❌ **Mode démo et captures** (`scripts/demo_client.py`, `scripts/capture_screens.py`) : à ajouter si @pj35 veut
  l'écran dans la vitrine.
