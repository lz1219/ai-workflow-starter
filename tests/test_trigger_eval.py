import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills/relay-onboard/scripts/trigger_eval.py"
DATASET = ROOT / "evals/trigger_cases.jsonl"

CASES = [
    {"utterance": "接入这个仓库", "expected": "relay-onboard"},
    {"utterance": "评审判定设计", "expected": "relay-change"},
    {"utterance": "解释这段代码", "expected": None},
]


class TriggerEvalTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def write(self, name, records):
        path = self.root / name
        path.write_text(
            "\n".join(json.dumps(record, ensure_ascii=False) for record in records) + "\n",
            encoding="utf-8",
        )
        return path

    def run_eval(self, cases, predictions, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--cases", str(cases),
             "--predictions", str(predictions), *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )

    def test_perfect_predictions_pass(self):
        cases = self.write("cases.jsonl", CASES)
        predictions = self.write("perfect.jsonl", [
            {"utterance": record["utterance"], "predicted": record["expected"]} for record in CASES
        ])
        result = self.run_eval(cases, predictions, "--json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertTrue(report["ok"])
        self.assertEqual(report["misrouted"], [])
        self.assertEqual(report["labels"]["relay-onboard"]["precision"], 1.0)
        self.assertEqual(report["labels"]["（不触发）"]["recall"], 1.0)

    def test_false_positive_fails_precision_threshold(self):
        cases = self.write("cases.jsonl", CASES)
        predictions = self.write("broad.jsonl", [
            {"utterance": "接入这个仓库", "predicted": "relay-onboard"},
            {"utterance": "评审判定设计", "predicted": "relay-change"},
            {"utterance": "解释这段代码", "predicted": "relay-change"},
        ])
        result = self.run_eval(cases, predictions, "--json", "--min-precision", "0.9")
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertFalse(report["ok"])
        self.assertLess(report["labels"]["relay-change"]["precision"], 1.0)
        self.assertEqual(report["misrouted"][0]["predicted"], "relay-change")

    def test_missing_prediction_is_an_input_error(self):
        cases = self.write("cases.jsonl", CASES)
        predictions = self.write("partial.jsonl", [
            {"utterance": "接入这个仓库", "predicted": "relay-onboard"},
        ])
        result = self.run_eval(cases, predictions)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("不一致", result.stderr)

    def test_duplicate_utterance_is_an_input_error(self):
        cases = self.write("cases.jsonl", CASES + [CASES[0]])
        predictions = self.write("perfect.jsonl", [
            {"utterance": record["utterance"], "predicted": record["expected"]} for record in CASES
        ])
        result = self.run_eval(cases, predictions)
        self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
        self.assertIn("重复", result.stderr)

    def test_repository_dataset_is_valid_and_uses_installed_skills(self):
        installed = {path.parent.name for path in (ROOT / "skills").glob("*/SKILL.md")}
        records = [json.loads(line) for line in DATASET.read_text(encoding="utf-8-sig").splitlines()
                   if line.strip() and not line.startswith("#")]
        self.assertGreaterEqual(len(records), 20)
        self.assertEqual(len({record["utterance"] for record in records}), len(records))
        for record in records:
            self.assertTrue(record["expected"] is None or record["expected"] in installed,
                            record["utterance"])
        for name in installed:
            self.assertTrue(any(record["expected"] == name for record in records), name)

    def test_keyword_baseline_runs_against_repository_dataset(self):
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--cases", str(DATASET),
             "--predict-argv", sys.executable, str(ROOT / "evals/baselines/keyword_router.py"),
             "{utterance}", "--json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        self.assertIn(result.returncode, (0, 1), result.stdout + result.stderr)
        report = json.loads(result.stdout)
        self.assertEqual(report["cases"], 28)
        self.assertEqual(set(report["labels"]), {"relay-change", "relay-onboard", "（不触发）"})
        self.assertGreater(report["labels"]["relay-change"]["recall"], 0.5)

    def test_predict_command_generates_predictions_and_scores_them(self):
        cases = self.write("cases.jsonl", CASES)
        router = self.root / "router.py"
        router.write_text(
            "import sys\n"
            "text = sys.argv[1]\n"
            "print('relay-onboard' if '接入' in text else "
            "'relay-change' if '设计' in text else 'none')\n",
            encoding="utf-8",
        )
        output = self.root / "predictions.jsonl"
        command = f'"{sys.executable}" "{router}" {{utterance}}'
        result = subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--cases", str(cases),
             "--predict-command", command, "--output", str(output), "--json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(json.loads(result.stdout)["ok"])
        records = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
        self.assertEqual({record["predicted"] for record in records},
                         {"relay-onboard", "relay-change", None})


if __name__ == "__main__":
    unittest.main()