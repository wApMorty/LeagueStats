# Guide: Créer un User READ-ONLY sur Neon PostgreSQL

**Projet**: LeagueStats Coach
**Auteur**: Database Expert
**Date**: 2026-02-11
**Tâche**: TODO T13

---

## Objectif

Créer un utilisateur PostgreSQL **READ-ONLY** sur Neon pour permettre au client `.exe` de se connecter directement à la base de données Neon sans risque de modifications accidentelles.

---

## Prérequis

- Accès au **Neon Console**: https://console.neon.tech
- Projet Neon existant avec base de données `leaguestats`
- Droits administrateur sur le projet Neon

---

## Étape 1: Générer un Mot de Passe Sécurisé

1. Utiliser un générateur de mots de passe aléatoires:
   - https://www.random.org/passwords/?num=1&len=24&format=plain
   - OU `openssl rand -base64 24` dans terminal

2. **Copier le mot de passe** (exemple: `Xk9!mP2$vL8@qW3#nR7%tY6&`)

---

## Étape 2: Ouvrir Neon Console SQL Editor

1. Se connecter à https://console.neon.tech
2. Sélectionner le projet **LeagueStats**
3. Naviguer vers **SQL Editor** (dans sidebar gauche)
4. S'assurer que la base de données **neondb** est sélectionnée

---

## Étape 3: Exécuter le Script SQL

1. Ouvrir le fichier `scripts/create_readonly_user_neon.sql`
2. **Remplacer** `CHANGE_ME_TO_SECURE_PASSWORD` par le mot de passe généré à l'Étape 1
3. Copier **tout le script** (Ctrl+A, Ctrl+C)
4. Coller dans **Neon SQL Editor**
5. Cliquer sur **Run** (ou F5)

**Résultat attendu**:
```
CREATE ROLE
COMMENT
GRANT
GRANT
GRANT
ALTER DEFAULT PRIVILEGES
REVOKE
REVOKE
```

---

## Étape 4: Vérifier les Permissions

Le script contient 3 tests de vérification automatiques.

### Test 1: Vérifier que le rôle existe

```sql
SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolcanlogin
FROM pg_roles
WHERE rolname = 'leaguestats_readonly';
```

**Résultat attendu**:
```
 rolname               | rolsuper | rolcreatedb | rolcreaterole | rolcanlogin
-----------------------+----------+-------------+---------------+-------------
 leaguestats_readonly  | f        | f           | f             | t
```

Tous les champs doivent être `f` (false) sauf `rolcanlogin` qui doit être `t` (true).

### Test 2: Vérifier les permissions SELECT

```sql
SELECT
    grantee,
    table_schema,
    table_name,
    privilege_type
FROM information_schema.role_table_grants
WHERE grantee = 'leaguestats_readonly'
ORDER BY table_name, privilege_type;
```

**Résultat attendu**: Liste de tables avec **uniquement** `SELECT` dans `privilege_type`.

### Test 3: Vérifier l'absence de permissions WRITE

```sql
SELECT
    grantee,
    table_schema,
    table_name,
    privilege_type
FROM information_schema.role_table_grants
WHERE grantee = 'leaguestats_readonly'
  AND privilege_type IN ('INSERT', 'UPDATE', 'DELETE')
ORDER BY table_name;
```

**Résultat attendu**: **0 rows** (aucune permission WRITE).

---

## Étape 5: Tester la Connexion READ-ONLY

### 5.1 Récupérer le Connection String Neon

1. Dans Neon Console, aller dans **Dashboard**
2. Cliquer sur **Connection Details**
3. Copier le **Hostname** (exemple: `ep-cool-fire-12345678.us-east-2.aws.neon.tech`)

### 5.2 Construire le Connection String

Format:
```
postgresql://leaguestats_readonly:wkevBSryeCxBKqjbmwZpxYyG@ep-curly-shadow-abkhu9hs-pooler.eu-west-2.aws.neon.tech/neondb?sslmode=require&channel_binding=require:5432/neondb?sslmode=require
```

