# SPEC-02 ⭐ — Scraper matchups et synergies en une seule visite de page

**Item** : C1 · **Priorité** : 2 (priorisé par @pj35) · **Effort estimé** : ~1-2 jours
**Constat d'audit** : P1 (`docs/AUDIT_2026_08.md` §5)
**Prérequis** : aucun · **Bloque** : rien

---

## 1. Contexte

Le pipeline fait **deux passes complètes** sur les mêmes pages :

```
Phase 1 — matchups  : 283 couples (champion, lane)  →  24,7 min
Phase 2 — synergies : les mêmes 283 couples         →  18,1 min
                                                       ─────────
                                          run du 16/07 :  45 min
```

Or les deux jeux de données sont **sur la même page LoLalytics**. `src/parser.py` le montre :

| Méthode | URL chargée | Différence |
|---|---|---|
| `get_champion_data_on_patch(patch, champion, lane)` (l. 285) | `https://lolalytics.com/lol/{champion}/build/?lane={lane}&tier=diamond_plus&patch={patch}` | lit directement le carrousel |
| `get_champion_synergies_on_patch(patch, champion, lane)` (l. 422) | **la même URL** | clique `xpath_config.SYNERGIES_BUTTON_XPATH` (`//span[text()='Common Teammates']/..`) avant de lire |

La seconde passe repaie donc intégralement : chargement de page (~2 s), attente du rendu Qwik, bannière cookies, scroll de lazy-loading — pour ne changer qu'un onglet.

**Gain attendu** : 30 à 40 % du temps total (45 min → ~28 min) et surtout **moitié moins de requêtes** vers LoLalytics, donc moitié moins d'exposition à un blocage — ce qui compte autant que le temps, vu l'historique Cloudflare du projet (janvier-juin 2026).

---

## 2. Objectif

Une visite de page produit **les deux** jeux de données. Le pipeline passe de deux phases séquentielles à une seule, sans perdre la tolérance aux pannes actuelle : aujourd'hui, un échec de synergies n'invalide pas les matchups déjà écrits, et ce doit rester vrai.

---

## 3. Travail à faire

### 3.1 `src/parser.py` — extraire le tronc commun

Les deux méthodes partagent ~90 % de leur corps. Comparaison vérifiée :

| | `get_champion_data_on_patch` | `get_champion_synergies_on_patch` |
|---|---|---|
| Attente du premier conteneur | `WebDriverWait(...).until(presence_of_element_located(first_row_path))` + repli `scrollIntoView` sur `/html/body/main/div[6]` | **identique** |
| Boucle sur les rangs de tier | `for row_idx in range(2, 7)` (5 rangs) | `for row_idx in range(2, 6)` (4 rangs) |
| Parcours du carrousel | `scrollIntoView({block:'center'})`, boucle `while True`, `ActionChains` de défilement horizontal | **identique** |
| Extraction d'une cellule | `href.split("/lol/")[1].split("/build")[0]` → nom d'adversaire | **identique**, nom d'allié |

**À faire** :

1. Créer une méthode privée `_extract_carousel_rows(self, champion: str, row_range: range, label: str) -> List[tuple]` contenant toute la logique commune (attente, parcours des rangs, défilement horizontal, extraction, garde-fous anti-boucle infinie déjà présents depuis `40ae072`).
2. Créer `_load_champion_page(self, patch: str, champion: str, lane: Optional[str]) -> None` : construction d'URL, `webdriver.get`, délai, scroll `MATCHUP_SCROLL_Y`, `_accept_cookies()`.
3. Créer la méthode publique :

```python
def get_champion_page_data(
    self, patch: str, champion: str, lane: Optional[str] = None,
    include_synergies: bool = True,
) -> Tuple[List[tuple], List[tuple]]:
    """Charge la page une fois et renvoie (matchups, synergies).

    Renvoie ([], []) si la page ne rend jamais la section matchups.
    Renvoie (matchups, []) si l'onglet « Common Teammates » est introuvable
    ou ne charge pas : les matchups obtenus ne sont jamais perdus.
    """
```

