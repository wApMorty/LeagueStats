# SPEC-34 — Vitrine : mode démo, captures, README et teaser

**Statut** : 🟢 Validée par @pj35 le 2026-10-15 (moteur du mode démo : approche A, pile réelle sur faux LCU) ; mode démo (tâches 163 à 165) implémenté le 2026-10-16. Reste : captures, README, teaser et clôture (166 à 170).

**Origine** : @pj35, 2026-10-15 : « Je vais bientôt commencer à présenter le projet dans mon environnement
professionnel. […] consolider la vitrine de ce projet en retravaillant le README, notamment en y intégrant des
rendus de l'UI du client, et potentiellement une vidéo en Motion Design hyper catchy avec des images de l'appli
et des animations dans tous les sens. »

**Effort** : ~4 jours, 8 tâches (163 à 170), 29 pts (§5).

---

## 1. Constat

Mesuré le 2026-10-15 (lecture du code et des fixtures, `data/db.db` ouverte en lecture seule).

- **Le README n'a aucune image** (`README.md`, 107 lignes) : badges, menu en texte, un paragraphe de 14 lignes
  pour tout le client (point 7). Aucun dossier d'images dans `docs/`.
- **Le client est une page web** : FastAPI + Jinja + htmx servis par uvicorn (`src/client/server.py`), affichés
  dans une fenêtre pywebview (`src/client/window.py`). N'importe quel navigateur peut donc les rendre, en
  particulier Firefox headless par Selenium, déjà en dépendance (`requirements.txt`) et déjà utilisé pour mesurer
  l'écran « En partie » (`scripts/measure_en_partie.py:280-327` : taille intérieure exacte, serveur sur port libre).
- **Toutes les données d'écran passent par trois jointures :**
  1. le LCU, par `LCUClient.find_lcu_credentials` et `LCUClient._make_request` (`src/lcu_client.py:73`, `:210`),
     qu'empruntent le proxy du client (`src/client/lcu_proxy.py`, liste blanche), le `DraftMonitor`
     (`src/draft_monitor.py:59`) et le `PhaseTracker` (`src/draft/phase_tracker.py:37`) ;
  2. la Live Client API (port 2999), injectable : `LiveGame(bus, get_phase, fetch=...)` (`src/client/ingame.py:120`) ;
  3. la base SQLite, dont le chemin vient de `config.DATABASE_PATH` (`src/config.py:54`). `crawl.db` en dérive
     (`src/winprob/crawl.py:185`) : rediriger la base redirige aussi la collecte.
- **Sujets du bus lus par les écrans** : `phase`, `draft`, `game`, `ingame`, `players` (`src/client/app.py:185`,
  `:477-510`), plus `game_captured` pour la bascule vers la revue (`src/coaching/capture.py:115`).
