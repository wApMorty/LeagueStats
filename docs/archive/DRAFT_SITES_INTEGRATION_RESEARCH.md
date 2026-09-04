# Draft Sites Integration - Research Report

**Date:** 3 octobre 2025
**Objectif:** Connecter Tournament Coach aux sites de draft en ligne (DraftLol, ProDraft, etc.)

> **Restauré le 2026-09-04** — supprimé collatéralement par `17c621b` (nettoyage
> de `server/`, 25/07/2026) alors que `docs/ROADMAP_2026.md` (Horizon 3, point 4)
> continuait à le citer comme recherche disponible. Contenu inchangé depuis
> octobre 2025 : à revalider si cette feature est reprise (les sites/APIs cités
> peuvent avoir changé depuis).

---

## 🔍 Sites de draft identifiés

### **1. DraftLol** (draftlol.dawe.gg)
- **Développeur:** DaWe35 (GitHub: @dawe35)
- **Stack:** Application web JavaScript (SPA)
- **Popularité:** ~78K visiteurs/mois, #162826 US
- **Usage:** Scrims, tournois communautaires

### **2. ProDraft** (prodraft.leagueoflegends.com)
- **Éditeur:** Riot Games (officiel)
- **Usage:** Compétition pro, scrims officiels
- **Avantages:** Permet corrections de misclicks, temps ajustable

### **3. ProComps.gg**
- **Type:** Outil d'analyse de draft
- **Intégrations:** DraftLol, ProDraft, League Client
- **Méthode:** Import via "spectator link"

### **Autres outils**
- DraftGap, LoLDraftAI, iTero - Outils d'analyse avec IA
- Pick Ban Pro - Simulateur de draft

---

## 🔬 Découvertes techniques

### **WebSocket - Confirmation d'existence**

✅ **Confirmé :** DraftLol utilise WebSocket pour la communication temps réel

**Source :** GitHub issue summonerschool/steadfast-scrim #25
> "Can get this from the websocket communication"

**Problème :** Aucune documentation technique publique trouvée
- Pas de format d'URL révélé
- Pas d'exemples de messages
- Pas de protocole documenté

---

### **Spectator Link - Méthode ProComps**

ProComps s'intègre à DraftLol et ProDraft via un "spectator link" :
> "All you need to do is copy & paste the spectator link to the suitable place and ProComps will do the rest!"

**Hypothèses :**
1. **Option A :** Le spectator link contient l'ID de la room
   - Format possible : `https://draftlol.dawe.gg/spectate/{room_id}`
   - ProComps extrait l'ID et se connecte au WebSocket

2. **Option B :** Le spectator link est une URL avec toutes les infos
   - ProComps fait du polling HTTP sur cette URL
   - Parsing HTML pour extraire le draft state

3. **Option C :** API REST cachée
   - ProComps connaît un endpoint API non documenté
   - `GET /api/draft/{room_id}` → JSON avec le draft state

---

## 💡 Approches techniques possibles

### **1. Reverse Engineering du WebSocket** ⭐⭐⭐

**Complexité :** Moyenne à Élevée

**Méthode :**
1. Créer une draft test sur DraftLol
2. Ouvrir DevTools (F12) → Network → WS
3. Capturer les messages WebSocket
4. Analyser le protocole (JSON, binaire, framework)
5. Reproduire en Python avec `websocket-client`

**Risques :**
- Protocole complexe (ActionCable, Socket.io)
- Authentification requise
- Peut changer sans préavis

**Dépendances :**
```
websocket-client==1.6.4  # 200KB, pure Python
```

---

### **2. Polling HTTP avec BeautifulSoup** ⭐⭐⭐⭐

**Complexité :** Moyenne

**Méthode :**
1. Extraire `room_id` depuis l'URL du spectator
2. Fetch HTML toutes les 2-3 secondes
3. Parser avec BeautifulSoup/lxml (déjà utilisé)
4. Extraire picks/bans du DOM

**Avantages :**
- Pas de WebSocket complexe
- Fonctionne même si le site change de protocole WS
- Stack déjà disponible (lxml utilisé dans parser.py)

**Inconvénients :**
- Délai 2-3s (acceptable pour draft)
- Requêtes répétées

**Dépendances :**
```
requests==2.31.0  # Déjà utilisé
lxml==5.1.0       # Déjà utilisé
```

---

### **3. Découvrir l'API REST cachée** ⭐⭐⭐⭐⭐

**Complexité :** Variable (facile si ça existe, impossible sinon)

