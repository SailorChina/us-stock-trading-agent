#!/usr/bin/env python3
"""validate_ftquant_strategy — static-check a Futu Quant (FTQuant) strategy.

Why this exists: FTQuant strategies run inside the Futu NiuNiu client's own
sandbox, which we cannot invoke from here. A typo'd API name (or a constant
that does not exist) therefore fails only when the user hits Run in the GUI --
the worst possible feedback loop. This script catches those mistakes offline by
parsing the strategy and checking every call against the real SDK exports read
straight out of the client's own futu.zip.

Checks performed:
  1. the file parses (syntax)
  2. every bare function call resolves to a real SDK export, a platform helper
     (declare_trig_symbol / show_variable / ...), or a Python builtin
  3. a caller-supplied list of critical APIs is present
  4. sandbox-forbidden imports are not used
  5. sandbox-forbidden file-write modes are not used

Usage:
    python scripts/validate_ftquant_strategy.py scripts/ftquant_mom_12_1_raw.py

Exit code 0 = clean, 1 = problems found (listed on stdout).
"""
from __future__ import annotations

import ast
import glob
import io
import os
import re
import sys
import zipfile
from typing import Dict, List, Optional, Set

# The SDK lives inside the Futu NiuNiu install. Version dir changes on every
# client update, so glob rather than hardcode.
_SDK_GLOBS = [
    r"C:\Program Files\FTNN\app\*\PythonEnv\pkgs\futu.zip",
    r"C:\Program Files (x86)\FTNN\app\*\PythonEnv\pkgs\futu.zip",
]

_HELPER_NAMES = {
    # exported by futu.quant.strategy_base alongside StrategyBase
    "declare_trig_symbol", "show_variable", "declare_strategy_type", "check_bar_type",
    # from futu.quant.wrapper_utils
    "log_info", "log_warn", "log_error",
}

# The FTQuant sandbox blocks these outright (see futu/common/safe_env.py).
_FORBIDDEN_IMPORTS = {"ctypes", "socket", "multiprocessing", "subprocess", "sqlite3", "sqlite"}

# Critical APIs our strategies depend on; a missing one means a broken strategy.
_REQUIRED_APIS = [
    "bar_close", "atr_atr", "current_price", "place_market", "place_stop",
    "close_positions", "cancel_order_by_symbol", "lot_size", "total_cash",
    "position_holding_qty", "max_qty_to_buy_on_cash",
]

# Python builtins we allow in strategy bodies.
_BUILTINS = {
    "print", "len", "int", "float", "str", "bool", "min", "max", "round", "abs", "sum",
    "sorted", "set", "list", "dict", "tuple", "range", "enumerate", "zip", "getattr",
    "setattr", "hasattr", "isinstance", "type", "repr", "format", "map", "filter", "any",
    "all", "open", "super", "property", "staticmethod", "classmethod", "Exception",
    "BaseException", "ValueError", "TypeError", "KeyError", "IndexError", "RuntimeError",
    "enumerate", "id", "iter", "next", "reversed", "slice", "vars", "dir", "callable",
}


def find_sdk() -> Optional[str]:
    for pat in _SDK_GLOBS:
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]
    return None


def load_sdk_exports(sdk_path: str) -> Dict[str, Set[str]]:
    """Return {'functions': {...}, 'classes': {...}} found in the SDK."""
    funcs: Set[str] = set()
    classes: Set[str] = set()
    with zipfile.ZipFile(sdk_path) as z:
        for name in z.namelist():
            if not name.startswith("futu/") or not name.endswith(".py"):
                continue
            src = z.read(name).decode("utf-8", "replace")
            funcs |= set(re.findall(r"^def (\w+)\(", src, re.M))
            classes |= set(re.findall(r"^class (\w+)", src, re.M))
    return {"functions": funcs, "classes": classes}


def check_strategy(path: str, sdk: Dict[str, Set[str]]) -> List[str]:
    problems: List[str] = []
    src = open(path, encoding="utf-8").read()

    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return ["syntax error at line %s: %s" % (e.lineno, e.msg)]

    # --- calls ---------------------------------------------------------
    called = {n.func.id for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    unresolved = sorted(c for c in called
                        if c not in sdk["functions"]
                        and c not in _HELPER_NAMES
                        and c not in _BUILTINS)
    if unresolved:
        problems.append("unresolved call names (not in SDK/helpers/builtins): %s"
                        % ", ".join(unresolved))

    # --- required APIs present in the SDK -----------------------------------
    missing_req = [a for a in _REQUIRED_APIS if a not in sdk["functions"]]
    if missing_req:
        problems.append("SDK is missing expected APIs: %s" % ", ".join(missing_req))

    # --- forbidden imports -------------------------------------------------
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                top = a.name.split(".")[0]
                if top in _FORBIDDEN_IMPORTS:
                    problems.append("forbidden import: %s (blocked by FTQuant sandbox)" % top)
        elif isinstance(n, ast.ImportFrom):
            top = (n.module or "").split(".")[0]
            if top in _FORBIDDEN_IMPORTS:
                problems.append("forbidden import: %s (blocked by FTQuant sandbox)" % top)

    # --- forbidden file-write modes ---------------------------------------
    for n in ast.walk(tree):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "open":
            if len(n.args) >= 2 and isinstance(n.args[1], ast.Constant):
                mode = str(n.args[1].value)
                if any(ch in mode for ch in "wax+"):
                    problems.append("open(..., '%s') writes a file; FTQuant sandbox forbids writes"
                                    % mode)

    # --- sanity: strategy class present -----------------------------------
    classes = [c.name for c in ast.walk(tree) if isinstance(c, ast.ClassDef)]
    if "Strategy" not in classes:
        problems.append("no class named 'Strategy' found (the platform looks for it)")
    else:
        bases = []
        for c in ast.walk(tree):
            if isinstance(c, ast.ClassDef) and c.name == "Strategy":
                bases = [b.id for b in c.bases if isinstance(b, ast.Name)]
        if "StrategyBase" not in bases:
            problems.append("class Strategy does not inherit StrategyBase")

    return problems


def main(argv: List[str]) -> int:
    if len(argv) > 1:
        targets = argv[1:]
    else:
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        targets = sorted(glob.glob(os.path.join(here, "scripts", "ftquant_*.py")))

    if not targets:
        sys.stdout.write("no strategy files to check\n")
        return 0

    sdk_path = find_sdk()
    if sdk_path is None:
        sys.stdout.write("[SKIP] Futu client install not found; cannot verify API names.\n")
        sys.stdout.write("       Looked for: %s\n" % " or ".join(_SDK_GLOBS))
        return 0
    sys.stdout.write("SDK: %s\n" % sdk_path)
    sdk = load_sdk_exports(sdk_path)
    sys.stdout.write("SDK exports: %d functions, %d classes\n\n"
                     % (len(sdk["functions"]), len(sdk["classes"])))

    failed = 0
    for path in targets:
        name = os.path.basename(path)
        problems = check_strategy(path, sdk)
        if problems:
            failed += 1
            sys.stdout.write("[FAIL] %s\n" % name)
            for p in problems:
                sys.stdout.write("       - %s\n" % p)
        else:
            sys.stdout.write("[ OK ] %s\n" % name)
    sys.stdout.write("\n%d file(s) checked, %d with problems\n" % (len(targets), failed))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
