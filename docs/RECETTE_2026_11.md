# Recette groupée — novembre 2026

**Date** : 2026-11-10. **Objet** : chantier 0.1 de `docs/AUDIT_2026_11.md` §9, vider la file des specs « livrées, recette @pj35 à faire ».
**État** : ✅ validée en bloc par @pj35 le 2026-11-10, les 57 lignes. Statuts des specs, de leur index et du `TODO.md` mis à jour le même jour. Reste ouvert : la draft lente (constat 2), que @pj35 reprend.
**Périmètre** : 31 specs (SPEC-24 à 34, 36 à 41, 43 à 56), plus les reliquats de SPEC-19, 20 et 21. L'audit en comptait 29 : son décompte ratait les formulations « recette à l'œil » et SPEC-47.

## Mode d'emploi

- Coche en jouant. Un point raté : note son numéro et ce que tu as vu (« C4 KO : bouton sur le mauvais allié »). Chaque KO devient un bug avec son test de régression.
- Une spec est recettée quand toutes ses lignes sont cochées (tableau de §8). Je passe alors ses statuts à jour en un seul lot.
- Les libellés entre guillemets sont ceux des specs. Quand une spec plus récente a remplacé l'écran, la ligne le dit.

**Parcours conseillé**

1. Vingt minutes hors partie : A1 à A16, A20 à A23.
2. Une classée complète, client en plein écran : B, C, D, E.
3. Une normale blind : fin de C5, puis F3.
4. Un soir sans jouer : A17 à A19 (le scrape a pris 2 h 43 au dernier passage), F1 et F2.

---

## 1. Déjà prouvé par les traces

Relevé le 2026-11-10 sur `data/db.db` (lecture seule), `logs/draft_monitor_ticks.log`, `user_prefs.json` et `data/winprob_model.json`. Ces points n'ont pas besoin de tes yeux.

| Spec | Ce qui était à vérifier | Preuve |
|---|---|---|
| SPEC-25 | `raw_eog` et `lp_delta` écrits après une partie | `raw_eog` présent sur 53 parties de novembre sur 54 (161 sur 180 en octobre) ; 233 photos de rang liées à une partie, `lp_delta` non nul sur 223 photos |
| SPEC-29 | Un axe d'objectif se fixe puis se juge à la partie suivante | 22 axes en référence `objective` (20 acquis, 2 actifs), 268 verdicts |
| SPEC-36 | L'accueil recalcule les analyses en `GRID_VERSION` 2 | 2 820 valeurs de morts sans contrepartie en base |
| SPEC-43 | Prédiction journalisée sous `spec43-v1` | 61 prédictions sous cette version |
| SPEC-44 | Un pool désigné par poste | `pools_by_role` renseigné aux cinq postes |
| SPEC-46 | `alembic upgrade head`, stratégie journalisée, stratégie relue au lancement | Base à la tête `b52d1e7c9a40` ; `predictions.strategy` rempli (PresqueComplet 4, Arbre 22) ; `active_strategy` = Arbre |
| SPEC-47 | Modèle réentraîné avec la draft | `wp-d819a71d` adopté le 2026-11-01, 13 entrées dont `draft` |
| SPEC-50 | « Créer le pool » écrit et désigne le pool, suffixe au second clic | Pools « … GÉNÉRÉ 2026-11-07 (2) » désignés aux cinq postes, « (3) » au mid |
| SPEC-52 | `alembic upgrade head`, chaque photo rattachée à un compte | 0 photo sans compte, trois comptes distincts ; le compte secondaire est passé de 11 à 24 photos, rattachées à lui seul |
| SPEC-53 | `python scripts/update_all.py --recompute-only` | `db_meta.pick_order` présent, recalcul du 2026-11-08 |
| SPEC-54 | Stratégie Arbre active, drafts réelles sous Arbre | `active_strategy` = Arbre, 22 prédictions sous Arbre |

## 2. Trois constats à traiter

