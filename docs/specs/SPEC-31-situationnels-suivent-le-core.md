# SPEC-31 — Items situationnels liés au core, selon les chemins OneTricks

**Statut** : 🟡 Rédigée le 2026-10-12 ; arbitrages de §2 validés par @pj35 le 2026-10-12, sauf deux points « à valider » (valeur des seuils, volume du banc).

**Origine** : @pj35, 2026-10-12 : « Il arrive souvent que l'algorithme me recommande des items Situationnels qui n'ont pas
de lien avec le Core Build. Est-ce qu'il serait possible d'améliorer l'algorithme d'optimisation des builds en suivant les
"paths" ou "options" renseignés sur OneTricks ? »

**Effort** : ~2 jours, 5 tâches, 15 pts (§5).

---

## 1. Constat

Mesuré le 2026-10-12 sur trois pages réelles OneTricks (Ambessa top, Yorick top, Jinx bot ; 3 requêtes, onglet ALL), avec
les fonctions du dépôt lues sur `src/draft/loadout.py`.

- **Les situationnels sont les items les plus achetés, sans rapport avec le core choisi.** `_item_blocks`
  (`src/draft/loadout.py:159-172`) remplit « Situationnels » avec `popularItems` (part des parties où l'item est acheté,
  tous cores confondus) privé de ce qui est déjà listé, puis coupe à `LOADOUT_SITUATIONAL_ITEMS` = 8. Le core choisi
  (`popCore[0]`) n'entre en rien dans la sélection.
