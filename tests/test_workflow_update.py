import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "skills/project-onboard/scripts/workflow_update.py"
spec = importlib.util.spec_from_file_location("workflow_update", SCRIPT)
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


class WorkflowUpdateTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.source = self.root / "upstream"
        self.project = self.root / "project"
        self.source.mkdir()
        self.project.mkdir()
        self.git("init", "-q")
        self.git("config", "user.name", "Test")
        self.git("config", "user.email", "test@example.invalid")
        self.git("config", "core.autocrlf", "false")
        self.git("remote", "add", "origin", "https://example.invalid/workflow.git")
        self.upstream = self.source / "skills/example"
        self.upstream.mkdir(parents=True)
        self.installed = self.project / ".agents/skills/example"
        self.installed.mkdir(parents=True)
        for name, data in {"SKILL.md": b"---\nname: example\n---\nv1\n", "old.md": b"old\n", "custom.md": b"base\n"}.items():
            (self.upstream / name).write_bytes(data)
            (self.installed / name).write_bytes(data)
        self.old = self.commit()
        checks = self.root / "checks.json"
        checks.write_text(json.dumps([{"cwd": ".", "argv": ["{python}", "-c", "pass"]}]), encoding="utf-8")
        registered = self.run_update("--register", "example", "--checks-file", str(checks))
        self.assertEqual(registered.returncode, 0, registered.stderr)

    def git(self, *args):
        result = subprocess.run(["git", "-C", str(self.source), *args], capture_output=True, check=True)
        return result.stdout.decode().strip()

    def commit(self):
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")
        return self.git("rev-parse", "HEAD")

    def upgrade(self):
        (self.upstream / "SKILL.md").write_bytes(b"---\nname: example\n---\nv2\n")
        (self.upstream / "new.md").write_bytes(b"new\n")
        (self.upstream / "old.md").unlink()
        return self.commit()

    def run_update(self, *args):
        return subprocess.run(
            [sys.executable, "-B", str(SCRIPT), "--project", str(self.project), "--source", str(self.source), *args],
            capture_output=True, text=True, encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"})

    def snapshot(self):
        return {str(path.relative_to(self.project)): path.read_bytes()
                for path in self.project.rglob("*") if path.is_file()}

    def manifest(self):
        return json.loads((self.project / updater.MANIFEST).read_text(encoding="utf-8"))

    def test_preview_then_update_preserves_customizations_and_project_docs(self):
        new = self.upgrade()
        (self.installed / "custom.md").write_bytes(b"project customization\n")
        (self.installed / "local.md").write_bytes(b"local addition\n")
        (self.project / "AGENTS.md").write_bytes(b"project instructions\n")
        before = self.snapshot()
        preview = self.run_update()
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertEqual(self.snapshot(), before)
        result = self.run_update("--apply", "--revision", new)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse((self.installed / "old.md").exists())
        self.assertEqual((self.installed / "new.md").read_bytes(), b"new\n")
        self.assertEqual((self.installed / "custom.md").read_bytes(), b"project customization\n")
        self.assertEqual((self.installed / "local.md").read_bytes(), b"local addition\n")
        self.assertEqual((self.project / "AGENTS.md").read_bytes(), b"project instructions\n")
        self.assertEqual(self.manifest()["skills"]["example"]["revision"], new)
        after = self.snapshot()
        repeat = self.run_update("--apply")
        self.assertEqual(repeat.returncode, 0, repeat.stderr)
        self.assertEqual(self.snapshot(), after)
        # An upstream edit after keeping a customization must still conflict.
        (self.upstream / "custom.md").write_bytes(b"new upstream customization\n")
        self.commit()
        conflict = self.run_update("--apply")
        self.assertEqual(conflict.returncode, 1)
        self.assertEqual(self.snapshot(), after)

    def test_conflict_and_modified_upstream_deletion_leave_everything_unchanged(self):
        self.upgrade()
        for name in ("SKILL.md", "old.md"):
            with self.subTest(name=name):
                path = self.installed / name
                original = path.read_bytes()
                path.write_bytes(b"local edit\n")
                before = self.snapshot()
                result = self.run_update("--apply")
                self.assertEqual(result.returncode, 1)
                self.assertIn("Conflicts", result.stderr)
                self.assertEqual(self.snapshot(), before)
                path.write_bytes(original)

    def test_failed_validation_restores_files_deletions_and_manifest(self):
        self.upgrade()
        manifest = self.manifest()
        manifest["checks"][0]["argv"] = ["{python}", "-c", "raise SystemExit(7)"]
        (self.project / updater.MANIFEST).write_bytes(updater.json_bytes(manifest))
        before = self.snapshot()
        result = self.run_update("--apply")
        self.assertEqual(result.returncode, 1)
        self.assertIn("exit code 7", result.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_write_failure_rolls_back_previous_writes(self):
        self.upgrade()
        real_write = updater.write_file

        def fail_new(path, data):
            if path.name == "new.md" and data is not None:
                raise OSError("simulated disk failure")
            return real_write(path, data)

        before = self.snapshot()
        argv = [str(SCRIPT), "--project", str(self.project), "--source", str(self.source), "--apply"]
        with patch.object(sys, "argv", argv), patch.object(updater, "write_file", side_effect=fail_new):
            self.assertEqual(updater.main(), 1)
        self.assertEqual(self.snapshot(), before)

    def test_interrupted_update_can_be_recovered_and_later_edits_are_protected(self):
        path = self.installed / "SKILL.md"
        before = path.read_bytes()
        after = b"partial update\n"
        journal = {"changes": [{"path": ".agents/skills/example/SKILL.md",
                                "before": updater.pack(before), "after": updater.pack(after)}]}
        (self.project / updater.JOURNAL).write_bytes(updater.json_bytes(journal))
        path.write_bytes(after)
        blocked = self.run_update("--apply")
        self.assertEqual(blocked.returncode, 1)
        path.write_bytes(b"edit after interruption\n")
        guarded = self.run_update("--rollback")
        self.assertEqual(guarded.returncode, 1)
        self.assertEqual(path.read_bytes(), b"edit after interruption\n")
        path.write_bytes(after)
        restored = self.run_update("--rollback")
        self.assertEqual(restored.returncode, 0, restored.stderr)
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse((self.project / updater.JOURNAL).exists())

    def test_path_escape_and_missing_validation_are_rejected(self):
        self.upgrade()
        original = self.manifest()
        for target in ("../outside", ".agents/skills/example/../other", "docs/design"):
            manifest = json.loads(json.dumps(original))
            manifest["skills"]["example"]["target"] = target
            (self.project / updater.MANIFEST).write_bytes(updater.json_bytes(manifest))
            before = self.snapshot()
            result = self.run_update("--apply")
            self.assertEqual(result.returncode, 1)
            self.assertEqual(self.snapshot(), before)
        original["checks"] = []
        (self.project / updater.MANIFEST).write_bytes(updater.json_bytes(original))
        before = self.snapshot()
        result = self.run_update("--apply")
        self.assertEqual(result.returncode, 1)
        self.assertIn("validation commands", result.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_wrong_source_and_local_addition_collision_are_rejected(self):
        self.upgrade()
        self.git("remote", "set-url", "origin", "https://example.invalid/other.git")
        before = self.snapshot()
        result = self.run_update("--apply")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.snapshot(), before)
        self.git("remote", "set-url", "origin", "https://example.invalid/workflow.git")
        (self.installed / "new.md").write_bytes(b"local new file\n")
        before = self.snapshot()
        result = self.run_update("--apply")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Conflicts", result.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_multiple_skills_are_updated_or_restored_together(self):
        other_source = self.source / "skills/second"
        other_source.mkdir()
        other_target = self.project / ".claude/skills/second"
        other_target.mkdir(parents=True)
        for directory in (other_source, other_target):
            (directory / "SKILL.md").write_bytes(b"second v1\n")
        self.commit()
        registered = self.run_update("--register", "second", "--target", ".claude/skills/second")
        self.assertEqual(registered.returncode, 0, registered.stderr)
        self.upgrade()
        (other_source / "SKILL.md").write_bytes(b"second v2\n")
        self.commit()
        (other_target / "SKILL.md").write_bytes(b"second customized\n")
        before = self.snapshot()
        conflict = self.run_update("--apply")
        self.assertEqual(conflict.returncode, 1)
        self.assertEqual(self.snapshot(), before)
        (other_target / "SKILL.md").write_bytes(b"second v1\n")
        manifest = self.manifest()
        manifest["checks"][0]["argv"] = ["{python}", "-c", "raise SystemExit(3)"]
        (self.project / updater.MANIFEST).write_bytes(updater.json_bytes(manifest))
        before = self.snapshot()
        failed = self.run_update("--apply")
        self.assertEqual(failed.returncode, 1)
        self.assertEqual(self.snapshot(), before)
        manifest["checks"][0]["argv"] = ["{python}", "-c", "pass"]
        (self.project / updater.MANIFEST).write_bytes(updater.json_bytes(manifest))
        success = self.run_update("--apply")
        self.assertEqual(success.returncode, 0, success.stderr)
        self.assertEqual((other_target / "SKILL.md").read_bytes(), b"second v2\n")
        self.assertEqual((self.installed / "new.md").read_bytes(), b"new\n")

    def test_validation_timeout_restores_the_old_version(self):
        self.upgrade()
        manifest = self.manifest()
        manifest["checks"][0].update(argv=["{python}", "-c", "import time; time.sleep(5)"], timeout=1)
        (self.project / updater.MANIFEST).write_bytes(updater.json_bytes(manifest))
        before = self.snapshot()
        result = self.run_update("--apply")
        self.assertEqual(result.returncode, 1)
        self.assertIn("timed out", result.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_directory_collision_is_rejected_before_writes(self):
        self.upgrade()
        (self.installed / "new.md").mkdir()
        (self.installed / "new.md" / "local.txt").write_bytes(b"keep\n")
        before = self.snapshot()
        result = self.run_update("--apply")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.snapshot(), before)

    def test_registration_checks_exact_baseline_without_overwriting_custom_files(self):
        (self.project / updater.MANIFEST).unlink()
        (self.installed / "SKILL.md").write_bytes(b"customized\n")
        before = self.snapshot()
        result = self.run_update("--register", "example")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Baseline does not match", result.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_untracked_source_root_files_do_not_affect_git_object_reads(self):
        (self.upstream / "references").mkdir()
        (self.upstream / "references/a.md").write_bytes(b"reference\n")
        revision = self.commit()
        (self.source / "references").write_bytes(b"unrelated untracked file\n")
        result = self.run_update("--apply", "--revision", revision)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.installed / "references/a.md").read_bytes(), b"reference\n")

    def test_executable_source_is_rejected_instead_of_losing_permissions(self):
        (self.upstream / "tool.sh").write_bytes(b"#!/bin/sh\nexit 0\n")
        self.git("add", ".")
        self.git("update-index", "--chmod=+x", "skills/example/tool.sh")
        self.git("commit", "-qm", "executable fixture")
        before = self.snapshot()
        result = self.run_update("--apply")
        self.assertEqual(result.returncode, 1)
        self.assertIn("executable modes", result.stderr)
        self.assertEqual(self.snapshot(), before)

    def test_install_preview_and_apply_register_exact_git_bytes_and_keep_project_rules(self):
        (self.project / updater.MANIFEST).unlink()
        for path in self.installed.iterdir():
            path.unlink()
        (self.project / "AGENTS.md").write_bytes(b"Existing team rules.\n")
        before = self.snapshot()
        checks = self.root / "checks.json"
        preview = self.run_update("--install", "example", "--checks-file", str(checks), "--dry-run")
        self.assertEqual(preview.returncode, 0, preview.stderr)
        self.assertEqual(self.snapshot(), before)
        installed = self.run_update("--install", "example", "--checks-file", str(checks))
        self.assertEqual(installed.returncode, 0, installed.stderr)
        self.assertEqual(self.manifest()["skills"]["example"]["revision"], self.old)
        self.assertTrue((self.project / "AGENTS.md").read_bytes().startswith(b"Existing team rules.\n"))
        self.assertEqual((self.installed / "SKILL.md").read_bytes(), (self.upstream / "SKILL.md").read_bytes())
        after = self.snapshot()
        repeated = self.run_update("--install", "example")
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        self.assertEqual(self.snapshot(), after)
        inspected = self.run_update("--doctor")
        self.assertEqual(inspected.returncode, 0, inspected.stderr)
        self.assertFalse(json.loads(inspected.stdout)["checks_executed"])

    def test_install_failure_restores_project_instructions_and_missing_manifest(self):
        (self.project / updater.MANIFEST).unlink()
        for path in self.installed.iterdir():
            path.unlink()
        (self.project / "AGENTS.md").write_bytes(b"keep these rules\n")
        checks = self.root / "bad-checks.json"
        checks.write_text(json.dumps([{"cwd": ".", "argv": ["{python}", "-c", "raise SystemExit(9)"]}]), encoding="utf-8")
        before = self.snapshot()
        result = self.run_update("--install", "example", "--checks-file", str(checks))
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.snapshot(), before)

    def test_install_does_not_adopt_unknown_customized_files(self):
        (self.project / updater.MANIFEST).unlink()
        (self.installed / "SKILL.md").write_bytes(b"keep customization\n")
        before = self.snapshot()
        result = self.run_update("--install", "example", "--checks-file", str(self.root / "checks.json"))
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.snapshot(), before)

    def test_doctor_distinguishes_customizations_missing_files_and_interruption(self):
        (self.installed / "custom.md").write_bytes(b"customized\n")
        before = self.snapshot()
        inspected = self.run_update("--doctor")
        self.assertEqual(inspected.returncode, 0)
        report = json.loads(inspected.stdout)
        self.assertEqual(report["skills"]["example"]["modified"], ["custom.md"])
        self.assertEqual(self.snapshot(), before)
        (self.installed / "old.md").unlink()
        (self.project / updater.JOURNAL).write_bytes(b"{}")
        before = self.snapshot()
        inspected = self.run_update("--doctor")
        self.assertEqual(inspected.returncode, 1)
        report = json.loads(inspected.stdout)
        self.assertEqual(report["skills"]["example"]["missing"], ["old.md"])
        self.assertTrue(any("Unfinished" in error for error in report["errors"]))
        self.assertEqual(self.snapshot(), before)

    def test_claude_install_creates_discoverable_entry_without_overwriting_rules(self):
        (self.project / updater.MANIFEST).unlink()
        (self.project / "CLAUDE.md").write_bytes(b"Existing Claude rules.\n")
        result = self.run_update("--install", "example", "--tool", "claude", "--checks-file", str(self.root / "checks.json"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.manifest()["skills"]["example"]["target"], ".claude/skills/example")
        self.assertTrue((self.project / "CLAUDE.md").read_bytes().startswith(b"Existing Claude rules.\n"))
        self.assertIn(b"@AGENTS.md", (self.project / "CLAUDE.md").read_bytes())

    def test_doctor_resolves_relative_commands_in_the_check_working_directory(self):
        module = self.project / "module"
        module.mkdir()
        command = module / ("check.cmd" if os.name == "nt" else "check.sh")
        command.write_text("@exit /b 0\n" if os.name == "nt" else "#!/bin/sh\nexit 0\n", encoding="utf-8")
        command.chmod(0o755)
        manifest = self.manifest()
        manifest["checks"] = [{"cwd": "module", "argv": ["./" + command.name]}]
        (self.project / updater.MANIFEST).write_bytes(updater.json_bytes(manifest))
        inspected = self.run_update("--doctor")
        self.assertEqual(inspected.returncode, 0, inspected.stderr + inspected.stdout)
        updater.run_checks(self.project, manifest["checks"])


if __name__ == "__main__":
    unittest.main()
