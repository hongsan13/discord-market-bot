import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / (name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DevelopmentToolsTests(unittest.TestCase):
    def test_hashes_detect_changed_or_missing_state(self):
        checker = load_script("check_dev")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "data").mkdir()
            state = root / "data/reports.json"
            state.write_text('{"reports": [1]}', encoding="utf-8")
            before = checker.protected_hashes(root)
            self.assertIsNone(before["docs/data/reports.json"])
            state.write_text('{"reports": [1, 2]}', encoding="utf-8")
            self.assertNotEqual(before, checker.protected_hashes(root))

    def test_missing_tests_fail_closed(self):
        checker = load_script("check_dev")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "market_discord_bot.py").write_text("x = 1\n", encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "tests are missing"):
                checker.run_checks(root)

    def test_offline_setup_does_not_create_or_install(self):
        setup = load_script("setup_dev")
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(setup, "ROOT", Path(temp)), \
             patch.object(sys, "argv", ["setup_dev.py", "--skip-install"]), \
             patch.object(setup.subprocess, "run") as run, \
             contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                setup.main()
            run.assert_not_called()
            self.assertFalse((Path(temp) / ".venv").exists())

    def test_incomplete_environment_is_not_overwritten(self):
        setup = load_script("setup_dev")
        with tempfile.TemporaryDirectory() as temp, \
             patch.object(setup, "ROOT", Path(temp)), \
             patch.object(sys, "argv", ["setup_dev.py"]), \
             patch.object(setup.subprocess, "run") as run, \
             contextlib.redirect_stderr(io.StringIO()):
            env = Path(temp) / ".venv"
            env.mkdir()
            marker = env / "keep.txt"
            marker.write_text("existing data", encoding="utf-8")
            with self.assertRaises(SystemExit):
                setup.main()
            run.assert_not_called()
            self.assertEqual(marker.read_text(encoding="utf-8"), "existing data")

    def test_old_python_fails_before_environment_changes(self):
        setup = load_script("setup_dev")
        with patch.object(sys, "argv", ["setup_dev.py"]), \
             patch.object(sys, "version_info", (3, 9, 0)), \
             patch.object(setup.subprocess, "run") as run, \
             contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                setup.main()
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
