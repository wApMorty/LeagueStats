# Handoff : Client LeagueStats — thème « Alchimie » (atelier des sorciers)

## Vue d'ensemble
Interface graphique du client LeagueStats (SPEC-21) : une coque de fenêtre (barre de titre, navigation, pastille LCU) et six moments :
Accueil coaching, Rang, Progression, Draft interactive (bans, picks, runes, sorts, skin), File trouvée, Post-game.
Direction artistique : grimoire d'alchimiste nocturne. Les cercles runiques et les pentacles **portent la donnée** sur la draft, la file trouvée et le post-game ; ailleurs, ils restent ornementaux. Motion « spectaculaire » par défaut, coupé entièrement en mode Réduit.

## À propos des fichiers de design
Les fichiers `*.dc.html` de ce dossier sont des **références de design écrites en HTML** : des prototypes qui montrent l'apparence et le comportement attendus. Ce n'est **pas** du code de production à copier.
La tâche consiste à **recréer ces écrans dans l'environnement existant du client** :
- FastAPI + gabarits Jinja (`src/client/templates/`) ;
- htmx pour les fragments (`static/htmx.min.js`, jeton de session dans `shell.js`) ;
- CSS statique (`static/style.css`) ;
- JS vanilla, sans dépendance ni étape de build ;
- fenêtre pywebview sans bordure (classe `no-chrome`).

Les prototypes utilisent un moteur maison (`support.js`, styles inline, `{{ }}`). Il ne faut pas le reprendre. Il faut traduire chaque écran en gabarit Jinja, en classes CSS dans `style.css` et en petits modules JS.

Pour ouvrir les prototypes, servez ce dossier en local (`python -m http.server`) et ouvrez `Client Alchimie.dc.html`. Les écrans sont aussi ouvrables seuls.

## Fidélité
**Haute fidélité.** Couleurs, typographies, tailles, espacements, textes et animations sont définitifs.
Les **données** sont fictives (pool GRIND, Sion contre Darius, LP, métriques). À brancher sur les vraies sources (voir « Données »).

## Cadre et grille
- Fenêtre de référence : **1920 × 986**. La barre de titre fait 36 px ; la zone utile fait 1920 × 950.
- Navigation : 220 px de large. Zone de contenu : 1700 × 950.
- **Draft : pas de navigation**, le contenu prend 1920 px. La navigation revient en glissant (−220 px → 0, 520 ms) à la sortie de la draft.
- Marges internes des écrans : 48 px à gauche et à droite (40 px en draft) ; le titre de page commence à 30 px du haut.
- Grille de contenu type : colonne principale de 1124 px, gouttière de 40 px, colonne latérale de 440 px.
- Coins arrondis : 6 px (cartes), 8 px (tuiles), pilule pour les boutons et les puces.

## Design tokens
Couleurs en OKLCH : c'est la source de vérité, à déclarer en propriétés CSS dans `style.css`.

### Fonds
| Jeton | Valeur | Usage |
|---|---|---|
| `--bg` | `oklch(0.15 0.02 170)` | Fond des écrans |
| `--bg-chrome` | `oklch(0.13 0.018 170)` | Barre de titre |
| `--bg-nav` | `oklch(0.14 0.018 170)` | Navigation (dégradé violet en haut, magenta en bas) |
| `--surface` | `oklch(0.195 0.02 170)` | Cartes |
| `--surface-2` | `oklch(0.185 0.02 170)` | Panneaux de graphiques |
| `--surface-pop` | `oklch(0.23 0.022 170)` | Popovers |
| `--overlay` | `oklch(0.13 0.018 170 / 0.97)` | Grimoires plein écran |

### Texte
| Jeton | Valeur |
|---|---|
| `--ink` | `oklch(0.94 0.012 120)` |
| `--ink-2` | `oklch(0.82 0.015 140)` |
| `--muted` | `oklch(0.70 0.02 160)` |
| `--muted-2` | `oklch(0.62 0.03 160)` |

