# SPEC-15 — Runes, items et sorts poussés dans le client au lock-in

**Statut** : 🟡 Phase 0 **à faire** · Phase 1 **bloquée par la phase 0** · Phase 2 → déplacée
dans [SPEC-16](SPEC-16-moteur-optimisation-builds.md).

**Origine** : @pj35, 2026-09-23 — « une optimisation et import de runes/items dans le client ».
Arbitrages du 2026-09-23 : source **Coachless** ([ADR-001](../adr/ADR-001-source-builds-coachless.md)),
optimisation **maison** ([ADR-002](../adr/ADR-002-moteur-optimisation-builds.md)), import
**automatique au lock-in**.

**Effort** : phase 0 ~1 jour (deux sources) · phase 1 ~1,5 jour (dont la collecte des
photographies).

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

## 2. Phase 0 — Spike des sources (bloquant)

### 2.1 Coachless

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

### 2.2 OneTricks (source des candidats de SPEC-16)

1. **Les endpoints** qui donnent les builds jouées par les one-tricks sur (champion, lane), avec
   leur nombre de parties (la popularité), et le **filtre par adversaire**, avec son winrate et
   son nombre de parties.
2. **La tolérance à l'accès scripté** : deux requêtes WebFetch ont reçu un **HTTP 429** le
   2026-09-23. À quel débit l'accès passe-t-il ? Un débit d'une requête par champion et par patch
   suffit pour une collecte hebdomadaire.
3. **L'historique**, comme pour Coachless.

**Repli** si OneTricks reste inaccessible : LoLalytics, déjà scrapé, fournit popularité et winrate
par matchup.

### 2.3 Livrable

Une section « Résultats du spike » ajoutée à cette spec, avec un exemple de réponse JSON tronqué
par source. **Si Coachless échoue** (API inexploitable ou bloquée) : on s'arrête et on rouvre
ADR-001 avec LoLalytics comme repli.

## 3. Phase 1 — Import de la build Coachless au lock-in

Ce qu'on importe, c'est **la build recommandée par Coachless** pour (champion, lane).
L'optimisation maison viendra avec SPEC-16. La phase 1 livre toute la tuyauterie, dont SPEC-16
aura besoin quoi qu'il arrive, **et commence la collecte des photographies par patch** (§3.6).

### 3.1 Module

`src/draft/loadout.py` (nouveau) contient deux responsabilités, séparées en fonctions :

- **`fetch_build(champion, lane) -> Optional[Build]`** : appel Coachless avec un timeout court
  (valeur dans `config_constants.py`) et un cache mémoire par (champion, lane, patch). Renvoie
  `None` en cas d'échec, sans lever d'exception.
- **`apply_build(lcu, build) -> None`** : les trois écritures LCU (§3.3), chacune indépendante et
  best-effort. L'échec de l'une n'empêche pas les autres.

**Identifiants Coachless** : jamais dans le dépôt ni dans les logs. Ils sont lus depuis une
variable d'environnement (`COACHLESS_TOKEN`, ou ce que le spike aura désigné). Si elle est absente
ou si le jeton a expiré (401/403) : `[INFO] Build non importée : session Coachless absente ou
expirée`, sans aucune nouvelle tentative en boucle.

`Build` est un simple dataclass : perks principaux et secondaires, styles, fragments, blocs
d'items, deux sorts.

Si le code Coachless dépasse une cinquantaine de lignes, il sort dans `src/coachless_client.py`.
Sinon, tout reste dans `loadout.py`.

### 3.2 Déclenchement

- **Au lock-in** : l'action `pick` du joueur local est `completed: True`. Tester `completed`
  explicitement, sans passer par `player_champion` (cf. §1).
- **Une fois par (champion, lane) et par draft** : un échange de champion (trade) ou une
  correction de lane via la commande existante relance l'import. Tout le reste est ignoré.
- Lane : `self.hover._resolve_player_lane()`, la même résolution que pour l'ouverture de
  OneTricks.
- Flag `draft_config.AUTO_IMPORT_LOADOUT` (par défaut `True`) pour désactiver la fonction.
- Réinitialisé avec le reste de l'état de draft dans `lifecycle.py` (à côté de
  `player_champion = None`, l.216).

### 3.3 Écritures LCU

| Quoi | Appel | Règle |
|---|---|---|
| Runes | `POST /lol-perks/v1/pages` `{name, primaryStyleId, subStyleId, selectedPerkIds, current: true}` | Page nommée avec un préfixe fixe (`"LS "`, dans `config_constants.py`). Avant de créer, supprimer **uniquement** une page existante portant ce préfixe (`DELETE /lol-perks/v1/pages/{id}`). **Ne jamais supprimer ni écraser une page du joueur** : s'il n'y a aucun emplacement libre, afficher `[INFO] Aucun emplacement de page de runes libre` et passer. |
| Items | `PUT /lol-item-sets/v1/item-sets/{summonerId}/sets` | `summonerId` via `GET /lol-summoner/v1/current-summoner`. Le PUT remplace **toute** la liste : faire un GET, retirer uniquement le set au préfixe `"LS "`, ajouter le nouveau, puis PUT. Les sets du joueur sont préservés. |
| Sorts | `PATCH /lol-champ-select/v1/session/my-selection` `{spell1Id, spell2Id}` | Respecter l'ordre Flash existant du joueur : si Flash est déjà sur D ou F, le garder sur cette touche. |

