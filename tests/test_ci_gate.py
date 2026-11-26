import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "skills/relay-change/scripts/ci_gate.py"
REQUIREMENTS = ROOT / "skills/relay-change/scripts/requirements.py"

DESIGN = """---
title: "导出"
depends_on: []
follows: []
related: []
---

# 导出

## 1. 需求与验收

| 编号 | 场景与触发条件 | 预期结果 |
|---|---|---|
| AC-1 | 正常导出 | 下载文件 |
| AC-2 | 上线前对账 | CSV 与台账一致 |

## 2. 现状与技术方案

入口为 `export.py`。

## 3. 实施、验证与发布

| 验收项 | 验证安排 | 任务或证据链接 |
|---|---|---|
| AC-2 | 用脱敏台账手工核对 | — |
"""

TASKS = """# 任务看板

设计见 [design.md](design.md)。

| 编号 | 计划任务 | 状态 | 验收项 | 实际完成内容 | 证据或交接 |
|---|---|---|---|---|---|
| T1 | 正常导出 | 待办 | AC-1 | — | — |
"""


class CiGateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name).resolve()
        self.requirement = self.project / "docs/design/Req-20261126-导出"
        self.requirement.mkdir(parents=True)
        (self.requirement / "design.md").write_text(DESIGN, encoding="utf-8")
        (self.requirement / "tasks.md").write_text(TASKS, encoding="utf-8")
        self.git("init", "-q")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "core.autocrlf", "false")
        written = self.run_requirements("--write")
        self.assertEqual(written.returncode, 0, written.stderr)
        self.commit()

    def git(self, *args):
        return subprocess.run(
            ["git", "-C", str(self.project), *args], capture_output=True, check=True
        )

    def commit(self):
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")

    def run_requirements(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(REQUIREMENTS), "--project", str(self.project), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )

    def run_gate(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(GATE), "--project", str(self.project), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )

    def test_task_and_legacy_verification_table_cover_distinct_criteria(self):
        result = self.run_gate("--base", "HEAD", "--all")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("均通过", result.stdout)

    def test_uncovered_acceptance_item_fails(self):
        design = (self.requirement / "design.md").read_text(encoding="utf-8")
        design = design.replace(
            "| AC-2 | 上线前对账 | CSV 与台账一致 |",
            "| AC-2 | 上线前对账 | CSV 与台账一致 |\n| AC-3 | 空结果 | 只含表头 |",
        )
        (self.requirement / "design.md").write_text(design, encoding="utf-8")
        refreshed = self.run_requirements("--write")
        self.assertEqual(refreshed.returncode, 0, refreshed.stderr)

        result = self.run_gate("--base", "HEAD", "--all")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("AC-3 缺少关联任务或验证安排", result.stdout)

    def test_changed_requirement_is_detected_from_working_tree(self):
        tasks = (self.requirement / "tasks.md").read_text(encoding="utf-8")
        (self.requirement / "tasks.md").write_text(
            tasks.replace("| T1 | 正常导出 | 待办 |", "| T1 | 正常导出（修订） | 待办 |"),
            encoding="utf-8",
        )
        refreshed = self.run_requirements("--write")
        self.assertEqual(refreshed.returncode, 0, refreshed.stderr)

        result = self.run_gate("--base", "HEAD", "--json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["changed"], ["Req-20261126-导出"])
        self.assertTrue(payload["ok"])

    def test_stale_board_fails_check(self):
        board = self.project / "docs/design/README.md"
        text = board.read_text(encoding="utf-8")
        marker = "<!-- /ai-workflow:board -->"
        self.assertIn(marker, text)
        board.write_text(
            text.replace(marker, "| 过期行 | — | — | — | — | — |\n" + marker, 1),
            encoding="utf-8",
        )
        result = self.run_gate("--base", "HEAD", "--all")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn("[失败] check", result.stdout)
        self.assertIn("看板需重新生成", result.stdout)

    def test_untracked_requirement_is_detected(self):
        other = self.project / "docs/design/Req-20261126-新增"
        other.mkdir()
        (other / "design.md").write_text(
            DESIGN.replace("导出", "新增").replace("AC-1", "AC-1"),
            encoding="utf-8",
        )
        (other / "tasks.md").write_text(TASKS, encoding="utf-8")
        refreshed = self.run_requirements("--write")
        self.assertEqual(refreshed.returncode, 0, refreshed.stderr)

        result = self.run_gate("--base", "HEAD", "--json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["changed"], ["Req-20261126-新增"])

    def test_missing_project_returns_two(self):
        result = subprocess.run(
            [sys.executable, "-B", str(GATE), "--project", str(self.project / "missing")],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        self.assertEqual(result.returncode, 2)

    def test_unknown_base_returns_two(self):
        result = self.run_gate("--base", "no-such-revision")
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
