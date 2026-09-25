# SPEC-15 — Runes, items et sorts poussés dans le client au lock-in

**Statut** : 🟡 Phase 1 **implémentée le 2026-09-24**, recette en partie réelle à faire (tâche 14)
(source OneTricks, [ADR-003](../adr/ADR-003-onetricks-temps-reel.md)).
Spike OneTricks fait (§2.2.1). Spike Coachless (§2.1.1) **fait le 2026-09-24** : faisable
techniquement mais exclu par les CGU de Coachless, ce qui bloque aussi
[SPEC-16](SPEC-16-moteur-optimisation-builds.md) A.

**Origine** : @pj35, 2026-09-23 — « une optimisation et import de runes/items dans le client ».
Arbitrages du 2026-09-23 : optimisation **maison** ([ADR-002](../adr/ADR-002-moteur-optimisation-builds.md)),
import **automatique au lock-in**. Révisé le 2026-09-24 après le spike : la source de l'import
devient **OneTricks en temps réel** (2 pages par draft, comme la recherche manuelle de @pj35),
Coachless est reporté, et la collecte de photographies par patch est **abandonnée**.

**Effort** : phase 1 ~1,5 jour.

---

## 1. Constat

- Rien n'existe : aucun appel `lol-perks`, `lol-item-sets` ni `my-selection` dans le code. Le
  Live Coach se contente d'afficher `[FINAL] Finalisez runes et sorts d'invocateur`
  (`src/draft/recommendations.py:248`).
- `src/lcu_client.py` fait **493 lignes** : tout le nouveau code va dans un module dédié.
  `_make_request(endpoint, method, data)` (l.181) suffit pour tous les appels LCU nécessaires.
- **Piège** : `self.player_champion` est renseigné **dès le survol**, pas au lock-in
  (`src/draft/state_parser.py:120-125` ne teste pas `action["completed"]`). Le déclencheur de
  cette spec ne doit pas s'y fier tel quel.

## 2. Phase 0 — Spike des sources

### 2.1 Coachless (🔵 reporté avec SPEC-16)

Coachless est une SPA. Avant toute ligne de production, ouvrir une page de build dans un
navigateur et relever dans l'onglet réseau :

1. **Les endpoints JSON** : URL, paramètres (champion, lane, patch, tier) et en-têtes exigés.
2. **L'authentification** : Coachless est **payant**, et @pj35 a un compte. Il faut relever quelles
   données sont derrière le paywall, le mécanisme d'authentification (cookie de session, JWT
   Bearer, autre), la durée de vie du jeton et la manière de le renouveler. Cela détermine si
   l'outil peut se reconnecter seul, ou s'il faudra recoller un jeton à la main à chaque
   expiration.
3. **La granularité exposée**, qui décide de la faisabilité de SPEC-16 :
   - builds complètes seulement (page de runes et build d'items « recommandées ») ;
   - **ou** WPA **par rune** et **par item**, **avec échantillons** (indispensable au shrinkage) ;
   - **ou** « situational WPA » (WPA d'un item selon le contexte : composition adverse, etc.) ;
   - une erreur-type ou un intervalle par WPA, qui donnerait directement le `C` de SPEC-16 §2.3.
   - **L'historique** : des patchs antérieurs sont-ils consultables ? Si oui, SPEC-16 A+ démarre
     avec un historique au lieu de 4 mois d'attente.
4. **Les identifiants** : IDs de perks et d'items au format Riot/Data Dragon (directement
   utilisables par le LCU), ou noms à mapper.
5. **Le comportement face à un client scripté** : `requests` avec un User-Agent navigateur
   passe-t-il, ou y a-t-il un 429 ou un challenge comme sur OneTricks ?

#### 2.1.1 Résultat du spike (2026-09-24) : faisable techniquement, exclu par les CGU

Source : un HAR de la page d'accueil connectée (@pj35) et les chunks JS publics de la SPA, qui
contiennent tous les services Angular. Aucun appel direct à l'API n'a été fait.

1. **Endpoints** : `https://api.coachless.gg/api`, en `POST` JSON.
   - Runes : `Rune/GetKeystoneData`, `GetMainTreePlaycount`, `GetSecondaryTreePlaycount`,
     `GetRunesForKeystoneAndTree`, `GetShardsForKeystoneAndTree`.
   - Items et sorts : `ChampionWinprob/GetGlobalItemStatistics`, `GetItemDetailed`,
     `GetItemUsers`, `GetGlobalSummonerSpellStatistics`.
   - Filtres communs : `{patch: {major, patch, patchAdditions}, championIds: [key],
     matchupChampionIds: [key] | null, leagueTiers: [3..9], regions, role: 0..4}`.
     Le filtre par adversaire est réservé aux abonnés.
