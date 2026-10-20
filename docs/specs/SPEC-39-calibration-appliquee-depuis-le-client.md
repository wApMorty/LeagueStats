# SPEC-39 — Écran Calibration : diagnostic complet et « Appliquer »

**Statut** : 🟡 Rédigée le 2026-10-20, arbitrages validés par @pj35 le 2026-10-20 (§2).

**Origine** : @pj35, 2026-10-20 — « Il faudrait que l'écran calibration me propose un bouton pour exécuter
calibrate_model. »

**Effort** : ~1 jour, 3 tâches (§5).

---

## 1. Constat

Mesuré le 2026-10-20 sur le code et sur `data/db.db`.

- **L'écran recalcule déjà à chaque ouverture ce que montre le script, sauf la fin.** `calibration_view`
  (`src/client/data.py:485`) lit `fetch_labeled_predictions` et rend la courbe par décile et le Brier, les mêmes que
  `scripts/calibrate_model.py` (`tests/test_client_calibration.py` le vérifie). Il ne montre ni le facteur d'échelle
  (`suggest_scale`), ni son intervalle de confiance (`scale_interval`), ni les K suggérés : c'est la seule différence
  avec le script.
- **Le calcul complet est instantané** : `suggest_scale` + `scale_interval` (200 tirages) prennent 66 ms sur les
  159 issues de `spec13-v1`, 283 ms sur 4 fois plus. Aucun bouton n'est nécessaire pour le lancer.
- **État réel** : `spec13-v1` (la version courante, `src/config_constants.py:190`) a 159 issues sur 167
  prédictions ; facteur 0,613 (le script suggère K_MATCHUP 1,00 → 0,61, K_SYNERGY 0,50 → 0,31), mais intervalle à
  90 % de −1,17 à 2,25. `build_proposal` rend donc `None` : il exige au moins `CALIBRATION_APPLY_MIN_ROWS` = 100
  issues (`src/config_constants.py:210`) et un intervalle qui exclut 1,0 sans atteindre 0
  (`src/draft/calibration_notice.py:120`). Aucun `calibration.json` n'existe.
- **Le client ne peut pas répondre au « Appliquer ? (o/n) » du Live Coach.** Le Live Coach du client tourne en fil
  avec `console_input=False` (`src/client/launch.py:70`) ; la proposition est imprimée sur une console absente de
  l'exe, et `_pending_calibration` n'est lu que par la file de commandes console (`src/draft/commands.py:67`).
  Appliquer une calibration n'est aujourd'hui possible que dans `python lol_coach.py`.
- **Appliquer depuis le client vaut tout de suite pour son Live Coach** : `apply_proposal` écrit `calibration.json`
  puis modifie `analysis_config` en mémoire (`src/draft/calibration_notice.py:155`), et le Live Coach du client vit
  dans le même processus. Un Live Coach console déjà ouvert ne le lira qu'à son redémarrage (lecture à l'import,
  `src/config_constants.py:630`).
- **Le refus en draft ou en partie existe déjà** sur l'écran Données : `_reason` (`src/client/donnees.py:238`) lit
  la phase du bus (`bus.latest("phase")["kind"]`), la route rend 409 (`src/client/app.py:374`). Les POST du client
  passent par le jeton de session (`src/client/app.py:216`).

## 2. Objectif et arbitrages

L'écran Calibration montre le diagnostic complet de `calibrate_model.py` et permet d'appliquer le réglage proposé,
avec le même garde-fou que le Live Coach.

| Sujet | Décision |
|---|---|
| Rôle du bouton | **Validé (@pj35, 2026-10-20)** : facteur, intervalle à 90 % et K suggérés affichés d'office (pas de bouton de calcul). Un bouton « Appliquer » reprend la règle de `build_proposal` (≥ 100 issues, intervalle qui exclut 1,0 sans atteindre 0) ; il écrit `calibration.json`, passe `MODEL_VERSION` à `+calN` et vaut tout de suite pour le Live Coach du client. Grisé avec la raison sinon (aujourd'hui : « l'intervalle contient 1,0 »). |
| Draft ou partie en cours | **Validé (@pj35, 2026-10-20)** : « Appliquer » grisé en phase `draft` et `game`, avec la raison ; 409 côté serveur. Même règle que l'écran Données. |
| Retour aux K du code | **Validé (@pj35, 2026-10-20)** : pas de bouton « Rétablir » ; supprimer `calibration.json` à la main suffit. |
| Version affichée ≠ version courante | Décidé à la rédaction (découle du code) : « Appliquer » et les K suggérés seulement pour la version courante. Les K suggérés multiplient les K *en vigueur* ; sur une ancienne version ils ne voudraient rien dire. Une ancienne version garde facteur et intervalle. |

