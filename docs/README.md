# League Stats Coach - Documentation

Documentation complète du projet League Stats Coach.

---

## 📚 Index de la documentation

### **État du Projet & Direction**
- [AUDIT_2026_08.md](AUDIT_2026_08.md) - **Audit courant (2026-08-28)** : fiabilité, performance, métier, UX — vérifié sur pièces
- [BACKLOG_2026_08.md](BACKLOG_2026_08.md) - Backlog issu de l'audit d'août, trié le 29/08 → reporté dans [../TODO.md](../TODO.md)
- [specs/](specs/) - **Specs d'implémentation** (SPEC-01 à SPEC-07), une par chantier, autoportantes
- [ROADMAP_2026.md](ROADMAP_2026.md) - Décisions stratégiques tranchées le 2026-06-11 (SQLite only, outil perso, pas de Playwright) — toujours en vigueur
- [AUDIT_2026_06.md](AUDIT_2026_06.md) - Audit précédent (2026-06-11), base de la roadmap ; conservé pour comparaison

### **Architecture & Structure**
- [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) - Structure générale du projet et organisation des fichiers

### **Configuration & Déploiement**
- [DATABASE_STRUCTURE.md](DATABASE_STRUCTURE.md) - Gestion de la base de données, chemins, et packaging PyInstaller
- [BUILD_AND_TEST.md](BUILD_AND_TEST.md) - Build PyInstaller et exécution des tests
- [CI_CD_SETUP.md](CI_CD_SETUP.md) - Pipeline GitHub Actions
- [AUTO_UPDATE_SETUP.md](AUTO_UPDATE_SETUP.md) - Mise à jour automatique (Task Scheduler)
- [LOG_ROTATION.md](LOG_ROTATION.md) - Rotation des logs
- [alembic_guide.md](alembic_guide.md) - Commandes de migration Alembic

### **Scraping**
- [runbook_scraping.md](runbook_scraping.md) - Runbook d'incident scraping (DOM, Cloudflare, lanes)
- [HEADLESS_MODE_TESTING.md](HEADLESS_MODE_TESTING.md) - Tests du mode headless Firefox

### **Features & Améliorations**
- [TOURNAMENT_COACH_IMPROVEMENTS.md](TOURNAMENT_COACH_IMPROVEMENTS.md) - Refonte complète du Tournament Coach (Oct 2025)
- [SECURITY_FIXES.md](SECURITY_FIXES.md) - Corrections de sécurité appliquées

### **Guide Développeur**
- [../CLAUDE.md](../CLAUDE.md) - Instructions pour Claude Code et historique des décisions de design

---

## 🚀 Quick Links

**Pour commencer :**
1. Lire [../README.md](../README.md) - Vue d'ensemble et installation
2. Consulter [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) - Comprendre l'architecture
3. Voir [../CLAUDE.md](../CLAUDE.md) - Contexte technique et modèle statistique

**Pour contribuer :**
1. [DATABASE_STRUCTURE.md](DATABASE_STRUCTURE.md) - Conventions de gestion de données
2. [TOURNAMENT_COACH_IMPROVEMENTS.md](TOURNAMENT_COACH_IMPROVEMENTS.md) - Exemple de refonte feature

**Pour déployer :**
1. [DATABASE_STRUCTURE.md](DATABASE_STRUCTURE.md#build-process) - Instructions de build
2. [../build_app.py](../build_app.py) - Script de packaging

---

## 📝 Conventions de documentation

### **Fichiers à la racine**
- `README.md` - Vue d'ensemble publique du projet
- `CLAUDE.md` - Instructions spécifiques pour Claude Code

### **Fichiers dans docs/**
- `PROJECT_STRUCTURE.md` - Architecture générale
- `DATABASE_STRUCTURE.md` - Documentation technique spécifique
- `TOURNAMENT_COACH_IMPROVEMENTS.md` - Changelog détaillé d'une feature
- Plus de docs techniques à venir...

### **Règle de rangement**
> **Toute documentation technique détaillée doit être placée dans `docs/`**
> Seuls `README.md` et `CLAUDE.md` restent à la racine.

---

## 🔄 Mise à jour de cette doc

Dernière mise à jour : 25 juillet 2026

Lorsque vous ajoutez une nouvelle documentation :
1. Créer le fichier dans `docs/`
2. Ajouter une entrée dans cet index
3. Mettre à jour la date ci-dessus
