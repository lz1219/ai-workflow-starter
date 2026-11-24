import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "evals/run.py"


DRIFT_SOURCE = '''import argparse
import csv
import json
import sys
from pathlib import Path


def load(source):
    rows = list(csv.DictReader(Path(source).open(encoding="utf-8", newline="")))
    kept, order = {}, []
    for row in rows:
        name = row.get("name") or ""
        if name not in kept:
            order.append(name)
        kept[name] = row
    return [kept[name] for name in order]


def main():
    argv = sys.argv[1:]
    if argv and argv[0] == "export":
        rows = load(argv[1])
        write_csv(argv[2], rows)
        print(json.dumps({"exported": len(rows)}))
        return
    parser = argparse.ArgumentParser()
    parser.add_argument("source")
    parser.add_argument("target")
    args = parser.parse_args()
    rows = load(args.source)
    Path(args.target).write_text(json.dumps(rows), encoding="utf-8")
    print(json.dumps({"accepted": len(rows)}))


def write_csv(target, rows):
    with Path(target).open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["name", "email"])
        writer.writeheader()
        writer.writerows(rows)


if __name__ == "__main__":
    main()
'''


class EvalTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def call(self, *args):
        return subprocess.run([sys.executable, "-B", str(SCRIPT), *map(str, args)], capture_output=True,
                              text=True, encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"})

    def prepare(self, case="python-cli", variant="baseline"):
        trial = self.root / (case + "-" + variant)
        result = self.call("prepare", "--case", case, "--variant", variant, "--trial", trial)
        self.assertEqual(result.returncode, 0, result.stderr)
        return trial

    def fix(self, trial):
        path = trial / "workspace/importer.py"
        path.write_text(path.read_text(encoding="utf-8").replace(
            '    Path(args.target).write_text(json.dumps(accepted), encoding="utf-8")',
            '    if not args.dry_run:\n        Path(args.target).write_text(json.dumps(accepted), encoding="utf-8")'), encoding="utf-8")

    def test_quarter_handoff_detects_inverted_months_despite_equal_totals(self):
        trial = self.prepare("quarter-handoff")
        path = trial / "workspace/handoff.json"
        entries = {"february.csv": {"reported": [1, 3], "missing": [2]},
                   "revised.csv": {"reported": [1, 3], "missing": [2]}}
        path.write_text(json.dumps(entries), encoding="utf-8")
        checks = self.cold_checks(trial, 1)
        self.assertFalse(checks["february.csv"])
        self.assertTrue(checks["revised.csv"])
        entries["february.csv"] = {"reported": [2], "missing": [1, 3]}
        path.write_text(json.dumps(entries), encoding="utf-8")
        self.assertTrue(all(self.cold_checks(trial, 0).values()))
        (trial / "workspace/reports/summary.csv").write_text("changed", encoding="utf-8")
        self.assertFalse(self.cold_checks(trial, 1)["published_reports_unchanged"])

    def test_design_review_case_prepares_and_refuses_automated_grading(self):
        trial = self.prepare("design-review")
        workspace = trial / "workspace"
        self.assertTrue((workspace / "docs/design/Req-20251120-事件关闭通知/design.md").is_file())
        self.assertTrue((workspace / "app/events.py").is_file())
        result = self.call("grade", "--trial", trial)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        graded = json.loads((trial / "grade.json").read_text(encoding="utf-8"))
        self.assertEqual(graded["status"], "environment_error")
        self.assertEqual(graded["checks"], {})

    def test_claim_check_requires_fix_and_truthful_record(self):
        trial = self.prepare("claim-check-cli")
        self.assertEqual(self.call("grade", "--trial", trial).returncode, 1)
        workspace = trial / "workspace"
        importer = workspace / "importer.py"
        text = importer.read_text(encoding="utf-8")
        old = ('    Path(args.target).parent.mkdir(parents=True, exist_ok=True)\n'
               '    Path(args.target).write_text(json.dumps(accepted), encoding="utf-8")\n')
        new = ('    if not args.dry_run:\n'
               '        Path(args.target).parent.mkdir(parents=True, exist_ok=True)\n'
               '        Path(args.target).write_text(json.dumps(accepted), encoding="utf-8")\n')
        importer.write_text(text.replace(old, new), encoding="utf-8")
        # Fixed code with a stale record must still fail the record check.
        self.assertEqual(self.call("grade", "--trial", trial).returncode, 1)
        tasks = workspace / "docs/tasks.md"
        tasks.write_text(tasks.read_text(encoding="utf-8").replace(
            "| T1 | 修复预演的写文件副作用 | 待办 | AC-1、AC-2 | — | — |",
            "| T1 | 修复预演的写文件副作用 | 完成 | AC-1、AC-2 | 已修复 | verify.py --full 通过 |"), encoding="utf-8")
        self.assertEqual(self.call("grade", "--trial", trial).returncode, 0)

    def test_gate_case_rejects_fix_that_satisfies_only_shipped_checks(self):
        trial = self.prepare("gate-check-cli")
        workspace = trial / "workspace"
        importer = workspace / "importer.py"
        text = importer.read_text(encoding="utf-8")
        old = '    Path(args.target).write_text(json.dumps(accepted), encoding="utf-8")\n'
        new = '    if not args.dry_run:\n        Path(args.target).write_text(json.dumps(accepted), encoding="utf-8")\n'
        importer.write_text(text.replace(old, new), encoding="utf-8")
        shipped = subprocess.run([sys.executable, "-B", "verify.py", "--full"], cwd=workspace, capture_output=True)
        self.assertEqual(shipped.returncode, 0, "shipped checks should be green after the partial fix")
        self.assertEqual(self.call("grade", "--trial", trial).returncode, 1)
        graded = json.loads((trial / "grade.json").read_text(encoding="utf-8"))
        self.assertFalse(graded["checks"]["ac3_preview_does_not_create_parent"])

    def test_drift_case_detects_reimplemented_dedup_in_export(self):
        trial = self.prepare("drift-cli")
        self.assertEqual(self.call("grade", "--trial", trial).returncode, 1)
        workspace = trial / "workspace"
        importer = workspace / "importer.py"
        importer.write_text(DRIFT_SOURCE, encoding="utf-8")
        (workspace / "docs/tasks.md").write_text("""# 任务

| 编号 | 计划任务 | 状态 | 验收项 | 实际完成内容 | 证据或交接 |
| --- | --- | --- | --- | --- | --- |
| T1 | 导入时按名称去重 | 完成 | — | 首次位置、末条内容 | tests/test_importer.py |
| T2 | 增加 export 子命令 | 完成 | — | 复用去重结果按导入顺序写出 | 手工样例 |
""", encoding="utf-8")
        self.assertEqual(self.call("grade", "--trial", trial).returncode, 0)
        drifted = DRIFT_SOURCE.replace('        rows = load(argv[1])', '''        kept = {}
        for row in csv.DictReader(Path(argv[1]).open(encoding="utf-8", newline="")):
            name = row.get("name") or ""
            kept.pop(name, None)
            kept[name] = row
        rows = list(kept.values())''')
        self.assertNotEqual(drifted, DRIFT_SOURCE)
        importer.write_text(drifted, encoding="utf-8")
        self.assertEqual(self.call("grade", "--trial", trial).returncode, 1)

    def test_drift_runner_hands_only_workspace_to_second_process(self):
        trial = self.prepare("drift-cli")
        runner = self.root / "runner.json"
        script = self.root / "actor.py"
        # A delivers import only. B shares its load() rule and adds export.
        start = DRIFT_SOURCE.index('    if argv and argv[0] == "export":')
        end = DRIFT_SOURCE.index('    parser = argparse.ArgumentParser()', start)
        import_only = DRIFT_SOURCE[:start] + DRIFT_SOURCE[end:]
        (self.root / "import-only.py").write_text(import_only, encoding="utf-8")
        (self.root / "import-export.py").write_text(DRIFT_SOURCE, encoding="utf-8")
        script.write_text("""import os, sys
from pathlib import Path
prompt = sys.stdin.buffer.read().decode('utf-8')
note = Path('handoff.txt')
if 'T1' in prompt:
    assert not note.exists()
    note.write_text(str(os.getpid()))
    source = 'import-only.py'
    task = 'T1'
    response = 'private A response'
else:
    assert 'T2' in prompt and 'private A response' not in prompt
    assert int(note.read_text()) != os.getpid()
    note.write_text('B received the handoff')
    source = 'import-export.py'
    task = 'T2'
    response = 'B completed'
Path('importer.py').write_bytes(Path(__file__).with_name(source).read_bytes())
tasks = Path('docs/tasks.md')
rows = tasks.read_text(encoding='utf-8').splitlines()
outcome = '按名称去重' if task == 'T1' else '按导入顺序导出 CSV'
for index, row in enumerate(rows):
    if row.startswith('| ' + task + ' |'):
        rows[index] = row.replace('待办 | — | — | —', '完成 | — | ' + outcome + ' | importer.py')
tasks.write_text('\\n'.join(rows), encoding='utf-8')
Path(sys.argv[1]).write_text(response)
print(response)
""", encoding="utf-8")
        runner.write_text(json.dumps({"argv": [sys.executable, str(script), "{response}"]}), encoding="utf-8")
        attempt = self.call("run", "--trial", trial, "--runner", runner)
        self.assertEqual(attempt.returncode, 0, attempt.stdout + attempt.stderr)
        for name in ("A", "B"):
            stage = trial / name
            self.assertEqual(json.loads((stage / "execution.json").read_bytes())["status"], "completed")
            self.assertEqual((stage / "response.md").read_text().strip(), (stage / "trace.jsonl").read_text().strip())
        self.assertTrue((trial / "A/workspace/handoff.txt").read_text().isdigit())
        self.assertEqual((trial / "workspace/handoff.txt").read_text(), "B received the handoff")
        self.assertEqual((trial / "A/workspace/importer.py").read_text(encoding="utf-8"), import_only)
        self.assertEqual(json.loads((trial / "grade.json").read_bytes())["status"], "passed")

    def test_drift_aborts_on_stage_error(self):
        runner = self.root / "runner.json"
        for stop, variant in (("T1", "baseline"), ("T2", "candidate")):
            with self.subTest(stage=stop):
                trial = self.prepare("drift-cli", variant)
                code = "import sys; sys.exit(9 if %r in sys.stdin.buffer.read() else 0)" % stop.encode()
                runner.write_text(json.dumps({"argv": [sys.executable, "-c", code]}), encoding="utf-8")
                self.assertEqual(self.call("run", "--trial", trial, "--runner", runner).returncode, 2)
                result = json.loads((trial / "execution.json").read_bytes())
                self.assertEqual(result["status"], "execution_error")
                self.assertEqual((trial / "B").exists(), stop == "T2")
                self.assertFalse((trial / "grade.json").exists())

    def test_holdout_checks_reject_original_bug_and_accept_real_fix(self):
        trial = self.prepare()
        bad = self.call("grade", "--trial", trial)
        self.assertEqual(bad.returncode, 1, bad.stderr)
        result = json.loads((trial / "grade.json").read_text(encoding="utf-8"))
        self.assertFalse(result["checks"]["dry_run_preserves_existing_file"])
        self.fix(trial)
        good = self.call("grade", "--trial", trial)
        self.assertEqual(good.returncode, 0, good.stderr)

    def test_resume_grader_detects_loss_of_previously_completed_behavior(self):
        trial = self.prepare("resume-cli")
        self.fix(trial)
        self.assertEqual(self.call("grade", "--trial", trial).returncode, 0)
        path = trial / "workspace/importer.py"
        path.write_text(path.read_text(encoding="utf-8").replace('    accepted = list({row["name"]: row for row in accepted}.values())\n', ''), encoding="utf-8")
        self.assertEqual(self.call("grade", "--trial", trial).returncode, 1)

    def cold_checks(self, trial, expected_status):
        result = self.call("grade", "--trial", trial)
        self.assertEqual(result.returncode, expected_status, result.stdout + result.stderr)
        return json.loads((trial / "grade.json").read_text(encoding="utf-8"))["checks"]

    def test_cold_handoff_rejects_green_smoke_and_stale_evidence(self):
        trial = self.prepare("cold-handoff-cli")
        workspace = trial / "workspace"
        verification = [sys.executable, "-B", "verify.py"]
        report = workspace / "evidence/current.json"
        self.assertEqual(subprocess.run(verification, cwd=workspace, capture_output=True).returncode, 0)
        self.assertFalse(report.exists())
        self.assertFalse(self.cold_checks(trial, 1)["dry_run_preserves_existing_file"])

        self.fix(trial)
        tasks = workspace / "docs/import/tasks.md"
        tasks.write_text(tasks.read_text(encoding="utf-8").replace(
            "待办 | AC-2、AC-1 | — | 本工作区需跑完整验证并链接当前回执",
            "完成 | AC-2、AC-1 | 导入与预演验证通过 | [本次回执](../../evidence/current.json)"),
            encoding="utf-8")
        report.parent.mkdir()
        report.write_bytes((workspace / "docs/import/previous-check.json").read_bytes())
        checks = self.cold_checks(trial, 1)
        self.assertTrue(checks["dry_run_preserves_existing_file"])
        self.assertTrue(checks["original_task_links_current_evidence"])
        self.assertFalse(checks["current_evidence_matches_checkout"])

        full = subprocess.run([*verification, "--current"], cwd=workspace, capture_output=True)
        self.assertEqual(full.returncode, 0, full.stderr)
        self.assertTrue(all(self.cold_checks(trial, 0).values()))

        handoff = tasks.read_text(encoding="utf-8")
        tasks.write_text(handoff.replace("../../evidence/current.json", "../evidence/current.json"), encoding="utf-8")
        checks = self.cold_checks(trial, 1)
        self.assertTrue(checks["current_evidence_matches_checkout"])
        self.assertFalse(checks["original_task_links_current_evidence"])
        tasks.write_text(handoff, encoding="utf-8")

        importer = workspace / "importer.py"
        importer.write_text(importer.read_text(encoding="utf-8") + "\n# Change after verification\n", encoding="utf-8")
        checks = self.cold_checks(trial, 1)
        self.assertTrue(checks["dry_run_preserves_existing_file"])
        self.assertFalse(checks["current_evidence_matches_checkout"])

    def test_cold_handoff_detects_premature_activation_of_future_rule(self):
        trial = self.prepare("cold-handoff-cli")
        self.fix(trial)
        importer = trial / "workspace/importer.py"
        importer.write_text(importer.read_text(encoding="utf-8").replace(
            'row["name"]: row', 'row["name"].casefold(): row'), encoding="utf-8")
        checks = self.cold_checks(trial, 1)
        self.assertTrue(checks["normal_import_preserves_existing_rules"])
        self.assertFalse(checks["active_case_sensitive_rule"])

    def test_agent_success_claim_is_not_a_passing_outcome(self):
        trial = self.prepare()
        runner = self.root / "runner.json"
        runner.write_text(json.dumps({"label": "fake-success", "argv": [sys.executable, "-c", "print('All tasks completed successfully')"]}), encoding="utf-8")
        result = self.call("run", "--trial", trial, "--runner", runner)
        self.assertEqual(result.returncode, 1)
        execution = json.loads((trial / "execution.json").read_text(encoding="utf-8"))
        self.assertEqual(execution["status"], "completed")
        self.assertIsNone(execution["usage"])
        self.assertEqual(json.loads((trial / "grade.json").read_text(encoding="utf-8"))["status"], "failed")
        self.assertNotEqual(self.call("run", "--trial", trial, "--runner", runner).returncode, 0)

    def test_baseline_and_candidate_share_fixture_and_prompt(self):
        baseline, candidate = self.prepare(), self.prepare(variant="candidate")
        left = json.loads((baseline / "trial.json").read_text(encoding="utf-8"))
        right = json.loads((candidate / "trial.json").read_text(encoding="utf-8"))
        self.assertEqual(left["fixture"], right["fixture"])
        self.assertEqual(left["prompt"], right["prompt"])
        self.assertIsNone(left["workflow"])
        self.assertTrue(right["workflow"])
        self.assertFalse((baseline / "workspace/.agents").exists())
        self.assertTrue((candidate / "workspace/.agents/skills/change-design/SKILL.md").is_file())
        self.assertNotEqual(self.call("prepare", "--case", "python-cli", "--variant", "baseline", "--trial", baseline).returncode, 0)

    def test_runner_failure_is_recorded_separately_from_acceptance(self):
        trial = self.prepare()
        runner = self.root / "runner.json"
        runner.write_text(json.dumps({"argv": [sys.executable, "-c", "raise SystemExit(9)"]}), encoding="utf-8")
        result = self.call("run", "--trial", trial, "--runner", runner)
        self.assertEqual(result.returncode, 2)
        self.assertFalse((trial / "grade.json").exists())
        self.assertEqual(json.loads((trial / "execution.json").read_text(encoding="utf-8"))["status"], "execution_error")

    def test_deleting_target_is_a_task_failure_not_an_environment_error(self):
        trial = self.prepare()
        path = trial / "workspace/importer.py"
        path.write_text(path.read_text(encoding="utf-8").replace(
            '    Path(args.target).write_text(json.dumps(accepted), encoding="utf-8")',
            '    Path(args.target).unlink(missing_ok=True)'), encoding="utf-8")
        result = self.call("grade", "--trial", trial)
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads((trial / "grade.json").read_text(encoding="utf-8"))["status"], "failed")

    def test_explicit_host_policy_rejection_is_not_a_task_quality_result(self):
        trial = self.prepare()
        runner = self.root / "runner.json"
        runner.write_text(json.dumps({"argv": [sys.executable, "-c", "import sys; print('rejected: blocked by policy',file=sys.stderr)"]}), encoding="utf-8")
        self.assertEqual(self.call("run", "--trial", trial, "--runner", runner).returncode, 2)
        self.assertFalse((trial / "grade.json").exists())

    def test_runner_timeout_does_not_produce_an_acceptance_result(self):
        trial = self.prepare()
        runner = self.root / "runner.json"
        runner.write_text(json.dumps({"argv": [sys.executable, "-c", "import time; time.sleep(60)"]}), encoding="utf-8")
        self.assertEqual(self.call("run", "--trial", trial, "--runner", runner, "--timeout", "1").returncode, 2)
        self.assertFalse((trial / "grade.json").exists())
        self.assertEqual(json.loads((trial / "execution.json").read_text(encoding="utf-8"))["error"], "TimeoutExpired")
