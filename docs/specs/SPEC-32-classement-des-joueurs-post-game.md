# SPEC-32 — Classement des joueurs en post-game : MVP et ACE

**Statut** : 🟡 Rédigée le 2026-10-12 ; score, forme et règle de l'ACE validés par @pj35 le 2026-10-12, un point « à valider » en §2 (emplacement dans la page).

**Origine** : @pj35, 2026-10-12 : « J'aimerais que le post game donne également un classement des joueurs (en utilisant les
icônes des champions via l'API DataDragons) en fonction de leur impact dans la game (avec un petit badge/couronne pour le
MVP (meilleur joueur gagnant) et le ACE (meilleur joueur perdant)) »

**Effort** : ~1,5 jour, 4 tâches, 12 pts (§5).

---

## 1. Constat

Mesuré le 2026-10-12 sur `data/db.db` ouverte en `mode=ro` (98 parties avec impact, 100 parties capturées dont 100 avec
timeline ; 24 315 lignes de `game_impact`, modèle `wp-361f2990`).

- **Tout est déjà en base pour les dix joueurs.** `game_impact` porte une ligne par joueur et par événement, pour les
  deux équipes (`winprob/impact.py:65-109`) ; `game_page` relit déjà ces lignes pour toute la partie
  (`src/client/review.py:365`, `repo.impact_rows(game_id)`), puis n'en garde que celles du joueur. Un seul joueur sur 980
  (parties × joueurs) a un impact nul faute de ligne. Les dix postes sont connus : `game_metrics` en donne un pour chaque
  participant (196 occurrences par poste sur 98 parties).
- **Rien n'affiche aujourd'hui le classement.** `grep -rn "MVP\|ACE"` ne trouve rien dans le dépôt ; la page
  (`src/client/templates/partie.html`) montre la courbe, les événements coûteux et rentables **du joueur** et la pile
  d'impact de l'équipe, jamais les neuf autres joueurs.
- **Les portraits existent.** `Champions.image(champion_id)` (`src/client/draft_view.py:107`) renvoie
  `/assets/champion/{id}.png`, servi par `assets.py` depuis un cache disque alimenté par Data Dragon ; image absente =
  emplacement neutre. Aucune nouvelle source ni requête réseau.
- **Le ΔP cumulé n'est pas centré sur zéro, d'où un classement par équipe.** Somme moyenne des cinq joueurs d'une équipe :
  **+70,8 pts** côté gagnant, **−23,5 pts** côté perdant (SPEC-22 : les objectifs perdus ne sont débités à personne). Le n° 1
  de la partie entière est du côté gagnant **94 fois sur 98** : dans un classement unique de 1 à 10, l'ACE serait 5ᵉ ou 6ᵉ dans
  53 parties sur 98 (rang 1 : 4, 2 : 7, 3 : 16, 4 : 18, 5 : 25, 6 : 28), donc loin de la couronne qu'il porte.
- **L'ACE est négatif dans 17 parties sur 98** (le meilleur perdant a perdu de la win chance sur l'ensemble de la partie).
- **Ex æquo rares** : écart de moins de 0,2 pt entre les deux premiers de l'équipe gagnante dans 3 parties sur 98, de la
  perdante dans 2.
- **Biais par poste, modéré.** Rang moyen dans l'équipe (1 à 5, neutre = 3) : jungle 2,48, support 2,80, mid 2,99, top 3,36,
  bot 3,38 (196 occurrences chacun). Le ΔP voit les kills et les objectifs, pas la vision, le farm ni les dégâts hors
  événements : le jungle monte, le bot descend.
- **L'impact n'est pas le KDA ni les dégâts.** Le n° 1 d'une équipe par ΔP est aussi celui du meilleur (K+A)/max(D,1) dans 60
  parties sur 98 chez les gagnants (63 chez les perdants), et celui des plus gros dégâts aux champions dans 36 sur 98 (36 chez
  les perdants). Le classement dira donc autre chose que le tableau de fin de partie du client LoL : c'est voulu, c'est la
  mesure de SPEC-20, pas un score de combat.

## 2. Objectif et arbitrages

