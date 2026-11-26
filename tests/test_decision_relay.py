import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
RELAY = ROOT / "evals/decision_relay/relay.py"


class DecisionRelayTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def relay(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(RELAY), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )

    def test_calibration_distinguishes_correct_and_wrong_variants(self):
        trial = self.root / "calibration"
        result = self.relay("calibrate", "--trial", str(trial))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads((trial / "calibration.json").read_text(encoding="utf-8"))
        self.assertTrue(report["matched"])
        self.assertEqual(report["variants"]["r2-correct"]["status"], "passed")
        self.assertIn("O2", report["variants"]["r1-report-only"]["failed"])
        self.assertIn("O1", report["variants"]["r0-shared"]["failed"])
        self.assertIn("O5b", report["variants"]["r3-history-rewrite"]["failed"])

    def test_prepare_creates_committed_fixture_and_prompts(self):
        trial = self.root / "trial"
        result = self.relay("prepare", "--trial", str(trial), "--variant", "baseline")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        workspace = trial / "workspace"
        self.assertTrue((workspace / "docs/design/Req-20261001-报表舍入/design.md").is_file())
        self.assertIn("half-even", (trial / "stage-b.txt").read_text(encoding="utf-8"))
        self.assertIn("历史", (trial / "stage-c.txt").read_text(encoding="utf-8"))
        log = subprocess.run(
            ["git", "-C", str(workspace), "log", "--oneline"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        self.assertEqual(log.returncode, 0, log.stderr)
        metadata = json.loads((trial / "trial.json").read_text(encoding="utf-8"))
        self.assertEqual(metadata["case"], "decision-relay")
        self.assertIsNone(metadata["workflow"])

    def test_grade_without_b_checkpoint_fails(self):
        trial = self.root / "trial"
        prepared = self.relay("prepare", "--trial", str(trial))
        self.assertEqual(prepared.returncode, 0, prepared.stderr)
        result = self.relay("grade", "--trial", str(trial))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        grade = json.loads((trial / "grade.json").read_text(encoding="utf-8"))
        self.assertEqual(grade["status"], "failed")
        self.assertIn("O3", grade["failed"])

    def test_grade_accepts_reverted_report_with_preserved_history(self):
        trial = self.root / "trial"
        prepared = self.relay("prepare", "--trial", str(trial))
        self.assertEqual(prepared.returncode, 0, prepared.stderr)
        workspace = trial / "workspace"
        stage_b = trial / "B/workspace"
        stage_b.parent.mkdir(parents=True)
        shutil.copytree(workspace, stage_b, ignore=shutil.ignore_patterns(".git", "__pycache__"))

        half_even = (
            "from decimal import Decimal, ROUND_HALF_EVEN\n"
            "from .money import CENT\n\n"
            "def report_total(amounts):\n"
            "    total = sum((Decimal(str(amount)) for amount in amounts), Decimal(\"0\"))\n"
            "    return total.quantize(CENT, rounding=ROUND_HALF_EVEN)\n"
        )
        (stage_b / "billing/report.py").write_text(half_even, encoding="utf-8")
        appended = json.dumps({"kind": "report", "amount": "10.00"}) + "\n"
        with (stage_b / "history.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(appended)

        # C reverts only the report and leaves the appended history alone.
        original = (workspace / "billing/report.py").read_text(encoding="utf-8")
        (workspace / "billing/report.py").write_text(original, encoding="utf-8")
        with (workspace / "history.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(appended)

        result = self.relay("grade", "--trial", str(trial))
        grade = json.loads((trial / "grade.json").read_text(encoding="utf-8"))
        self.assertEqual(grade["status"], "passed", result.stdout + result.stderr)
        self.assertEqual(result.returncode, 0)

    def test_grade_rejects_report_that_was_not_reverted(self):
        trial = self.root / "trial"
        prepared = self.relay("prepare", "--trial", str(trial))
        self.assertEqual(prepared.returncode, 0, prepared.stderr)
        workspace = trial / "workspace"
        stage_b = trial / "B/workspace"
        stage_b.parent.mkdir(parents=True)
        shutil.copytree(workspace, stage_b, ignore=shutil.ignore_patterns(".git", "__pycache__"))
        half_even = (
            "from decimal import Decimal, ROUND_HALF_EVEN\n"
            "from .money import CENT\n\n"
            "def report_total(amounts):\n"
            "    total = sum((Decimal(str(amount)) for amount in amounts), Decimal(\"0\"))\n"
            "    return total.quantize(CENT, rounding=ROUND_HALF_EVEN)\n"
        )
        (stage_b / "billing/report.py").write_text(half_even, encoding="utf-8")
        (workspace / "billing/report.py").write_text(half_even, encoding="utf-8")

        result = self.relay("grade", "--trial", str(trial))
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        grade = json.loads((trial / "grade.json").read_text(encoding="utf-8"))
        self.assertIn("O2", grade["failed"])

    def _scripted_runner(self):
        script = self.root / "scripted_runner.py"
        script.write_text(
            "import sys\n"
            "from pathlib import Path\n"
            "workspace, response, mode = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]\n"
            "prompt = sys.stdin.read()\n"
            "half_even = (\n"
            "    'from decimal import Decimal, ROUND_HALF_EVEN\\n'\n"
            "    'from .money import CENT\\n\\n'\n"
            "    'def report_total(amounts):\\n'\n"
            "    '    total = sum((Decimal(str(amount)) for amount in amounts), Decimal(\"0\"))\\n'\n"
            "    '    return total.quantize(CENT, rounding=ROUND_HALF_EVEN)\\n'\n"
            ")\n"
            "original = (\n"
            "    'from decimal import Decimal\\n\\n'\n"
            "    'from .money import round_money\\n\\n\\n'\n"
            "    'def report_total(amounts):\\n'\n"
            "    '    return round_money(sum((Decimal(str(amount)) for amount in amounts), Decimal(\"0\")))\\n'\n"
            ")\n"
            "shared = (\n"
            "    'from decimal import Decimal, ROUND_HALF_EVEN\\n\\n'\n"
            "    'CENT = Decimal(\"0.01\")\\n\\n\\n'\n"
            "    'def round_money(value):\\n'\n"
            "    '    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_EVEN)\\n'\n"
            ")\n"
            "if mode == 'naive':\n"
            "    (workspace / 'billing/money.py').write_text(shared, encoding='utf-8')\n"
            "elif 'half-even' in prompt:\n"
            "    (workspace / 'billing/report.py').write_text(half_even, encoding='utf-8')\n"
            "    with (workspace / 'history.jsonl').open('a', encoding='utf-8') as handle:\n"
            "        handle.write('{\"kind\": \"report\", \"amount\": \"10.00\"}\\n')\n"
            "else:\n"
            "    (workspace / 'billing/report.py').write_text(original, encoding='utf-8')\n"
            "response.write_text('scripted', encoding='utf-8')\n",
            encoding="utf-8",
        )
        return script

    def _runner(self, script, mode):
        path = self.root / f"runner-{mode}.json"
        path.write_text(json.dumps({
            "label": f"scripted-{mode}",
            "environment": "offline test",
            "argv": [sys.executable, str(script), "{workspace}", "{response}", mode],
        }), encoding="utf-8")
        return path

    def test_run_with_scripted_correct_runner_passes(self):
        trial = self.root / "trial"
        self.assertEqual(self.relay("prepare", "--trial", str(trial)).returncode, 0)
        script = self._scripted_runner()
        result = self.relay("run", "--trial", str(trial), "--runner", str(self._runner(script, "correct")),
                            "--timeout", "60")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        grade = json.loads((trial / "grade.json").read_text(encoding="utf-8"))
        self.assertEqual(grade["status"], "passed")

    def test_run_with_scripted_naive_runner_fails(self):
        trial = self.root / "trial"
        self.assertEqual(self.relay("prepare", "--trial", str(trial)).returncode, 0)
        script = self._scripted_runner()
        result = self.relay("run", "--trial", str(trial), "--runner", str(self._runner(script, "naive")),
                            "--timeout", "60")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        grade = json.loads((trial / "grade.json").read_text(encoding="utf-8"))
        self.assertIn("O1", grade["failed"])


if __name__ == "__main__":
    unittest.main()