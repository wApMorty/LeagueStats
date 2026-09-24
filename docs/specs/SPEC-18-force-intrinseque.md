# SPEC-18 — La force d'un champion, c'est son winrate de lane, pas `avg_delta2`

**Statut** : 🟢 Phase A **implémentée le 2026-09-24**. Phase B **reportée**, à rouvrir sur mesure
(approche C, choisie par @pj35 le 2026-09-24).

**Origine** : la tâche reportée « shrink de `avg_delta2` dans la tier list » (SPEC-17 §7,
Kassadin 1er en top). Mesurée avant d'écrire la spec, elle ne tenait pas : il n'y a rien à
rétrécir.

---

## 1. Constats (base de production, 2026-09-24)

### 1.1 `avg_delta2` ne mesure rien au niveau du champion

Le `delta2` de LoLalytics est un écart à la moyenne du champion. Sa moyenne sur tous les
adversaires est donc nulle par construction, et ce qu'il en reste est du bruit
d'échantillonnage :

- l'estimateur de SPEC-13 (MLE, `shrink.estimate_signal_variance`) trouve une variance de
  signal **nulle** sur les 5 lanes ;
- sur les champions à plus de 20 000 parties, `mean(z²)` vaut 0,43 à 0,74, où 1 serait du bruit
  pur.

Un lissage ramènerait tout le monde à 0. Deux écrans triaient pourtant sur cette valeur :

- la **composante performance de la tier list** blind pick (`TierListGenerator.generate_tier_list`) :
  Kassadin 1er en top sur 606 parties, Karthus 1er en mid sur 174 ;
- le **survol du meilleur blind pick** (`HoverAutomation`), à chaque draft : `score_against_team`
  sans adversaire revient à `avg_delta2`.

### 1.2 Le signal qui existe : le winrate de lane

Écart à la moyenne de la lane, même MLE, même modèle de bruit binomial :

| lane | écart-type du signal (pp) | K mesuré (games) |
|---|---:|---:|
| top | 1,72 | 838 |
| jungle | 1,66 | 909 |
| middle | 2,06 | 584 |
| bottom | 1,75 | 811 |
| support | 2,04 | 600 |

C'est plus que le signal propre des matchups (~1,1 pp, SPEC-13). **Attention au centre** : les
winrates LoLalytics sont en moyenne à **52,4 %** sur chaque lane, pas 50 %. Centrer sur 50
gonfle l'écart-type mesuré à ~3 pp : c'est l'erreur faite dans la première analyse.

Réserve : ce winrate inclut un biais de sélection (les champions peu joués sont souvent entre les
mains de spécialistes). Le lissage l'atténue sans l'éliminer.

### 1.3 Le modèle de prédiction ignore ce signal

SPEC-05 §3.3 spécifiait un terme de force intrinsèque, `Σ (winrate_base − 50)`. `GameEvaluator`
ne l'a jamais implémenté : il ne somme que des paires (matchups et synergies).

## 2. Phase A — implémentée

- `MatchupsRepository.get_lane_winrates(lane)` : winrate pondéré par les games et nombre de
  games, par champion (`lane=None` agrège toutes les lanes).
- `shrink.shrunk_lane_winrates(db, lane)` : winrate rétréci vers la moyenne de la lane,
  `moyenne + (wr − moyenne) · confidence(games, K)`, avec K estimé à chaque appel par
  `estimate_shrink_k` (quelques dizaines de champions : instantané, pas de clé `db_meta`).
- Tier list blind pick : la performance est ce winrate (affiché « Winrate lissé »). La stabilité
  et la couverture ne changent pas.
- Survol du blind pick : classé sur ce winrate, `score_against_team` n'y est plus appelé.

**Hors périmètre** : le modèle de prédiction ne change pas (pas de bump de `MODEL_VERSION`, le
compteur de calibration continue). La colonne `champion_scores.avg_delta2` reste calculée mais
n'est plus lue par la tier list. La stabilité et la couverture (dérivées de `delta2`) n'ont pas été
mesurées.

## 3. Phase B — reportée, décidée sur mesure

Ajouter le terme de SPEC-05 §3.3 à `GameEvaluator`. Coût : bump de `MODEL_VERSION`, donc
compteur de calibration remis à 0 et pondération par lane restante désactivée jusqu'à 30 parties.

**Critère de réouverture** : `scripts/compare_intrinsic_strength.py` rejoue les parties
labellisées (compositions stockées dans `predictions`) avec et sans le terme, et donne le gain
d'AUC avec un intervalle bootstrap à 90 %. On rouvre quand la borne basse dépasse 0.

État au 2026-09-24, 72 parties : AUC 0,560 → 0,579, gain +0,019, IC 90 % [−0,053 ; +0,090].
Les données ne tranchent pas. Détecter un gain de cet ordre demandera plusieurs centaines de
parties.