- **La page publie ce lien et le code ne le lit pas.** `firstItemStats.all.all.popPath` (jamais lu : `grep popPath src/`
  ne trouve rien) contient, **pour chaque option de `popCore`, dans le même ordre**, les options des 3ᵉ, 4ᵉ et 5ᵉ items,
  trois au plus par rang, chacune avec sa part **de toutes les parties de la page**. Alignement vérifié le 2026-10-12 :
  les items d'un core n'apparaissent jamais dans son propre chemin, et sur les 100 parties de `matchHistory` (Jinx,
  core Hexoptics + Runaan's), 26 troisièmes items sur 34 sont Infinity Edge, premier du chemin (87 parties de 500).
- **Ce que ça donne aujourd'hui** (items « Situationnels » du set, 8 par page) :

  | Page | Core choisi (parties) | Situationnels dans le chemin du core | Autres seconds items de core | Sans lien avec aucun chemin |
  |---|---|---|---|---|
  | Ambessa top | Eclipse + Black Cleaver (147) | 4 sur 8 (Death's Dance, Mortal Reminder, Maw, Endless Hunger) | 3 (Voltaic Cyclosword, Shojin, Profane Hydra) | 1 (Bastionbreaker) |
  | Yorick top | Trinity + Black Cleaver (43) | 2 sur 8 (Sterak's, Randuin's) | 2 (Shojin, Eclipse) | 4 (Voltaic, Hullbreaker, Spirit Visage, Serylda's) |
  | Jinx bot | Hexoptics + Runaan's (178) | 6 sur 8 | 2 (Yun Tal, Phantom Dancer) | 0 |

- **Le chemin est bruité en queue.** Part des parties du core qui prennent l'item aux rangs 3 à 5 (somme des trois
  rangs / part du core), parties dérivées de `patchStats["all"]` : Ambessa, Death's Dance 52 % (77 parties), Maw 14 %
  (20), Mortal Reminder 11 % (16), Guardian Angel 1,2 % (1,7), Endless Hunger 0,7 % (1,1) ; Yorick, dont le core ne pèse
  que 43 parties, Sterak's 33 % (14), Guardian Angel 7 % (3), Randuin's 5 % (2,3).
- **Banc du 2026-10-12** (`scripts/bench_loadout_paths.py`, 12 pages : Ambessa, Yorick, Darius, Garen top ; Lee Sin, Viego
  jungle ; Ahri, Orianna, Syndra mid ; Jinx, Kai'Sa, Ezreal bot, aux seuils de départ 5 % et 3 parties) : items de
  « Situationnels » hors du chemin du core, **53 avant, 0 après** ; repli 0 / 12 ; nombre de situationnels, médiane 8 avant,
  **4 après** (de 2 à 6). Les seuils de départ sont conservés : aucune page ne justifie de les bouger (Guardian Angel de
  Yorick, 7 % et 3 parties sur un core de 44 parties, reste le cas limite). Les pages de support n'ont pas pu être
  mesurées : OneTricks nomme ce poste `supp` et `LANE_TO_ONETRICKS_ROLE` ne le traduit pas, la page répond 404 (hors
  périmètre, voir le rapport).
- **Après un changement de core par le duel** (`chosen["Core"]`, `loadout.py:406`), le chemin à lire est celui du nouveau
  core. La page du duel publie son propre `popPath`, aligné sur son propre `popCore`, mais sur ~40 parties.
- **Le test de non-régression actuel fige le comportement à changer** :
  `tests/regression/test_regression_loadout_alt_core_hides_items.py` exige que « Situationnels » soit exactement les items
  populaires hors core. Il est réécrit (§4.5), pas supprimé : sa leçon (Death's Dance disparue des situationnels
  d'Ambessa, 2026-09-25) reste vraie.
- **Pas de chemin d'import cassé en amont** : `_trim` (`loadout.py:102-114`) garde déjà tout `firstItemStats.all.all`, donc
  `popPath` est en cache sans changement.

## 2. Objectif et arbitrages

Les situationnels d'un set sont les suites observées du core choisi, rien d'autre : plus d'item sans lien avec lui.

| Sujet | Décision |
|---|---|
| Source du lien | **Validé (@pj35, 2026-10-12)** : `popPath` d'OneTricks, onglet ALL, pour le core choisi. Aucune règle de contre-item ni de synergie : la pondération est la fréquence observée (part des parties du core), de même nature que celle du moteur actuel ([ADR-003](../adr/ADR-003-onetricks-temps-reel.md)). |
| Items hors chemin | **Validé** : bloc séparé. « Situationnels » ne contient que des suites du core ; les items des **autres options de `popCore`** vont dans un bloc « Autres cores » en fin de set ; un item sans lien avec aucun chemin ni aucun core disparaît du set. |
| Items sur-représentés au duel | **Validé** : « Duel dans le chemin ». Le chemin du core est lu aussi sur la page du duel ; un item significatif (test de SPEC-15 §3.2.3, inchangé) n'est promu en tête de « Situationnels » que s'il est dans le chemin du core choisi ; sinon il passe en tête de « Autres cores » s'il appartient à un autre core ; sinon il est ignoré. |
| Options trop rares | **Validé** : seuil, liste plus courte. Une option n'est gardée que si elle est prise par au moins `LOADOUT_PATH_MIN_SHARE` des parties du core **et** par au moins `LOADOUT_PATH_MIN_GAMES` parties. Aucune complétion par `popularItems` : le bloc peut compter 2 à 6 items. |
| Valeur des seuils | **À valider** : départ 5 % et 3 parties, tirés du constat ci-dessus (écarte Guardian Angel d'Ambessa à 1,2 % et 1,7 partie, garde Bloodthirster de Jinx à 5,2 % et 9 parties). Réglés par le banc de la tâche 144, que @pj35 relit. |
| Repli | **Validé (défaut)** : si le chemin du core est introuvable (`popPath` absent, core absent des deux pages, structure inattendue), « Situationnels » garde l'ancien calcul (`popularItems`) et la console le dit. Un set sans situationnels parce que le site a changé de structure serait pire que l'ancien set. |
| Volume du banc | **À valider** : la tâche 144 interroge OneTricks pour 12 pages, espacées de 20 s (≈ 4 min), une seule fois, à la main. Hors du volume de la boucle de draft (2 pages) qui fonde ADR-003 ; sous le plafond mesuré par le spike de SPEC-15 (blocage à ~17 pages en 5 min). |

## 3. Approches considérées

| Approche | Pour | Contre |
|---|---|---|
| **A. Remplir « Situationnels » avec le chemin du core (retenue)** | Une seule source, déjà dans la page en cache ; supprime le défaut à la racine ; le lien est mesuré, pas déduit | Liste plus courte quand le core est peu joué (Yorick : 43 parties) ; dépend du format `popPath` |
| B. Garder `popularItems` et classer le chemin en tête | Aucun set plus court | Les items sans lien reviennent dès que le chemin publie moins de 8 items (Ambessa : 5 sur 8 places), donc le défaut reste |
| C. Reconstruire les suites depuis `matchHistory` (100 parties, `orderedItems`) | Ordre d'achat réel | 100 parties au lieu de 500 : 6 parties seulement pour le core d'Ambessa ; `popPath` agrège déjà les 500 |

A retenue : B laisse le défaut en place, C divise l'échantillon par cinq.

## 4. Détail

### 4.1 Constantes (`src/config_constants.py`, `DraftConfig`, à côté de `LOADOUT_SITUATIONAL_ITEMS`)

| Constante | Défaut | Origine |
|---|---|---|
| `LOADOUT_PATH_MIN_SHARE` | `0.05` | Part minimale des parties du core ; mesure du 2026-10-12 (§1), à régler tâche 144 |
| `LOADOUT_PATH_MIN_GAMES` | `3` | Parties minimales derrière une option : un core de 43 parties à 5 % n'en donne que 2 (§1) |
| `LOADOUT_ALT_CORE_ITEMS` | `4` | Taille du bloc « Autres cores » : Ambessa en a 3, Jinx 2 (§1) |

`LOADOUT_SITUATIONAL_ITEMS` (8) reste le plafond de « Situationnels ».

### 4.2 Lecture du chemin (`src/draft/loadout.py`)

```python
def _core_path(stats: dict, games: int, core: Tuple[int, ...]) -> Optional[List[PathItem]]:
    """Suites du core (rangs 3 à 5) : [(item, part des parties du core, parties)], de la plus
    à la moins prise ; None si `popPath` est absent ou si le core n'est pas listé dans `stats`."""
```

- Le core est repéré par **égalité exacte de l'option** dans `stats["popCore"]` (ordre des deux items compris : aucune
  page vue ne publie la même paire dans les deux ordres) ; son indice sert à lire `stats["popPath"][indice]`.
- Pour chaque item : `part_du_core = Σ des parts sur les 3 rangs / part de popCore[indice]` et
  `parties = round(Σ des parts × games)`, `games` = `patchStats["all"]` de la page lue. Un item d'un rang n'apparaît pas à
  un autre rang d'une même partie, la somme sur les rangs est donc la part des parties du core qui l'achètent.
- Seuils : `part_du_core >= LOADOUT_PATH_MIN_SHARE and parties >= LOADOUT_PATH_MIN_GAMES`.
- Tout `KeyError` / `IndexError` / `TypeError` / `ZeroDivisionError` donne `None` (cohérent avec le reste du module : la
  boucle de draft ne lève jamais).

### 4.3 Blocs (`_item_blocks`)

`_item_blocks(stats, chosen, matchup_items, path)` : `path` est la liste de §4.2 (ou `None`).

- **« Situationnels »** : si `path` est une liste, les `matchup_items` présents dans `path` d'abord (ordre de
  `_matchup_items`), puis le reste du chemin dans l'ordre de `path`, hors items déjà listés, coupé à
  `LOADOUT_SITUATIONAL_ITEMS`. Si `path` est `None` : calcul actuel (`[*matchup_items, *ids("popularItems")]`).
- **« Autres cores »** (nouveau, après « Situationnels », uniquement quand `path` est une liste) : les `matchup_items` hors
  chemin et appartenant à une autre option de `popCore` (générale ou duel), puis les items des autres options de
  `popCore` de la page générale dans l'ordre de popularité du core, hors items déjà listés, coupé à
  `LOADOUT_ALT_CORE_ITEMS`. La déduplication existante (`seen`) range « Situationnels » **avant** « Autres cores » : un
  item à la fois dans le chemin et dans un autre core reste en situationnel (la leçon du 2026-09-25).
- Le titre « Autres cores » ne porte pas de pourcentage : les consommateurs lisent la base du titre avant ` (`
  (`src/client/en_partie.py:245`, `src/client/draft_loadout.py:166`) et affichent tout bloc non vide
  (`en_partie.py:238-242`) ; aucun ne dépend du nombre de blocs.
- `Build` gagne `path_games: int = 0` : parties du core derrière le chemin (0 = repli). Sert à la console (§4.6).

### 4.4 Duel (`adapt_to_matchup`)

- Le core final (`chosen["Core"]`, éventuellement substitué par le duel) est cherché d'abord dans la page générale, puis
  dans la page du duel : `path = _core_path(general_stats, …) ` sinon `_core_path(duel_stats, …)`. Un core publié par les
  deux pages se lit sur la générale (500 parties contre ~40).
- « Dans le chemin » pour un item du duel = présent dans le chemin du core lu sur **l'une ou l'autre** page, sans seuil de
  parties : le test binomial de §3.2.3 a déjà écarté le bruit.
- **Piège** : `loadout.py:410` (`sub.new[0] in blocks[-1][1]`) suppose « Situationnels » dernier bloc. Avec « Autres
  cores » derrière, il faut lire `dict(blocks)` : un item qui atterrit en « Situationnels » ou en « Autres cores » change
  le set et se signale ; les `Substitution` des items en « Autres cores » portent la catégorie `"Autres cores"`, ajoutée à
  `ITEM_CATEGORIES` (`src/draft/loadout_import.py:28`) pour que leurs noms soient résolus.
- Un item significatif absent du chemin et de tout core est ignoré et **n'est pas signalé** (il n'entre pas dans le set).

### 4.5 Tests

Hermétiques, sur les fixtures existantes plus une nouvelle (`tests/fixtures/onetricks_ambessa_top.json`, enregistrée avec
`loadout._trim` sur la page du 2026-10-12, onglet ALL seul, quelques Ko).

- `tests/test_loadout.py` : propriété sur les trois fixtures (Jinx, Jinx vs Draven, Ambessa) : tout item de « Situationnels »
  est dans le chemin du core choisi ; aucun item deux fois hors départ ; sur Ambessa, « Situationnels » =
  Death's Dance, Maw, Mortal Reminder et « Autres cores » = Shojin, Voltaic, Profane Hydra (aux seuils de départ) ;
  repli sans `popPath` ; core absent des deux pages ; seuils lus dans `draft_config` (monkeypatch) ; page malformée → `None`
  sans exception.
- Duel : item significatif dans le chemin → en tête de « Situationnels » ; hors chemin mais dans un autre core → en tête
  de « Autres cores » ; dans aucun → absent et non signalé ; core substitué par le duel → chemin relu (Jinx vs Draven :
  Runaan's, ancien core, en tête).
- Réécrits : `test_regression_loadout_alt_core_hides_items.py` (nouveau contrat, même leçon : un item à la fois dans le
  chemin et dans un autre core reste en « Situationnels »), `tests/test_loadout.py:67`, `:217-223` et
  `tests/regression/test_regression_loadout_situational_ignores_matchup.py` (le Kraken Slayer boosté doit être mis dans le
  chemin de la fixture pour rester en tête).
- `tests/test_loadout_import.py` / `tests/test_client_en_partie_build.py` : un bloc « Autres cores » s'affiche et ne devient
  jamais la cible du « prochain objet » (seuls « Core » et « Bottes » le sont).

### 4.6 Console et écran

- Ligne ajoutée à `loadout_import._report` (`src/draft/loadout_import.py:220`), sans emoji :
  `[INFO] Situationnels : suites du core (147 parties)` ou
  `[INFO] Situationnels : chemin du core introuvable, items les plus joués`.
- L'écran « En partie » gagne éventuellement une ligne de titre de bloc : `scripts/measure_en_partie.py:91-98` (cas le plus
  lourd) reçoit « Autres cores » et la marge de SPEC-30 (≥ 30 px à 1 920 × 986) est remesurée.
- SPEC-15 §3.1 et §3.2.3 reçoivent une note « révisé par SPEC-31 » (blocs d'items).

## 5. Tâches

Numéros à la suite de la tâche 141.

| # | Tâche | Pts | Dépend de |
|---|---|---|---|
| 142 | `_core_path`, `_item_blocks` (Situationnels par le chemin, bloc « Autres cores », repli), `Build.path_games`, constantes, fixture Ambessa, tests §4.5 (hors duel) | 5 | — |
| 143 | Duel : chemin lu sur les deux pages, items du duel dans le chemin ou « Autres cores », `blocks[-1]` corrigé, `ITEM_CATEGORIES`, tests de duel et tests réécrits | 3 | 142 |
| 144 | Banc `scripts/bench_loadout_paths.py` (12 pages espacées de 20 s, avant/après, repli) ; réglage des deux seuils sur ses chiffres, résultat noté en §1 | 3 | 143 |
| 145 | Ligne console, bloc « Autres cores » dans l'écran « En partie », remesure `measure_en_partie.py`, tests §4.5 (import, client) | 2 | 143 |
| 146 | Clôture : `CHANGELOG.md`, notes SPEC-15, statuts, README des specs, recette @pj35 | 2 | 144, 145 |

## 6. Critères d'acceptation

1. `python -m pytest tests/ -v` vert, avec les tests des tâches 142 à 145.
2. Sur chacune des fixtures Jinx, Jinx vs Draven et Ambessa, `python -c` ou test : tout item de « Situationnels » appartient
   au chemin du core choisi (`_core_path`), et aucun item n'apparaît deux fois hors « Départ ».
3. Sur la fixture Ambessa, aux seuils de départ : « Situationnels » = Death's Dance, Maw of Malmortius, Mortal Reminder ;
   « Autres cores » = Spear of Shojin, Voltaic Cyclosword, Profane Hydra ; Bastionbreaker absent du set.
4. Un item à la fois dans le chemin et dans un autre core est en « Situationnels », pas en « Autres cores » (régression
   du 2026-09-25 conservée).
5. Page sans `popPath`, core absent des deux pages ou chemin malformé : « Situationnels » = ancien calcul, `path_games == 0`,
   aucune exception ; la boucle de draft continue.
6. Duel : un item significatif dans le chemin est en tête de « Situationnels » ; hors chemin et dans un autre core, en tête
   de « Autres cores » ; dans aucun, absent du set et de `substitutions`. Un core substitué par le duel relit son chemin.
7. `grep -rn "LOADOUT_PATH_MIN_SHARE\|LOADOUT_PATH_MIN_GAMES\|LOADOUT_ALT_CORE_ITEMS" src/` ne trouve leurs définitions que
   dans `src/config_constants.py` ; `src/draft/loadout.py` les lit via `draft_config`, sans seuil littéral.
8. `python scripts/bench_loadout_paths.py` (12 pages) : zéro item de « Situationnels » hors chemin, taux de repli et nombre
   médian de situationnels notés en §1 avec leur date.
9. `python scripts/measure_en_partie.py` : marge ≥ 30 px à 1 920 × 986 avec le bloc « Autres cores » dans le cas le plus lourd.
10. `CHANGELOG.md` (`[Unreleased]`), statut de cette spec, `docs/specs/README.md` et `TODO.md` à jour.

**Vérification de bout en bout** : @pj35 verrouille Ambessa (ou Yorick) en partie réelle, puis ouvre le set d'items « LS »
dans le client : « Situationnels » ne contient que des suites du core, « Autres cores » les autres seconds items, et la
console affiche la ligne `[INFO] Situationnels : suites du core (N parties)`.

## 7. Hors périmètre

- ❌ **Onglets par premier objet et correctif du test binomial du duel** : abandonnés par @pj35 le 2026-10-08. Le test de
  §3.2.3 est repris tel quel ; rappel : il compte des parties d'un même joueur comme indépendantes, donc sa p-value
  surestime la significativité.
- ❌ **Règles de contre-items** (Serpent's Fang contre un support à boucliers) : sans métrique pour peser la
  recommandation, abandonnées le 2026-09-25.
- ❌ **Ordre d'achat** des situationnels (`popClassicPath`, `matchHistory`) : le chemin donne quoi acheter après le core,
  pas dans quel ordre selon la partie ; les parts de `popClassicPath` ne dépassent pas 12 %.
- ❌ **Winrate des items** : OneTricks ne publie que des fréquences ; la source avec mesure d'efficacité (Coachless) reste
  exclue par ses CGU (SPEC-15 §2.1.1).
