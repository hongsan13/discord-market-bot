"""Syntax + offline tests. No production entry point and no Discord credentials."""
import ast
import hashlib
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def protected_hashes(root):
    paths = ("data/reports.json", "docs/data/reports.json", "docs/index.html",
             "web/index.html", ".github/workflows/daily_discord_report.yml")
    return {p: hashlib.sha256((root / p).read_bytes()).hexdigest()
            if (root / p).is_file() else None for p in paths}


def run_checks(root):
    before = protected_hashes(root)
    source = [root / "market_discord_bot.py"]
    for directory in ("tests", "scripts", "weekly"):
        source.extend(sorted((root / directory).glob("*.py")))
    for path in source:
        ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path),
                  feature_version=(3, 11))
    if not (root / "tests/test_strategy_v7.py").is_file():
        raise RuntimeError("Expected v7 tests are missing; refusing an empty test run.")
    suite = unittest.TestSuite()
    # Block real connections during both import/discovery and execution.
    with patch("socket.socket.connect", side_effect=AssertionError("Live network forbidden")), \
         patch("socket.socket.connect_ex", side_effect=AssertionError("Live network forbidden")), \
         patch("socket.create_connection", side_effect=AssertionError("Live network forbidden")):
        for directory in ("tests", "weekly"):
            if (root / directory).is_dir():
                suite.addTests(unittest.TestLoader().discover(
                    str(root / directory), pattern="test_*.py"))
        if not suite.countTestCases():
            raise RuntimeError("No tests found.")
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    after = protected_hashes(root)
    changed = [path for path in before if before[path] != after[path]]
    if changed:
        raise RuntimeError("Protected files changed; inspect without resetting: " + ", ".join(changed))
    print("Protected state, history, dashboard and schedule: unchanged.")
    return 0 if result.wasSuccessful() else 1


def main():
    if sys.version_info[:2] not in ((3, 11), (3, 12)):
        raise SystemExit("Use Python 3.11 or 3.12 from the local .venv.")
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(ROOT))
    os.chdir(ROOT)
    for key in ("DISCORD_WEBHOOK_URL", "GITHUB_TOKEN", "GH_TOKEN", "OPENAI_API_KEY"):
        os.environ.pop(key, None)
    return run_checks(ROOT)


if __name__ == "__main__":
    raise SystemExit(main())
