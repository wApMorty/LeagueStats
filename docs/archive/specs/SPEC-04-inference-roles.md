# SPEC-04 ⭐ — Inférer le rôle des 10 joueurs et l'exploiter dans le Live Coach

**Items** : B3, B4, B5 · **Priorité** : 4 · **Effort estimé** : ~3 jours
**Constats d'audit** : M1 (`docs/AUDIT_2026_08.md` §4)
**Prérequis** : **SPEC-03 obligatoire** (les accesseurs doivent déjà accepter une lane)
**Décision @pj35 (29/08)** : *« Il va falloir que le Live Coach soit en mesure de deviner la lane de chaque allié et chaque adversaire pour affiner les calculs. »*

---

## 1. Contexte

SPEC-03 rend la lecture des données filtrable par lane. Cette spec fournit **l'information manquante** : quel joueur joue quel rôle, des deux côtés du draft.

Sans elle, le coach compare des données mélangées : Pantheon vaut +0,30 en top et −0,08 en support, et il ne fait pas la différence. Avec elle, chaque matchup est évalué dans son contexte réel.

Le problème n'est pas « deviner 10 lanes indépendamment ». Une équipe a **exactement un joueur par rôle** : c'est une **affectation sous contrainte**, et cette contrainte est ce qui rend l'inférence fiable. « Chaque champion prend sa lane la plus fréquente » produit des équipes à deux junglers et zéro support ; l'affectation globale, non.

---

## 2. Objectif

1. Le Live Coach connaît, à tout moment du draft, le rôle probable de chacun des 10 champions sélectionnés.
2. Cette information alimente le scoring (via le paramètre `lane` de SPEC-03).
3. Elle est **affichée** et **corrigeable** par le joueur.
4. Elle se **réévalue à chaque pick**, l'information s'affinant à mesure que le draft avance.

---

## 3. Sources d'information, par ordre de fiabilité

| # | Source | Fiabilité | Disponibilité |
|---|---|---|---|
| 1 | `assignedPosition` du LCU | Certaine | Alliés uniquement, files avec sélection de rôle |
| 2 | Distribution de lanes du champion | Probabiliste | Toujours (déjà scrapée) |
| 3 | Contrainte « un rôle par joueur » | Structurelle | Toujours |
| 4 | Ordre de pick | Faible | Toujours — **à n'utiliser qu'en départage, phase 2** |

---

## 4. Travail à faire

### B3 — Exposer `assignedPosition` (à faire en premier, autonome)

**`src/lcu_client.py`** — la session de champion select contient, pour chaque joueur de `myTeam` :

```json
{"cellId": 2, "championId": 84, "assignedPosition": "middle", "summonerId": ...}
```

Valeurs LCU : `"top"`, `"jungle"`, `"middle"`, `"bottom"`, `"utility"`, ou `""` quand la file n'attribue pas de rôle. `theirTeam` a presque toujours `assignedPosition` vide (masqué par le client).

⚠️ **`"utility"` doit être traduit en `"support"`** — c'est la valeur utilisée par LoLalytics et stockée dans la colonne `lane`. Placer la table de correspondance dans `src/config_constants.py` :

```python
LCU_POSITION_TO_LANE = {
    "top": "top", "jungle": "jungle", "middle": "middle",
    "bottom": "bottom", "utility": "support",
}
```

Ajouter à `LCUClient` :

```python
def get_assigned_positions(self, champ_select_data: Dict) -> Dict[int, str]:
    """cellId -> lane normalisée, pour les joueurs dont le rôle est attribué.

    Les entrées sans assignedPosition (ou avec une valeur inconnue) sont
    simplement absentes du dictionnaire.
    """
```

**`src/draft_monitor.py`** — étendre `DraftState` (l. 52) :

```python
ally_positions: Dict[int, str] = field(default_factory=dict)    # cellId -> lane
inferred_roles: Dict[int, str] = field(default_factory=dict)    # championId -> lane
role_confidence: Dict[int, float] = field(default_factory=dict) # championId -> [0,1]
```

et remplir `ally_positions` dans `_parse_draft_state` (l. 656).

> **Note de typage** : `DraftState.ally_picks` et `enemy_picks` sont annotés `List[str]` mais contiennent des **`int`** (IDs Riot, voir l. 672-679). Ne pas propager l'erreur : les nouveaux champs sont typés juste. Corriger les annotations existantes est bienvenu si c'est fait dans un commit séparé.

### B4 — Inférence des rôles

#### 4.1 Persister la distribution de lanes

`src/lane_discovery.py:parse_lane_distribution()` renvoie déjà la distribution complète (`{"top": 75.1, "jungle": 22.0, ...}`) à chaque scrape — **et la jette** : seules les lanes au-dessus du seuil sont conservées, sous forme de tag sur les lignes.

