-- =============================================================================
-- Script: Create READ-ONLY User for Neon PostgreSQL
-- Database Expert - LeagueStats Project
-- Date: 2026-02-11
-- =============================================================================
--
-- INSTRUCTIONS:
-- 1. Open Neon Console SQL Editor: https://console.neon.tech
-- 2. Select your database (leaguestats)
-- 3. Copy-paste this entire script
-- 4. Execute
-- 5. Save the generated password securely
--
-- SECURITY:
-- - User has SELECT-only permissions
-- - INSERT/UPDATE/DELETE/TRUNCATE are explicitly revoked
-- - Connection requires SSL
--
-- =============================================================================

-- Step 1: Create READ-ONLY user with secure random password
-- IMPORTANT: Replace 'CHANGE_ME_TO_SECURE_PASSWORD' with a strong password
-- Example: Use https://www.random.org/passwords/?num=1&len=24&format=plain
CREATE ROLE leaguestats_readonly WITH
    LOGIN
    PASSWORD 'CHANGE_ME_TO_SECURE_PASSWORD'  -- ⚠️ REPLACE THIS
    CONNECTION LIMIT -1
    NOSUPERUSER
    NOCREATEDB
    NOCREATEROLE
    NOREPLICATION;

-- Add comment for documentation
COMMENT ON ROLE leaguestats_readonly IS 'Read-only user for LeagueStats client .exe - created 2026-02-11';

-- Step 2: Grant CONNECT permission to database
GRANT CONNECT ON DATABASE neondb TO leaguestats_readonly;

-- Step 3: Grant USAGE on schema public
GRANT USAGE ON SCHEMA public TO leaguestats_readonly;

-- Step 4: Grant SELECT on ALL existing tables
GRANT SELECT ON ALL TABLES IN SCHEMA public TO leaguestats_readonly;

-- Step 5: Grant SELECT on ALL future tables (automatic for new tables)
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT ON TABLES TO leaguestats_readonly;

-- Step 6: EXPLICITLY REVOKE write permissions (defense in depth)
REVOKE INSERT, UPDATE, DELETE, TRUNCATE ON ALL TABLES IN SCHEMA public FROM leaguestats_readonly;

-- Step 7: REVOKE DDL operations
REVOKE CREATE ON SCHEMA public FROM leaguestats_readonly;

-- =============================================================================
-- VERIFICATION TESTS
-- =============================================================================

-- Test 1: Verify role exists
SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolcanlogin
FROM pg_roles
WHERE rolname = 'leaguestats_readonly';

-- Expected output:
--   rolname               | rolsuper | rolcreatedb | rolcreaterole | rolcanlogin
-- ------------------------+----------+-------------+---------------+-------------
--   leaguestats_readonly  | f        | f           | f             | t

-- Test 2: Verify table permissions
SELECT
    grantee,
    table_schema,
    table_name,
    privilege_type
FROM information_schema.role_table_grants
WHERE grantee = 'leaguestats_readonly'
ORDER BY table_name, privilege_type;

-- Expected output: Only 'SELECT' privileges on all tables

-- Test 3: Verify NO write permissions
SELECT
    grantee,
    table_schema,
    table_name,
    privilege_type
FROM information_schema.role_table_grants
WHERE grantee = 'leaguestats_readonly'
  AND privilege_type IN ('INSERT', 'UPDATE', 'DELETE')
ORDER BY table_name;

-- Expected output: 0 rows (no write permissions)

-- =============================================================================
-- CONNECTION STRING TEMPLATE
-- =============================================================================
--
-- After executing this script, use this connection string:
--
-- postgresql://leaguestats_readonly:YOUR_PASSWORD@YOUR_NEON_HOST:5432/neondb?sslmode=require
--
-- Replace:
-- - YOUR_PASSWORD: The password you set above
-- - YOUR_NEON_HOST: Your Neon endpoint (e.g., ep-xxx-yyy.us-east-2.aws.neon.tech)
--
-- Example:
-- postgresql://leaguestats_readonly:abc123XYZ!@ep-cool-fire-12345678.us-east-2.aws.neon.tech:5432/neondb?sslmode=require
--
-- =============================================================================

-- =============================================================================
-- POST-CREATION TESTS (Run from another connection as leaguestats_readonly)
-- =============================================================================
--
-- Test 1: SELECT should work
-- SELECT * FROM champions LIMIT 5;
--
-- Test 2: INSERT should FAIL with "permission denied"
-- INSERT INTO champions (name) VALUES ('TestChampion');
--
-- Test 3: UPDATE should FAIL with "permission denied"
-- UPDATE champions SET name = 'Hacked' WHERE id = 1;
--
-- Test 4: DELETE should FAIL with "permission denied"
-- DELETE FROM champions WHERE id = 1;
--
-- =============================================================================
