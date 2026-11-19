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
            '---\ntitle: "数据导出"\n---\n\n## 需求与验收\n| AC-1 | 导出 | 下载文件 |\n',
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

    def create_requirement(self, extra=""):
        requirement = self.design_root / "Req-example"
        requirement.mkdir(parents=True)
        (requirement / "design.md").write_text(
            '---\ntitle: "Example"\n---\n## 1. 需求与验收\n'
            '| AC-1 | input | output |\n' + extra, encoding="utf-8")
        (requirement / "tasks.md").write_text(
            (SCRIPT.parent.parent / "assets/tasks.md").read_text(encoding="utf-8"), encoding="utf-8")
        return requirement

    def test_unknown_verification_reference_is_not_a_definition(self):
        requirement = self.create_requirement(
            '## 3. 实施、验证与发布\n| 验收项 | 验证方式 |\n|---|---|\n| AC-999 | test |\n')
        tasks = requirement / "tasks.md"
        tasks.write_text(tasks.read_text(encoding="utf-8").replace("AC-1", "AC-999"), encoding="utf-8")
        for mode in (("--write",), ("--review", requirement.name)):
            with self.subTest(mode=mode):
                result = self.run_board(self.project, *mode)
                self.assertEqual(result.returncode, 1)
                self.assertIn("未知验收项", result.stderr)
        self.assertFalse(self.board.exists())

    def test_duplicate_definitions_are_rejected(self):
        self.create_requirement('| AC-1 | another input | conflicting output |\n')
        result = self.run_board(self.project, "--write")
        self.assertEqual(result.returncode, 1)
        self.assertIn("重复验收编号", result.stderr)

    def test_fenced_examples_cannot_define_acceptance(self):
        requirement = self.create_requirement('```md\n| AC-999 | example | example |\n```\n')
        tasks = requirement / "tasks.md"
        tasks.write_text(tasks.read_text(encoding="utf-8").replace("AC-1", "AC-999"), encoding="utf-8")
        result = self.run_board(self.project, "--write")
        self.assertEqual(result.returncode, 1)
        self.assertIn("未知验收项", result.stderr)

    def test_table_whitespace_and_fenced_task_examples_are_accepted(self):
        requirement = self.create_requirement()
        tasks = requirement / "tasks.md"
        original = tasks.read_text(encoding="utf-8")
        tasks.write_text('```md\n' + original + '\n```\n' + original.replace(' | ', '|'), encoding="utf-8")
        result = self.run_board(self.project, "--write")
        self.assertEqual(result.returncode, 0, result.stderr)
        reviewed = self.run_board(self.project, "--review", requirement.name)
        self.assertEqual(reviewed.returncode, 0, reviewed.stderr)
        self.assertIn("不代表验收通过", reviewed.stdout)

    def test_team_index_is_preserved_until_a_region_is_selected(self):
        self.create_requirement()
        start = b"<!-- ai-workflow:board -->"
        end = b"<!-- /ai-workflow:board -->"
        prefix = b"\xef\xbb\xbf# Team index\r\n\r\n```md\r\n" + start + b"\r\n" + end + b"\r\n```\r\n"
        suffix = b"\r\n## Release notes\r\nKeep this note."
        for markers in (b"", start, end, end + b"\r\n" + start, start + b"\r\n" + start + b"\r\n" + end):
            with self.subTest(markers=markers):
                original = prefix + markers + suffix
                self.board.write_bytes(original)
                result = self.run_board(self.project, "--write")
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertEqual(self.board.read_bytes(), original)
        self.board.write_bytes(prefix + start + b"\r\n" + end + suffix)
        self.assertEqual(self.run_board(self.project, "--check").returncode, 1)
        self.assertEqual(self.run_board(self.project, "--write").returncode, 0)
        generated = self.board.read_bytes()
        self.assertTrue(generated.startswith(prefix + start + b"\r\n"))
        self.assertTrue(generated.endswith(end + suffix))
        self.assertIn(b"Req-example/design.md", generated)
        self.assertNotIn(b"\n", generated.replace(b"\r\n", b""))
        self.assertEqual(self.run_board(self.project, "--check").returncode, 0)
        self.assertEqual(self.run_board(self.project, "--write").returncode, 0)
        self.assertEqual(self.board.read_bytes(), generated)

    def test_legacy_board_refreshes_but_mixed_legacy_index_requires_opt_in(self):
        self.create_requirement()
        preview = self.run_board(self.project)
        self.assertEqual(preview.returncode, 0, preview.stderr)
        legacy = preview.stdout
        self.board.write_text(legacy, encoding="utf-8")
        self.assertEqual(self.run_board(self.project, "--check").returncode, 0)
        extra = legacy + "\n## Release notes\nHandwritten\n"
        self.board.write_text(extra, encoding="utf-8")
        self.assertEqual(self.run_board(self.project, "--write").returncode, 1)
        self.assertEqual(self.board.read_text(encoding="utf-8"), extra)
        self.board.write_text(legacy.replace("待办 1", "待办 2"), encoding="utf-8")
        self.assertEqual(self.run_board(self.project, "--check").returncode, 1)
        self.assertEqual(self.run_board(self.project, "--write").returncode, 0)
        self.assertIn("<!-- ai-workflow:board -->", self.board.read_text(encoding="utf-8"))
        self.assertIn("待办 1", self.board.read_text(encoding="utf-8"))

    def test_detached_blocked_task_is_reported_before_board_is_replaced(self):
        requirement = self.create_requirement()
        tasks = requirement / "tasks.md"
        original = tasks.read_text(encoding="utf-8")
        self.assertEqual(self.run_board(self.project, "--write").returncode, 0)
        before = self.board.read_bytes()
        blocked = "| T2 | 等待样本 | 阻塞 | AC-1 | — | 上游提供样本后验收 |"
        for location in ("before", "after"):
            with self.subTest(location=location):
                detached = blocked + "\n\n" + original if location == "before" else original + "\n" + blocked
                tasks.write_text(detached, encoding="utf-8")
                result = self.run_board(self.project, "--write")
                self.assertEqual(result.returncode, 1)
                self.assertIn("T2 位于标准任务表之外", result.stderr)
                self.assertEqual(self.board.read_bytes(), before)
        tasks.write_text(original.replace("| — | — |\n", "| — | — |\n" + blocked + "\n"), encoding="utf-8")
        self.assertEqual(self.run_board(self.project, "--write").returncode, 0)
        self.assertIn("上游提供样本后验收", self.board.read_text(encoding="utf-8"))

    def test_checks_report_table_and_independent_row_errors_without_writing(self):
        requirement = self.create_requirement("| AC-2 | another input | another output |\n")
        tasks = requirement / "tasks.md"
        original = tasks.read_text(encoding="utf-8")
        self.assertEqual(self.run_board(self.project, "--write").returncode, 0)
        board_before = self.board.read_bytes()
        header = next(line for line in original.splitlines() if line.startswith("| 编号"))
        broken = original + (
            f"\n{header}\n|---|---|---|---|---|---|\n"
            "| T2 | 复验 | 完成（按回执覆盖范围） | AC-1、回归 AC-1 至 AC-2 | 已复验 | 浏览器报告 |\n"
            "\n| T3 | 等待真实数据 | 阻塞 | AC-404 | — | — |\n"
        )
        tasks.write_text(broken, encoding="utf-8")
        task_before = tasks.read_bytes()
        row_number = next(i for i, line in enumerate(broken.splitlines(), 1) if line.startswith("| T2"))

        for mode in (("--check",), ("--write",), ("--review", requirement.name)):
            with self.subTest(mode=mode):
                result = self.run_board(self.project, *mode)
                self.assertEqual(result.returncode, 1, result.stderr)
                self.assertIn(f"tasks.md:{row_number}: T2 的状态无效", result.stderr)
                self.assertIn("T2 的验收项格式无效", result.stderr)
                self.assertIn("应包含一份标准任务表", result.stderr)
                self.assertIn("T3 位于标准任务表之外", result.stderr)
                self.assertIn("T3 引用了未知验收项：AC-404", result.stderr)
                self.assertIn("T3 阻塞时须记录", result.stderr)
                self.assertEqual(self.board.read_bytes(), board_before)
                self.assertEqual(tasks.read_bytes(), task_before)

    def test_check_reports_errors_in_independent_requirements(self):
        first = self.create_requirement()
        second = self.design_root / "Req-second"
        second.mkdir()
        (second / "design.md").write_bytes((first / "design.md").read_bytes())
        template = (first / "tasks.md").read_text(encoding="utf-8")
        (first / "tasks.md").write_text(template.replace("待办 | AC-1", "待办（待安排） | AC-1"), encoding="utf-8")
        (second / "tasks.md").write_text(template.replace("| AC-1 |", "| AC-404 |"), encoding="utf-8")

        result = self.run_board(self.project, "--check")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn(str((first / "tasks.md").resolve()), result.stderr)
        self.assertIn(str((second / "tasks.md").resolve()), result.stderr)
        self.assertIn("状态无效", result.stderr)
        self.assertIn("未知验收项：AC-404", result.stderr)
        self.assertFalse(self.board.exists())

    def test_misplaced_separator_is_reported_as_table_syntax(self):
        requirement = self.create_requirement()
        tasks = requirement / "tasks.md"
        original = tasks.read_text(encoding="utf-8")
        tasks.write_text(original.replace("|---|---|---|---|---|---|", "\n|---|---|---|---|---|---|"),
                         encoding="utf-8")

        result = self.run_board(self.project, "--review", requirement.name)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("分隔行须紧跟表头", result.stderr)
        self.assertNotIn("缺少任务表分隔行", result.stderr)
        self.assertNotIn("任务编号无效", result.stderr)
        self.assertNotIn("状态无效", result.stderr)

    def test_base_review_requires_tracked_project_files_when_using_an_outer_repository(self):
        self.project = self.project / "snapshot"
        self.design_root = self.project / "docs/design"
        requirement = self.create_requirement()
        repo = self.project.parent
        (repo / "README.md").write_text("Outer repository\n", encoding="utf-8")

        def git(*args):
            subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)

        git("init", "-q")
        git("add", "README.md")
        git("-c", "user.name=Test", "-c", "user.email=test@example.invalid",
            "-c", "commit.gpgsign=false", "commit", "-qm", "outer baseline")
        review = ("--review", requirement.name)
        comparison = (*review, "--base", "HEAD")

        snapshot = self.run_board(self.project, *comparison)
        self.assertEqual(snapshot.returncode, 1, snapshot.stdout)
        self.assertIn("外层仓库未跟踪该项目的文件", snapshot.stderr)
        self.assertEqual(self.run_board(self.project, *review).returncode, 0)

        (self.project / "README.md").write_text("Nested project\n", encoding="utf-8")
        git("add", "snapshot/README.md")
        git("-c", "user.name=Test", "-c", "user.email=test@example.invalid",
            "-c", "commit.gpgsign=false", "commit", "-qm", "track nested project")
        new_design = self.run_board(self.project, *comparison)
        self.assertEqual(new_design.returncode, 0, new_design.stderr)
        self.assertIn("AC-1: （基准无此项）", new_design.stdout)

    def test_base_review_shows_changed_expectation_and_completed_task_in_nested_project(self):
        self.project = self.project / "子项目"
        self.design_root = self.project / "docs/design"
        requirement = self.create_requirement("| AC-2 | old | retired |\n")
        design = requirement / "design.md"
        tasks = requirement / "tasks.md"
        tasks.write_text(tasks.read_text(encoding="utf-8").replace(
            "待办 | AC-1 | — | —", "完成 | AC-1 | 生成文件 | 二月为空"), encoding="utf-8")
        def git(*args):
            subprocess.run(["git", "-C", str(self.project.parent), *args], check=True, capture_output=True)
        git("init", "-q")
        git("add", ".")
        git("-c", "user.name=Test", "-c", "user.email=test@example.invalid",
            "-c", "commit.gpgsign=false", "commit", "-qm", "baseline")
        options = ("--review", requirement.name, "--base", "HEAD")
        first = self.run_board(self.project, *options)
        self.assertEqual(first.returncode, 0, first.stderr)
        self.assertIn("条目无变化", first.stdout)
        design.write_text(design.read_text(encoding="utf-8").replace(
            "input | output", "input | fill zero").replace("AC-2 | old | retired", "AC-3 | new | added"),
            encoding="utf-8")
        review = self.run_board(self.project, *options)
        self.assertEqual(review.returncode, 0, review.stderr)
        self.assertIn("AC-1: input / output → input / fill zero。当前关联任务：T1（完成）", review.stdout)
        self.assertIn("AC-2: old / retired → （当前无此项）", review.stdout)
        self.assertIn("AC-3: （基准无此项） → new / added", review.stdout)
        self.assertFalse((self.design_root / "README.md").exists())
        self.assertNotEqual(self.run_board(self.project, "--review", requirement.name,
                                          "--base", "missing-revision").returncode, 0)