C'est exactement la matrice de vraisemblance dont l'inférence a besoin. **La persister** :

Migration Alembic — nouvelle table :

```sql
CREATE TABLE champion_lanes (
    champion INTEGER NOT NULL,
    lane TEXT NOT NULL,
    share REAL NOT NULL,          -- part des parties du champion, en %
    PRIMARY KEY (champion, lane),
    FOREIGN KEY (champion) REFERENCES champions(id) ON DELETE CASCADE
);
```

Écrite par `discover_lanes_for_champions` (ou par son appelant dans le pipeline), avec la distribution **complète**, pas seulement les lanes retenues pour le scrape.

**Repli si la table est vide** (base pas encore re-scrapée) : dériver la distribution depuis `matchups` —

```sql
SELECT lane, SUM(games) FROM matchups WHERE champion = ? GROUP BY lane
```

normalisé à 100 %. C'est un proxy imparfait (le volume de parties d'un matchup n'est pas celui du champion) mais suffisant pour démarrer. Le code doit fonctionner dans les deux cas.

#### 4.2 L'algorithme d'affectation

Nouveau module **`src/role_inference.py`** (< 250 lignes, aucune dépendance externe).

**Principe.** Pour une équipe de N champions (N ≤ 5) et les 5 rôles, on cherche l'affectation qui maximise la vraisemblance globale :

```
score(affectation) = Σ_i  log( max(share[champion_i][rôle_i], EPSILON) )
```

- `share` = part des parties du champion sur ce rôle, en % (table `champion_lanes`) ;
- le logarithme transforme le produit des probabilités en somme — c'est ce qui rend les scores additionnables ;
- `EPSILON` (nouvelle constante, **0.5**, en %) évite `log(0)` pour un rôle jamais joué : une affectation absurde devient très improbable, pas impossible — ce qui est nécessaire quand la seule affectation valide en contient une (comp exotique).

**Méthode de résolution : énumération exhaustive.** Il y a au plus `5! = 120` affectations. Les énumérer toutes et garder la meilleure est **exact, instantané (< 1 ms), et tient en une dizaine de lignes** :

```python
from itertools import permutations

best = max(
    permutations(LANES, len(champions)),
    key=lambda assignment: sum(
        log_share(champion, lane) for champion, lane in zip(champions, assignment)
    ),
)
```

> Ne **pas** introduire `scipy` pour un algorithme hongrois : la force brute est optimale à cette taille, et `scipy` pèserait ~30 Mo dans le binaire PyInstaller pour zéro bénéfice.

**Contraintes dures.** Quand `assignedPosition` donne le rôle d'un allié, ce rôle est **fixé** : on retire le champion et le rôle de l'énumération et on résout sur le reste (au plus 4! = 24 cas). Si toutes les positions sont connues, il n'y a rien à inférer.

**Interface publique** :

```python
@dataclass(frozen=True)
class RoleAssignment:
    roles: Dict[int, str]        # championId -> lane
    confidence: Dict[int, float] # championId -> [0,1]
    source: Dict[int, str]       # championId -> "lcu" | "inferred"

def infer_team_roles(
    champion_ids: List[int],
    lane_distributions: Dict[int, Dict[str, float]],
    known_positions: Optional[Dict[int, str]] = None,
) -> RoleAssignment:
    """Affecte un rôle distinct à chaque champion d'une équipe (partielle ou complète)."""
```

**Confiance.** Pour chaque champion, comparer la meilleure affectation globale à la meilleure affectation qui lui donnerait un *autre* rôle :

```
confiance = 1 − exp(score_meilleure_alternative − score_meilleure)
```

Résultat dans [0, 1] : proche de 1 quand le rôle est évident (Yuumi support), proche de 0 quand deux rôles se valent (Pantheon top/support). `confidence = 1.0` pour un rôle venu du LCU. Cette valeur pilote l'affichage (B5) et **doit** être exposée : c'est ce qui permet au joueur de savoir quand corriger.

**Équipes partielles.** En début de draft, une équipe peut n'avoir que 1 ou 2 champions. L'affectation fonctionne à l'identique sur un sous-ensemble — mais la contrainte joue moins, donc la confiance est mécaniquement plus basse. Ne pas forcer d'affectation quand un seul champion est connu : renvoyer son rôle le plus probable avec la confiance correspondante.

#### 4.3 Branchement dans le Live Coach

Dans `src/draft_monitor.py` :

- après `_parse_draft_state`, appeler `infer_team_roles` **deux fois** (équipe alliée avec `known_positions`, équipe ennemie sans) et remplir `state.inferred_roles` / `state.role_confidence` ;
- recalculer **à chaque changement de draft** (`_handle_draft_change`, l. 737) — c'est peu coûteux et l'information s'affine à chaque pick ;
- passer la lane du joueur à `_calculate_score_against_team` et `_calculate_synergy_score` (paramètre ajouté par SPEC-03) ;
- pour l'évaluation d'un **champion candidat** du pool : sa lane est celle du joueur (celle de son propre rôle), pas celle de l'adversaire.