## 3. Approches considérées

1. **Bouton « Lancer » qui calcule et affiche la sortie du script** : un clic pour 66 ms de calcul que l'écran fait
   déjà en partie à chaque ouverture ; n'apporte pas l'application. Écarté.
2. **Diagnostic affiché d'office + « Appliquer » sur la règle de `build_proposal`** (retenu) : réutilise
   `calibration_notice` tel quel, aucune règle nouvelle, comble le seul manque réel (pas d'o/n possible dans le
   client).
3. **Répondre au « o/n » du Live Coach depuis le client** (envoyer `o` par `LiveCoachThread.send`) : ne marche que si
   le Live Coach vient de franchir un seuil dans cette session ; la proposition n'existe pas le reste du temps. Écarté.

## 4. Détail

### 4.1 Diagnostic partagé (`src/draft/calibration_notice.py`)

`build_proposal(db, model_version)` lit les lignes puis appelle une nouvelle fonction pure qui fait le travail, pour
que l'écran ne refasse pas le bootstrap deux fois :

```python
@dataclass(frozen=True)
class Diagnostic:
    n: int
    scale: float
    low: float
    high: float
    proposal: Optional[Proposal]   # None : voir refusal
    refusal: Optional[str]         # raison en français, None si proposal

def diagnose(rows: List[Row], model_version: str) -> Diagnostic:
    """Facteur, intervalle et proposition (règle de build_proposal) sur des lignes déjà lues."""
```

Raisons, dans cet ordre : `"{n} issues sur {CALIBRATION_APPLY_MIN_ROWS} nécessaires"`,
`"L'intervalle atteint 0 : les prédictions ne séparent pas les victoires des défaites"`,
`"L'intervalle contient 1,0 : un réglage ajusterait du bruit"`. `build_proposal` devient
`diagnose(rows, model_version).proposal` ; son comportement ne change pas (tests existants de
`tests/test_calibration_apply.py` inchangés). Sous `MIN_ROWS_FOR_CALIBRATION`, `diagnose` n'est pas appelée (l'écran
refuse déjà, `src/client/data.py:513`).

### 4.2 Vue (`src/client/data.py`)

`calibration_view(repo, version, phase_kind="closed")` ajoute, quand `enough` :

- `scale` (`fr(scale, 3)`), `interval` (`"[−1,17 ; 2,25]"`, niveau `CALIBRATION_CI_CONFIDENCE` affiché « à 90 % »),
  `verdict` : « plus prudent » / « plus confiant » / « proche de 1, K raisonnables » / « aucun signal » (mêmes seuils
  que `format_summary` : `scale <= 0`, `abs(scale - 1) < 0.05`) ;
- pour la version courante seulement : `suggested` = `{"k_matchup": "1,00 → 0,61", "k_synergy": "0,50 → 0,31",
  "version": "spec13-v1 → spec13-v1+cal1"}` ;
- `can_apply` (bool) et `apply_reason` (str ou None) : la première raison parmi version non courante (« Seule la
  version courante {current} se règle »), `phase_reason(phase_kind)`, `Diagnostic.refusal`.

Dans `src/client/donnees.py`, la partie phase de `_reason` devient une fonction publique
`phase_reason(phase_kind: str) -> Optional[str]` réutilisée par les deux écrans (`_reason` l'appelle).

### 4.3 Route et gabarit (`src/client/app.py`, `src/client/templates/calibration.html`)

- `GET /calibration` passe la phase du bus (`(bus.latest("phase") or {}).get("kind", "closed")`, comme
  `donnees_body`).
- `POST /calibration/appliquer` : relit la vue de la version courante en lecture seule ; `can_apply` faux → 409 et
  la vue (bouton grisé, raison) ; sinon `calibration_notice.apply_proposal(diagnostic.proposal)`. Échec d'écriture
  → 500 et message « Écriture de calibration.json impossible, rien n'est modifié ». Succès → la vue rechargée avec
  `message` : « Réglage appliqué : K_MATCHUP 1,00 → 0,61, K_SYNERGY 0,50 → 0,31, version spec13-v1+cal1. Un Live
  Coach ouvert en console ne le verra qu'à son redémarrage. » La réponse remplace `#calib` (htmx, `hx-select`
  comme les puces de version).