2. **Authentification** : JWT `Bearer`. Le jeton d'accès vit 24 h, le jeton de
   rafraîchissement 30 jours et tourne à chaque `POST Auth/refresh {refreshToken}`.
   L'outil pourrait se reconnecter seul s'il sert au moins une fois tous les 30 jours.
3. **Granularité** : WPA **par rune et par item** (`wpaOverall`), **avec échantillon**
   (`occurrence` en nombre de parties, `occurrenceRelative` en %), plus `winrateExpected` et
   `winrateObserved`. Il y a aussi un WPA situationnel (`GetItemDetailed` : par groupe de
   situation, par slot d'item, par elo). Aucune erreur-type n'est exposée : le `C` de
   SPEC-16 §2.3 serait à dériver de `occurrence`.
   - **Historique** : `GetPatches` liste 18 patchs (16.1 à 16.18, 5 à 11 M de parties
     chacun), et `patchAdditions` agrège une plage. SPEC-16 A+ aurait démarré avec un historique.
4. **Identifiants** : IDs Riot (clé numérique de champion Data Dragon, perks `8xxx`, items,
   sorts), utilisables tels quels par le LCU.
5. **Client scripté** : non testé, par choix (voir ci-dessous).

**Bloquant** : les conditions d'utilisation (section 17, « Limited, Personal and
Non-Transferable License ») interdisent d'accéder à « any Coachless database, source code or
back-office service », sauf pour l'usage prévu du service. Elles interdisent aussi les copies
non autorisées au-delà du cache. Un client qui interroge l'API directement, et à plus forte
raison une collecte par patch, sort de cet usage. **Le spike est clos** : Coachless n'est pas
une source possible sans **autorisation écrite** de Coachless, que les CGU prévoient pour les
usages non personnels. SPEC-16 A reste reporté : sa matière existe, mais elle n'est pas
accessible légitimement.

### 2.2 OneTricks (source de l'import depuis ADR-003)

1. **Les endpoints** qui donnent les builds jouées par les one-tricks sur (champion, lane), avec
   leur nombre de parties (la popularité), et le **filtre par adversaire**, avec son winrate et
   son nombre de parties.
2. **La tolérance à l'accès scripté** : deux requêtes WebFetch ont reçu un **HTTP 429** le
   2026-09-23. À quel débit l'accès passe-t-il ? Un débit d'une requête par champion et par patch
   suffit pour une collecte hebdomadaire.
3. **L'historique**, comme pour Coachless.

**Repli** si OneTricks reste inaccessible : LoLalytics, déjà scrapé, fournit popularité et winrate
par matchup.

### 2.2.1 Résultats du spike OneTricks (2026-09-23)

**Accès.** Le site tourne sur Next.js et Vercel. La page HTML
`/champions/builds/{Champion}?role={role}&matchup={Adversaire}` embarque toutes ses données dans
le JSON `<script id="__NEXT_DATA__">` (~450 Ko) : il n'y a pas d'API à rétro-ingénierer.

- Avec l'User-Agent par défaut de `curl` ou de `requests`, on reçoit un **429 « Vercel Security
  Checkpoint »** : c'est un challenge anti-bot, qui explique les 429 constatés avec WebFetch.
- Avec un User-Agent de navigateur, la page répond **200** (10 requêtes espacées de 3 s, entre 0,1
  et 2,3 s chacune).
- La route JSON de Next.js (`/_next/data/{buildId}/...json`) est **toujours** derrière le
  checkpoint.
