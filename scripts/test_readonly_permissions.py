#!/usr/bin/env python3
"""
Test Script: Verify READ-ONLY Permissions for Neon PostgreSQL User

This script tests that the 'leaguestats_readonly' user has:
- ✅ SELECT permissions (read access)
- ❌ INSERT/UPDATE/DELETE/TRUNCATE permissions (blocked)

Usage:
    python scripts/test_readonly_permissions.py "postgresql://leaguestats_readonly:PASSWORD@HOST:5432/DB?sslmode=require"

Author: Database Expert
Date: 2026-02-11
"""

import sys
import psycopg2
from typing import Tuple
from dataclasses import dataclass


@dataclass
class TestResult:
    """Test result with status and message."""

    test_name: str
    expected: str
    passed: bool
    message: str


class ReadOnlyPermissionTester:
    """Tests READ-ONLY permissions on PostgreSQL database."""

    def __init__(self, connection_string: str):
        """Initialize with connection string."""
        self.connection_string = connection_string
        self.conn = None
        self.results = []

    def connect(self) -> bool:
        """Establish database connection."""
        try:
            self.conn = psycopg2.connect(self.connection_string)
            print("✅ Connection established successfully")
            return True
        except psycopg2.Error as e:
            print(f"❌ Connection failed: {e}")
            return False

    def test_select_permission(self) -> TestResult:
        """Test SELECT permission (should succeed)."""
        test_name = "SELECT Permission"
        expected = "SUCCESS"

        try:
            cursor = self.conn.cursor()
            cursor.execute("SELECT * FROM champions LIMIT 5;")
            rows = cursor.fetchall()
            cursor.close()

            passed = len(rows) > 0
            message = (
                f"✅ SELECT succeeded (fetched {len(rows)} rows)"
                if passed
                else "❌ SELECT failed (no rows returned)"
            )

        except psycopg2.Error as e:
            passed = False
            message = f"❌ SELECT failed with error: {e}"

        return TestResult(test_name, expected, passed, message)

    def test_insert_blocked(self) -> TestResult:
        """Test INSERT is blocked (should fail with permission denied)."""
        test_name = "INSERT Blocked"
        expected = "PERMISSION DENIED"

        try:
            cursor = self.conn.cursor()
            cursor.execute("INSERT INTO champions (name) VALUES ('TestChampion');")
            self.conn.commit()
            cursor.close()

            # If we reach here, INSERT succeeded (BAD!)
            passed = False
            message = "❌ INSERT succeeded (SECURITY RISK!)"

        except psycopg2.errors.InsufficientPrivilege:
            # Expected behavior
            self.conn.rollback()
            passed = True
            message = "✅ INSERT blocked (permission denied)"

        except psycopg2.Error as e:
            # Unexpected error
            self.conn.rollback()
            passed = False
            message = f"❌ INSERT failed with unexpected error: {e}"

        return TestResult(test_name, expected, passed, message)

    def test_update_blocked(self) -> TestResult:
        """Test UPDATE is blocked (should fail with permission denied)."""
        test_name = "UPDATE Blocked"
        expected = "PERMISSION DENIED"

        try:
            cursor = self.conn.cursor()
            cursor.execute("UPDATE champions SET name = 'Hacked' WHERE id = 1;")
            self.conn.commit()
            cursor.close()

            # If we reach here, UPDATE succeeded (BAD!)
            passed = False
            message = "❌ UPDATE succeeded (SECURITY RISK!)"

        except psycopg2.errors.InsufficientPrivilege:
            # Expected behavior
            self.conn.rollback()
            passed = True
            message = "✅ UPDATE blocked (permission denied)"

        except psycopg2.Error as e:
            # Unexpected error
            self.conn.rollback()
            passed = False
            message = f"❌ UPDATE failed with unexpected error: {e}"

        return TestResult(test_name, expected, passed, message)

    def test_delete_blocked(self) -> TestResult:
        """Test DELETE is blocked (should fail with permission denied)."""
        test_name = "DELETE Blocked"
        expected = "PERMISSION DENIED"

        try:
            cursor = self.conn.cursor()
            cursor.execute("DELETE FROM champions WHERE id = 1;")
            self.conn.commit()
            cursor.close()

            # If we reach here, DELETE succeeded (BAD!)
            passed = False
            message = "❌ DELETE succeeded (SECURITY RISK!)"

        except psycopg2.errors.InsufficientPrivilege:
            # Expected behavior
            self.conn.rollback()
            passed = True
            message = "✅ DELETE blocked (permission denied)"

        except psycopg2.Error as e:
            # Unexpected error
            self.conn.rollback()
            passed = False
            message = f"❌ DELETE failed with unexpected error: {e}"

        return TestResult(test_name, expected, passed, message)

    def test_truncate_blocked(self) -> TestResult:
        """Test TRUNCATE is blocked (should fail with permission denied)."""
        test_name = "TRUNCATE Blocked"
        expected = "PERMISSION DENIED"

        try:
            cursor = self.conn.cursor()
            cursor.execute("TRUNCATE TABLE champions;")
            self.conn.commit()
            cursor.close()

            # If we reach here, TRUNCATE succeeded (BAD!)
            passed = False
            message = "❌ TRUNCATE succeeded (SECURITY RISK!)"

        except psycopg2.errors.InsufficientPrivilege:
            # Expected behavior
            self.conn.rollback()
            passed = True
            message = "✅ TRUNCATE blocked (permission denied)"

        except psycopg2.Error as e:
            # Unexpected error
            self.conn.rollback()
            passed = False
            message = f"❌ TRUNCATE failed with unexpected error: {e}"

        return TestResult(test_name, expected, passed, message)

    def test_drop_blocked(self) -> TestResult:
        """Test DROP TABLE is blocked (should fail with permission denied)."""
        test_name = "DROP TABLE Blocked"
        expected = "PERMISSION DENIED"

        try:
            cursor = self.conn.cursor()
            cursor.execute("DROP TABLE champions;")
            self.conn.commit()
            cursor.close()

            # If we reach here, DROP succeeded (BAD!)
            passed = False
            message = "❌ DROP TABLE succeeded (CATASTROPHIC SECURITY RISK!)"

        except psycopg2.errors.InsufficientPrivilege:
            # Expected behavior
            self.conn.rollback()
            passed = True
            message = "✅ DROP TABLE blocked (permission denied)"

        except psycopg2.Error as e:
            # Unexpected error
            self.conn.rollback()
            passed = False
            message = f"❌ DROP TABLE failed with unexpected error: {e}"

        return TestResult(test_name, expected, passed, message)

    def run_all_tests(self) -> bool:
        """Run all permission tests."""
        print("\n" + "=" * 70)
        print("READ-ONLY Permission Test Suite")
        print("=" * 70 + "\n")

        # Test 1: SELECT (should work)
        result = self.test_select_permission()
        self.results.append(result)
        print(f"[1/6] {result.message}")

        # Test 2: INSERT (should be blocked)
        result = self.test_insert_blocked()
        self.results.append(result)
        print(f"[2/6] {result.message}")

        # Test 3: UPDATE (should be blocked)
        result = self.test_update_blocked()
        self.results.append(result)
        print(f"[3/6] {result.message}")

        # Test 4: DELETE (should be blocked)
        result = self.test_delete_blocked()
        self.results.append(result)
        print(f"[4/6] {result.message}")

        # Test 5: TRUNCATE (should be blocked)
        result = self.test_truncate_blocked()
        self.results.append(result)
        print(f"[5/6] {result.message}")

        # Test 6: DROP TABLE (should be blocked)
        result = self.test_drop_blocked()
        self.results.append(result)
        print(f"[6/6] {result.message}")

        # Summary
        total_tests = len(self.results)
        passed_tests = sum(1 for r in self.results if r.passed)
        all_passed = passed_tests == total_tests

        print("\n" + "=" * 70)
        print(f"Test Summary: {passed_tests}/{total_tests} tests passed")
        print("=" * 70)

        if all_passed:
            print("\n✅ ALL TESTS PASSED - READ-ONLY permissions verified!")
            print("   The user can SELECT but cannot INSERT/UPDATE/DELETE/TRUNCATE/DROP.")
        else:
            print("\n❌ SOME TESTS FAILED - Security issue detected!")
            print("   Review failed tests above.")

        return all_passed

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
            print("\n✅ Connection closed")


def main():
    """Main entry point."""
    if len(sys.argv) != 2:
        print("Usage: python scripts/test_readonly_permissions.py CONNECTION_STRING")
        print(
            '\nExample: python scripts/test_readonly_permissions.py "postgresql://leaguestats_readonly:PASSWORD@HOST:5432/DB?sslmode=require"'
        )
        sys.exit(1)

    connection_string = sys.argv[1]

    # Validate connection string format
    if not connection_string.startswith("postgresql://"):
        print("❌ Invalid connection string (must start with 'postgresql://')")
        sys.exit(1)

    # Run tests
    tester = ReadOnlyPermissionTester(connection_string)

    if not tester.connect():
        sys.exit(1)

    try:
        all_passed = tester.run_all_tests()
        exit_code = 0 if all_passed else 1
    finally:
        tester.close()

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
