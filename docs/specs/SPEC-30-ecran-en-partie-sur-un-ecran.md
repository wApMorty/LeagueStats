# SPEC-30 — Écran « En partie » lisible et sur un seul écran

**Statut** : 🟡 Rédigée le 2026-10-12, arbitrages de §2 validés par @pj35 le 2026-10-12 ; rien « à valider ».

**Origine** : @pj35, 2026-10-12 : « J'aimerais qu'on améliore l'écran de Partie en cours ! Il faudrait repenser son
design pour qu'il soit plus lisible, et tienne sur un seul écran sans scroll. »

**Effort** : ~1,5 jour, 4 tâches, 13 pts (§5).

---

## 1. Constat

Lecture du code le 2026-10-12 (aucune mesure en fenêtre : l'estimation ci-dessous est arithmétique, la tâche 140 la
remplace par une mesure).

- **Une seule colonne de quatre panneaux empilés** (`src/client/templates/partials/en_partie_stage.html`) : bandeau
  horloge et win chance (`ig-head`, l.6), courbe (`ig-curve`, l.15), build (`ig-build`, l.23), face-à-face (`ig-draft`,
  l.60). Aucune grille : `.page-en-partie` n'a que des marges (`style.css:1080` et `:1095`).
- **La courbe prend à elle seule les deux tiers de la hauteur utile.** Le SVG a un `viewBox` de
  `GAME_CURVE_SIZE = (1124, 430)` (`src/config_client.py:138`) et `.chart { width: 100%; height: auto }`
  (`style.css:727`). À 1 920 px de large, la zone de contenu fait 1 920 − 220 (`--nav-w`) − 96 (padding de `.page`,
  `style.css:165`) − 48 (padding de `.panel`) ≈ 1 554 px, donc une courbe de 1 554 × 430 / 1 124 ≈ **594 px** de haut.
- **Hauteur totale estimée ≈ 1 600 px pour 890 utiles** (fenêtre 1 920 × 950, padding de page 2 × 30) : en-tête de
  page ~110, bandeau ~115, courbe ~690 avec son panneau, build ~360 (jusqu'à six blocs : Départ, Autres départs, Core,
  Bottes, Composants, Situationnels, `src/draft/loadout.py:157-172`, plus adaptations et compétences), face-à-face ~330.
- **Le face-à-face a huit colonnes de chiffres** (Mat, Syn, Tot de chaque côté, plus Duel, l.63) et aucun portrait : le
  nom seul, tel que la base le stocke (`MonkeyKing`, `KSante`, `Kaisa` : table `champions`, lue le 2026-10-12).
- **Écran de référence déjà tranché pour le client** : SPEC-29 §2, « tenir sans défiler dans 1 920 × 950, ≥ 1 500 px
  de large, deux colonnes ; en dessous la page peut défiler », appliqué à l'accueil.
- **SPEC-27 (non commencée) écrit sur ce même gabarit** : sa tâche 127 ajoute une ligne d'état sous l'en-tête du
  face-à-face et marque les lignes corrigées (SPEC-27 §4.6).

## 2. Objectif et arbitrages

Toute l'information utile d'une partie en cours se lit d'un coup d'œil, sans défiler, dans 1 920 × 950.

| Sujet | Décision |
|---|---|
| Disposition | **Validé (@pj35, 2026-10-12)** : deux colonnes. À gauche « ma partie » (prochain objet, plan, adaptations, compétences) ; à droite la win chance (courbe compacte) puis le face-à-face. Horloge, état et win chance en un bandeau d'une ligne au-dessus. |
| Écran de référence | **Validé (@pj35, 2026-10-12)** : comme SPEC-29, sans défilement à 1 920 × 950 (≥ 1 500 px de large, deux colonnes) ; sous 1 500 px, une colonne qui peut défiler. CSS seul, pas de scène mise à l'échelle. |
| Allègement | **Validé (@pj35, 2026-10-12)** : colonnes Mat et Syn retirées du face-à-face (Total et Duel restent ; Mat et Syn passent en infobulle du Total). Le reste est **gardé** : les six blocs du plan, la liste « Adaptations au duel », la win chance au bandeau et dans l'en-tête de la courbe. |
| Ajout | **Validé (@pj35, 2026-10-12)** : portrait du champion dans le face-à-face. Défaut retenu avec : le nom affiché devient celui de Data Dragon (`Wukong`, `K'Sante`) quand le portrait est trouvé ; sinon ni portrait ni changement de nom (ignorance visible : le nom de la base reste). |
| Vérification | **Validé (@pj35, 2026-10-12)** : mesure en Firefox headless (Selenium déjà installé, aucune fenêtre visible, curseur intouché) sur le cas le plus lourd, rejouable sans @pj35. |
| SPEC-27 | **Validé (@pj35, 2026-10-12)** : cette spec d'abord. Le gabarit réserve la ligne d'état de SPEC-27 dans le panneau du face-à-face ; la tâche 127 de SPEC-27 est réécrite pour viser ce gabarit (tâche 141). |