- Après ~17 requêtes en ~5 minutes, le checkpoint s'est déclenché **au niveau de l'IP**, même avec
  l'User-Agent de navigateur (y compris sur `/terms` et `robots.txt`). Le blocage
  était levé 10 minutes plus tard : c'est un plafond de débit, pas un bannissement.

**Contenu de `pageProps`** (exemple tronqué, Jinx bot) :

```json
{
  "filters": {"region": "", "role": "bot", "matchup": "", "twitch": ""},
  "patchList": ["all", "16", "16.19", "16.18"],
  "patchStats": {"16": 500, "all": 500, "16.19": 9, "16.18": 491},
  "firstItemStats": {"16": {"all": {
    "popKeystone": [["8008", 0.990], ["8992", 0.005]],
    "popRunes": {"8008": [[[8008, 8009, 8017, 8313, 8321, 9103], 0.302, [8000, 8300, 8008]], "..."]},
    "popStat": [5005, 5008, 5011],
    "popCore": [[[2523, 3085], 0.567], [[3032, 3031], 0.108], "..."],
    "sSpells": [[["21", "4"], 0.740], [["6", "4"], 0.149]],
    "startingItems": [[["1086", "2003", "2003", "3340"], 0.630]]
  }}},
  "matchHistory": [{"tier": "Master", "p": "16.19",
    "details": {"playerData": {"stats": {"item0": 3032, "perk0": 8008, "perkSubStyle": 8300, "win": true},
                               "spell1Id": 4, "spell2Id": 21}},
    "timeline": {"orderedItems": [3032, 3031, 3036, 3085, 1038, 1053]},
    "gameRoles": {"enemyChampion": 15, "playerRole": "bot", "gd15": 1316}}]
}
```

**Réponses aux trois questions de §2.2 :**

1. **Builds et popularité** : oui. Pages de runes complètes, core d'items, chemins d'items, sorts
   et items de départ, **identifiants Riot** directement utilisables par le LCU. Mais les agrégats
   ne portent qu'une **fraction de popularité**, sans winrate ni nombre de parties par build.
   L'échantillon total est donné par `patchStats` : les **500 dernières parties** de one-tricks
   (Master+). Un winrate par composant ne peut être recalculé que depuis `matchHistory`, qui
   n'expose que **100** de ces parties.
2. **Filtre par adversaire** : oui (`?matchup=Draven`), avec les mêmes agrégats restreints au duel.
   L'échantillon est mince : 40 parties Jinx contre Draven, sur 16.17 et 16.18.
3. **Historique** : **non**. `?patch=16.10` est ignoré ; seule la fenêtre glissante des 500
   dernières parties est servie (2 patchs ici). SPEC-16 A+ garde donc son délai de ~4 mois.

**Décision (@pj35, 2026-09-24) : OneTricks en temps réel, sans collecte.** La recommandation
initiale du spike (repli LoLalytics) supposait la collecte des 283 combos par patch prévue par
l'ancien §3.6. @pj35 a fait remarquer que sa recherche manuelle se limite à **deux pages** : son
champion sur sa lane, puis le duel contre son adversaire direct. Ni l'historique ni les autres
champions de la draft ne servent. Deux requêtes par draft restent très en dessous du seuil du
checkpoint (10 requêtes espacées de 3 s sont passées sans blocage) et correspondent au volume
d'une consultation manuelle. Voir [ADR-003](../adr/ADR-003-onetricks-temps-reel.md).

### 2.3 Livrable

Une section « Résultats du spike » ajoutée à cette spec, avec un exemple de réponse JSON tronqué
par source. Fait pour OneTricks (§2.2.1) ; celle de Coachless viendra avec SPEC-16.

## 3. Phase 1 — Import de la build OneTricks au lock-in, affinée au duel

Ce qu'on importe, c'est **la build la plus jouée par les one-tricks** sur (champion, lane). Dès
que l'adversaire direct est connu, on la **compare** à la page du duel, et on n'y substitue que
les composants que le duel sur-représente de façon significative (§3.2.1). Ce n'est pas la build
la plus jouée du duel qu'on copie : sur 40 parties, elle diffère surtout par le bruit
(décision @pj35 du 2026-09-24).

### 3.1 Module

