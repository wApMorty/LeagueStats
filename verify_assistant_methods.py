"""
Verification script to check if all Assistant method calls are valid.

This script:
1. Parses assistant.py to find all available methods
2. Searches the codebase for all Assistant method calls
3. Reports any missing methods
"""

import re
import ast
from pathlib import Path

def get_assistant_methods():
    """Extract all method names from the Assistant class."""
    assistant_path = Path("src/assistant.py")

    with open(assistant_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Parse the AST
    tree = ast.parse(content)

    methods = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "Assistant":
            for item in node.body:
                if isinstance(item, ast.FunctionDef):
                    methods.append(item.name)

    return set(methods)

def find_assistant_method_calls():
    """Find all assistant.method() calls in the codebase."""
    method_calls = {}

    # Patterns to search for
    patterns = [
        r'self\.assistant\.(\w+)\(',  # self.assistant.method()
        r'assistant\.(\w+)\(',         # assistant.method()
        r'ast\.(\w+)\(',               # ast.method()
    ]

    # Files to search
    src_files = list(Path("src").rglob("*.py"))
    src_files.append(Path("main.py"))

    for filepath in src_files:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()

            for pattern in patterns:
                matches = re.findall(pattern, content)
                for method_name in matches:
                    if method_name not in method_calls:
                        method_calls[method_name] = []
                    method_calls[method_name].append(str(filepath))

        except Exception as e:
            print(f"Error reading {filepath}: {e}")

    return method_calls

def main():
    print("=" * 80)
    print("ASSISTANT METHOD VERIFICATION")
    print("=" * 80)

    # Get available methods
    available_methods = get_assistant_methods()
    print(f"\n[OK] Found {len(available_methods)} methods in Assistant class:")
    for method in sorted(available_methods):
        print(f"   - {method}")

    # Get method calls
    method_calls = find_assistant_method_calls()
    print(f"\n[SEARCH] Found {len(method_calls)} unique method calls in codebase:")

    # Check for missing methods
    missing_methods = {}
    valid_methods = {}

    for method, locations in method_calls.items():
        # Filter out built-in methods and properties
        if method.startswith('__') or method in ['db', 'close', 'verbose', 'MIN_GAMES']:
            continue

        if method not in available_methods:
            missing_methods[method] = locations
        else:
            valid_methods[method] = locations

    # Report results
    print(f"\n[VALID] VALID METHOD CALLS ({len(valid_methods)}):")
    for method in sorted(valid_methods.keys()):
        locations_count = len(set(valid_methods[method]))
        print(f"   - {method} (used in {locations_count} files)")

    if missing_methods:
        print(f"\n[ERROR] MISSING METHODS ({len(missing_methods)}):")
        print("=" * 80)
        for method, locations in sorted(missing_methods.items()):
            unique_locations = sorted(set(locations))
            print(f"\n[MISSING] {method}()")
            print(f"   Called in {len(unique_locations)} file(s):")
            for loc in unique_locations:
                print(f"      - {loc}")

        print("\n" + "=" * 80)
        print("[ACTION REQUIRED]")
        print(f"   {len(missing_methods)} methods are called but not defined in Assistant!")
        print("=" * 80)
        return 1
    else:
        print("\n" + "=" * 80)
        print("[SUCCESS] All method calls are valid!")
        print("=" * 80)
        return 0

if __name__ == "__main__":
    exit(main())
