## 📊 Résumé

**Tâche**: #X - [Nom complet de la tâche]
**Branche**: `feature/task-name`
**Durée estimée**: X jours
**Commits**: X commits
**Gitmoji**: [Emoji principal - ex: ♻️ pour Refactor]

[Description courte des changements]

---

## 📝 Changements

### Fichiers Modifiés (X)
1. `src/file1.py` (X lignes modifiées)
   - [Description changement 1]
   - [Description changement 2]
2. `src/file2.py` (X lignes modifiées)
   - [Description]

### Fichiers Créés (X)
1. `src/new_file1.py` (X lignes)
   - [Description rôle]
2. `src/new_file2.py` (X lignes)
   - [Description rôle]

### Fichiers Supprimés (X)
1. `old_file.py` - [Raison suppression]

---

## 🧪 Tests

- [x] Compilation Python: ✅ Tous fichiers compilent
- [x] Imports fonctionnels: ✅ Pas d'erreur import
- [x] Tests unitaires: ✅ XX/XX tests passent
- [x] Tests manuels: ✅ [Scénarios testés]

**Couverture**: XX% (objectif: 70%+)

---

## 📦 Commits Principaux

```
1. [hash] - 🎨 Type: Description commit 1
2. [hash] - ♻️ Type: Description commit 2
3. [hash] - ✅ Type: Description commit 3
```

*(Liste complète visible dans l'onglet "Commits" de la PR)*

---

## ⚠️ Points d'Attention

1. [Point spécifique nécessitant validation]
2. [Choix architectural à confirmer]
3. [Breaking changes éventuels]

---

## 📊 Métriques

| Métrique | Avant | Après | Amélioration |
|----------|-------|-------|--------------|
| Largest File | 2,381 lignes | XXX lignes | -XX% |
| Test Coverage | X% | XX% | +XX% |
| [Autre métrique] | X | XX | +XX% |

---

## 🚀 Prochaines Étapes

Après validation et merge de cette PR:
1. ✅ Mettre à jour TODO.md (marquer tâche ✅)
2. ✅ Mettre à jour CHANGELOG.md si nécessaire
3. ✅ Pull changes en local
4. ✅ Commencer Tâche #Y (si applicable)

---

## ❓ Questions

[Questions éventuelles pour review]

---

## ✅ Checklist Review

- [ ] Code compilable (`python -m py_compile src/*.py`)
- [ ] Tests passent (`pytest tests/ -v`)
- [ ] Documentation à jour (README, TODO, etc.)
- [ ] Pas de valeurs hardcodées (utilise `config_constants.py`)
- [ ] Requêtes SQL paramétrées (sécurité)
- [ ] Backward compatibility maintenue
- [ ] Type hints sur nouvelles fonctions
- [ ] Docstrings sur nouvelles classes/méthodes
- [ ] Gitmoji cohérent dans tous les commits

---

📋 **Merci de review cette PR et d'approuver/commenter directement sur GitHub !**

**Process**:
1. Review code dans l'onglet "Files changed"
2. Commenter les lignes spécifiques si nécessaire
3. Cliquer "Review changes" → "Approve" ou "Request changes"
4. Une fois approuvé, je mergerai via `gh pr merge`