`src/draft/loadout.py` (nouveau) contient trois responsabilités, séparées en fonctions :

- **`fetch_page(champion, lane, opponent=None) -> Optional[dict]`** : `GET
  https://www.onetricks.gg/champions/builds/{Nom}?role={role}[&matchup={Adversaire}]`, avec un
  User-Agent de navigateur et un timeout court (tous deux dans `config_constants.py`), puis
  extraction du JSON `<script id="__NEXT_DATA__">` → `props.pageProps`. Les noms passent par
  `normalize_champion_name_for_onetricks` et les lanes par `_LANE_TO_ONETRICKS_ROLE`
  (`src/draft/onetricks.py`), les mêmes que pour la fenêtre de fin de draft. Renvoie `None` en
  cas d'échec (réseau, 429, JSON absent), sans lever d'exception. Le cache mémoire par
  (champion, lane, adversaire) vit dans `get_build`, et ne retient que les succès.
- **`pick_build(page_props) -> Optional[Build]`** : lit l'agrégat
  `firstItemStats["all"]["all"]`, c'est-à-dire la fenêtre glissante des 500 dernières parties de
  one-tricks, tous premiers items confondus :
  - **runes** : `popKeystone[0]`, puis la première page de `popRunes[keystone]` (6 perks et
    `[style principal, style secondaire, keystone]`), et les fragments `popStat` ;
  - **items** (révisé le 2026-09-25, set « façon Coachless ») : départ `startingItems[0]`,
    autres départs, core `popCore[0]`, cores alternatifs, bottes (choix puis alternatives),
    composants (`componentBuildPaths`) et les `LOADOUT_SITUATIONAL_ITEMS` items les plus joués
    (`popularItems`). La popularité du choix est dans le titre du bloc (« Core (57%) »), et un
    item ne figure qu'une fois hors départ. `popPath` n'est plus lu : ses options pèsent 0,3 à
    2 % des parties, et le même item pouvait arriver premier de deux emplacements (Sterak ×2
    dans le set Yorick du 2026-09-25) ;
  - **sorts** : `sSpells[0]`.

  Tout champ manquant donne `None`, car la structure n'est pas documentée et peut changer.
- **`adapt_to_matchup(general_page, duel_page) -> Optional[(Build, List[Substitution])]`** : la
  build générale, avec les substitutions significatives du duel (§3.2.1). Chaque `Substitution`
  garde sa catégorie, l'ancienne et la nouvelle option, les deux popularités et le nombre de
  parties, pour la console.
- **`apply_build(lcu, build) -> None`** (dans `loadout_lcu.py`) : les trois écritures LCU (§3.3), chacune indépendante et
  best-effort. L'échec de l'une n'empêche pas les autres.

`Build` est un simple dataclass : perks, styles, fragments, blocs d'items, deux sorts, plus le
nombre de parties de la page (`patchStats["all"]`) pour la sortie console.

**Fenêtre temporelle.** « Le patch actuel » est approché par la fenêtre des 500 dernières parties,
et non par la clé du dernier patch. Juste après une sortie de patch, la clé de ce patch ne
contient qu'une poignée de parties (9 pour Jinx le 2026-09-23, contre 491 pour le patch
précédent).

### 3.2 Déclenchement

- **Au lock-in** : l'action `pick` du joueur local est `completed: True`. Tester `completed`
  explicitement, sans passer par `player_champion` (cf. §1). On importe la build générale, puis
  l'affinage suit immédiatement si l'adversaire direct est déjà connu.
- **Affinage** : dès qu'un ennemi **locké** a pour lane inférée celle du joueur, on télécharge la
  page du duel et on applique `adapt_to_matchup`. S'il y a au moins une substitution, on
  réimporte (la page de runes `"LS "` et le set sont remplacés) ; sinon, on conserve la build
  générale, avec un `[INFO]`.
- **Une fois par (champion, lane, adversaire) et par draft** : un échange de champion (trade),
  une correction de lane via la commande existante ou une réinférence de l'adversaire relance
  l'import. Tout le reste est ignoré. En pratique, cela fait **deux requêtes par draft**.