- **Des fixtures LCU anonymisées existent déjà** : `tests/fixtures/lcu_nav/` (profil, historique, collection,
  social, lobby, file) et `tests/fixtures/lcu_forms/` (sessions de ban, de pick et d'échanges, runes, skins).
  Identités relevées : `Invocateur`, `Alpha`, `Bravo`, `Joueur2` à `Joueur10`, tag `EUW`. Il n'y a aucun vrai pseudo.
- **Les écrans de coaching lisent `data/db.db`** : 125 `game_records`, 19 335 `game_metrics`, 7 `coaching_goals`,
  224 `rank_snapshots`. `raw_game` contient les Riot ID des dix joueurs, mais aucun module de coaching ne les
  affiche : un grep de `gameName|summonerName|riotId` ne trouve que `historique.py`, `profil.py`, `social.py`,
  `lobby.py` et `ingame.py`, qui tous lisent le LCU.
- **Les polices du client sont libres** (Alegreya Sans, Cormorant Garamond, Noto Sans Runic, en woff2 dans
  `src/client/static/fonts/`) et réutilisables dans la vidéo.
- **Outils disponibles** : Node v26.9.0, npx 12.0.2, ffmpeg, Pillow 12.3.0. `node_modules` est déjà ignoré par
  `.gitignore`. `docs/presentation/` n'est pas suivi : `setup-agentique.pptx` et `teaser-spec-release.mp4`.
- **Taille des fenêtres** : fenêtre par défaut de 1 280 × 800, scène de draft de 1 920 × 950
  (`src/config_client.py:24`, `:47`).

## 2. Objectif et arbitrages

**Objectif** : un README qui montre le produit en images, avec une boucle animée en tête et des captures des quatre
familles d'écrans, plus un teaser de 30 s en motion design pour la présentation pro. Tout est produit à partir d'un
mode démo rejouable, sans client League of Legends et sans vraie identité.

| Sujet | Décision |
|---|---|
| Angle du README | **Validé (@pj35, 2026-10-15)** : produit seul. La démarche agentique reste dans le PowerPoint et la vidéo existants. |
| Langue | **Validé (@pj35, 2026-10-15)** : français, pour le README comme pour les textes de la vidéo. |
| Source des captures | **Validé (@pj35, 2026-10-15)** : mode démo, aucun client LoL et aucune capture de vraie partie. |
| Données personnelles | **Validé (@pj35, 2026-10-15)** : pseudos fictifs. Champions et stats restent réalistes. Les écrans de coaching montrent les vraies stats de la copie de `db.db`, qui n'affichent aucun pseudo (§1). |
| Forme du mode démo | **Validé (@pj35, 2026-10-15)** : script séparé `scripts/demo_client.py`. Rien n'est ajouté au code de prod ni à l'exe. |
| Moteur du mode démo | **Validé (@pj35, 2026-10-15)** : pile réelle sur faux LCU (§3, approche A). |
| Écrans | **Validé (@pj35, 2026-10-15)** : draft interactive, En partie, revue et coaching, profil et historique. |
| Vidéo | **Validé (@pj35, 2026-10-15)** : Remotion (React), 30 s en 16:9, 1 920 × 1 080, muette, plus une boucle GIF pour le README. |
| Emplacement de la vidéo | **Validé (@pj35, 2026-10-15)** : `docs/presentation/video/`. Les sources sont versionnées ; `node_modules` et les rendus ne le sont pas. |
| Présentation existante | **Validé (@pj35, 2026-10-15)** : le `.pptx` et le `.mp4` de `docs/presentation/` restent hors git (`.gitignore`). |
| Échéance | **Validé (@pj35, 2026-10-15)** : aucune. Ordre : mode démo, captures, README, vidéo. |

## 3. Approches considérées

**3.1 Moteur du mode démo** (arbitré ci-dessus)

| Approche | Compromis |
|---|---|
| **A. Pile réelle sur faux LCU (retenue)** | `scripts/demo_client.py` remplace, dans son seul processus, `LCUClient.find_lcu_credentials` et `LCUClient._make_request` par un faux LCU piloté par un scénario. Il donne à `LiveGame` un `fetch` qui sert des trames générées et pointe `config.DATABASE_PATH` sur une copie temporaire de `db.db`. Le `DraftMonitor`, le recommandeur, le modèle de win chance et les transitions d'écran sont les vrais : les chiffres affichés sont réels et l'UI s'anime comme en partie, ce qui est utile pour la vidéo et pour une démo en direct. Coûts : les écritures du Live Coach (survol auto, import du loadout) arrivent au faux LCU, qui les accepte et les applique à sa session ; l'import du loadout interroge OneTricks.gg (réseau, best-effort). |
| B. Payloads factices sur le bus | Comme `scripts/measure_en_partie.py` : le script construit et publie à la main les payloads `draft`, `game`, `ingame` et `players`. C'est déterministe et sans `DraftMonitor`, mais il faut écrire et maintenir une centaine de champs par snapshot. Les chiffres sont inventés et dérivent dès qu'un payload change de forme. |
| C. Maquettes HTML figées | Écartée par @pj35 le 2026-10-15 : elles dérivent dès que l'UI évolue. |

**3.2 Captures** : Selenium et Firefox headless (retenu). Ils sont déjà en dépendance, scriptés et rejouables
après chaque évolution de l'UI ; la taille intérieure est exacte (`fenetre()` de `measure_en_partie.py`) et la
souris de @pj35 n'est jamais touchée. Écartés : les captures à la main dans la fenêtre pywebview (pas
reproductibles) et l'enregistrement vidéo de l'écran (inutile, puisque la vidéo anime des images fixes et redessine
la courbe elle-même, §4.6).