- Gabarit : dans la colonne latérale, sous le Brier, un bloc « Facteur d'échelle » (facteur, intervalle, verdict,
  K suggérés) puis le bouton `<button hx-post="/calibration/appliquer" …>Appliquer</button>`, `disabled
  title="{{ v.apply_reason }}"` et la raison en clair sous le bouton quand `not v.can_apply`. Styles dans
  `src/client/static/style.css` sur les classes existantes (`sample`, `fine`) ; aucune nouvelle couleur.

Aucune constante nouvelle (seuils déjà dans `analysis_config`), aucune migration.

### 4.4 Tests (`tests/test_client_calibration.py`, `tests/test_calibration_apply.py`)

Hermétiques : `calibration_overrides.get_calibration_path` monkeypatché vers `tmp_path`, `analysis_config`
restauré après chaque test (K et `MODEL_VERSION`), base de `conftest.py`, bus factice pour la phase.

- `diagnose` : moins de 100 issues, intervalle contenant 1, intervalle atteignant 0, proposition (lignes
  `_rows(n, slope)` de `test_calibration_apply.py`) ; `build_proposal` rend la même chose qu'avant.
- Vue : facteur et intervalle égaux à `suggest_scale` / `scale_interval` ; K suggérés absents pour une ancienne
  version ; raisons de `can_apply` (version, draft, partie, refus du diagnostic).
- Route : 409 en draft, 409 quand l'intervalle contient 1 (fichier non écrit), 403 sans jeton, succès qui écrit
  `calibration.json` avec les K proposés et `+cal1`, et modifie `analysis_config`.

## 5. Tâches

| # | Tâche | Pts | Dépend de |
|---|---|---|---|
| 191 | `Diagnostic` et `diagnose()` dans `calibration_notice.py`, `build_proposal` qui s'appuie dessus ; `phase_reason` dans `donnees.py` ; champs de `calibration_view` ; tests | 3 | — |
| 192 | Route `POST /calibration/appliquer`, phase dans `GET /calibration`, gabarit et CSS ; tests de route | 3 | 191 |
| 193 | Clôture : `CHANGELOG.md`, statuts, README des specs, recette @pj35 | 1 | 192 |

## 6. Critères d'acceptation

1. `python -m pytest tests/ -v` vert, avec les tests des tâches 191 et 192.
2. `python -m pytest tests/test_calibration_apply.py -v` vert sans modification des tests existants (comportement de
   `build_proposal` inchangé).
3. Sur `data/db.db` du 2026-10-20 (copie), `calibration_view` de `spec13-v1` rend un facteur `0,613`, un intervalle
   `[−1,17 ; 2,25]`, `can_apply` faux avec la raison « L'intervalle contient 1,0 ».
4. `POST /calibration/appliquer` rend 409 en phase `draft` et `game`, et quand `can_apply` est faux ; aucun
   `calibration.json` n'est écrit dans ces cas (test).
5. Un succès écrit `calibration.json` (`K_MATCHUP`, `K_SYNERGY` = K × facteur, `MODEL_VERSION` = `+cal1`) et
   modifie `analysis_config` du processus (test).
6. Une ancienne version affichée montre facteur et intervalle, sans K suggérés, avec « Appliquer » grisé (test).
7. `grep -n "f\"SELECT\|f'SELECT" src/draft/calibration_notice.py src/client/data.py` : rien ; aucune émoji dans les
   sorties console ajoutées.
8. `CHANGELOG.md` (`[Unreleased]`), statut de cette spec et `docs/specs/README.md` à jour.

**Vérification de bout en bout** : `python lol_coach.py` → client → Calibration : facteur 0,613, intervalle de −1,17
à 2,25, bouton « Appliquer » grisé avec « L'intervalle contient 1,0 ». Le chemin d'application (écriture de
`calibration.json`, à la racine du dépôt ou à côté de l'exe, `src/pool_manager.py:37`) n'est prouvé que par le
critère 5 tant que les vraies données ne justifient pas de réglage : le provoquer sur `data/db.db` changerait le
modèle réel.

## 7. Hors périmètre

- ❌ Bouton « Rétablir » (suppression de `calibration.json`) : refusé par @pj35 le 2026-10-20, à rouvrir le jour où
  un réglage appliqué serait regretté.
- ❌ Option `--all-versions` du script à l'écran : mélanger les versions rend la calibration sans objet (SPEC-05 §7) ;
  le script la garde pour compter les lignes.
- ❌ Réglage séparé de K_MATCHUP et K_SYNERGY : la probabilité stockée ne permet pas de séparer les deux
  contributions (`scripts/calibrate_model.py:101`), la mise à l'échelle reste uniforme.
- ❌ Suppression du « o/n » console du Live Coach : il reste le chemin de `python lol_coach.py`.
