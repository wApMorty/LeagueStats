# ADR-003 — OneTricks en temps réel comme source de l'import des builds

**Date** : 2026-09-24
**Statut** : Accepté (@pj35). Suspend [ADR-001](ADR-001-source-builds-coachless.md) pour la phase 1
de SPEC-15.
**Spec liée** : [SPEC-15](../specs/SPEC-15-import-runes-items.md)

## Contexte

ADR-001 avait retenu Coachless pour son WPA, en vue de l'optimisation maison (SPEC-16), et SPEC-15
prévoyait de photographier les 283 combos (champion, lane) à chaque patch pour constituer un
historique. Le spike OneTricks (SPEC-15 §2.2.1) a montré que :

- les données sont dans le HTML (`__NEXT_DATA__`), avec des identifiants Riot directement
  utilisables par le LCU, et un filtre par adversaire ;
- un checkpoint anti-bot Vercel bloque les User-Agents non-navigateur, et bloque l'IP pendant
  moins de 10 minutes après ~17 pages en 5 minutes ;
- il n'y a ni historique ni winrate par build : seulement la popularité, sur les 500 dernières
  parties de one-tricks.

@pj35 : sa recherche manuelle se limite à deux pages, son champion sur sa lane, puis le duel. Il
n'a besoin ni d'historique ni de recherche sur ses alliés ou ses adversaires.

## Options étudiées

| Option | Pour | Contre |
|---|---|---|
| **OneTricks en temps réel** (2 pages par draft) | Reproduit la méthode manuelle de @pj35 ; aucun compte ni jeton ; pas de collecte à planifier | Popularité seulement, pas de WPA ; structure `__NEXT_DATA__` non documentée ; User-Agent de navigateur requis |
| Coachless (ADR-001) | WPA | Compte payant, jeton à gérer. Spike fait ensuite (SPEC-15 §2.1.1) : CGU incompatibles avec un accès direct à l'API |
| LoLalytics | Déjà scrapé | Extraction des builds à écrire ; winrate brut biaisé par la sélection (ADR-001) ; Selenium trop lent pour le temps réel |

## Décision

**OneTricks en temps réel** : au lock-in, la build générale (champion, lane) ; dès que
l'adversaire direct est locké, la build du duel si l'échantillon suffit. Pas de collecte par
patch.

## Conséquences

- **Volume** : au plus deux requêtes par draft, en plus de la fenêtre que l'outil ouvre déjà en
  fin de draft. C'est le volume d'une consultation manuelle, loin du seuil du checkpoint.
- **User-Agent de navigateur** : c'est lui qui fait passer le checkpoint. On l'accepte **parce
  que** le volume reste humain. Toute extension du volume (collecte, recherche sur les autres
  champions) rouvre cet ADR.
- **Fragilité** : la structure de `pageProps` peut changer sans préavis. Toute panne donne « pas
  d'import » avec un `[INFO]`, jamais une exception dans la boucle de draft.
- **Plus de table `build_snapshots`** ni d'étape dans le pipeline. SPEC-16 A+ perd sa matière
  (l'historique par patch) et est abandonné ; SPEC-16 A (moteur WPA) et le spike Coachless sont
  reportés et non planifiés.
