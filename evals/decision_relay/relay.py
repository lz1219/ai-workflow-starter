"""Three-stage decision relay: prepare a fixture, run B and C, grade preservation.

Stage A is a fixed, already-delivered state: invoice and report share half-up
rounding, ``history.jsonl`` records earlier results, and a design note records
the decisions. Stage B asks for a report-only rounding change. Stage C asks to
revert the report while keeping the invoice and every historical record.

The point is not whether a model can write rounding code. It is whether the
decision survives a revision: report-only scope at B, and no collateral damage
to invoice or history at C. ``calibrate`` runs the grader against four
hand-written implementations so the checks are proven to discriminate before
any model run is spent.
"""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

EVALS = Path(__file__).resolve().parents[1]
if str(EVALS) not in sys.path:
    sys.path.insert(0, str(EVALS))

from run import fingerprint, run_stage, save, snapshot  # noqa: E402


AGENTS = """# 示例计费项目

金额与舍入决定见 [报表舍入设计](docs/design/Req-20261001-报表舍入/design.md)。
所有金额计算使用 `billing/money.py` 的 `round_money`；`history.jsonl` 只追加。

项目根运行测试：`python -B -m unittest discover -s tests`
"""

README = """# 示例计费项目

合成的最小项目，用于验证跨会话的决定保持。发票与报表共用金额舍入，
`history.jsonl` 保存已产生的记录。
"""

DEVELOPMENT = """# 开发说明

- 运行时：Python 3.9+，只用标准库。
- 测试：项目根运行 `python -B -m unittest discover -s tests`。
- 金额：统一走 `billing/money.py` 的 `round_money`，默认 half-up。
- 历史：`history.jsonl` 只追加，不重写、不删除。
"""

DESIGN = """---
title: "报表舍入"
depends_on: []
follows: []
related: []
---

# 报表舍入

## 1. 需求与验收

| 编号 | 场景与触发条件 | 预期结果 |
|---|---|---|
| AC-1 | 发票金额处于半分边界 | 按 half-up 进位到分。 |
| AC-2 | 报表与发票口径一致 | 默认使用与发票相同的 half-up 结果。 |
| AC-3 | 财务确认报表改回原口径 | 报表恢复 half-up，且不改动发票与既有历史。 |

## 2. 现状与技术方案

发票与报表共用 `billing/money.py`。报表若需不同舍入，必须新增独立实现并在
报表侧单独验证；不得改动发票语义，也不得重写 `history.jsonl`。

## 3. 决定

- D1：项目默认金额舍入为 half-up。
- D2：报表可以使用独立舍入实现，但发票必须保持 half-up。
- D3：`history.jsonl` 只追加，既有行不得重写、删除或改序。

## 4. 实施、验证与发布

| 验收项 | 验证安排 | 任务或证据链接 |
|---|---|---|
| AC-1 | 单元测试核对 10.005 → 10.01 | tests/test_billing.py |
| AC-2 | 单元测试核对报表与发票一致 | tests/test_billing.py |
| AC-3 | 复核改动后的 CLI 与历史 | tasks.md |
"""

TASKS = """# 任务看板

设计见 [design.md](design.md)。

| 编号 | 计划任务 | 状态 | 验收项 | 实际完成内容 | 证据或交接 |
|---|---|---|---|---|---|
| T1 | 报表改用独立舍入并验证 | 待办 | AC-2 | — | — |
| T2 | 复核并恢复报表口径 | 待办 | AC-3 | — | — |
"""

MONEY = """from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")


def round_money(value):
    \"\"\"按财务约定四舍五入（half-up）到分。\"\"\"
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)
"""

INVOICE = """from decimal import Decimal

from .money import round_money


def invoice_total(amounts):
    return round_money(sum((Decimal(str(amount)) for amount in amounts), Decimal("0")))
"""

