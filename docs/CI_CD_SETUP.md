# CI/CD Setup Guide - LeagueStats Coach

**Created**: 2025-12-28 (Tâche #10)
**Status**: ✅ Complete

---

## 📋 Overview

Le projet utilise GitHub Actions pour l'intégration et déploiement continu (CI/CD) avec:
- **Tests automatiques** sur chaque push/PR
- **Quality gates** (pylint, black, mypy, bandit)
- **Coverage enforcement** (89% minimum)
- **Build validation** (main branch uniquement)
- **Performance benchmarks** (main branch uniquement)

---

## 🚀 Quick Start

### 1. Activer le Workflow

Le workflow est **automatiquement activé** après merge dans main. Aucune action requise !

Vérifier le statut: https://github.com/wApMorty/LeagueStats/actions

### 2. Configurer Codecov (Optionnel mais Recommandé)

#### Étape 1: S'inscrire sur Codecov

1. Aller sur https://codecov.io
2. Cliquer "Sign up with GitHub"
3. Autoriser Codecov à accéder à ton repo

#### Étape 2: Obtenir le Token

1. Sur Codecov.io, sélectionner ton repo "LeagueStats"
2. Aller dans **Settings** → **General**
3. Copier le **Upload Token**

#### Étape 3: Ajouter le Secret GitHub

1. Sur GitHub, aller dans ton repo
2. **Settings** → **Secrets and variables** → **Actions**
3. Cliquer **New repository secret**
4. Name: `CODECOV_TOKEN`
5. Value: Coller le token de Codecov
6. Cliquer **Add secret**

#### Étape 4: Mettre à Jour le Badge

Dans `README.md`, remplacer `?token=YOUR_TOKEN` par ton token:

```markdown
[![codecov](https://codecov.io/gh/wApMorty/LeagueStats/branch/inspiring-rhodes/graph/badge.svg?token=ABC123DEF456)](https://codecov.io/gh/wApMorty/LeagueStats)
```

Le token est visible dans l'URL du badge sur Codecov.io.

---

## 🏗️ Architecture

### Workflow File

`.github/workflows/ci.yml` - Workflow principal avec 5 jobs

### Jobs Breakdown

| Job | Durée | Quand | Description |
|-----|-------|-------|-------------|
| **quality** | ~2 min | Tous push/PR | Pylint, Black, Mypy, Bandit |
| **tests** | ~3 min | Tous push/PR | Tests + coverage 89% |
| **performance** | ~5 min | Main branch uniquement | Benchmarks (informatif) |
| **build** | ~6 min | Main branch uniquement | Build .exe validation |
| **ci-status** | <10 sec | Toujours | Résumé statut |

### Execution Flow

```
Push/PR
├─ [Parallel]
│  ├─ quality (2 min) ← Fail-fast si Black fail
│  └─ tests (3 min)   ← Coverage 89%
│
├─ ci-status (always)
│
└─ [Main branch only, after tests pass]
   ├─ build (6 min)
   └─ performance (5 min)
```

**Temps total**:
- PR: **~3 minutes** (quality + tests en parallèle)
- Main: **~9 minutes** (inclut build + performance)

---

## 📊 Status Checks

### Required Checks (Bloquent le merge)

- ✅ **Code Quality**: Pylint 8.0+, Black formatting, Bandit security
- ✅ **Tests & Coverage**: 146 tests, 89% coverage minimum

### Optional Checks (Informatifs)

- ℹ️ **Performance Benchmarks**: Main branch uniquement
- ℹ️ **Build Windows Executable**: Main branch uniquement

---

## 🛠️ Local Development

### Installer Quality Tools

```bash
pip install -r requirements-dev.txt
```

Cela installe:
- `pylint>=3.0.0` - Linter
- `black>=24.0.0` - Formatter
- `mypy>=1.8.0` - Type checker
- `bandit>=1.7.0` - Security scanner
- `pytest-benchmark>=4.0.0` - Performance benchmarks

### Pre-Push Checklist

Avant de pusher, exécuter localement:

```bash
# 1. Format code
black src/ tests/ scripts/ *.py

# 2. Run quality checks
pylint src/ --fail-under=8.0
mypy src/ --ignore-missing-imports
bandit -r src/ -f screen

# 3. Run tests with coverage
pytest tests/ -v --cov=src --cov-fail-under=89

# 4. (Optional) Run benchmarks
pytest tests/ -k "benchmark" --benchmark-only
```

### Configuration Files

**pyproject.toml** - Configuration centralisée pour:
- Black: `line-length=100`, `target-version=py313`
- Pylint: `fail-under=8.0`, désactive docstrings warnings
- Mypy: `python_version=3.13`, `ignore_missing_imports=true`
- Pytest: `--cov-fail-under=89`, markers pour tests slow/benchmark
- Bandit: Exclude tests, skip assert warnings

---

## 🚨 Common Issues

### Issue 1: Coverage Below 89%

**Symptom**: CI fails with "Coverage 87.5% < 89%"

**Solution**:
```bash
# Check which files have low coverage
pytest tests/ --cov=src --cov-report=term-missing

# Add tests for uncovered lines
# Or adjust threshold if justified (requires discussion)
```

### Issue 2: Black Formatting Failure

**Symptom**: CI fails in ~30 seconds with formatting errors

**Solution**:
```bash
# Auto-format all files
black src/ tests/ scripts/ *.py

# Commit formatted code
git add .
git commit -m "🎨 Style: Auto-format code with black"
```

### Issue 3: Pylint Score Below 8.0

**Symptom**: CI fails with "Your code has been rated at 7.8/10"

**Solution**:
```bash
# Check specific warnings
pylint src/ --fail-under=8.0

# Fix warnings or adjust pyproject.toml to disable specific rules
```

### Issue 4: Codecov Upload Fails

**Symptom**: "Codecov upload failed" (but CI still passes)

**Note**: CI configuré avec `fail_ci_if_error: false` pour Codecov

**Solution**:
1. Vérifier que `CODECOV_TOKEN` secret existe dans GitHub
2. Vérifier token valide sur https://codecov.io
3. Si problème persiste, check Codecov status: https://status.codecov.io

---

## 📈 Metrics & Badges

### CI/CD Status

[![CI/CD Pipeline](https://github.com/wApMorty/LeagueStats/actions/workflows/ci.yml/badge.svg)](https://github.com/wApMorty/LeagueStats/actions/workflows/ci.yml)

Statut actuel du workflow (vert = passing, rouge = failing)

### Code Coverage

[![codecov](https://codecov.io/gh/wApMorty/LeagueStats/branch/inspiring-rhodes/graph/badge.svg)](https://codecov.io/gh/wApMorty/LeagueStats)

Pourcentage coverage tests (target: 89%+)

### Python Version

[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/downloads/)

Version Python requise

### Code Style

[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

Formatage code avec Black

---

## 💰 GitHub Actions Quotas

### Gratuit pour Dépôts Publics

✅ **Minutes illimitées** pour dépôts publics
✅ **500 MB artifacts storage** gratuits
✅ **Runners Windows/Linux/macOS** gratuits

### Usage Estimé

- **CI time**: ~3 min par PR × 30 PRs/mois = ~90 min/mois
- **Artifacts**: ~15 MB (coverage + benchmarks) auto-cleanup après 7-30 jours
- **Coût**: **$0** (100% gratuit)

### Limites

- **Concurrent jobs**: 20 (largement suffisant)
- **Workflow run time**: 6 heures max (notre max: 20 min)
- **Artifact retention**: 90 jours max (notre usage: 7-30 jours)

**Conclusion**: Aucun risque de dépassement, tout reste gratuit ! 🎉

---

## 🔧 Maintenance

### Mettre à Jour Dependencies

GitHub Actions recommande d'utiliser versions spécifiques (v4, v5) au lieu de @latest.

**Current versions**:
- `actions/checkout@v4`
- `actions/setup-python@v5`
- `actions/upload-artifact@v4`
- `codecov/codecov-action@v4`

**Update process**: GitHub Dependabot peut créer des PRs automatiques pour updates.

### Modifier le Workflow

1. Éditer `.github/workflows/ci.yml`
2. Tester localement avec [act](https://github.com/nektos/act) (optionnel)
3. Commit et push → CI vérifie automatiquement
4. Si échec, check logs dans GitHub Actions tab

---

## 📚 Resources

- **GitHub Actions Docs**: https://docs.github.com/en/actions
- **Codecov Docs**: https://docs.codecov.io
- **Pytest Coverage**: https://pytest-cov.readthedocs.io
- **Black Formatter**: https://black.readthedocs.io
- **Pylint**: https://pylint.pycqa.org
- **Mypy**: https://mypy.readthedocs.io
- **Bandit**: https://bandit.readthedocs.io

---

## ✅ Success Criteria

CI/CD est considéré réussi si:

- ✅ Tous les PRs passent tests + quality gates
- ✅ Coverage maintenue à 89%+
- ✅ Build successful sur main branch
- ✅ Codecov badge montre 89%+
- ✅ Feedback en <5 minutes sur PRs

**Current Status**: ✅ READY (après setup Codecov token)

---

**Last Updated**: 2025-12-28
**Maintainer**: @pj35
**CI/CD Version**: v1.0.0 (Tâche #10)