- Lane : `self.hover._resolve_player_lane()`, la même résolution que pour l'ouverture de
  OneTricks. Lane de l'adversaire : `state.inferred_roles`.
- Flag `draft_config.AUTO_IMPORT_LOADOUT` (par défaut `True`) pour désactiver la fonction.
- Réinitialisé avec le reste de l'état de draft dans `lifecycle.py` (à côté de
  `player_champion = None`).
- Appel synchrone dans la boucle de draft : la page répond entre 0,1 et 2,3 s. Le timeout borne
  le pire cas. À signaler `ponytail:`, avec un thread comme voie de sortie si la latence gêne en
  pratique.

#### 3.2.1 Règle de substitution

Catégories comparées, chacune comme une unité : **keystone** (avec la première page de runes du
duel pour cette keystone), **items de départ**, **core**, **bottes** et **paire de sorts**. Pour
chaque catégorie, avec `n` le nombre de parties du duel (`patchStats["all"]`) :

1. Pour chaque option `o` de la page du duel, autre que le choix de la build générale, on calcule
   `k = round(popularité_duel(o) × n)` et `p0 = popularité_générale(o)`. Si `o` est absente de la
   page générale, qui ne publie que ses options les plus jouées, `p0` prend
   `min(plus petite popularité publiée, 1 − somme des popularités publiées)` de la catégorie.
   Les deux bornes sont des majorants valides : sur les fixtures, la somme par catégorie reste
   ≤ 1, donc le dénominateur est commun. La règle reste prudente. La plus petite popularité
   publiée ne suffit pas seule : les items de départ n'en publient qu'une, à 94 %. Le
   majorant ne descend jamais sous `1 / parties générales` (1/500) : quand la somme publiée
   atteint 100 %, la masse restante vaut 0, et une seule partie de duel suffirait sinon.
2. `o` est **significative** si `P(Binomiale(n, p0) ≥ k) < draft_config.LOADOUT_MATCHUP_ALPHA`
   (0,05). Le test se calcule en stdlib (`math.comb`).
3. Si plusieurs options sont significatives, on retient la plus jouée dans le duel. Elle remplace
   le choix général, même si ce dernier reste majoritaire dans le duel : ce qu'on cherche, c'est
   ce que le duel **change**, pas ce qu'il reproduit.

Exemple sur les fixtures, Jinx contre Draven (40 parties) :

| Option du duel | Duel | Général (p0) | p | Substituée |
|---|---|---|---|---|
| Fatigue + Flash | 12,2 % | < 3,7 % (masse restante) | 0,015 | **oui** |
| Lame de Doran au départ | 12,2 % | < 6,2 % (masse restante) | 0,098 | non |
| Core Hexoptics C44 + Infinity Edge | 12,9 % | < 8,4 % (plus petite publiée) | 0,239 | non |
| Gluttonous Greaves (3008) | 10,7 % | 15,5 % | 0,886 | non |

La build affinée ne change donc que les sorts. α se règle dans `config_constants.py`.

### 3.3 Écritures LCU

| Quoi | Appel | Règle |
|---|---|---|
| Runes | `POST /lol-perks/v1/pages` `{name, primaryStyleId, subStyleId, selectedPerkIds, current: true}` | Page nommée avec un préfixe fixe (`"LS "`, dans `config_constants.py`). Avant de créer, supprimer **uniquement** une page existante portant ce préfixe (`DELETE /lol-perks/v1/pages/{id}`). **Ne jamais supprimer ni écraser une page du joueur** : s'il n'y a aucun emplacement libre, afficher `[INFO] Aucun emplacement de page de runes libre` et passer. |
| Items | `PUT /lol-item-sets/v1/item-sets/{summonerId}/sets` | `summonerId` via `GET /lol-summoner/v1/current-summoner`. Le PUT remplace **toute** la liste : faire un GET, retirer uniquement le set au préfixe `"LS "`, ajouter le nouveau, puis PUT. Les sets du joueur sont préservés. |
| Sorts | `PATCH /lol-champ-select/v1/session/my-selection` `{spell1Id, spell2Id}` | Respecter l'ordre Flash existant du joueur : si Flash est déjà sur D ou F, le garder sur cette touche. |