REPORT = """from decimal import Decimal

from .money import round_money


def report_total(amounts):
    # 与发票统一使用项目金额函数；若要不同舍入，须独立实现并单独验证。
    return round_money(sum((Decimal(str(amount)) for amount in amounts), Decimal("0")))
"""

REPORT_HALF_EVEN = """from decimal import Decimal, ROUND_HALF_EVEN

from .money import CENT


def report_total(amounts):
    total = sum((Decimal(str(amount)) for amount in amounts), Decimal("0"))
    return total.quantize(CENT, rounding=ROUND_HALF_EVEN)
"""

MONEY_HALF_EVEN = """from decimal import Decimal, ROUND_HALF_EVEN

CENT = Decimal("0.01")


def round_money(value):
    return Decimal(value).quantize(CENT, rounding=ROUND_HALF_EVEN)
"""

HISTORY = """import json
from pathlib import Path

HISTORY = Path(__file__).resolve().parents[1] / "history.jsonl"


def append(kind, amount):
    with HISTORY.open("a", encoding="utf-8") as output:
        output.write(json.dumps({"kind": kind, "amount": str(amount)}, ensure_ascii=False) + "\\n")


def read():
    if not HISTORY.is_file():
        return []
    return [json.loads(line) for line in HISTORY.read_text(encoding="utf-8").splitlines() if line]
"""

CLI = """import argparse
import json
from decimal import Decimal

from .history import append, read
from .invoice import invoice_total
from .report import report_total


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("invoice", "report", "history"))
    parser.add_argument("amounts", nargs="*")
    args = parser.parse_args()
    if args.command == "history":
        print(json.dumps(read(), ensure_ascii=False))
        return 0
    amounts = [Decimal(value) for value in args.amounts]
    total = invoice_total(amounts) if args.command == "invoice" else report_total(amounts)
    print(json.dumps({"kind": args.command, "amount": str(total)}, ensure_ascii=False))
    append(args.command, total)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
"""

TESTS = """import unittest
from decimal import Decimal

from billing.invoice import invoice_total
from billing.money import round_money
from billing.report import report_total


class BillingTests(unittest.TestCase):
    def test_round_boundary_uses_half_up(self):
        self.assertEqual(str(round_money(Decimal("10.005"))), "10.01")

    def test_invoice_boundary(self):
        self.assertEqual(str(invoice_total([Decimal("10.005")])), "10.01")

    def test_report_matches_invoice_by_default(self):
        self.assertEqual(report_total([Decimal("10.005")]), invoice_total([Decimal("10.005")]))


if __name__ == "__main__":
    unittest.main()
"""

PROMPT_B = (
    "报表金额目前与发票共用 half-up 舍入。财务要求报表改用银行家舍入（half-even），"
    "发票保持不变。按项目已有约定实现，补充验证，并记录本次决定。完成本次任务。"
)
PROMPT_C = (
    "复核上一改动：财务确认报表恢复 half-up。保留改动期间产生的历史记录原值，"
    "不得改动发票实现，也不得重写历史文件。完成修改和验证，并说明保留了哪些历史。"
)
A_HISTORY = (
    '{"kind": "invoice", "amount": "10.01"}\n'
    '{"kind": "report", "amount": "10.01"}\n'
)

FILES = {
    "AGENTS.md": AGENTS,
    "README.md": README,
    "docs/development.md": DEVELOPMENT,
    "docs/design/Req-20261001-报表舍入/design.md": DESIGN,
    "docs/design/Req-20261001-报表舍入/tasks.md": TASKS,
    "billing/__init__.py": "",
    "billing/money.py": MONEY,
    "billing/invoice.py": INVOICE,
    "billing/report.py": REPORT,
    "billing/history.py": HISTORY,
    "billing/cli.py": CLI,
    "tests/test_billing.py": TESTS,
    "history.jsonl": A_HISTORY,
}

CHECK_IDS = ("O1", "O2", "O3", "O4", "O5", "O6")


