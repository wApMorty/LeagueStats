# SPEC-22 — Attribution complète de l'impact (objectifs perdus, niveaux, respawn)

**Statut** : 🟡 **Rédigée le 2026-10-04**, périmètre, règle des objectifs perdus et modèle unique
validés par @pj35 (§2). Trois conventions restent « à valider » (§2).

**Origine** : @pj35, 2026-10-04, sur le rapport de fin de partie : « Non attribué (temps, farm,
niveaux) : −20 pts pour ton équipe ; vision, placement et gestion de vague ne sont pas mesurés. Il
faudrait compléter le modèle. »

**Effort** : ~2 jours, 5 tâches, 16 pts (§5).

---

## 1. Constat

Mesuré le 2026-10-04 sur les 45 parties du joueur qui ont une timeline (`data/db.db`,
`game_records`), modèle `wp-361f2990` (patch 16.19, 7 782 parties), `impacts()` tel quel :

| Résidu de l'équipe du joueur (`teams[…]["unattributed"]`) | Moyenne | Moyenne en valeur absolue |
|---|---|---|
| **Objectifs pris par l'adversaire** (tours, inhibiteurs, drakes, Nashor, Héraut, larves) | **−22,9 pts** | 22,9 |
| Dérive entre deux événements (respawn, niveaux, compteurs × temps) | +2,2 pts | 17,6 |
| **Résidu affiché** | **−20,3 pts** | 25,1 |

- Le « −20 pts » **n'est pas du temps, du farm ni des niveaux** : c'est un biais de construction.
  `impacts()` crédite l'équipe qui marque un objectif (`src/winprob/impact.py:97-108`) mais ne débite
  personne dans l'équipe qui le perd. Les objectifs pris par l'équipe du joueur lui rapportent
  +24,8 pts, ceux qu'elle perd ne lui coûtent rien : l'impact cumulé du joueur est **biaisé vers
  le haut** de la même quantité (attribué +26,5 pts en moyenne contre une variation totale de +6,2).
- Une fois ces pertes débitées, la dérive pèse ±17,6 pts en valeur absolue mais elle se compense
  (+2,2 en moyenne) : grands flux de signes opposés, dominés par la récupération après respawn
  (`dead_s`) et les niveaux (`level`). Attribués aux joueurs (§4.2 et §4.3), il reste **−1,5 pt en
  moyenne, 10,3 en valeur absolue** (maximum 39,6) : compteurs × temps (9,4) et expiration du
  buff de Nashor ou d'Ancien (1,8). Prototype jetable, non versionné.
- Le libellé du rapport (`src/winprob/report.py:93`) est faux sur un point : le **CS n'est pas dans le
  modèle** (`INPUTS` exclut `cs`, `src/winprob/model.py:20`, spike du 2026-10-02) ; « farm » n'y
  entre que par les niveaux (l'XP).
- **Vision, placement, gestion de vague** : la timeline LCU ne porte que `CHAMPION_KILL`,
  `BUILDING_KILL` et `ELITE_MONSTER_KILL`, aucun événement de ward (SPEC-19 §3.4, confirmé sur une
  timeline de 23 images), et les positions sont échantillonnées une fois par minute. Les totaux
  de vision n'existent qu'en **fin de partie** (`visionScore`, `wardsPlaced`).
  Test (3 609 parties du patch 16.19 de plus de 20 min, image à 15 min, validation croisée à 5
  blocs, Brier) : modèle actuel 0,1824 ; avec l'or et l'XP 0,1774 ; avec le CS 0,1805 ; avec la
  vision de fin de partie par minute 0,1709 ; avec tout 0,1673. Le gain de la vision est
  **probablement une fuite** (des totaux de fin de partie résument la partie, pas son état à 15 min).

## 2. Objectif et arbitrages

Faire que l'impact du joueur soit **symétrique** (les objectifs perdus coûtent, les niveaux et le
respawn sont attribués) et que le résidu affiché ne contienne plus que ce qui n'est pas
attribuable à un joueur : la valeur d'une avance qui évolue avec l'horloge.

