# SPEC-14 — La draft finale se lit en face-à-face, lane par lane

**Statut** : ✅ **Implémentée** le 2026-09-23 — format validé par @pj35 le 2026-09-23.
Écart assumé : « Données insuffisantes » s'affiche « peu de données » (21 caractères ne tiennent
pas dans les 17 des trois colonnes, critère §5.6).

**Origine** : @pj35 — « J'aimerais que le coach m'affiche la draft finale dans le bon ordre des
lanes (Top > Jungle > Mid > ADC > Supp) », puis : un tableau head-to-head, une flèche qui indique
l'avantage dans le matchup direct, avec sa valeur, et les scores matchup/synergie en miroir.

**Effort** : ~0,5 jour, tests compris. Un seul fichier de production touché en substance.

---

## 1. Constat

`src/draft/final_analysis.py` (`FinalDraftAnalyzer.analyze`) affiche aujourd'hui :

- une ligne `COMPOSITION FINALE` par équipe, dans **l'ordre des picks** (`state.ally_picks`) ;
- deux tableaux séparés (`VOTRE ÉQUIPE`, `ÉQUIPE ENNEMIE`), **triés par score total décroissant**
  (`_score_team`, l.90).

Le joueur doit donc reconstituer lui-même qui affronte qui. Le **duel direct** (mon top contre leur
top) n'est affiché nulle part, alors que le modèle le calcule déjà :
`evaluator.matchup_logit((allié, lane), (ennemi, lane))` (`src/analysis/game_eval.py:114`), qui est
antisymétrique, si bien qu'une seule valeur suffit pour orienter la flèche.

Aucune donnée nouvelle n'est nécessaire :
- l'ordre des lanes existe déjà : `scraping_config.LANES = ("top", "jungle", "middle", "bottom", "support")` ;
- la lane de chaque champion est connue : `ally_lanes` (= `state.inferred_roles`, les deux équipes
  fusionnées).

## 2. Cible

Un seul tableau miroir remplace les deux tableaux et les lignes `COMPOSITION FINALE`. Il ne comporte
**pas de colonne lane** : c'est l'ordre des lignes qui l'indique. Il tient en 80 colonnes et utilise
**uniquement de l'ASCII** (la console cp1252 interdit ◄ ►, cf. règle 6 de `README.md`).

```
 Mat   Syn   Tot  Allié              DUEL      Ennemi           Tot   Syn   Mat
----- ----- ----- -------------- ------------ -------------- ----- ----- -----
+2.1  +0.8  +2.9  Garen          <<<  +3.4    Darius          -1.2  +0.4  -1.6
-0.4  +1.2  +0.8  Vi              >   -1.3    Lee Sin         +0.3  -0.2  +0.5
+0.1  +0.5  +0.6  Ahri            =   +0.2    Syndra          +0.2  +0.1  +0.1
-1.8  +0.9  -0.9  Jinx            >>  -2.5    Draven          +1.9  +0.6  +1.3
 données insuffisantes  Rell      ?           Nautilus        +0.4  +0.9  -0.5

  DUEL : matchup direct, en points de winrate de votre point de vue (+ = avantage pour vous)
```

Puis le bloc `COMPARAISON DU DRAFT` (probabilité, évaluation), **inchangé**.

### 2.1 Ordre des lignes

- Une ligne par lane, dans l'ordre de `scraping_config.LANES`. Ne **pas** dupliquer cet ordre dans
  une nouvelle constante.
- L'allié et l'ennemi d'une ligne sont les champions dont la lane inférée est celle de la ligne.
- **Lane ambiguë** : si une lane est inconnue (`None`), ou si deux champions d'une même équipe
  partagent une lane, ils sont placés **en fin de tableau**, sans appariement, avec `?` en DUEL.
  Mieux vaut un appariement absent qu'un appariement faux.

### 2.2 Colonne DUEL

- Valeur : `_to_points(evaluator.matchup_logit(allié, ennemi))`, soit la même échelle que les
  colonnes Mat/Syn/Tot. Elle est affichée avec son signe, sur une décimale, **toujours à côté de la
  flèche**, pour que le joueur n'ait pas à mémoriser les seuils.