**Le point subtil, à traiter explicitement.** La colonne `lane` d'une ligne `matchups` est celle du champion **A** (le picker), pas celle de son adversaire. Quand on évalue « mon candidat X en top contre Darius », la requête pertinente est `get_champion_matchups_for_draft("X", lane="top")` puis on y cherche Darius. Le rôle inféré de Darius **ne sert pas à filtrer cette requête** ; il sert à savoir **quels adversaires comptent le plus** : celui qui joue la même lane que nous est notre adversaire direct.

Suggestion de pondération, à mettre en config (`draft_config`) plutôt qu'en dur :

```python
SAME_LANE_WEIGHT: float = 2.0    # adversaire direct
OTHER_LANE_WEIGHT: float = 1.0   # reste de l'équipe ennemie
```

Valeurs de départ à considérer comme provisoires — elles se calibreront avec SPEC-05.

**Ne pas faire grossir `draft_monitor.py`** (1 547 lignes) : toute la logique d'inférence vit dans `src/role_inference.py`, le monitor ne fait qu'appeler et stocker.

### B5 — Affichage et correction

**Affichage de l'état du draft** (`_display_draft_state`, l. 790) — montrer les rôles :

```
ALLIÉS   : Ornn (top·LCU) · Sejuani (jungle·LCU) · Ahri (middle·LCU) · ? · ?
ENNEMIS  : Darius (top·92%) · Viego (jungle·88%) · Pantheon (support·54%)
```

Marquer la source : `LCU` pour un rôle certain, un pourcentage pour un rôle inféré. Sous un seuil (`ROLE_CONFIDENCE_WARN`, **0.6**), signaler par `?` la nécessité d'une vérification.

**Recommandations** (`_provide_recommendations`, l. 818) — ajouter lane et volume :

```
[1st] Pantheon (top vs Darius) +2,34% · 4 800 parties
```

