# Structure du Projet League Stats Coach

## Fichiers Principaux (Application)

```
LeagueStats/
├── lol_coach.py          # Point d'entrée principal - Menu unifié
├── main.py               # Ancien point d'entrée (legacy)
├── assistant.py          # Moteur d'analyse et recommendations
├── draft_monitor.py      # Coach temps réel pour champion select
├── lcu_client.py         # Client API League of Legends
├── parser.py             # Parsing web des statistiques
├── db.py                 # Couche base de données SQLite
├── constants.py          # Pools de champions et configurations
├── config.py             # Configuration globale
└── db.db                 # Base de données SQLite (171 champions, 36k+ matchups)
```

## Documentation

```
├── CLAUDE.md             # Instructions pour Claude Code
├── README.md             # Documentation utilisateur
└── PROJECT_STRUCTURE.md  # Ce fichier
```

## Outils de Build

```
tools/
├── README.md             # Documentation des outils
├── build_simple.py       # Script de build principal
├── build_config.spec     # Configuration PyInstaller
├── create_distribution.py # Création du package ZIP
├── validate_simple.py    # Validation du package
└── build_release.py      # Script avancé (non utilisé)
```

## Scripts Utilitaires

```
├── make_release.py       # Processus complet de release
```

## Artefacts de Build

```
├── LeagueStatsCoach_Release/    # Dossier de release
│   ├── LeagueStatsCoach.exe     # Exécutable standalone
│   ├── db.db                    # Base de données
│   ├── INSTRUCTIONS.txt         # Guide utilisateur
│   ├── CLAUDE.md               # Documentation technique
│   └── README.md               # Information générale
├── LeagueStatsCoach_Portable.zip # Package final pour distribution
├── build/                       # Fichiers temporaires PyInstaller
└── dist/                        # Sortie PyInstaller
```

## Utilisation

### Développement
```bash
python lol_coach.py                    # Lancer l'application
```

### Build & Distribution
```bash
python tools/build_simple.py           # Créer l'exécutable
python tools/create_distribution.py    # Créer le ZIP
python tools/validate_simple.py        # Valider le package
```

### Release Complète
```bash
python make_release.py                 # Processus complet automatisé
```

## Fonctionnalités Principales

1. **Draft Coach Temps Réel** - Recommendations pendant champion select
2. **Team Builder** - Trouve trios optimaux avec pools élargis
3. **Parsing Automatique** - Met à jour les statistiques de matchups
4. **Multi-Pools** - Support top, support, jungle, mid, adc
5. **Base Complète** - 171 champions, 36k+ matchups

## Distribution

Le fichier `LeagueStatsCoach_Portable.zip` (34.5 MB) contient tout le nécessaire pour fonctionner sur n'importe quel PC Windows sans Python installé.

**Installation :**
1. Décompresser le ZIP
2. Lancer `LeagueStatsCoach.exe`
3. Aucune configuration requise

**Prérequis sur PC de destination :**
- Windows 10/11
- League of Legends installé
- Firefox installé (pour parsing web)