1. **Prédictions perdues pendant huit jours.** Du 30 octobre 14 h 57 au 7 novembre 22 h 52, 32 parties ont été jouées Live Coach ouvert (il a vu les drafts : 9 le 1er, 6 le 2, 6 le 3, 18 le 7) sans aucune prédiction en base. Cause la plus probable : le code de SPEC-46 écrivait la colonne `strategy`, créée seulement par l'`alembic upgrade head` du 7 novembre au soir. L'échec ne laisse qu'un `[WARNING]` en console (`src/draft/final_analysis.py:347`). Reporté au chantier 0.2 de l'audit (§9), qui ajoute une migration : une alerte au démarrage quand la base est en retard sur la tête Alembic.
2. **SPEC-28 ne passe pas sur ses propres chiffres.** 212 drafts tracées : médiane à 0,75 s, 201 vues en 6 s ou moins, 11 au-delà (maximum 21,8 s le 30 octobre, 4 depuis le 1er novembre). Et pendant la sélection, l'étape `draft` d'un tour a dépassé 6 s à 38 reprises en un mois (maximum 28,7 s le 7 novembre, 17,0 s le 9). Cause non cherchée ; le journal ne dit pas si ce temps est du calcul ou une requête au client. Reporté par @pj35 le 2026-11-10 (ligne « Draft lente » du `TODO.md`, section « Reporté ») ; E4 est validée sur l'enchaînement des parties, pas sur ces délais.
3. **Statut de SPEC-47 périmé.** La spec dit « à fusionner » et l'index la marque 🟡, alors que la branche `claude/clever-jang-6d19f8` est dans `master` et que le modèle tourne. Statut, index et `TODO.md` corrigés le 2026-11-10. Le worktree `.claude/worktrees/clever-jang-6d19f8`, propre et fusionné, appartient à une session de l'application : il part avec l'archivage de cette session.

---

## 3. A — Hors partie

Client LeagueStats ouvert, LoL au repos.

**Accueil**

- [x] **A1** · SPEC-29 — « Derniers constats » : 5 métriques sur les 10 dernières parties du poste, 10 points par ligne, un clic sur un point ouvre la partie. Aucune barre de défilement à 1 920 px, même avec un bandeau de notification.
- [x] **A2** · SPEC-36 — La ligne « Morts sans contrepartie avant 14 min » figure dans les constats ou dans le choix d'axe. Quand une place se libère, fixer cet axe (cible ≤ 1) : jamais fait à ce jour, aucun axe sur cette métrique en base.

**Rang**

- [x] **A3** · SPEC-52 — LoL fermé : courbe du dernier compte vu, sans creux d'un autre palier. Changer de compte dans LoL : l'écran bascule sur la courbe de ce compte.

**Parties et revue**

- [x] **A4** · SPEC-32 — Une partie ouverte : deux listes de cinq avec portraits, couronne « MVP » chez les gagnants, « ACE » chez les perdants, ta ligne marquée « toi ». À voir en Motion Réduit et Complet, puis fenêtre à 1 400 px (listes empilées).
- [x] **A5** · SPEC-36 — La revue montre le panneau des morts avant 14 min.
- [x] **A6** · SPEC-45 — La partie 8024448317 (remake) affiche « 0 LP » neutre et « · remake ».
- [x] **A7** · SPEC-47 — Revue d'une partie à draft déséquilibrée : la courbe de win chance démarre à l'écart de 50 % annoncé par la draft.

**Calibration**

- [x] **A8** · SPEC-39 — Facteur, intervalle et bouton « Appliquer » grisé avec sa raison écrite. Les valeurs de la spec (0,613, de −1,17 à 2,25) valaient pour `spec13-v1` ; elles ont changé sous `spec43-v1`. Ne pas forcer l'application : elle modifierait le modèle réel.

**Méta du poste**

- [x] **A9** · SPEC-51 — Menu Coaching → « Méta du poste », Top : cases du top entourées dans les deux matrices, picks 8 et 10 en surbrillance, champions du pool du poste marqués dans l'histogramme. Quitter puis rouvrir depuis le menu : la page revient sur le dernier poste choisi.
- [x] **A10** · SPEC-50 — Panneau : exclure deux champions, « Générer » ; le pool proposé ne les contient pas. Un second « Générer » sans changement répond aussitôt.
- [x] **A11** · SPEC-49 — Cartes de suggestion : passer une carte (elle ne revient pas), prendre la suivante ; seul le panneau se redessine ; flèches gauche et droite au clavier. L'écran « Suggestions » de la spec a été remplacé par ce panneau.
- [x] **A12** · SPEC-54, SPEC-55 — L'arbre du pool s'affiche sous le pool du poste, puis sous le pool généré après « Générer ».

**Pool**

- [x] **A13** · SPEC-44 — Désigner un pool pour un poste, le retirer : la désignation se lit dans l'en-tête et dans la liste.
- [x] **A14** · SPEC-49 — Après la carte prise en A11 : le pool a changé, même taille, même ordre.
- [x] **A15** · SPEC-54, SPEC-55 — Pool du top : l'arbre s'affiche sous les champions.

**Stratégies**

- [x] **A16** · SPEC-46 — Les quatre stratégies système (Simple, Counter, Complet, Arbre) ne sont ni modifiables ni supprimables. Un réglage hors limite (nom trop long, poids hors borne, stratégie de trop) affiche son refus dans l'écran.

**Données**