- **La flèche pointe vers le gagnant** : `<` pour un avantage allié, `>` pour un avantage ennemi.
  Le nombre de chevrons suit |valeur| :

  | \|valeur\| (pts) | affichage |
  |---|---|
  | < 1,0 | `=` |
  | 1,0 – 2,0 | `<` / `>` |
  | 2,0 – 3,0 | `<<` / `>>` |
  | ≥ 3,0 | `<<<` / `>>>` |

  Ces seuils vont dans `src/config_constants.py` (`draft_config`), avec un commentaire indiquant
  qu'ils reprennent les paliers des marqueurs `[+]`/`[++]` existants (1,0 et 2,0), plus un palier
  à 3,0.
- **`?` sans valeur** lorsque le matchup direct n'a **aucune donnée**. Aujourd'hui,
  `matchup_logit` renvoie `0.0` aussi bien pour « égalité mesurée » que pour « rien de mesuré » ;
  afficher `= +0.0` dans le second cas serait un mensonge (esprit de SPEC-09). Il faut ajouter une
  méthode publique `GameEvaluator.has_matchup_data(champion, enemy) -> bool`, qui répond vrai si
  l'une des deux tables (`forward` ou `reverse`) contient la paire. `final_analysis.py` ne doit pas
  lire `_matchup_table` directement.
- `?` également pour les lignes non appariées (§2.1).

### 2.3 Colonnes Mat / Syn / Tot

- Mêmes valeurs qu'aujourd'hui (`_score_team`), avec les mêmes définitions : Mat = somme des
  matchups contre toute l'équipe adverse, Syn = paires de ce champion avec ses alliés.
- **En miroir** : côté allié `Mat Syn Tot Nom`, côté ennemi `Nom Tot Syn Mat`.
- Les marqueurs `[++]`/`[--]` **disparaissent** du tableau, faute de place en 80 colonnes.
  `_marker()` devient inutilisée : la supprimer si plus rien ne l'appelle.
- `Données insuffisantes` (SPEC-06 E7) occupe la place des trois colonnes du champion concerné.
- Le tri par score de `_score_team` (l.90) est supprimé : `_score_team` renvoie les lignes dans
  l'ordre reçu, et c'est l'appelant qui ordonne par lane.

## 3. Hors périmètre

- Le calcul des scores, `team_logit`, la probabilité de victoire et la prédiction enregistrée pour
  la calibration : **aucun changement**. C'est un pur changement d'affichage, et la prédiction
  journalisée doit rester strictement identique.
- La correction de l'inférence de lane (`state_parser.py`) : si une lane est mal inférée, le
  tableau le montrera (appariement étrange ou ligne `?`), et il ne la masquera pas.
- Les affichages en cours de draft (`src/draft/display.py`).

## 4. Fichiers touchés

| Fichier | Changement |
|---|---|
| `src/draft/final_analysis.py` | Tableau miroir, ordre par lane, colonne DUEL, suppression des deux tableaux, de `COMPOSITION FINALE` et du tri par score |
| `src/analysis/game_eval.py` | `has_matchup_data()` publique |
| `src/config_constants.py` | Seuils des chevrons (`draft_config`) |
| `tests/test_final_analysis.py` (ou existant équivalent) | Voir §5 |

`final_analysis.py` fait 211 lignes : il reste largement sous la limite de 500.

## 5. Critères d'acceptation (tests)

Hermétiques, avec un évaluateur factice ; aucun accès à `data/db.db`.

1. **Ordre** : des picks fournis dans le désordre (support, top, adc, jungle, mid) sont affichés
   top → jungle → mid → adc → support.
2. **Flèche et valeur** : +3,4 donne `<<<  +3.4`, -1,3 donne `>   -1.3` et +0,2 donne
   `=   +0.2`. Tester chaque palier dans les deux sens, ainsi que ses bornes (0,99 / 1,0 / 2,0 / 3,0).
3. **Absence de donnée** : si `has_matchup_data` est faux, DUEL affiche `?` sans valeur (et non `=`).
4. **Lane ambiguë** : deux alliés en `middle` ou une lane `None` donnent des lignes en fin de
   tableau, avec `?` en DUEL, et aucun appariement inventé.
5. **Données insuffisantes** : le champion concerné garde sa ligne et son duel.
6. **Largeur** : aucune ligne du tableau ne dépasse 80 caractères, noms de 14 caractères compris.
7. **Non-régression calibration** : `insert_prediction` reçoit exactement les mêmes arguments
   qu'avant le changement.
8. **ASCII** : la sortie s'encode en cp1252 sans erreur.