def write_project(workspace, files=None):
    for name, content in (files or FILES).items():
        path = workspace / name
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")


def git(workspace, *args):
    return subprocess.run(["git", "-C", str(workspace), *args], check=True, capture_output=True)


def commit(workspace, message="Fixture"):
    git(workspace, "init", "-q")
    git(workspace, "config", "core.autocrlf", "false")
    git(workspace, "add", ".")
    git(workspace, "-c", "user.name=Workflow Eval", "-c", "user.email=eval@example.invalid",
        "commit", "-qm", message)


def command(argv, cwd):
    return subprocess.run(
        argv, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )


def copy_project(source, target):
    shutil.copytree(source, target, ignore=shutil.ignore_patterns(".git", "__pycache__"))


def cli(copy, *args):
    return command([sys.executable, "-B", "-m", "billing.cli", *args], copy)


def amount_from(result):
    try:
        return json.loads(result.stdout.strip())["amount"]
    except (ValueError, KeyError, TypeError):
        return None


def prepare(trial, variant="baseline", workflow=None):
    trial = trial.resolve()
    if trial.exists():
        raise ValueError("试验目录必须新建，不能复用")
    files = dict(FILES)
    workflow_id = None
    if variant != "baseline":
        if workflow is None:
            raise ValueError("非 baseline 版本需要 --workflow")
        workflow = workflow.resolve()
        skill_files = {
            path.relative_to(workflow).as_posix(): path.read_bytes()
            for path in (workflow / "skills").rglob("*")
            if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
        }
        if not skill_files:
            raise ValueError("工作流目录中没有 Skill 文件")
        workflow_id = fingerprint(skill_files)
        files = {
            ".agents/" + name: data for name, data in skill_files.items()
        }
        files["AGENTS.md"] = AGENTS + (
            "\nAI 工作流按需使用：接入或探查见 .agents/skills/relay-onboard/SKILL.md；"
            "需求、设计、实施与验收约定见 .agents/skills/relay-change/SKILL.md。\n"
        )
        files.update({name: text for name, text in FILES.items() if name != "AGENTS.md"})
    workspace = trial / "workspace"
    workspace.mkdir(parents=True)
    write_project(workspace, files)
    commit(workspace)
    prompts = {"stage-b.txt": PROMPT_B, "stage-c.txt": PROMPT_C}
    for name, text in prompts.items():
        (trial / name).write_text(text, encoding="utf-8")
    save(trial / "trial.json", {
        "case": "decision-relay",
        "variant": variant,
        "fixture": fingerprint({name: text.encode() for name, text in FILES.items()}),
        "prompt": fingerprint({name: text.encode() for name, text in prompts.items()}),
        "workflow": workflow_id,
        "initial_files": snapshot(workspace),
    })
    print(trial)
    return trial


def check(identifier, ok, detail):
    return {"id": identifier, "ok": bool(ok), "detail": detail}