### Accents
| Jeton | Valeur | Usage |
|---|---|---|
| `--copper` | `oklch(0.74 0.11 55)` | Marque, filets, boutons primaires |
| `--gold` | `oklch(0.86 0.13 85)` | Sélection, pool, objectifs |
| `--mint` | `oklch(0.82 0.13 165)` | Nous, positif, victoire |
| `--rose` | `oklch(0.72 0.21 345)` | Eux, négatif, bans |
| `--violet` | `oklch(0.72 0.20 290)` | Complémentaire du cuivre |
| `--blue` | `oklch(0.74 0.15 230)` | Complémentaire de l'or |
| `--magenta` | `oklch(0.70 0.27 345)` | Complémentaire de la menthe |

- **Filets :** `--copper` à 14–25 % d'opacité (`oklch(0.74 0.11 55 / 0.2)`).
- **Halos de fond :** 3 dégradés radiaux par écran, en violet `oklch(0.25 0.09 290 / .75)`, cyan `oklch(0.24 0.07 190 / .8)` et magenta `oklch(0.23 0.08 345 / .55)`, posés sur `--bg`. La position varie par écran (voir les fichiers).
- **Arbres de runes :**

| Arbre | Couleur |
|---|---|
| Précision | `oklch(0.86 0.13 85)` |
| Domination | `oklch(0.70 0.21 20)` |
| Sorcellerie | `oklch(0.72 0.17 280)` |
| Volonté | `oklch(0.78 0.15 150)` |
| Inspiration | `oklch(0.80 0.12 210)` |

- **Teinte par rôle** (OKLCH, H) : Top 55, Jungle 150, Mid 290, Bot 85, Support 230.

### Typographie (Google Fonts)
- **Titres et chiffres :** *Cormorant Garamond* 600 (italique 500 pour les citations). Titre de page 46/1 ; titre de draft 38/1 ; titre de section 26–30/1 ; nom de champion 21–28/1.05 ; grands chiffres 58–64/1, en `tabular-nums`.
- **Texte d'interface :** *Alegreya Sans* 400/500/700. Corps 14–17 px ; sur-titres 11–12 px en `uppercase`, `letter-spacing` 0.18–0.22em.
- **Runes décoratives :** *Noto Sans Runic*. **Jamais porteuses de sens** : ornements, anneaux et icônes de navigation à côté d'un libellé uniquement.

### Ombres et lueurs
Lueurs de la couleur d'accent, par exemple `0 0 22px oklch(0.8 0.1 165 / 0.35)` sur les portraits. Ombre de popover : `0 20px 40px oklch(0.08 0.02 170 / 0.6)`.

## Écrans

### Coque (`Client Alchimie.dc.html`)
**Barre de titre (36 px)**
- Logo : pentacle de 16 px dans un cercle, puis « LEAGUESTATS » en 12 px.
- Au centre, la file :
  - « Lancer la file · Classée solo/duo » (pilule, filet cuivre) ;
  - pendant la recherche, anneau en pointillé qui tourne, chrono et « Annuler » ;
  - en draft, « Champ select en cours ».
- Pastille « Client LoL connecté » avec un point menthe pulsé.
- Boutons système de 46 px (le bouton fermer devient rouge au survol).
- Liseré inférieur en dégradé cuivre → violet → menthe → magenta.

**Navigation (220 px)**
- Trois groupes : Coaching (Accueil, Rang, Progression, Parties, Calibration), Partie (Draft, Post-game), Client (Profil, Collection, Lobby, Social).
- Chaque entrée : une rune colorée à la teinte de l'entrée, puis le libellé en 15 px.
- Entrée active : dégradé de sa teinte vers transparent et liseré interne.
- En bas : réglage Thème, et réglage Motion en segmenté Système / Complet / Réduit.
- Les entrées des lots suivants (Parties, Calibration, Profil, Collection, Lobby, Social) sont grisées.

### Accueil (`Accueil.dc.html`)
- **En-tête :** « Coaching · rôle principal Top », titre « Accueil », et à droite l'état de la base (« 48 parties capturées · dernière il y a 2 h »).
- **Axes de travail :** 2 cartes de 250 px de haut ; l'axe 1 est en violet, l'axe 2 en bleu.
  - Contenu : origine (proposé par le coach / fixé par toi), métrique, rôle et cible, 5 pastilles tenu/non tenu (menthe pleine ou rose vide), « Tenu x fois sur les 5 dernières · acquis à 4 sur 5 », « Clore l'axe ».
  - Place libre : la proposition du coach, avec « Fixer cet axe » et « Choisir une autre métrique ».
