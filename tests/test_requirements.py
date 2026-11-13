from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "skills/change-design/scripts/requirements.py"


class RequirementsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.project = Path(temporary.name)
        self.design_root = self.project / "docs/design"
        self.board = self.design_root / "README.md"

    def run_board(self, project, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), "--project", str(project), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )

    def test_write_rejects_missing_project_without_creating_it(self):
        missing = self.project / "missing"
        result = self.run_board(missing, "--write")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("项目目录不存在", result.stderr)
        self.assertFalse(missing.exists())

    def test_blocker_appears_after_refresh(self):
        requirement = self.design_root / "Req-20261113-数据导出"
        requirement.mkdir(parents=True)
        (requirement / "design.md").write_text(
            '---\ntitle: "数据导出"\n---\n\n| AC-1 | 导出 | 下载文件 |\n',
            encoding="utf-8",
        )
        tasks = requirement / "tasks.md"
        template = SCRIPT.parent.parent / "assets/tasks.md"
        tasks.write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
        initial = self.run_board(self.project, "--write")
        self.assertEqual(initial.returncode, 0, initial.stderr)
        self.assertNotIn("## 阻塞任务", self.board.read_text(encoding="utf-8"))

        task_text = tasks.read_text(encoding="utf-8")
        blocked = "| T1 | 正式数据验收 | 阻塞 | AC-1 | 隔离测试通过 | 等待上游样例后对账 |"
        tasks.write_text(
            task_text.replace("| T1 | 填写要交付的结果 | 待办 | AC-1 | — | — |", blocked),
            encoding="utf-8",
        )
        stale = self.run_board(self.project, "--check")
        self.assertEqual(stale.returncode, 1, stale.stderr)
        self.assertIn("看板需重新生成", stale.stderr)
        refreshed = self.run_board(self.project, "--write")
        self.assertEqual(refreshed.returncode, 0, refreshed.stderr)
        checked = self.run_board(self.project, "--check")
        self.assertEqual(checked.returncode, 0, checked.stderr)
        content = self.board.read_text(encoding="utf-8")
        self.assertIn("## 阻塞任务", content)
        self.assertIn("[数据导出 / T1]", content)
        self.assertIn("等待上游样例后对账", content)

        tasks.write_text(
            tasks.read_text(encoding="utf-8").replace("等待上游样例后对账", "—"),
            encoding="utf-8",
        )
        invalid = self.run_board(self.project, "--write")
        self.assertEqual(invalid.returncode, 1, invalid.stderr)
        self.assertIn("阻塞时须记录", invalid.stderr)
        self.assertEqual(self.board.read_text(encoding="utf-8"), content)
