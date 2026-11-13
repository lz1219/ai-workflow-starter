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

    def test_review_reports_uncovered_and_cancelled_criteria_without_changing_board(self):
        requirement = self.design_root / "Req-20261113-数据导出"
        requirement.mkdir(parents=True)
        design_template = SCRIPT.parent.parent / "assets/design.md"
        design = design_template.read_text(encoding="utf-8")
        (requirement / "design.md").write_text(
            design.replace(
                "| AC-1 | 填写核心场景 | 填写可验证结果 |",
                "| AC-1 | 正常导出 | 下载文件 |\n"
                "| AC-2 | 跨部门 | HTTP 403 |\n"
                "| AC-3 | 正式数据 | 记录对账差异 |\n"
                "| AC-4 | 空结果 | CSV 仅有表头 |\n"
                "| AC-5 | 无权访问 | HTTP 403 |\n"
                "| AC-6 | 重复请求 | 响应一致 |",
            ).replace(
                "| AC-1 | 测试、命令或手工步骤 | 实现后填写 |",
                "| AC-3 | 收到脱敏台账后按部门对账（已确认延期） | — |\n"
                "| AC-4 | 手工导出空结果，核对文件只含表头 | — |\n"
                "| AC-5 | 测试、命令或手工步骤 | 实现后填写 |\n"
                "| AC-6 | — | 上次发布的重试回归测试，契约一致 |\n\n"
                "```markdown\n"
                "| 验收项 | 验证方式 |\n"
                "|---|---|\n"
                "| AC-5 | 这里只是示例 |\n"
                "```",
            ),
            encoding="utf-8",
        )
        tasks_template = SCRIPT.parent.parent / "assets/tasks.md"
        (requirement / "tasks.md").write_text(
            tasks_template.read_text(encoding="utf-8").replace(
                "| T1 | 填写要交付的结果 | 待办 | AC-1 | — | — |",
                "| T1 | 正常导出下载文件 | 待办 | AC-1 | — | — |\n"
                "| T2 | 跨部门请求返回 403 | 取消 | AC-2 | — | — |",
            ),
            encoding="utf-8",
        )
        generated = self.run_board(self.project, "--write")
        self.assertEqual(generated.returncode, 0, generated.stderr)
        before = self.board.read_bytes()

        reviewed = self.run_board(self.project, "--review", requirement.name)
        self.assertEqual(reviewed.returncode, 0, reviewed.stderr)
        self.assertIn("AC-2 缺少关联任务或验证安排", reviewed.stderr)
        self.assertIn("AC-5 缺少关联任务或验证安排", reviewed.stderr)
        for criterion in ("AC-1", "AC-3", "AC-4", "AC-6"):
            self.assertNotIn(criterion, reviewed.stderr)
        self.assertEqual(self.board.read_bytes(), before)
        checked = self.run_board(self.project, "--check")
        self.assertEqual(checked.returncode, 0, checked.stderr)

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