Séquence : `_load_champion_page` → `_extract_carousel_rows(range(2, 7))` pour les matchups → clic sur `SYNERGIES_BUTTON_XPATH` → re-scroll → `_extract_carousel_rows(range(2, 6))` pour les synergies.

4. **Conserver** `get_champion_data_on_patch` et `get_champion_synergies_on_patch` comme fines enveloppes autour de la nouvelle méthode. Elles sont utilisées par `scripts/repair_data.py` (via `RepairTarget.scrape`, l. 113 et 131) et par plusieurs tests : les supprimer élargirait inutilement le périmètre.

### 3.2 `src/parallel_parser.py` — une passe au lieu de deux

Ajouter `parse_page_by_role(db, champion_list, lane, normalize_func, include_synergies=True, init_tables=False) -> dict`, symétrique de `parse_champions_by_role` (l. 525) mais qui, pour chaque champion :

- appelle une méthode de scraping avec retry `_scrape_champion_page_with_retry` (copiée sur `_scrape_champion_with_retry`, l. ~160-196 : mêmes décorateurs `@retry(stop_after_attempt(3), wait_exponential(...))`, mêmes exceptions `WebDriverException`, `TimeoutException`, `CloudflareException`, `reraise=True`) ;
- écrit les deux jeux via `_write_matchups_thread_safe` et `_write_synergies_thread_safe`, **inchangés**.

Statistiques retournées : conserver les clés `success`, `failed`, `total`, `duration`, et ajouter `synergies_missing: List[str]` (champions dont la page a rendu les matchups mais pas les synergies).

> ⚠️ **Ne pas supprimer** `parse_champions_by_role` ni `parse_synergies_by_role` : elles restent utilisées par les scripts de réparation ciblée.

### 3.3 `src/multilane.py` — fusionner les deux boucles

Actuellement (l. 113-124) :

```python
for lane, champs in groups.items():          # phase 1
    stats["matchups"][lane or "default"] = parser.parse_champions_by_role(...)
if include_synergies:
    for lane, champs in groups.items():      # phase 2
        stats["synergies"][lane or "default"] = parser.parse_synergies_by_role(...)
```

Devient une seule boucle appelant `parse_page_by_role`. Conserver **exactement** la forme du dictionnaire `stats` renvoyé (clés `lane_map`, `discovery_failures`, `pages_total`, `matchups`, `synergies`, `success`, `failed`, `total`) : il est consommé par `_format_report()` dans `scripts/update_all.py` et par les tests. `pages_total` devient le nombre de pages réellement chargées (une par couple champion/lane au lieu de deux).

Agréger `synergies_missing` au niveau du run et le remonter dans le rapport de notification.

### 3.4 Décision de conception : que faire si l'onglet synergies échoue ?

C'est le vrai point de vigilance de cette spec, et ce qui la classe en difficulté 8 plutôt que 5.

Aujourd'hui, les deux phases étant indépendantes, un échec de synergie n'a aucun effet sur les matchups. Après fusion, les deux extractions partagent un chargement de page — un échec au milieu pourrait tout emporter.

**Comportement exigé** :

| Situation | Comportement |
|---|---|
| Page ne charge pas / Cloudflare | Retry (tenacity) puis échec du champion : `failed += 1`, rien n'est écrit |
| Matchups OK, bouton « Common Teammates » introuvable | **Écrire les matchups**, `synergies = []`, ajouter le champion à `synergies_missing`, `success += 1`, log en `WARNING` |
| Matchups OK, section synergies ne rend jamais | Idem |
| Matchups vides mais page chargée | `failed += 1`, ne rien écrire (comportement actuel de `get_champion_data_on_patch`) |

Le champion listé dans `synergies_missing` est ensuite rattrapé par le mécanisme de réparation ciblée (voir SPEC-01 A4) — ne pas réimplémenter de reprise ici.

---

## 4. Critères d'acceptation

