"""Run requirement structure and acceptance-coverage checks for CI.

This is a read-only gate around requirements.py. It fails when the board is
stale, a task record is invalid, or a changed design has an acceptance item
without a task or a written verification plan.

It does not run project tests, judge design quality, or prove that an
acceptance result is true. Those remain separate checks.
"""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


REQUIREMENTS = Path(__file__).with_name("requirements.py")


def run(argv, cwd):
    return subprocess.run(
        argv,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env={**os.environ, "PYTHONIOENCODING": "utf-8"},
    )


def git(project, *args):
    return subprocess.run(
        ["git", "-C", str(project), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def all_requirements(project):
    root = project / "docs" / "design"
    return sorted(path.parent.name for path in root.glob("*/design.md"))


def changed_requirements(project, base):
    """List requirement directories touched by the change.

    Git quotes non-ASCII paths unless told otherwise, so read NUL-separated
    names with core.quotepath disabled. Untracked requirement files are
    included: a new design should fail the gate before it is committed.
    """
    diff = git(
        project, "-c", "core.quotepath=false", "diff", "--name-only", "-z", "--no-renames",
        base, "--", "docs/design",
    )
    if diff.returncode:
        raise ValueError(diff.stderr.strip() or f"无法读取 Git 基准 {base!r}")
    untracked = git(project, "-c", "core.quotepath=false",
                    "ls-files", "--others", "--exclude-standard", "-z", "--", "docs/design")
    if untracked.returncode:
        raise ValueError(untracked.stderr.strip() or "无法读取未跟踪的需求文件")

    names = set()
    for line in (diff.stdout + untracked.stdout).split("\0"):
        parts = Path(line.strip()).parts
        if len(parts) >= 4 and parts[0] == "docs" and parts[1] == "design":
            names.add(parts[2])
    return sorted(names)


def review_passed(reviewed):
    """--review exits 0 but prints coverage gaps to stderr."""
    return reviewed.returncode == 0 and not reviewed.stderr.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument(
        "--base",
        help="Git 基准。默认读取 GITHUB_BASE_SHA、CI_MERGE_REQUEST_TARGET_BRANCH_SHA，最后使用 HEAD",
    )
    parser.add_argument("--all", action="store_true", help="检查所有需求，而不只是本次改动的需求")
    parser.add_argument("--json", action="store_true", help="输出 JSON")
    args = parser.parse_args()

    project = args.project.resolve()
    if not project.is_dir():
        print(f"项目目录不存在或不是目录：{project}", file=sys.stderr)
        return 2

    base = args.base or os.environ.get("GITHUB_BASE_SHA") or os.environ.get(
        "CI_MERGE_REQUEST_TARGET_BRANCH_SHA"
    ) or "HEAD"
    results = []

    checked = run(
        [sys.executable, "-B", str(REQUIREMENTS), "--project", str(project), "--check"],
        project,
    )
    output = (checked.stdout + checked.stderr).strip()
    results.append({"name": "check", "ok": checked.returncode == 0, "output": output})

    try:
        names = all_requirements(project) if args.all else changed_requirements(project, base)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2

    for name in names:
        reviewed = run(
            [sys.executable, "-B", str(REQUIREMENTS), "--project", str(project), "--review", name],
            project,
        )
        output = (reviewed.stdout + reviewed.stderr).strip()
        results.append({"name": name, "ok": review_passed(reviewed), "output": output})

    ok = all(result["ok"] for result in results)
    if args.json:
        print(json.dumps({"base": base, "changed": names, "ok": ok, "results": results},
                         ensure_ascii=False, indent=2))
    else:
        print(f"基准：{base}")
        for result in results:
            print(f"[{'通过' if result['ok'] else '失败'}] {result['name']}")
            if not result["ok"] and result["output"]:
                print(result["output"])
        if ok:
            print("需求结构、看板与本次改动需求的验收安排均通过。")
        else:
            print("需求检查未通过。修复后重跑；CI 通过不等于验收结果已证实。")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())