## 3. Approches considérées

- **A. Grille CSS à deux colonnes, courbe recalibrée** (retenue). On réordonne le gabarit, on ajoute une grille et on
  change le `viewBox` de la courbe pour qu'elle soit basse à la largeur d'une colonne. Texte à taille réelle, même règle
  que l'accueil. Limite : sous 1 500 px, la page défile (accepté, SPEC-29).
- **B. Scène fixe 1 920 × 950 mise à l'échelle** comme l'écran Draft (`draft.js:376`). Jamais de défilement, mais texte
  à ~67 % dans la fenêtre par défaut 1 280 × 800 et un second mécanisme de mise à l'échelle à maintenir. Écartée par
  @pj35.
- **C. Panneaux repliables ou onglets.** Tient en hauteur en cachant de l'information : contraire au « d'un coup
  d'œil ». Non proposée.

## 4. Détail

### 4.1 Vue (`src/client/en_partie.py`, tâche 138)

- `_score(line, champions)` : ajoute `img` (`str | None`) et `detail` (`"Matchups +1.2 · Synergies -0.4"`, None si
  `thin`) ; `name` devient le nom Data Dragon si le portrait est trouvé. `matchup` et `synergy` ne sont plus rendus en
  colonnes mais restent dans la vue (le `detail` en dérive).
- `analysis_view(analysis, champions=None)` et `en_partie_view(ingame, analysis, items=None, champions=None)` :
  `champions` est un `Champions` (`src/client/draft_view.py:79`) ; None (tests existants) : aucun portrait.
- `Champions.by_name(name) -> Optional[Dict[str, str]]` (`src/client/draft_view.py`) : `{"img", "name"}` du champion
  dont l'`id` ou le `name` Data Dragon, réduit aux lettres et chiffres en minuscules, égale `name` réduit de même ;
  None sinon. Index construit une fois dans `__init__`. Couvre les noms de la base (`MonkeyKing` = `id` de Wukong,
  `Kaisa`, `KSante`) et ceux des tests (`Lee Sin`).
- `src/client/app.py:474` `ingame_view()` : passe `Champions(app.state.assets)` quand une analyse existe.

### 4.2 Gabarit (`templates/partials/en_partie_stage.html`, tâche 139)