**Méthode :**
1. DevTools → Network → XHR/Fetch
2. Créer une draft et observer les requêtes
3. Tester si un endpoint type `/api/draft/{id}` existe
4. Si oui → Jackpot ! Simple HTTP GET

**Exemple hypothétique :**
```python
import requests

# Si l'API existe
response = requests.get(f"https://draftlol.dawe.gg/api/draft/{room_id}")
data = response.json()
# {
#   "blue_team": ["Aatrox", "Graves", ...],
#   "red_team": ["Gwen", "Camille", ...],
#   "bans": ["Yone", "Yasuo", ...]
# }
```

**Probabilité :** 30-40% que ça existe (beaucoup de SPAs ont une API REST derrière)

---

### **4. Utiliser le code de Prodraft-Tool** ⭐⭐

**Complexité :** Moyenne

**Repository :** https://github.com/Subi/Prodraft-Tool

**Stack :** Next.js (JavaScript/React)

**Approche :**
- Analyser le code source pour comprendre la logique
- Reproduire en Python
- Problème : C'est un simulateur standalone, pas un client pour le site officiel

---

## 📋 Plan d'action recommandé

### **Phase 1 : Investigation (30 min - TOI)**

**Objectif :** Déterminer la faisabilité technique

**Actions :**
1. Créer une draft sur DraftLol
2. Ouvrir DevTools (F12)
3. Capturer :
   - **Network → WS** : Messages WebSocket
   - **Network → Fetch/XHR** : Requêtes API
   - **Sources** : Fichiers JavaScript chargés
4. Me fournir :
   - URL du WebSocket (si visible)
   - 2-3 exemples de messages WS
   - URLs d'API appelées (si visibles)

**Temps nécessaire :** 5-10 minutes de ta part

---

### **Phase 2 : Implémentation (selon résultat)**

**Scénario A : API REST trouvée** ✅ IDÉAL
- **Complexité :** ⭐⭐☆☆☆
- **Temps dev :** 2-3h
- **Méthode :** Simple HTTP polling

**Scénario B : WebSocket simple (JSON clair)**
- **Complexité :** ⭐⭐⭐☆☆
- **Temps dev :** 4-6h
- **Méthode :** WebSocket client avec parsing JSON

**Scénario C : WebSocket complexe (framework)**
- **Complexité :** ⭐⭐⭐⭐☆
- **Temps dev :** 8-12h
- **Méthode :** Reverse engineering ActionCable/Socket.io

**Scénario D : Impossible sans navigateur**
- **Complexité :** ⭐⭐⭐⭐⭐
- **Solution alternative :** Import manuel amélioré

---

### **Phase 3 : Intégration Tournament Coach**

**Nouvelle commande :**
```bash
⚡ Coach > watch https://draftlol.dawe.gg/draft/abc123

👁️ Connecté à la draft...
🔵 Blue team (0/5):
🔴 Red team (0/5):
🚫 Bans (0/10):

[Live updates automatiques]

🔴 Enemy picked Gwen (1/5)

📊 Top counters to Gwen:
🥇 Aatrox          |  +4.23% advantage
🥈 Mordekaiser     |  +3.87% advantage
🥉 Jax             |  +2.95% advantage

⚡ Coach > analyze
[Full draft analysis when complete]

⚡ Coach > stop
👋 Déconnecté de la draft
```

---

## 🎯 Décision à prendre

### **Option 1 : Investigation approfondie** (RECOMMANDÉE)
- Tu fais les captures DevTools (10 min)
- Je détermine la faisabilité exacte
- On décide ensuite si on implémente

### **Option 2 : Import manuel amélioré** (Fallback sûr)
- Améliorer la commande `import` existante
- Format multi-ligne intelligent
- Reste portable et simple
- Temps dev : 1h

### **Option 3 : Reporter la feature**
- Attendre qu'une API publique soit disponible
- Ou que quelqu'un d'autre reverse-engineer

---

## 📊 Comparaison des approches

| Approche | Portable | Temps réel | Complexité | Robustesse | Temps dev |
|----------|----------|------------|------------|------------|-----------|
| **API REST** | ✅ 100% | ⚠️ 2-3s delay | ⭐⭐☆☆☆ | ⭐⭐⭐⭐⭐ | 2-3h |
| **WebSocket simple** | ✅ 100% | ✅ Instantané | ⭐⭐⭐☆☆ | ⭐⭐⭐⭐☆ | 4-6h |
| **WebSocket complexe** | ✅ 100% | ✅ Instantané | ⭐⭐⭐⭐☆ | ⭐⭐⭐☆☆ | 8-12h |
| **Import manuel** | ✅ 100% | ❌ Manuel | ⭐☆☆☆☆ | ⭐⭐⭐⭐⭐ | 1h |

