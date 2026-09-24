# SPEC-16 — Moteur d'optimisation des builds

**Statut** : ⏸️ **Reportée, non planifiée** (2026-09-24, [ADR-003](../adr/ADR-003-onetricks-temps-reel.md)).
L'import de SPEC-15 prend la build la plus jouée sur OneTricks, sans moteur. Phase A : bloquée
par les CGU de Coachless (spike du 2026-09-24, SPEC-15 §2.1.1). Les données existent, mais il
faut l'autorisation écrite de Coachless pour y accéder hors du site. Phase A+ :
**abandonnée**, faute de collecte par patch (la table `build_snapshots` n'est plus prévue).

**Origine** : @pj35, 2026-09-23. Méthode arrêtée en discussion, cf.
[ADR-002](../adr/ADR-002-moteur-optimisation-builds.md). Remplace la phase 2 de
[SPEC-15](SPEC-15-import-runes-items.md).

**Dépend de** : SPEC-15 phase 0 (données accessibles) et phase 1 (tuyauterie LCU et table
`build_snapshots`).

**Effort** : A ~3 jours · A+ non estimé.

---

## 1. Principe

Le moteur ne cherche pas la meilleure build dans l'absolu. Il **classe un petit ensemble de
candidats réalistes** selon une note dont chaque poids est **mesuré** : jamais une constante
réglée à la main, jamais une partie personnelle de @pj35.

## 2. Phase A — Shrinkage hiérarchique

### 2.1 Candidats

Les N builds les plus jouées par les one-tricks sur (champion, lane), via OneTricks, ou via
LoLalytics si le spike montre OneTricks inaccessible. N est à fixer dans `config_constants.py`,
avec une valeur de départ de 10 à justifier par la couverture : part des parties couvertes par
les N premières.

Ce choix a deux intérêts :
- il exclut les builds absurdes qu'un WPA bruité pourrait porter en tête ;
- il réduit l'espace à quelques dizaines de candidats, ce qui rend l'optimisation triviale (un
  classement), sans solveur ni recherche combinatoire.

### 2.2 Note d'un candidat

```
note(b | champion, lane, adversaire) =
      wpa_shrunk(b | champion, lane)
    + diff_shrunk(b | adversaire)
```

- **`wpa_shrunk`** : WPA Coachless de chaque composant (keystone, runes, items du core), rétréci
  vers 0 par `confidence(games, K_wpa)`, puis sommé sur les composants. L'hypothèse d'additivité
  est **assumée et nommée** : elle ignore les interactions entre items. C'est à documenter comme
  plafond connu, avec un commentaire `ponytail:`.
- **`diff_shrunk`** : différentiel de matchup, `winrate(b vs adversaire) − winrate(b global)`,
  rétréci vers 0 par `confidence(games_vs, K_diff)`. Le biais de sélection commun aux deux termes
  s'annule en partie ; le reste est corrigé en A+.
- Si l'adversaire est inconnu (import au lock-in avant le pick ennemi), `diff_shrunk = 0` : on
  recommande pour la lane. La réimportation à la révélation du laner adverse relève de SPEC-15
  §3.2, à étendre.

### 2.3 Mesure des K

Même méthode que SPEC-13 (`src/analysis/shrink.py`, MLE à 1 paramètre, `K = C / var_signal`), à
une différence près : **le WPA n'est pas un winrate binomial**, donc son `C` ne vaut pas ~2500.
Deux possibilités, à trancher selon ce que le spike révèle :
- Coachless publie un intervalle ou une erreur-type par WPA : `C` s'en déduit directement ;
- sinon, `C` est estimé par la régression de `mean(d²)` sur `1/n`, comme SPEC-13 l'a fait pour
  valider le `C` binomial.

Les K sont recalculés à chaque collecte et stockés dans `db_meta`, comme les K de SPEC-13.

### 2.4 Validation de A

Sans vérité terrain, on se donne un critère **falsifiable** :
- **Stabilité sur les témoins** : pour les (champion, lane) dont ni le champion ni aucun item des
  candidats n'a changé entre deux patchs (diff Data Dragon), le candidat classé premier ne doit
  pas changer plus souvent que ne le prédit le bruit mesuré.
- **Cohérence de signe** : le candidat classé premier a un WPA et un différentiel de même signe
  dans la majorité des cas ; un désaccord systématique signale un biais non corrigé.

Ce n'est pas une preuve qu'on bat Coachless. C'est une mesure qui peut échouer.

## 3. Phase A+ — Correction par les patchs (bloquée)

**Débloquée à** ~8 transitions de patch dans `build_snapshots`, soit 4 mois de collecte à partir
de la mise en service de SPEC-15 phase 1.

### 3.1 Changements par patch

Pour chaque transition N → N+1, un diff de `item.json`, `runesReforged.json` et `champion.json`
Data Dragon (`https://ddragon.leagueoflegends.com/cdn/<version>/data/...`, gratuit et sans limite
de débit). Chaque item, rune et champion est classé **modifié** ou **inchangé**. Seul le fait
d'avoir changé est retenu, pas le sens : un changement de stats n'est pas toujours clairement un
buff.

### 3.2 Trois mesures

1. **Bruit des témoins** : variation inter-patch des estimations sur les paires (champion, item)
   dont ni l'un ni l'autre n'a changé. Elle mesure le bruit *réel* de chaque source, à comparer au
   bruit théorique utilisé pour les K de A.
2. **Réactivité aux changements** (différence de différences) : écart de variation entre items
   modifiés et témoins. Une source qui ne réagit pas aux vrais changements, ou qui réagit
   autant sur les témoins, est pondérée à la baisse.
3. **Biais de sélection** : sur les témoins, la corrélation entre la variation de popularité et
   la variation de winrate. À stats constantes, elle mesure le biais de sélection du winrate, et
   permet de **corriger** `diff_shrunk` au lieu de seulement l'atténuer.

### 3.3 Confusion à contrôler

Un item inchangé peut bouger parce que les champions qui l'achètent ont changé : les paires
(champion modifié, item) sortent des témoins. Les autres facteurs de méta (items voisins modifiés,
etc.) restent un plafond connu de la méthode.

## 4. Hors périmètre

- **Méta-modèle sur parties brutes** (Riot match-v5) : écarté par ADR-002 tant que A+ n'a pas
  montré ses limites.
- **Parties personnelles de @pj35** : exclues du calcul comme de la validation.
- **Ordre de montée des sorts, ordre d'achat fin** : seul le core (items complets) est noté.

## 5. Fichiers pressentis

| Fichier | Rôle |
|---|---|
| `src/analysis/build_engine.py` (nouveau) | Candidats, note, classement (phase A) |
| `src/analysis/shrink.py` | Réutilisé ; extension pour un `C` non binomial si nécessaire |
| `src/analysis/patch_diff.py` (nouveau, phase A+) | Diff Data Dragon et classement modifié/inchangé |
| `src/draft/loadout.py` (SPEC-15) | Appelle `build_engine` au lieu d'importer la build Coachless brute |
| `scripts/validate_build_engine.py` (nouveau) | Mesures §2.4 puis §3.2 : c'est le rapport, sur le modèle de `scripts/calibrate_model.py` |
