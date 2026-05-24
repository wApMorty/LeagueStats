# ADR-018 : Migration Selenium → Playwright + playwright-stealth

**Date** : 2026-05-24  
**Statut** : Accepté  
**Décideur** : @pj35  
**Tâche associée** : TODO #18

---

## Contexte

Depuis mai 2026, LoLalytics a durci sa configuration Cloudflare. Le site présente
désormais un **Managed Challenge** (Cloudflare Turnstile) au lieu du simple JS
auto-challenge (IUAM) qui se résolvait automatiquement en 5-15 secondes.

### Symptômes observés

- En mode headless : CF détecte Firefox via `navigator.webdriver` exposé par
  geckodriver malgré `dom.webdriver.enabled = False` → challenge infini
- En mode GUI avec 5 workers parallèles : 5 challenges simultanés impossibles à
  résoudre manuellement, tous timeout à 30 s
- En mode GUI avec 1 worker : le clic manuel sur "Verify" déclenche un refresh et
  un nouveau challenge → Cloudflare détecte des signaux d'automatisation
  supplémentaires (canvas fingerprint, WebGL renderer, plugins absents)

### Cause racine

`geckodriver` (driver Selenium pour Firefox) expose plusieurs signaux détectables
que `playwright-stealth` avec Chromium masque nativement :

| Signal | Selenium Firefox | Playwright + stealth |
|--------|-----------------|----------------------|
| `navigator.webdriver` | `true` (geckodriver) | `undefined` (patché) |
| Canvas fingerprint | automation-mode | réaliste |
| WebGL renderer | SwiftShader/llvmpipe (headless) | GPU réaliste |
| `navigator.plugins` | vide | réaliste |
| `window.chrome` | absent | présent |
| `navigator.permissions` | Notification denied | réaliste |
| TLS JA3 fingerprint | geckodriver signature | Chrome standard |

---

## Décision

Migrer de **Selenium 4.x + Firefox + geckodriver** vers
**Playwright 1.40+ + Chromium + playwright-stealth**.

**Raison du choix Playwright vs alternatives :**

| Option | CF Bypass | Stabilité | Documentation | Effort migration |
|--------|-----------|-----------|---------------|-----------------|
| Playwright + stealth | ✅ Bon | ✅ Mature | ✅ Excellente | Moyen |
| nodriver | ✅ Excellent | ⚠️ Instable | ⚠️ Limitée | Élevé |
| DrissionPage | ✅ Bon | ⚠️ Moyen | ❌ Chinois | Élevé |
| Selenium patchs | ❌ Insuffisant | ✅ Mature | N/A | Faible |

---

## Conséquences

### Positives
- `playwright-stealth` masque nativement les signaux CF détectés
- API moderne : `locators` > `find_elements`, `wait_for_selector` > `WebDriverWait`
- Sessions persistantes via `storage_state.json` pour réutiliser `cf_clearance`
- Meilleure gestion des SPA React/Next.js (interception réseau, auto-wait)
- `--disable-blink-features=AutomationControlled` au niveau engine Chrome

### Négatives
- **Chromium remplace Firefox** (fingerprint différent — acceptable car Chromium
  est plus répandu et moins suspect que Firefox automation)
- **Réécriture de `src/parser.py`** (~400 lignes — seul fichier à refactorer
  entièrement, le reste du projet conserve son API)
- **Nouveau binaire système** : `playwright install chromium` (~150 MB Chrome)
- **Tests mocks** : adapter propriétés Selenium → méthodes Playwright

### API publique de `Parser` : inchangée

Les signatures publiques suivantes sont **préservées** :
```python
Parser(headless: bool = False)
Parser.close() -> None
Parser.get_champion_data(champion, lane) -> List[tuple]
Parser.get_champion_data_on_patch(patch, champion, lane) -> List[tuple]
Parser.get_champion_synergies(champion, lane) -> List[tuple]
Parser.get_champion_synergies_on_patch(patch, champion, lane) -> List[tuple]
Parser.get_matchup_data(champion, enemy) -> float
Parser.get_matchup_data_on_patch(patch, champion, enemy) -> tuple
```

`parallel_parser.py`, `repair_matchups.py`, `parallel_parser.py` et les callers
amont **ne nécessitent aucun changement** sauf le remplacement des imports
d'exceptions Selenium → Playwright.

---

## Fichiers impactés

| Fichier | Type de changement |
|---------|--------------------|
| `src/parser.py` | Réécriture complète |
| `src/cloudflare_detector.py` | Type hint + API (driver → page) |
| `src/parallel_parser.py` | Import exceptions uniquement |
| `src/config_constants.py` | Ajout `PLAYWRIGHT_STORAGE_STATE_PATH` |
| `requirements.txt` | `playwright`, `playwright-stealth` ; retrait `selenium` |
| `tests/test_cloudflare_detector.py` | Mocks Selenium → Playwright |
| `tests/regression/test_regression_cloudflare_*.py` | Mocks |

---

## Mapping API Selenium → Playwright

| Selenium | Playwright |
|---------|-----------|
| `webdriver.Firefox(options)` | `playwright.chromium.launch(...)` |
| `driver.get(url)` | `page.goto(url)` |
| `driver.title` | `page.title()` |
| `driver.current_url` | `page.url` |
| `driver.page_source` | `page.content()` |
| `driver.find_element(By.ID, x)` | `page.query_selector(f'#{x}')` |
| `driver.find_elements(By.XPATH, x)` | `page.query_selector_all(f'xpath={x}')` |
| `elem.get_attribute("innerHTML")` | `elem.inner_html()` |
| `elem.get_dom_attribute("href")` | `elem.get_attribute("href")` |
| `WebDriverWait(d, t).until(cond)` | `page.wait_for_selector(sel, timeout=t*1000)` |
| `driver.execute_script(js)` | `page.evaluate(js)` |
| `ActionChains.move_to_element_with_offset` | `page.mouse.move(x, y)` |
| `ActionChains.click_and_hold().move_by_offset` | `page.mouse.down(); page.mouse.move(...)` |
| `NoSuchElementException` | `query_selector` retourne `None` |
| `TimeoutException` | `playwright.sync_api.TimeoutError` |
| `WebDriverException` | `playwright.sync_api.Error` |

---

## Stratégie de déploiement

1. Feature branch `feature/playwright-migration`
2. Implémenter et faire tourner les tests → tout vert
3. Tester manuellement `repair_matchups.py` sur 1 champion
4. Valider sur 5 champions avec `--max-workers 5`
5. PR + merge
