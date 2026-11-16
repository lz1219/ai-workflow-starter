"""Preview and transactionally update registered, repository-local skills.

Uses an explicitly supplied Git checkout; fetching and choosing a trusted revision
remain the caller's responsibility. Python standard library and Git only.
"""

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile


MANIFEST = ".ai-workflow.json"
JOURNAL = ".ai-workflow-transaction.json"


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
        if relative != MANIFEST and not re.fullmatch(r"\.(agents|claude)/skills/[a-z0-9-]+/.+", relative):
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
        for check in checks:
            cwd = project if check["cwd"] == "." else safe_path(project, check["cwd"])
            argv = [sys.executable if arg == "{python}" else arg for arg in check["argv"]]
            result = subprocess.run(argv, cwd=cwd, timeout=check.get("timeout", 120))
            if result.returncode:
                raise ValueError(f"Validation failed with exit code {result.returncode}")
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
    parser.add_argument("--target")
    parser.add_argument("--checks-file", type=Path)
    args = parser.parse_args()
    try:
        run(args)
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
