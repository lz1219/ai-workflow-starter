import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "skills/relay-onboard/scripts/skill_audit.py"


class SkillAuditTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name) / "skills"
        self.demo = self.root / "demo"
        self.demo.mkdir(parents=True)
        (self.demo / "references").mkdir()
        (self.demo / "SKILL.md").write_text(
            "---\n"
            "name: demo\n"
            "description: Demo skill for audit tests.\n"
            "---\n\n"
            "# Demo\n\n"
            "Read [one](references/one.md).\n",
            encoding="utf-8",
        )
        (self.demo / "references/one.md").write_text(
            "# One\n\nRead [two](two.md).\n", encoding="utf-8"
        )
        (self.demo / "references/two.md").write_text("# Two\n", encoding="utf-8")

    def run_audit(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--skills", str(self.root), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )

    def test_json_reports_entry_and_reachable_tokens(self):
        result = self.run_audit("--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        report = json.loads(result.stdout)["skills"][0]
        self.assertEqual(report["name"], "demo")
        self.assertGreater(report["entry_tokens"], 0)
        self.assertGreaterEqual(report["reachable_tokens"], report["entry_tokens"])
        self.assertEqual(report["reference_files"], 2)
        self.assertEqual(report["warnings"], [])

    def test_orphan_reference_is_a_warning_and_strict_fails(self):
        (self.demo / "references/orphan.md").write_text("# Orphan\n", encoding="utf-8")
        result = self.run_audit("--json")
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        self.assertTrue(any("orphan.md" in warning for warning in payload["warnings"]))
        strict = self.run_audit("--strict")
        self.assertEqual(strict.returncode, 1, strict.stdout)

    def test_missing_front_matter_and_name_mismatch_are_reported(self):
        (self.demo / "SKILL.md").write_text(
            "# Demo\n\nRead [one](references/one.md).\n", encoding="utf-8"
        )
        result = self.run_audit("--json")
        payload = json.loads(result.stdout)
        warnings = payload["warnings"]
        self.assertTrue(any("front matter" in warning for warning in warnings))
        self.assertTrue(any("description" in warning for warning in warnings))

    def test_broken_link_is_reported(self):
        (self.demo / "SKILL.md").write_text(
            "---\nname: demo\ndescription: Demo.\n---\n\n"
            "Read [missing](references/missing.md).\n",
            encoding="utf-8",
        )
        result = self.run_audit("--json")
        payload = json.loads(result.stdout)
        self.assertTrue(any("不存在" in warning for warning in payload["warnings"]))

    def test_missing_skills_directory_returns_two(self):
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--skills", str(self.root / "missing")],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        self.assertEqual(result.returncode, 2)


if __name__ == "__main__":
    unittest.main()