Les formats exacts des corps de requête sont à confirmer contre le client réel pendant
l'implémentation : les champs ci-dessus sont ceux documentés par la communauté, pas par Riot.

### 3.4 Sortie console

Une ligne, en ASCII : `[OK] Build importée : Électrocution / Ahri mid (runes, items, sorts)`, ou
bien `[INFO] Build non importée : <raison>`. Rien de plus en mode normal ; le détail n'apparaît
qu'en verbose.

### 3.5 Critères d'acceptation (tests)

Hermétiques : LCU et HTTP Coachless simulés (`monkeypatch` / `unittest.mock`), sans aucun appel
réseau réel.

1. Un survol (`completed: False`) **ne déclenche pas** d'import ; le lock-in en déclenche un seul.
   Un deuxième passage dans la boucle avec le même état n'en déclenche pas de second.
2. Un trade de champion après le lock-in relance l'import.
3. **Runes** : une page `"LS …"` existante est supprimée puis recréée. Les pages sans préfixe ne
   subissent jamais de `DELETE`. Sans emplacement libre, pas d'écriture et un `[INFO]`.
4. **Items** : le PUT contient les sets du joueur à l'identique, plus un seul set `"LS …"`.
5. **Sorts** : Flash reste sur la touche où le joueur l'avait.
6. **Best-effort** : un jeton absent ou expiré (401/403), un timeout Coachless, un 500 du LCU ou
   un JSON inattendu ne lèvent aucune exception hors de `loadout.py`, et la boucle de draft
   continue.
7. Le flag `AUTO_IMPORT_LOADOUT = False` désactive tout appel.
8. Cache : deux lock-ins sur le même (champion, lane, patch) ne font qu'un seul appel Coachless.

### 3.6 Photographies par patch (collecte pour SPEC-16)

Pourquoi dès la phase 1, sans consommateur : SPEC-16 A+ a besoin de ~8 transitions de patch
d'historique (ADR-002). Un patch non photographié est **perdu définitivement**, et la collecte ne
coûte presque rien.

- **Table `build_snapshots`**, avec une migration Alembic. Granularité par **composant** (rune,
  item, sort), car c'est ce que SPEC-16 consomme : `source`, `patch`, `champion`, `lane`,
  `opponent` (NULL = toutes lanes adverses confondues), `component_type`, `component_id`, `games`,
  `winrate`, `wpa` (NULL hors Coachless), `popularity`, `collected_at`. Clé d'unicité
  `(source, patch, champion, lane, opponent, component_type, component_id)` : une seconde collecte
  sur le même patch met à jour la ligne au lieu de la dupliquer. Les colonnes exactes sont à
  ajuster aux résultats du spike.
- **Patch** : la première entrée de `https://ddragon.leagueoflegends.com/api/versions.json`,
  tronquée à `majeur.mineur`.
- **Déclenchement** : une étape best-effort de `src/pipeline.py`, après le scrape. Elle couvre
  les 283 combos (champion, lane) connus, pour Coachless et pour OneTricks (ou son repli), avec un
  débit limité (constante dans `config_constants.py`, calée sur le spike). Un échec est journalisé
  et **n'échoue pas le pipeline**.
- **Alerte d'oubli** : le pipeline est lancé manuellement. Si le patch courant n'a aucune
  photographie, `data_freshness.py` affiche un `[ALERTE]` au démarrage, pour ne pas laisser passer
  un patch en silence.
- Le module de collecte vit à part : `src/build_snapshots.py`, pas dans `loadout.py`, parce que
  l'un sert le temps réel et l'autre le pipeline.

**Tests** : idempotence (deux collectes sur le même patch = mêmes lignes) ; un échec de source ne
fait pas échouer le pipeline ; l'alerte se déclenche quand le patch courant n'a pas de
photographie ; la migration est testée en upgrade et en downgrade.

## 4. Optimisation maison

Déplacée dans [SPEC-16](SPEC-16-moteur-optimisation-builds.md) (méthode : ADR-002). Quand le moteur
sera prêt, `fetch_build` sera remplacé par un appel au moteur, sans toucher aux écritures LCU.

## 5. Fichiers touchés (phase 1)

| Fichier | Changement |
|---|---|
| `src/draft/loadout.py` (nouveau) | Fetch Coachless, cache, écritures LCU |
| `src/build_snapshots.py` (nouveau) | Collecte par patch, toutes sources |
| `src/draft/lifecycle.py` | Déclenchement au lock-in, réinitialisation |
| `src/pipeline.py` | Étape de collecte, best-effort |
| `src/data_freshness.py` | `[ALERTE]` si le patch courant n'a aucune photographie |
| `src/config_constants.py` | `AUTO_IMPORT_LOADOUT`, timeout, préfixe `"LS "`, débit de collecte |
| `alembic/versions/` | Table `build_snapshots` |
| `tests/test_loadout.py`, `tests/test_build_snapshots.py` (nouveaux) | §3.5 et §3.6 |