Les formats exacts des corps de requête sont à confirmer contre le client réel pendant
l'implémentation : les champs ci-dessus sont ceux documentés par la communauté, pas par Riot.
Les identifiants OneTricks sont ceux de Riot (§2.2.1) : aucun mapping n'est nécessaire.

### 3.4 Sortie console

```
[OK] Build importée : Jinx bot (500 parties one-tricks)
[OK] Build affinée vs Draven (40 parties) :
  Sorts  Barrier+Flash -> Exhaust+Flash  (12% vs <4% en général)
```

ou `[INFO] Duel vs Draven (40 parties) : aucun écart significatif, build générale conservée`,
ou encore `[INFO] Build non importée : <raison>`. Les noms d'items, de runes et de sorts viennent
de `itemData`, de `runes` et de `summonerSpells`, déjà présents dans `pageProps`. Le détail des
tests n'apparaît qu'en verbose.

### 3.5 Critères d'acceptation (tests)

Hermétiques : LCU et HTTP simulés (`monkeypatch` / `unittest.mock`), avec une page OneTricks
enregistrée et tronquée comme fixture, sans aucun appel réseau réel.

1. Un survol (`completed: False`) **ne déclenche pas** d'import ; le lock-in en déclenche un seul.
   Un deuxième passage dans la boucle avec le même état n'en déclenche pas de second.
2. **Affinage** : le lock de l'adversaire direct déclenche une seule comparaison ; un ennemi
   d'une autre lane n'en déclenche aucune. Sans substitution, aucune écriture LCU n'a lieu.
11. **Substitutions** (`adapt_to_matchup`) : sur les fixtures Jinx contre Draven, seuls les
    sorts sont remplacés (Barrière+Flash → Fatigue+Flash). Une option absente de la page générale est
    testée contre `min(plus petite publiée, 1 − somme publiée)`. Avec deux options
    significatives, la plus jouée l'emporte. Un changement de keystone emporte la page de runes
    du duel pour cette keystone.
3. Un trade de champion après le lock-in relance l'import.
4. **Runes** : une page `"LS …"` existante est supprimée puis recréée. Les pages sans préfixe ne
   subissent jamais de `DELETE`. Sans emplacement libre, pas d'écriture et un `[INFO]`.
5. **Items** : le PUT contient les sets du joueur à l'identique, plus un seul set `"LS …"`.
6. **Sorts** : Flash reste sur la touche où le joueur l'avait.
7. **Best-effort** : un 429 (checkpoint Vercel), un timeout, une page sans `__NEXT_DATA__`, un
   champ manquant dans `pageProps` ou un 500 du LCU ne lèvent aucune exception hors de
   `loadout.py`, et la boucle de draft continue.
8. Le flag `AUTO_IMPORT_LOADOUT = False` désactive tout appel.
9. **Cache et débit** : deux lock-ins sur le même (champion, lane, adversaire) ne font qu'un seul
   appel HTTP. Une draft complète en fait au plus deux.
10. `pick_build` sur la fixture renvoie la page de runes, les blocs d'items et les sorts attendus.

## 4. Optimisation maison

Reportée avec [SPEC-16](SPEC-16-moteur-optimisation-builds.md) (méthode : ADR-002). Quand le
moteur sera prêt, `pick_build` sera remplacé par un appel au moteur, sans toucher aux écritures
LCU.

## 5. Fichiers touchés (phase 1)

| Fichier | Changement |
|---|---|
| `src/draft/loadout.py` (nouveau) | Fetch OneTricks, choix de la build, cache, affinage au duel |
| `src/draft/loadout_lcu.py` (nouveau) | Écritures LCU (§3.3), extraites de `loadout.py` pour la limite de 500 lignes |
| `src/draft/lifecycle.py` | Déclenchement au lock-in et à l'affinage, réinitialisation |
| `src/config_constants.py` | `AUTO_IMPORT_LOADOUT`, `LOADOUT_MATCHUP_ALPHA`, timeout, User-Agent, préfixe `"LS "` |
| `tests/test_loadout.py`, `tests/fixtures/onetricks_*.json` (nouveaux) | §3.5 |