- **Derniers constats :** tableau Métrique / Toi / Norme · objectif / Écart / σ, avec une barre divergente centrée sur la norme.
- **Colonne latérale :**
  - carte Rang (palier, LP, sparkline sur 30 jours) ;
  - les 10 dernières parties en portraits cerclés menthe ou rose ;
  - bilan du rôle (points forts, à travailler).

### Rang (`Rang.dc.html`)
- **Courbe :** 1124 × 560 ; échelle continue de 100 LP par division ; libellés des paliers à gauche, dates en bas.
  - Bandes de fond : Platine en bleu-cyan, Émeraude en vert ; ligne de séparation or à 400.
  - Solo : dégradé bleu → vert, avec aire. Flex : dégradé violet → magenta.
  - Dernier point lumineux, étiquette « Émeraude II · 47 LP ».
- **LP par partie :** histogramme divergent des 20 dernières parties.
- **Cartes par file :** palier, LP en compteur, V / D / taux de victoire, delta sur 30 jours.
- **Règle :** sous 2 photos, une file n'a pas de courbe.

### Progression (`Progression.dc.html`)
- **Puces de rôle :** une par rôle, à sa teinte, avec le nombre de parties.
- **Grille du rôle :** une ligne par métrique de `src/coaching/grid.py`.
  - Colonnes : Métrique (losange coloré), Poids (●● principal / ● secondaire), Toi, Norme, Objectif, Tendance, Verdict.
  - Tendance : sparkline de 190 × 40 ; en trait plein le z face à la norme, en pointillé le z face à l'objectif.
  - Verdict : en progrès (menthe), en recul (rose) ou stable.
- **Sous 5 parties :** pas de verdict, pastille en pointillé « n/5 parties, pas de verdict ».
- **Colonne latérale :** échantillon, schémas (pentacle coloré et phrase), légende.

### Draft (`Draft.dc.html`) — écran clé
**Positions (zone de 1920 × 950)**

| Élément | Position et taille |
|---|---|
| En-tête | 40, 22 · 1400 × 68 |
| Sceau allié | 70, 104 · 520 × 520 |
| Balance | 650, 150 · 180 px de large |
| Sceau adverse | 890, 104 · 520 × 520 |
| Rangée basse | 40, 640 → bas − 26 · 1400 de large |
| Colonne loadout | à partir de x 1480 (440 px de large) |

**Sceaux d'équipe**
- 2 anneaux tournants (160 s, sens opposés) avec un anneau runique.
- Pentacle de rayon 190 : un rôle par branche, portraits de 92 px.
- Moi : portrait de 104 px à la pointe haute, cercle en pointillé qui tourne tant que je ne suis pas verrouillé.
- Le reste de l'équipe sur les branches 4, 3, 2, 1. Adversaires sur les branches 0 à 4.
- Adversaire inconnu : cercle en pointillé rose avec la rune ᛃ pulsée.

**Balance**
- Jauge verticale de 46 × 270 : dégradé menthe → bleu côté nous, magenta côté eux, curseur or.
- Pourcentage en 58 px (anime 800 ms, ease-out cubique).
- Note « si X est verrouillé ».

**En-tête**
- Fil d'Ariane, titre (effet runes → lettres), chrono circulaire de 64 px.
- Bans alliés (5) et adverses (5), en pastilles de 32 px barrées. Mon ban : pastille de 40 px.

**Phase de bans**
- Mon ban : 40 px, bordure magenta en pointillé lumineux, aperçu de la cible à 50 %.
- Bans adverses cachés : rune ᛜ.
- Rangée basse : « Bans conseillés · menaces pour ton pool », 4 cartes (gain « +2,9 pts si banni » et justification).
- Bouton principal « Bannir X » en magenta.
- Après le ban : tampon et explosion magenta. 1,1 s plus tard, révélation des bans adverses en cascade (120 ms), puis apparition des picks adverses (150 ms), puis passage en phase de picks.

