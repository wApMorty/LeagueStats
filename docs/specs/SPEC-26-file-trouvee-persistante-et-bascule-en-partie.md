# SPEC-26 — Partie trouvée persistante et bascule vers « En partie »

**Statut** : 🟡 Rédigée le 2026-10-08 ; écran cible et déclencheur de la bascule validés par @pj35 (§2), trois
réglages marqués « à valider ».

**Origine** : @pj35, 2026-10-08 : « l'animation d'Acceptation quand je trouve une game est complètement buggée
dès lors qu'on a cliqué sur Accepter. Il faudrait qu'elle persiste à l'écran jusqu'à ce que je me retrouve en
draft. De même, une fois la draft terminée, j'aimerais que l'application switch sur l'analyse de game
automatiquement. »

**Effort** : ~0,5 jour, 3 tâches (§5, 10 pts).

---

## 1. Constat

Lecture de `src/client/static/found.js` (commit `c8e5618`), 2026-10-08. Rien n'a été rejoué contre un vrai
client : la cause est établie à la lecture, et la tâche 119 la confirme par un test rouge avant le correctif.

- **L'overlay se referme avant la fin de la file.** `acceptedSequence` (`found.js:124-156`) joue l'explosion,
  puis 1 200 ms plus tard fait disparaître l'overlay (`close()`, `found.js:115-121`, qui remet `overlay` à
  `null`). Or, tant que les autres joueurs n'ont pas tous accepté, la phase reste `ReadyCheck` et le
  ready-check reste `InProgress` : j'ai accepté, pas eux.
- **Il se rouvre aussitôt, en entier.** `apply` (`found.js:181-197`) calcule `found` = phase `ReadyCheck` et
  état `InProgress` et réponse différente de `Declined` ; avec `found` vrai et pas d'overlay, il rappelle
  `show` (`found.js:187`) : les boutons « Accepter » et « Refuser » reviennent, 90 runes convergent, pilier,
  impact et explosion sont rejoués. Le rafraîchissement suivant voit la réponse `Accepted` et rejoue la
  séquence d'acceptation (`found.js:188`). La boucle dure jusqu'à l'arrivée du champ select (rafraîchissement
  à chaque événement du LCU, et toutes les 4 s). C'est ce que @pj35 voit : une animation « complètement
  buggée » après le clic. Le correctif `c8e5618` n'a traité que le refus (« refus sans réouverture »).
- **L'overlay accepté ne sait pas partir.** `leave` (`found.js:171-172`) sort aussitôt si `overlay.accepted` ;
  si un autre joueur refuse après mon acceptation (la phase retombe à `Matchmaking`), rien n'est prévu.
- **La navigation vers la draft dépend d'un délai** (`expectDraft`, 20 s codé en dur dans `found.js:7`, réglage
  hors `config`) et ne part que si l'overlay est déjà fermé (`found.js:193`).
- **Aucune bascule à la fin de la draft.** Seul un clic sur la pastille de phase ouvre « En partie »
  (`base.html:40`). C'était voulu : SPEC-24 §2 (« sans bascule automatique de page », ligne 108) et §7
  (ligne 448, « à rouvrir après usage »), SPEC-25 §7 (ligne 271). `test_aucune_bascule_automatique_de_page`
  (`tests/test_client_en_partie.py:135`) ne regarde que `en_partie.js`.
- **L'analyse est prête avant `GameStart`.** `FinalAnalysis` est publiée dès que les 10 champions sont
  verrouillés (`src/draft/lifecycle.py:126-127`, `224-240`), pendant la phase de finalisation, avant que la
  phase `ChampSelect` ne devienne `GameStart`. Le tracker publie `{phase, kind, since}` sur le sujet `phase`
  (`src/draft/phase_tracker.py:128`) ; `PHASE_KINDS` range `ChampSelect` dans `draft` et `GameStart`,
  `InProgress`, `Reconnect` dans `game` (`src/config_constants.py:399-412`).

## 2. Objectif et arbitrages

Après « Accepter », l'overlay reste à l'écran jusqu'à l'ouverture de la draft, sans rejouer la séquence ni
rouvrir les boutons ; quand la draft se termine et que la partie démarre, le client passe tout seul sur
« En partie ».

