"""Preview and transactionally update registered, repository-local skills.

Uses an explicitly supplied Git checkout; fetching and choosing a trusted revision
remain the caller's responsibility. Python standard library and Git only.
"""

import argparse
import ast
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import shutil
import subprocess
import sys
import tempfile


MANIFEST = ".ai-workflow.json"
JOURNAL = ".ai-workflow-transaction.json"
ENTRY_MARKER = "<!-- ai-workflow -->"


def check_executable(cwd, executable):
    if executable == "{python}":
        return sys.executable
    if os.path.dirname(executable) or Path(executable).is_absolute():
        path = (cwd / executable).resolve()
        return str(path) if path.is_file() and os.access(path, os.X_OK) else None
    return shutil.which(executable)


def run_checks(project, checks):
    for check in checks:
        cwd = project if check["cwd"] == "." else safe_path(project, check["cwd"])
        argv = [sys.executable if arg == "{python}" else arg for arg in check["argv"]]
        argv[0] = check_executable(cwd, check["argv"][0])
        if argv[0] is None:
            raise ValueError("Validation executable is unavailable in its working directory")
        result = subprocess.run(argv, cwd=cwd, timeout=check.get("timeout", 120),
                                env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        if result.returncode:
            raise ValueError(f"Validation failed with exit code {result.returncode}")


def doctor(project):
    """Inspect the installation offline, without executing registered commands."""
    report = {"healthy": True, "skills": {}, "errors": [], "warnings": []}
    try:
        if safe_path(project, JOURNAL).exists():
            report["errors"].append("Unfinished transaction: run --rollback before installing or updating")
        data = file_bytes(safe_path(project, MANIFEST))
        if data is None:
            raise ValueError("No installation manifest. Use --install for a new installation or --register for a known baseline.")
        manifest = json.loads(data)
        validate_manifest(project, manifest)
        if not manifest["skills"]:
            report["errors"].append("No registered skills")
        for name, entry in manifest["skills"].items():
            missing, modified = [], []
            for path, expected in entry["files"].items():
                data = file_bytes(safe_path(project, entry["target"] + "/" + path))
                if data is None:
                    missing.append(path)
                elif digest(data) != expected:
                    modified.append(path)
            report["skills"][name] = {"revision": entry["revision"], "target": entry["target"],
                                      "missing": missing, "modified": modified}
            if missing:
                report["errors"].append(f"{name}: missing installed files")
            if modified:
                report["warnings"].append(f"{name}: local customization detected; review during update")
        if not manifest["checks"]:
            report["errors"].append("No validation commands configured")
        for check in manifest["checks"]:
            cwd = project if check["cwd"] == "." else safe_path(project, check["cwd"])
            if not cwd.is_dir():
                report["errors"].append(f"Validation working directory is missing: {check['cwd']}")
            executable = check["argv"][0]
            if not check_executable(cwd, executable):
                report["errors"].append("Validation executable is unavailable; inspect checks in the manifest")
        agents = file_bytes(safe_path(project, "AGENTS.md")) or b""
        if MANIFEST.encode() not in agents:
            report["warnings"].append("AGENTS.md does not link the installation manifest")
        report["checks"] = len(manifest["checks"])
        report["checks_executed"] = False
    except (ValueError, OSError, KeyError, TypeError) as error:
        report["errors"].append(str(error))
    report["healthy"] = not report["errors"]
    return report


def change_record(project, relative, data):
    before = file_bytes(safe_path(project, relative))
    return {"path": relative, "before": pack(before), "after": pack(data)} if before != data else None


def install(project, source, revision, manifest, before_manifest, args):
    changes = []
    for name in args.install:
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
            raise ValueError("Invalid skill name")
        target = args.target or f".{ 'agents' if args.tool == 'codex' else 'claude' }/skills/{name}"
        target_path(project, target, name)
        if name in manifest["skills"]:
            entry = manifest["skills"][name]
            if entry["target"] != target or entry["revision"] != revision:
                raise ValueError(f"{name} is already registered elsewhere or at another version; use update")
            print(f"ALREADY INSTALLED {name}; preserving local changes")
            continue
        files = source_files(source, revision, name)
        text = files["SKILL.md"].decode("utf-8-sig")
        if not re.search(r"(?m)^name:\s*" + re.escape(name) + r"\s*$", text):
            raise ValueError(f"Skill metadata name does not match: {name}")
        for path, data in files.items():
            if path.endswith(".py"):
                ast.parse(data, filename=path)
            relative = target + "/" + path
            local = file_bytes(safe_path(project, relative))
            if local is not None and local != data:
                raise ValueError(f"Existing file differs; nothing installed: {relative}")
            change = change_record(project, relative, data)
            if change:
                changes.append(change)
                print(f"INSTALL {relative}")
        manifest["skills"][name] = {"target": target, "revision": revision,
                                     "files": {path: digest(data) for path, data in files.items()}}
        # These are workflow smoke checks, never a claim of business acceptance.
        smoke = {"change-design": "requirements.py", "project-onboard": "maven_preflight.py"}.get(name)
        if smoke and f"scripts/{smoke}" in files:
            check = {"cwd": ".", "argv": ["{python}", "-B", target + "/scripts/" + smoke, "--help"], "timeout": 120}
            if check not in manifest["checks"]:
                manifest["checks"].append(check)
        if name == "change-design":
            board = file_bytes(safe_path(project, "docs/design/README.md")) or b""
            if "由各需求的 `design.md` 和 `tasks.md` 生成。".encode() in board:
                manifest["checks"].append({"cwd": ".", "argv": ["{python}", "-B", target + "/scripts/requirements.py", "--check"], "timeout": 120})
    if args.checks_file:
        manifest["checks"] = json.loads(args.checks_file.read_text(encoding="utf-8-sig"))
    validate_manifest(project, manifest)
    if not manifest["checks"]:
        raise ValueError("This skill needs explicit validation commands via --checks-file")
    for relative in (["AGENTS.md", "CLAUDE.md"] if args.tool == "claude" or (args.target or "").startswith(".claude/") else ["AGENTS.md"]):
        current = file_bytes(safe_path(project, relative)) or b""
        if ENTRY_MARKER.encode() in current:
            continue
        body = ("\n" + ENTRY_MARKER + "\n## AI 工作流\n\n"
                "安装位置、源版本与检查命令见 `.ai-workflow.json`。按任务需要读取其中登记的 Skill。\n"
                "局部修复保留简短计划和验证记录；若清单启用 change-design，需要独立设计时读取其约定。\n"
                "收到“检查工作流”或“更新工作流”时，从登记上游的独立副本使用 workflow_update.py，\n"
                "先运行 --doctor；更新先预览确定提交，确认无冲突后按已授权范围应用并验证。\n"
                "<!-- /ai-workflow -->\n") if relative == "AGENTS.md" else "\n" + ENTRY_MARKER + "\n@AGENTS.md\n<!-- /ai-workflow -->\n"
        changes.append(change_record(project, relative, current + body.encode("utf-8")))
    after_manifest = json_bytes(manifest)
    if not changes and after_manifest == before_manifest:
        print("Already installed. Use --doctor to inspect local state.")
        return
    changes.append({"path": MANIFEST, "before": pack(before_manifest), "after": pack(after_manifest)})
    if args.dry_run:
        print(f"Installation preview only. Revision: {revision}")
        return
    apply_changes(project, changes, manifest["checks"])
    print("Installation includes workflow smoke checks. Add project acceptance commands when applicable.")


def digest(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None


def path_parts(relative):
    """Validate portable path syntax without consulting a working tree."""
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError(f"Invalid relative path: {relative!r}")
    parts = relative.split("/")
    for part in parts:
        if (part in ("", ".", "..") or part.endswith((".", " "))
                or re.search(r'[<>:"|?*\x00-\x1f]', part)
                or part.casefold() == ".git"
                or re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?", part)):
            raise ValueError(f"Unsafe path: {relative!r}")
    return parts


def safe_path(root, relative):
    """Reject traversal, Windows aliases, and symlinks/junctions before any I/O."""
    parts = path_parts(relative)
    path = root
    for index, part in enumerate(parts):
        path = path / part
        if path.is_symlink() or (path.exists() and getattr(path.lstat(), "st_file_attributes", 0) & 0x400):
            raise ValueError(f"Linked path is not supported: {relative}")
        if index < len(parts) - 1 and path.exists() and not path.is_dir():
            raise ValueError(f"Parent path is not a directory: {relative}")
    path.resolve().relative_to(root)
    return path


def target_path(project, target, name):
    if target not in (f".agents/skills/{name}", f".claude/skills/{name}"):
        raise ValueError(f"Unsupported skill target: {target}")
    return safe_path(project, target)


def file_bytes(path):
    if path.exists() and not path.is_file():
        raise ValueError(f"Expected a regular file: {path}")
    return path.read_bytes() if path.exists() else None


def git(source, *args):
    result = subprocess.run(["git", "-C", str(source), *args], capture_output=True)
    if result.returncode:
        # Do not echo remote URLs or credential-bearing Git diagnostics.
        raise ValueError("Git source could not be read; check the checkout and revision.")
    return result.stdout


def source_files(source, revision, name):
    prefix = f"skills/{name}/"
    files = {}
    folded = set()
    for entry in git(source, "ls-tree", "-rz", revision, "--", prefix).split(b"\0"):
        if not entry:
            continue
        attributes, raw_path = entry.split(b"\t", 1)
        mode, kind, blob = attributes.decode().split()
        if mode != "100644" or kind != "blob":
            raise ValueError("Only regular Git 100644 files are supported; links and executable modes need manual handling.")
        path = raw_path.decode("utf-8")
        if not path.startswith(prefix):
            raise ValueError("Unexpected upstream path")
        relative = path[len(prefix):]
        path_parts(relative)
        if relative.casefold() in folded:
            raise ValueError(f"Case-colliding upstream file: {relative}")
        folded.add(relative.casefold())
        files[relative] = git(source, "cat-file", "blob", blob)
    if "SKILL.md" not in files:
        raise ValueError(f"No SKILL.md in upstream skills/{name}")
    return files


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def write_file(path, data):
    if data is None:
        if path.exists():
            path.unlink()
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    old_mode = stat.S_IMODE(path.stat().st_mode) if path.exists() else None
    descriptor, temporary = tempfile.mkstemp(prefix=".workflow-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if old_mode is not None:
            os.chmod(temporary, old_mode)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def validate_manifest(project, manifest):
    if (not isinstance(manifest, dict) or manifest.get("version") != 1
            or not isinstance(manifest.get("skills"), dict)
            or not isinstance(manifest.get("upstream"), str)
            or not isinstance(manifest.get("checks"), list)):
        raise ValueError("Unsupported workflow manifest")
    for name, entry in manifest["skills"].items():
        if not isinstance(entry, dict):
            raise ValueError("Invalid skill entry")
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name):
            raise ValueError("Invalid skill name")
        target_path(project, entry["target"], name)
        if not re.fullmatch(r"[0-9a-f]{40,64}", entry["revision"]):
            raise ValueError("Invalid source revision")
        if not isinstance(entry["files"], dict):
            raise ValueError("Invalid source file manifest")
        for path, sha in entry["files"].items():
            safe_path(project, entry["target"] + "/" + path)
            if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
                raise ValueError("Invalid source file digest")
    for check in manifest.get("checks", []):
        if not isinstance(check, dict):
            raise ValueError("Invalid validation command")
        if check["cwd"] != ".":
            safe_path(project, check["cwd"])
        if not isinstance(check["argv"], list) or not check["argv"] or any(
                not isinstance(arg, str) or not arg for arg in check["argv"]):
            raise ValueError("Checks require a nonempty argv array")
        if not isinstance(check.get("timeout", 120), int) or check.get("timeout", 120) <= 0:
            raise ValueError("Check timeout must be a positive number of seconds")


def pack(data):
    return base64.b64encode(data).decode("ascii") if data is not None else None


def unpack(data):
    return base64.b64decode(data, validate=True) if data is not None else None


def rollback(project):
    journal_path = safe_path(project, JOURNAL)
    journal = json.loads(journal_path.read_text(encoding="utf-8"))
    changes = journal["changes"]
    # Check ALL files before restoring any. Edits after interruption must survive.
    for change in changes:
        relative = change["path"]
        if relative not in (MANIFEST, "AGENTS.md", "CLAUDE.md") and not re.fullmatch(r"\.(agents|claude)/skills/[a-z0-9-]+/.+", relative):
            raise ValueError("Unexpected recovery path")
        current = file_bytes(safe_path(project, relative))
        if current not in (unpack(change["before"]), unpack(change["after"])):
            raise ValueError(f"Recovery conflict, preserve journal and resolve manually: {relative}")
    for change in reversed(changes):
        write_file(safe_path(project, change["path"]), unpack(change["before"]))
    journal_path.unlink()
    print("Restored files and source versions from before this update.")


def apply_changes(project, changes, checks):
    journal_path = safe_path(project, JOURNAL)
    with journal_path.open("xb") as stream:
        stream.write(json_bytes({"changes": changes}))
        stream.flush()
        os.fsync(stream.fileno())
    try:
        for change in changes:
            path = safe_path(project, change["path"])
            if file_bytes(path) != unpack(change["before"]):
                raise ValueError(f"File changed since preview: {change['path']}")
            if change["path"] != MANIFEST:
                write_file(path, unpack(change["after"]))
        run_checks(project, checks)
        # Checks must be read-only with respect to managed files.
        for change in changes:
            expected = change["before"] if change["path"] == MANIFEST else change["after"]
            if file_bytes(safe_path(project, change["path"])) != unpack(expected):
                raise ValueError(f"Managed file changed during validation: {change['path']}")
        manifest_change = next(change for change in changes if change["path"] == MANIFEST)
        write_file(safe_path(project, MANIFEST), unpack(manifest_change["after"]))
    except BaseException:
        rollback(project)
        raise
    journal_path.unlink()
    print("Update and validation passed; source versions recorded.")


def run(args):
    project = args.project.resolve()
    if not project.is_dir():
        raise ValueError("Project directory does not exist")
    if args.doctor:
        report = doctor(project)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["healthy"] else 1
    if args.rollback:
        rollback(project)
        return
    if safe_path(project, JOURNAL).exists():
        raise ValueError("Unfinished update detected. Run --rollback before another update.")
    if args.source is None:
        raise ValueError("Supply --source pointing to the trusted upstream Git checkout")
    source = args.source.resolve()
    revision = git(source, "rev-parse", "--verify", "--end-of-options", args.revision + "^{commit}").decode().strip()
    origin = git(source, "config", "--get", "remote.origin.url").decode().strip()
    if re.search(r"https?://[^/]*@", origin, re.I) or "?" in origin or "#" in origin:
        raise ValueError("Use an upstream remote URL without embedded credentials or query parameters")
    manifest_path = safe_path(project, MANIFEST)
    before_manifest = file_bytes(manifest_path)
    manifest = json.loads(before_manifest) if before_manifest else {
        "version": 1, "upstream": origin, "skills": {}, "checks": []}
    validate_manifest(project, manifest)
    if manifest["upstream"] != origin:
        raise ValueError("Source remote does not match the registered upstream")
    if args.install:
        if len(set(args.install)) != len(args.install) or (args.target and len(args.install) != 1):
            raise ValueError("Use distinct skill names; --target requires exactly one skill")
        install(project, source, revision, manifest, before_manifest, args)
        return
    if args.register:
        name = args.register
        if not re.fullmatch(r"[a-z0-9]+(?:-[a-z0-9]+)*", name) or name in manifest["skills"]:
            raise ValueError("Invalid or already registered skill name")
        target = args.target or f".agents/skills/{name}"
        target_path(project, target, name)
        files = source_files(source, revision, name)
        for path, data in files.items():
            if file_bytes(safe_path(project, target + "/" + path)) != data:
                raise ValueError(f"Baseline does not match installed file: {target}/{path}")
        manifest["skills"][name] = {"target": target, "revision": revision,
                                     "files": {path: digest(data) for path, data in files.items()}}
        if args.checks_file:
            manifest["checks"] = json.loads(args.checks_file.read_text(encoding="utf-8-sig"))
        validate_manifest(project, manifest)
        write_file(manifest_path, json_bytes(manifest))
        print(f"Registered {name} at {revision}; installed files unchanged.")
        return
    if args.target or args.checks_file:
        raise ValueError("--target and --checks-file require --register")
    if not manifest["skills"]:
        raise ValueError("No registered skills; register the exact installed baseline first")
    changes = []
    conflicts = []
    for name, entry in manifest["skills"].items():
        files = source_files(source, revision, name)
        paths = set(entry["files"]) | set(files)
        if len({path.casefold() for path in paths}) != len(paths):
            raise ValueError(f"Case-only renames need manual resolution: {name}")
        for path in sorted(paths):
            relative = entry["target"] + "/" + path
            local = file_bytes(safe_path(project, relative))
            base = entry["files"].get(path)
            upstream = files.get(path)
            if digest(local) == base:
                if local != upstream:
                    changes.append({"path": relative, "before": pack(local), "after": pack(upstream)})
                    print(f"{'DELETE' if upstream is None else 'UPDATE' if local is not None else 'ADD'} {relative}")
            elif digest(upstream) == base or local == upstream:
                print(f"KEEP LOCAL {relative}")
            else:
                conflicts.append(relative)
        entry["revision"] = revision
        entry["files"] = {path: digest(data) for path, data in files.items()}
    if conflicts:
        raise ValueError("Conflicts; nothing changed:\n" + "\n".join(conflicts))
    after_manifest = json_bytes(manifest)
    if not changes and after_manifest == before_manifest:
        print("Already up to date.")
        return
    changes.append({"path": MANIFEST, "before": pack(before_manifest), "after": pack(after_manifest)})
    print(f"Target revision: {revision}. Preview includes source version metadata.")
    if args.apply:
        if not manifest.get("checks"):
            raise ValueError("Register read-only validation commands in manifest checks before applying")
        apply_changes(project, changes, manifest["checks"])
    else:
        print("Preview only. Review upstream scripts and checks, then use --apply with this exact revision.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--source", type=Path)
    parser.add_argument("--revision", default="HEAD")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--register", metavar="SKILL")
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--rollback", action="store_true")
    mode.add_argument("--install", nargs="+", metavar="SKILL")
    mode.add_argument("--doctor", action="store_true", help="Inspect installation offline without executing checks")
    parser.add_argument("--tool", choices=("codex", "claude"), default="codex")
    parser.add_argument("--dry-run", action="store_true", help="Preview installation; updates preview by default")
    parser.add_argument("--target")
    parser.add_argument("--checks-file", type=Path)
    args = parser.parse_args()
    try:
        if args.dry_run and not args.install:
            raise ValueError("--dry-run requires --install; updates preview by default")
        return run(args) or 0
    except (ValueError, OSError, KeyError, TypeError, SyntaxError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
