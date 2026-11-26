import json
import os
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / "skills"
AUDIT = SKILLS / "relay-onboard/scripts/skill_audit.py"


class WorkflowAssetTests(unittest.TestCase):
    def test_repository_skills_audit_without_warnings(self):
        result = subprocess.run(
            [sys.executable, "-B", str(AUDIT), "--skills", str(SKILLS), "--strict"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("未发现", result.stdout)

    def test_presets_are_valid_json_with_required_keys(self):
        presets = sorted((SKILLS / "relay-onboard/assets/presets").glob("*.json"))
        self.assertTrue(presets)
        for path in presets:
            data = json.loads(path.read_text(encoding="utf-8"))
            for key in ("name", "stack", "runtime", "build", "conventions"):
                self.assertIn(key, data, path.name)
            self.assertIn("commands", data["build"], path.name)

    def test_design_check_template_uses_the_gate_and_keeps_base_sha(self):
        text = (SKILLS / "relay-change/assets/design-check.yml").read_text(encoding="utf-8")
        self.assertIn("ci_gate.py", text)
        self.assertIn("BASE_SHA", text)
        self.assertIn("fetch-depth: 0", text)

    def test_overlay_template_names_conflict_and_review_rules(self):
        text = (SKILLS / "relay-onboard/assets/overlay.md").read_text(encoding="utf-8")
        for phrase in ("target:", "covers:", "覆盖方式", "与上游冲突时", "复核条件"):
            self.assertIn(phrase, text)

    def test_coverage_matrix_lists_known_and_unknown_paths(self):
        text = (SKILLS / "relay-onboard/references/README.md").read_text(encoding="utf-8")
        for phrase in ("java-spring.md", "python.md", "node.md", "未知技术栈", "_template.md"):
            self.assertIn(phrase, text)

    def test_design_template_records_impact_surface_without_file_list(self):
        text = (SKILLS / "relay-change/assets/design.md").read_text(encoding="utf-8")
        for phrase in ("影响面", "明确不改", "不逐文件罗列", "PR 的 diff"):
            self.assertIn(phrase, text)

    def test_onboarding_report_template_is_a_checkable_delivery(self):
        text = (SKILLS / "relay-onboard/assets/onboarding-report.md").read_text(encoding="utf-8")
        for phrase in ("结论", "已证实的项目约定", "基线验证", "待确认清单"):
            self.assertIn(phrase, text)


if __name__ == "__main__":
    unittest.main()