| Sujet | Décision |
|---|---|
| Périmètre | **Validé (@pj35, 2026-10-04)** : attribution complète (objectifs perdus, respawn, niveaux) **et** niveaux/XP face à l'adversaire de lane. Placement (position des morts) et vision : hors périmètre (§7). |
| Objectifs perdus | **Validé (@pj35, 2026-10-04)** : la perte va aux coéquipiers **absents** du lieu (même rayon et même position à l'image la plus proche que les présents, `WINPROB_PRESENCE_RADIUS`). **À valider** : si les cinq étaient présents, partage à parts égales entre les cinq. |
| Modèle | **Validé (@pj35, 2026-10-04)** : un seul modèle, celui de SPEC-20, inchangé. Pas de second modèle post-partie avec l'or et le CS (−0,002 de Brier sur tout le jeu, SPEC-20 §4.3 bis) : le CS et l'or restent dans la grille de SPEC-19. |
| Niveaux | **À valider** : l'impact des niveaux est zero-sum face à l'adversaire de lane (`participant_roles()` de SPEC-19) ; si un des dix postes est inconnu, **tous** les joueurs se comparent à la moyenne des cinq adversaires (la somme reste exacte). |
| Respawn | **À valider** : la récupération après une mort (la mort coûte moins cher qu'à l'instant où elle survient) revient à la victime ; l'avance qui s'évapore débite le tueur et les assistants de cette mort, à parts égales. Sans tueur (exécution, sbire), la part reste au résidu. |
| Recalcul | **À valider** : les impacts des 45 parties déjà rangées (11 086 lignes) sont recalculés une fois avec le modèle courant (les anciens modèles ne sont pas conservés) ; la convention d'attribution est versionnée dans `model_version` (§4.4). |

## 3. Approches considérées

| Approche | Pour | Contre |
|---|---|---|
| A. Seulement symétriser (objectifs perdus) | 3 pts, supprime l'essentiel du biais | La dérive (±17,6 pts) reste un bloc opaque, « farm » toujours faux |
| **B. Symétriser + décomposer la dérive par joueur (retenue)** | Résidu −20 → ~−1,5 pt en moyenne ; le modèle de SPEC-20 reste unique ; décomposition exacte car le modèle est linéaire en logit sur des sommes par joueur | Conventions d'attribution à documenter (respawn, duel) |
| C. B + second modèle avec l'or et le CS | Farm exact | Deux modèles à versionner et calibrer, impact du rapport et de l'overlay qui divergent, gain de 0,002 de Brier : écartée par @pj35 |

## 4. Détail

### 4.1 Objectifs perdus (`src/winprob/impact.py`)

Pour chaque `BUILDING_KILL` et `ELITE_MONSTER_KILL` suivi, l'équipe **adverse** de `scoring_team()`
porte la perte : `event_type = "lost_" + kind` (`lost_tower`, `lost_inhibitor`, `lost_dragon`,
`lost_elder`, `lost_baron`, `lost_herald`, `lost_grubs`), `delta_p` négatif (du point de vue de
cette équipe), réparti à parts égales entre ses joueurs **absents** (`_present()` complémentaire).
Aucun absent : les cinq. Un kill n'a pas de perte à répartir (la victime porte déjà la sienne).
Invariant : somme des lignes `lost_<k>` d'un événement = −(somme des lignes `<k>` du même événement).

### 4.2 Niveaux face à l'adversaire de lane

`WinModel.logit_parts(a, b) -> Dict[str, float]` (`src/winprob/model.py`) : contribution de chaque
variable d'entrée au changement de logit entre deux états, produit direct et produit avec le temps
réunis ; la somme égale la différence de logit. `state.py` gagne un générateur de segments
(état après un événement → état avant le suivant) qui expose aussi, **par joueur**, `level`,
`dead` et `dead_s` aux deux instants. Ces trois variables sont des sommes par joueur : la
contribution de chaque joueur se calcule exactement avec les mêmes poids (pas de répartition
approchée), puis se convertit en probabilité par le rapport ΔP / Δlogit du segment.

Une ligne `event_type = "levels"` par joueur et par partie (`event_time_ms` = dernière image) :
contribution de ses niveaux moins celle des niveaux de son adversaire de lane. Les deux
adversaires de lane portent des lignes opposées. Tous les postes connus et distincts → appariement
par poste ; sinon repli sur la moyenne des cinq adversaires (`participant_roles(game, eog)`,
`src/coaching/metrics.py`). `impacts()` reçoit `roles: Optional[dict]`.

### 4.3 Respawn

Une ligne `event_type = "respawn"` par joueur et par partie : pour une victime, la contribution
de ses `dead` et `dead_s` pendant la période de réapparition (positive, c'est le retour au
combat) ; pour un tueur ou un assistant, la part opposée de la même mort. La dernière mort de la
victime avant l'instant du segment désigne ses tueurs.

### 4.4 Résidu, versionnage et recalcul

- `teams[…]["unattributed"]` ne contient plus que les variables à compteurs × temps, l'expiration
  des buffs et les morts sans tueur ; `attributed + unattributed == total` reste vrai.
- `WINPROB_IMPACT_CONVENTION: int = 2` dans `src/config_winprob.py`. `CoachingRepository.save_impact`
  range `model_version` sous la forme `wp-xxxxxxxx+c2` ; `games_without_impact()` renvoie aussi les
  parties dont les lignes n'ont pas la convention courante, et le brut de l'écran de fin
  (`raw_eog`, pour les postes). Le rattrapage du Live Coach (`compute_pending`) les recalcule : pas
  de commande nouvelle. Aucune migration Alembic : `event_type` est du texte libre.
- `compute_pending` reste best-effort : un écran de fin absent ou illisible → repli sur la moyenne
  adverse, jamais d'exception vers le Live Coach.

### 4.5 Rapport et bilan (`src/winprob/report.py`)

- La ligne « Non attribué (temps, farm, niveaux) » devient « Temps (valeur des avances qui évolue
  avec l'horloge, non attribuable) : N pts pour ton équipe ». La mention « vision, placement et
  gestion de vague ne sont pas mesurés » est conservée.
- `TYPE_LABELS` : `lost_*` (« Tours perdues », « Nashors perdus », …), `levels` (« Niveaux face à
  ton adversaire de lane »), `respawn` (« Récupération après mort »). `_describe()` couvre les
  `lost_*` (« tour perdue à 12:30 », « Nashor perdu à 24:10 »).
- `impact_review()` : le libellé « hors temps, farm et niveaux » est retiré ; `levels` et
  `respawn` sont comptés une fois par partie.
- Les écrans de SPEC-21 qui lisent `game_impact` par type (tâche 53) doivent connaître ces
  nouveaux types.

### 4.6 Mesure

`scripts/bench_impact_residual.py` : lit `data/db.db` en lecture seule, rejoue `impacts()` sur les
parties avec timeline et imprime le résidu de l'équipe du joueur (moyenne, moyenne en valeur
absolue, maximum) et sa composition. Base de référence au §1 (−20,3 / 25,1).

### 4.7 Tests (hermétiques, fixtures de `tests/fixtures/spike_gameplay/`)

Dans `tests/test_winprob_impact.py` et `tests/test_winprob_report.py` : symétrie des objectifs perdus,
repli « cinq présents », exactitude de la somme des niveaux, repli sans poste, opposition des deux
adversaires de lane, résidu nul avec un modèle jouet qui n'a de poids que sur `level` et `dead_s`,
convention versionnée (recalcul d'une partie `+c1`).

## 5. Tâches

| # | Tâche | Pts | Dépend de |
|---|---|---|---|
| 57 | `scripts/bench_impact_residual.py` : relever la base (−20,3 / 25,1) avant tout changement | 2 | — |
| 58 | Objectifs perdus : lignes `lost_*` aux absents, repli cinq présents (§4.1) + tests | 3 | 57 |
| 59 | `WinModel.logit_parts`, segments par joueur dans `state.py`, lignes `levels` et `respawn` (§4.2, §4.3) + tests | 5 | 58 |
| 60 | Convention versionnée, `games_without_impact` + `raw_eog`, rôles dans `compute_pending`, recalcul des 45 parties (§4.4) + tests | 3 | 59 |
| 61 | Rapport, bilan et libellés (§4.5), mesure finale consignée au §1, `CHANGELOG.md` | 3 | 60 |

## 6. Critères d'acceptation

1. `python -m pytest tests/ -v` vert, avec les tests des tâches ci-dessus.
2. `python scripts/bench_impact_residual.py` : résidu moyen de l'équipe du joueur **entre −3 et +3 pts**
   et moyenne en valeur absolue **≤ 12 pts** (avant : −20,3 et 25,1).
3. Un objectif pris par une équipe donne des lignes `lost_<k>` à l'autre équipe dont la somme est
   l'opposée de la somme des lignes de l'équipe qui marque (test).
4. Avec un modèle jouet pondérant seulement `level`, `dead` et `dead_s`, `unattributed` vaut 0 à
   1e-9 près sur la partie de la fixture (test).
5. Les lignes `levels` des deux adversaires de lane sont opposées ; sans poste connu, la somme des
   lignes `levels` d'une équipe est inchangée (tests).
6. `SELECT COUNT(DISTINCT game_id) FROM game_impact WHERE model_version NOT LIKE '%+c2'` vaut 0
   après un `compute_pending` sur la base de production.
7. Aucune occurrence de « Non attribué (temps, farm, niveaux) » dans `src/` (`grep`).
8. Un `raw_eog` absent, `None` ou corrompu ne lève aucune exception dans `compute_pending` (test).
9. `CHANGELOG.md` (`[Unreleased]`), statut de cette spec, `TODO.md` et `docs/specs/README.md` à jour.

**Vérification de bout en bout** : relancer le Live Coach après la tâche 60, laisser le rattrapage
recalculer les parties, puis `bilan` : la section d'impact liste les types `lost_*`, `levels` et
`respawn`, et le rapport d'une nouvelle partie affiche la ligne « Temps » à quelques points.

## 7. Hors périmètre

- ❌ **Vision** : aucun événement de ward dans la timeline LCU ; les totaux de fin de partie ne
  sont pas résolus dans le temps (gain de Brier probablement une fuite, §1). Reste dans la grille
  de SPEC-19 (`vision_per_min`). **À rouvrir** si l'overlay enregistre `wardScore` (Live Client,
  1 Hz) pendant les parties du joueur : la vision deviendrait résolue dans le temps.
- ❌ **Placement** : un seul échantillon de position par minute ; le seul proxy sûr est la position
  des morts (surextension), écarté par @pj35 le 2026-10-04.
- ❌ **Gestion de vague** : invisible à cette résolution.
- ❌ **CS et or dans le modèle** : modèle unique (§2). Le CS reste dans la grille de SPEC-19.
- ❌ **Attribution de la part « Temps »** (valeur d'une avance qui évolue avec l'horloge) : aucune
  convention défendable par joueur.