**3.3 Vidéo** : Remotion (retenu par @pj35). La vidéo est du code versionné, itérable et rendue en MP4 comme en
GIF par la même composition. Écartés : le montage ffmpeg (peu de motion) et le storyboard seul (le montage
retomberait sur @pj35).

## 4. Détail

### 4.1 `src/config_constants.py` : `DemoConfig`

```python
@dataclass
class DemoConfig:
    """Mode démo, captures et vitrine (SPEC-34). Valeurs de mise en scène, choisies sans mesure."""

    SCENE_DELAY_S: float = 2.5  # pause entre deux étapes du scénario en lecture continue
    INGAME_FRAME_STEP_S: float = 30.0  # temps de jeu simulé entre deux trames de la Live Client API
    INGAME_FRAME_PERIOD_S: float = 0.5  # temps réel entre deux trames (une partie de 30 min en ~30 s)
    CAPTURE_SIZE: Tuple[int, int] = (1920, 1080)  # taille intérieure des captures (rendu de la vidéo)
    CAPTURE_RENDER_TIMEOUT_S: float = 15.0
    CAPTURE_SETTLE_S: float = 1.0  # fin des animations CSS avant la capture
    README_IMAGE_WIDTH: int = 1280
    README_IMAGE_MAX_KB: int = 400
    HERO_GIF_MAX_KB: int = 5000


demo_config = DemoConfig()
```

### 4.2 `scripts/demo/` : données de démo (nouveau, versionné)

- `lcu/*.json` : réponses du faux LCU, une par endpoint de lecture de la liste blanche (`lcu_proxy.READS`).
  Le point de départ, ce sont les fixtures de `tests/fixtures/lcu_nav/` et `lcu_forms/`, **copiées puis
  enrichies** et non lues dans `tests/` (une fixture de test doit pouvoir changer sans casser la démo). Il faut
  un historique de 20 parties, une collection fournie et quelques amis en ligne. L'invocateur local s'appelle
  `Démo#EUW` ; les autres joueurs `Alpha`, `Bravo`… comme dans les fixtures.
- `scenario.json` : la suite des **scènes** nommées. Chaque scène fixe la phase gameflow et, selon la phase,
  la session de champ select ou l'état de la partie. Le faux LCU construit les sessions à partir de
  `lcu/session_pick.json` et d'une description compacte (cellule, champion, action, terminée ou non) : on n'écrit
  pas dix sessions complètes à la main.

  Scènes minimales, dans l'ordre : `accueil` (`None`), `profil`, `historique`, `file` (`Matchmaking`), `trouvee`
  (`ReadyCheck`), `draft-bans`, `draft-pick` (mon tour, recommandations), `draft-lock` (verrouillé, loadout),
  `chargement` (`InProgress`, temps 0, pastilles de l'éclaireur), `en-partie` (courbe sur ~25 min), `fin`
  (`EndOfGame`), `revue`, `coaching`.

  La composition de la draft se choisit dans la pool mémorisée de `user_prefs.json` (lue, jamais écrite) ; la
  tâche 164 la propose et la recette la valide sur les captures.

### 4.3 `scripts/demo_client.py` (nouveau)

```python
def start_demo(scene: Optional[str] = None, window: bool = True) -> "DemoHandle":
    """Copie `data/db.db` dans un dossier temporaire, y pointe `config.DATABASE_PATH`, remplace le LCU et la
    Live Client API par le scénario, puis lance serveur, Live Coach et `LiveGame` comme `run_client`.
    Ne lève pas : un échec s'annonce en `[ERREUR]` et le handle le dit."""

class DemoHandle:
    url: str
    def goto(self, scene: str) -> None: ...   # saute à la scène et l'y fige
    def play(self) -> None: ...               # lit le scénario en boucle, `SCENE_DELAY_S` par scène
    def stop(self) -> None: ...               # arrête tout, supprime le dossier temporaire
```

- CLI : `python scripts/demo_client.py [--scene NOM] [--sans-fenetre] [--liste]`. Sans `--scene`, le scénario
  tourne en boucle (démo en direct) ; avec `--scene`, il s'arrête sur la scène demandée. `--liste` affiche les
  scènes.
- **Isolation** (garde-fous non négociables) :
  - `data/db.db`, `data/crawl.db` et `logs/` réels ne sont jamais écrits : copie dans `tempfile.mkdtemp()`, ce
    qui donne aussi un `crawl.db` vide ;
  - aucun appel n'atteint le vrai client LoL, même s'il est ouvert. **Amendé à l'implémentation
    (2026-10-15)** : le faux LCU est servi en HTTP local (`ThreadingHTTPServer`), et seuls
    `LCUClient.find_lcu_credentials` et `live.URL` sont remplacés, pas `_make_request`. `Scout` et
    `LiveGame` figent en effet `live.fetch` comme valeur par défaut à l'import (`scout.py:296`,
    `ingame.py:122`), alors que `live.fetch` relit `live.URL` à chaque appel ;
  - port libre (`client_config.PORT` = 0), donc aucun conflit avec un vrai client ouvert ;
  - `LcuEvents` (WebSocket) n'est pas lancé : la phase vient du `PhaseTracker`.