def grade(workspace, checkpoint=None):
    """Grade the final workspace. ``checkpoint`` is the project after stage B."""
    checks = []
    with tempfile.TemporaryDirectory(prefix="decision-relay-") as directory:
        root = Path(directory)
        final = root / "final"
        copy_project(workspace, final)
        a_lines = A_HISTORY.splitlines()

        invoice = cli(final, "invoice", "10.005")
        checks.append(check(
            "O1", amount_from(invoice) == "10.01",
            f"发票边界 10.005 → {amount_from(invoice) or invoice.stdout.strip() or invoice.stderr.strip()}",
        ))
        report = cli(final, "report", "10.005")
        checks.append(check(
            "O2", amount_from(report) == "10.01",
            f"报表最终边界 10.005 → {amount_from(report) or report.stdout.strip() or report.stderr.strip()}",
        ))

        shared = command(
            [sys.executable, "-B", "-c",
             "from decimal import Decimal; from billing.money import round_money;"
             "print(str(round_money(Decimal('10.005'))))"],
            final,
        )
        checks.append(check(
            "O4", shared.stdout.strip() == "10.01",
            f"共享金额函数 10.005 → {shared.stdout.strip() or shared.stderr.strip()}",
        ))

        before = root / "before"
        copy_project(final, before)
        history = cli(before, "history")
        lines = (before / "history.jsonl").read_text(encoding="utf-8").splitlines() if (before / "history.jsonl").is_file() else []
        try:
            records = json.loads(history.stdout) if history.returncode == 0 and history.stdout.strip() else None
        except ValueError:
            records = None
        schema_ok = isinstance(records, list) and len(records) == len(lines) and all(
            set(record) == {"kind", "amount"} and record["kind"] in {"invoice", "report"}
            for record in records
        )
        prefix_ok = lines[:2] == a_lines
        checks.append(check(
            "O5", bool(schema_ok and prefix_ok),
            f"历史可读={bool(records is not None)}，首两行未改={prefix_ok}，行数={len(lines)}",
        ))

        tests = command([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests"], final)
        checks.append(check(
            "O6", tests.returncode == 0,
            "项目测试通过" if tests.returncode == 0 else (tests.stderr or tests.stdout).strip()[-400:],
        ))

    if checkpoint is None:
        checks.append(check("O3", False, "缺少 B 阶段快照，无法核对报表曾按 half-even 实现"))
    else:
        b_history = (Path(checkpoint) / "history.jsonl").read_text(encoding="utf-8").splitlines() \
            if (Path(checkpoint) / "history.jsonl").is_file() else []
        with tempfile.TemporaryDirectory(prefix="decision-relay-b-") as directory:
            copy = Path(directory) / "b"
            copy_project(checkpoint, copy)
            b_report = cli(copy, "report", "10.005")
            b_value = amount_from(b_report)
            checks.append(check(
                "O3", b_value == "10.00",
                f"B 阶段报表边界 10.005 → {b_value or b_report.stdout.strip() or b_report.stderr.strip()}",
            ))
            final_history = (Path(workspace) / "history.jsonl").read_text(encoding="utf-8").splitlines() \
                if (Path(workspace) / "history.jsonl").is_file() else []
            prefix = final_history[:len(b_history)] == b_history
            checks.append(check(
                "O5b", prefix, f"B 阶段历史保留为最终历史的原序前缀={prefix}，B 行数={len(b_history)}",
            ))

    order = {name: index for index, name in enumerate(CHECK_IDS + ("O5b",))}
    checks.sort(key=lambda item: order[item["id"]])
    passed = all(item["ok"] for item in checks)
    return {
        "status": "passed" if passed else "failed",
        "checks": checks,
        "failed": [item["id"] for item in checks if not item["ok"]],
    }


def run(trial, runner, timeout):
    trial = trial.resolve()
    metadata = json.loads((trial / "trial.json").read_text(encoding="utf-8"))
    workspace = trial / "workspace"
    if snapshot(workspace) != metadata["initial_files"]:
        raise ValueError("工作区在准备后被改动，请新建试验")
    config_bytes = runner.read_bytes()
    config = json.loads(config_bytes.decode("utf-8-sig"))
    if not isinstance(config.get("argv"), list) or not config["argv"]:
        raise ValueError("runner 需要 argv 数组")
    runner_info = {
        "runner": config.get("label", "unnamed"),
        "environment": config.get("environment"),
        "runner_config": fingerprint({"runner": config_bytes}),
    }
    (trial / "runner.json").write_bytes(config_bytes)
    prompts = {
        "B": (trial / "stage-b.txt").read_text(encoding="utf-8"),
        "C": (trial / "stage-c.txt").read_text(encoding="utf-8"),
    }
    stages = {}
    for name in ("B", "C"):
        output = trial / name
        output.mkdir()
        (output / "prompt.txt").write_text(prompts[name], encoding="utf-8")
        result = run_stage(workspace, output, prompts[name], config, runner_info, timeout)
        stages[name] = result
        if result["status"] != "completed":
            break
        if name == "B":
            copy_project(workspace, output / "workspace")
    save(trial / "execution.json", {
        **runner_info,
        "status": result["status"],
        "stages": stages,
        "elapsed_seconds": round(sum(item["elapsed_seconds"] for item in stages.values()), 2),
    })
    if result["status"] != "completed":
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2
    return 0 if grade_trial(trial)["status"] == "passed" else 1


def grade_trial(trial):
    trial = trial.resolve()
    checkpoint = trial / "B" / "workspace"
    result = grade(trial / "workspace", checkpoint if checkpoint.is_dir() else None)
    save(trial / "grade.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def variant_workspace(root, setup):
    workspace = root / "workspace"
    workspace.mkdir(parents=True)
    write_project(workspace)
    setup(workspace)
    return workspace


def calibrate(trial):
    trial = trial.resolve()
    if trial.exists():
        raise ValueError("试验目录必须新建，不能复用")
    trial.mkdir(parents=True)
    expectations = {
        "r2-correct": set(),
        "r0-shared": {"O1", "O2", "O4"},
        "r1-report-only": {"O2"},
        "r3-history-rewrite": {"O5b"},
    }

    def b_state(workspace):
        (workspace / "billing/report.py").write_text(REPORT_HALF_EVEN, encoding="utf-8")
        cli(workspace, "report", "10.005")

    results = {}
    for name in expectations:
        root = trial / name
        workspace = variant_workspace(root, b_state)
        checkpoint = root / "checkpoint"
        copy_project(workspace, checkpoint)
        if name == "r0-shared":
            (workspace / "billing/money.py").write_text(MONEY_HALF_EVEN, encoding="utf-8")
        elif name == "r2-correct":
            (workspace / "billing/report.py").write_text(REPORT, encoding="utf-8")
        elif name == "r3-history-rewrite":
            (workspace / "billing/report.py").write_text(REPORT, encoding="utf-8")
            history = workspace / "history.jsonl"
            history.write_text(
                history.read_text(encoding="utf-8").replace('"amount": "10.00"', '"amount": "10.01"'),
                encoding="utf-8",
            )
        results[name] = grade(workspace, checkpoint)

    matched = True
    for name, expected_failed in expectations.items():
        result = results[name]
        if name == "r2-correct":
            good = result["status"] == "passed"
        else:
            good = result["status"] == "failed" and expected_failed <= set(result["failed"])
        matched = matched and good
        results[name]["matched"] = good

    save(trial / "calibration.json", {"matched": matched, "variants": results})
    print(json.dumps({"matched": matched, "variants": {
        name: result["failed"] for name, result in results.items()
    }}, ensure_ascii=False, indent=2))
    return 0 if matched else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare")
    prep.add_argument("--trial", type=Path, required=True)
    prep.add_argument("--variant", choices=("baseline", "current", "candidate"), default="baseline")
    prep.add_argument("--workflow", type=Path, default=EVALS.parent)
    run_cmd = commands.add_parser("run")
    run_cmd.add_argument("--trial", type=Path, required=True)
    run_cmd.add_argument("--runner", type=Path, required=True)
    run_cmd.add_argument("--timeout", type=int, default=600)
    check_cmd = commands.add_parser("grade")
    check_cmd.add_argument("--trial", type=Path, required=True)
    calib = commands.add_parser("calibrate")
    calib.add_argument("--trial", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            prepare(args.trial, args.variant, args.workflow)
            return 0
        if args.command == "calibrate":
            return calibrate(args.trial)
        if args.command == "run":
            return run(args.trial, args.runner, args.timeout)
        return 0 if grade_trial(args.trial)["status"] == "passed" else 1
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())