- [x] **A17** · SPEC-37 — LoL fermé, « Actualiser » : jauge de la première lane, champions qui défilent, estimation après 5 pages. Pendant ce temps, `python scripts/update_all.py` dans un terminal refuse de démarrer (verrou).
- [x] **A18** · SPEC-37 — Fermer la fenêtre pendant le scrape : dialogue de confirmation ; « oui » arrête, et la base retrouve son volume (`sqlite3 data/db.db "select count(*) from matchups"`).
- [x] **A19** · SPEC-37 — Relancer et laisser finir : « Dernier passage » montre la date du jour et le bilan par lane.

**Fenêtre et écrans « Client »** (SPEC-21, lots 4 à 6)

- [x] **A20** — Poignées de redimensionnement basse et bas-droite sans saut ; transitions de page fluides.
- [x] **A21** — L'exe construit par `python build_app.py` affiche la page dès son premier lancement (au spike, un exe neuf ne l'avait pas affichée une fois).
- [x] **A22** — Profil, Historique, Collection, Social : mêmes contenus que dans LoL.
- [x] **A23** — Lobby : ouvrir, choisir les postes, quitter. File : lancer, annuler. Mêmes états que dans LoL.

## 4. B — File et partie trouvée

- [x] **B1** · SPEC-25 — La pastille suit les phases : « En file », « Champion select », « En partie », « Fin de partie », « Hors partie ».
- [x] **B2** · SPEC-26 — « Accepter » : l'overlay reste sur « Acceptée · En attente des autres joueurs », sans se rejouer ni rouvrir les boutons, puis s'efface sur la draft déjà ouverte.
- [x] **B3** · SPEC-26 — Un joueur refuse : « Un joueur n'a pas accepté », retour en file sans changement de page.

## 5. C — Draft classée

**Bans, ordre, poste**

- [x] **C1** · SPEC-24 — Survoler puis valider un ban depuis LeagueStats : il apparaît dans LoL.
- [x] **C2** · SPEC-24 — Numéros 1 à 10 et anneau du joueur en cours, y compris quand c'est le tout premier joueur.
- [x] **C3** · SPEC-24 — Demander, recevoir et accepter un échange de rôle. Ces écritures n'ont jamais été exercées en vrai.
- [x] **C4** · SPEC-53 — Dès la sélection : « … vise le n° X (tu es n° Y) », bouton « ⇄ ordre · conseillé » sur le bon allié, même ligne en console. Le conseil disparaît après ton pick.
- [x] **C5** · SPEC-44 — Console : `[INFO] Poste … : pool « … »` ; blind pick et bans du poste obtenu. Ensuite, une normale blind repart sur le pool par défaut.

**Cartes**

- [x] **C6** · SPEC-40 — Après un pick adverse : le gros chiffre de chaque carte égale celui de sa tuile du grimoire ; survoler dans le grimoire un champion hors cartes déplace la jauge. La sous-ligne « Fin de draft attendue » a été retirée par SPEC-48 : ne pas la chercher.
- [x] **C7** · SPEC-41 — Sous-ligne « dont toi sur X : ±N pts (n parties) » ; « aucune partie sur X » pour un champion jamais joué.
- [x] **C8** · SPEC-43 — Carte, tuile et jauge donnent le même chiffre pour un même champion.
- [x] **C9** · SPEC-55, SPEC-54 — Sous Arbre : la carte du n° 1 porte « Connu … · Exposition … », la console une ligne `[D]` ; en B4-B5 sans vis-à-vis, l'exposition n'est pas nulle. Les libellés « Blind » et « Counter de X » de SPEC-54 ont été remplacés par cette ligne.
- [x] **C10** · SPEC-48 — Sous WIN LANE, avant le vis-à-vis : « Réponse attendue : X », classement sans délai. Vis-à-vis posé : la ligne disparaît. Sous Simple : elle n'apparaît jamais.
- [x] **C11** · SPEC-46 — Basculer de Simple à Counter puis à Complet pendant les picks : le classement et la ligne de décomposition changent aussitôt, les pourcentages de la jauge ne bougent pas.

**Runes**

- [x] **C12** · SPEC-38 — Survoler un champion, ouvrir « 3 pages OneTricks » : trois pages distinctes avec leur part ; après le verrouillage du vis-à-vis, la ligne du duel apparaît.
- [x] **C13** · SPEC-38 — « Choisir » sur la page 2 : page `LS` écrite dans LoL, colonne « Modifiée à la main », et le verrouillage ne la remplace pas.

**Verrouillage**

- [x] **C14** · SPEC-26 — Dix champions verrouillés : le client bascule seul sur « En partie », une fois depuis l'écran Draft, une autre fois depuis une autre page.

## 6. D — En partie

