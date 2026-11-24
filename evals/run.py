"""Prepare isolated agent trials, run a configured runner, and grade outcomes."""

import argparse
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

from cases import CASES, PROMPT_DRIFT_RESUME, case_files
from grade import grade


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fingerprint(files):
    value = hashlib.sha256()
    for name, data in sorted(files.items()):
        value.update(name.encode() + b"\0" + data + b"\0")
    return value.hexdigest()


def project_files(workspace):
    for path in workspace.rglob("*"):
        relative = path.relative_to(workspace)
        if any(part in (".git", "__pycache__", "target", "build", ".gradle") for part in relative.parts):
            continue
        if path.is_file():
            if not path.resolve().is_relative_to(workspace.resolve()):
                raise ValueError(f"File points outside the trial workspace: {relative}")
            yield relative


def snapshot(workspace):
    return {path.as_posix(): hashlib.sha256((workspace / path).read_bytes()).hexdigest()
            for path in project_files(workspace)}


def prepare(args):
    trial = args.trial.resolve()
    if trial.exists():
        raise ValueError("Trial directory must be new; existing trials are never overwritten")
    files, prompt = case_files(args.case)
    fixture_id = fingerprint({name: text.encode() for name, text in files.items()})
    workflow_id = None
    if args.variant != "baseline":
        workflow = args.workflow.resolve()
        skill_files = {p.relative_to(workflow).as_posix(): p.read_bytes()
                       for p in (workflow / "skills").rglob("*") if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"}
        if not skill_files:
            raise ValueError("Workflow source has no skill files")
        workflow_id = fingerprint(skill_files)
        for name, data in skill_files.items():
            files[".agents/" + name] = data
        files["AGENTS.md"] += ("\nAI 工作流按需使用：接入或探查见 .agents/skills/project-onboard/SKILL.md；"
                               "需求、设计、实施与验收约定见 .agents/skills/change-design/SKILL.md。\n")
    workspace = trial / "workspace"
    workspace.mkdir(parents=True)
    for name, data in files.items():
        path = workspace / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data if isinstance(data, bytes) else data.encode("utf-8"))
    # A real baseline commit makes resume/diff checks meaningful.
    for command in (["init", "-q"], ["config", "core.autocrlf", "false"], ["add", "."],
                    ["-c", "user.name=Workflow Eval", "-c", "user.email=eval@example.invalid", "commit", "-qm", "Fixture baseline"]):
        subprocess.run(["git", "-C", str(workspace), *command], check=True, capture_output=True)
    prefix = ("先阅读项目入口。只在当前工作区内完成任务，不访问凭据或工作区外的评测文件，不推送、不联网调研。"
              "可运行项目原有构建（必要依赖下载允许）。最后报告实际改动和验证结果。\n\n")
    prompts = {"prompt.txt": (prefix + prompt).encode()}
    if args.case == "drift-cli":
        prompts["resume.txt"] = (prefix + PROMPT_DRIFT_RESUME).encode()
    for name, data in prompts.items():
        (trial / name).write_bytes(data)
    prompt_id = fingerprint(prompts) if len(prompts) > 1 else hashlib.sha256(prompts["prompt.txt"]).hexdigest()
    save(trial / "trial.json", {"case": args.case, "variant": args.variant, "fixture": fixture_id,
                                 "prompt": prompt_id, "workflow": workflow_id,
                                 "initial_files": snapshot(workspace)})
    print(trial)