Après chaque partie capturée, la revue montre les dix joueurs classés par impact sur la win chance, avec leur portrait, et
couronne le meilleur joueur de l'équipe gagnante (MVP) et celui de l'équipe perdante (ACE).

| Sujet | Décision |
|---|---|
| Score du classement | **Validé (@pj35, 2026-10-12)** : ΔP cumulé de SPEC-20, somme de `game_impact` par participant, en points de win chance. Pas de score composite : une pondération dégâts / vision / farm serait inventée, sans mesure pour la fonder (même raison que pour les seuils refusés en SPEC-18). Quand SPEC-22 sera livrée, le classement se recalcule seul (il lit `game_impact`). |
| Forme | **Validé (@pj35, 2026-10-12)** : deux listes de cinq, chacune classée de 1 à 5 : « Ton équipe » à gauche, « Équipe adverse » à droite, quel que soit le résultat. Pas de classement unique de 1 à 10 (§1). |
| MVP / ACE | **Validé (@pj35, 2026-10-12)** : MVP = n° 1 de l'équipe qui a gagné ; ACE = n° 1 de l'équipe qui a perdu. Toujours attribués quand une équipe a gagné et l'autre perdu. |
| ACE à impact négatif | **Validé (@pj35, 2026-10-12)** : le badge est posé quand même (l'ACE est relatif) ; l'impact reste affiché signé et en rose. Aucun seuil. |
| Partie sans vainqueur (remake) | **Défaut** : aucun badge si les deux équipes n'ont pas un vainqueur et un perdant ; le classement s'affiche sans couronne. |
| Ex æquo | **Défaut** : l'ordre se fait sur le ΔP exact, puis sur `participantId` croissant (déterministe) ; l'affichage à 0,1 pt peut montrer deux fois la même valeur. |
| Où | **Défaut** : `/postgame` et `/parties/{id}` (même gabarit `partie.html`). Pas dans `/historique/{id}` : ses parties ne sont pas capturées, donc sans impact. |
| Emplacement dans la page | **À valider** : panneau pleine largeur de la colonne principale, entre la courbe de win chance et les deux cartes « plus coûteux / plus rentables ». Au-delà de 1 500 px de large, les deux listes sont côte à côte ; en dessous, empilées (même point de rupture que `.cols`, `style.css:694`). |
| Badges | **Défaut** : couronne et texte (« MVP » en or, « ACE » en violet). Le texte porte le sens : la couleur ne l'est pas seule. À voir à l'œil par @pj35. |
| Constantes | **Défaut** : aucune. Pas de seuil ni de taille réglable : cinq joueurs par équipe, un MVP, un ACE. |

## 3. Approches considérées

| Approche | Pour | Contre |
|---|---|---|
| **A. Classement par équipe sur le ΔP stocké, calculé à la lecture (retenue)** | Zéro migration, zéro nouvelle requête ; suit SPEC-22 sans retouche ; MVP et ACE sortent de la définition, sans seuil | Ne voit ni la vision ni le farm (§1) ; recalculé à chaque affichage (dix sommes) |
| B. Stocker `mvp` / `ace` par partie dans une table | Interrogeable (« combien de MVP ce mois-ci ») | Migration Alembic et double source de vérité ; le recalcul de SPEC-22 (tâche 60) obligerait à le rejouer ; personne ne demande l'historique |
| C. Score composite (ΔP + dégâts + vision + farm) | Plus proche d'un « OP score » classique | Pondération arbitraire, non calibrée ; écarté par @pj35 |

A retenue : le besoin est une lecture, pas un historique ; B s'ajoutera si un bilan du nombre de MVP est demandé.

## 4. Détail

### 4.1 Module `src/client/classement.py` (nouveau)

`review.py` fait 458 lignes ; le classement y ferait dépasser 500. Module pur, sans base ni réseau :

```python
def ranking(
    rows: List[dict], game: dict, roles: Dict[int, str], pid: int, champions: Champions
) -> Optional[dict]:
    """Les deux équipes classées par ΔP cumulé, la plus proche (celle de `pid`) d'abord.
    None si `rows` est vide ou si le brut de la partie est illisible."""
```

Sortie :

```python
{"teams": [
    {"win": True, "mine": True, "players": [
        {"pid": 3, "rank": 1, "impact": 0.052, "champion": "Wukong", "portrait": "/assets/champion/MonkeyKing.png",
         "role": "Jungle", "kda": "7 / 2 / 9", "me": False, "badge": "MVP"},
        ...]},
    {"win": False, "mine": False, "players": [... "badge": "ACE" sur le n° 1 ...]},
]}
```

- `impact` = Σ `delta_p` des lignes du participant ; un participant du brut sans ligne vaut `0.0` (il reste dans la liste).
- Équipes lues sur `participants[*].teamId` ; `win` sur `stats.win` ; tri par `(-impact, participantId)`.
- `badge` : `"MVP"` sur le n° 1 de l'équipe où `win` est vrai, `"ACE"` sur le n° 1 de celle où il est faux, seulement si une
  équipe a gagné et l'autre perdu ; sinon `None` partout.
- `role` : `ROLE_LABELS.get(roles.get(pid))`, `None` si la partie n'a pas de métriques. Le champion vient de
  `Champions.name` / `Champions.image` (nom Data Dragon, portrait local).
- Best-effort comme `_residual` : `KeyError`, `TypeError` ou `ValueError` donnent `None`, et la revue s'affiche sans classement.

### 4.2 `game_page` (`src/client/review.py`)

- Nouvelle clé `page["ranking"]`, `None` par défaut. Appelée avec les `rows` déjà lues (`review.py:365`) et `roles` déjà lus
  (`review.py:316`) : aucune requête de plus.
- Pour chaque joueur : `impact_text = _pts(impact)` (`review.py:84`, virgule française, vrai signe moins), puis
  `**_bar(impact, plus_grand_ecart)` (`review.py:443`) où l'échelle est le plus grand `|impact|` **des dix joueurs** : les deux
  listes se lisent à la même échelle. `tone` : `"gain"` si `impact >= 0`, sinon `"cost"`.
- Sans `rows` (impact non calculé) ou sans timeline : `ranking` reste `None`, et les notes existantes (`curve_note`,
  `impact_note`) disent déjà pourquoi. Aucune note de plus.

### 4.3 Gabarit et CSS (`src/client/templates/partie.html`, `src/client/static/style.css`)

Panneau `<section class="panel ranking">` dans `.main`, après `game-curve`, absent quand `g.ranking` est `None` :

- en-tête « Classement de la partie » et, à droite, « impact sur la win chance, pts » (`muted-2`, comme la pile d'impact) ;
- une colonne par équipe, titrée « Ton équipe · Victoire » / « Équipe adverse · Défaite » (menthe ou rose) ;
- une ligne par joueur : rang (1 à 5), `<img class="rank-champ" src=… alt="{{ champion }}" width height>`, nom et poste
  (« Jungle »), KDA, barre divergente (`.diverge` et `.diverge-bar`, mêmes classes que la pile d'impact), valeur en points,
  couleur selon `tone` ; la ligne du joueur (`me`) reçoit la classe `is-me` et le mot « toi » (comme `partie.html:73`) ;
- le badge dans la ligne du n° 1 : `<span class="rank-badge mvp" aria-label="MVP de la partie">` avec un SVG de couronne et le
  texte `MVP` (`--gold`), ou `ACE` (`--violet`). Le sens ne repose pas sur la couleur seule.
- apparition par `data-rise` / `data-delay` (réglage Motion « Réduit » déjà respecté par `motion.js`) ; **aucun JavaScript
  nouveau**, donc aucune sonde d'interface à lancer sans accord de @pj35.
- `@media (max-width: 1500px)` : les deux listes s'empilent.

### 4.4 Tests

Hermétiques, sur les fixtures existantes (`tests/test_client_parties.py` : `GAME`, `capture`, `roles`, `impact`).

- `tests/test_client_classement.py` : sur un brut à dix participants construit à la main : équipes de cinq classées par ΔP
  décroissant, MVP sur le n° 1 gagnant, ACE sur le n° 1 perdant (**y compris à impact négatif**), ordre stable aux ex æquo,
  participant sans ligne à `0.0`, aucun badge sans vainqueur (remake), `None` sans lignes, `None` sur un brut illisible,
  l'équipe de `pid` en premier même quand elle a perdu.
- Pages : `/postgame` et `/parties/{id}` rendent dix `<img … /assets/champion/…>`, un seul `MVP`, un seul `ACE`, la ligne
  « toi » une fois ; sans impact ou sans timeline, le panneau est absent et la page répond 200 avec ses notes ; la variante
  Défaite met l'équipe du joueur à gauche avec le badge `ACE`.
- Pas de test de régression dans `tests/regression/` : fonctionnalité nouvelle, pas un bug.

## 5. Tâches

Numéros à la suite de la tâche 146.

| # | Tâche | Pts | Dépend de |
|---|---|---|---|
| 147 | `src/client/classement.py` : `ranking` (ΔP par participant, équipes, MVP / ACE, ex æquo, remake, best-effort) et tests purs §4.4 | 3 | — |
| 148 | `game_page` : clé `ranking`, `_pts` et `_bar` partagés sur les dix joueurs, absence sans impact, tests de page | 2 | 147 |
| 149 | Gabarit et CSS : panneau à deux listes, portraits, barres, badges MVP et ACE, point de rupture à 1 500 px, tests de rendu (`TestClient`) | 5 | 148 |
| 150 | Clôture : critère 8 sur la base réelle, `check_exe_assets.py` et `PROJECT_STRUCTURE.md` (nouveau module), `CHANGELOG.md`, statuts, README des specs, recette @pj35 | 2 | 149 |

## 6. Critères d'acceptation

1. `python -m pytest tests/ -v` vert, avec les tests des tâches 147 à 149.
2. `python -m pytest tests/test_client_classement.py -v` : chaque équipe a cinq joueurs classés par ΔP décroissant, exactement
   un MVP (n° 1 de l'équipe gagnante) et un ACE (n° 1 de l'équipe perdante) ; l'ACE d'une équipe à impact négatif est
   couronné.
3. Même fichier : un brut sans vainqueur ne porte aucun badge ; des `rows` vides ou un brut sans `participants` donnent `None`
   sans exception.
4. `/postgame` et `/parties/{id}` : le HTML contient dix portraits `/assets/champion/…`, une couronne `MVP`, une couronne `ACE`
   et une seule ligne `is-me`.
5. Une partie sans timeline ou sans impact : réponse 200, aucun panneau « Classement de la partie », notes existantes inchangées.
6. `wc -l src/client/review.py src/client/classement.py` : chacun sous 500 lignes.
7. `grep -n "requests\|urlopen\|ddragon" src/client/classement.py` ne trouve rien : les portraits viennent de `Champions.image`.
8. Sur la base réelle, en lecture seule (`src/client/db.py:read_only`), pour chacune des 98 parties avec impact :
   `ranking(...)` renvoie deux équipes de cinq joueurs, un MVP, un ACE, sans exception ; le nombre de parties à ACE négatif
   retombe sur 17 (mesure du §1). Commande à consigner dans le `CHANGELOG.md` avec le résultat.
9. `CHANGELOG.md` (`[Unreleased]`), statut de cette spec, `docs/specs/README.md` et `TODO.md` à jour.

**Vérification de bout en bout** : @pj35 ouvre `/postgame` après une partie (ou `/parties/{id}` sur une partie capturée) :
deux listes de cinq avec portraits Data Dragon, couronne « MVP » sur le meilleur de l'équipe gagnante, couronne « ACE » sur le
meilleur de la perdante, sa propre ligne repérée par « toi » ; à voir en Réduit et en mode complet, puis à 1 400 px de large
(listes empilées).

## 7. Hors périmètre

- ❌ **Score composite** (dégâts, vision, farm, objectifs hors événements) : pondération sans mesure ; à rouvrir si le biais par
  poste du §1 gêne à l'usage, et après SPEC-22.
- ❌ **Stockage de MVP / ACE par partie** et compteur dans le bilan ou l'accueil : approche B, non demandée.
- ❌ **Classement dans l'écran « En partie »** : l'impact n'y existe pas (il se calcule sur la timeline de fin de partie).
- ❌ **Classement des parties non capturées** (`/historique/{id}`) : pas de timeline, donc pas de ΔP.
- ❌ **Note de 0 à 10** ou lettre (S, A, B) : le ΔP en points de win chance est la seule mesure défendable ici.