- **Faux LCU** : la lecture renvoie la réponse de la scène courante, puis le fichier `lcu/`, sinon `None` (comme
  un client qui ne répond pas). L'écriture est acceptée : `PATCH` sur une action met à jour la session et
  `POST /lol-perks/v1/pages` est enregistré, ce qui fait apparaître le loadout. Les endpoints de fin de partie
  (`eog`) renvoient `None` : la capture de coaching ne range donc aucune partie inventée. En scène `revue`, le script
  publie lui-même `game_captured` avec la dernière partie réelle de la copie.
- **Trames de partie** : générées depuis `tests/fixtures/spike_live/allgamedata_items.json`, copié dans
  `scripts/demo/`. Le temps avance de `INGAME_FRAME_STEP_S` par trame et des événements scriptés (kills, dragons,
  tours, or) font bouger la win chance, calculée par le vrai modèle.

Tests (`tests/test_demo_client.py`, hermétiques, sans réseau ni Firefox, base factice de `conftest.py`) :
1. chaque scène de `scenario.json` produit une session que `DraftStateParser` lit sans erreur ;
2. le faux LCU renvoie `None` hors scénario et n'émet aucune requête réseau (`requests` bloqué par monkeypatch) ;
3. `PATCH` sur une action de la scène `draft-pick` met à jour la session lue ensuite ;
4. les trames générées passent par `LiveGame._read` et donnent une série croissante en temps ;
5. `start_demo` n'écrit jamais dans le chemin passé comme base réelle : son mtime reste identique.

### 4.4 `scripts/capture_screens.py` (nouveau)

- Il lance `start_demo(window=False)`, ouvre Firefox headless à la taille intérieure `CAPTURE_SIZE` (en
  reprenant `fenetre()` de `scripts/measure_en_partie.py`, déplacée dans un module commun
  `scripts/_firefox.py` et importée par les deux), puis capture pour chaque couple (scène, route) :
  `goto(scene)`, chargement de la route, attente d'un sélecteur propre à l'écran, pause de
  `CAPTURE_SETTLE_S`, puis `save_screenshot`.
- Il écrit dans `docs/images/captures/` (versionné) : `NN-<scene>.png` en pleine résolution, et
  `manifest.json` qui contient la liste des captures, la série de win chance de la scène `en-partie` et les
  chiffres clés lus dans `db_meta` et les comptes de la copie (champions, matchups par rôle, patch).
- Il dérive les images du README dans `docs/images/readme/` : largeur `README_IMAGE_WIDTH`, PNG optimisé par
  Pillow, sous `README_IMAGE_MAX_KB` chacune. Un dépassement est signalé en `[ALERTE]`.
- Il sort avec un code non nul si une capture échoue, sans laisser de processus Firefox ouvert.

Captures attendues (au moins) : draft bans, draft pick, draft verrouillée avec loadout, partie trouvée, en partie,
chargement avec pastilles, revue d'après-partie, accueil coaching, progression, profil, historique.

### 4.5 `README.md` (réécrit)

Ordre :