| Sujet | Décision |
|---|---|
| Cause du bug d'animation | **Défaut proposé** : réouverture de l'overlay par `apply` tant que le ready-check est `InProgress` (§1). Confirmée par le test rouge de la tâche 119 ; si le test passe avant correctif, on s'arrête et on relève la forme réelle du ready-check. |
| Fin de l'overlay accepté | **Validé par la demande (@pj35, 2026-10-08)** : il persiste jusqu'à l'arrivée en draft (phase `ChampSelect`), puis s'efface en laissant la draft déjà ouverte dessous. |
| Si la file échoue après mon acceptation | **Défaut proposé** : l'overlay s'efface avec un message d'une ligne (« Un joueur n'a pas accepté · retour en file ») quand la phase quitte `ReadyCheck` autrement que vers `ChampSelect`, ou quand le client LoL se ferme. |
| Garde-fou de durée | **À valider** : l'overlay accepté s'efface seul après `FOUND_HOLD_MAX_S` = 30 s (un ready-check dure ~10 s, le champ select suit immédiatement) pour ne jamais couvrir l'application si la phase n'arrive pas. |
| Contenu pendant l'attente | **À valider** : titre « Acceptée », sous-titre « En attente des autres joueurs », anneaux à vitesse ambiante (le ×9 de l'explosion retombe), pas de compte à rebours (le décompte de 10 s ne dit plus rien de ce qui reste). |
| Écran de la bascule | **Validé (@pj35, 2026-10-08)** : « En partie » (`/en-partie`), qui porte l'analyse de la draft (`FinalAnalysis`), le plan de build et la win chance. |
| Déclencheur de la bascule | **Validé (@pj35, 2026-10-08)** : toujours, depuis n'importe quelle page du client, au passage de la famille de phase `draft` à `game` (`ChampSelect` vers `GameStart`). Pas à l'instant des 10 picks verrouillés : la finalisation (runes, sorts, skin) se fait encore sur l'écran Draft. Un dodge (`ChampSelect` vers `Matchmaking`), une reconnexion (`game` vers `game`) et un client ouvert en pleine partie ne basculent pas. |
| Réglage pour couper la bascule | **À valider** : aucun (outil mono-utilisateur, demande explicite). À ajouter à `user_prefs` si la bascule gêne à l'usage. |
| Rouvre des décisions | SPEC-24 §2 (« Ouverture de l'écran ») et §7, SPEC-25 §7 : la pastille continue d'informer sans naviguer, seule la transition draft vers partie navigue. Actés à la tâche 121. |

## 3. Approches considérées

**Persistance de l'overlay accepté**

- ❌ **Garde temporelle** (ignorer les états `found` pendant N secondes après l'acceptation) : la durée d'un
  ready-check n'est pas garantie, et elle ne règle ni l'échec de la file ni la sortie vers la draft.
- ❌ **Calculer l'étape côté serveur** (`/found/state` renvoie `asking | accepted | draft`) : la décision
  « l'overlay existe-t-il, est-il déjà accepté » reste dans le navigateur ; on déplacerait la table sans
  supprimer le besoin de mémoire côté JS.
- ✅ **Table de décision pilotée par la phase** (§4.1) : l'overlay a trois états (`asking`, `held`,
  `entering`) ; une fois accepté, il ne dépend plus du détail du ready-check (dont la forme après acceptation
  n'a jamais été relevée) mais de la phase du client : tenir pendant `ReadyCheck`, entrer en draft à
  `ChampSelect`, partir sinon.

**Bascule vers « En partie »**

- ❌ **Dans `en_partie.js`** : le script ne tourne que sur sa page, et `test_aucune_bascule_automatique_de_page`
  l'interdit.
- ❌ **Le serveur ordonne la navigation** (événement `navigate` sur le bus) : un nouveau canal pour une
  information que le sujet `phase` porte déjà.
- ✅ **`found.js` écoute le sujet `phase`** (déjà sur toutes les pages, comme la pastille) et navigue par la
  transition signature (`Transition.go`, exposée par `transition.js`).

## 4. Détail

### 4.1 Overlay de la partie trouvée (`src/client/static/found.js`)

États de l'overlay : `asking` (boutons, compte à rebours), `held` (accepté, en attente), `entering`
(effondrement vers la draft). `expectDraft` et `EXPECT_DRAFT_MS` disparaissent. Table de décision de `apply`,
évaluée à chaque état lu :

| Overlay | État lu | Action |
|---|---|---|
| absent | `ReadyCheck`, `InProgress`, réponse `None` | `show` (boutons) |
| absent | `ReadyCheck`, réponse `Accepted` (auto-accept du Live Coach, ou page ouverte après l'acceptation) | `show` puis séquence d'acceptation une fois, puis `held` |
| absent | `ReadyCheck` et réponse `Declined`, ou toute autre phase | rien |
| `asking` | réponse `Accepted` | séquence d'acceptation une fois, puis `held` |
| `asking` | `ChampSelect` | séquence d'acceptation (le Live Coach a accepté avant nous), puis `entering` |
| `asking` | plus de ready-check (`Matchmaking`, `Lobby`, `None`, client fermé) | `leave` (existant) |
| `held` | phase `ReadyCheck`, **quel que soit** `ready_check` (`null` compris, `state` autre que `InProgress` compris) | tenir, ne rien rejouer |
| `held` | `ChampSelect` | `entering` |
| `held` | toute autre phase, ou client fermé | `leave` avec message |
| `held` | durée depuis l'acceptation > `hold_max` | `leave` avec message |
| `entering` | tout | ignorer (une seule entrée) |

- `acceptedSequence` ne se rejoue jamais (garde `overlay.accepted`, conservée) et ne ferme plus l'overlay :
  après l'impact et l'explosion elle passe à `held`, rend aux anneaux leur vitesse (`playbackRate` revient à 1),
  masque les boutons et le décompte, affiche « Acceptée » et « En attente des autres joueurs ».
- `entering` : `goDraft()` charge `/draft` sous l'overlay, puis l'effondrement existant (rotation, fondu,
  `brightness`) démarre au `htmx:load` de `#view` ou après `enter_wait` secondes au plus ; l'overlay se retire
  à la fin de l'animation. En mode Réduit : navigation puis retrait immédiats.
- `leave` (refus, esquive, expiration) accepte un message optionnel affiché avant le fondu (400 ms existants) ;
  pour un overlay `held` le message vaut « Un joueur n'a pas accepté · retour en file ».
- `goDraft` n'est appelé que par l'entrée en draft de l'overlay et par le clic sur la pastille `#tb-center`
  (existant). Une draft qui s'ouvre sans overlay (refus, ou overlay déjà parti) ne navigue pas toute seule.

### 4.2 Constantes et état serveur

`src/config_client.py` (`client_config`), à côté de `FOUND_SECONDS` :

| Constante | Valeur | Origine |
|---|---|---|
| `FOUND_HOLD_MAX_S` | 30.0 | trois fois la fenêtre de réponse (`FOUND_SECONDS` = 10 s) ; **à valider** |
| `FOUND_ENTER_WAIT_S` | 1.5 | marge pour le chargement de `/draft` sous l'overlay (serveur local ; durée non mesurée) ; **à valider** |

`src/client/found.py` : `state()` ajoute `"hold_max": client_config.FOUND_HOLD_MAX_S` et
`"enter_wait": client_config.FOUND_ENTER_WAIT_S` à sa réponse ; rien d'autre ne change côté serveur (liste
blanche du LCU inchangée : aucune écriture nouvelle).

### 4.3 Bascule vers « En partie »

- `src/client/static/transition.js` : exposer `window.Transition = { go }` (la fonction `go(path)` existe,
  `transition.js:43-47`, et garde déjà le veil signature ; en mode Réduit elle reste un simple remplacement).
- `src/client/static/found.js` : `Sse.open("phase", …)` mémorise la famille précédente (`kind`) en mémoire de page ;
  sur `draft` puis `game` appelle `Transition.go("/en-partie")` (ou `htmx.ajax` si `Transition` est absent, par
  sécurité). Première charge de page ou premier événement vu : aucune bascule (pas d'arrachage d'une page
  ouverte en cours de partie). Si l'utilisateur est déjà sur `/en-partie`, rien à faire.
- `en_partie.js`, `en_partie.py` et les gabarits ne changent pas : l'analyse est déjà publiée (`game`) quand la
  page se charge (§1), et `test_aucune_bascule_automatique_de_page` reste vrai.

### 4.4 Tests

Banc commun `tests/support_found_js.py` (modèle : `tests/support_lcu_nav.py` et le harnais `node` de
`tests/test_client_transition.py`) : exécute le vrai `found.js` sous `node` avec `document`, `Motion`, `htmx`,
`Sse` et `fetch` factices ; une liste d'étapes (état `/found/state` à servir, événement `phase`, clic sur
« Accepter », avance de l'horloge) ; renvoie les compteurs (overlays créés, séquences d'acceptation, boutons
visibles, `goDraft`, `Transition.go`, overlay encore présent). Les tests sautent si `node` est absent (comme
les existants).

- `tests/regression/test_regression_found_overlay_reopens.py` (4 points en docstring) : la suite d'états
  « ReadyCheck sans réponse, clic, `Accepted` × 4, `ChampSelect` » ne crée **qu'un** overlay, ne rejoue qu'une
  séquence d'acceptation, garde l'overlay présent et sans boutons pendant `Accepted`, navigue vers `/draft`
  une fois, puis retire l'overlay. **Rouge avant le correctif.**
- `tests/test_client_found.py` : `hold_max` et `enter_wait` dans `/found/state` ; échec après acceptation
  (`Accepted` puis `Matchmaking`) : message, retrait, aucune navigation ; `ready_check` à `null` ou autre
  état pendant `ReadyCheck` accepté : tenu ; garde-fou `hold_max` ; auto-accept (réponse `Accepted` dès le
  premier état) : un overlay, une séquence ; mode Réduit.
- `tests/test_client_game_switch.py` : `draft` vers `game` appelle `Transition.go("/en-partie")` une fois,
  depuis `/draft` comme depuis une autre page ; aucun appel pour `game` vers `game`, `draft` vers `queue`,
  un premier événement `game`, ni quand la page est déjà `/en-partie`.

## 5. Tâches

Numéros globaux : à la suite de la tâche 118 du `TODO.md`.

| # | Tâche | Pts | Dépend de |
|---|---|---|---|
| 119 | Banc `support_found_js.py`, régression rouge puis table de décision de l'overlay (`asking` / `held` / `entering`), `hold_max` et `enter_wait`, tests de `test_client_found.py` | 5 | — |
| 120 | Bascule vers « En partie » : `Transition.go` exposé, écoute du sujet `phase` dans `found.js`, `tests/test_client_game_switch.py` | 3 | 119 |
| 121 | Clôture : SPEC-24 §2 / §7 et SPEC-25 §7 rouverts, `CHANGELOG.md`, `TODO.md`, README des specs, statut | 2 | 119, 120 |

## 6. Critères d'acceptation

1. `python -m pytest tests/ -v` vert.
2. `python -m pytest tests/regression/test_regression_found_overlay_reopens.py -v` vert ; le même test, lancé
   sur `found.js` d'avant la tâche 119 (`git stash` du seul fichier), est rouge : plus d'un overlay créé.
3. Suite « `None`, clic, `Accepted` × 4 » : un seul overlay dans le DOM, une seule séquence d'acceptation, les
   boutons « Accepter » et « Refuser » masqués dès l'acceptation.
4. Pendant `ReadyCheck` accepté, un `ready_check` à `null` ou à un état autre que `InProgress` ne referme pas
   l'overlay (test `held` tenu).
5. `Accepted` puis `Matchmaking` : l'overlay s'efface avec « Un joueur n'a pas accepté », sans navigation.
6. `Accepted` puis 31 s sans changement de phase : l'overlay s'efface (`hold_max`).
7. `Accepted` puis `ChampSelect` : navigation vers `/draft` une fois, overlay retiré après l'effondrement ;
   en mode Réduit, sans animation.
8. `GET /found/state` contient `hold_max` et `enter_wait` égaux à `client_config.FOUND_HOLD_MAX_S` et
   `FOUND_ENTER_WAIT_S`.
9. Événements `phase` : `draft` puis `game` provoque un seul `Transition.go("/en-partie")` depuis `/draft` et
   depuis `/historique` ; `game` puis `game`, `draft` puis `queue`, un premier événement `game` et la page
   `/en-partie` déjà ouverte n'en provoquent aucun.
10. `grep -n "pushState\|htmx.ajax\|location" src/client/static/en_partie.js` ne renvoie rien
    (`test_aucune_bascule_automatique_de_page` vert, `en_partie.js` inchangé).
11. `node --check` passe sur `found.js` et `transition.js` ; aucune écriture nouvelle dans la liste blanche de
    `LcuProxy` (`test_liste_blanche_n_ouvre_que_accepter_et_refuser` vert).
12. `CHANGELOG.md` (`[Unreleased]`, une entrée Fix et une Feature), statut de cette spec, SPEC-24 §2 / §7,
    SPEC-25 §7 et `docs/specs/README.md` à jour.

**Vérification de bout en bout** (recette @pj35, le rendu d'une animation ne se prouve pas par un test) : lancer
le client avec le Live Coach, trouver une partie classée, cliquer « Accepter » : l'overlay reste sur
« Acceptée · En attente des autres joueurs » sans se rejouer ni rouvrir les boutons, puis s'efface sur la draft
déjà ouverte. Verrouiller les 10 champions, attendre le chargement : le client bascule sur « En partie » avec
l'analyse de la draft, depuis l'écran Draft puis depuis une autre page. À relever au passage : la valeur de
`playerResponse` et de `state` du ready-check après acceptation (`/lol-matchmaking/v1/ready-check`), jamais
relevée ; la table de décision ne s'appuie dessus que pour détecter l'acceptation d'un tiers (auto-accept).

## 7. Hors périmètre

- ❌ **Réglage pour désactiver la bascule** : demande explicite, outil mono-utilisateur ; à ajouter à
  `user_prefs` si elle gêne.
- ❌ **Bascule à l'instant des 10 picks verrouillés** : la finalisation (runes, sorts, skin) se joue encore sur
  l'écran Draft ; validé à `GameStart` (§2).
- ❌ **Bascule vers le post-game** à la fin de la partie : non demandée (la capture de fin de partie est
  celle de SPEC-25).
- ❌ **Relevé du ready-check réel en script** : un champ à noter pendant la recette suffit, la table de décision
  ne dépend pas de sa forme (§3).
- ❌ **Refonte de la séquence d'animation** (convergence, explosion) : seule sa durée de vie change.