- [ ] Un run complet charge **une seule fois** chaque couple (champion, lane) : le log `parallel_parser` montre 283 chargements au lieu de 566.
- [ ] La volumétrie obtenue est équivalente à celle d'un run à deux passes (± 2 %) : ~26 000 matchups, ~21 000 synergies sur 173 champions.
- [ ] Durée mesurée d'un run complet **inférieure à 35 min** (référence : 45 min le 16/07, même machine, `DEFAULT_MAX_WORKERS = 5`).
- [ ] Un champion dont l'onglet synergies échoue conserve ses matchups en base et apparaît dans `synergies_missing`.
- [ ] `scripts/repair_data.py` fonctionne toujours à l'identique (il utilise les anciennes méthodes).
- [ ] Aucune régression sur les tests Cloudflare : `tests/test_cloudflare_detector.py` et `tests/regression/test_regression_parallel_parser_fixes.py` passent — en particulier la propagation de `CloudflareException` jusqu'au retry, qui avait déjà régressé une fois (juin 2026).
- [ ] `pytest tests/ -v` : 0 échec.

---

## 5. Tests exigés

| Fichier | Contenu |
|---|---|
| `tests/test_parser_page_data.py` (nouveau) | `get_champion_page_data` avec un WebDriver mocké : renvoie `(matchups, synergies)` ; bouton introuvable → `(matchups, [])` ; page vide → `([], [])` |
| `tests/test_parallel_parser.py` (étendu) | `parse_page_by_role` : un seul appel de chargement de page par champion (vérifié par compteur sur le mock), `synergies_missing` correctement peuplé |
| `tests/test_multilane.py` (existant) | Adapter : boucle unique, forme du dict `stats` inchangée, `pages_total` = 1 page par couple |
| `tests/regression/test_regression_synergies_partial_failure.py` (nouveau) | Un échec de l'onglet synergies **n'empêche pas** l'écriture des matchups (le risque introduit par cette spec) |
| `tests/regression/test_regression_parallel_parser_fixes.py` (existant) | Doit continuer à passer sans modification — si un ajustement est nécessaire, le justifier explicitement dans le commit |

---

## 6. Pièges connus

- **Le carrousel a des bugs historiques** corrigés en juin 2026 (`40ae072` : boucle infinie, index hors bornes, éléments périmés). En factorisant `_extract_carousel_rows`, **conserver tous les garde-fous existants** : condition d'arrêt sur `prev_count == len(result)`, `try/except NoSuchElementException` par cellule, `pickrate` décroissant comme sentinelle. Relire le corps actuel des deux méthodes ligne à ligne avant de fusionner.
- **Nombre de rangs différent** : 5 pour les matchups (`range(2, 7)`), 4 pour les synergies (`range(2, 6)`). Ce n'est pas une erreur — c'est la structure réelle du site.
- **Le clic sur le bouton** se fait sur le `<div>` parent du `<span>` (le span a `pointer-events-none`) — d'où le `/..` dans l'XPath. Ne pas « simplifier ».
- **Le state de la page après clic** : LoLalytics remplace le contenu du carrousel sans recharger. Il faut re-scroller (`MATCHUP_SCROLL_Y`) et ré-attendre le premier conteneur, sinon on relit les matchups en croyant lire les synergies. **Vérifier explicitement** que les données extraites après le clic diffèrent de celles d'avant (sur un champion de test, en manuel, avant de généraliser).
- **Un worker = un Firefox** (`thread_local`, `src/parallel_parser.py:53`). Fusionner les phases augmente la durée de vie de chaque page mais pas le nombre de navigateurs : ne pas toucher à `DEFAULT_MAX_WORKERS = 5`, calibré pour la machine (i5-14600KF).
- **Mesurer avant/après** sur le même pool et la même machine, et reporter le chiffre réel dans le CHANGELOG. Le README annonce toujours « 12 min » — un chiffre de 2025, mono-lane, 10 workers.

---

## 7. Hors périmètre

- Modification du nombre de workers ou de la stratégie anti-détection.
- Suppression des méthodes `get_champion_data_on_patch` / `get_champion_synergies_on_patch`.
- Refonte des scripts de réparation (`scripts/repair_data.py`).
- Toute optimisation des délais fixes (`PAGE_LOAD_DELAY`, `SCROLL_DELAY`) : tentant, mais c'est le genre de réglage qui a coûté des semaines au projet début 2026. À traiter séparément, avec mesures.