1. Titre, accroche d'une ligne et badges actuels.
2. La boucle GIF `docs/images/hero.gif`, sous `HERO_GIF_MAX_KB`.
3. « Ce que ça fait », en 4 blocs (draft, en partie, revue et coaching, client) : 2 à 3 lignes et une capture
   chacun ; un tableau à deux colonnes quand deux captures vont ensemble.
4. Chiffres clés (champions, matchups par rôle, tier Master+), repris du `manifest.json` et datés.
5. Démarrage, mise à jour des données, distribution, structure et prérequis, repris de l'actuel et resserrés.
   Le paragraphe de 14 lignes du point 7 du menu disparaît au profit des blocs du point 3.
6. Une ligne « Démo sans client LoL » : `python scripts/demo_client.py`.
7. L'avertissement Riot : *LeagueStats Coach n'est ni approuvé ni sponsorisé par Riot Games et ne reflète pas
   les opinions de Riot Games ni de quiconque ayant participé à la production ou à la gestion de League of
   Legends.* (texte du « Legal Jibber Jabber » de Riot, en français).

Aucune section sur la démarche agentique (§2).

### 4.6 `docs/presentation/video/` : projet Remotion (nouveau)

- `package.json` avec des versions **exactes** de `remotion`, `@remotion/cli` et `react` (la dernière 4.x
  disponible à l'implémentation), et les scripts `render` (MP4) et `gif`.
- `remotion.config.ts` : `Config.setPublicDir("../../images/captures")`, pour que les captures et le
  `manifest.json` soient lus sans copie. Les polices woff2 sont chargées depuis `src/client/static/fonts/` par
  `@font-face`, avec un chemin relatif résolu au build.
- `src/Root.tsx` déclare les compositions `Teaser` (1 920 × 1 080, 30 fps, 900 images) et `Hero` (960 × 540,
  la même scène 2 à 4 sur ~8 s). `src/scenes/*.tsx` contient une scène par fichier.
- Licence Remotion : gratuite pour un particulier ; à revérifier sur la page de licence de Remotion au moment
  de l'installation, résultat consigné dans le commit.
- `.gitignore` : `docs/presentation/*.pptx`, `docs/presentation/*.mp4` et `docs/presentation/video/out/`.

**Storyboard** (30 s, muet, textes en français, palette du client `--bg` `#030e0a` et ses accents) :

| Temps | Scène | Motion |
|---|---|---|
| 0–3 s | Accroche | Titre cinétique « Ta draft se joue avant la partie. », mot à mot, lignes hextech qui se tracent. |
| 3–9 s | Draft | Capture `draft-pick` en perspective qui se redresse, zoom sur le classement, pourcentages en compteur, n° 1 surligné. |
| 9–13 s | Verrouillage | Flash au verrouillage, puis les cartes runes, sorts et items glissent depuis la capture `draft-lock`. |
| 13–20 s | En partie | Courbe de win chance **redessinée en SVG** depuis `manifest.json` (tracé progressif, chiffre qui suit la pointe), face-à-face en arrière-plan flouté. |
| 20–25 s | Revue et coaching | Split-screen revue / progression, cartes « axes de travail » qui tombent en cascade. |
| 25–27 s | Mosaïque | Grille 3 × 2 des captures, en rotation 3D et en accélération. |
| 27–30 s | Clôture | « LeagueStats Coach », chiffres clés en compteur, URL du dépôt. |

- `Hero` → `docs/images/hero.gif` (`remotion render Hero --codec=gif --every-nth-frame=2`), versionné.
- `Teaser` → `docs/presentation/video/out/teaser.mp4`, non versionné.

## 5. Tâches

| # | Tâche | Pts | Dépend de |
|---|---|---|---|
| 163 | `DemoConfig` ; `scripts/demo/lcu/` (fixtures copiées et enrichies, `Démo#EUW`) ; `scripts/demo_client.py` : copie de la base, faux LCU des écrans Client, `--scene`, `--liste`, `--sans-fenetre` ; tests 2 et 5 (§4.3) | 3 | — |
| 164 | Scénario de draft : `scenario.json`, sessions construites par le faux LCU, écritures acceptées, `DraftMonitor` réel, scènes `file` à `draft-lock` ; tests 1 et 3 | 5 | 163 |
| 165 | Partie simulée : trames générées et `LiveGame(fetch=…)`, scènes `chargement` à `coaching`, `game_captured` sur la dernière vraie partie ; test 4 | 3 | 164 |
| 166 | `scripts/_firefox.py` (extrait de `measure_en_partie.py`), `scripts/capture_screens.py`, captures et `manifest.json`, images du README | 3 | 165 |
| 167 | `README.md` réécrit (§4.5) avec captures et avertissement Riot ; `.gitignore` de `docs/presentation/` | 2 | 166 |
| 168 | Projet Remotion : installation à versions exactes, config, polices, scènes « Accroche », « Draft », « Verrouillage » et « Clôture » | 5 | 166 |
| 169 | Scènes « En partie » (courbe SVG), « Revue et coaching » et « Mosaïque » ; composition `Hero` → `docs/images/hero.gif` branchée dans le README | 5 | 167, 168 |
| 170 | Clôture : `CHANGELOG.md`, statuts, README des specs, `docs/PROJECT_STRUCTURE.md` ; recette à l'œil de @pj35 (captures, GIF, teaser) | 3 | 169 |

## 6. Critères d'acceptation

1. `python -m pytest tests/ -v` vert, avec les 5 tests de `tests/test_demo_client.py`.
2. `python scripts/demo_client.py --liste` affiche les 13 scènes de §4.2.
3. `python scripts/demo_client.py --scene draft-pick --sans-fenetre` affiche une URL sur laquelle
   `/draft/stage` contient au moins 3 recommandations chiffrées.
4. Après `python scripts/capture_screens.py` (code de sortie 0), le hash de `data/db.db` est identique à celui
   d'avant (`certutil -hashfile data/db.db SHA256` avant et après) et `data/crawl.db` n'a pas changé de mtime.
5. `docs/images/captures/` contient au moins les 11 captures de §4.4, en 1 920 × 1 080, et un `manifest.json`
   avec une série de win chance d'au moins 20 points.
6. Aucune capture ni aucun fichier de `scripts/demo/` ne contient le Riot ID de @pj35 : un grep du `gameName`
   réel sur `scripts/demo/` et `docs/images/` ne trouve rien, et les PNG sont vérifiés à l'œil à la recette.
7. Chaque image de `docs/images/readme/` pèse moins de `README_IMAGE_MAX_KB` ; `docs/images/hero.gif` moins
   de `HERO_GIF_MAX_KB`.
8. `README.md` référence `hero.gif` et au moins 4 captures, toutes existantes (`grep -o 'docs/images/[^)]*'`
   puis `ls`), et contient l'avertissement Riot.
9. `npm run render` dans `docs/presentation/video/` produit `out/teaser.mp4`, et
   `ffprobe -show_entries format=duration:stream=width,height` donne 30 s (± 0,1), 1 920 × 1 080 et aucune piste
   audio.
10. `git status` ne montre ni `node_modules`, ni `out/`, ni le `.pptx`, ni le `.mp4` de `docs/presentation/`.
11. `CHANGELOG.md` (`[Unreleased]`), le statut de cette spec et `docs/specs/README.md` sont à jour.

**Vérification de bout en bout** : LoL fermé, `python scripts/demo_client.py` ouvre la fenêtre du client, qui
parcourt seule profil, file, partie trouvée, draft (bans, recommandations, verrouillage et loadout), chargement,
En partie (la courbe avance), revue et coaching, puis recommence. Ensuite `python scripts/capture_screens.py`,
`npm run render` et `npm run gif` régénèrent toute la vitrine.

## 7. Hors périmètre

- ❌ Section « démarche agentique » dans le README : écartée par @pj35 (§2), elle reste dans le PowerPoint.
- ❌ Bande-son et voix off : la vidéo est muette par choix (§2).
- ❌ Déclinaison verticale 9:16 et version anglaise : non demandées.
- ❌ Option `--demo` dans l'exe : le mode démo reste un script de développement (§2).
- ❌ Hébergement du MP4 (GitHub Releases, pièce jointe d'issue) : la publication est un geste de @pj35, qui
  passe par `/release` s'il le souhaite.
- ❌ Capture d'une vraie partie : tout vient du scénario (§2).