def grade_trial(trial):
    metadata = json.loads((trial / "trial.json").read_text(encoding="utf-8"))
    workspace = trial / "workspace"
    result = grade(workspace, metadata["case"])
    (trial / "grade.log").write_text(result.pop("output"), encoding="utf-8")
    files = snapshot(workspace)
    changed = sorted(name for name in files.keys() | metadata["initial_files"].keys()
                     if files.get(name) != metadata["initial_files"].get(name))
    grader_files = ["grade.py", "cases.py"]
    if metadata["case"] == "cold-handoff-cli":
        grader_files.append("cold_handoff.py")
    grader = fingerprint({name: Path(__file__).with_name(name).read_bytes() for name in grader_files})
    result.update(grader=grader, changed_files=changed, new_design_files=sum(name.startswith("docs/design/") and name not in metadata["initial_files"] for name in files))
    save(trial / "grade.json", result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return result


def execute(args):
    trial = args.trial.resolve()
    if (trial / "execution.json").exists():
        raise ValueError("Use a fresh trial for each attempt")
    metadata = json.loads((trial / "trial.json").read_text(encoding="utf-8"))
    if snapshot(trial / "workspace") != metadata["initial_files"]:
        raise ValueError("Workspace changed since preparation; use a fresh trial")
    config_bytes = args.runner.read_bytes()
    config = json.loads(config_bytes.decode("utf-8-sig"))
    if not isinstance(config.get("argv"), list) or not config["argv"] or any(not isinstance(a, str) for a in config["argv"]):
        raise ValueError("Runner requires an argv array")
    workspace = trial / "workspace"
    prompt = (trial / "prompt.txt").read_text(encoding="utf-8")
    runner_info = {"runner": config.get("label", "unnamed"), "environment": config.get("environment"),
                   "runner_config": fingerprint({"runner": config_bytes})}
    if metadata["case"] == "drift-cli":
        if not (trial / "resume.txt").exists():
            raise ValueError("Prepare a new drift-cli trial to capture both stages")
        resume = (trial / "resume.txt").read_text(encoding="utf-8")
        if fingerprint({"prompt.txt": prompt.encode(), "resume.txt": resume.encode()}) != metadata["prompt"]:
            raise ValueError("Trial prompts changed since preparation")
    # Reserve the trial before spawning a process, also after an interrupted attempt.
    with (trial / "execution.json").open("x", encoding="utf-8") as handle:
        json.dump({**runner_info, "status": "started"}, handle)
    if metadata["case"] == "drift-cli":
        (trial / "runner.json").write_bytes(config_bytes)
        stages = {}
        for name, instruction in (("A", prompt), ("B", resume)):
            output = trial / name
            output.mkdir()
            (output / "prompt.txt").write_bytes(instruction.encode())
            result = run_stage(workspace, output, instruction, config, runner_info, args.timeout)
            stages[name] = result
            if result["status"] != "completed":
                break
            if name == "A":
                checkpoint = output / "workspace"
                for path in project_files(workspace):
                    target = checkpoint / path
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(workspace / path, target)
        summary = {**runner_info, "status": result["status"], "stages": stages,
                   "elapsed_seconds": round(sum(s["elapsed_seconds"] for s in stages.values()), 2)}
        save(trial / "execution.json", summary)
    else:
        result = run_stage(workspace, trial, prompt, config, runner_info, args.timeout)
    if result["status"] == "completed":
        return {"passed": 0, "failed": 1, "environment_error": 2}[grade_trial(trial)["status"]]
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2


def run_stage(workspace, output, prompt, config, runner_info, timeout):
    substitutions = {"{workspace}": str(workspace), "{response}": str(output / "response.md")}
    argv = [substitutions.get(arg, arg) for arg in config["argv"]]
    argv[0] = shutil.which(argv[0]) or argv[0]
    started = time.monotonic()
    result = {**runner_info,
              "status": "execution_error", "usage": None, "cost": None, "human_corrections": None}
    try:
        with (output / "trace.jsonl").open("w", encoding="utf-8") as out, (output / "stderr.log").open("w", encoding="utf-8") as err:
            process = subprocess.Popen(argv, stdin=subprocess.PIPE,
                                       cwd=workspace, text=True, encoding="utf-8", stdout=out, stderr=err,
                                       start_new_session=os.name != "nt")
            try:
                process.communicate(prompt, timeout=timeout)
            except subprocess.TimeoutExpired:
                if os.name == "nt":
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True)
                else:
                    os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                raise
        result.update(status="completed" if process.returncode == 0 else "execution_error", exit_code=process.returncode)
    except (OSError, subprocess.TimeoutExpired) as error:
        result["error"] = type(error).__name__
    result["elapsed_seconds"] = round(time.monotonic() - started, 2)
    stderr = (output / "stderr.log").read_text(encoding="utf-8", errors="replace")
    if "rejected: blocked by policy" in stderr:
        result["status"] = "environment_blocked"
        result["error"] = "Runner tools were rejected by the host execution policy"
    # Usage is taken only from runner events; absent telemetry remains unknown.
    for line in (output / "trace.jsonl").read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
            if event.get("type") == "turn.completed" and isinstance(event.get("usage"), dict):
                if result["usage"] is None:
                    result["usage"] = {}
                for key, value in event["usage"].items():
                    if isinstance(value, (int, float)):
                        result["usage"][key] = result["usage"].get(key, 0) + value
        except (ValueError, AttributeError):
            pass
    save(output / "execution.json", result)
    return result


def report(args):
    groups = defaultdict(list)
    for directory in args.trials:
        metadata = json.loads((directory / "trial.json").read_text(encoding="utf-8"))
        execution = json.loads((directory / "execution.json").read_text(encoding="utf-8")) if (directory / "execution.json").exists() else {"status": "not_run"}
        result = json.loads((directory / "grade.json").read_text(encoding="utf-8")) if (directory / "grade.json").exists() else {"status": "not_graded"}
        key = (metadata["case"], metadata["fixture"], metadata["prompt"], execution.get("runner_config"), result.get("grader"))
        groups[key].append({"trial": str(directory), "variant": metadata["variant"], "workflow": metadata["workflow"],
                            "execution": execution, "grade": result})
    output = {"note": "Descriptive trials only. Compare identical fixture, prompt, runner and environment; repeat before claiming improvement.",
              "groups": [{"case": key[0], "fixture": key[1], "prompt": key[2], "runner_config": key[3], "grader": key[4], "trials": trials}
                         for key, trials in groups.items()]}
    save(args.output, output)
    print(args.output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare")
    prep.add_argument("--case", choices=CASES, required=True)
    prep.add_argument("--variant", choices=("baseline", "current", "candidate"), required=True)
    prep.add_argument("--workflow", type=Path, default=Path(__file__).resolve().parents[1])
    prep.add_argument("--trial", type=Path, required=True)
    run = commands.add_parser("run")
    run.add_argument("--trial", type=Path, required=True)
    run.add_argument("--runner", type=Path, required=True)
    run.add_argument("--timeout", type=int, default=600)
    check = commands.add_parser("grade")
    check.add_argument("--trial", type=Path, required=True)
    compare = commands.add_parser("report")
    compare.add_argument("trials", nargs="+", type=Path)
    compare.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            prepare(args)
        elif args.command == "run":
            return execute(args)
        elif args.command == "grade":
            return {"passed": 0, "failed": 1, "environment_error": 2}[grade_trial(args.trial.resolve())["status"]]
        else:
            report(args)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