Exemple complet:
```
postgresql://leaguestats_readonly:Xk9!mP2$vL8@qW3#nR7%tY6&@ep-cool-fire-12345678.us-east-2.aws.neon.tech:5432/neondb?sslmode=require
```

### 5.3 Tester avec psql

```bash
psql "postgresql://leaguestats_readonly:YOUR_PASSWORD@YOUR_NEON_HOST:5432/neondb?sslmode=require"
```

**Si connexion réussie**, vous verrez:
```
SSL connection (protocol: TLSv1.3, cipher: TLS_AES_128_GCM_SHA256, compression: off)
Type "help" for help.

neondb=>
```

---

## Étape 6: Tests de Sécurité (CRITIQUE)

Exécuter ces tests **depuis la connexion `leaguestats_readonly`** (psql).

### Test 1: SELECT doit FONCTIONNER ✅

```sql
SELECT * FROM champions LIMIT 5;
```

**Résultat attendu**: 5 lignes de la table `champions` affichées.

### Test 2: INSERT doit ÉCHOUER ❌

```sql
INSERT INTO champions (name) VALUES ('TestChampion');
```

**Résultat attendu**:
```
ERROR:  permission denied for table champions
```

### Test 3: UPDATE doit ÉCHOUER ❌

```sql
UPDATE champions SET name = 'Hacked' WHERE id = 1;
```

**Résultat attendu**:
```
ERROR:  permission denied for table champions
```

### Test 4: DELETE doit ÉCHOUER ❌

```sql
DELETE FROM champions WHERE id = 1;
```

**Résultat attendu**:
```
ERROR:  permission denied for table champions
```

### Test 5: TRUNCATE doit ÉCHOUER ❌

```sql
TRUNCATE TABLE champions;
```

**Résultat attendu**:
```
ERROR:  permission denied for table champions
```

---

## Étape 7: Sauvegarder les Credentials (Sécurisé)

### Option A: Fichier .env Local (développement)

Créer `config/.env.neon` (git-ignored):
```env
NEON_READONLY_CONNECTION_STRING=postgresql://leaguestats_readonly:YOUR_PASSWORD@YOUR_NEON_HOST:5432/neondb?sslmode=require
```

### Option B: Obfuscation (production .exe)

Le connection string sera obfusqué en **ROT13 + Base64** dans le build .exe (TODO T14).

**NE PAS** commit le password en clair dans Git.

---

## Étape 8: Documenter dans CHANGELOG.md

Ajouter une entrée:

```markdown
## [1.1.0-dev] - 2026-02-11

### Added
- 🗃️ Database: Created READ-ONLY PostgreSQL user `leaguestats_readonly` on Neon for client .exe direct access
```

---

## Troubleshooting

### Erreur: "role 'leaguestats_readonly' already exists"

**Solution**: Le user existe déjà. Vous pouvez soit:
1. Utiliser le user existant (récupérer son password)
2. Le supprimer puis le recréer:
   ```sql
   DROP ROLE IF EXISTS leaguestats_readonly;
   ```

### Erreur: "database 'neondb' does not exist"

**Solution**: Remplacer `neondb` par le nom de votre base de données Neon réelle (vérifier dans Neon Console Dashboard).

### Erreur: "permission denied" sur GRANT

**Solution**: Vous devez être connecté avec un user **admin** (neon_superuser) pour exécuter ce script. Vérifier que vous utilisez bien le SQL Editor avec votre compte principal.

---

## Prochaines Étapes (TODO T14)

Une fois le user créé et testé:
1. Fournir le connection string au **Python Expert** pour obfuscation
2. Intégrer la connexion obfusquée dans `src/db.py`
3. Tester la connexion depuis le client .exe local

---

## Références

- [Neon Docs: Manage Roles](https://neon.com/docs/manage/roles)
- [Neon Docs: Database Access](https://neon.com/docs/manage/database-access)
- [PostgreSQL GRANT Documentation](https://www.postgresql.org/docs/current/sql-grant.html)

---

**Créé par**: Database Expert
**Date**: 2026-02-11
**Version**: 1.0