Le nombre de parties vient de la somme des `games` des matchups retenus (déjà disponible après l'agrégation de SPEC-03).

**Correction manuelle** : une commande simple dans la boucle du coach (par exemple `r` puis `<champion> <lane>`) qui force un rôle et relance le calcul. Le rôle forcé prend le statut `"user"` et une confiance de 1.0, et **survit aux recalculs suivants** tant que le champion reste dans le draft. À implémenter sans bloquer la boucle de polling (`_monitor_loop`, l. 290) — si l'entrée non bloquante s'avère compliquée, se limiter d'abord à l'affichage et livrer la correction dans un second temps : elle n'est pas indispensable au fonctionnement.

---

## 5. Critères d'acceptation

- [x] En file classée, les rôles des 5 alliés viennent du LCU avec `source="lcu"` et `confidence=1.0`. Vérifié au niveau algorithme par `tests/test_role_inference.py::TestKnownPositions` et bout-en-bout (DraftState) par `tests/test_draft_monitor_roles.py::test_lcu_known_position_overrides_dominant_lane`. `DraftState` ne persiste pas le champ `source` (schéma fixé en B3) : seul `RoleAssignment.source` (interne à `role_inference.py`) le porte ; B5 le redérive via `ally_positions` pour l'affichage.
- [x] `"utility"` est bien traduit en `"support"` (aucun `"utility"` ne parvient jusqu'aux requêtes SQL). Vérifié par `tests/test_lcu_assigned_positions.py`.
- [x] L'inférence sur une équipe ennemie complète renvoie **5 rôles distincts** — jamais deux junglers. Vérifié par `tests/test_role_inference.py::TestRoleUniqueness` et `tests/regression/test_regression_role_uniqueness.py` (50 compositions aléatoires).
- [x] Un cas de test « équipe classique » (Ornn, Sejuani, Ahri, Jinx, Thresh) est résolu correctement à 100 %. `tests/test_role_inference.py::TestClassicTeam::test_resolves_exactly`.
- [x] Un cas ambigu (type Pantheon/Senna, jouables sur plusieurs rôles) renvoie une affectation cohérente avec une confiance faible sur les champions concernés (et une confiance élevée sur un cas évident type Yuumi). `tests/test_role_inference.py::TestAmbiguousCase`.
- [x] L'inférence fonctionne sur une équipe partielle (1 à 4 champions) sans exception. `tests/test_role_inference.py::TestPartialTeams` (paramétré 1 à 5).
- [x] Un champion absent de `champion_lanes` (nouveau champion) ne fait pas planter : repli sur la distribution dérivée de `matchups`, ou confiance nulle. `tests/test_champion_lanes_table.py::TestFallbackToMatchups`, `tests/test_role_inference.py::TestMissingDistribution`.
- [ ] Les rôles sont recalculés à chaque pick (vérifié : `tests/test_draft_monitor_roles.py::test_recomputed_as_more_champions_are_picked`), et la confiance augmente à mesure que le draft se remplit (non vérifié spécifiquement — propriété émergente de l'algorithme, pas testée numériquement).
- [x] Le scoring reçoit bien la lane : forcer sa lane à `top` puis `support` change les recommandations. Vérifié au niveau `ChampionScorer.score_against_team` (`tests/test_bidirectional_scoring.py::TestLaneWeighting`), de son branchement dans `DraftMonitor` (`tests/test_draft_monitor_roles.py::TestLaneWiringIntoScoring`), et désormais via la commande de correction manuelle elle-même (B5, `tests/test_draft_monitor_display.py::TestManualCorrectionCommand`).
- [x] L'affichage montre rôle, source et volume de parties (B5). `_display_draft_state` : `tests/test_draft_monitor_display.py::TestFormatRoleTag`/`TestDisplayDraftStateShowsRoles`. `_provide_recommendations` : `TestRecommendationLaneAndVolumeTags`.
- [x] Temps d'inférence < 5 ms pour les deux équipes (mesuré) — il tourne dans la boucle de polling. Mesuré manuellement : ~0.73 ms pour les deux équipes (10 champions, 100 itérations).
- [x] `pytest tests/ -v` : 0 échec. 705 tests passent.

---

## 6. Tests exigés

| Fichier | Contenu |
|---|---|
| `tests/test_role_inference.py` (nouveau) | Cœur de la spec : équipe classique → affectation exacte ; unicité des rôles garantie ; contraintes LCU respectées ; équipes de 1 à 5 champions ; champion sans distribution ; `EPSILON` empêche `log(0)` ; confiance élevée sur un cas évident, faible sur un cas ambigu |
| `tests/test_lcu_assigned_positions.py` (nouveau) | `get_assigned_positions` : mapping `utility → support`, `assignedPosition` vide ignoré, valeur inconnue ignorée, `theirTeam` sans positions |
| `tests/test_draft_monitor_roles.py` (nouveau) | `DraftState` peuplé correctement ; recalcul à chaque changement ; lane transmise aux fonctions de score (mock) ; rôle forcé par l'utilisateur préservé |
| `tests/test_champion_lanes_table.py` (nouveau) | Migration ; écriture de la distribution complète ; repli sur `matchups` quand la table est vide |
| `tests/regression/test_regression_role_uniqueness.py` (nouveau) | **Invariant central** : sur 50 compositions aléatoires, aucune affectation ne duplique un rôle |

Les tests d'inférence doivent utiliser des distributions **fixées en dur dans le test**, jamais la base réelle : le méta change, les tests ne doivent pas.

---

## 7. Pièges connus

- **Le rôle n'est pas le champion.** Un joueur peut jouer Pantheon en support avec des runes de support : la distribution de lanes le capture statistiquement, jamais individuellement. Le système propose, le joueur corrige — d'où l'importance de B5.
- **`assignedPosition` peut être présent mais faux** en file flexible / normale (rôle « autofill » puis échange en draft). Prévoir que le joueur puisse corriger même un rôle venu du LCU.
- **ARAM et modes sans lanes** : `assignedPosition` vide partout, distributions non pertinentes. Détecter le mode de jeu (`gameflow` / `queueId`) et **désactiver** l'inférence plutôt que produire n'importe quoi.
- **Les IDs Riot ne sont pas les IDs de la base.** `DraftState` manipule des `championId` Riot ; `champion_lanes` référence `champions.id` (interne). La conversion passe par `self.champion_id_to_name` (`_load_champion_mappings`, l. 557) puis `db.get_champion_id`. Ne pas confondre les deux espaces d'identifiants — c'est la source d'erreur la plus probable de cette spec.
- **Performance** : l'inférence tourne dans `_monitor_loop`, cadencé à `POLL_INTERVAL = 1.0 s`. 120 permutations sont négligeables, mais **ne pas** relire `champion_lanes` en base à chaque tick : charger les distributions une fois au démarrage du monitor.
- **Ne pas réintroduire un fichier > 500 lignes.** `src/role_inference.py` doit rester un module de calcul pur, sans accès base ni I/O : cela le rend trivialement testable.

---

## 8. Hors périmètre

- Prédire le rôle **avant** le pick (à partir du ban ou de l'ordre de pick seul).
- Utiliser l'ordre de pick comme signal : possible plus tard, en départage uniquement, si les mesures montrent que l'ambiguïté est fréquente.
- Détection du swap de rôles en jeu (après la fin du draft).
- Refonte de la formule de score → SPEC-05.