- [x] **D1** · SPEC-30 — Plein écran 1 920 × 1 080 : tout l'écran visible sans barre de défilement, portraits dans le face-à-face.
- [x] **D2** · SPEC-24 — Analyse de la draft affichée, courbe de win chance qui avance, plan de build qui se coche à l'achat.
- [x] **D3** · SPEC-47 — La courbe démarre à l'écart de 50 % annoncé par la draft.
- [x] **D4** · SPEC-33 — Dix pastilles : taux de victoire en quelques secondes, puis ΔP moyen ; infobulle 5 / 10 / 20 ; aucune erreur en console.
- [x] **D5** · SPEC-27 — Draft juste : console `[OK] Postes vérifiés en partie : 10/10 conformes`.
- [x] **D6** · SPEC-27 — Une fois, forcer un faux poste adverse en sélection (`r <champion> <lane>`) : en partie, console `[ALERTE] Postes corrigés en partie : …`, ligne « Postes corrigés », tableau recalculé, build qui cite le vrai vis-à-vis.
- [x] **D7** · SPEC-31 — Ambessa ou Yorick verrouillé : dans le set d'items « LS » de LoL, « Situationnels » ne contient que des suites du core, « Autres cores » les autres seconds objets ; console `[INFO] Situationnels : suites du core (N parties)`.
- [x] **D8** · SPEC-56 — Duel publié (idéalement Malphite contre Nasus) : la console annonce la substitution « Compétences », les bottes sont à leur rang dans le bloc Core du set, et « En partie » vise les objets dans cet ordre.

## 7. E — Fin de partie, F — Hors client

**Fin de partie et enchaînement**

- [x] **E1** · SPEC-45 — Revue d'une classée : ton gain (« +19 LP ») en entier dans le dégradé, rang en petit dessous. LP arrivées après coup : l'encart apparaît sans recharger la page.
- [x] **E2** · SPEC-32 — Écran Post-game : même classement MVP / ACE qu'en A4, sur la partie qui vient de finir.
- [x] **E3** · SPEC-25 — « Rejouer » dans les 3 s après l'écran de fin : la partie figure quand même dans Parties, avec ses LP.
- [x] **E4** · SPEC-28 — Trois parties enchaînées (« Rejouer » puis file) : à chaque draft la recommandation s'affiche, l'écran Draft s'ouvre, « En partie » a perdu l'analyse précédente. Les délais du constat 2 restent ouverts.

**Hors client**

- [x] **F1** · SPEC-34 — LoL fermé, `python scripts/demo_client.py` : la fenêtre parcourt seule profil, file, partie trouvée, draft, chargement, En partie, revue et coaching, puis recommence.
- [x] **F2** · SPEC-34 — Captures, GIF et teaser relus à l'œil : aucun Riot ID réel. Les captures datent du 16 octobre : à régénérer (`python scripts/capture_screens.py`, `npm run render`, `npm run gif`) quand l'interface sera stable.
- [x] **F3** · SPEC-27 — Deux relevés `python scripts/spike_live_positions.py`, dont une normale blind.
- [x] **F4** · SPEC-26 — Facultatif : relever `playerResponse` et `state` du ready-check après acceptation (`/lol-matchmaking/v1/ready-check`).
- [x] **F5** · SPEC-19, SPEC-20 — Rappel d'axe en draft, rapport de fin de partie, overlay en jeu : notés « recette en partie réelle » au `TODO.md` depuis octobre. À cocher s'ils servent encore, sinon à déclarer caducs.

---

## 8. Suivi par spec

| Spec | Lignes à cocher | Déjà prouvé (§1) |
|---|---|---|
| SPEC-21 | A20 à A23 | |
| SPEC-24 | C1, C2, C3, D2 | |
| SPEC-25 | B1, E3 | oui |
| SPEC-26 | B2, B3, C14, F4 | |
| SPEC-27 | D5, D6, F3 | |
| SPEC-28 | E4 | constat 2 |
| SPEC-29 | A1 | oui |
| SPEC-30 | D1 | |
| SPEC-31 | D7 | |
| SPEC-32 | A4, E2 | |
| SPEC-33 | D4 | |
| SPEC-34 | F1, F2 | |
| SPEC-36 | A2, A5 | oui |
| SPEC-37 | A17, A18, A19 | |
| SPEC-38 | C12, C13 | |
| SPEC-39 | A8 | |
| SPEC-40 | C6 | |
| SPEC-41 | C7 | |
| SPEC-43 | C8 | oui |
| SPEC-44 | A13, C5 | oui |
| SPEC-45 | A6, E1 | |
| SPEC-46 | A16, C11 | oui |
| SPEC-47 | A7, D3 | oui, constat 3 |
| SPEC-48 | C10 | |
| SPEC-49 | A11, A14 | |
| SPEC-50 | A10 | oui |
| SPEC-51 | A9 | |
| SPEC-52 | A3 | oui |
| SPEC-53 | C4 | oui |
| SPEC-54 | A12, A15, C9 | oui |
| SPEC-55 | A12, A15, C9 | |
| SPEC-56 | D8 | |
| SPEC-19, SPEC-20 | F5 | |