**Phase de picks**
- 4 cartes de recommandation (lien de couleur en haut : or, menthe, bleu, violet) : portrait, nom, games, win % sur 2 décimales, delta en pts (menthe ou rose), « Suite attendue : … ».
- Clic sur une carte = survol. Le bouton principal « Verrouiller X » est en haut à droite de la rangée.

**Grimoire des champions** (overlay sur 1480 × 950)
- Ouverture : bouton « Tous les champions », clic sur mon portrait ou sur mon emplacement de ban.
- Recherche (accents ignorés), puces de rôle (Top par défaut), « Pool GRIND uniquement », compteur.
- Grille `auto-fill minmax(104px, 1fr)` de portraits de 76 px.
- Tri : recommandations, puis pool, puis ordre alphabétique.
- Méta sous chaque nom : win % (menthe), « pool » (or), « +x pts » en ban.
- Losange or si le champion est dans le pool.
- Indisponibles : à 40 %, en niveaux de gris et barrés, avec la raison (banni / allié / adverse / intention alliée / ton intention).
- Barre basse : sélection, détail, « Double-clic pour … », « Fermer » et l'action. Échap ferme.

**Verrouillage**
- Sceau apposé (voir Motion).
- La rangée basse devient la **sélection de skin**. Cartes de 104 × 188 : art de chargement, nom en bas, cadenas et niveaux de gris si le skin n'est pas possédé, losange or si sélectionné.
- Le splash du skin choisi s'affiche en fond (opacité 0.24, masque radial).
- Titre « Skin · nom », sous-titre « n skins possédés sur m ».

**Colonne loadout**
- **Carte de page de runes**, teintée par l'arbre principal (dégradé vers l'arbre secondaire) :
  - rune majeure de 72 px, 3 runes de 44 px ;
  - arbre secondaire, 2 runes de 36 px ;
  - fragments ;
  - « Modifier › ».
- **Sorts d'invocateur :** 2 tuiles (D et F), popover de 9 sorts, « Échanger D ⇄ F ». Choisir un sort déjà pris échange les deux.
- **Objets :** lecture seule.
- **Pied de colonne :** note d'état, « Envoyer au client », « Rétablir OneTricks » si la page est modifiée. Pastille « Modifiée à la main ».

**Grimoire de runes** (overlay)
- Arbre principal, rune majeure, 3 rangées.
- Arbre secondaire : 2 runes de rangées différentes ; choisir une troisième rangée remplace la plus ancienne.
- Fragments : 3 rangées.
- « Annuler » ou « Appliquer la page ». L'overlay s'ouvre par un clip-path circulaire, puis les runes éclosent en cascade.

### File trouvée (overlay de la coque)
- Fond radial sombre, pilier de lumière (menthe et magenta), halo.
- Cercle de 720 px : anneau runique (60 s), pentacle menthe et pentacle inversé magenta (−90 s).
- Anneau du compte à rebours : 10 s.
- Titre « Partie trouvée », sous-titre « n s pour répondre ».
- Boutons « Accepter » (menthe) et « Refuser ».
- Auto-accept à 4 s (Live Coach). Après acceptation : « Acceptée », puis effondrement en tournoyant vers la draft.

### Post-game (`Post-game.dc.html`)
- **Sceau de victoire** de 104 px (menthe), titre « Victoire » en 64 px, contexte (champion, matchup, durée, file).
- **Axes :** pastilles tenu / non tenu. **LP :** gain en dégradé or → menthe (compteur).
- **Courbe de win chance :** 1124 × 430, tracée à l'encre, dégradé bleu → violet → menthe → or.
  - Marqueurs d'événements colorés par type : Baron violet, tour or, dragon orange, larves violet, héraut bleu, kill menthe, mort rose.