---

## 🔗 Ressources utiles

### **Repos GitHub intéressants**
- [Subi/Prodraft-Tool](https://github.com/Subi/Prodraft-Tool) - Simulateur standalone
- [summonerschool/steadfast-scrim](https://github.com/summonerschool/steadfast-scrim) - Bot avec mention DraftLol WS

### **Documentation WebSocket Python**
- [websocket-client](https://github.com/websocket-client/websocket-client) - Client WS léger
- [WAMP Protocol](https://wamp-proto.org/) - Protocole utilisé par LCU (pas DraftLol)

### **Outils de reverse engineering**
- Chrome DevTools Network tab
- Burp Suite (pour HTTPS interception avancée)
- Wireshark (pour analyse protocole réseau)

---

## 💬 Conclusion

**État actuel :** Techniquement faisable, mais nécessite investigation

**Bloqueur principal :** Absence de documentation publique

**Prochaine étape :** Capture DevTools pour déterminer la méthode exacte

**Risque :** Fragile face aux changements du site (sauf si API officielle)

**Alternative sûre :** Import manuel amélioré (simple, portable, robuste)

---

**Recommandation finale :** Commencer par l'investigation DevTools (10 min de ton temps) pour une réponse définitive.

---

## 🔄 Mise à jour - Session du 3 octobre 2025

### **Statut actuel : EN PAUSE - En attente d'informations WebSocket**

**Décision prise :**
- ✅ DraftLol confirmé avec **WebSocket simple et explicite**
- ✅ Drafter confirmé avec **WebSocket verbeux mais exploitable**
- ✅ ProDraft : Saisie manuelle acceptable (usage ponctuel)

**Ordre d'implémentation :**
1. **DraftLol** (priorité 1) - WebSocket simple, ~3-4h de dev
2. **Drafter** (priorité 2) - WebSocket verbeux, ~5-6h de dev
3. **ProDraft** (manuel) - Utiliser Tournament Coach existant

### **Informations nécessaires pour démarrer**

Pour implémenter DraftLol, besoin de :

1. **URL du WebSocket**
   - Format attendu : `wss://draftlol.dawe.gg/cable?room_id=...`
   - Ou équivalent

2. **Exemples de messages WebSocket** (2-3 suffisent)
   - Message lors d'un pick
   - Message lors d'un ban
   - Message de state initial (optionnel)

3. **Format URL de draft**
   - Ex: `https://draftlol.dawe.gg/draft/{id}`

4. **Mapping ally/enemy**
   - Quel side est joué (blue/red)

### **Architecture prévue**

```
src/
├── draft_watcher.py          # NOUVEAU MODULE
│   ├── BaseDraftWatcher       # Classe abstraite
│   ├── DraftLolWatcher        # Implémentation DraftLol
│   └── DrafterWatcher         # Implémentation Drafter (phase 2)
```

**Nouvelle dépendance :**
```
websocket-client==1.6.4  # ~200KB, pure Python, portable
```

### **Commandes prévues**

```bash
# Mode watch temps réel
⚡ Coach > watch draftlol https://draftlol.dawe.gg/draft/abc123
🔌 Connexion au WebSocket...
✅ Connecté à la draft
👁️ Mode spectateur actif

[Updates automatiques en temps réel]

# Import one-shot (snapshot)
⚡ Coach > import draftlol https://draftlol.dawe.gg/draft/abc123
✅ Imported draft snapshot
```

### **Timeline estimée**

| Tâche | Temps |
|-------|-------|
| Setup WebSocket + connexion | 1h |
| Parsing messages | 1h |
| Intégration UI | 1h |
| Tests & debug | 1h |
| **Total DraftLol** | **~4h** |

### **Prochaines étapes**

1. ⏸️ **EN PAUSE** - Résoudre bugs prioritaires
2. ⏭️ Paul fournit infos WebSocket DraftLol
3. ⏭️ Implémentation du module `draft_watcher.py`
4. ⏭️ Intégration dans Tournament Coach
5. ⏭️ Tests avec drafts réels

---

**Dernière mise à jour :** 3 octobre 2025, 18h30
**Statut :** En attente - Informations WebSocket requises
**Bloqueur :** Bugs prioritaires à résoudre d'abord
