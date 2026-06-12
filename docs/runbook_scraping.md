# 📕 Runbook — Pipeline de Scraping LoLalytics

**Créé** : 2026-06-12 (Horizon 1, ROADMAP_2026.md §3 H1.5)
**Public** : @pj35 (ou l'assistant IA) quand la mise à jour nocturne casse.

---

## 1. Vue d'Ensemble du Pipeline

`scripts/update_all.py` (Task Scheduler, ~3h du matin) :

```
1. Découverte des lanes   src/lane_discovery.py   HTTP requests (~172 GET légers)
2. Scrape matchups        src/multilane.py        Selenium Firefox headless, par lane
3. Scrape synergies       src/multilane.py        idem, bouton "Common Teammates"
4. Gate de complétude     src/data_quality.py     échec bruyant si volumétrie insuffisante
5. Recalcul scores        Assistant.calculate_global_scores()
6. Recalcul bans          Assistant.precalculate_all_custom_pool_bans()
7. Métadonnées fraîcheur  db_meta.last_update_utc (lu par l'app au lancement)
8. Notifications          Windows toast + Discord (DISCORD_WEBHOOK_URL dans .env)
```

**Logs** : `logs/update_all.log`. **Exit code** : 0 = succès complet, 1 = échec (notification envoyée).

---

## 2. Diagnostic Rapide (5 minutes)

1. **Lire la notification** (toast/Discord) — elle contient la cause et les compteurs.
2. **Consulter le log** :
   ```powershell
   Get-Content logs\update_all.log -Tail 100
   ```
3. **Vérifier la volumétrie en BD** :
   ```powershell
   python -X utf8 -c "from src.data_freshness import *; print(format_freshness_banner(get_freshness_info('data/db.db')))"
   ```
4. **Run de diagnostic** (matchups seulement, plus rapide) :
   ```powershell
   python scripts/update_all.py --skip-synergies
   ```
5. **Tester une seule page champion** : `python test_parser_single.py` (script utilitaire racine).

---

## 3. Pannes Connues et Marche à Suivre

### 3.1 Échec de la découverte des lanes (`LaneDiscoveryError`)

**Symptôme** : log `No lane distribution found in HTML for <champ>` ; champions listés
dans `discovery_failures` (ils basculent en fallback lane par défaut, lane=NULL).

**Cause probable** : LoLalytics a changé le DOM du sélecteur de lanes.

**Diagnostic** :
```powershell
# Vérifier ce que renvoie la page (la donnée est dans le HTML brut, SSR Qwik)
$r = Invoke-WebRequest "https://lolalytics.com/lol/aatrox/build/" -UserAgent "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:127.0) Gecko/20100101 Firefox/127.0" -UseBasicParsing
[regex]::Matches($r.Content, 'alt="(top|jungle|middle|bottom|support) lane"').Count   # attendu : >= 5
```

**Réparation** : ajuster `LANE_SHARE_PATTERN` dans `src/lane_discovery.py`.
Le motif attendu (2026-06-12) : `<img ... alt="top lane" ...>` suivi à <600 caractères
d'un pourcentage `75.1%`. Mettre à jour la fixture dans `tests/test_lane_discovery.py`
avec le nouveau HTML réel, vérifier que les tests échouent puis passent (test de régression).

### 3.2 Échec du parsing des matchups (0 matchups, Selenium)

**Symptôme** : `Matchup section never rendered`, ou complétude en échec avec des
champions à 0 matchups.

**Sélecteurs à vérifier** (dans l'ordre de probabilité de casse) :

| Sélecteur | Fichier | Rôle |
|---|---|---|
| `MATCHUP_ROW_BASE` (`/html/body/main/div[6]/div[1]/div[{index}]/div[2]/div`) | `config_constants.py` | lignes du carrousel matchups |
| classe `my-1` (indices 4/5/6 = delta1/delta2/pickrate) | `parser.py` | métriques d'un matchup |
| classe `text-\[9px\]` | `parser.py` | nombre de games |
| `SYNERGIES_BUTTON_XPATH` (`//span[text()='Common Teammates']/..`) | `config_constants.py` | onglet synergies |
| `MATCHUP_SCROLL_Y` (1700) | `config_constants.py` | déclenche le lazy-loading |

**Diagnostic** : lancer `python test_parser_single.py` en mode non-headless
(`HEADLESS: bool = False` temporairement) et observer la page.

### 3.3 Gate de complétude en échec (`DataCompletenessError`)

**Symptôme** : notification « Données incomplètes », exit 1, `last_update_utc` **pas** mis à jour
(c'est voulu : la fraîcheur n'avance que sur run réussi).

**Lire le rapport** : il liste les champions sous le seuil et les totaux.

- **Quelques champions à 0** → re-scrape ciblé probable demain ; vérifier leurs pages à la main
  (champion retiré ? renommage d'URL ? cf. `normalize_champion_name_for_url`).
- **Total global sous le seuil** → régression mono-lane (le scénario du 01/06) :
  vérifier que la découverte des lanes fonctionne (§3.1).
- **Faux positif après changement de méta/patch** → recalibrer les seuils dans
  `DataQualityConfig` (`src/config_constants.py`). Seuils initiaux (2026-06-12) :
  20 000 matchups, 15 000 synergies, 75 matchups/champion, 50 synergies/champion.
  Après 2 semaines de runs verts, les remonter vers ~80% de la volumétrie constatée.

### 3.4 Si Cloudflare réapparaît un jour

Le challenge CF a été retiré de LoLalytics (constat 2026-06-11, Décision A de la roadmap).
La machinerie de mitigation existe encore (jusqu'à l'Horizon 2) :

1. **Symptômes** : `CloudflareException` dans les logs, pages « Just a moment... »,
   ou la découverte HTTP renvoie HTTP 403.
2. **Mitigations encore en place** :
   - `src/cloudflare_detector.py` + attente `CLOUDFLARE_WAIT_SECONDS` (120 s)
   - `FIREFOX_PROFILE_PATH` (`config_constants.py`) : profil Firefox avec cookie
     `cf_clearance` résolu à la main — instructions détaillées dans le docstring
3. **Ne PAS** : remettre du scraping GitHub Actions (IP datacenter bannies),
   ni relancer la migration Playwright sans décision explicite (chantier archivé,
   tag `archive/playwright-migration`).
4. La découverte de lanes (requests) recevra aussi le challenge → elle échouera
   proprement et les champions passeront en fallback lane par défaut ; le scrape
   Selenium peut continuer à fonctionner si le profil cookie est configuré.

### 3.5 La tâche planifiée ne tourne plus

```powershell
Get-ScheduledTask -TaskName "LeagueStats Auto-Update" | Get-ScheduledTaskInfo
# LastRunTime / LastTaskResult (0 = OK, 0x1 = échec script, 0x41303 = jamais lancée)
```

- Recréer la tâche : `.\scripts\setup_auto_update.ps1` (en Administrateur).
- Le PC doit être **allumé** à l'heure planifiée (`-StartWhenAvailable` rattrape un réveil tardif).
- L'app affiche un bandeau `[ALERTE] DONNÉES OBSOLÈTES` après 7 jours sans run réussi —
  si vous le voyez, c'est précisément ce cas.

---

## 4. Recettes

### Re-scrape complet manuel (console visible)
```powershell
python scripts/update_all.py
```

### Re-scrape rapide sans synergies ni gate (diagnostic uniquement)
```powershell
python scripts/update_all.py --skip-synergies --skip-completeness
```

### Vérifier les lanes découvertes pour un champion
```powershell
python -c "from src.lane_discovery import *; d = fetch_lane_distribution('aatrox', '14'); print(d, select_lanes(d))"
```

### Volumétrie par lane en BD
```sql
SELECT lane, COUNT(*) FROM matchups GROUP BY lane;
SELECT COUNT(DISTINCT champion) FROM matchups;   -- attendu : 172
```

---

*Document vivant : compléter à chaque incident (cause + fix + test de régression créé).*