- **Les plus coûteux / les plus rentables :** 3 lignes chacun.
- **Colonne :** impact par événement (ΔP de l'équipe, barres divergentes, « toi » pour les miens), impact attribué et résidu, écarts à la norme et à l'objectif.

## Motion (`motion.js`)
`motion.js` est déjà en JS vanilla, sans dépendance. Il peut être **repris presque tel quel** dans `static/motion.js` (API `window.Motion`), en gardant les attributs `data-*` comme contrat avec les gabarits.

### Primitives
| Primitive | Effet |
|---|---|
| `data-trace="ms"` | Tracé SVG par `stroke-dashoffset`, avec une plume d'étincelles qui suit la pointe |
| `data-rise` | Entrée : `perspective(900px) translateY(34px) rotateX(38deg) scale(.96)` → neutre, 900 ms |
| `data-pop` | Apparition `scale(.2) rotate(-70deg)` → 1.14 → 1, 760 ms, puis petite gerbe d'étincelles |
| `data-fade` | Fondu d'opacité |
| `data-spell` | Chaque lettre passe par des runes avant de se fixer |
| `data-count` | Compteur qui roule, 1300 ms |
| `data-spin="s"` | Rotation infinie (valeur négative = sens inverse) |
| `data-glow` | Pulsation d'opacité |
| `data-tilt` | Inclinaison 3D au survol (±10–12°) |

Toutes les primitives acceptent `data-delay`.

### Courbes
| Nom | Courbe |
|---|---|
| Standard | `cubic-bezier(.65,0,.35,1)` |
| Entrée | `(.22,1,.36,1)` |
| Ressort | `(.2,.8,.2,1)` |
| Sceau | `(.3,0,.2,1)` |

### Particules
- Un seul `<canvas>` fixe, en `pointer-events: none`, composité en `lighter`.
- Étincelles, braises montantes en continu (0,35 par image), anneaux de choc, runes projetées ou en spirale (`converge`).
- Plafond de 1600 particules.

### Moments signature
1. **Transition de page :**
   - le contenu s'assombrit (560 ms) pendant qu'un cercle runique de 520 px se trace et que 44 runes convergent ;
   - le cercle implose (860 ms) ;
   - puis explosion, éclair cuivre, secousse (8 px) et ouverture par `clip-path: circle()` de 0 à 75 % (820 ms).
2. **Partie trouvée :** convergence de 90 runes (1,5 s), pilier, puis impact menthe/magenta et explosion.
   - À l'acceptation : impact, grosse explosion, éclair blanc, secousse de 16 px, les anneaux accélèrent (×9) ;
   - puis effondrement `scale(.2) rotate(160deg)` (560 ms).
3. **Sceau apposé** (verrouillage, victoire) :
   - tampon `scale(3.4) rotate(-40deg)` → 1 (680 ms) ;
   - impact frame, explosion de 170 étincelles et 24 runes, ondes de choc, secousse.
4. **Ban :** tampon et explosion magenta, puis révélation en cascade.
5. **Survol d'un pick :** éclosion du portrait et convergence de 26 runes.
6. **Courbes** de win chance et de rang tracées à l'encre.

### Impact frame (version adoucie, validée)
- **Une seule image (~50 ms) :** voile de la couleur complémentaire en `soft-light` (0.55) et quelques lignes de vitesse fines. Les particules se figent ~50 ms.
- **Après l'image :** léger décalage des couleurs sur les bords (240 ms).
- **Pas** de négatif, **pas** de fond noir, **pas** d'arrêt des autres animations.
- Réservée aux grands moments : partie trouvée, acceptation, verrouillage, victoire.

### Paires complémentaires
- Cuivre ↔ violet, or ↔ bleu, menthe ↔ magenta.
- Chaque explosion mêle sa couleur et sa complémentaire.

### Accessibilité et performance (SPEC-21)
- Réglage Motion : **Système** suit `prefers-reduced-motion`. **Réduit** coupe tout : intros, particules, braises, secousses, transitions (le changement d'écran devient instantané).
- La vitesse globale est un multiplicateur (prop `speed`).
- Budget de 16,7 ms par image, à mesurer sur le banc `/_motion`. Leviers si besoin : plafond de particules, débit des braises, plume de tracé, désactiver le `drop-shadow` animé sur la cible.

## État (par écran)
**Coque**
- `route` (accueil | rang | progression | draft | postgame), persistée.
- `motion` (systeme | complet | reduit).
- `queue` (idle | searching | found | draft), `qSec`, `accept` (compte à rebours), `accepted`.

**Draft**
- **Bans et picks :** `phase` (ban | pick), `banHover`, `myBan`, `hover`, `locked`, `shown` (win chance animée).
- **Grimoire des champions :** `grid`, `q`, `role`, `poolOnly`.
- **Loadout :**
  - `page` : `{ p, k, r[3], s, sub[[row, i] × 2], sh[3] }` ;
  - `edit`, la copie de travail de `page` dans l'éditeur ;
  - `spells[2]`, `picker`, `modified`, `pushed`.
- **Skins :** `skins[champId]` (cache), `skin`.

**Accueil :** `goals[]` (actif ou libre).

**Progression :** `role`.

**Recommandation de découpage htmx :** un fragment par zone de draft (bans, sceaux et balance, rangée basse, loadout), rafraîchi sur les événements LCU (WebSocket ou SSE) plutôt que par écran entier. Les animations se rejouent sur `htmx:afterSwap` via `Motion.intro(fragment)`.

## Données
| Besoin | Source |
|---|---|
| Recommandations de pick, profondeur, « suite attendue » | `src/draft/recommendations.py` |
| Bans conseillés | `src/analysis/ban_recommendations.py` |
| Win chance en draft et en partie, impact par événement | `src/winprob/…`, dont `impact.py` |
| Page OneTricks et import au lock-in | `src/draft/loadout.py` (SPEC-15, ADR-003) ; la modification manuelle doit **primer** sur l'import automatique |
| Grille, normes, objectifs | `src/coaching/grid.py`, `metrics.py` |
| Axes | `src/coaching/goals.py` |
| Photos de rang | captures de rang en base |
| Champ select, bans, picks, skins possédés, envoi des runes / sorts / skin | API LCU |

Pour les bans, picks et skins possédés : endpoints `lol-champ-select` et `lol-champions` (inventaire des skins).
Dans le prototype, la possession des skins est **simulée** (environ 2 sur 3).

## Assets
Data Dragon, version **14.24.1** dans le prototype ; à rendre configurable et mettre en cache localement.

| Asset | Chemin |
|---|---|
| Portraits | `cdn/{v}/img/champion/{Id}.png` |
| Runes et fragments | `cdn/img/perk-images/Styles/…`, `StatMods/…` |
| Sorts | `cdn/{v}/img/spell/Summoner*.png` |
| Objets | `cdn/{v}/img/item/{id}.png` |
| Skins (liste FR) | `cdn/{v}/data/fr_FR/champion/{Id}.json` |
| Skins (illustrations) | `cdn/img/champion/loading/{Id}_{num}.jpg` et `…/splash/{Id}_{num}.jpg` |

- Quelques chemins de runes ont été écrits à la main : à valider contre `runesReforged.json`.
- Polices : Cormorant Garamond, Alegreya Sans, Noto Sans Runic (Google Fonts). À embarquer localement pour le mode hors ligne.
- Aucune autre image : tous les ornements sont en SVG inline.

## Fichiers
| Fichier | Contenu |
|---|---|
| `Client Alchimie.dc.html` | Coque, navigation, transition de page, file trouvée ; monte les écrans ci-dessous |
| `Accueil.dc.html` | Écran Accueil |
| `Rang.dc.html` | Écran Rang |
| `Progression.dc.html` | Écran Progression |
| `Draft.dc.html` | Écran Draft |
| `Post-game.dc.html` | Écran Post-game |
| `motion.js` | Primitives de motion et particules (réutilisable) |
| `Draft Directions.dc.html` | Exploration initiale : 3 directions de draft (1a cercle, 1b parchemin, 1c alchimie — retenue) |
| `support.js` | Moteur de prototype, pour l'ouverture des fichiers seulement ; **ne pas porter** |

Dans chaque `.dc.html`, la logique (données de démo, calculs, déclencheurs d'animation) est dans le `<script data-dc-script>` en bas du fichier.

## Ordre d'implémentation conseillé
1. Jetons, polices et coque (barre de titre, navigation, réglage Motion) dans `base.html` et `style.css`.
2. `static/motion.js` et le banc `/_motion` (mesure de la durée par image).
3. Draft : sceaux et balance, recommandations, bans, grimoire des champions, loadout, éditeur de runes, skins.
4. File trouvée, puis transition de page.
5. Post-game, Accueil, Rang, Progression.
