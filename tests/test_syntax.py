"""Test: all scripts compile without syntax errors."""
import ast, os, sys

SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "..", "scripts")

def test_all_scripts_compile():
    """Every .py file in scripts/ must parse as valid Python."""
    py_files = [f for f in os.listdir(SCRIPTS_DIR) if f.endswith(".py") and not f.startswith("__")]
    assert len(py_files) >= 14, f"Expected >= 14 scripts, found {len(py_files)}"
    errors = []
    for fname in sorted(py_files):
        path = os.path.join(SCRIPTS_DIR, fname)
        try:
            with open(path, encoding="utf-8-sig") as f:  # utf-8-sig strips BOM
                ast.parse(f.read())
        except SyntaxError as e:
            errors.append(f"{fname}:{e.lineno} {e.msg}")
    if errors:
        raise AssertionError("\n".join(errors))