Ordre et classes (les textes et états actuels sont conservés, seul l'agencement change) :

```
<div class="ig-strip">  horloge · « Partie en cours / terminée » · win chance + variation (ou notice « pas de modèle »)
<div class="ig-grid">
  <div class="ig-col">   panneau Build : prochain objet (icône 48 px), plan (6 blocs), adaptations, compétences
                          (ou panneau « Plan de build indisponible »)
  <div class="ig-col">   panneau Win chance en direct (courbe) ; panneau Face-à-face :
                          en-tête (évaluation · probabilité · écart), emplacement de la ligne d'état SPEC-27
                          (rien rendu tant que la charge n'a pas `reality`), tableau à 5 colonnes :
                          portrait + nom | Tot | Duel | Tot | nom + portrait ; Tot porte `title="{{ detail }}"`
```

- `ig-strip` remplace le panneau `ig-head` : une ligne sans fond de panneau, chiffres à 34 px comme aujourd'hui.
  Les classes `ig-clock` et `ig-chance` restent (tests existants).
- Légende sous le tableau raccourcie à une ligne : « Tot : matchups + synergies, en points de victoire (détail au
  survol). Duel : la lane, + = avantage pour vous. »
- Les cellules de nom gardent `ig-side ig-ally-ink` / `ig-side ig-foe-ink` ; le portrait est un `<img class="ig-champ">`
  avant (allié) ou après (ennemi) le texte, absent sans `img`.
- L'état `idle` (« Pas de partie en cours ») ne change pas.

### 4.3 CSS et constantes (tâche 139)

`src/client/static/style.css`, bloc « En partie » (`:1080` à `:1108`) :

- `.page-en-partie .page-head { margin-bottom: 16px; }`
- `.ig-strip { display: flex; align-items: baseline; justify-content: space-between; gap: 24px; margin-bottom: 16px; }`
- `.ig-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 24px 32px; align-items: start; }`,
  `.ig-col { display: flex; flex-direction: column; gap: 24px; min-width: 0; }`,
  `@media (max-width: 1500px) { .ig-grid { grid-template-columns: minmax(0, 1fr); } }` (même seuil que `.cols`, `:694`).
- Les marges `margin-bottom: 20px` de `ig-head`, `ig-curve`, `ig-build` disparaissent (le `gap` les remplace).
- `.ig-champ { width: 32px; height: 32px; border-radius: 50%; vertical-align: middle; }`, lignes du tableau à
  `padding: 6px 10px`.
- Prochain objet : `.ig-next .ig-item { width: 48px; height: 48px; }`.

`src/config_client.py` : `GAME_CURVE_SIZE = (736, 220)` (au lieu de `(1124, 430)`). Origine : largeur intérieure d'une
colonne à 1 920 px ≈ (1 920 − 220 − 96 − 32) / 2 − 48 − 2 = 736, donc un `viewBox` à l'échelle 1 (ticks à 13 px réels)
et 220 px de haut. `GAME_CURVE_MARGIN` inchangé sauf si la mesure montre des étiquettes rognées (à noter dans la
tâche 140).

**Budget à 1 920 × 950** (arithmétique, la tâche 140 tranche) : 890 utiles − en-tête de page ~83 − bandeau ~66 =
~741 par colonne. Droite : courbe 36 + 36 + 220 = 292, gap 24, face-à-face 36 + 36 + ligne SPEC-27 24 + en-tête 30 +
5 × 44 + légende 20 ≈ 370, soit ~686. Gauche, cas le plus lourd : 36 + 36 + prochain objet 60 + blocs ~3 rangées × 74
+ adaptations ~5 lignes 144 + compétences 40 + notice d'achats 40 ≈ 580.

### 4.4 Mesure (`scripts/measure_en_partie.py`, nouveau, tâche 140)

Script hors pytest (il lance Firefox) :

1. Crée l'application avec `create_app(db_path, bus=EventBus(), assets=...)` sur une base temporaire
   (`tempfile.TemporaryDirectory`, jamais `data/db.db`) et un `Assets` de cache temporaire sans réseau (les images
   tombent sur `PLACEHOLDER`, aux tailles fixées par le CSS).
2. Publie le **cas le plus lourd** : `ingame` en `live` sans modèle (`p` None, notice affichée) puis avec modèle et
   une série de 30 min à 5 s ; `game` avec cinq lignes complètes, un `loadout` aux six blocs pleins
   (`LOADOUT_SITUATIONAL_ITEMS` objets en Situationnels, 10 en Composants), quatre substitutions et l'ordre des
   compétences. Tant que SPEC-27 ne rend pas sa ligne d'état, le script en insère une (`<p class="fine">` d'une
   ligne, sous l'en-tête du face-à-face) par `execute_script` avant de mesurer.
3. Sert l'app avec `uvicorn.Server` dans un fil sur un port libre de `127.0.0.1`, ouvre Firefox headless
   (`Options().add_argument("-headless")`, `--width=1920 --height=986`), charge `/en-partie`.
4. Imprime et vérifie `page.scrollHeight <= page.clientHeight` et `page.scrollWidth <= page.clientWidth` pour
   `page = document.querySelector(".page")`, puis la marge restante ; sort en code 1 sinon. Sorties `[OK]` /
   `[ERREUR]`, sans emoji. Refait la mesure à 1 400 × 900 pour constater qu'une colonne s'affiche (aucune exigence de
   hauteur).

La zone utile de 950 px à 1 920 × 986 vient de SPEC-29 §4.3 (barre de titre de 36 px). Firefox rend un peu
différemment de WebView2 : exiger **≥ 30 px de marge** dans le script.

### 4.5 Tests (`tests/test_client_en_partie.py`, tâches 138 et 139)

- Adapter `test_face_a_face_de_la_draft` : plus de colonnes `Mat`/`Syn` dans l'en-tête ; l'infobulle du Total contient
  « Matchups » et « Synergies ».
- Nouveau : avec un `Champions` factice (fixture `assets` de `tests/test_client_draft.py`), un champion connu a son
  `<img class="ig-champ" src="/assets/champion/…png">` et son nom Data Dragon ; un nom inconnu n'a pas d'image et garde
  son nom.
- Nouveau : `Champions.by_name` sur `MonkeyKing`, `Lee Sin`, `lee sin`, et un nom absent (None).
- Nouveau : le fragment contient `ig-strip` et `ig-grid`, pas `ig-head` ; l'ordre est build puis courbe puis
  face-à-face.
- `test_sans_modele_l_ecran_dit_comment_l_entrainer`, `test_en_partie_horloge_win_chance_et_variation` et les tests
  de build (`tests/test_client_en_partie_build.py`) restent verts sans modification de leurs assertions.

## 5. Tâches

Numéros globaux : à la suite de la tâche 137 du `TODO.md`.

| # | Tâche | Pts | Dépend de |
|---|---|---|---|
| 138 | Vue : `Champions.by_name`, `_score` (portrait, nom Data Dragon, `detail`), `champions` passé par `ingame_view` ; tests | 3 | — |
| 139 | Gabarit et CSS : bandeau `ig-strip`, grille `ig-grid` à deux colonnes (build / courbe puis face-à-face), tableau à 5 colonnes, emplacement SPEC-27, une colonne sous 1 500 px, `GAME_CURVE_SIZE` ; tests du fragment | 5 | 138 |
| 140 | Mesure : `scripts/measure_en_partie.py` (Firefox headless, cas le plus lourd, 1 920 × 986), ajustements de CSS jusqu'à ≥ 30 px de marge, chiffres consignés en §4.3 | 3 | 139 |
| 141 | Clôture : SPEC-27 §4.6 et tâche 127 réécrites pour ce gabarit, `CHANGELOG.md`, statut, `docs/specs/README.md`, `TODO.md`, recette @pj35 | 2 | 140 |

## 6. Critères d'acceptation

1. `python -m pytest tests/ -v` vert, avec les tests des tâches 138 et 139.
2. `python -m pytest tests/test_client_en_partie.py -v` : le fragment `live` avec analyse contient `ig-strip`,
   `ig-grid`, aucun `<th>Mat</th>` ni `<th>Syn</th>`, un `title` contenant « Matchups » et « Synergies » par champion
   chiffré, et un `ig-champ` pour chaque champion connu de Data Dragon.
3. `Champions.by_name("MonkeyKing")["name"] == "Wukong"` (avec un `champion.json` qui le contient) et
   `Champions.by_name("Inconnu") is None` (test unitaire).
4. `python scripts/measure_en_partie.py` imprime `[OK]` à 1 920 × 986 : `scrollHeight <= clientHeight` et
   `scrollWidth <= clientWidth` sur `.page`, marge ≥ 30 px, sur le cas le plus lourd (notice « pas de modèle », six
   blocs pleins, quatre adaptations, compétences, ligne SPEC-27 occupée).
5. Le même script à 1 400 × 900 constate une grille à une colonne (`getComputedStyle(.ig-grid).gridTemplateColumns`
   à une valeur).
6. `grep -n "GAME_CURVE_SIZE" src/config_client.py` donne `(736, 220)` ; aucune valeur de réglage nouvelle en dur dans
   `en_partie.py`.
7. SPEC-27 §4.6 et sa tâche 127 (`TODO.md`) visent le panneau du face-à-face du nouveau gabarit.
8. `CHANGELOG.md` (`[Unreleased]`), statut de cette spec, `docs/specs/README.md` et `TODO.md` à jour.

**Vérification de bout en bout** : `python scripts/measure_en_partie.py` (`[OK]`), puis recette @pj35 pendant une
vraie partie, client en plein écran 1 920 × 1 080 : tout l'écran « En partie » visible sans barre de défilement, la
courbe avance, le plan se coche à l'achat, les portraits s'affichent dans le face-à-face.

## 7. Hors périmètre

- ❌ **Scène mise à l'échelle et tenue en 1 280 × 800** : approche B écartée (§3) ; sous 1 500 px la page défile.
- ❌ **Retrait des blocs secondaires du plan, des doublons de win chance, liste d'adaptations en badges** : proposés,
  non retenus par @pj35 (§2).
- ❌ **Jauge d'or et prochain sort à monter** : proposés, non retenus par @pj35 (2026-10-12) ; à rouvrir après usage.
- ❌ **Identifiant de champion dans `FinalAnalysis`** (portrait exact au lieu d'un rapprochement par nom) : le
  rapprochement couvre les noms de la base ; à faire si un portrait manque à la recette.
- ❌ **Contenu de la ligne d'état SPEC-27** : seule sa place est réservée ici ; le texte reste à SPEC-27 §4.6.
